from vnpy.app.cta_strategy.arb_backtesting import BacktestingEngine, OptimizationSetting
from vnpy.app.portfolio_strategy.strategies.arb_wtch3_strategy import ArbWtCh3Strategy
from datetime import datetime

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbols=["ni6666.SHFE","ni7777.SHFE"],
    start=datetime(2020, 8, 30),
    end=datetime(2020, 9, 12),
    rate=0.25/10000,
    slippage=0,
    size=5,
    pricetick=10,
    capital=500000
)



engine.add_strategy(ArbWtCh3Strategy, {
    'price_add': 1,
    'ema_window': 180,
    'ema_th': 1.5,
    'arb_size': 1,
    'time_out':120,
    'dom_symbol':1,
    'pricetick':10
    })
engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
# engine.show_chart()

# setting = OptimizationSetting()
# setting.set_target("sharpe_ratio")
# setting.add_parameter("ema_window", 150, 210, 30) # 4
# #setting.add_parameter("ema_th", 1.5, 2.5, 0.5) # 0.4
# #setting.add_parameter("time_out", 90, 150, 30) # 0.4

# engine.run_optimization(setting)