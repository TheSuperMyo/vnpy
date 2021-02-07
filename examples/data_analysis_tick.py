from datetime import datetime, date
from contextlib import closing
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
#from statsmodels.stats.diagnostic import acorr_ljungbox
#from statsmodels.tsa.stattools import adfuller as ADF
#from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
import talib
import arb

def null_analysis_and_show(ts):
    """计空值并画图"""
    if ts is None:
        print("数据为空，请输入数据")
    print("检验空值")
    nan_num = ts.isnull().sum()
    print(f"总体空值为 {nan_num}")
    print("画图")
    plt.figure(figsize=(20,8))
    plt.plot(range(0,len(ts)), ts, "ob",color='c')
    plt.show()

def statitstic_info(ts):
    """基本统计"""
    mean = round(ts.mean(), 4)
    median = round(ts.median(), 4)
    std = round(ts.std(), 4)
    print(f"样本平均数：{mean}, 中位数: {median}, 标准差{std}")
    skew = round(ts.skew(), 4)
    kurt = round(ts.kurt(), 4)
    print(f"偏度为：{skew}, 峰度为：{kurt}\n")
    plt.figure(figsize=(20,8))
    plt.hist(ts, bins=30, histtype='stepfilled', density=True)
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



