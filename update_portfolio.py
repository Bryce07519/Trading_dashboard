#!/usr/bin/env python3
"""
Portfolio Dashboard Updater
更新 Nautilus 多标的实盘 portfolio 整体表现到 dashboard.

数据安全:
  - API key 从 /root/Binance/config/ 读取, 不进 git
  - 输出仅含: 收益率% / PnL$ / 币种名 / 统计指标
  - 不输出: API key, 账户余额绝对值, 持仓明细, venue order id

输出:
  data/stats.json              — 整体关键指标
  data/portfolio_data.json     — 完整数据 (equity / daily / symbols / costs)
  data/equity_curve.png        — 累计 PnL 曲线
  data/daily_pnl.png           — 每日 PnL 柱状图
  data/symbol_contribution.png — 各币种 PnL 贡献
"""
import os, sys, json, datetime, time
from collections import defaultdict
from pathlib import Path

import ccxt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ── 配置 ──
API_CONFIG = '/root/Binance/config/bn_sub2_api_config.json'
START_DATE = datetime.datetime(2026, 4, 24, 0, 0, tzinfo=datetime.timezone.utc)
INITIAL_CAPITAL = 1000.0  # 4/24 启动时本金近似 (BN 按比例下单, 复利反映在 equity 曲线)

SYMBOLS = [
    'DOGE/USDC:USDC', 'FET/USDT:USDT', 'PENDLE/USDT:USDT', '1000BONK/USDC:USDC',
    'RENDER/USDT:USDT', '1000PEPE/USDC:USDC', 'CRV/USDC:USDC', 'ARB/USDC:USDC',
    'LDO/USDT:USDT', 'LTC/USDC:USDC', 'LINK/USDC:USDC', 'BCH/USDC:USDC',
]
DASHBOARD_DIR = Path('/home/bryce/coding/Trading_dashborad')
DATA_DIR = DASHBOARD_DIR / 'data'


def get_exchange():
    api = json.load(open(API_CONFIG))
    ex = ccxt.binance({
        'apiKey': api['api_key'],
        'secret': api['secret_key'],
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })
    ex.load_markets()
    return ex


def fetch_all_trades(ex):
    """分批拉取 + 去重"""
    since_start = int(START_DATE.timestamp() * 1000)
    now_ms = int(time.time() * 1000)
    all_trades = []
    for sym in SYMBOLS:
        since = since_start
        seen = set()
        while since < now_ms:
            try:
                trades = ex.fetch_my_trades(sym, since=since, limit=1000)
            except Exception as e:
                print(f"  {sym} fetch error: {e}", file=sys.stderr)
                break
            if not trades:
                break
            new = [t for t in trades if t['id'] not in seen]
            if not new:
                since += 7 * 24 * 3600 * 1000
                continue
            for t in new:
                seen.add(t['id'])
                all_trades.append(t)
            since = max(t['timestamp'] for t in trades) + 1
    all_trades.sort(key=lambda x: x['timestamp'])
    return all_trades


def pair_trades(all_trades, bnb_price):
    """配对开平仓 → roundtrips"""
    pos_state = defaultdict(lambda: {'qty': 0.0, 'avg_cost': 0.0, 'open_time': None})
    roundtrips = []
    fees = []  # 每笔 fill 的 fee
    for t in all_trades:
        sym = t['symbol'].split('/')[0]
        qty, px, side, ts, cost = t['amount'], t['price'], t['side'], t['timestamp'], t['cost']
        fee = t.get('fee') or {}
        fee_amt = float(fee.get('cost', 0))
        fee_usd = fee_amt * bnb_price if fee.get('currency') == 'BNB' else fee_amt
        fees.append({'symbol': sym, 'fee_usd': fee_usd, 'volume': cost, 'ts': ts})
        s = pos_state[sym]
        if s['qty'] == 0 or (side == 'buy' and s['qty'] > 0) or (side == 'sell' and s['qty'] < 0):
            new_qty = s['qty'] + (qty if side == 'buy' else -qty)
            new_cost = s['qty'] * s['avg_cost'] + (qty if side == 'buy' else -qty) * px
            if new_qty != 0:
                s['avg_cost'] = abs(new_cost / new_qty)
            s['qty'] = new_qty
            if not s.get('open_time'):
                s['open_time'] = ts
        else:
            close_qty = min(qty, abs(s['qty']))
            pnl = (px - s['avg_cost']) * close_qty if s['qty'] > 0 else (s['avg_cost'] - px) * close_qty
            roundtrips.append({
                'symbol': sym,
                'side': 'long' if s['qty'] > 0 else 'short',
                'open_time': s['open_time'], 'close_time': ts,
                'open_px': s['avg_cost'], 'close_px': px,
                'qty': close_qty, 'notional': s['avg_cost'] * close_qty,
                'pnl': pnl,
                'hold_min': (ts - s['open_time']) / 1000 / 60,
            })
            remaining = abs(s['qty']) - close_qty
            if remaining > 0:
                s['qty'] = remaining if s['qty'] > 0 else -remaining
            else:
                s['qty'] = 0
                s['avg_cost'] = 0
                s['open_time'] = None
                leftover = qty - close_qty
                if leftover > 0:
                    s['qty'] = -leftover if side == 'sell' else leftover
                    s['avg_cost'] = px
                    s['open_time'] = ts
    roundtrips.sort(key=lambda x: x['close_time'])
    return roundtrips, fees


def compute_metrics(roundtrips, fees):
    """统计指标"""
    if not roundtrips:
        return None

    # equity 曲线
    cum, peak, max_dd = 0.0, 0.0, 0.0
    equity_points = []  # (ts_ms, cum_pnl)
    for rt in roundtrips:
        cum += rt['pnl']
        equity_points.append((rt['close_time'], cum))
        if cum > peak:
            peak = cum
        if cum - peak < max_dd:
            max_dd = cum - peak

    total_pnl = cum
    wins = [r for r in roundtrips if r['pnl'] > 0]
    losses = [r for r in roundtrips if r['pnl'] <= 0]
    win_rate = len(wins) / len(roundtrips) * 100
    gross_win = sum(r['pnl'] for r in wins)
    gross_loss = abs(sum(r['pnl'] for r in losses)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')

    # 每日 PnL
    daily_pnl = defaultdict(float)
    for rt in roundtrips:
        date = datetime.datetime.fromtimestamp(rt['close_time']/1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')
        daily_pnl[date] += rt['pnl']

    # Sharpe (用每日 PnL)
    daily_values = list(daily_pnl.values())
    if len(daily_values) > 1:
        import statistics
        avg = statistics.mean(daily_values)
        std = statistics.stdev(daily_values)
        sharpe = (avg / std) * (365 ** 0.5) if std > 0 else 0
    else:
        sharpe = 0

    # 总成交额, fee
    total_volume = sum(f['volume'] for f in fees)
    total_fee_usd = sum(f['fee_usd'] for f in fees)
    avg_fee_bps = (total_fee_usd / total_volume * 10000) if total_volume > 0 else 0

    # 时间跨度
    days = (datetime.datetime.now(datetime.timezone.utc) - START_DATE).days
    if days < 1:
        days = 1
    annualized = total_pnl / INITIAL_CAPITAL * 100 * 365 / days

    # Calmar
    max_dd_pct = max_dd / INITIAL_CAPITAL * 100
    calmar = annualized / abs(max_dd_pct) if max_dd_pct < 0 else 0

    # 每币种聚合
    per_sym = defaultdict(lambda: {'trades': 0, 'pnl': 0, 'volume': 0, 'fee': 0})
    for rt in roundtrips:
        per_sym[rt['symbol']]['trades'] += 1
        per_sym[rt['symbol']]['pnl'] += rt['pnl']
    for f in fees:
        per_sym[f['symbol']]['fee'] += f['fee_usd']
        per_sym[f['symbol']]['volume'] += f['volume']  # 双边 volume (open + close fills)

    return {
        'total_pnl': total_pnl,
        'total_return_pct': total_pnl / INITIAL_CAPITAL * 100,
        'annualized_pct': annualized,
        'max_drawdown_dollar': max_dd,
        'max_drawdown_pct': max_dd_pct,
        'calmar': calmar,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'profit_factor': pf if pf != float('inf') else 999.0,
        'total_trades': len(roundtrips),
        'wins': len(wins),
        'losses': len(losses),
        'avg_win': gross_win / len(wins) if wins else 0,
        'avg_loss': -gross_loss / len(losses) if losses else 0,
        'max_win': max((r['pnl'] for r in roundtrips), default=0),
        'max_loss': min((r['pnl'] for r in roundtrips), default=0),
        'avg_hold_min': sum(r['hold_min'] for r in roundtrips) / len(roundtrips),
        'avg_fee_bps': avg_fee_bps,
        'total_fee_usd': total_fee_usd,
        'total_volume': total_volume,
        'running_days': days,
        'equity_curve': equity_points,
        'daily_pnl': dict(daily_pnl),
        'per_symbol': dict(per_sym),
    }


def plot_equity(equity_points, output):
    if not equity_points:
        return
    times = [datetime.datetime.fromtimestamp(t/1000, tz=datetime.timezone.utc) for t, _ in equity_points]
    pnls = [INITIAL_CAPITAL + p for _, p in equity_points]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(times, pnls, color='#2563eb', linewidth=1.8)
    ax.fill_between(times, INITIAL_CAPITAL, pnls, alpha=0.15, color='#2563eb')
    ax.axhline(INITIAL_CAPITAL, color='gray', linestyle='--', alpha=0.5, label='Initial Capital')
    ax.set_xlabel('Date')
    ax.set_ylabel('Equity ($)')
    ax.set_title('Portfolio Equity Curve')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.grid(alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(output, dpi=100)
    plt.close()


def plot_daily(daily_pnl, output):
    if not daily_pnl:
        return
    dates = sorted(daily_pnl.keys())
    values = [daily_pnl[d] for d in dates]
    colors = ['#16a34a' if v > 0 else '#dc2626' for v in values]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.bar(range(len(dates)), values, color=colors, alpha=0.85)
    ax.axhline(0, color='black', linewidth=0.5)
    ax.set_xticks(range(0, len(dates), max(1, len(dates)//15)))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), max(1, len(dates)//15))], rotation=45)
    ax.set_ylabel('Daily PnL ($)')
    ax.set_title('Daily PnL')
    ax.grid(alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(output, dpi=100)
    plt.close()


def plot_symbol_contrib(per_symbol, output):
    if not per_symbol:
        return
    syms = sorted(per_symbol.keys(), key=lambda s: -per_symbol[s]['pnl'])
    pnls = [per_symbol[s]['pnl'] for s in syms]
    colors = ['#16a34a' if p > 0 else '#dc2626' for p in pnls]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(syms, pnls, color=colors, alpha=0.85)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_xlabel('PnL ($)')
    ax.set_title('PnL Contribution by Symbol')
    ax.grid(alpha=0.3, axis='x')
    plt.tight_layout()
    plt.savefig(output, dpi=100)
    plt.close()


def write_stats(m, output):
    """简化指标 JSON (兼容现有 index.html 风格)"""
    stats = {
        '总收益率 (%)': f"{m['total_return_pct']:+.2f}",
        '年化收益率 (%)': f"{m['annualized_pct']:+.1f}",
        '夏普比率': f"{m['sharpe']:.2f}",
        '最大回撤 (%)': f"{m['max_drawdown_pct']:.2f}",
        '卡玛比率': f"{m['calmar']:.2f}",
        '胜率 (%)': f"{m['win_rate']:.1f}",
        '盈亏比': f"{m['profit_factor']:.2f}",
        '总交易笔数': m['total_trades'],
        '运行天数': m['running_days'],
        '平均手续费 (bps)': f"{m['avg_fee_bps']:.2f}",
        '最后更新时间 (UTC)': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def write_portfolio_data(m, output):
    """完整数据"""
    equity_simple = [
        {
            'time': datetime.datetime.fromtimestamp(t/1000, tz=datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
            'pnl': round(p, 4),
            'equity': round(INITIAL_CAPITAL + p, 4),
        }
        for t, p in m['equity_curve']
    ]
    per_sym_list = []
    for sym, d in sorted(m['per_symbol'].items(), key=lambda x: -x[1]['pnl']):
        fee_bps = (d['fee'] / d['volume'] * 10000) if d['volume'] > 0 else 0
        per_sym_list.append({
            'symbol': sym,
            'trades': d['trades'],
            'pnl': round(d['pnl'], 2),
            'fee_bps': round(fee_bps, 2),
        })
    data = {
        'last_updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        'start_date': START_DATE.strftime('%Y-%m-%d'),
        'initial_capital': INITIAL_CAPITAL,
        'strategy_description': 'Multi-symbol momentum strategy (12 coins, rolling 15min return, long/inverse)',
        'metrics': {
            'total_pnl': round(m['total_pnl'], 2),
            'total_return_pct': round(m['total_return_pct'], 2),
            'annualized_pct': round(m['annualized_pct'], 1),
            'max_drawdown_dollar': round(m['max_drawdown_dollar'], 2),
            'max_drawdown_pct': round(m['max_drawdown_pct'], 2),
            'calmar': round(m['calmar'], 2),
            'sharpe': round(m['sharpe'], 2),
            'win_rate': round(m['win_rate'], 1),
            'profit_factor': round(m['profit_factor'], 2),
            'total_trades': m['total_trades'],
            'wins': m['wins'],
            'losses': m['losses'],
            'avg_win': round(m['avg_win'], 2),
            'avg_loss': round(m['avg_loss'], 2),
            'max_win': round(m['max_win'], 2),
            'max_loss': round(m['max_loss'], 2),
            'avg_hold_min': round(m['avg_hold_min'], 1),
            'avg_fee_bps': round(m['avg_fee_bps'], 2),
            'running_days': m['running_days'],
        },
        'symbol_pool': [s.split('/')[0] for s in SYMBOLS],  # 完整策略池 12 币种
        'symbols_with_trades': [s['symbol'] for s in per_sym_list],  # 实际成交过的
        'per_symbol': per_sym_list,
        'daily_pnl': [{'date': d, 'pnl': round(v, 2)} for d, v in sorted(m['daily_pnl'].items())],
        'equity_curve': equity_simple,
        'images': {
            'equity': 'data/equity_curve.png',
            'daily_pnl': 'data/daily_pnl.png',
            'symbol_contribution': 'data/symbol_contribution.png',
        },
    }
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    print(f"Updating portfolio dashboard...")
    print(f"  Start date: {START_DATE.strftime('%Y-%m-%d')}")
    print(f"  Initial capital: ${INITIAL_CAPITAL}")
    print(f"  Symbols: {len(SYMBOLS)}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ex = get_exchange()
    try:
        bnb_price = float(ex.fetch_ticker('BNB/USDT')['last'])
    except Exception:
        bnb_price = 700.0
    print(f"  BNB price: ${bnb_price:.2f}")

    print("Fetching trades...")
    trades = fetch_all_trades(ex)
    print(f"  Total fills: {len(trades)}")

    roundtrips, fees = pair_trades(trades, bnb_price)
    print(f"  Round-trips: {len(roundtrips)}")

    m = compute_metrics(roundtrips, fees)
    if m is None:
        print("No trades found, exit.")
        return

    print(f"\nResults:")
    print(f"  Total PnL: ${m['total_pnl']:+.2f} ({m['total_return_pct']:+.2f}%)")
    print(f"  Annualized: {m['annualized_pct']:+.1f}%")
    print(f"  Max DD: ${m['max_drawdown_dollar']:+.2f} ({m['max_drawdown_pct']:+.2f}%)")
    print(f"  Sharpe: {m['sharpe']:.2f}, Calmar: {m['calmar']:.2f}")
    print(f"  Win Rate: {m['win_rate']:.1f}% ({m['wins']}W/{m['losses']}L)")
    print(f"  PF: {m['profit_factor']:.2f}")

    # 输出
    write_stats(m, DATA_DIR / 'stats.json')
    write_portfolio_data(m, DATA_DIR / 'portfolio_data.json')
    plot_equity(m['equity_curve'], DATA_DIR / 'equity_curve.png')
    plot_daily(m['daily_pnl'], DATA_DIR / 'daily_pnl.png')
    plot_symbol_contrib(m['per_symbol'], DATA_DIR / 'symbol_contribution.png')

    print(f"\nFiles written to {DATA_DIR}/")
    print("  - stats.json")
    print("  - portfolio_data.json")
    print("  - equity_curve.png")
    print("  - daily_pnl.png")
    print("  - symbol_contribution.png")


if __name__ == '__main__':
    main()
