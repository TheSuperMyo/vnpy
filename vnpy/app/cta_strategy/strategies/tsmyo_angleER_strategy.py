from datetime import time
from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager
)
from vnpy.app.cta_strategy.base import (
    EngineType,
    STOPORDER_PREFIX,
    StopOrder,
    StopOrderStatus,
)
from vnpy.app.cta_strategy.TSMtools import TSMArrayManager
import numpy as np

class TSMyoAngleERStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    # 日内交易
    exit_time = time(hour=14, minute=57)
    # 针对不同交易时间的市场
    open_time_night = time(hour=21,minute=0)# 商品夜盘
    open_time_day_1 = time(hour=9,minute=0)# 商品
    open_time_day_2 = time(hour=9,minute=30)# 股指

    close_time_day = time(hour=15,minute=0)# 商品/股指（除了利率期货）
    close_time_night_1 = time(hour=23,minute=0)# 其他夜盘商品
    close_time_night_2 = time(hour=1,minute=0)# 工业金属
    close_time_night_3 = time(hour=2,minute=30)# 黄金/白银/原油
    
    break_time_start_1 = time(hour=10,minute=15)# 商品茶歇
    break_time_start_2 = time(hour=11,minute=30)# 全体午休
    break_time_end_1 = time(hour=10,minute=30)# 商品茶歇
    break_time_end_2 = time(hour=13,minute=0)# 股指下午
    break_time_end_3 = time(hour=13,minute=30)# 商品下午

    setup_bar = 50 # 基础拟合分钟数
    open_bar_1 = 50 # 开仓时点1
    open_bar_2 = 150 # 开仓时点2
    angle_fliter = 0.2 # 角度过滤
    er_fliter = 0.35 # er过滤

    trailing_stop = 0.45 # 跟踪止损
    fixed_size = 1 # 固定手数

    bar_counter = 0 # 每日分钟计数器
    er_value = 0 
    angle_value = 0

    stop_long = 0
    stop_short = 0
    hold_high = 0
    hold_low = 0
    
    parameters = ['open_bar_1','open_bar_2','angle_fliter','setup_bar','trailing_stop','fixed_size']
    variables = ['bar_counter','er_value','angle_value','stop_long','stop_short']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoAngleERStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar)
        # 股指每天240分钟
        self.am = TSMArrayManager(240)
        # 策略自身订单管理
        self.active_orderids = []
        self.bars = []

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        # 不会用到昨日数据
        self.load_bar(5)
        
    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    def tick_filter(self, tick: TickData):
        """
        过滤异常时间的tick
        """
        tick_time = tick.datetime.time()
        if tick_time < self.open_time_day_2:
            return False
        if tick_time > self.break_time_start_2 and tick_time < self.break_time_end_2:
            return False
        if tick_time > self.close_time_day:
            return False
        
        return True

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        if not self.tick_filter(tick):
            return
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        1.分钟计数
        2.挂撤单
        """
        self.bar_counter += 1

        self.cancel_all()

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        
        last_bar = self.bars[-2]

        if ( last_bar.datetime.date() != bar.datetime.date() ):
            self.bar_counter = 1

        self.er_value = am.er(self.setup_bar, False)
        self.angle_value = am.angle(self.setup_bar, False)

        if self.pos == 0 and (self.bar_counter == self.open_bar_1 or self.bar_counter == self.open_bar_2):
            if self.angle_value > self.angle_fliter and self.er_value > self.er_fliter:
                # 入场开多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.buy(bar.high_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)

            if self.angle_value < -self.angle_fliter and self.er_value > self.er_fliter:
                # 入场开空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.short(bar.low_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)

        if self.pos > 0:
            self.hold_high = max(self.hold_high,bar.high_price)
            self.stop_long = self.hold_high*(1-self.trailing_stop/100)

            if bar.datetime.time() > self.exit_time:
                # 日内平仓
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)
            else:
                # 停止单平多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(self.stop_long, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

        if self.pos < 0:
            self.hold_low = min(self.hold_low,bar.low_price)
            self.stop_short = self.hold_low*(1+self.trailing_stop/100)

            if bar.datetime.time() > self.exit_time:
                # 日内平仓
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)
            else:
                # 停止单平空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(self.stop_short, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)        

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        # 移除已成交或已撤销的订单
        if not order.is_active() and order.vt_orderid in self.active_orderids:
            self.active_orderids.remove(order.vt_orderid)

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        # 邮寄提醒
        self.send_email(f"{trade.vt_symbol}在{trade.time}成交，价格{trade.price}，方向{trade.direction}{trade.offset}，数量{trade.volume}")
        if self.pos == 0:
            self.stop_long = 0
            self.stop_short = 0
        if self.pos > 0:
            self.hold_high = trade.price
        if self.pos < 0:
            self.hold_low = trade.price
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        # 刚刚生成的本地停止单
        if stop_order.status == StopOrderStatus.WAITING:
            return
        # 撤销的本地停止单，从活跃列表移除
        if stop_order.status == StopOrderStatus.CANCELLED:
            if stop_order.stop_orderid in self.active_orderids:
                self.active_orderids.remove(stop_order.stop_orderid)
        # 触发的本地停止单，停止单移除，限价单加入
        if stop_order.status == StopOrderStatus.TRIGGERED:
            if stop_order.stop_orderid in self.active_orderids:
                self.active_orderids.remove(stop_order.stop_orderid)
                self.active_orderids.extend(stop_order.vt_orderids)
            # 撤掉其他停止单
            for other_orderids in self.active_orderids:
                if other_orderids.startswith(STOPORDER_PREFIX):
                    self.cancel_order(other_orderids)