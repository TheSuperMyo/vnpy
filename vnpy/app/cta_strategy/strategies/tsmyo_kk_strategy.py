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


class TsmyoKKStrategy(CtaTemplate):
    """"""

    author = '用Python的交易员'

    kk_length = 11
    kk_dev = 1.6
    trailing_percent = 0.8
    fixed_size = 1

    kk_up = 0
    kk_down = 0
    kk_ma = 0
    intra_trade_high = 0
    intra_trade_low = 0

    long_vt_orderids = []
    short_vt_orderids = []
    vt_orderids = []

    parameters = ['kk_length', 'kk_dev', 'fixed_size']
    variables = ['kk_up', 'kk_down']

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TsmyoKKStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )

        self.bg = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.am = ArrayManager()

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
        self.bg.update_bar(bar)

    def on_5min_bar(self, bar: BarData):
        """"""
        # 把所有委托单撤单
        self.cancel_all()

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.kk_up, self.kk_down = am.keltner(self.kk_length, self.kk_dev)
        self.kk_ma = am.sma(self.kk_length)

        if self.pos == 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price
            # 同时挂上下轨停止单
            self.long_vt_orderids = self.buy(self.kk_up, self.fixed_size, True)
            self.short_vt_orderids = self.short(self.kk_down, self.fixed_size, True)

        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            self.intra_trade_low = bar.low_price

            #self.sell(self.intra_trade_high * (1 - self.trailing_percent / 100), abs(self.pos),True)
            self.sell(self.kk_ma, abs(self.pos), True)

        elif self.pos < 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)

            #self.cover(self.intra_trade_low * (1 + self.trailing_percent / 100), abs(self.pos),True)
            self.cover(self.kk_ma, abs(self.pos), True)

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    # 防止上下轨停止单同时触发
    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        #self.cancel_all()
        #self.put_event()
        pass

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
