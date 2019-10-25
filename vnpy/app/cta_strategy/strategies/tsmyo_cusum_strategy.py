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
import numpy as np

class TSMyoCusumStrategy(CtaTemplate):
    """"""

    author = 'TheSuperMyo'

    cs_len = 30
    cs_h_std = 5.0
    cs_k_std = 1 
    stop_loss = 0.618
    fixed_size = 1

    cs_max = 0
    cs_min = 0
    ma = []
    ma_rets_std = []
    trigger = 0
    logr = 0
    intra_trade_high = 0
    intra_trade_low = 0
    intra_trade_open = 0

    parameters = ['cs_len', 'cs_h_std','cs_k_std', 'fixed_size','stop_loss']
    variables = ['intra_trade_high','intra_trade_low']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoCusumStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )

        self.bg = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.am = ArrayManager()
        self.ma = []
        self.ma_rets_std = []

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
        """
        Callback of new bar data update.
        """
        # 在1分钟周期交易
        self.bg.update_bar(bar)
        self.cancel_all()

        if self.pos == 0 :
            # 最近的5分周期出现向上变点
            if self.trigger == 1:
                self.buy(bar.close_price, self.fixed_size)
            
            elif self.trigger == -1:
                self.short(bar.close_price, self.fixed_size)

            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price

        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            self.intra_trade_low = bar.low_price
            # 止损（可选）
            self.sell(self.intra_trade_open * (1 - self.stop_loss / 100),abs(self.pos),True)
            # 出现向下变点，平多仓
            if self.trigger == -1:
                self.sell(bar.close_price,abs(self.pos))
                # 直接反手（可选）
                #self.short(bar.close_price, self.fixed_size)

        elif self.pos < 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)

            # 止损（可选）
            self.cover(self.intra_trade_open * (1 + self.stop_loss / 100),abs(self.pos),True)
            # 出现向上变点，平空仓
            if self.trigger == 1:
                self.cover(bar.close_price,abs(self.pos))
                # 直接反手（可选）
                #self.buy(bar.close_price, self.fixed_size)

        self.put_event()

    def on_5min_bar(self, bar: BarData):
        """"""
        # 基于5分钟周期计算变点

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.ma = am.sma(self.cs_len,True)
        self.ma_rets_std = am.ma_rets_std(self.cs_len,True)
        self.logr = np.log(bar.close_price/self.ma[-2])

        self.cs_max += max(self.logr - self.cs_k_std*self.ma_rets_std[-2], 0)
        self.cs_min += min(self.logr + self.cs_k_std*self.ma_rets_std[-2], 0)

        if self.cs_max > self.cs_h_std*self.ma_rets_std[-2]:
            self.trigger = 1
            self.cs_max = 0

        elif abs(self.cs_min) > self.cs_h_std*self.ma_rets_std[-2]:
            self.trigger = -1
            self.cs_min = 0

        self.put_event()

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        # 成交后将变点复位
        self.trigger == 0
        if trade.offset == "开":
            self.intra_trade_open = trade.price
        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass