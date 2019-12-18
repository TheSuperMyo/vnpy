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

class TSMyoORBStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    # OR及计数器
    or_setup = 30
    bar_counter = 0
    a_up_setup_counter = 0
    c_up_setup_counter = 0
    a_down_setup_counter = 0
    c_down_setup_counter = 0
    stop_long_counter = 0
    stop_short_counter = 0
    or_h = 0
    or_l = 0
    or_r = 0
    a_up = 0
    a_down = 0
    c_up = 0
    c_down = 0
    k1 = 0
    k2 = 0
    day_high = 0
    day_low = 0
    long_intra = 0
    short_intra = 0
    long_stop = 0
    short_stop = 0
    is_lock = 0
    fixed_size = 1

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

    parameters = []
    variables = []

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoORBStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar)
        self.am = TSMArrayManager()
        # 策略自身订单管理
        self.active_orderids = []
        self.bars = []

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        # 根据需要的历史数据长度设定
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
        pass

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.cancel_all()

        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        
        last_bar = self.bars[-2]
        # 今日开盘
        if last_bar.datetime.date() != bar.datetime.date():
            self.day_high = bar.high_price
            self.day_low = bar.low_price
            self.bar_counter = 0
            self.a_up = 0
            self.a_down = 0
            self.c_up = 0
            self.c_down = 0

        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)

        if self.bar_counter == self.or_setup:
            self.or_h, self.or_l = am.donchian(self.or_setup, False)
            self.or_r = self.or_h-self.or_l
            self.a_up = self.or_h + self.k1*self.or_r
            self.a_down = self.or_l - self.k1*self.or_r
            self.c_up = self.or_h + self.k2*self.or_r
            self.c_down = self.or_l + self.k2*self.or_r

        if self.pos == 0 and self.a_up:
            # 价格大于+A
            if bar.close_price > self.a_up:
                if self.a_up_setup_counter >= self.or_setup:
                    # 且持续一个OR，开多
                    if self.active_orderids:
                        self.write_log("存在活跃订单，无法挂单")
                        return
                    if self.is_lock:
                        orderids = self.buy(bar.close_price, self.fixed_size, lock=True)
                    else:
                        orderids = self.buy(bar.close_price, self.fixed_size, lock=False)
                    self.active_orderids.extend(orderids)
                else:
                    self.a_up_setup_counter += 1
                # 价格大于+C
                if bar.close_price > self.c_up and self.day_low < self.a_down:
                    if self.c_up_setup_counter >= self.or_setup/2:
                        # 从低于-A反转且持续1/2个OR，开多
                        if self.active_orderids:
                            self.write_log("存在活跃订单，无法挂单")
                            return
                        if self.is_lock:
                            orderids = self.buy(bar.close_price, self.fixed_size, lock=True)
                        else:
                            orderids = self.buy(bar.close_price, self.fixed_size, lock=False)
                        self.active_orderids.extend(orderids)
                    else:
                        self.c_up_setup_counter += 1
                else:
                    self.c_up_setup_counter = 0
            else:
                self.a_up_setup_counter = 0

            # 价格小于-A
            if bar.close_price < self.a_down:
                if self.a_down_setup_counter >= self.or_setup:
                    # 且持续一个OR，开空
                    if self.active_orderids:
                        self.write_log("存在活跃订单，无法挂单")
                        return
                    if self.is_lock:
                        orderids = self.short(bar.close_price, self.fixed_size, lock=True)
                    else:
                        orderids = self.short(bar.close_price, self.fixed_size, lock=False)
                    self.active_orderids.extend(orderids)
                else:
                    self.a_down_setup_counter += 1
                # 价格小于-C
                if bar.close_price < self.c_down and self.day_high > self.a_up:
                    if self.c_down_setup_counter >= self.or_setup/2:
                        # 从低于-A反转且持续1/2个OR，开空
                        if self.active_orderids:
                            self.write_log("存在活跃订单，无法挂单")
                            return
                        if self.is_lock:
                            orderids = self.short(bar.close_price, self.fixed_size, lock=True)
                        else:
                            orderids = self.short(bar.close_price, self.fixed_size, lock=False)
                        self.active_orderids.extend(orderids)
                    else:
                        self.c_down_setup_counter += 1
                else:
                    self.c_down_setup_counter = 0
            else:
                self.a_down_setup_counter = 0

        if self.pos > 0:
            close_long = self.long_stop
            if bar.close_price < self.long_intra:
                if self.stop_long_counter >= self.or_setup:
                    # 一个OR不盈利平多
                    close_long = bar.close_price
                else:
                    self.stop_long_counter = 0
            if self.long_stop:
                # 统一挂停止单平多
                stop_long_price = max(close_long, self.long_stop)
                if self.active_orderids:
                    self.write_log("存在活跃订单，无法挂单")
                    return
                if self.is_lock:
                    orderids = self.sell(stop_long_price, self.fixed_size, stop=True, lock=True)
                else:
                    orderids = self.sell(stop_long_price, self.fixed_size, stop=True, lock=False)
                self.active_orderids.extend(orderids)

        if self.pos < 0:
            close_short = self.short_stop
            if bar.close_price > self.short_intra:
                if self.stop_short_counter >= self.or_setup:
                    # 一个OR不盈利平空
                    close_short = bar.close_price
                else:
                    self.stop_short_counter = 0
            if self.short_stop:
                # 统一挂停止单平空
                stop_short_price = min(close_short, self.short_stop)
                if self.active_orderids:
                    self.write_log("存在活跃订单，无法挂单")
                    return
                if self.is_lock:
                    orderids = self.cover(stop_short_price, self.fixed_size, stop=True, lock=True)
                else:
                    orderids = self.cover(stop_short_price, self.fixed_size, stop=True, lock=False)
                self.active_orderids.extend(orderids)

        self.bar_counter += 1

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
        if self.pos > 0:
            self.long_intra = trade.price
            self.short_intra = 0
            self.long_stop = self.or_l
            self.short_stop = 0

        elif self.pos < 0:
            self.long_intra = 0
            self.short_intra = trade.price
            self.long_stop = 0
            self.short_stop = self.or_h

        elif self.pos == 0:
            self.long_intra = 0
            self.short_intra = 0 
            self.long_stop = 0
            self.short_stop = 0
            
        self.stop_short_counter = 0
        self.stop_long_counter = 0
        self.a_up_setup_counter = 0
        self.c_up_setup_counter = 0
        self.a_down_setup_counter = 0
        self.c_down_setup_counter = 0

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