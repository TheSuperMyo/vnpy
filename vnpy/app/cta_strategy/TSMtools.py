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
import pandas as pd
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

    def tr(self, array=False):
        """ 真实波幅 """
        result = talib.TRANGE(self.high, self.low, self.close)
        if array:
            return result
        return result[-1]

    def polyfit(self, n):
        """ 一二阶拟合斜率 """
        Y = self.close[-n:] - np.mean(self.close[-n:])  #去中心化处理,作为拟合用的因变量
        X = np.linspace(1,len(Y),len(Y)) #拟合用的自变量
    
        poly_1 = np.polyfit(X,Y,deg=1) #一阶拟合
        poly_2 = np.polyfit(X,Y,deg=2) #二阶拟合

        return poly_1[0], poly_2[0]

    def er(self, n, array=False):
        """ ER位移路程比 """
        pre_close = np.zeros(self.size)
        pre_n_close = np.zeros(self.size)
        pre_cumsum = np.zeros(self.size)

        pre_close[1:] = self.close[:-1]
        pre_n_close[n:] = self.close[:-n]
        # 计算单位周期位移
        m1 = abs(self.close - pre_close)
        # 计算n周期位移
        x = abs(self.close - pre_n_close)
        # 计算n周期单位位移加总（路程）
        cumsum = np.cumsum(m1)
        pre_cumsum[n:] = cumsum[:-n]
        s = cumsum - pre_cumsum

        ER = x/s        
        if array:
            return ER
        return ER[-1]

    def angle(self, n, array=False):
        """ 线性回归角度 """
        angle = talib.LINEARREG_SLOPE(self.close, n)   
        if array:
            return angle
        return angle[-1]

    def clfxc(self, n, array=False):
        """缠论分型通道"""
        clfx_high = np.zeros(self.size)
        clfx_low = np.zeros(self.size)
        clfx_high_index = []
        clfx_low_index = []
        
        # 遍历，找到是分型点的index
        for i in range(1,self.size-1):
            if self.high[i]>self.high[i-1] and self.high[i]>self.high[i+1] and self.low[i]>self.low[i-1] and self.low[i]>self.low[i+1]:
                clfx_high_index.append(i)
            elif self.high[i]<self.high[i-1] and self.high[i]<self.high[i+1] and self.low[i]<self.low[i-1] and self.low[i]<self.low[i+1]:
                clfx_low_index.append(i)
        # 填充“当前时点最近一个分型值”数组
        print(clfx_high_index)
        for i in range(len(clfx_high_index)-1):
            clfx_high[clfx_high_index[i]:clfx_high_index[i+1]] = self.high[clfx_high_index[i]]
        if len(clfx_high_index) >= 2:
            clfx_high[clfx_high_index[-1]:] = self.high[clfx_high_index[-1]]

        for i in range(len(clfx_low_index)-1):
            clfx_low[clfx_low_index[i]:clfx_low_index[i+1]] = self.low[clfx_low_index[i]]
        if len(clfx_low_index) >= 2:
            clfx_low[clfx_low_index[-1]:] = self.low[clfx_low_index[-1]]
        # 窗口期内最大分型点的数值构成通道上下轨
        up = talib.MAX(clfx_high, n)
        down = talib.MIN(clfx_low, n)

        if array:
            return up, down
        return up[-1], down[-1]

    def LLT(self, n, array=False):
        """广发低延时均线"""
        LLT = np.zeros(self.size)
        LLT[:3] = self.close[:3]
        a = 2/(n+1)
        """LLT(T) = (a - a**2/4)*p(T) + (a**2/2)*p(T-1)
					- (a - 3a**2/4)*p(T-2) + 2(1-a)*LLT(T-1)
					- (1-a)**2*LLT(T-2)   T>=3
			LLT(T) = p(T)  0<T<=2
			a = 2/(d+1)"""
        for i in range(3,self.size):
            LLT[i] = (a-(a**2)/4)*self.close[i] + (a**2/2)*self.close[i-1] - (a-3*(a**2)/4)*self.close[i-2] + 2*(1-a)*LLT[i-1] - (1-a)**2*LLT[i-2]

        if array:
            return LLT
        return LLT[-1]

    def bias_SMA_Accumulated_signal(self, ma_len, window_len, std_n, array=False):
        """价格-均线l窗口std通道信号"""
        signal = np.zeros(self.size)
        bias = self.close - talib.SMA(self.close, ma_len)
        bias_Accu = talib.SUM(bias, window_len)
        bias_var = talib.VAR(bias, ma_len)
        bias_Accu_std = talib.SQRT(talib.SUM(bias_var, window_len))

        for i in range(self.size):
            if bias_Accu[i] > std_n * bias_Accu_std[i]:
                signal[i] = 1
            elif bias_Accu[i] < -1 * std_n * bias_Accu_std[i]:
                signal[i] = -1
            else:
                signal[i] = 0
        
        if array:
            return signal
        return signal[-1]

    def higher_order_moment(self, moment_order, n, array=False):
        """因为收益率均值较小，此处返回高阶原点矩"""
        # 对数收益率序列，长度size-1
        log_r = self.log_return(True)
        # 原点矩
        result = talib.SUM(log_r**moment_order, n)/n

        if array:
            return result
        return result[-1]
        
        
        

        
        


        

            
                
        

