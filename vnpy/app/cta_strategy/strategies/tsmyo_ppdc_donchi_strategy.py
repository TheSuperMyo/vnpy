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
from vnpy.app.cta_strategy.TSMtools import TSMArrayManager


class TSMyoPPDCDONCHIStrategy(CtaTemplate):
    """
    轴心点双通道股指日内
    """

    author = "TheSuperMyo"

    fixed_size = 1
    trailing_stop = 0.6

    atr_stop = 4
    atr_window = 35
    don_len = 30

    PP = 0
    R1 = 0
    R2 = 0
    S1 = 0
    S2 = 0

    intra_trade_high = 0
    intra_trade_low = 0

    day_high = 0
    day_low = 0
    day_close = 0

    atr_value = 0
    atr_ma_value = 0
    tend_high = 0
    tend_low = 0

    limited_size = 8
    td_traded = 0

    exit_time = time(hour=14, minute=56)

    parameters = ["trailing_stop", "fixed_size","limited_size","atr_stop","atr_window"]
    variables = ["atr_value","atr_ma_value","PP","R1","R2","S1","S2","tend_high","tend_low"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TSMyoPPDCDONCHIStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar)
        self.am = TSMArrayManager()
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

        if ( last_bar.datetime.date() != bar.datetime.date() ):
            if self.day_high:

                self.PP = (self.day_high + self.day_low + self.day_close)/3
                self.R1 = 2*self.PP - self.day_low
                self.S1 = 2*self.PP - self.day_high
                self.R2 = self.PP - self.S1 + self.R1
                self.S2 = self.PP - self.R1 + self.S1
        
            self.write_log( f"{bar.datetime.date()}开盘使用数据：" )
            self.write_log( f"昨收：{self.day_close}，昨高：{self.day_high}，昨低：{self.day_low}" )
            self.write_log( f"计算得出：" )
            self.write_log( f"PP：{self.PP}, R1/S1：{self.R1}/{self.S1}, R2/S2：{self.R2}/{self.S2}" )

            self.day_high = bar.high_price
            self.day_low = bar.low_price
            self.day_close = bar.close_price
            self.td_traded = 0
        
        # 盘中记录当日HLC，为第二天计算做准备
        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)
            self.day_close = bar.close_price

        if not self.PP:
            return
    
        # ATR相关指标
        
        self.atr_value = am.atr(self.atr_window,False)
       

        # 30min唐安奇通道
        self.tend_high, self.tend_low = am.donchian(self.don_len,False)
        
        # 交易时间
        if (bar.datetime.time() < self.exit_time):
            if self.pos == 0:
                self.intra_trade_low = bar.low_price
                self.intra_trade_high = bar.high_price
                
                if self.tend_high > self.R1:
                    # 添加过滤，突破价不低于最高价，才进场
                    long_entry = max(self.R2, self.day_high)
                    if self.vt_orderids or self.td_traded >= self.limited_size:
                        self.write_log("撤单不干净或达到交易限制，无法挂单")
                        return
                    orderids = self.buy(long_entry, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)
                    orderids = self.short(self.PP, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)

                elif self.tend_low < self.S1:
                    short_entry = min(self.S2, self.day_low)
                    if self.vt_orderids or self.td_traded >= self.limited_size:
                        self.write_log("撤单不干净或达到交易限制，无法挂单")
                        return
                    orderids = self.short(short_entry, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)
                    orderids = self.buy(self.PP, self.fixed_size, stop=True, lock=True)
                    self.vt_orderids.extend(orderids)

            elif self.pos > 0:
                # 跟踪止损出场（百分比&ATR）
                self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
                long_stop = max(self.intra_trade_high*(1-self.trailing_stop/100), self.intra_trade_high-self.atr_stop*self.atr_value)
                if self.vt_orderids:
                    self.write_log("撤单不干净，无法挂单")
                    return
                orderids = self.sell(long_stop, abs(self.pos), stop=True, lock=True)
                self.vt_orderids.extend(orderids)

            elif self.pos < 0:
                self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
                short_stop = min(self.intra_trade_low*(1+self.trailing_stop/100), self.intra_trade_low+self.atr_stop*self.atr_value)
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
        self.td_traded += 1
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