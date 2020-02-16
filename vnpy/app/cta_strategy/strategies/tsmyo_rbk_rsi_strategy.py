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



class TSMyoRBKRSIStrategy(CtaTemplate):
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
    atr_stop = 4
    atr_window = 35
    atr_ma_len = 20
    rsi_filter = 25

    trailing_stop = 0.6
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
    atr_value = 0
    atr_ma_value = 0
    limited_size = 8
    td_traded = 0

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

    parameters = ["trailing_stop", "rsi_filter","donchian_window","limited_size","atr_stop","atr_window","atr_ma_len"]
    variables = ["tend_low","tend_high","atr_value","atr_ma_value","buy_break", "sell_setup", "sell_enter", "buy_enter", "buy_setup", "sell_break"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoRBKRSIStrategy, self).__init__(
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
        if ( last_bar.datetime.date() != bar.datetime.date() ):
            if self.day_high:

                self.buy_setup = self.day_low - self.setup_coef * (self.day_high - self.day_close)  # 观察买入价
                self.sell_setup = self.day_high + self.setup_coef * (self.day_close - self.day_low)# 观察卖出
        
                self.buy_enter = (self.enter_coef_1 / 2) * (self.day_high + self.day_low) - self.enter_coef_2 * self.day_high  # 反转买入价
                self.sell_enter = (self.enter_coef_1 / 2) * (self.day_high + self.day_low) - self.enter_coef_2 * self.day_low  # 反转卖出价

                self.buy_break = self.sell_setup + self.break_coef * (self.sell_setup - self.buy_setup)  # 突破买入价
                self.sell_break = self.buy_setup - self.break_coef * (self.sell_setup - self.buy_setup)  # 突破卖出价
        
            self.write_log( f"{bar.datetime.date()}开盘使用数据：" )
            self.write_log( f"昨收：{self.day_close}，昨高：{self.day_high}，昨低：{self.day_low}" )
            self.write_log( f"计算得出：" )
            self.write_log( f"上中轨：{self.sell_setup}，下中轨：{self.buy_setup}" )
            self.day_high = bar.high_price
            self.day_low = bar.low_price
            self.day_close = bar.close_price
            self.td_traded = 0
            
            
        # 盘中记录当日HLC，为第二天计算做准备
        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)
            self.day_close = bar.close_price

        if not self.sell_setup:
            return
        
        # N分钟内最高价和最低价
        self.tend_high, self.tend_low = am.donchian(self.donchian_window)
        # ATR相关指标
        atr_array = am.atr(self.atr_window,True)
        self.atr_value = atr_array[-1]
        self.atr_ma_value = atr_array[-self.atr_ma_len:].mean()
        # RSI
        rsi_value = am.rsi(False)
        if abs(rsi_value-50) > self.rsi_filter:
            rsi_flag = 1
        
        # 交易时间
        if (bar.datetime.time() < self.exit_time):
            # 设置ATR过滤，只有波动扩大才开仓
            if self.pos == 0 and self.atr_value > self.atr_ma_value and rsi_flag == 1:
                self.write_log( f"波动扩大：{self.atr_value} > {self.atr_ma_value}" )
                self.intra_trade_low = bar.low_price
                self.intra_trade_high = bar.high_price
                # N分钟内最高价在sell_setup之上
                if self.tend_high > self.sell_setup:
                    self.write_log( f"N分钟内 tend_high > sell_setup：{self.tend_high} > {self.sell_setup}" )
                    # 添加过滤，突破价不低于最高价，才进场
                    long_entry = max(self.buy_break, self.day_high)
                    # 检查策略是否还有订单留存,或者是否达到交易上限
                    if self.vt_orderids or self.td_traded >= self.limited_size:
                        self.write_log("撤单不干净或达到交易限制，无法挂单")
                        return
                    orderids = self.buy(long_entry, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)

                    # 反转系统进场，手数可以和趋势系统做区分
                    orderids = self.short(self.sell_enter, self.multiplier * self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)
                    self.write_log( f"stop_order for buy & short：{long_entry} & {self.sell_enter}" )

                elif self.tend_low < self.buy_setup:
                    self.write_log( f"N分钟内 tend_low < buy_setup：{self.tend_low} < {self.buy_setup}" )
                    short_entry = min(self.sell_break, self.day_low)
                    if self.vt_orderids or self.td_traded >= self.limited_size:
                        self.write_log("撤单不干净或达到交易限制，无法挂单")
                        return
                    orderids = self.short(short_entry, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)
                    orderids = self.buy(self.buy_enter, self.multiplier * self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)
                    self.write_log( f"stop_order for short & buy：{short_entry} & {self.buy_enter}" )

            elif self.pos > 0:
                # 跟踪止损出场（百分比&ATR）
                self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                long_stop = max(self.intra_trade_high*(1-self.trailing_stop/100), self.intra_trade_high-self.atr_stop*self.atr_value)
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(long_stop, abs(self.pos), stop=True, lock=True)
                self.vt_orderids.extend(orderids)
                self.write_log( f"stop_order for sell：{long_stop}" )

            elif self.pos < 0:
                self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                short_stop = min(self.intra_trade_low*(1+self.trailing_stop/100), self.intra_trade_low+self.atr_stop*self.atr_value)
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(short_stop, abs(self.pos), stop=True, lock=True)
                self.vt_orderids.extend(orderids)
                self.write_log( f"stop_order for cover：{short_stop}" )
        
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
        self.td_traded += 1
        self.write_log(f"{trade.vt_symbol}在{trade.time}成交，价格{trade.price}，方向{trade.direction}{trade.offset}，数量{trade.volume}")
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