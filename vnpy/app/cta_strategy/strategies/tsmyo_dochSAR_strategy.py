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

class TSMyoDochSARStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    # 日内交易
    exit_time = time(hour=14, minute=56)
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

    fit_bar = 3 # K线周期
    offset_bar = 2 # 入场极值偏移
    setup_bar = 85 # 基础拟合分钟数
    end_window = 95 # 时间窗口分钟数

    trailing_stop = 0.45 # 跟踪止损
    fixed_size = 1 # 固定手数

    bar_counter = 0 # 每日分钟计数器
    add_counter = 0 # 每日计算极值数据变长计数器

    SAR_stop_long = 0
    SAR_stop_short = 0
    AF = 0

    long_entry = 0 
    short_entry = 0
    long_exit = 0 
    short_exit = 0  
    hold_high = 0
    hold_low = 0
    
    parameters = ['offset_bar','end_window','setup_bar','fit_bar','fixed_size']
    variables = ['bar_counter','add_counter','SAR_stop_long','SAR_stop_short','AF','hold_high','hold_low']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoDochSARStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar, self.fit_bar, self.on_fit_bar)
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
        2.根据信号挂单
        3.计算SAR系统止损点位
        """
        self.bar_counter += 1
        if self.bar_counter > self.setup_bar:
            self.add_counter += 1
        self.bg.update_bar(bar)

        self.cancel_all()

        if self.pos == 0 and bar.datetime.time() < self.exit_time:
            if self.long_entry:
                # 入场开多，收盘价
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.buy(bar.close_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)

            if self.short_entry:
                # 入场开空，收盘价
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.short(bar.close_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)

        if self.pos > 0:
            old_high = self.hold_high
            self.hold_high = max(self.hold_high,bar.high_price)
            if old_high - self.hold_high != 0:
                self.AF += 0.01
                self.AF = min(self.AF,0.1)

            self.SAR_stop_long = self.SAR_stop_long + (self.hold_high-self.SAR_stop_long)*self.AF
            #self.stop_long = self.hold_high*(1-self.trailing_stop/100)

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
                orderids = self.sell(self.SAR_stop_long, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

        if self.pos < 0:
            old_low = self.hold_low
            self.hold_low = min(self.hold_low,bar.low_price)
            if old_low - self.hold_low != 0:
                self.AF += 0.01
                self.AF = min(self.AF,0.1)

            self.SAR_stop_short = self.SAR_stop_short - (self.SAR_stop_short-self.hold_low)*self.AF

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
                orderids = self.cover(self.SAR_stop_short, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

    def on_fit_bar(self, bar: BarData):
        """
        1.负责每日开盘的初始化
        2.计算极值并产生信号
        """
        # self.cta_engine.output(f"{bar.datetime.time()}")
        # self.write_log(f"{bar.datetime.time()}")

        am = self.am
        am.update_bar(bar)

        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        
        last_bar = self.bars[-2]
        # 开盘fit_min_bar
        if last_bar.datetime.date() != bar.datetime.date():
            # 初始化
            self.bar_counter = self.fit_bar
            self.add_counter = 0
            self.long_entry = 0 
            self.short_entry = 0
            self.long_exit = 0 
            self.short_exit = 0
            self.SAR_stop_long = 0
            self.SAR_stop_short = 0

        if self.bar_counter < self.setup_bar:
            return
        
        up_array, down_array = am.donchian(int((self.bar_counter+self.add_counter)/self.fit_bar))
        up = up_array[-1-self.offset_bar]
        down = down_array[-1-self.offset_bar]

        if self.pos == 0 and self.bar_counter < self.end_window:
            if bar.close_price > up:
                # 向上突破，开多信号
                self.long_entry = 1 
                self.short_entry = 0
                self.long_exit = 0 
                self.short_exit = 0
                # 抛物线初始止损点
                self.SAR_stop_long = bar.low_price

            if bar.close_price < down:
                # 向下突破，开空信号
                self.long_entry = 0 
                self.short_entry = 1
                self.long_exit = 0 
                self.short_exit = 0
                # 抛物线初始止损点
                self.SAR_stop_short = bar.high_price
        

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
        self.long_entry = 0 
        self.short_entry = 0
        self.long_exit = 0 
        self.short_exit = 0
        if self.pos == 0:
            self.SAR_stop_long = 0
            self.SAR_stop_short = 0
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