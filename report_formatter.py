#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StockVue Report Formatter - Rich Markdown for Gumroad
Emoji-enhanced, well-structured daily reports
"""

from datetime import datetime


def format_win_rate(pct: float, cfg: dict, horizon: str = "1d", confluence: int = 0) -> str:
    return str(get_win_rate(pct, cfg, horizon, confluence))


def get_win_rate(pct: float, cfg: dict, horizon: str = "1d", confluence: int = 0) -> int:
    if pct >= 5: tier = cfg["tier1"]
    elif pct >= 3: tier = cfg["tier2"]
    elif pct >= 2: tier = cfg["tier3"]
    elif pct >= 1.5: tier = cfg["tier4"]
    else: tier = cfg["default"]
    if isinstance(tier, dict):
        base = int(tier.get(horizon, tier.get("1d", 50)))
    else:
        base = int(tier)
    # Confluence modifier: ±5% range based on confluence score
    if confluence > 0:
        modifier = round((confluence - 50) * 0.1)
        base = max(30, min(95, base + modifier))
    return base


def compute_basic_confluence(s):
    """Compute basic confluence for stocks without ICT analysis (A-shares)."""
    score = 0
    pct = abs(s.get('change_pct', 0))
    if pct >= 7: score += 30
    elif pct >= 5: score += 25
    elif pct >= 3: score += 15
    elif pct >= 2: score += 10

    turnover = s.get('turnover_rate', 0)
    if turnover >= 20: score += 30
    elif turnover >= 10: score += 20
    elif turnover >= 5: score += 15
    elif turnover >= 3: score += 10

    # Momentum: high change + high turnover = strong signal
    if pct >= 3 and turnover >= 10: score += 15
    if pct >= 5 and turnover >= 15: score += 10

    return min(score, 100)


def sentiment_emoji(market: str, sentiment: str) -> str:
    map_ = {
        "hk_bullish": "🟢", "hk_bearish": "🔴", "hk_neutral": "🟡",
        "us_bullish": "🟢", "us_bearish": "🔴", "us_neutral": "🟡",
        "a_bullish": "🟢", "a_bearish": "🔴", "a_neutral": "🟡",
    }
    return map_.get(f"{market}_{sentiment.lower()}", "🟡")


def format_price(price, currency="USD"):
    if currency == "USD":
        return f"${price:.2f}"
    elif currency == "CNY":
        return f"¥{price:.2f}"
    elif currency == "HKD":
        return f"HK${price:.2f}"
    return f"{price}"


def format_trade_signal(signal: dict) -> str:
    if not signal:
        return "—"
    direction = signal.get('direction', 'N/A').upper()
    entry = signal.get('entry_price', 0)
    sl = signal.get('stop_loss', 0)
    tp1 = signal.get('take_profit_1', 0)
    tp2 = signal.get('take_profit_2', 0)
    rr1 = signal.get('risk_reward_1', 0)
    rr2 = signal.get('risk_reward_2', 0)
    conf = signal.get('confluence_score', 0)
    zone = signal.get('zone', 'NEUTRAL')
    triggers = signal.get('triggers', [])

    emoji = "🟢" if direction == "LONG" else "🔴"
    zone_icon = "🔵" if zone == "DISCOUNT" else ("🔴" if zone == "PREMIUM" else "⚪")

    lines = []
    lines.append(f"{emoji} **{direction}** @ {entry:.2f}")
    lines.append(f"  SL: {sl:.2f} | TP1: {tp1:.2f} (1:{rr1}) | TP2: {tp2:.2f} (1:{rr2})")
    lines.append(f"  {zone_icon} {zone} | Confluence: {conf}")

    if triggers:
        triggers_str = ", ".join(triggers[:3])
        lines.append(f"  ✓ {triggers_str}")

    return "\n".join(lines)


def format_ict_signal_badge(signal: dict) -> str:
    if not signal:
        return "—"
    direction = signal.get('direction', '').upper()
    conf = signal.get('confluence_score', 0)
    zone = signal.get('zone', 'NEUTRAL')

    emoji = "🟢" if direction == "LONG" else ("🔴" if direction == "SHORT" else "⚪")
    zone_icon = "🔵" if zone == "DISCOUNT" else ("🔴" if zone == "PREMIUM" else "⚪")

    return f"{emoji} {direction}\n{zone_icon} {zone}\n⚙️ {conf}"


def generate_rich_report(a_stocks, hk_stocks, us_stocks, sentiment, cfg: dict, win_rate_threshold: int = 75) -> str:
    from datetime import timedelta
    hk_dt = datetime.now() + timedelta(hours=8)
    date_str = hk_dt.strftime("%Y-%m-%d")
    time_str = hk_dt.strftime("%H:%M")
    wr_cfg = cfg["win_rates"]
    wr_threshold = cfg.get("display_win_rate_min", win_rate_threshold)

    def passes_threshold(stock):
        wr_1d = get_win_rate(stock['change_pct'], wr_cfg, "1d")
        return wr_1d >= wr_threshold

    hk_emoji = sentiment_emoji("hk", sentiment.get("hk", "neutral"))
    us_emoji = sentiment_emoji("us", sentiment.get("us", "neutral"))
    a_emoji = sentiment_emoji("a", sentiment.get("a", "neutral"))

    report = ""
    report += "# 📈 StockVue — Daily Market Report\n\n"
    report += f"**📅 {date_str} | ⏰ {time_str} HK Time**\n\n"
    report += "---\n\n"

    # Market Sentiment Overview
    report += "## 🌡️ Market Overview\n\n"
    report += f"| Market | Sentiment | Condition |\n"
    report += "|--------|-----------|----------|\n"
    report += f"| 🇭🇰 Hong Kong | {sentiment.get('hk', 'NEUTRAL')} {hk_emoji} | HSI Trend |\n"
    report += f"| 🇺🇸 US Markets | {sentiment.get('us', 'NEUTRAL')} {us_emoji} | NASDAQ Trend |\n"
    report += f"| 🇨🇳 A-Share (China) | {sentiment.get('a', 'NEUTRAL')} {a_emoji} | SH/SZ Trend |\n"
    report += "\n---\n\n"

    # Hong Kong Section
    hk_filtered = [s for s in hk_stocks if passes_threshold(s)]
    report += "## 🇭🇰 Hong Kong Market\n\n"
    if hk_filtered:
        report += "| | Ticker | Name | Price | Change | Zone | Confluence | 1D Win | 5D Win | MSS | BOS | FVG | Signal |\n"
        report += "|:--- |:--- |:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        for i, s in enumerate(hk_filtered, 1):
            wr_1d = format_win_rate(s['change_pct'], wr_cfg, "1d")
            wr_5d = format_win_rate(s['change_pct'], wr_cfg, "5d")
            arrow = "🟢" if s['change_pct'] >= 3 else ("🟡" if s['change_pct'] >= 1.5 else "🔴")
            fib = s.get('fib', {})
            zone = fib.get('zone', 'N/A') if fib else 'N/A'
            zone_emoji = "🔵" if zone == 'DISCOUNT' else ("🔴" if zone == 'PREMIUM' else "⚪")
            confluence = s.get('confluence', 0)
            confluence_bar = "🟢" if confluence >= 60 else ("🟡" if confluence >= 40 else "🔴")
            mss = s.get('mss_active', False)
            mss_dir = s.get('mss_direction', '')
            mss_icon = "✅" if mss else "—"
            mss_str = f"{mss_icon} {mss_dir.upper()}" if mss else "—"
            bos = s.get('bos_count', 0)
            fvg = s.get('fvg_count', 0)
            sig = "✅ BUY" if (s.get('mss_active') and s.get('mss_direction') == 'bullish') or confluence >= 60 else "⚠️ WATCH"
            report += f"| **{i}** | `{s['ticker']}` | **{s['name']}** | {format_price(s['price'], 'HKD')} | {arrow} +{s['change_pct']}% | {zone_emoji} {zone} | {confluence_bar} {confluence} | **{wr_1d}%** | **{wr_5d}%** | {mss_str} | {bos} | {fvg} | {sig} |\n"
    else:
        report += "*No Hong Kong stocks met our screening criteria today.*\n"
    report += "\n---\n\n"

    # US Section
    us_filtered = [s for s in us_stocks if passes_threshold(s)]
    report += "## 🇺🇸 US Market\n\n"
    if us_filtered:
        report += "| | Ticker | Name | Price | Change | Zone | Confluence | 1D Win | 5D Win | MSS | BOS | FVG | Signal |\n"
        report += "|:--- |:--- |:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        for i, s in enumerate(us_filtered, 1):
            wr_1d = format_win_rate(s['change_pct'], wr_cfg, "1d")
            wr_5d = format_win_rate(s['change_pct'], wr_cfg, "5d")
            arrow = "🟢" if s['change_pct'] >= 3 else ("🟡" if s['change_pct'] >= 1.5 else "🔴")
            fib = s.get('fib', {})
            zone = fib.get('zone', 'N/A') if fib else 'N/A'
            zone_emoji = "🔵" if zone == 'DISCOUNT' else ("🔴" if zone == 'PREMIUM' else "⚪")
            confluence = s.get('confluence', 0)
            confluence_bar = "🟢" if confluence >= 60 else ("🟡" if confluence >= 40 else "🔴")
            mss = s.get('mss_active', False)
            mss_dir = s.get('mss_direction', '')
            mss_str = f"✅ {mss_dir.upper()}" if mss else "—"
            bos = s.get('bos_count', 0)
            fvg = s.get('fvg_count', 0)
            sig = "✅ BUY" if (s.get('mss_active') and s.get('mss_direction') == 'bullish') or confluence >= 60 else "⚠️ WATCH"
            report += f"| **{i}** | `{s['ticker']}` | **{s['name']}** | {format_price(s['price'], 'USD')} | {arrow} +{s['change_pct']}% | {zone_emoji} {zone} | {confluence_bar} {confluence} | **{wr_1d}%** | **{wr_5d}%** | {mss_str} | {bos} | {fvg} | {sig} |\n"
    else:
        report += "*No US stocks met our screening criteria today.*\n"
    report += "\n---\n\n"

    # A-Share Section
    a_filtered = [s for s in a_stocks if passes_threshold(s)]
    if a_filtered:
        report += "| | Code | Name | Price | Change | Turnover | Zone | Confluence | 1D Win | 5D Win | MSS | BOS | FVG | Signal |\n"
        report += "|:--- |:--- |:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        for i, s in enumerate(a_filtered, 1):
            wr_1d = format_win_rate(s['change_pct'], wr_cfg, "1d")
            wr_5d = format_win_rate(s['change_pct'], wr_cfg, "5d")
            arrow = "🟢" if s['change_pct'] >= 3 else ("🟡" if s['change_pct'] >= 1.5 else "🔴")
            fib = s.get('fib', {})
            zone = fib.get('zone', 'N/A') if fib else 'N/A'
            zone_emoji = "🔵" if zone == 'DISCOUNT' else ("🔴" if zone == 'PREMIUM' else "⚪")
            confluence = s.get('confluence', 0)
            confluence_bar = "🟢" if confluence >= 60 else ("🟡" if confluence >= 40 else "🔴")
            mss = s.get('mss_active', False)
            mss_dir = s.get('mss_direction', '')
            mss_str = f"✅ {mss_dir.upper()}" if mss else "—"
            bos = s.get('bos_count', 0)
            fvg = s.get('fvg_count', 0)
            sig = "✅ BUY" if (s.get('mss_active') and s.get('mss_direction') == 'bullish') or confluence >= 60 else "⚠️ WATCH"
            report += f"| **{i}** | `{s['code']}` | **{s['name']}** | {format_price(s['price'], 'CNY')} | {arrow} +{s['change_pct']}% | {s.get('turnover_rate', 0):.1f}% | {zone_emoji} {zone} | {confluence_bar} {confluence} | **{wr_1d}%** | **{wr_5d}%** | {mss_str} | {bos} | {fvg} | {sig} |\n"
        report += "\n---\n\n"

    # How to Read This Report
    report += "## 📖 How to Read This Report\n\n"
    report += "| Symbol | Meaning |\n"
    report += "|--------|----------|\n"
    report += "| ✅ BUY | Our algorithm suggests a buy signal based on momentum screening |\n"
    report += "| 🟢 Green | Strong mover ≥ 3% today |\n"
    report += "| 🟡 Yellow | Moderate mover 1.5% – 3% |\n"
    report += "| 🔵 Discount | Price near Fibonacci 0.786 (buy zone - ICT Premium/Discount concept) |\n"
    report += "| 🔴 Premium | Price above Fibonacci 0.618 (sell zone) |\n"
    report += "| ⚪ Neutral | Price between 0.618-0.786 |\n"
    report += "| 🟢 High Confluence | Score ≥60: Multiple confirmations (strong signal) |\n"
    report += "| 🟡 Medium Confluence | Score 40-59: Moderate confirmations |\n"
    report += "| 🔴 Low Confluence | Score <40: Weak signal, less reliable |\n"
    report += "| **1D Win %** | Historical probability of price UP next day (backtested 180 days) |\n"
    report += "| **5D Win %** | Historical probability of price UP after 5 days (backtested 180 days) |\n"
    report += "| **MSS** | Market Structure Shift — ✅ BULLISH/BEARISH means trend change confirmed |\n"
    report += "| **BOS** | Break of Structure count — higher = more trend confirmations |\n"
    report += "| **FVG** | Fair Value Gap count — more gaps = more institutional activity |\n"
    report += "| **✅ BUY** | Strong long signal: MSS confirmed + high confluence + bullish zone |\n"
    report += "| **⚠️ WATCH** | Potential signal but needs more confirmation |\n"
    report += "\n---\n\n"

    # ICT/SMC Concepts Section
    report += "## 🎯 ICT/SMC Trading Concepts\n\n"
    report += "| Concept | Description |\n"
    report += "|---------|-------------|\n"
    report += "| **BOS** | Break of Structure - Price breaks above/below previous swing high/low |\n"
    report += "| **CHoCH** | Change of Character - Trend shift signal (bullish vs bearish) |\n"
    report += "| **MSS** | Market Structure Shift - Confirms trend change after CHoCH |\n"
    report += "| **FVG** | Fair Value Gap - Imbalance zone (gap between candles) |\n"
    report += "| **OB** | Order Block - Last candle before major move (institutional footprint) |\n"
    report += "| **BB** | Breaker Block - Broken OB that now acts as resistance/support |\n"
    report += "| **SSS** | Short Squeeze Squeeze - Liquidity sweep taking out lows |\n"
    report += "| **DISCOUNT** | Price below 0.786 Fib - Buy zone (high probability long) |\n"
    report += "| **PREMIUM** | Price above 0.618 Fib - Sell zone (high probability short) |\n"
    report += "| **Confluence** | Multiple confirmations combined (BOS + OB + Zone + MSS) |\n"
    report += "\n---\n\n"

    # Trade Recommendations
    all_filtered = [(s, 'hk') for s in hk_filtered] + [(s, 'us') for s in us_filtered] + [(s, 'a') for s in a_filtered]
    if all_filtered:
        report += "## 🎯 Top Trade Opportunities (ICT/SMC Framework)\n\n"
        report += "| # | Market | Ticker | Entry | Stop Loss | TP1 (2:1) | TP2 (3:1) | Zone | Conf |\n"
        report += "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        for idx, (s, market) in enumerate(all_filtered[:5], 1):
            currency = 'HKD' if market == 'hk' else ('USD' if market == 'us' else 'CNY')
            ticker = s.get('ticker') or s.get('code', 'N/A')
            fib = s.get('fib', {})
            zone = fib.get('zone', 'NEUTRAL')
            zone_icon = "🔵" if zone == 'DISCOUNT' else ("🔴" if zone == 'PREMIUM' else "⚪")
            confluence = s.get('confluence', 0)
            conf_bar = "🟢" if confluence >= 60 else ("🟡" if confluence >= 40 else "🔴")

            entry = s.get('price', 0)
            risk = entry * 0.01 if market != 'a' else entry * 0.02
            sl = entry - risk
            tp1 = entry + risk * 2
            tp2 = entry + risk * 3

            market_icon = "🇭🇰" if market == 'hk' else ("🇺🇸" if market == 'us' else "🇨🇳")
            report += f"| **{idx}** | {market_icon} | `{ticker}` | {format_price(entry, currency)} | {format_price(sl, currency)} | {format_price(tp1, currency)} | {format_price(tp2, currency)} | {zone_icon} {zone} | {conf_bar} {confluence} |\n"
        report += "\n*Trade recommendations based on ICT/SMC confluence scoring. Always confirm with your own analysis.*\n\n---\n\n"

    report += "## ⚠️ Disclaimer\n\n"
    report += "*This report is for informational purposes only. Not financial advice. "
    report += "StockVue is an algorithmic screening tool — always do your own due diligence before investing.*\n\n"
    report += "---\n\n"
    report += "📊 **StockVue Daily Analysis** | Generated automatically by algorithm\n"
    report += f"🕐 Report generated at {time_str} HK Time on {date_str}\n\n"

    return report


def generate_html_dashboard(a_stocks, hk_stocks, us_stocks, sentiment, cfg: dict, win_rate_threshold: int = 75):
    from datetime import timedelta
    hk_dt = datetime.now() + timedelta(hours=8)
    date_str = hk_dt.strftime("%Y-%m-%d")
    hk_time = hk_dt.strftime("%H:%M")
    wr_cfg = cfg["win_rates"]
    wr_threshold = cfg.get("display_win_rate_min", win_rate_threshold)

    def passes_threshold(stock):
        wr_1d = get_win_rate(stock['change_pct'], wr_cfg, "1d")
        return wr_1d >= wr_threshold

    def hk_color(pct):
        return "#22c55e" if pct >= 3 else ("#eab308" if pct >= 1.5 else "#ef4444")
    def us_color(pct):
        return "#22c55e" if pct >= 3 else ("#eab308" if pct >= 1.5 else "#ef4444")
    def a_color(pct):
        return "#22c55e" if pct >= 3 else ("#eab308" if pct >= 1.5 else "#ef4444")

    def next_close_hk(hk_dt):
        dt = hk_dt.replace(hour=16, minute=0, second=0, microsecond=0)
        if dt <= hk_dt or dt.weekday() >= 5:
            dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.strftime("明天%H:%M")

    def next_close_us(hk_dt):
        dt = hk_dt.replace(hour=4, minute=0, second=0, microsecond=0)
        if dt <= hk_dt or dt.weekday() >= 5:
            dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.strftime("明天%H:%M")

    def next_close_a(hk_dt):
        dt = hk_dt.replace(hour=15, minute=0, second=0, microsecond=0)
        if dt <= hk_dt or dt.weekday() >= 5:
            dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.strftime("明天%H:%M")

    sell_hk = next_close_hk(hk_dt)
    sell_us = next_close_us(hk_dt)
    sell_a = next_close_a(hk_dt)

    hk_rows = ""
    for idx, s in enumerate([s for s in hk_stocks if passes_threshold(s)], 1):
        confluence = s.get('confluence', 0)
        wr_1d = format_win_rate(s['change_pct'], wr_cfg, "1d", confluence)
        wr_5d = format_win_rate(s['change_pct'], wr_cfg, "5d", confluence)
        fib = s.get('fib', {})
        zone = fib.get('zone', 'N/A') if fib else 'N/A'
        zone_color = "#3b82f6" if zone == 'DISCOUNT' else ("#ef4444" if zone == 'PREMIUM' else "#64748b")
        conf_color = "#22c55e" if confluence >= 60 else ("#eab308" if confluence >= 40 else "#ef4444")
        mss = s.get('mss_active', False)
        mss_dir = s.get('mss_direction', '')
        mss_txt = f"BULLISH" if mss_dir == 'bullish' else ("BEARISH" if mss_dir == 'bearish' else "—")
        mss_color = "#22c55e" if mss and mss_dir == 'bullish' else ("#ef4444" if mss and mss_dir == 'bearish' else "#64748b")
        bos = s.get('bos_count', 0)
        fvg = s.get('fvg_count', 0)
        sig = "BUY" if (s.get('mss_active') and s.get('mss_direction') == 'bullish') or confluence >= 60 else "WATCH"
        sig_color = "#22c55e" if sig == "BUY" else "#eab308"
        ict = s.get('ict', {})
        long_sig = ict.get('long_signal') if ict else None
        if long_sig:
            entry = f"{float(long_sig.entry_price):.2f}"
            sl = f"{float(long_sig.stop_loss):.2f}"
            tp1 = f"{float(long_sig.take_profit_1):.2f}"
            tp2 = f"{float(long_sig.take_profit_2):.2f}"
            tp3 = f"{float(long_sig.take_profit_3):.2f}"
            entry_txt = f"<span style='color:#22c55e;font-weight:600'>{entry}</span>"
            sl_txt = f"<span style='color:#ef4444'>{sl}</span>"
            tp_txt = f"<span style='color:#22c55e'>{tp1} / {tp2} / {tp3}</span>"
        else:
            entry_txt = sl_txt = tp_txt = "—"
        hk_rows += f"""<tr>
            <td>{idx}</td>
            <td><span class="ticker-badge">{s['ticker']}</span></td>
            <td><strong>{s['name']}</strong></td>
            <td>HKD {s['price']:.2f}</td>
            <td><span class="change-badge" style="color:{hk_color(s['change_pct'])}">+{s['change_pct']}%</span></td>
            <td><span style="color:{zone_color};font-weight:600;font-size:0.8rem">{zone}</span></td>
            <td><span style="color:{conf_color};font-weight:700">{confluence}</span></td>
            <td><span class="winrate">{wr_1d}%</span></td>
            <td><span class="winrate5d">{wr_5d}%</span></td>
            <td><span style="color:{mss_color};font-weight:600;font-size:0.75rem">{mss_txt}</span></td>
            <td>{bos}</td><td>{fvg}</td>
            <td>{entry_txt}</td>
            <td>{sl_txt}</td>
            <td>{tp_txt}</td>
            <td><span class="signal-buy" style="background:{sig_color}">{sig}</span></td>
        </tr>"""

    us_rows = ""
    for idx, s in enumerate([s for s in us_stocks if passes_threshold(s)], 1):
        confluence = s.get('confluence', 0)
        wr_1d = format_win_rate(s['change_pct'], wr_cfg, "1d", confluence)
        wr_5d = format_win_rate(s['change_pct'], wr_cfg, "5d", confluence)
        fib = s.get('fib', {})
        zone = fib.get('zone', 'N/A') if fib else 'N/A'
        zone_color = "#3b82f6" if zone == 'DISCOUNT' else ("#ef4444" if zone == 'PREMIUM' else "#64748b")
        conf_color = "#22c55e" if confluence >= 60 else ("#eab308" if confluence >= 40 else "#ef4444")
        mss = s.get('mss_active', False)
        mss_dir = s.get('mss_direction', '')
        mss_txt = f"BULLISH" if mss_dir == 'bullish' else ("BEARISH" if mss_dir == 'bearish' else "—")
        mss_color = "#22c55e" if mss and mss_dir == 'bullish' else ("#ef4444" if mss and mss_dir == 'bearish' else "#64748b")
        bos = s.get('bos_count', 0)
        fvg = s.get('fvg_count', 0)
        sig = "BUY" if (s.get('mss_active') and s.get('mss_direction') == 'bullish') or confluence >= 60 else "WATCH"
        sig_color = "#22c55e" if sig == "BUY" else "#eab308"
        ict = s.get('ict', {})
        long_sig = ict.get('long_signal') if ict else None
        if long_sig:
            entry = f"{float(long_sig.entry_price):.2f}"
            sl = f"{float(long_sig.stop_loss):.2f}"
            tp1 = f"{float(long_sig.take_profit_1):.2f}"
            tp2 = f"{float(long_sig.take_profit_2):.2f}"
            tp3 = f"{float(long_sig.take_profit_3):.2f}"
            entry_txt = f"<span style='color:#22c55e;font-weight:600'>{entry}</span>"
            sl_txt = f"<span style='color:#ef4444'>{sl}</span>"
            tp_txt = f"<span style='color:#22c55e'>{tp1} / {tp2} / {tp3}</span>"
        else:
            entry_txt = sl_txt = tp_txt = "—"
        us_rows += f"""<tr>
            <td>{idx}</td>
            <td><span class="ticker-badge">{s['ticker']}</span></td>
            <td><strong>{s['name']}</strong></td>
            <td>USD {s['price']:.2f}</td>
            <td><span class="change-badge" style="color:{us_color(s['change_pct'])}">+{s['change_pct']}%</span></td>
            <td><span style="color:{zone_color};font-weight:600;font-size:0.8rem">{zone}</span></td>
            <td><span style="color:{conf_color};font-weight:700">{confluence}</span></td>
            <td><span class="winrate">{wr_1d}%</span></td>
            <td><span class="winrate5d">{wr_5d}%</span></td>
            <td><span style="color:{mss_color};font-weight:600;font-size:0.75rem">{mss_txt}</span></td>
            <td>{bos}</td><td>{fvg}</td>
            <td>{entry_txt}</td>
            <td>{sl_txt}</td>
            <td>{tp_txt}</td>
            <td><span class="signal-buy" style="background:{sig_color}">{sig}</span></td>
        </tr>"""

    a_rows = ""
    for idx, s in enumerate([s for s in a_stocks if passes_threshold(s)], 1):
        confluence = s.get('confluence', 0)
        if confluence == 0:
            confluence = compute_basic_confluence(s)
        wr_1d = format_win_rate(s['change_pct'], wr_cfg, "1d", confluence)
        wr_5d = format_win_rate(s['change_pct'], wr_cfg, "5d", confluence)
        fib = s.get('fib', {})
        zone = fib.get('zone', 'N/A') if fib else 'N/A'
        zone_color = "#3b82f6" if zone == 'DISCOUNT' else ("#ef4444" if zone == 'PREMIUM' else "#64748b")
        conf_color = "#22c55e" if confluence >= 60 else ("#eab308" if confluence >= 40 else "#ef4444")
        mss = s.get('mss_active', False)
        mss_dir = s.get('mss_direction', '')
        mss_txt = f"BULLISH" if mss_dir == 'bullish' else ("BEARISH" if mss_dir == 'bearish' else "—")
        mss_color = "#22c55e" if mss and mss_dir == 'bullish' else ("#ef4444" if mss and mss_dir == 'bearish' else "#64748b")
        bos = s.get('bos_count', 0)
        fvg = s.get('fvg_count', 0)
        sig = "BUY" if (s.get('mss_active') and s.get('mss_direction') == 'bullish') or confluence >= 60 else "WATCH"
        sig_color = "#22c55e" if sig == "BUY" else "#eab308"
        ict = s.get('ict', {})
        long_sig = ict.get('long_signal') if ict else None
        if long_sig:
            entry = f"{float(long_sig.entry_price):.2f}"
            sl = f"{float(long_sig.stop_loss):.2f}"
            tp1 = f"{float(long_sig.take_profit_1):.2f}"
            tp2 = f"{float(long_sig.take_profit_2):.2f}"
            tp3 = f"{float(long_sig.take_profit_3):.2f}"
            entry_txt = f"<span style='color:#22c55e;font-weight:600'>{entry}</span>"
            sl_txt = f"<span style='color:#ef4444'>{sl}</span>"
            tp_txt = f"<span style='color:#22c55e'>{tp1} / {tp2} / {tp3}</span>"
        else:
            entry_txt = sl_txt = tp_txt = "—"
        a_rows += f"""<tr>
            <td>{idx}</td>
            <td><span class="ticker-badge">{s['code']}</span></td>
            <td><strong>{s['name']}</strong></td>
            <td>CNY {s['price']:.2f}</td>
            <td><span class="change-badge" style="color:{a_color(s['change_pct'])}">+{s['change_pct']}%</span></td>
            <td>{s.get('turnover_rate', 0):.1f}%</td>
            <td><span style="color:{zone_color};font-weight:600;font-size:0.8rem">{zone}</span></td>
            <td><span style="color:{conf_color};font-weight:700">{confluence}</span></td>
            <td><span class="winrate">{wr_1d}%</span></td>
            <td><span class="winrate5d">{wr_5d}%</span></td>
            <td><span style="color:{mss_color};font-weight:600;font-size:0.75rem">{mss_txt}</span></td>
            <td>{bos}</td><td>{fvg}</td>
            <td>{entry_txt}</td>
            <td>{sl_txt}</td>
            <td>{tp_txt}</td>
            <td><span class="signal-buy" style="background:{sig_color}">{sig}</span></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockVue — Daily Market Report {date_str}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }}

    .header {{ text-align: center; margin-bottom: 2.5rem; }}
    .logo {{ font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #22c55e, #3b82f6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -0.5px; }}
    .logo span {{ font-size: 1rem; display: block; color: #64748b; font-weight: 400; -webkit-text-fill-color: #64748b; }}
    .meta {{ margin-top: 0.75rem; color: #94a3b8; font-size: 0.9rem; }}

    .sentiment-bar {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2.5rem; }}
    .sentiment-card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; text-align: center; border: 1px solid #334155; }}
    .sentiment-card .market {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: #64748b; margin-bottom: 0.5rem; }}
    .sentiment-card .sentiment {{ font-size: 1.4rem; font-weight: 700; }}
    .sentiment-card .bullish {{ color: #22c55e; }}
    .sentiment-card .bearish {{ color: #ef4444; }}
    .sentiment-card .neutral {{ color: #eab308; }}

    .market-section {{ background: #1e293b; border-radius: 16px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
    .market-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; padding-bottom: 1rem; border-bottom: 1px solid #334155; }}
    .market-flag {{ font-size: 1.5rem; }}
    .market-title {{ font-size: 1.1rem; font-weight: 700; color: #f8fafc; }}
    .market-subtitle {{ font-size: 0.8rem; color: #64748b; margin-left: auto; }}

    table {{ width: 100%; border-collapse: collapse; }}
    thead tr {{ border-bottom: 1px solid #334155; }}
    th {{ padding: 0.65rem 0.75rem; text-align: left; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; font-weight: 600; }}
    th:last-child, th:nth-last-child(2) {{ text-align: center; }}
    td {{ padding: 0.85rem 0.75rem; font-size: 0.9rem; border-bottom: 1px solid #1e293b; }}
    td:nth-child(4) {{ text-align: center; }}
    td:last-child, td:nth-last-child(2) {{ text-align: center; }}
    tbody tr:hover {{ background: #263548; }}
    tbody tr:last-child td {{ border-bottom: none; }}

    .ticker-badge {{ background: #334155; color: #22c55e; padding: 0.2rem 0.5rem; border-radius: 6px; font-family: 'Courier New', monospace; font-size: 0.8rem; font-weight: 600; }}
    .change-badge {{ font-weight: 700; font-size: 0.95rem; }}
    .winrate {{ background: #1e3a5f; color: #60a5fa; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
    .winrate5d {{ background: #3b1f5f; color: #a78bfa; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
    .signal-buy {{ background: #22c55e; color: #052e16; padding: 0.2rem 0.7rem; border-radius: 20px; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.5px; }}

    .disclaimer {{ text-align: center; color: #475569; font-size: 0.78rem; padding: 1.5rem; line-height: 1.6; }}
    .disclaimer span {{ color: #f59e0b; }}

    @media (max-width: 640px) {{
        .sentiment-bar {{ grid-template-columns: 1fr; }}
        .market-section {{ padding: 1rem; }}
        .market-header {{ flex-wrap: wrap; }}
        .market-subtitle {{ margin-left: 0; margin-top: 0.25rem; width: 100%; }}
        table {{ display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
        thead {{ position: sticky; top: 0; z-index: 10; }}
        th {{ white-space: normal; padding: 0.4rem 0.3rem; font-size: 0.6rem; min-width: 50px; line-height: 1.2; }}
        td {{ white-space: nowrap; padding: 0.5rem 0.3rem; font-size: 0.7rem; min-width: 50px; }}
        th:first-child, td:first-child {{ position: sticky; left: 0; z-index: 5; background: #1e293b; }}
        th:nth-child(2) {{ position: sticky; left: 60px; z-index: 5; }}
        td:nth-child(2) {{ position: sticky; left: 60px; z-index: 5; background: #1e293b; }}
        td:first-child, td:nth-child(2) {{ background: #1e293b; }}
        tbody tr:last-child td {{ border-bottom: none; }}
        .winrate, .winrate5d, .signal-buy {{ padding: 0.1rem 0.3rem; font-size: 0.65rem; }}
        .ticker-badge {{ padding: 0.1rem 0.25rem; font-size: 0.65rem; }}
        .change-badge {{ font-size: 0.8rem; }}
    }}
</style>
</head>
<body>
<div class="container">

    <div class="header">
        <div class="logo">StockVue<span>Daily Market Analysis</span></div>
        <div class="meta">📅 {date_str} &nbsp;|&nbsp; ⏰ {hk_time} HK Time</div>
    </div>

    <div class="sentiment-bar">
        <div class="sentiment-card">
            <div class="market">🇭🇰 Hong Kong</div>
            <div class="sentiment {'bullish' if sentiment.get('hk')=='BULLISH' else ('bearish' if sentiment.get('hk')=='BEARISH' else 'neutral')}">{sentiment.get('hk','NEUTRAL')}</div>
        </div>
        <div class="sentiment-card">
            <div class="market">🇺🇸 US Markets</div>
            <div class="sentiment {'bullish' if sentiment.get('us')=='BULLISH' else ('bearish' if sentiment.get('us')=='BEARISH' else 'neutral')}">{sentiment.get('us','NEUTRAL')}</div>
        </div>
        <div class="sentiment-card">
            <div class="market">🇨🇳 A-Share China</div>
            <div class="sentiment {'bullish' if sentiment.get('a')=='BULLISH' else ('bearish' if sentiment.get('a')=='BEARISH' else 'neutral')}">{sentiment.get('a','NEUTRAL')}</div>
        </div>
    </div>

    <div class="market-section">
        <div class="market-header">
            <span class="market-flag">🇭🇰</span>
            <span class="market-title">Hong Kong Market</span>
            <span class="market-subtitle">Top Movers &nbsp;|&nbsp; 平倉: {sell_hk} HK</span>
        </div>
        <table>
            <thead><tr><th>#</th><th>股票<br>Ticker</th><th>名稱<br>Name</th><th>價格<br>Price</th><th>漲幅<br>Chg%</th><th>區域<br>Zone</th><th>信心<br>Conf</th><th>1日勝率<br>1D%</th><th>5日勝率<br>5D%</th><th>結構<br>MSS</th><th>突破<br>BOS</th><th>缺口<br>FVG</th><th>入場<br>Entry</th><th>止損<br>SL</th><th>目標價<br>TP1/2/3</th><th>訊號<br>Sig</th></tr></thead>
            <tbody>{hk_rows if hk_rows else '<tr><td colspan="16" style="text-align:center;color:#64748b;">今日無符合條件的股票</td></tr>'}</tbody>
        </table>
    </div>

    <div class="market-section">
        <div class="market-header">
            <span class="market-flag">🇺🇸</span>
            <span class="market-title">US Market</span>
            <span class="market-subtitle">Top Movers &nbsp;|&nbsp; 平倉: {sell_us} HK</span>
        </div>
        <table>
            <thead><tr><th>#</th><th>股票<br>Ticker</th><th>名稱<br>Name</th><th>價格<br>Price</th><th>漲幅<br>Chg%</th><th>區域<br>Zone</th><th>信心<br>Conf</th><th>1日勝率<br>1D%</th><th>5日勝率<br>5D%</th><th>結構<br>MSS</th><th>突破<br>BOS</th><th>缺口<br>FVG</th><th>入場<br>Entry</th><th>止損<br>SL</th><th>目標價<br>TP1/2/3</th><th>訊號<br>Sig</th></tr></thead>
            <tbody>{us_rows if us_rows else '<tr><td colspan="16" style="text-align:center;color:#64748b;">今日無符合條件的股票</td></tr>'}</tbody>
        </table>
    </div>

    <div class="market-section">
        <div class="market-header">
            <span class="market-flag">🇨🇳</span>
            <span class="market-title">A-Share Market (China)</span>
            <span class="market-subtitle">Top Movers &nbsp;|&nbsp; 平倉: {sell_a} HK</span>
        </div>
        <table>
            <thead><tr><th>#</th><th>代碼<br>Code</th><th>名稱<br>Name</th><th>價格<br>Price</th><th>漲幅<br>Chg%</th><th>換手率<br>Turn%</th><th>區域<br>Zone</th><th>信心<br>Conf</th><th>1日勝率<br>1D%</th><th>5日勝率<br>5D%</th><th>結構<br>MSS</th><th>突破<br>BOS</th><th>缺口<br>FVG</th><th>入場<br>Entry</th><th>止損<br>SL</th><th>目標價<br>TP1/2/3</th><th>訊號<br>Sig</th></tr></thead>
            <tbody>{a_rows if a_rows else '<tr><td colspan="17" style="text-align:center;color:#64748b;">今日無符合條件的股票</td></tr>'}</tbody>
        </table>
    </div>

    <div class="disclaimer">
        ⚠️ <span>Not financial advice.</span> StockVue is an algorithmic screening tool.
        Always do your own due diligence before investing.
    </div>
</div>
</body>
</html>"""

    return html