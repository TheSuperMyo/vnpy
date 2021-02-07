from datetime import datetime, date
from contextlib import closing
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
#from statsmodels.stats.diagnostic import acorr_ljungbox
#from statsmodels.tsa.stattools import adfuller as ADF
#from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
#from tqsdk.ta import BOLL,EMA
import talib
import arb

def base_analysis(spread_series):

    if spread_series is None:
        print("数据为空，请输入数据")

    print("检验空值")
    nan_num = spread_series.isnull().sum()
    print(f"总体空值为 {nan_num}")
    
    print("画图")
    plt.figure(figsize=(20,8))
    plt.plot(range(0,len(spread_series)), spread_series, "ob",color='c')
    plt.show()
    
def random_test(spread_series):
    """"""
    acorr_result = acorr_ljungbox(spread_series, lags=1)
    p_value = acorr_result[1]
    if p_value < 0.05:
        print("随机性检验：非纯随机性")
    else:
        print("随机性检验：纯随机性")
    print(f"白噪声检验结果:{acorr_result}\n")

def stability_test(spread_series):
    """"""
    statitstic = ADF(spread_series)
    t_s = statitstic[1]
    t_c = statitstic[4]["5%"]

    if t_s > t_c:
        print("平稳性检验：存在单位根，时间序列不平稳")
    else:
        print("平稳性检验：不存在单位根，时间序列平稳")

    print(f"ADF检验结果：{statitstic}\n")

def autocorrelation_test(spread_series):
    """"""
    print("画出自相关性图，观察自相关特性")

    plot_acf(spread_series, lags=60)
    plt.show()

    plot_pacf(spread_series, lags=60).show()
    plt.show()

def statitstic_info(spread_series):
    """"""
    mean = round(spread_series.mean(), 4)
    median = round(spread_series.median(), 4)
    print(f"样本平均数：{mean}, 中位数: {median}")

    skew = round(spread_series.skew(), 4)
    kurt = round(spread_series.kurt(), 4)

    if skew == 0:
        skew_attribute = "对称分布"
    elif skew > 0:
        skew_attribute = "分布偏左"
    else:
        skew_attribute = "分布偏右"

    if kurt == 0:
        kurt_attribute = "正态分布"
    elif kurt > 0:
        kurt_attribute = "分布陡峭"
    else:
        kurt_attribute = "分布平缓"

    print(f"偏度为：{skew}，属于{skew_attribute}；峰度为：{kurt}，属于{kurt_attribute}\n")

def show_boll(spread_df, window, boll_wide, min_volume=1):

    std = talib.STDDEV(spread["mid"], n)
    boll_mid = talib.SMA(spread["mid"], window)
    boll_top = boll_mid + boll_wide * std
    boll_bottom = boll_mid - boll_wide * std

    up_signal = []
    down_signal = []
    len_data = len(spread["mid"])
    for i in range(1, len_data):
        #if spread.iloc[i]["bid"] > boll.iloc[i]["top"]and spread.iloc[i - 1]["bid"] < boll.iloc[i - 1]["top"]:
        if spread.iloc[i]["mid"] > boll.iloc[i]["top"]:
            if spread.iloc[i]["bid_v"] > min_volume:
                down_signal.append(i)

        #elif spread.iloc[i]["ask"] < boll.iloc[i]["bottom"] and spread.iloc[i - 1]["ask"] > boll.iloc[i - 1]["bottom"]:
        elif spread.iloc[i]["mid"] < boll.iloc[i]["bottom"]:
            if spread.iloc[i]["ask_v"] > min_volume:
                up_signal.append(i)

    plt.figure(figsize=(20, 8))
    
    plt.plot(range(0,len(spread["mid"])),spread["mid"],'ob',lw=0.5,color='c')
    plt.plot(range(0,len(spread["ask"])),spread["ask"], '^', markersize=10, color='r',
                label='UP signal', markevery=up_signal)
    plt.plot(range(0,len(spread["bid"])),spread["bid"], 'v', markersize=10, color='g',
                label='DOWN signal', markevery=down_signal)
    plt.plot(range(0,len(boll_top)),boll_top, lw=0.5, color="r")
    plt.plot(range(0,len(boll_bottom)),boll_bottom, lw=0.5, color="g")
    plt.plot(range(0,len(boll_mid)),boll_mid, lw=0.5, color="b")
    plt.legend()
    plt.show()

def show_ema_fixed(spread, window, fixed_value, min_volume=1):
    #data = pd.DataFrame(index=spread.index, columns=["close"])
    #data["close"] = spread["mid"]
    ema = talib.EMA(spread["mid"], window)
    ema_top = ema + fixed_value
    ema_bottom = ema - fixed_value
    
    up_signal = []
    down_signal = []
    len_data = len(spread["mid"])
    for i in range(1, len_data):
        #if spread.iloc[i]["bid"] > ema.iloc[i]["top"] and spread.iloc[i - 1]["bid"] < ema.iloc[i - 1]["top"]:
        if spread.iloc[i]["mid"] > ema_top[i]:
            if spread.iloc[i]["bid_v"] > min_volume:
                up_signal.append(i)
                down_signal.append(i)

        #elif spread.iloc[i]["ask"] < ema.iloc[i]["bottom"] and spread.iloc[i - 1]["ask"] > ema.iloc[i - 1]["bottom"]:
        elif spread.iloc[i]["mid"] < ema_bottom[i]:
            if spread.iloc[i]["ask_v"] > min_volume:
                up_signal.append(i)
                down_signal.append(i)

    plt.figure(figsize=(20, 8))
    
    plt.plot(range(0,len(spread["mid"])),spread["mid"],'ob',lw=0.5,color='c')
    plt.plot(range(0,len(spread["bid"])),spread["bid"], '^', markersize=10, color='r',
                label='UP signal', markevery=up_signal)
    plt.plot(range(0,len(spread["ask"])),spread["ask"], 'v', markersize=10, color='g',
                label='DOWN signal', markevery=down_signal)
    plt.plot(range(0,len(ema_top)),ema_top, lw=0.5, color="r")
    plt.plot(range(0,len(ema_bottom)),ema_bottom, lw=0.5, color="g")
    plt.plot(range(0,len(ema)),ema, lw=0.5, color="b")
    plt.legend()
    plt.show()

def show_ou_best(spread, window, cost, min_volume=1):
    data = pd.DataFrame(index=spread.index, columns=["close","mid","top","bottom","a"])
    data["close"] = spread["mid"]
    data["mid"] = data["close"].rolling(window).apply(arb.get_ou_mean,args=(cost,))
    data["a"] = data["close"].rolling(window).apply(arb.get_ou_a,args=(cost,))
    data["top"] = data["mid"] - data["a"]
    data["bottom"] = data["mid"] + data["a"]

    up_signal = []
    down_signal = []
    len_data = len(spread["mid"])
    for i in range(1, len_data):
        #if spread.iloc[i]["bid"] > data.iloc[i]["top"]and spread.iloc[i - 1]["bid"] < data.iloc[i - 1]["top"]:
        if spread.iloc[i]["bid"] > data.iloc[i]["top"]:
            if spread.iloc[i]["bid_v"] > min_volume:
                down_signal.append(i)

        #elif spread.iloc[i]["ask"] < data.iloc[i]["bottom"] and spread.iloc[i - 1]["ask"] > data.iloc[i - 1]["bottom"]:
        elif spread.iloc[i]["ask"] < data.iloc[i]["bottom"]:
            if spread.iloc[i]["ask_v"] > min_volume:
                up_signal.append(i)

    plt.figure(figsize=(20, 8))
    
    plt.plot(range(0,len(spread["mid"])),spread["mid"],'ob',lw=0.5,color='c')
    plt.plot(range(0,len(spread["ask"])),spread["ask"], '^', markersize=10, color='r',
                label='UP signal', markevery=up_signal)
    plt.plot(range(0,len(spread["bid"])),spread["bid"], 'v', markersize=10, color='g',
                label='DOWN signal', markevery=down_signal)
    plt.plot(range(0,len(data["top"])),data["top"], lw=0.5, color="r")
    plt.plot(range(0,len(data["bottom"])),data["bottom"], lw=0.5, color="g")
    plt.plot(range(0,len(data["mid"])),data["mid"], lw=0.5, color="b")
    plt.legend()
    plt.show()

def show_ema_fixed_info(spread, window, fixed_value, min_volume=1):
    ema = talib.EMA(spread["mid"], window)
    ema_top = ema + fixed_value
    ema_bottom = ema - fixed_value
    
    up_signal = []
    down_signal = []
    len_data = len(spread["mid"])
    for i in range(1, len_data):
        #if spread.iloc[i]["bid"] > ema.iloc[i]["top"] and spread.iloc[i - 1]["bid"] < ema.iloc[i - 1]["top"]:
        if spread.iloc[i]["mid"] > ema_top[i]:
            if spread.iloc[i]["bid_v"] > min_volume:
                up_signal.append(i)
                down_signal.append(i)

        #elif spread.iloc[i]["ask"] < ema.iloc[i]["bottom"] and spread.iloc[i - 1]["ask"] > ema.iloc[i - 1]["bottom"]:
        elif spread.iloc[i]["mid"] < ema_bottom[i]:
            if spread.iloc[i]["ask_v"] > min_volume:
                up_signal.append(i)
                down_signal.append(i)
    print("在窗口长度为{0}，阈值为{1}情况下，共产生{2}个信号".format(window, fixed_value, len(up_signal)))

def generate_spread_tick(dom_path, sub_path, result_path):
    raw_df1 = pd.read_csv(dom_path)
    raw_df2 = pd.read_csv(sub_path)
    result = raw_df1.set_index("datetime").join(raw_df2.set_index("datetime"), on="datetime", how="outer", lsuffix='_dom', rsuffix='_sub')
    res = result.sort_index()
    print(len(res))
    print(res.isnull().sum())
    res2 = res.fillna(method='ffill')
    print(len(res2))
    print(res2.isnull().sum())
    res2.to_csv(result_path)
    return res2

generate_spread_tick("", "", "")

# raw = pd.read_csv("D:/Study/数据/SHFE.al2009-2008_0706-0731_tick.csv", index_col='datetime')
# # spread = 远月-近月
# spread = pd.DataFrame(index=raw.index, columns=["ask,mid,bid,ask_v,bid_v"])
# spread.index = pd.to_datetime(spread.index)
# spread["ask"] = raw['SHFE.al2009.ask_price1'] - raw['SHFE.al2008.bid_price1']
# spread["ask_v"] = raw['SHFE.al2009.ask_volume1'].where(raw['SHFE.al2009.ask_volume1'] < raw['SHFE.al2008.bid_volume1'], raw['SHFE.al2008.bid_volume1'])
# spread["mid"] = (raw['SHFE.al2009.ask_price1'] - raw['SHFE.al2008.bid_price1'] + raw['SHFE.al2009.bid_price1'] - raw['SHFE.al2008.ask_price1'])/2
# spread["bid"] = raw['SHFE.al2009.bid_price1'] - raw['SHFE.al2008.ask_price1']
# spread["bid_v"] = raw['SHFE.al2009.bid_volume1'].where(raw['SHFE.al2009.bid_volume1'] < raw['SHFE.al2008.ask_volume1'], raw['SHFE.al2008.ask_volume1'])

# window_list = range(120,481,60)
# th_list = range(3,6,1)
# for win in window_list:
#     for t in th_list:
#         show_ema_fixed_info(spread, win, 2.5*t)

