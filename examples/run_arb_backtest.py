from vnpy.app.cta_strategy.arb_backtesting import BacktestingEngine, OptimizationSetting
from vnpy.app.portfolio_strategy.strategies.arb_wtch3_strategy import ArbWtCh3Strategy
from datetime import datetime

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbols=["cu6666.SHFE","cu7777.SHFE"],
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
engine.show_chart()

# setting = OptimizationSetting()
# setting.set_target("sharpe_ratio")
# setting.add_parameter("atr_stop", 3, 6, 0.5) # 4
# setting.add_parameter("trailing_short", 0.3, 0.6, 0.05) # 0.4
# setting.add_parameter("trailing_long", 0.3, 0.6, 0.05) # 0.4
# #setting.add_parameter("atr_window", 20, 60, 4) # 44
# #setting.add_parameter("atr_ma_len", 10, 30, 2) # 22

# engine.run_optimization(setting)