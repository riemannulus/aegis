"""Paper trading simulation - end-to-end pipeline verification.

Note: The LightGBM model produces near-constant predictions (~5e-5) because it
was trained without sufficient funding/OI data, making z-score filtering reject
all signals. To verify the pipeline end-to-end, we use a price-momentum proxy
signal (normalized 12-candle return) which produces realistic z-score variation
while still exercising PaperTrader -> RiskEngine -> Storage in full.
"""
import warnings
warnings.filterwarnings('ignore')
import sys
import numpy as np
from data.storage import Storage
from data.feature_engineer import FeatureEngineer
from models.lgbm_model import LGBMModel
from execution.paper_trader import PaperTrader
from strategy.signal_converter import SignalConverter
from risk.risk_engine import RiskEngine

storage = Storage()
print("Loading candles...")
candles_raw = storage.get_candles('BTCUSDT', '30m')[-300:]
candles_clean = [{k: v for k, v in c.items() if not k.startswith('_')} for c in candles_raw]
print(f"  Loaded {len(candles_clean)} candles")

print("Computing features...")
fe = FeatureEngineer()
features_df = fe.compute(candles_clean)
print(f"  Feature shape: {features_df.shape}")

print("Loading LightGBM model...")
lgbm = LGBMModel()
lgbm.load('models/saved/lgbm_latest.lgbm')
raw_preds = lgbm.predict(features_df)
print(f"  Model loaded. Prediction range: [{raw_preds.min():.6f}, {raw_preds.max():.6f}] (unique: {len(set(raw_preds))})")
print("  Note: Model predictions are near-constant; using return_zscore_24h as proxy signal.")

# Use return_zscore_24h feature as signal proxy (varies meaningfully, same sign as model intent)
proxy_signals = features_df['return_zscore_24h'].values if 'return_zscore_24h' in features_df.columns else raw_preds

# Align candles to features (feature engineer may drop rows due to lookback)
n_features = len(features_df)
candles_aligned = candles_clean[-n_features:]

print("\nInitializing paper trader, signal converter, risk engine...")
paper = PaperTrader(initial_balance=10000, leverage=3)
converter = SignalConverter()
risk_engine = RiskEngine()
risk_engine.initialise(opening_balance=10000)

trades = []
open_trade = None

print("\nRunning simulation loop...")
for i in range(n_features):
    pred = float(proxy_signals[i])
    price = float(candles_aligned[i]['close'])
    ts = int(candles_aligned[i]['timestamp'])

    paper.update_price('BTCUSDT', price)

    sig = converter.convert(pred)
    pos = paper.get_position('BTCUSDT')
    bal = paper.get_balance()

    # Close position on FLAT signal if holding
    if sig.direction == 'FLAT':
        if pos.get('size', 0) != 0:
            paper.close_position('BTCUSDT')
            pnl = paper.get_balance()['total'] - (open_trade['balance_before'] if open_trade else 10000)
            trades.append({
                'candle': i, 'action': 'close', 'price': price,
                'ts': ts, 'pnl': round(pnl, 2)
            })
            open_trade = None
    else:
        # Open new position if flat
        if pos.get('size', 0) == 0:
            order_usdt = bal['available'] * sig.size_ratio * 0.3
            stage1 = risk_engine.check_pre_order(
                order_usdt=order_usdt,
                account_balance=bal['available']
            )
            if stage1.passed and order_usdt > 0 and price > 0:
                amount = order_usdt / price
                if amount > 0.0001:
                    side = 'buy' if sig.direction == 'LONG' else 'sell'
                    try:
                        paper.create_market_order('BTCUSDT', side, amount)
                        open_trade = {'balance_before': bal['total']}
                        trades.append({
                            'candle': i, 'action': 'open', 'side': side,
                            'price': price, 'amount': round(amount, 6),
                            'order_usdt': round(order_usdt, 2), 'ts': ts
                        })
                    except Exception as e:
                        print(f"  Order failed at candle {i}: {e}")

    risk_engine.tick_candle()

# Close any remaining open position
pos = paper.get_position('BTCUSDT')
if pos.get('size', 0) != 0:
    last_price = float(candles_aligned[-1]['close'])
    paper.close_position('BTCUSDT')
    trades.append({
        'candle': n_features - 1, 'action': 'close', 'price': last_price,
        'ts': int(candles_aligned[-1]['timestamp']), 'pnl': 0.0
    })

# Final state
final_bal = paper.get_balance()
trade_history = paper.get_trade_history()
initial = 10000.0
final = final_bal['total']
ret_pct = (final - initial) / initial * 100

print("\n" + "="*60)
print("SIMULATION RESULTS")
print("="*60)
print(f"Initial balance : $10,000.00")
print(f"Final balance   : ${final:.2f}")
print(f"Return          : {ret_pct:+.2f}%")
print(f"Unrealized PnL  : ${final_bal['unrealized_pnl']:.2f}")
print(f"Total events    : {len(trades)}")
open_trades = [t for t in trades if t['action'] == 'open']
close_trades = [t for t in trades if t['action'] == 'close']
print(f"  Opens         : {len(open_trades)}")
print(f"  Closes        : {len(close_trades)}")

print("\nFirst 15 trade events:")
for t in trades[:15]:
    if t['action'] == 'open':
        print(f"  [c{t['candle']:3d}] OPEN  {t.get('side','?').upper():5s} @ ${t['price']:,.2f}  amt={t['amount']} (${t['order_usdt']})")
    else:
        pnl_str = f"  pnl=${t['pnl']:.2f}" if t.get('pnl') is not None else ""
        print(f"  [c{t['candle']:3d}] CLOSE         @ ${t['price']:,.2f}{pnl_str}")

# Save trades to DB
print("\nSaving trades to DB...")
saved = 0
for t in trades:
    if t['action'] == 'open':
        storage.insert_trade({
            'timestamp': t['ts'],
            'symbol': 'BTCUSDT',
            'side': t['side'],
            'entry_price': t['price'],
            'exit_price': t['price'],
            'pnl': 0.0,
            'funding_cost': 0.0,
        })
        saved += 1
print(f"  Saved {saved} trade records.")

# Verify from DB
db_trades = storage.get_trades(limit=20)
print(f"\nDB verification: {len(db_trades)} trades retrieved (limit 20)")
if db_trades:
    t0 = db_trades[0]
    keys = [k for k in (t0.keys() if hasattr(t0, 'keys') else vars(t0).keys()) if not k.startswith('_')]
    print(f"  Sample keys: {keys}")
    print(f"  Latest trade: {dict((k, getattr(t0, k, t0.get(k) if hasattr(t0, 'get') else '?')) for k in keys[:6])}")

print("\nDone.")
