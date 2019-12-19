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

class TSMyoIntradayGapStrategy(CtaTemplate):
    """"""

    author = "TheSuperMyo"

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

    xmin = 15
    close_signal = 0
    gap_signal = 0
    reverse = 0
    intra = 0
    fixed_size = 1


    parameters = []
    variables = []

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoIntradayGapStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar, self.xmin, self.on_xmin_bar)
        self.am = TSMArrayManager()
        # 策略自身订单管理
        self.active_orderids = []
        self.bars = []
        self.xbars = [] 

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
        1.开盘若持仓则平仓
        2.根据第一个xminbar的信号操作
        3.挂止损
        """
        self.bg.update_bar(bar)

        self.cancel_all()

        self.bars.append(bar)
        if len(self.bars) <= 2:
            return
        else:
            self.bars.pop(0)
        
        last_bar = self.bars[-2]
        # 今日开盘
        if last_bar.datetime.date() != bar.datetime.date():
            if self.pos == 0:
                self.close_signal = 0
            else:
                self.close_signal = 1

        if self.pos == 0:
            if self.gap_signal == 1 and self.intra:
                # 开多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.buy(self.intra, self.fixed_size)
                self.active_orderids.extend(orderids)

            if self.gap_signal == -1 and self.intra:
                # 开空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.short(self.intra, self.fixed_size)
                self.active_orderids.extend(orderids)

        if self.pos > 0:
            if self.close_signal:
                # 开盘平多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                else:
                    orderids = self.sell(bar.close_price, self.fixed_size)
                    self.active_orderids.extend(orderids)

            elif self.reverse and self.gap_signal == 1:
                # 停止单平多开空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(self.reverse, self.fixed_size, True)
                self.active_orderids.extend(orderids)
                orderids = self.short(self.reverse, self.fixed_size, True)
                self.active_orderids.extend(orderids)

        if self.pos < 0:
            if self.close_signal:
                # 开盘平空
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                else:
                    orderids = self.cover(bar.close_price, self.fixed_size)
                    self.active_orderids.extend(orderids)

            elif self.reverse and self.gap_signal == -1:
                # 停止单平空开多
                if self.active_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.cover(self.reverse, self.fixed_size, True)
                self.active_orderids.extend(orderids)
                orderids = self.buy(self.reverse, self.fixed_size, True)
                self.active_orderids.extend(orderids)
        
        self.put_event()


    def on_xmin_bar(self, bar: BarData):
        """
        1.确定当日是否存在缺口以及缺口方向
        2.确定价位
        """
        self.xbars.append(bar)
        if len(self.xbars) <= 2:
            return
        else:
            self.xbars.pop(0)
        
        last_bar = self.xbars[-2]
        # 第一根xminbar
        if last_bar.datetime.date() != bar.datetime.date():
            self.intra = 0
            self.reverse = 0
            self.gap_signal = 0
            if last_bar.high_price < bar.low_price:
                # 跳高缺口
                self.gap_signal = 1
                self.intra = bar.close_price
                self.reverse = last_bar.close_price

            if last_bar.low_price > bar.high_price:
                # 跳空缺口
                self.gap_signal = -1
                self.intra = bar.close_price
                self.reverse = last_bar.close_price

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
        1.开盘平仓信号的复位
        """
        if self.pos == 0:
            self.close_signal = 0
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