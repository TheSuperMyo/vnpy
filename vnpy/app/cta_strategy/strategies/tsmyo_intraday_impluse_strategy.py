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

class TSMyoIntradayImpluseStrategy(CtaTemplate):
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

    impluse_mul = 6
    atr_len =  30
    target_mul = 2.1
    stop_loss_mul = 0.7

    trailing_stop = 1.2 # 跟踪止损
    fixed_size = 1 # 固定手数

    intra_bar_range = 0 

    stop_long = 0
    stop_short = 0
    target_long = 0
    target_short = 0
    hold_high = 0
    hold_low = 0
    
    parameters = ['impluse_mul','target_mul','atr_len','stop_loss_mul','trailing_stop','fixed_size']
    variables = ['target_long','target_short','stop_long','stop_short','intra_bar_range']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoIntradayImpluseStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar)
        self.am = TSMArrayManager()
        # 策略自身订单管理
        self.active_orderids = []
        self.bars = []

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
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
        1.挂停止单等待基于ATR倍数的冲击来临
        2.基于冲击倍数设置止盈
        3.冲击完全抹平止损并设置有单笔最大亏损上限
        4.日内平仓
        """
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
            self.intra_bar_range = 0
            self.hold_high = 0
            self.hold_low = 0
            self.stop_long = 0
            self.stop_short = 0
            self.target_long = 0
            self.target_short = 0
        
        atr_value = am.atr(self.atr_len, False)
        up = bar.close_price + self.impluse_mul * atr_value
        down = bar.close_price - self.impluse_mul * atr_value

        # 可交易时间
        if bar.datetime.time() < self.exit_time:
            if self.pos == 0:
                # 上下轨挂单
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.buy(up, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)
                orderids = self.short(down, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

            if self.pos > 0:
                # 在这个 bar 入场的
                if self.intra_bar_range == 0:
                    self.intra_bar_range = bar.high_price - bar.low_price
                    self.target_long = bar.close_price + self.target_mul * self.intra_bar_range
                self.hold_high = max(self.hold_high,bar.high_price)
                self.stop_long = max(self.hold_high*(1-self.trailing_stop/100), self.hold_high-self.stop_loss_mul*self.intra_bar_range)

                # 多头止盈
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(self.target_long, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)
                # 停止单平多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(self.stop_long, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

            if self.pos < 0:
                # 在这个 bar 入场的
                if self.intra_bar_range == 0:
                    self.intra_bar_range = bar.high_price - bar.low_price
                    self.target_short = bar.close_price - self.target_mul * self.intra_bar_range
                self.hold_low = min(self.hold_low,bar.low_price)
                self.stop_short = min(self.hold_low*(1+self.trailing_stop/100), self.hold_low+self.stop_loss_mul*self.intra_bar_range)
                
                # 空头止盈
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(self.target_short, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)
                # 停止单平空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(self.stop_short, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)        
        # 日内平仓
        else:
            if self.pos > 0:
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price * 0.995, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)

            if self.pos < 0:
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price * 1.005, self.fixed_size, False, True)
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
            self.intra_bar_range = 0
            self.hold_high = 0
            self.hold_low = 0
            self.stop_long = 0
            self.stop_short = 0
            self.target_long = 0
            self.target_short = 0
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