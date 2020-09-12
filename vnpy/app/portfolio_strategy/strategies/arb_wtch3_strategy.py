from typing import List, Dict
from datetime import datetime, time

import numpy as np

from vnpy.app.portfolio_strategy import StrategyTemplate, StrategyEngine
#from vnpy.trader.utility import BarGenerator
from vnpy.trader.object import TickData, BarData, ContractData
import talib
from collections import deque
from vnpy.trader.constant import Interval, Direction, Offset


class ArbWtCh3Strategy(StrategyTemplate):
    """"""

    author = "TheSuperMyo"

    price_add = 1
    ema_window = 180
    ema_th = 1.5
    arb_size = 1
    time_out = 120
    pricetick = 10
    # 价差以该合约的tick为基准更新（应该配置为主力）
    dom_symbol = 1
    day_open_time = time(9, 10)
    day_close_time = time(14, 50)
    night_open_time = time(21, 10)
    night_close_time = time(0, 50)

    leg1_symbol = ""
    leg2_symbol = ""
    ema_mid = 0.0
    ema_down = 0.0
    ema_up = 0.0
    leg1_last_ask = 0
    leg1_last_bid = 0
    leg2_last_ask = 0
    leg2_last_bid = 0
    spread_last_mid = 0

    parameters = [
        "price_add",
        "ema_window",
        "ema_th",
        "arb_size",
        "time_out",
        "dom_symbol",
        "pricetick",
    ]

    variables = [
        "leg1_symbol",
        "leg2_symbol",
        "ema_mid",
        "ema_down",
        "ema_up",
        "leg1_last_ask",
        "leg1_last_bid",
        "leg2_last_ask",
        "leg2_last_bid",
        "spread_last_mid",
    ]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: List[str],
        setting: dict
    ):
        """"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        self.spread_count: int = 0
        self.spread_mid_array = deque(maxlen = self.ema_window + 5)
        self.flag: int = 0
        self.counter: int = 0
        self.try_open: int = 0
        self.risk_counter: int = 0
        self.trade_counter: int = 0
        self.put_counter: int = 0

        print(vt_symbols)
        # Obtain contract info
        self.leg1_symbol, self.leg2_symbol = vt_symbols


    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")
        self.write_log("组合为{0}-{1}".format(self.leg1_symbol, self.leg2_symbol))

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")
        self.write_log("交易次数{0},单腿风险次数{1},单腿风险比{2}".format(self.trade_counter,self.risk_counter,self.trade_counter/(self.risk_counter+1)))

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        # 时间过滤
        if (tick.datetime.time() > self.day_open_time and tick.datetime.time() < self.day_close_time) or (tick.datetime.time() > self.night_open_time) or (tick.datetime.time() < self.day_close_time):
            self.flag = 1
            self.put_counter += 1
            if self.put_counter > 120:
                self.put_counter = 0
                self.put_event()
        else:
            if self.flag == 0:
                return
            code_time = datetime.now()
            self.write_log("{0} in on_tick:不在交易时间".format(code_time))
            # 活跃单全撤
            self.cancel_all()
            # 市价平仓
            if self.get_pos(self.leg1_symbol) > 0:
                # leg1平多
                vt_orderids = self.sell(self.leg1_symbol, self.leg1_last_bid - 10*self.pricetick, abs(self.get_pos(self.leg1_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            if self.get_pos(self.leg1_symbol) < 0:
                # leg1平空
                vt_orderids = self.cover(self.leg1_symbol, self.leg1_last_ask + 10*self.pricetick, abs(self.get_pos(self.leg1_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            if self.get_pos(self.leg2_symbol) > 0:
                # leg2平多
                vt_orderids = self.sell(self.leg2_symbol, self.leg2_last_bid - 10*self.pricetick, abs(self.get_pos(self.leg2_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            if self.get_pos(self.leg2_symbol) < 0:
                # leg2平空
                vt_orderids = self.cover(self.leg2_symbol, self.leg2_last_ask + 10*self.pricetick, abs(self.get_pos(self.leg2_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            self.flag = 0
            return

        # 行情
        if tick.vt_symbol == self.leg1_symbol:
            self.leg1_last_ask = tick.ask_price_1
            self.leg1_last_bid = tick.bid_price_1
            if self.dom_symbol == 1:
                spread_mid = (self.leg1_last_ask - self.leg2_last_bid + self.leg1_last_bid - self.leg2_last_ask) / 2
                self.spread_mid_array.append(spread_mid)
                self.spread_count += 1
            else:
                return
        elif tick.vt_symbol == self.leg2_symbol:
            self.leg2_last_ask = tick.ask_price_1
            self.leg2_last_bid = tick.bid_price_1
            if self.dom_symbol == 2:
                spread_mid = (self.leg1_last_ask - self.leg2_last_bid + self.leg1_last_bid - self.leg2_last_ask) / 2
                self.spread_mid_array.append(spread_mid)
                self.spread_count += 1
            else:
                return
        else:
            return

        # 确保行情足够
        if self.spread_count < self.ema_window + 5:
            return

        # 检查委托
        if self.active_orderids:
            if self.try_open:
                # 试图开仓中，判断是否存在一边全成
                if (abs(self.get_pos(self.leg1_symbol)) == self.arb_size) or (abs(self.get_pos(self.leg2_symbol)) == self.arb_size):
                    if abs(self.get_pos(self.leg1_symbol)) != self.arb_size:
                        code_time = datetime.now()
                        self.write_log("{0} in on_tick:{1}尝试追单".format(code_time, self.leg1_symbol))
                        # leg1没到位
                        for vt_orderid in list(self.active_orderids):
                            order = self.get_order(vt_orderid)
                            if not order:
                                self.write_log("未找到该订单{}".format(vt_orderid))
                            if order and order.vt_symbol == self.leg1_symbol:
                                tar_direction = order.direction
                                tar_offset = order.offset
                                tar_price = order.price
                                tar_vol = self.arb_size - abs(self.get_pos(self.leg1_symbol))
                                if tar_direction == Direction.LONG:
                                    tar_price += self.price_add * self.pricetick
                                else:
                                    tar_price -= self.price_add * self.pricetick
                                self.cancel_order(order.vt_orderid)
                                # 挂新单
                                vt_orderids = self.send_order(order.vt_symbol,tar_direction,tar_offset,tar_price,tar_vol) 
                                if vt_orderids:
                                    for vt_orderid in vt_orderids:
                                        self.active_orderids.add(vt_orderid)
                                code_time = datetime.now()
                                self.write_log("{0} in on_tick:追单完成".format(code_time))
                                self.try_open = 0
                                break          
                    if abs(self.get_pos(self.leg2_symbol)) != self.arb_size:
                        code_time = datetime.now()
                        self.write_log("{0} in on_tick:{1}尝试追单".format(code_time,self.leg2_symbol))
                        # leg2没到位
                        for vt_orderid in list(self.active_orderids):
                            order = self.get_order(vt_orderid)
                            if not order:
                                self.write_log("未找到该订单{}".format(vt_orderid))
                            if order and order.vt_symbol == self.leg2_symbol:
                                tar_direction = order.direction
                                tar_offset = order.offset
                                tar_price = order.price
                                tar_vol = self.arb_size - abs(self.get_pos(self.leg2_symbol))
                                if tar_direction == Direction.LONG:
                                    tar_price += self.price_add * self.pricetick
                                else:
                                    tar_price -= self.price_add * self.pricetick
                                self.cancel_order(order.vt_orderid)
                                # 挂新单
                                vt_orderids = self.send_order(order.vt_symbol,tar_direction,tar_offset,tar_price,tar_vol)
                                if vt_orderids:
                                    for vt_orderid in vt_orderids:
                                        self.active_orderids.add(vt_orderid)
                                code_time = datetime.now()
                                self.write_log("{0} in on_tick:追单完成".format(code_time))
                                self.try_open = 0
                                break
            
            if self.counter < self.time_out:
                self.counter += 1
                return
            code_time = datetime.now()
            self.write_log("{} in on_tick:等待时间到，当前仓位：近月{}远月{}，本地委托{}".format(code_time,self.get_pos(self.leg1_symbol),self.get_pos(self.leg2_symbol),self.active_orderids))
            self.try_open = 0
            # 委托全撤
            self.cancel_all()
            return
        else:
            self.try_open = 0
            self.counter = 0
            
        # 检查单腿风险
        if (self.get_pos(self.leg1_symbol) + self.get_pos(self.leg2_symbol)) != 0:
            code_time = datetime.now()
            self.write_log("{} in on_tick:出现单腿风险，当前仓位：近月{}远月{}，本地委托{}".format(code_time,self.get_pos(self.leg1_symbol),self.get_pos(self.leg2_symbol),self.active_orderids))
            # 记录启动以来总单腿风险次数
            self.risk_counter += 1
            # 处理单腿
            # 市价平仓
            if self.get_pos(self.leg1_symbol) > 0:
                # leg1平多
                vt_orderids = self.sell(self.leg1_symbol, self.leg1_last_bid - 10*self.pricetick, abs(self.get_pos(self.leg1_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            if self.get_pos(self.leg1_symbol) < 0:
                # leg1平空
                vt_orderids = self.cover(self.leg1_symbol, self.leg1_last_ask + 10*self.pricetick, abs(self.get_pos(self.leg1_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            if self.get_pos(self.leg2_symbol) > 0:
                # leg2平多
                vt_orderids = self.sell(self.leg2_symbol, self.leg2_last_bid - 10*self.pricetick, abs(self.get_pos(self.leg2_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            if self.get_pos(self.leg2_symbol) < 0:
                # leg2平空
                vt_orderids = self.cover(self.leg2_symbol, self.leg2_last_ask + 10*self.pricetick, abs(self.get_pos(self.leg2_symbol)))
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
            return

        # 区间更新
        ema = talib.EMA(np.array(self.spread_mid_array), timeperiod = self.ema_window)
        self.ema_mid = ema[-2]
        self.ema_up = ema[-2] + self.ema_th * self.pricetick
        self.ema_down = ema[-2] - self.ema_th * self.pricetick
        self.spread_last_mid = self.spread_mid_array[-1]

        # 计算信号并发单
        if self.get_pos(self.leg1_symbol) == 0 and self.get_pos(self.leg2_symbol) == 0:
            if self.spread_last_mid >= self.ema_up:
                # 做空价差
                code_time = datetime.now()
                self.write_log(f"{code_time} in on_tick:{self.spread_last_mid}>={self.ema_up},价差开空头")
                vt_orderids = self.short(self.leg1_symbol, self.leg1_last_ask, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                vt_orderids = self.buy(self.leg2_symbol, self.leg2_last_bid, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                self.try_open = 1
                
            if self.spread_last_mid <= self.ema_down:
                # 做多价差
                code_time = datetime.now()
                self.write_log(f"{code_time} in on_tick:{self.spread_last_mid}<={self.ema_down},价差开多头")
                vt_orderids = self.buy(self.leg1_symbol, self.leg1_last_bid, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                vt_orderids = self.short(self.leg2_symbol, self.leg2_last_ask, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                self.try_open = 1

        if self.get_pos(self.leg1_symbol) > 0 and self.get_pos(self.leg2_symbol) < 0:
            if self.spread_last_mid >= self.ema_mid:
                # 反手做空价差
                code_time = datetime.now()
                self.write_log(f"{code_time} in on_tick:{self.spread_last_mid}>={self.ema_mid},价差多头退出")
                vt_orderids = self.sell(self.leg1_symbol, self.leg1_last_ask, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                vt_orderids = self.cover(self.leg2_symbol, self.leg2_last_bid, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                
            
        if self.get_pos(self.leg1_symbol) < 0 and self.get_pos(self.leg2_symbol) > 0:
            if self.spread_last_mid <= self.ema_mid:
                # 反手做多价差
                code_time = datetime.now()
                self.write_log(f"{code_time} in on_tick:{self.spread_last_mid}<={self.ema_mid},价差空头退出")
                vt_orderids = self.cover(self.leg1_symbol, self.leg1_last_bid, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                vt_orderids = self.sell(self.leg2_symbol, self.leg2_last_ask, self.arb_size)
                if vt_orderids:
                    for vt_orderid in vt_orderids:
                        self.active_orderids.add(vt_orderid)
                
    def on_trade(self, bars: Dict[str, BarData]) -> None:
        """
        Callback of trade.
        """
        self.trade_counter += 1
        code_time = datetime.now()
        self.write_log("{} in on_trade:发生成交！当前仓位：近月{}远月{}，本地委托{}".format(code_time,self.get_pos(self.leg1_symbol),self.get_pos(self.leg2_symbol),self.active_orderids))

    