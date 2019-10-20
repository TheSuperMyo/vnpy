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



class TSMyoRBreakerStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    setup_coef = 0.25
    break_coef = 0.2
    enter_coef_1 = 1.07
    enter_coef_2 = 0.07

    fixed_size = 1
    donchian_window = 30

    trailing_long = 0.4
    trailing_short = 0.4
    multiplier = 1

    buy_break = 0   # 突破买入价
    sell_setup = 0  # 观察卖出价
    sell_enter = 0  # 反转卖出价
    buy_enter = 0   # 反转买入价
    buy_setup = 0   # 观察买入价
    sell_break = 0  # 突破卖出价

    intra_trade_high = 0
    intra_trade_low = 0

    day_high = 0
    day_low = 0
    tend_high = 0
    tend_low = 0

    exit_time = time(hour=14, minute=50)
    # 针对不同交易时间的品种
    night_time = time(hour=20,minute=10)
    day_time = time(hour=8,minute=10)

    parameters = ["setup_coef", "break_coef", "enter_coef_1", "enter_coef_2", "fixed_size", "donchian_window", "multiplier"]
    variables = ["buy_break", "sell_setup", "sell_enter", "buy_enter", "buy_setup", "sell_break"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoRBreakerStrategy, self).__init__(
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

        # 判断开盘bar，先使用split判别有夜盘品种开盘
        # last_bar是昨天的，也就是说bar是今天第一根
        if ((last_bar.datetime.time()<self.night_time) and (bar.datetime.time()>self.night_time)) or ((last_bar.datetime.date() != bar.datetime.date()) and (bar.datetime.time()>self.day_time)):
            if self.day_high:

                self.buy_setup = self.day_low - self.setup_coef * (self.day_high - last_bar.close_price)  # 观察买入价
                self.sell_setup = self.day_high + self.setup_coef * (last_bar.close_price - self.day_low)# 观察卖出
        
                self.buy_enter = (self.enter_coef_1 / 2) * (self.day_high + self.day_low) - self.enter_coef_2 * self.day_high  # 反转买入价
                self.sell_enter = (self.enter_coef_1 / 2) * (self.day_high + self.day_low) - self.enter_coef_2 * self.day_low  # 反转卖出价

                self.buy_break = self.sell_setup + self.break_coef * (self.sell_setup - self.buy_setup)  # 突破买入价
                self.sell_break = self.buy_setup - self.break_coef * (self.sell_setup - self.buy_setup)  # 突破卖出价
        
            self.day_high = bar.high_price
            self.day_low = bar.low_price
            
        # 盘中记录当日HL，为第二天计算做准备
        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)

        if not self.sell_setup:
            return
        
        # N分钟内最高价和最低价
        self.tend_high, self.tend_low = am.donchian(self.donchian_window)

        if (bar.datetime.time() < self.exit_time) or ( bar.datetime.time() > self.night_time ):
            if self.pos == 0:
                self.intra_trade_low = bar.low_price
                self.intra_trade_high = bar.high_price
                # N分钟内最高价在sell_setup之上
                if self.tend_high > self.sell_setup:
                    # 添加过滤，突破价不低于最高价，才进场
                    long_entry = max(self.buy_break, self.day_high)
                    self.buy(long_entry, self.fixed_size, stop=True)

                    # 反转系统进场，手数可以和趋势系统做区分
                    self.short(self.sell_enter, self.multiplier * self.fixed_size, stop=True)
                    
                elif self.tend_low < self.buy_setup:
                    short_entry = min(self.sell_break, self.day_low)
                    self.short(short_entry, self.fixed_size, stop=True)

                    self.buy(self.buy_enter, self.multiplier * self.fixed_size, stop=True)
                    
            elif self.pos > 0:
                # 跟踪止损出场
                self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                long_stop = self.intra_trade_high * (1 - self.trailing_long / 100)
                self.sell(long_stop, abs(self.pos), stop=True)

            elif self.pos < 0:
                self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                short_stop = self.intra_trade_low * (1 + self.trailing_short / 100)
                self.cover(short_stop, abs(self.pos), stop=True)
        
        # 日内策略，最后10分钟不断尝试平仓
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