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

class TSMyoFHBKStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    # 日内交易
    exit_time = time(hour=14, minute=54)
    fh_time = time(hour=10, minute=1)


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

    fh_high = 0
    fh_low = 0

    long_entry = 0
    short_entry = 0
    stop_long = 0
    stop_short = 0
    hold_long = 0
    hold_short = 0

    rsi_filter = 20
    mrocprsi = 0
    m_len = 16
    rocp_len = 1
    rsi_len = 3
    td_trend = 0

    open_sell = 0
    open_cover = 0

    fixed_size = 1
    
    parameters = ['rsi_filter','m_len','rocp_len','rsi_len','fixed_size']
    variables = ['fh_high','fh_low','mrocprsi','td_trend']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoFHBKStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar, 15, self.on_15min_bar)
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
        self.load_bar(10)
        
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
        1.根据信号挂单
        """
        self.bg.update_bar(bar)

        self.cancel_all()

        if self.pos == 0:
            self.hold_long = 0
            self.hold_short = 0
            if self.long_entry:
                # 入场开多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.buy(self.long_entry, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

            if self.short_entry:
                # 入场开空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.short(self.short_entry, self.fixed_size, True, True)
                self.active_orderids.extend(orderids)

        if self.pos > 0:
            # 开多后记录成本，开多信号归零
            if self.long_entry:
                self.hold_long = self.long_entry
                self.long_entry = 0

            if self.open_sell == 1:
                # 开盘平多信号
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)
            else:
                if bar.datetime.time() < self.exit_time:
                    # 停止单平多
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.sell(self.stop_long, self.fixed_size, True, True)
                    self.active_orderids.extend(orderids)
                elif bar.close_price < self.hold_long:
                    # 收盘前持仓亏损平多（否则持仓过夜）
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.sell(bar.close_price, self.fixed_size, False, True)
                    self.active_orderids.extend(orderids)

        if self.pos < 0:
            # 开空后记录成本，开空信号归零
            if self.short_entry:
                self.hold_short = self.short_entry
                self.short_entry = 0

            if self.open_cover == 1:
                # 开盘平空信号
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price, self.fixed_size, False, True)
                self.active_orderids.extend(orderids)
            else:
                if bar.datetime.time() < self.exit_time:
                    # 停止单平空
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.cover(self.stop_short, self.fixed_size, True, True)
                    self.active_orderids.extend(orderids)
                elif bar.close_price > self.hold_short:
                    # 收盘前持仓亏损平空（否则持仓过夜）
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.cover(bar.close_price, self.fixed_size, False, True)
                    self.active_orderids.extend(orderids)

    def on_15min_bar(self, bar: BarData):
        """
        1.计算MROCPRSI指标，过滤交易日
        2.产生信号（相关交易价位）
        """
        # for backtest
        self.cta_engine.output(f"{bar.datetime.time()}")
        self.write_log(f"{bar.datetime.time()}")

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
        # 开盘bar
        if last_bar.datetime.date() != bar.datetime.date():
            # 初始化
            self.td_trend = 0

            self.open_sell = 0
            self.open_cover = 0

            self.fh_high = bar.high_price
            self.fh_low = bar.low_price
            # 开盘有利平仓
            if self.pos > 0 and bar.close_price > last_bar.close_price:
                # 开盘平多信号
                self.open_sell = 1
            if self.pos < 0 and bar.close_price < last_bar.close_price:
                # 开盘平空信号
                self.open_cover = 1

            # 过滤并决定方向
            self.mrocprsi = am.mom_rocp_rsi(self.m_len,self.rocp_len,self.rsi_len,True)[-2]

            if self.mrocprsi > (50+self.rsi_filter):
                self.td_trend = -1
            if self.mrocprsi < (50-self.rsi_filter):
                self.td_trend = 1

        if self.pos == 0:
            # 确定今日从未持仓
            if self.td_trend != 0 and self.open_sell==0 and self.open_cover==0:
                # 如果今日可以操作且仍在fh内，则记录
                if bar.datetime.time() < self.fh_time:
                    self.fh_high = max(self.fh_high,bar.high_price)
                    self.fh_low = min(self.fh_low,bar.low_price)
                # 入场
                elif bar.datetime.time() > self.fh_time:
                    if self.td_trend > 0 :
                        # 停止单开多
                        self.long_entry = self.fh_high
                        self.short_entry = 0
                        self.stop_long = self.fh_low
                        self.stop_short = 0
                    if self.td_trend < 0 :
                        # 停止单开空
                        self.long_entry = 0
                        self.short_entry = self.fh_low
                        self.stop_long = 0
                        self.stop_short = self.fh_high
        

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