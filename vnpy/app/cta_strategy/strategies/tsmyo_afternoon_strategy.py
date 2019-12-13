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

class TSMyoAfternoonStrategy(CtaTemplate):
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

    # 入场信号
    bn_high = 0
    bn_low = 0
    range_wide = 0.25
    an_r = 0
    an_s = 0
    signal = 0

    # 一般
    fixed_size = 1
    intra_trade_high = 0
    intra_trade_low = 0
    trailing_stop = 0.5
    atr_stop = 2.5
    atr_value = 0
    atr_ma_len = 10
    atr_window = 16

    parameters = ['range_wide','atr_ma_len','atr_window','fixed_size','trailing_stop','atr_stop']
    variables = ['bn_high','bn_low','an_r','an_s','signal']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoAfternoonStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg15 = BarGenerator(self.on_bar, 15, self.on_15min_bar)
        self.am = TSMArrayManager(50)
        # 策略自身订单管理
        self.active_orderids = []
        self.bars = []

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        # 根据需要的历史数据长度设定
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

        self.bg15.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        1.记录午前最高最低价
        2.计算午后R/S价位
        3.根据信号发单
        4.负责日内平仓
        5.am使用1min周期
        """

        self.bg15.update_bar(bar)

        self.cancel_all()

        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        
        last_bar = self.bars[-2]
        # 今日开盘
        if last_bar.datetime.date() != bar.datetime.date():
            self.bn_high = bar.high_price
            self.bn_low = bar.low_price

        # 午前
        if bar.datetime.time() < self.break_time_start_2:
            if self.bn_low:
                self.bn_high = max(self.bn_high, bar.high_price)
                self.bn_low = min(self.bn_low, bar.low_price)
        
        # 午后开盘
        if not (bar.datetime.time()<self.break_time_end_2) and last_bar.datetime.time()<self.break_time_end_2:
            # 计算R/S价位
            if self.bn_low:
                self.an_r = self.bn_high - self.range_wide * (self.bn_high - self.bn_low)
                self.an_s = self.bn_low + self.range_wide * (self.bn_high - self.bn_low)
                self.write_log(f"今日午后R/S: {self.an_r} / {self.an_s}")

        # 午后挂单
        if bar.datetime.time()>self.break_time_end_2 and bar.datetime.time()<self.exit_time:
            if self.pos == 0:
                self.intra_trade_high = bar.high_price
                self.intra_trade_low = bar.low_price
                if self.signal == 1:
                    # 开多
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.buy(bar.close_price, self.fixed_size, lock=True)
                    self.active_orderids.extend(orderids)
                if self.signal == -1:
                    # 开空
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.short(bar.close_price, self.fixed_size, lock=True)
                    self.active_orderids.extend(orderids)

            if self.pos > 0:
                # 移动止损
                self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                # 固定比率
                #orderids = self.sell(self.intra_trade_high*(1-self.trailing_stop/100), self.fixed_size, True, True)
                # ATR
                #orderids = self.sell(self.intra_trade_high - (self.atr_stop*self.atr_value), self.fixed_size, True, True)
                # 固定比率 & ATR
                stop_long = max(self.intra_trade_high*(1-self.trailing_stop/100), self.intra_trade_high - (self.atr_stop*self.atr_value))
                orderids = self.sell(stop_long, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

                # # 正反手
                # if self.signal == -1:
                #     # 平多开空
                #     if self.active_orderids:
                #         self.write_log("撤单不干净，无法挂单")
                #         return
                #     orderids = self.sell(bar.close_price, self.fixed_size, lock=True)
                #     self.active_orderids.extend(orderids)
                #     orderids = self.short(bar.close_price, self.fixed_size, lock=True)
                #     self.active_orderids.extend(orderids)

            if self.pos < 0:
                # 移动止损
                self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                # 固定比率    
                #orderids = self.cover(self.intra_trade_low*(1+self.trailing_stop/100), self.fixed_size, True, True)
                # ATR
                #orderids = self.cover(self.intra_trade_low + (self.atr_stop*self.atr_value), self.fixed_size, True, True)
                # 固定比率 & ATR
                stop_short = min(self.intra_trade_low*(1+self.trailing_stop/100), self.intra_trade_low + (self.atr_stop*self.atr_value))
                orderids = self.cover(stop_short, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

                # # 正反手
                # if self.signal == 1:
                #     # 平空开多
                #     if self.active_orderids:
                #         self.write_log("撤单不干净，无法挂单")
                #         return
                #     orderids = self.cover(bar.close_price, self.fixed_size, lock=True)
                #     self.active_orderids.extend(orderids)
                #     orderids = self.buy(bar.close_price, self.fixed_size, lock=True)
                #     self.active_orderids.extend(orderids)

        # 日内平仓
        if bar.datetime.time() > self.exit_time:
            if self.pos > 0:
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price, abs(self.pos), lock=True)
                self.active_orderids.extend(orderids)

            elif self.pos < 0:
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price, abs(self.pos), lock=True)
                self.active_orderids.extend(orderids)
        
        self.put_event()

    def on_15min_bar(self, bar: BarData):
        """
        1.根据R/S及最高最低价发出信号
        2.根据ATR与ATRM进行过滤
        """
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 重置信号
        self.signal = 0
        # 波动率过滤
        atr_array = am.atr(self.atr_window, True)
        self.atr_value = atr_array[-1]
        atr_ma = atr_array[-self.atr_ma_len:].mean()

        # 午后
        if bar.datetime.time()>self.break_time_end_2 and self.an_r and self.atr_value>atr_ma:
            if bar.close_price > self.an_r and bar.close_price < self.bn_high:
                # 空
                self.signal = -1
            if bar.close_price > self.bn_high:
                # 多
                self.signal = 1
            if bar.close_price < self.an_s and bar.close_price > self.bn_low:
                # 多
                self.signal = 1
            if bar.close_price < self.bn_low:
                # 空
                self.signal = -1

        self.put_event()

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