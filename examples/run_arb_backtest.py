from vnpy.app.cta_strategy.arb_backtesting import BacktestingEngine, OptimizationSetting
from vnpy.app.portfolio_strategy.strategies.arb_wtch3_strategy import ArbWtCh3Strategy
from datetime import datetime

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol=["cu6666.SHFE","cu7777.SHFE"],
    interval="1m",
    start=datetime(2020, 8, 30),
    end=datetime(2020, 9, 12),
    rate=0.25/10000,
    slippage=0,
    size=5,
    pricetick=10,
    capital=500000,
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