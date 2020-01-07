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

class TSMyoImpulseStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

    # 日内交易
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

    exit_counter = 0
    bar_tr = 0
    bar_atr = 0
    long_open = 0
    short_open = 0
    long_stop = 0
    short_stop = 0
    tr_k1 = 3.0
    tr_k2 = 2.0
    close_range = 0.2
    xmin = 20
    fixed_size = 1


    parameters = ["tr_k1","tr_k2","close_range","xmin"]
    variables = ["exit_counter","bar_tr","bar_atr","long_open","long_stop","short_open","short_stop"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoImpulseStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar, self.xmin, self.on_xmin_bar)
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
        1.挂单
        """
        self.bg.update_bar(bar)

        self.cancel_all()

        if bar.datetime.time() < self.exit_time:
            if self.pos == 0:
                if self.long_open:
                    # 开多
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.buy(self.long_open, self.fixed_size, lock=True, stop=True)
                    self.active_orderids.extend(orderids)
                elif self.short_open:
                    # 开空
                    if self.active_orderids:
                        self.write_log("撤单不干净，无法挂单")
                        return
                    orderids = self.short(self.short_open, self.fixed_size, lock=True, stop=True)
                    self.active_orderids.extend(orderids)

            if self.pos > 0 :
                self.exit_counter += 1
                if self.exit_counter > self.xmin:
                    if self.long_stop:
                        # 停止单止损
                        if self.active_orderids:
                            self.write_log("撤单不干净，无法挂单")
                            return
                        orderids = self.sell(self.long_stop, self.fixed_size, lock=True, stop=True)
                        self.active_orderids.extend(orderids)

            if self.pos < 0 :
                self.exit_counter += 1
                if self.exit_counter > self.xmin:
                    if self.short_stop:
                        # 停止单止损
                        if self.active_orderids:
                            self.write_log("撤单不干净，无法挂单")
                            return
                        orderids = self.cover(self.long_stop, self.fixed_size, lock=True, stop=True)
                        self.active_orderids.extend(orderids)
        
        # 日内交易
        else:
            if self.pos > 0:
                # 平多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(bar.close_price, self.fixed_size, lock=True)
                self.active_orderids.extend(orderids)
            if self.pos < 0:
                # 平空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(bar.close_price, self.fixed_size, lock=True)
                self.active_orderids.extend(orderids)

        

        self.put_event()

    def on_xmin_bar(self, bar: BarData):
        """
        1.开盘/盘中信号生成
        2.生成止损价位
        """
        # for debug 930为930-945bar时间戳
        # self.cta_engine.output(bar.datetime.time())

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        # 当前bar的TR和之前bars的ATR
        self.bar_tr = am.tr(False)
        atr_array = am.atr(240/self.xmin,True)
        self.bar_atr = atr_array[-2]
        
        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        
        last_bar = self.bars[-2]
        # 第一根xminbar
        if last_bar.datetime.date() != bar.datetime.date():
            if self.bar_tr > self.bar_atr * self.tr_k1:
                # 计算close是否收在两端close_range内
                lv = (bar.close_price-bar.low_price)/(bar.high_price-bar.low_price)
                if lv < self.close_range:
                    # 快速下跌波动且close收低，开多信号
                    self.long_open = bar.close_price
                    self.long_stop = bar.low_price
                    self.short_stop = 0
                    self.short_open = 0
                    

                elif lv > (1-self.close_range):
                    # 快速上涨波动且close收高，开空信号
                    self.short_open = bar.close_price
                    self.short_stop = bar.high_price
                    self.long_open = 0
                    self.long_stop = 0

        elif self.pos == 0:
            if self.bar_tr > self.bar_atr * self.tr_k2:
                # 计算close是否收在两端close_range内
                lv = (bar.close_price-bar.low_price)/(bar.high_price-bar.low_price)
                if lv < self.close_range:
                    # 快速下跌波动且close收低，开多信号
                    self.long_open = bar.close_price
                    self.long_stop = bar.low_price
                    self.short_stop = 0
                    self.short_open = 0

                elif lv > (1-self.close_range):
                    # 快速上涨波动且close收高，开空信号
                    self.short_open = bar.close_price
                    self.short_stop = bar.high_price
                    self.long_open = 0
                    self.long_stop = 0
            
        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        # 移除已成交或已撤销的订单
        if not order.is_active() and order.vt_orderid in self.active_orderids:
            self.active_orderids.remove(order.vt_orderid)

    def on_trade(self, trade: TradeData):
        """
        1.重置倒计时
        """
        if self.pos == 0:
            self.exit_counter = 0
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