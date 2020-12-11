from typing import Callable
from vnpy.app.cta_strategy import (
    BarGenerator,
    ArrayManager
)
from vnpy.trader.object import (
    TickData,
    BarData
)
from vnpy.trader.constant import Interval
import numpy as np
import talib

class TSMBarGenerator(BarGenerator):
    '''
    自定义K线生成器，可以统一采用计数切分，
    支持任意分钟K线
    支持按57为分界切分1min线
    '''
    def __init__(
        self,
        on_bar: Callable,
        window: int = 0,
        on_window_bar: Callable = None,
        interval: Interval = Interval.MINUTE
    ):
        super().__init__(on_bar, window, on_window_bar, interval)

    def update_tick(self, tick:TickData):
        """
        Update new tick data into generator.
        """
        new_minute = False

        # Filter tick data with 0 last price
        if not tick.last_price:
            return

        if not self.bar:
            new_minute = True
        # 按57秒为界切分，尽量错峰交易
        #elif self.bar.datetime.minute != tick.datetime.minute:
        elif tick.datetime.second > 57 and self.last_tick.datetime.second < 57:
            self.bar.datetime = self.bar.datetime.replace(
                second=0, microsecond=0
            )
            self.on_bar(self.bar)

            new_minute = True

        if new_minute:
            self.bar = BarData(
                symbol=tick.symbol,
                exchange=tick.exchange,
                interval=Interval.MINUTE,
                datetime=tick.datetime,
                gateway_name=tick.gateway_name,
                open_price=tick.last_price,
                high_price=tick.last_price,
                low_price=tick.last_price,
                close_price=tick.last_price,
                open_interest=tick.open_interest
            )
        else:
            self.bar.high_price = max(self.bar.high_price, tick.last_price)
            self.bar.low_price = min(self.bar.low_price, tick.last_price)
            self.bar.close_price = tick.last_price
            self.bar.open_interest = tick.open_interest
            self.bar.datetime = tick.datetime

        if self.last_tick:
            volume_change = tick.volume - self.last_tick.volume
            self.bar.volume += max(volume_change, 0)

        self.last_tick = tick

    def update_bar(self, bar:BarData):
        """
        Update 1 minute bar into generator
        """
        # If not inited, creaate window bar object
        if not self.window_bar:
            # Generate timestamp for bar data
            if self.interval == Interval.MINUTE:
                dt = bar.datetime.replace(second=0, microsecond=0)
            else:
                dt = bar.datetime.replace(minute=0, second=0, microsecond=0)

            self.window_bar = BarData(
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=dt,
                gateway_name=bar.gateway_name,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price
            )
        # Otherwise, update high/low price into window bar
        else:
            self.window_bar.high_price = max(
                self.window_bar.high_price, bar.high_price)
            self.window_bar.low_price = min(
                self.window_bar.low_price, bar.low_price)

        # Update close price/volume into window bar
        self.window_bar.close_price = bar.close_price
        self.window_bar.volume += int(bar.volume)
        self.window_bar.open_interest = bar.open_interest

        # Check if window bar completed
        finished = False

        if self.interval == Interval.MINUTE:
            # x-minute bar
            # 和小时K线一样，采用计数切分法
            # if not (bar.datetime.minute + 1) % self.window:
            #     finished = True
            if self.last_bar and bar.datetime.minute != self.last_bar.datetime.minute:
                self.interval_count += 1

                if self.interval_count % self.window:
                    finished = True
                    self.interval_count = 0

        elif self.interval == Interval.HOUR:
            if self.last_bar and bar.datetime.hour != self.last_bar.datetime.hour:
                # 1-hour bar
                if self.window == 1:
                    finished = True
                # x-hour bar
                else:
                    self.interval_count += 1

                    if not self.interval_count % self.window:
                        finished = True
                        self.interval_count = 0

        if finished:
            self.on_window_bar(self.window_bar)
            self.window_bar = None

        # Cache last bar object
        self.last_bar = bar

class TSMArrayManager(ArrayManager):
    def __init__(self, size=100):
        super().__init__(size)

    def log_return(self, array=False):
        """对数收益率"""
        arrayold = self.close_array[:-1]
        arraynew = self.close_array[1:]
        result = np.log(arraynew/arrayold)
        if array:
            return result
        return result[-1]

    def log_return_sma(self, n, array=False):
        """对数收益率均值"""
        result = talib.SMA(self.log_return(True), n)
        if array:
            return result
        return result[-1]

    def log_return_std(self, n, array=False):
        """对数收益率标准差"""
        result = talib.STDDEV(self.log_return(True), n)
        if array:
            return result
        return result[-1]

    def log_close(self, array=False):
        """对数价格"""
        result = np.log(self.close)
        if array:
            return result
        return result[-1]

    def mom(self, n, array=False):
        """ N-bar 动量 """
        result = talib.MOM(self.close, n)
        if array:
            return result
        return result[-1]

    def mom_rocp(self, n1, n2, array=False):
        """ N1-bar动量的N2-bar变化率 """
        result = talib.ROCP(self.mom(n1,True), n2)
        if array:
            return result
        return result[-1]

    def mom_rocp_rsi(self, n1, n2, n3, array=False):
        """ N1-bar动量的N2-bar变化率的RSI指标 """
        result = talib.RSI(self.mom_rocp(n1, n2, True), n3)
        if array:
            return result
        return result[-1]
    

