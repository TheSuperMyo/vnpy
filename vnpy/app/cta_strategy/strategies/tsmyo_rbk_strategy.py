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



class TSMyoRBKStrategy(CtaTemplate):
    """
    针对本地停止单触发的撤单失败导致重复挂单
        1.给cancel_all()返回值，去标记是否出现 OmsEngine中找不到 的情况，做相应处理
        2.策略自身维护一个订单列表，使用 on_stop_order/on_order 去同步cta_engine的 策略—订单列表map ，做相应判断
    """

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

    exit_time = time(hour=14, minute=54)
    # 针对不同交易时间的品种
    #night_time = time(hour=20,minute=10)
    #day_time = time(hour=8,minute=10)

    parameters = ["trailing_short","trailing_long","setup_coef", "break_coef", "enter_coef_1", "enter_coef_2", "fixed_size", "donchian_window", "multiplier"]
    variables = ["tend_low","tend_high","day_close","day_high","day_low","buy_break", "sell_setup", "sell_enter", "buy_enter", "buy_setup", "sell_break"]
    #variables = ["tend_low","tend_high","day_close","day_high","day_low"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoRBKStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()
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
        """
        Callback of new bar data update.
        """
        # 如果撤单过程中出现在OMSEngine找不到订单
        # 则可能是挂单的EVENT_ORDER还未处理，跳过该此次执行
        any_not_find = 0
        any_not_find = self.cancel_all()
        if any_not_find == 1:
            self.write_log("出现撤单找不到问题，跳过此次执行")
            return

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
            if self.pos == 0:
                self.intra_trade_low = bar.low_price
                self.intra_trade_high = bar.high_price
                # N分钟内最高价在sell_setup之上
                if self.tend_high > self.sell_setup:
                    # 添加过滤，突破价不低于最高价，才进场
                    long_entry = max(self.buy_break, self.day_high)
                    # 检查策略是否还有订单留存
                    if self.vt_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.buy(long_entry, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)

                    # 反转系统进场，手数可以和趋势系统做区分
                    orderids = self.short(self.sell_enter, self.multiplier * self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)

                elif self.tend_low < self.buy_setup:
                    short_entry = min(self.sell_break, self.day_low)
                    if self.vt_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.short(short_entry, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)
                    orderids = self.buy(self.buy_enter, self.multiplier * self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)

            elif self.pos > 0:
                # 跟踪止损出场
                self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                long_stop = self.intra_trade_high * (1 - self.trailing_long / 100)
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(long_stop, abs(self.pos), stop=True, lock=True)
                self.vt_orderids.extend(orderids)

            elif self.pos < 0:
                self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                short_stop = self.intra_trade_low * (1 + self.trailing_short / 100)
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(short_stop, abs(self.pos), stop=True, lock=True)
                self.vt_orderids.extend(orderids)
        
        # 日内策略，最后6分钟不断尝试平仓
        else:
            if self.pos > 0:
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price, abs(self.pos), lock=True)
                self.vt_orderids.extend(orderids)

            elif self.pos < 0:
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price, abs(self.pos), lock=True)
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