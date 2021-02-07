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
from vnpy.app.cta_strategy.base import EngineType


from datetime import datetime


class KingKeltnerStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    kk_length = 11
    kk_dev = 1.6
    trailing_percent = 0.8
    fixed_size = 1

    kk_up = 0
    kk_down = 0
    intra_trade_high = 0
    intra_trade_low = 0

    long_vt_orderids = []
    short_vt_orderids = []
    vt_orderids = []

    parameters = ["kk_length", "kk_dev", "trailing_percent", "fixed_size"]
    variables = ["kk_up", "kk_down"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.am = ArrayManager(50)
        self.long_vt_orderids = []
        self.short_vt_orderids = []
        self.vt_orderids = []

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        #if self.get_engine_type() == EngineType.LIVE:
            #self.fo = open("C:\Study\MyDiary\VNPY_TSMyo_Log\VNPY_Log.txt", "a")
            #self.write_log("开启本地log记录文件")
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
        #if self.get_engine_type() == EngineType.LIVE and self.fo:
            #self.fo.close()

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
        # 把本地维护的所有委托单撤单
        '''
        for orderid in self.vt_orderids:
            self.cancel_order(orderid)
        self.vt_orderids.clear()
        '''
        self.cancel_all()

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.kk_up, self.kk_down = am.keltner(self.kk_length, self.kk_dev)

        if self.pos == 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price
            # oco单，二选一触发，同时挂上下轨突破的停止单，一个触发另一个立刻取消
            # 经常用于防止在bar中波动过大，上下轨同时触发
            self.send_oco_order(self.kk_up, self.kk_down, self.fixed_size)

        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            self.intra_trade_low = bar.low_price

            vt_orderids = self.sell(self.intra_trade_high * (1 - self.trailing_percent / 100),
                                    abs(self.pos),True)
            #self.vt_orderids.extend(vt_orderids)

        elif self.pos < 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)

            vt_orderids = self.cover(self.intra_trade_low * (1 + self.trailing_percent / 100),
                                     abs(self.pos),True)
            #self.vt_orderids.extend(vt_orderids)

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        #if self.get_engine_type() == EngineType.LIVE and self.fo:
            #self.fo.write(str(datetime.now())+ '\t' + str(order)+'\n')

    # 配合实现OCO挂单
    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        '''
        if self.pos != 0:
            if self.pos > 0:
                for short_orderid in self.short_vt_orderids:
                    self.cancel_order(short_orderid)

            elif self.pos < 0:
                for buy_orderid in self.long_vt_orderids:
                    self.cancel_order(buy_orderid)

            for orderid in (self.long_vt_orderids + self.short_vt_orderids):
                if orderid in self.vt_orderids:
                    self.vt_orderids.remove(orderid)
        '''
        #self.cancel_all()
        self.put_event()
        #if self.get_engine_type() == EngineType.LIVE and self.fo:
            #self.fo.write(str(datetime.now())+ '\t' + str(trade)+'\n')

    def send_oco_order(self, buy_price, short_price, volume):
        """"""
        self.long_vt_orderids = self.buy(buy_price, volume,True)
        self.short_vt_orderids = self.short(short_price, volume,True)

        #self.vt_orderids.extend(self.long_vt_orderids)
        #self.vt_orderids.extend(self.short_vt_orderids)

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
