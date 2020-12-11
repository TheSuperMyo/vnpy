from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Callable
from itertools import product
from functools import lru_cache
from time import time
import multiprocessing
import random
import traceback

import numpy as np
from pandas import DataFrame
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from deap import creator, base, tools, algorithms
from itertools import combinations

from vnpy.trader.constant import (Direction, Offset, Exchange, Status)
from vnpy.trader.database import database_manager
from vnpy.trader.object import OrderData, TradeData, BarData, TickData
from vnpy.trader.utility import round_to

from .base import (
    EngineType,
    STOPORDER_PREFIX,
    StopOrder,
    StopOrderStatus,
    INTERVAL_DELTA_MAP
)
from vnpy.app.portfolio_strategy.template import StrategyTemplate


# Set deap algo
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)

# 排队初始量
LQ = 123456


class OptimizationSetting:
    """
    Setting for runnning optimization.
    """

    def __init__(self):
        """"""
        self.params = {}
        self.target_name = ""

    def add_parameter(
        self, name: str, start: float, end: float = None, step: float = None
    ):
        """"""
        if not end and not step:
            self.params[name] = [start]
            return

        if start >= end:
            print("参数优化起始点必须小于终止点")
            return

        if step <= 0:
            print("参数优化步进必须大于0")
            return

        value = start
        value_list = []

        while value <= end:
            value_list.append(value)
            value += step

        self.params[name] = value_list

    def set_target(self, target_name: str):
        """"""
        self.target_name = target_name

    def generate_setting(self):
        """"""
        keys = self.params.keys()
        values = self.params.values()
        products = list(product(*values))

        settings = []
        for p in products:
            setting = dict(zip(keys, p))
            settings.append(setting)

        return settings

    def generate_setting_ga(self):
        """"""
        settings_ga = []
        settings = self.generate_setting()
        for d in settings:
            param = [tuple(i) for i in d.items()]
            settings_ga.append(param)
        return settings_ga


class BacktestingEngine:
    """"""

    gateway_name = "BACKTESTING"

    def __init__(self):
        """"""
        self.vt_symbols = []
        self.symbol_dom = ""
        self.symbol_sub = ""
        self.exchange = None
        self.start = None
        self.end = None
        self.rate = 0
        self.slippage = 0
        self.size = 1
        self.pricetick = 0
        self.capital = 1_000_000

        self.strategy_class = None
        self.strategy = None
        self.tick: TickData
        self.datetime = None

        self.callback = None
        self.history_data_dom = []
        self.history_data_sub = []

        self.limit_order_count = 0
        self.limit_orders = {}
        self.active_limit_orders = {}
        self.limit_que = {}
        self.limit_que_last_tick ={}

        self.trade_count = 0
        self.price_trade_count = 0
        self.volume_trade_count = 0
        self.trades = {}

        self.logs = []

        self.daily_results = {}
        self.daily_df = None

    def clear_data(self):
        """
        Clear all data of last backtesting.
        """
        self.strategy = None
        self.tick = None
        self.datetime = None

        self.limit_order_count = 0
        self.limit_orders.clear()
        self.active_limit_orders.clear()
        self.limit_que.clear()
        self.limit_que_last_tick.clear()

        self.trade_count = 0
        self.price_trade_count = 0
        self.volume_trade_count = 0
        self.trades.clear()

        self.logs.clear()
        self.daily_results.clear()

    def set_parameters(
        self,
        vt_symbols,
        start,
        rate,
        slippage,
        size,
        pricetick,
        capital = 0,
        end = None
    ):
        """"""
        
        self.vt_symbols = vt_symbols
        self.rate = rate
        self.slippage = slippage
        self.size = size
        self.pricetick = pricetick
        self.start = start

        self.symbol_dom, exchange_str = self.vt_symbols[0].split(".")
        self.symbol_sub, exchange_str = self.vt_symbols[1].split(".")
        self.exchange = Exchange(exchange_str)

        self.capital = capital
        self.end = end

    def add_strategy(self, strategy_class: type, setting: dict):
        """"""
        self.strategy_class = strategy_class
        self.strategy = strategy_class(self, strategy_class.__name__, self.vt_symbols, setting)

    def load_data(self):
        """"""
        self.output("开始加载历史数据")

        if not self.end:
            self.end = datetime.now()

        if self.start >= self.end:
            self.output("起始日期必须小于结束日期")
            return

        self.history_data_dom.clear()       # Clear previously loaded history data
        self.history_data_sub.clear()

        # 每次循环读一天，时间向后递推1秒，再读下一天
        progress_delta = timedelta(days=1)
        total_delta = self.end - self.start
        interval_delta = timedelta(seconds=1)

        start = self.start
        end = self.start + progress_delta
        progress = 0

        while start < self.end:
            end = min(end, self.end)  # Make sure end time stays within set range

            data_dom = load_tick_data(self.symbol_dom, self.exchange, start, end, self.symbol_dom)
            self.history_data_dom.extend(data_dom)
            data_sub = load_tick_data(self.symbol_sub, self.exchange, start, end, self.symbol_sub)
            self.history_data_sub.extend(data_sub)

            progress += progress_delta / total_delta
            progress = min(progress, 1)
            progress_bar = "#" * int(progress * 10)
            self.output(f"加载进度：{progress_bar} [{progress:.0%}]")

            start = end + interval_delta
            end += (progress_delta + interval_delta)

        self.output(f"历史数据加载完成，{self.symbol_dom}数据量：{len(self.history_data_dom)}，{self.symbol_sub}数据量{len(self.history_data_sub)}")

    def run_backtesting(self):

        self.strategy.on_init()
        self.strategy.inited = True
        self.output("策略初始化完成")

        self.strategy.on_start()
        self.strategy.trading = True
        self.output("开始回放历史数据")

        data_dom_index = 0
        data_sub_index = 0
        while data_dom_index < len(self.history_data_dom) or data_sub_index < len(self.history_data_sub):
            # dom已经全部回放完毕
            if data_dom_index >= len(self.history_data_dom):
                data_sub = self.history_data_sub[data_sub_index]
                try:
                    self.new_tick(data_sub)
                    data_sub_index += 1
                    continue
                except Exception:
                    self.output("推送tick时触发异常，回测终止")
                    self.output(traceback.format_exc())
                    return
            # sub已经回放完毕
            if data_sub_index >= len(self.history_data_sub):
                data_dom = self.history_data_dom[data_dom_index]
                try:
                    self.new_tick(data_dom)
                    data_dom_index += 1
                    continue
                except Exception:
                    self.output("推送tick时触发异常，回测终止")
                    self.output(traceback.format_exc())
                    return
            data_dom = self.history_data_dom[data_dom_index]
            data_sub = self.history_data_sub[data_sub_index]
            # 按时间顺序先推先到的
            # 行情产生时间一样，实盘按字母顺序
            if data_dom.datetime > data_sub.datetime:
                try:
                    self.new_tick(data_sub)
                    data_sub_index += 1
                except Exception:
                    self.output("推送tick时触发异常，回测终止")
                    self.output(traceback.format_exc())
                    return
            # elif data_dom.datetime <= data_sub.datetime:
            else:
                try:
                    self.new_tick(data_dom)
                    data_dom_index += 1
                except Exception:
                    self.output("推送tick时触发异常，回测终止")
                    self.output(traceback.format_exc())
                    return

        self.output("历史数据回放结束")
        self.output(f"见价成交数量：{self.price_trade_count}  排队成交数量：{self.volume_trade_count}")

    def calculate_result(self):
        """"""
        self.output("开始计算逐日盯市盈亏")

        if not self.trades:
            self.output("成交记录为空，无法计算")
            return

        # Add trade data into daily reuslt.
        for trade in self.trades.values():
            d = trade.datetime.date()
            daily_result = self.daily_results[d]
            daily_result.add_trade(trade)

        # Calculate daily result by iteration.
        pre_close = 0
        start_pos = 0

        for daily_result in self.daily_results.values():
            daily_result.calculate_pnl(
                pre_close,
                start_pos,
                self.size,
                self.rate,
                self.slippage,
                False
            )

            pre_close = daily_result.close_price
            start_pos = daily_result.end_pos

        # Generate dataframe
        results = defaultdict(list)

        for daily_result in self.daily_results.values():
            for key, value in daily_result.__dict__.items():
                results[key].append(value)

        self.daily_df = DataFrame.from_dict(results).set_index("date")

        self.output("逐日盯市盈亏计算完成")
        return self.daily_df

    def calc_pbo(self, op_re:list, s=10):
        # 计算过拟合概率 PBO
        
        # 获取各参数的每日收益率，建立DataFrame
        setting_returcn_dict = {}
        for re in op_re:
            setting_returcn_dict[re[0]] = re[3]['return']
        df = pd.DataFrame.from_dict(setting_returcn_dict)
        
        # 收益率时序切分为 S 份，每份包含 T/S 日收益率
        df = df.reset_index()
        num = pd.cut(df.index,bins=s, labels=range(0, s))
        df['num'] = num
        # 组合
        comb_list = list(combinations(range(0,s), int(s/2)))
        print(f"从总样本内（共{s}段）取{int(s/2)}段数据组成样本内，共有{len(comb_list)}种取法")
                        
        # 对于每种取样方法计算 样本内最优参数 在样本外不及中位数概率
        pbo_yes = 0 # 样本外表现不及中位数
        pbo_no = 0 # 样本外表现优于中位数
        for comb in comb_list:
            is_setting_sharpe_dict = {}
            os_setting_sharpe_dict = {}
            is_df = pd.DataFrame()
            os_df = pd.DataFrame()
            # 组成样本内外的 DataFrame
            for name,group in df.groupby('num'):
                if name in comb:
                    is_df = is_df.append(group)
                else:
                    os_df = os_df.append(group)
            #print(f"对于取样方式{comb}")
            #print(f"样本内长度{len(is_df)}")
            #print(f"样本外长度{len(os_df)}")
            is_df = is_df.drop(['num','date'],axis=1)
            os_df = os_df.drop(['num','date'],axis=1)
            
            # 样本内外分别计算夏普，并保存排序
            for col in is_df.columns:
                is_setting_sharpe_dict[col] = (is_df[col].mean() - (0.04/240))/ is_df[col].std() * np.sqrt(240)
            for col in os_df.columns:
                os_setting_sharpe_dict[col] = (os_df[col].mean() - (0.04/240))/ os_df[col].std() * np.sqrt(240)
            is_setting_sharpe_dict_list= sorted(is_setting_sharpe_dict.items(),key=lambda x:x[1])
            os_setting_sharpe_dict_list= sorted(os_setting_sharpe_dict.items(),key=lambda x:x[1])
            #print(f"此次样本内参数排序{is_setting_sharpe_dict_list}")
            #print(f"此次样本外参数排序{os_setting_sharpe_dict_list}")
            
            # 找到样本内最优在样本外的表现 是否优于 所有参数表现的中位数
            index_os = 1
            for os_kv in os_setting_sharpe_dict_list:
                # 找样本内最优参数在样本外对应的排序
                if os_kv[0] == is_setting_sharpe_dict_list[-1][0]:
                    break
                else:
                    index_os += 1
            w = index_os/len(os_setting_sharpe_dict_list)
            print(f"样本内组合为{comb}时，样本内最优参数在样本外相对排名 W （0,1）越大说明在样本外越优秀：{w}")
            if w < 0.5:
                pbo_yes += 1
            else:
                pbo_no += 1
        print(f"经计算，过拟合概率PBO为：{pbo_yes/(pbo_yes+pbo_no)}")
        return pbo_yes/(pbo_yes+pbo_no)

    def calculate_statistics(self, df: DataFrame = None, output=True):
        """"""
        self.output("开始计算策略统计指标")

        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            # Set all statistics to 0 if no trade.
            start_date = ""
            end_date = ""
            total_days = 0
            profit_days = 0
            loss_days = 0
            end_balance = 0
            max_drawdown = 0
            max_ddpercent = 0
            max_drawdown_duration = 0
            total_net_pnl = 0
            daily_net_pnl = 0
            total_commission = 0
            daily_commission = 0
            total_slippage = 0
            daily_slippage = 0
            total_turnover = 0
            daily_turnover = 0
            total_trade_count = 0
            daily_trade_count = 0
            total_return = 0
            annual_return = 0
            daily_return = 0
            return_std = 0
            sharpe_ratio = 0
            return_drawdown_ratio = 0
        else:
            # Calculate balance related time series data
            df["balance"] = df["net_pnl"].cumsum() + self.capital
            df["return"] = np.log(df["balance"] / df["balance"].shift(1)).fillna(0)
            df["highlevel"] = (
                df["balance"].rolling(
                    min_periods=1, window=len(df), center=False).max()
            )
            df["drawdown"] = df["balance"] - df["highlevel"]
            df["ddpercent"] = df["drawdown"] / df["highlevel"] * 100

            # Calculate statistics value
            start_date = df.index[0]
            end_date = df.index[-1]

            total_days = len(df)
            profit_days = len(df[df["net_pnl"] > 0])
            loss_days = len(df[df["net_pnl"] < 0])

            end_balance = df["balance"].iloc[-1]
            max_drawdown = df["drawdown"].min()
            max_ddpercent = df["ddpercent"].min()
            max_drawdown_end = df["drawdown"].idxmin()

            if isinstance(max_drawdown_end, date):
                max_drawdown_start = df["balance"][:max_drawdown_end].idxmax()
                max_drawdown_duration = (max_drawdown_end - max_drawdown_start).days
            else:
                max_drawdown_duration = 0

            total_net_pnl = df["net_pnl"].sum()
            daily_net_pnl = total_net_pnl / total_days

            total_commission = df["commission"].sum()
            daily_commission = total_commission / total_days

            total_slippage = df["slippage"].sum()
            daily_slippage = total_slippage / total_days

            total_turnover = df["turnover"].sum()
            daily_turnover = total_turnover / total_days

            total_trade_count = df["trade_count"].sum()
            daily_trade_count = total_trade_count / total_days

            total_return = (end_balance / self.capital - 1) * 100
            annual_return = total_return / total_days * 240
            daily_return = df["return"].mean() * 100
            return_std = df["return"].std() * 100

            if return_std:
                sharpe_ratio = (daily_return - (4/240))/ return_std * np.sqrt(240)
            else:
                sharpe_ratio = 0

            return_drawdown_ratio = -total_return / max_ddpercent

        # Output
        if output:
            self.output("-" * 30)
            self.output(f"首个交易日：\t{start_date}")
            self.output(f"最后交易日：\t{end_date}")

            self.output(f"总交易日：\t{total_days}")
            self.output(f"盈利交易日：\t{profit_days}")
            self.output(f"亏损交易日：\t{loss_days}")

            self.output(f"起始资金：\t{self.capital:,.2f}")
            self.output(f"结束资金：\t{end_balance:,.2f}")

            self.output(f"总收益率：\t{total_return:,.2f}%")
            self.output(f"年化收益：\t{annual_return:,.2f}%")
            self.output(f"最大回撤: \t{max_drawdown:,.2f}")
            self.output(f"百分比最大回撤: {max_ddpercent:,.2f}%")
            self.output(f"最长回撤天数: \t{max_drawdown_duration}")

            self.output(f"总盈亏：\t{total_net_pnl:,.2f}")
            self.output(f"总手续费：\t{total_commission:,.2f}")
            self.output(f"总滑点：\t{total_slippage:,.2f}")
            self.output(f"总成交金额：\t{total_turnover:,.2f}")
            self.output(f"总成交笔数：\t{total_trade_count}")

            self.output(f"日均盈亏：\t{daily_net_pnl:,.2f}")
            self.output(f"日均手续费：\t{daily_commission:,.2f}")
            self.output(f"日均滑点：\t{daily_slippage:,.2f}")
            self.output(f"日均成交金额：\t{daily_turnover:,.2f}")
            self.output(f"日均成交笔数：\t{daily_trade_count}")

            self.output(f"日均收益率：\t{daily_return:,.2f}%")
            self.output(f"收益标准差：\t{return_std:,.2f}%")
            self.output(f"Sharpe Ratio：\t{sharpe_ratio:,.2f}")
            self.output(f"收益回撤比：\t{return_drawdown_ratio:,.2f}")

        statistics = {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "profit_days": profit_days,
            "loss_days": loss_days,
            "capital": self.capital,
            "end_balance": end_balance,
            "max_drawdown": max_drawdown,
            "max_ddpercent": max_ddpercent,
            "max_drawdown_duration": max_drawdown_duration,
            "total_net_pnl": total_net_pnl,
            "daily_net_pnl": daily_net_pnl,
            "total_commission": total_commission,
            "daily_commission": daily_commission,
            "total_slippage": total_slippage,
            "daily_slippage": daily_slippage,
            "total_turnover": total_turnover,
            "daily_turnover": daily_turnover,
            "total_trade_count": total_trade_count,
            "daily_trade_count": daily_trade_count,
            "total_return": total_return,
            "annual_return": annual_return,
            "daily_return": daily_return,
            "return_std": return_std,
            "sharpe_ratio": sharpe_ratio,
            "return_drawdown_ratio": return_drawdown_ratio,
        }

        # Filter potential error infinite value
        for key, value in statistics.items():
            if value in (np.inf, -np.inf):
                value = 0
            statistics[key] = np.nan_to_num(value)

        self.output("策略统计指标计算完成")
        return statistics

    def show_chart(self, df: DataFrame = None):
        """"""
        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            return

        fig = make_subplots(
            rows=4,
            cols=1,
            subplot_titles=["Balance", "Drawdown", "Daily Pnl", "Pnl Distribution"],
            vertical_spacing=0.06
        )

        balance_line = go.Scatter(
            x=df.index,
            y=df["balance"],
            mode="lines",
            name="Balance"
        )
        drawdown_scatter = go.Scatter(
            x=df.index,
            y=df["drawdown"],
            fillcolor="red",
            fill='tozeroy',
            mode="lines",
            name="Drawdown"
        )
        pnl_bar = go.Bar(y=df["net_pnl"], name="Daily Pnl")
        pnl_histogram = go.Histogram(x=df["net_pnl"], nbinsx=100, name="Days")

        fig.add_trace(balance_line, row=1, col=1)
        fig.add_trace(drawdown_scatter, row=2, col=1)
        fig.add_trace(pnl_bar, row=3, col=1)
        fig.add_trace(pnl_histogram, row=4, col=1)

        fig.update_layout(height=1000, width=1000)
        fig.show()

    def run_optimization(self, optimization_setting: OptimizationSetting, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Use multiprocessing pool for running backtesting with different setting
        # Force to use spawn method to create new process (instead of fork on Linux)
        ctx = multiprocessing.get_context("spawn")
        #pool = ctx.Pool(multiprocessing.cpu_count())
        pool = ctx.Pool(2)

        results = []
        for setting in settings:
            result = (pool.apply_async(optimize, (
                target_name,
                self.strategy_class,
                setting,
                self.vt_symbols,
                self.start,
                self.rate,
                self.slippage,
                self.size,
                self.pricetick,
                self.capital,
                self.end
            )))
            results.append(result)

        pool.close()
        pool.join()

        # Sort results and output
        result_values = [result.get() for result in results]
        result_values.sort(reverse=True, key=lambda result: result[1])

        if output:
            for value in result_values:
                msg = f"参数：{value[0]}, 目标：{value[1]}"
                self.output(msg)

        return result_values

    def run_ga_optimization(self, optimization_setting: OptimizationSetting, population_size=100, ngen_size=30, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting_ga()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Define parameter generation function
        def generate_parameter():
            """"""
            return random.choice(settings)

        def mutate_individual(individual, indpb):
            """"""
            size = len(individual)
            paramlist = generate_parameter()
            for i in range(size):
                if random.random() < indpb:
                    individual[i] = paramlist[i]
            return individual,

        # Create ga object function
        global ga_target_name
        global ga_strategy_class
        global ga_setting
        global ga_vt_symbols
        global ga_start
        global ga_rate
        global ga_slippage
        global ga_size
        global ga_pricetick
        global ga_capital
        global ga_end

        ga_target_name = target_name
        ga_strategy_class = self.strategy_class
        ga_setting = settings[0]
        ga_vt_symbols = self.vt_symbols
        ga_start = self.start
        ga_rate = self.rate
        ga_slippage = self.slippage
        ga_size = self.size
        ga_pricetick = self.pricetick
        ga_capital = self.capital
        ga_end = self.end

        # Set up genetic algorithem
        toolbox = base.Toolbox()
        toolbox.register("individual", tools.initIterate, creator.Individual, generate_parameter)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mutate", mutate_individual, indpb=1)
        toolbox.register("evaluate", ga_optimize)
        toolbox.register("select", tools.selNSGA2)

        total_size = len(settings)
        pop_size = population_size                      # number of individuals in each generation
        lambda_ = pop_size                              # number of children to produce at each generation
        mu = int(pop_size * 0.8)                        # number of individuals to select for the next generation

        cxpb = 0.95         # probability that an offspring is produced by crossover
        mutpb = 1 - cxpb    # probability that an offspring is produced by mutation
        ngen = ngen_size    # number of generation

        pop = toolbox.population(pop_size)
        hof = tools.ParetoFront()               # end result of pareto front

        stats = tools.Statistics(lambda ind: ind.fitness.values)
        np.set_printoptions(suppress=True)
        stats.register("mean", np.mean, axis=0)
        stats.register("std", np.std, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)

        # Multiprocessing is not supported yet.
        # pool = multiprocessing.Pool(multiprocessing.cpu_count())
        # toolbox.register("map", pool.map)

        # Run ga optimization
        self.output(f"参数优化空间：{total_size}")
        self.output(f"每代族群总数：{pop_size}")
        self.output(f"优良筛选个数：{mu}")
        self.output(f"迭代次数：{ngen}")
        self.output(f"交叉概率：{cxpb:.0%}")
        self.output(f"突变概率：{mutpb:.0%}")

        start = time()

        algorithms.eaMuPlusLambda(
            pop,
            toolbox,
            mu,
            lambda_,
            cxpb,
            mutpb,
            ngen,
            stats,
            halloffame=hof
        )

        end = time()
        cost = int((end - start))

        self.output(f"遗传算法优化完成，耗时{cost}秒")

        # Return result list
        results = []

        for parameter_values in hof:
            setting = dict(parameter_values)
            target_value = ga_optimize(parameter_values)[0]
            results.append((setting, target_value, {}))

        return results

    def update_daily_close(self, price: float):
        """"""
        d = self.datetime.date()

        daily_result = self.daily_results.get(d, None)
        if daily_result:
            daily_result.close_price = price
        else:
            self.daily_results[d] = DailyResult(d, price)

    def new_tick(self, tick: TickData):
        """"""
        self.tick = tick
        self.datetime = tick.datetime

        self.cross_limit_order()
        self.strategy.on_tick(tick)
        self.update_daily_close(tick.last_price)

    # 估计两边盘口的成交量
    def calc_tick_volume(self, tick, lasttick, size):
        """计算两边盘口的成交量"""
        currentVolume = tick.volume - lasttick.volume
        currentTurnOver = tick.turnover - lasttick.turnover
        pOnAsk = lasttick.ask_price_1
        pOnBid = lasttick.bid_price_1

        if lasttick and currentVolume > 0: 
            avgPrice = currentTurnOver / currentVolume / size
            ratio = (avgPrice - pOnBid) / (pOnAsk - pOnBid)
            ratio = max(ratio, 0)
            ratio = min(ratio, 1)
            volOnAsk = ratio * currentVolume
            volOnBid = currentVolume - volOnAsk
        else:
            volOnAsk = 0
            volOnBid = 0

        return volOnBid, volOnAsk

    # 考虑限价单排队
    def cross_limit_order(self):
        """
        Cross limit order with last bar/tick data.
        """
        long_best_price = self.tick.ask_price_1
        short_best_price = self.tick.bid_price_1

        for order in list(self.active_limit_orders.values()):
            if order.vt_symbol != self.tick.vt_symbol:
                continue
            # Push order update with status "not traded" (pending).
            if order.status == Status.SUBMITTING:
                order.status = Status.NOTTRADED
                #self.strategy.on_order(order)
                self.strategy.update_order(order)

            # Check whether limit orders can be filled.
            # 检查价格(见价成交)
            long_cross = (
                order.direction == Direction.LONG
                and self.tick.ask_price_1 > 0
                and order.price > self.tick.bid_price_1
            )

            short_cross = (
                order.direction == Direction.SHORT
                and self.tick.bid_price_1 > 0
                and order.price < self.tick.ask_price_1
            )
            long_que = False
            short_que = False

            # 见价成交无法成交
            if not long_cross and not short_cross:
                # 检查限价单队列（认为排在你之前的人都不撤单）
                # 从未计算排队位置的新订单
                if self.limit_que[order.vt_orderid] == LQ:
                    if order.direction == Direction.LONG:
                        # 从五档里匹配对应价格的排队位置
                        if self.tick.bid_price_1 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.bid_volume_1
                        elif self.tick.bid_price_2 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.bid_volume_2
                        elif self.tick.bid_price_3 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.bid_volume_3
                        elif self.tick.bid_price_4 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.bid_volume_4
                        elif self.tick.bid_price_5 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.bid_volume_5
                    if order.direction == Direction.SHORT:
                        if self.tick.ask_price_1 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.ask_volume_1
                        elif self.tick.ask_price_2 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.ask_volume_2
                        elif self.tick.ask_price_3 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.ask_volume_3
                        elif self.tick.ask_price_4 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.ask_volume_4
                        elif self.tick.ask_price_5 == order.price:
                            self.limit_que[order.vt_orderid] = self.tick.ask_volume_5
                    # 记录当前tick，用于更新排队位置
                    self.limit_que_last_tick[order.vt_orderid] = self.tick
                # 已经在排队的老订单更新排队位置
                elif self.limit_que[order.vt_orderid] > 0:
                    # 只有订单在一档了才更新（认为进入一档后，你之前的人都不撤单）
                    if order.direction == Direction.LONG and self.tick.bid_price_1 == order.price:
                        # 订单首次到达一档或再次到达一档
                        if self.limit_que_last_tick[order.vt_orderid].bid_price_1 != order.price:
                            # 处理进入一档队列最差位置仍然优于之前的情况
                            self.limit_que[order.vt_orderid] = min(self.limit_que[order.vt_orderid], self.tick.bid_volume_1)
                        # 连续在一档排队
                        else:
                            # 一档买卖成交量
                            bid_v, ask_v = self.calc_tick_volume(self.tick, self.limit_que_last_tick[order.vt_orderid], self.size)
                            # 更新排队位置
                            self.limit_que[order.vt_orderid] -= bid_v
                    if order.direction == Direction.SHORT and self.tick.ask_price_1 == order.price:
                        if self.limit_que_last_tick[order.vt_orderid].ask_price_1 != order.price:
                            self.limit_que[order.vt_orderid] = min(self.limit_que[order.vt_orderid], self.tick.ask_volume_1)
                        else:
                            bid_v, ask_v = self.calc_tick_volume(self.tick, self.limit_que_last_tick[order.vt_orderid], self.size)
                            self.limit_que[order.vt_orderid] -= ask_v
                    # 记录并判断
                    self.limit_que_last_tick[order.vt_orderid] = self.tick
                    long_que = (order.direction == Direction.LONG and self.limit_que[order.vt_orderid] <= 0)
                    short_que = (order.direction == Direction.SHORT and self.limit_que[order.vt_orderid] <= 0)
                else:
                    long_que = (order.direction == Direction.LONG and self.limit_que[order.vt_orderid] <= 0)
                    short_que = (order.direction == Direction.SHORT and self.limit_que[order.vt_orderid] <= 0)
                
                # 排队被动成交也无法成交
                if not long_que and not short_que: 
                    continue
                else:
                    print("排队成交")
                    self.volume_trade_count += 1
            else:
                print("见价成交")
                self.price_trade_count += 1
        
            # Push order udpate with status "all traded" (filled).
            order.traded = order.volume
            order.status = Status.ALLTRADED
            #self.strategy.on_order(order)
            self.strategy.update_order(order)

            self.active_limit_orders.pop(order.vt_orderid)
            self.limit_que.pop(order.vt_orderid)
            self.limit_que_last_tick.pop(order.vt_orderid)

            # Push trade update
            self.trade_count += 1

            if long_cross or long_que:
                trade_price = min(order.price, long_best_price)
            elif short_cross or short_que:
                trade_price = max(order.price, short_best_price)

            trade = TradeData(
                symbol=order.symbol,
                exchange=order.exchange,
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                datetime=self.datetime,
                gateway_name=self.gateway_name,
            )

            self.strategy.update_trade(trade)
            self.strategy.on_trade(trade)

            self.trades[trade.vt_tradeid] = trade

    def send_order(
        self,
        strategy: StrategyTemplate,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        lock: bool
    ):
        """"""
        price = round_to(price, self.pricetick)
        symbol = vt_symbol.split(".")[0]
        vt_orderid = self.send_limit_order(symbol, direction, offset, price, volume)
        return [vt_orderid]

    def send_limit_order(
        self,
        symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ):
        """"""
        self.limit_order_count += 1

        order = OrderData(
            symbol=symbol,
            exchange=self.exchange,
            orderid=str(self.limit_order_count),
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            status=Status.SUBMITTING,
            gateway_name=self.gateway_name,
            datetime=self.datetime
        )

        self.active_limit_orders[order.vt_orderid] = order
        self.limit_orders[order.vt_orderid] = order
        self.limit_que[order.vt_orderid] = LQ
        self.limit_que_last_tick[order.vt_orderid] = LQ

        return order.vt_orderid

    def cancel_order(self, strategy: StrategyTemplate, vt_orderid: str):
        """"""
        if vt_orderid not in self.active_limit_orders:
            return
        order = self.active_limit_orders.pop(vt_orderid)
        self.limit_que.pop(vt_orderid)
        self.limit_que_last_tick.pop(vt_orderid)

        order.status = Status.CANCELLED
        #self.strategy.on_order(order)
        self.strategy.update_order(order)

    def write_log(self, msg: str, strategy: StrategyTemplate = None):
        """
        Write log message.
        """
        msg = f"{self.datetime}\t{msg}"
        self.logs.append(msg)

    def put_strategy_event(self, strategy: StrategyTemplate):
        """
        Put an event to update strategy status.
        """
        pass

    def output(self, msg):
        """
        Output message of backtesting engine.
        """
        print(f"{datetime.now()}\t{msg}")

    def get_all_trades(self):
        """
        Return all trade data of current backtesting result.
        """
        return list(self.trades.values())

    def get_all_orders(self):
        """
        Return all limit order data of current backtesting result.
        """
        return list(self.limit_orders.values())

    def get_all_daily_results(self):
        """
        Return all daily result data.
        """
        return list(self.daily_results.values())


class DailyResult:
    """"""

    def __init__(self, date: date, close_price: float):
        """"""
        self.date = date
        self.close_price = close_price
        self.pre_close = 0

        self.trades = []
        self.trade_count = 0

        self.start_pos = 0
        self.end_pos = 0

        self.turnover = 0
        self.commission = 0
        self.slippage = 0

        self.trading_pnl = 0
        self.holding_pnl = 0
        self.total_pnl = 0
        self.net_pnl = 0

    def add_trade(self, trade: TradeData):
        """"""
        self.trades.append(trade)

    def calculate_pnl(
        self,
        pre_close: float,
        start_pos: float,
        size: int,
        rate: float,
        slippage: float,
        inverse: bool
    ):
        """"""
        # If no pre_close provided on the first day,
        # use value 1 to avoid zero division error
        if pre_close:
            self.pre_close = pre_close
        else:
            self.pre_close = 1

        # Holding pnl is the pnl from holding position at day start
        self.start_pos = start_pos
        self.end_pos = start_pos

        if not inverse:     # For normal contract
            self.holding_pnl = self.start_pos * \
                (self.close_price - self.pre_close) * size
        else:               # For crypto currency inverse contract
            self.holding_pnl = self.start_pos * \
                (1 / self.pre_close - 1 / self.close_price) * size

        # Trading pnl is the pnl from new trade during the day
        self.trade_count = len(self.trades)

        for trade in self.trades:
            if trade.direction == Direction.LONG:
                pos_change = trade.volume
            else:
                pos_change = -trade.volume

            self.end_pos += pos_change

            # For normal contract
            if not inverse:
                turnover = trade.volume * size * trade.price
                self.trading_pnl += pos_change * \
                    (self.close_price - trade.price) * size
                self.slippage += trade.volume * size * slippage
            # For crypto currency inverse contract
            else:
                turnover = trade.volume * size / trade.price
                self.trading_pnl += pos_change * \
                    (1 / trade.price - 1 / self.close_price) * size
                self.slippage += trade.volume * size * slippage / (trade.price ** 2)

            self.turnover += turnover
            self.commission += turnover * rate

        # Net pnl takes account of commission and slippage cost
        self.total_pnl = self.trading_pnl + self.holding_pnl
        self.net_pnl = self.total_pnl - self.commission - self.slippage


def optimize(
    target_name: str,
    strategy_class: StrategyTemplate,
    setting: dict,
    vt_symbols,
    start: datetime,
    rate: float,
    slippage: float,
    size: float,
    pricetick: float,
    capital: int,
    end: datetime
):
    """
    Function for running in multiprocessing.pool
    """
    engine = BacktestingEngine()

    engine.set_parameters(
        vt_symbols=vt_symbols,
        start=start,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=capital,
        end=end
    )

    engine.add_strategy(strategy_class, setting)
    engine.load_data()
    engine.run_backtesting()
    result_df = engine.calculate_result()
    statistics = engine.calculate_statistics(output=False)

    target_value = statistics[target_name]
    return (str(setting), target_value, statistics, result_df)


@lru_cache(maxsize=1000000)
def _ga_optimize(parameter_values: tuple):
    """"""
    setting = dict(parameter_values)

    result = optimize(
        ga_target_name,
        ga_strategy_class,
        setting,
        ga_vt_symbols,
        ga_start,
        ga_rate,
        ga_slippage,
        ga_size,
        ga_pricetick,
        ga_capital,
        ga_end
    )
    return (result[1],)


def ga_optimize(parameter_values: list):
    """"""
    return _ga_optimize(tuple(parameter_values))

@lru_cache(maxsize=999)
def load_tick_data(
    symbol: str,
    exchange: Exchange,
    start: datetime,
    end: datetime,
    collection_name: str
):
    """"""
    return database_manager.load_tick_data(
        symbol, exchange, start, end, collection_name
    )


# GA related global value
ga_end = None
ga_target_name = None
ga_strategy_class = None
ga_setting = None
ga_vt_symbols = None
ga_start = None
ga_rate = None
ga_slippage = None
ga_size = None
ga_pricetick = None
ga_capital = None
