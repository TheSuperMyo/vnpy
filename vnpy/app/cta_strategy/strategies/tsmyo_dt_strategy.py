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



class TSMyoDTStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    fixed_size = 1
    k1 = 0.7
    k2 = 0.7
    trailing_stop = 0.4

    bars = []

    day_open = 0
    day_high = 0
    day_low = 0

    range = 0
    long_entry = 0
    short_entry = 0
    exit_time = time(hour=14, minute=50)
    # 针对不同交易时间的品种
    night_time = time(hour=20,minute=10)
    day_time = time(hour=8,minute=10)

    long_entered = False
    short_entered = False

    parameters = ["k1", "k2", "fixed_size"]
    variables = ["range", "long_entry", "short_entry", "exit_time"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoDTStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )

        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()
        self.bars = []

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
        self.cancel_all()

        self.bars.append(bar)
        
        # 维护当前bar和上一个bar，共两根
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        last_bar = self.bars[-2]

        # 判断开盘bar，先使用split判别有夜盘品种开盘
        # last_bar是昨天的，也就是说bar是今天第一根
        if ((last_bar.datetime.time()<self.night_time) and (bar.datetime.time()>self.night_time)) or ((last_bar.datetime.date() != bar.datetime.date()) and (bar.datetime.time()>self.day_time)):
            # 昨天有high/low的记录
            if self.day_high and self.day_low:
                 # 计算Range日内DT
                 # MAX(HH-LC,HC-LL)|N=1
                self.range = max((self.day_high-last_bar.close_price),(last_bar.close_price-self.day_low))
                self.long_entry = bar.open_price + self.k1 * self.range
                self.short_entry = bar.open_price - self.k2 * self.range

            self.day_open = bar.open_price
            self.day_high = bar.high_price
            self.day_low = bar.low_price

            #每天只开一次多一次空
            self.long_entered = False
            self.short_entered = False

        # 不是开盘第一根bar，更新当天的high/low
        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)

        # 没有计算好的range，就返回
        if not self.range:
            return

        # 在交易时间内（14：50之前或夜盘时段）
        if bar.datetime.time() < self.exit_time or bar.datetime.time() > self.night_time:
            if self.pos == 0:
                if bar.close_price > self.day_open:
                    if not self.long_entered:
                        self.buy(self.long_entry, self.fixed_size, stop=True)
                else:
                    if not self.short_entered:
                        self.short(self.short_entry, self.fixed_size, stop=True)

            elif self.pos > 0:
                self.long_entered = True
                
                #止盈止损（选项1）
                #self.sell(self.day_high*(1 + self.trailing_stop/100), self.fixed_size, stop=True)
                #正反手（选项2）
                self.sell(self.short_entry, self.fixed_size, stop=True)
                if not self.short_entered:
                    self.short(self.short_entry, self.fixed_size, stop=True)

            elif self.pos < 0:
                self.short_entered = True
                
                #self.cover(self.day_low*(1 - self.trailing_stop/100), self.fixed_size, stop=True)
                self.cover(self.long_entry, self.fixed_size, stop=True)
                if not self.long_entered:
                    self.buy(self.long_entry, self.fixed_size, stop=True)
        # 日内交易，收盘前不断尝试平仓
        else:
            if self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
            elif self.pos < 0:
                self.cover(bar.close_price, abs(self.pos))

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
