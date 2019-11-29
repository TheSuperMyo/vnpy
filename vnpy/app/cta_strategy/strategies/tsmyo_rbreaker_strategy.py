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



class TSMyoRBreakerTickStrategy(CtaTemplate):
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
    day_close = 0
    tend_high = 0
    tend_low = 0
    
    #开仓不使用停止单
    tick_flag = 0

    exit_time = time(hour=14, minute=54)
    # 针对不同交易时间的品种
    #night_time = time(hour=20,minute=10)
    #day_time = time(hour=8,minute=10)

    parameters = ["trailing_short","trailing_long","setup_coef", "break_coef", "enter_coef_1", "enter_coef_2", "fixed_size", "donchian_window", "multiplier"]
    variables = ["tend_low","tend_high","tick_flag","day_high","day_low","buy_break", "sell_setup", "sell_enter", "buy_enter", "buy_setup", "sell_break"]
    #variables = ["tend_low","tend_high","day_close","day_high","day_low"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoRBreakerTickStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()
        self.bars = []
        self.active_orderids = []       #活跃委托ID列表，防止重复下单

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
        # 无仓位无等待成交单才能开仓
        if not self.pos and not self.active_orderids: 
            #上中轨条件触发
            if self.tick_flag == 1:
                # 添加过滤，突破价不低于最高价，才进场
                long_entry = max(self.buy_break, self.day_high)
                if tick.ask_price_1 > long_entry:
                    self.write_log(f"当前卖一价{tick.ask_price_1}大于{long_entry}")
                    orderids = self.buy(long_entry, self.fixed_size, stop=False, lock=True)
                    if orderids:
                        self.active_orderids.extend(orderids)
                        self.write_log(f"上上：在{long_entry}位置挂单成功，添加{orderids}到活跃订单")
                if tick.bid_price_1 < self.sell_enter:
                    # 反转系统进场，手数可以和趋势系统做区分
                    self.write_log(f"当前买一价{tick.bid_price_1}小于{self.sell_enter}")
                    orderids = self.short(self.sell_enter, self.multiplier * self.fixed_size, stop=False, lock=True)
                    if orderids:
                        self.active_orderids.extend(orderids)
                        self.write_log(f"上下：在{self.sell_enter}位置挂单成功，添加{orderids}到活跃订单")
        
            #下中轨条件触发
            if self.tick_flag == -1:
                short_entry = min(self.sell_break, self.day_low)
                if tick.bid_price_1 < short_entry:
                    self.write_log(f"当前买一价{tick.bid_price_1}小于{short_entry}")
                    orderids = self.short(short_entry, self.fixed_size, stop=False, lock=True)
                    if orderids:
                        self.active_orderids.extend(orderids)
                        self.write_log(f"下下：在{short_entry}位置挂单成功，添加{orderids}到活跃订单")
                if tick.ask_price_1 > self.buy_enter:
                    self.write_log(f"当前卖一价{tick.ask_price_1}大于{self.buy_enter}")
                    orderids = self.buy(self.buy_enter, self.multiplier * self.fixed_size, stop=False, lock=True)
                    if orderids:
                        self.active_orderids.extend(orderids)
                        self.write_log(f"下上：在{self.buy_enter}位置挂单成功，添加{orderids}到活跃订单")
                

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
        #if ((last_bar.datetime.time()<self.night_time) and (bar.datetime.time()>self.night_time)) or ((last_bar.datetime.date() != bar.datetime.date()) and (bar.datetime.time()>self.day_time)):
        if ( last_bar.datetime.date() != bar.datetime.date() ):
            if self.day_high:

                self.buy_setup = self.day_low - self.setup_coef * (self.day_high - self.day_close)  # 观察买入价
                self.sell_setup = self.day_high + self.setup_coef * (self.day_close - self.day_low)# 观察卖出
        
                self.buy_enter = (self.enter_coef_1 / 2) * (self.day_high + self.day_low) - self.enter_coef_2 * self.day_high  # 反转买入价
                self.sell_enter = (self.enter_coef_1 / 2) * (self.day_high + self.day_low) - self.enter_coef_2 * self.day_low  # 反转卖出价

                self.buy_break = self.sell_setup + self.break_coef * (self.sell_setup - self.buy_setup)  # 突破买入价
                self.sell_break = self.buy_setup - self.break_coef * (self.sell_setup - self.buy_setup)  # 突破卖出价
        
            #if bar.datetime.date() != '2019-11-13':
            self.write_log( f"{bar.datetime.date()}开盘使用数据：" )
            self.write_log( f"昨收：{self.day_close}，昨高：{self.day_high}，昨低：{self.day_low}" )
            self.write_log( f"计算得出：" )
            self.write_log( f"上中轨：{self.sell_setup}，下中轨：{self.buy_setup}" )
            self.day_high = bar.high_price
            self.day_low = bar.low_price
            self.day_close = bar.close_price
            
        # 盘中记录当日HLC，为第二天计算做准备
        else:
            #if bar.datetime.date() != '2019-11-13':
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)
            self.day_close = bar.close_price

        if not self.sell_setup:
            return
        
        # N分钟内最高价和最低价
        self.tend_high, self.tend_low = am.donchian(self.donchian_window)

        #if (bar.datetime.time() < self.exit_time) or ( bar.datetime.time() > self.night_time ):
        if (bar.datetime.time() < self.exit_time):
            #防止重复下单
            if not self.pos: 
                self.intra_trade_low = bar.low_price
                self.intra_trade_high = bar.high_price
                self.tick_flag = 0
                # N分钟内最高价在sell_setup之上
                if self.tend_high > self.sell_setup:

                    #上中轨条件
                    self.write_log( f"上中轨建立{self.tend_high}大于{self.sell_setup}" )
                    self.tick_flag = 1

                elif self.tend_low < self.buy_setup:

                    #下中轨条件
                    self.write_log( f"下中轨建立{self.tend_low}小于{self.buy_setup}" )
                    self.tick_flag = -1
                    
            elif self.pos > 0:
                # 跟踪止损出场
                self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                long_stop = self.intra_trade_high * (1 - self.trailing_long / 100)
                self.sell(long_stop, abs(self.pos), stop=True, lock=True)

            elif self.pos < 0:
                self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                short_stop = self.intra_trade_low * (1 + self.trailing_short / 100)
                self.cover(short_stop, abs(self.pos), stop=True, lock=True)
        
        # 日内策略，最后6分钟不断尝试平仓
        else:
            if self.pos > 0:
                self.sell(bar.close_price, abs(self.pos), lock=True)
            elif self.pos < 0:
                self.cover(bar.close_price, abs(self.pos), lock=True)
                
        self.put_event()
        


    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        #没有活跃订单撤掉active_orderids的委托ID
        if not order.is_active() and order.vt_orderid in self.active_orderids:
            self.active_orderids.remove(order.vt_orderid)
            self.write_log( f"将{order.vt_orderid}移除活跃订单" )

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