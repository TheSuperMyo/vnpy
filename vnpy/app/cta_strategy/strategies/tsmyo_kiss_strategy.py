from datetime import time
from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from vnpy.app.cta_strategy.base import (
    BacktestingMode,
    EngineType,
    STOPORDER_PREFIX,
    StopOrder,
    StopOrderStatus,
    INTERVAL_DELTA_MAP
)
from vnpy.app.cta_strategy.TSMtools import TSMArrayManager


class TSMyoKISSStrategy(CtaTemplate):
    """
    Keep it super sample
    """

    author = "TheSuperMyo"

    fixed_size = 1
    target_atr = 3

    atr_stop = 4
    atr_window = 30
    ma_len = 5

    intra_trade_high = 0
    intra_trade_low = 0

    day_high = 0
    day_low = 0


    atr_value = 0
    ma_value = 0
    trend = 0

    exit_time = time(hour=15, minute=11)

    parameters = ["target_atr", "fixed_size","atr_stop","atr_window","ma_len"]
    variables = ["atr_value","ma_value","trend"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoKISSStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar,5,self.on_5min_bar)
        self.am = TSMArrayManager(400)
        self.bars = []
        self.vt_orderids = []

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
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

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        self.bg.update_bar(bar)
    def on_5min_bar(self, bar: BarData):
        """
        Callback of new bar data update.
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
            self.day_high = bar.high_price
            self.day_low = bar.low_price
        else:
            self.day_high = max(bar.high_price, self.day_high)
            self.day_low = min(bar.low_price, self.day_low)

        #if self.bar_counter < max(self.ma_len,self.atr_window):
            #return

        # ATR相关指标
        self.atr_value = am.atr(self.atr_window, False)
        self.ma_value = am.sma(self.ma_len, False)
        self.trend = am.sma(self.ma_len*10, False) 
        
        # 交易时间
        if (bar.datetime.time() < self.exit_time):
            if self.pos == 0:
                self.intra_trade_low = bar.low_price
                self.intra_trade_high = bar.high_price
                
                if bar.close_price > self.ma_value and bar.close_price > self.trend:     
                    if self.vt_orderids:
                        self.write_log("撤单不干净或达到交易限制，无法挂单")
                        return
                    orderids = self.buy(bar.close_price, self.fixed_size, stop=False, lock=False)
                    self.vt_orderids.extend(orderids)

                elif bar.close_price < self.ma_value and bar.close_price < self.trend:
                    if self.vt_orderids:
                        self.write_log("撤单不干净或达到交易限制，无法挂单")
                        return
                    orderids = self.short(bar.close_price, self.fixed_size, stop=False, lock=False)
                    self.vt_orderids.extend(orderids)

            elif self.pos > 0:
                if bar.close_price > self.ma_value + self.target_atr*self.atr_value:
                    # 主动止盈
                    if self.vt_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.sell(bar.close_price, abs(self.pos), stop=False, lock=False)
                    self.vt_orderids.extend(orderids)
                else:
                    # 跟踪止损出场（ATR）
                    self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                    #long_stop = max(self.ma_value, self.intra_trade_high-self.atr_stop*self.atr_value)
                    long_stop = self.ma_value - self.atr_stop*self.atr_value
                    if self.vt_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.sell(long_stop, abs(self.pos), stop=True, lock=False)
                    self.vt_orderids.extend(orderids)

            elif self.pos < 0:
                if bar.close_price < self.ma_value - self.target_atr*self.atr_value:
                    if self.vt_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.cover(bar.close_price, abs(self.pos), stop=False, lock=False)
                    self.vt_orderids.extend(orderids)
                else:    
                    self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                    #short_stop = min(self.ma_value, self.intra_trade_low+self.atr_stop*self.atr_value)
                    short_stop = self.ma_value+self.atr_stop*self.atr_value
                    if self.vt_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.cover(short_stop, abs(self.pos), stop=True, lock=False)
                    self.vt_orderids.extend(orderids)
        
        # 日内策略，最后不断尝试平仓
        else:
            if self.pos > 0:
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price, abs(self.pos), lock=False)
                self.vt_orderids.extend(orderids)

            elif self.pos < 0:
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price, abs(self.pos), lock=False)
                self.vt_orderids.extend(orderids)
                
        self.put_event()
        
    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        # 移除成交或撤销的订单
        if not order.is_active() and order.vt_orderid in self.vt_orderids:
            self.vt_orderids.remove(order.vt_orderid)

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.send_email(f"{trade.vt_symbol}在{trade.time}成交，价格{trade.price}，方向{trade.direction}{trade.offset}，数量{trade.volume}")
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        # 根据状态处理
        # 刚刚生成的本地停止单
        if stop_order.status == StopOrderStatus.WAITING:
            return
        # 撤销的本地停止单，从列表移除
        if stop_order.status == StopOrderStatus.CANCELLED:
            if  stop_order.stop_orderid in self.vt_orderids:
                self.vt_orderids.remove(stop_order.stop_orderid)
        # 触发的本地停止单，停止单移除，限价单加入
        if stop_order.status == StopOrderStatus.TRIGGERED:
            if  stop_order.stop_orderid in self.vt_orderids:
                self.vt_orderids.remove(stop_order.stop_orderid)
                self.vt_orderids.extend(stop_order.vt_orderids)
            # 撤掉其他停止单
            for other_stop_orderids in self.vt_orderids:
                if other_stop_orderids.startswith(STOPORDER_PREFIX):
                    self.cancel_order(other_stop_orderids)