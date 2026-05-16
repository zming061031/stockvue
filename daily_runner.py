#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StockVue - Unified Daily Runner v2.0
- Loads config from config.yaml
- Robust retry with exponential backoff
- A-share fallback chain (akshare -> eastmoney)
- Market sentiment data
- Gumroad posting
- Rich markdown reports + HTML dashboard
"""

import sys
import json
import os
import re
import logging
import yaml
import requests
import akshare
import yfinance
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
from report_formatter import generate_rich_report, generate_html_dashboard
from ict_smc_analyzer import ICTSMCAnalyzer, Candle, analyze_stock_ict
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "stockvue.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def calc_rsi(closes, period=14):
    """Calculate RSI for a list of close prices."""
    n = len(closes)
    if n < period + 1:
        return [None] * n
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        diff = float(closes[i]) - float(closes[i-1])
        if diff > 0:
            gains[i] = diff
        else:
            losses[i] = abs(diff)
    rsi = [None] * n
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    for i in range(period, n):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1 + rs))
    return rsi


def calc_ma(closes, period):
    n = len(closes)
    ma = [None] * n
    for i in range(period - 1, n):
        ma[i] = sum(float(closes[j]) for j in range(i - period + 1, i + 1)) / period
    return ma


def calc_vol_ratio(volumes, period=5):
    n = len(volumes)
    ratios = [None] * n
    for i in range(period - 1, n):
        window_sum = sum(float(volumes[j]) for j in range(i - period + 1, i + 1))
        avg_vol = window_sum / period
        if avg_vol > 0:
            ratios[i] = float(volumes[i]) / avg_vol
        else:
            ratios[i] = 1.0
    return ratios


def calc_fib_retracement(high, low, current):
    """Calculate Fibonacci retracement level: 0.618 and 0.786 zones."""
    range_val = high - low
    if range_val <= 0:
        return None
    level_618 = low + range_val * 0.618
    level_786 = low + range_val * 0.786
    zone = "PREMIUM" if current > level_618 else ("DISCOUNT" if current < level_786 else "NEUTRAL")
    return {
        'level_618': level_618,
        'level_786': level_786,
        'zone': zone,
        'retracement_pct': (current - low) / range_val if range_val > 0 else 0.5
    }


def calc_confluence_score(record, fib_data, rsi):
    """Calculate confluence score based on ICT/SMC concepts.
    Score 0-100 based on multiple confirmations."""
    score = 0
    reasons = []

    if fib_data and fib_data['zone'] == 'DISCOUNT':
        score += 30
        reasons.append('DiscountZone')
    elif fib_data and fib_data['zone'] == 'PREMIUM':
        score += 10
        reasons.append('PremiumZone')

    if rsi and 30 <= rsi <= 50:
        score += 20
        reasons.append('RSIOversold')
    elif rsi and 50 < rsi <= 70:
        score += 10
        reasons.append('RSINormal')

    vol_ratio = record.get('vol_ratio', 1.0)
    if vol_ratio and 1.0 <= vol_ratio <= 2.5:
        score += 15
        reasons.append('NormalVol')
    elif vol_ratio and vol_ratio > 2.5:
        score += 25
        reasons.append('HighVolMomentum')

    price = record.get('price', 0)
    ma20 = record.get('ma20', 0)
    if ma20 and price > ma20:
        score += 15
        reasons.append('AboveMA20')

    ma5 = record.get('ma5', 0)
    if ma5 and price > ma5:
        score += 10
        reasons.append('AboveMA5')

    return score, reasons


def compute_indicators_for_stock(ticker, lookback=25):
    """Fetch recent history and compute RSI, MA5, MA20, VolRatio, Fib, Confluence."""
    try:
        stock = yfinance.Ticker(ticker)
        hist = stock.history(period=f"{lookback}d", auto_adjust=True)
        if len(hist) < 25:
            return None
        closes = [row['Close'] for _, row in hist.iterrows()]
        volumes = [row['Volume'] for _, row in hist.iterrows()]
        rsi_vals = calc_rsi(closes, 14)
        ma5_vals = calc_ma(closes, 5)
        ma20_vals = calc_ma(closes, 20)
        vol_ratio_vals = calc_vol_ratio(volumes, 5)
        last = len(closes) - 1

        high = max(closes)
        low = min(closes)
        current = closes[last]
        fib_data = calc_fib_retracement(high, low, current)
        rsi = rsi_vals[last]
        confluence, reasons = calc_confluence_score(
            {'price': current, 'vol_ratio': vol_ratio_vals[last], 'ma5': ma5_vals[last], 'ma20': ma20_vals[last]},
            fib_data, rsi
        )

        return {
            'rsi': rsi,
            'ma5': ma5_vals[last],
            'ma20': ma20_vals[last],
            'vol_ratio': vol_ratio_vals[last],
            'fib': fib_data,
            'confluence': confluence,
            'confluence_reasons': reasons,
        }
    except Exception:
        return None


def analyze_with_ict(ticker: str, lookback: int = 50) -> dict:
    """Run full ICT/SMC analysis on a ticker. Returns dict with all signals."""
    result = analyze_stock_ict(ticker, lookback=lookback)
    if 'error' in result:
        return {}
    return result


def analyze_a_share_with_ict(symbol: str, lookback: int = 50) -> dict:
    """Run full ICT/SMC analysis on an A-share ticker via Sina Finance."""
    try:
        url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": lookback}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        raw = json.loads(r.content.decode('gbk'))
        if not raw or len(raw) < 20:
            return {}

        candles = []
        for item in reversed(raw):
            candles.append(Candle(
                open=float(item['open']),
                high=float(item['high']),
                low=float(item['low']),
                close=float(item['close']),
                volume=float(item.get('volume', 0))
            ))

        analyzer = ICTSMCAnalyzer(candles)
        summary = analyzer.get_summary()
        summary['current_price'] = candles[-1].close if candles else 0
        summary['ticker'] = symbol
        summary['candle_count'] = len(candles)
        return summary
    except Exception as e:
        logger.debug(f"  ICT analysis failed for {symbol}: {e}")
        return {}


def passes_threshold(record: dict, cfg: dict, horizon: str = "1d") -> bool:
    pct = record.get('change_pct', 0)
    wr_cfg = cfg.get("win_rates", {})
    tier = wr_cfg.get("default", {})
    if pct >= 5: tier = wr_cfg.get("tier1", tier)
    elif pct >= 3: tier = wr_cfg.get("tier2", tier)
    elif pct >= 2: tier = wr_cfg.get("tier3", tier)
    elif pct >= 1.5: tier = wr_cfg.get("tier4", tier)
    if isinstance(tier, dict):
        win_rate = tier.get(horizon, tier.get("1d", 50))
    else:
        win_rate = int(tier)
    threshold = cfg.get("display_win_rate_min", 75)
    return win_rate >= threshold


def fetch_a_share_indicators(symbol, lookback=25):
    """Fetch A-share history via Sina and compute indicators."""
    try:
        url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": lookback}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        raw = json.loads(r.content.decode('gbk'))
        if not raw or len(raw) < 20:
            return None
        closes = [float(item['close']) for item in raw]
        volumes = [float(item['volume']) for item in raw]
        rsi_vals = calc_rsi(closes, 14)
        ma5_vals = calc_ma(closes, 5)
        ma20_vals = calc_ma(closes, 20)
        vol_ratio_vals = calc_vol_ratio(volumes, 5)
        last = len(closes) - 1

        high = max(closes)
        low = min(closes)
        current = closes[last]
        fib_data = calc_fib_retracement(high, low, current)
        rsi = rsi_vals[last]
        confluence, reasons = calc_confluence_score(
            {'price': current, 'vol_ratio': vol_ratio_vals[last], 'ma5': ma5_vals[last], 'ma20': ma20_vals[last]},
            fib_data, rsi
        )

        return {
            'rsi': rsi,
            'ma5': ma5_vals[last],
            'ma20': ma20_vals[last],
            'vol_ratio': vol_ratio_vals[last],
            'fib': fib_data,
            'confluence': confluence,
            'confluence_reasons': reasons,
        }
    except Exception:
        return None


def passes_technical_filters(record, rsi_max=70, rsi_min=0, vol_ratio_min=0.8, vol_ratio_max=1.2, require_ma5=False, require_ma20=True, confluence_min=0):
    rsi = record.get('rsi')
    ma5 = record.get('ma5')
    ma20 = record.get('ma20')
    vol_ratio = record.get('vol_ratio')
    if rsi is None or ma5 is None or ma20 is None:
        return True
    if rsi >= rsi_max or rsi < rsi_min:
        return False
    if vol_ratio is not None and (vol_ratio < vol_ratio_min or vol_ratio > vol_ratio_max):
        return False
    if require_ma5 and record.get('price', 0) < ma5:
        return False
    if require_ma20 and record.get('price', 0) < ma20:
        return False
    confluence = record.get('confluence', 0)
    if confluence_min > 0 and confluence < confluence_min:
        return False
    return True


def win_rate(pct: float, cfg: dict, horizon: str = "1d") -> str:
    if pct >= 5: tier = cfg["tier1"]
    elif pct >= 3: tier = cfg["tier2"]
    elif pct >= 2: tier = cfg["tier3"]
    elif pct >= 1.5: tier = cfg["tier4"]
    else: tier = cfg["default"]
    return str(tier.get(horizon, tier["1d"] if isinstance(tier, dict) else tier))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def fetch_a_share_primary(cfg: dict):
    logger.info("Fetching A-share via AKShare...")
    df = ak.stock_zh_a_spot_em()
    sc = cfg["screening"]["a_share"]
    df_filtered = df[
        (df['成交額'] >= sc["min_turnover"]) &
        (df['換手率'] >= sc["min_turnover_rate"]) &
        (df['漲跌幅'] >= sc["min_change_pct"])
    ].copy()
    df_filtered = df_filtered.sort_values('成交額', ascending=False).head(sc["max_results"])
    tf = cfg.get("technical_filters", {})
    results = []
    for _, row in df_filtered.iterrows():
        symbol = row['代碼']
        record = {
            'code': symbol, 'name': row['名稱'],
            'price': row['最新價'], 'change_pct': row['漲跌幅'],
            'turnover_rate': row['換手率'], 'volume': row['成交額']
        }
        indicators = fetch_a_share_indicators(symbol, lookback=25)
        if indicators:
            record.update(indicators)
            if not passes_technical_filters(record,
                                            rsi_max=tf.get("rsi_max", 70),
                                            rsi_min=tf.get("rsi_min", 0),
                                            vol_ratio_min=tf.get("vol_ratio_min", 0.5),
                                            vol_ratio_max=tf.get("vol_ratio_max", 3.0),
                                            require_ma5=tf.get("ma5_required", False),
                                            require_ma20=tf.get("ma20_required", True),
                                            confluence_min=tf.get("confluence_min", 40)):
                logger.debug(f"  {symbol}: filtered out rsi={indicators.get('rsi')} vol={indicators.get('vol_ratio')} confluence={indicators.get('confluence', 0)}")
                continue
        ict_data = analyze_a_share_with_ict(symbol, lookback=50)
        if ict_data:
            record['ict'] = ict_data
            record['long_signal'] = ict_data.get('long_signal')
            record['short_signal'] = ict_data.get('short_signal')
            record['mss_active'] = ict_data.get('mss_active', False)
            record['mss_direction'] = ict_data.get('mss_direction')
            record['bos_count'] = ict_data.get('bos_count', 0)
            record['fvg_count'] = ict_data.get('fvg_count', 0)
            record['ob_count'] = ict_data.get('order_blocks', 0)
            record['liquidity_sweeps'] = ict_data.get('liquidity_sweeps', 0)
        results.append(record)
    logger.info(f"  A-share: {len(results)} stocks passed screening")
    return results


def fetch_a_share_fallback(cfg: dict):
    logger.info("Fetching A-share via Sina Finance fallback...")
    sc = cfg["screening"]["a_share"]
    min_amount = sc["min_turnover"]
    min_tr = sc["min_turnover_rate"]
    min_change = sc["min_change_pct"]
    tf = cfg.get("technical_filters", {})
    rsi_max = tf.get("rsi_max", 70)
    rsi_min = tf.get("rsi_min", 0)
    vol_min = tf.get("vol_ratio_min", 0.5)
    vol_max = tf.get("vol_ratio_max", 3.0)
    require_ma5 = tf.get("ma5_required", False)
    require_ma20 = tf.get("ma20_required", True)
    confluence_min = tf.get("confluence_min", 40)

    try:
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        params = {
            "page": 1, "num": 100, "sort": "changepercent", "asc": 0,
            "node": "hs_a", "symbol": "", "_s_r_a": "page"
        }
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = json.loads(r.content.decode('gbk'))
        stocks = []
        for item in data:
            try:
                change = float(item.get("changepercent", 0))
                amount = float(item.get("amount", 0))
                turnover_ratio = float(item.get("turnoverratio", 0))
                price = float(item.get("trade", 0))
                symbol = item.get("symbol", "")
                if change >= min_change and amount >= min_amount and turnover_ratio >= min_tr:
                    record = {
                        "code": symbol,
                        "name": item.get("name", ""),
                        "price": price,
                        "change_pct": round(change, 2),
                        "turnover_rate": round(turnover_ratio, 2),
                        "volume": amount
                    }
                    indicators = fetch_a_share_indicators(symbol, lookback=25)
                    if indicators:
                        record.update(indicators)
                        if not passes_technical_filters(record, rsi_max=rsi_max, rsi_min=rsi_min, vol_ratio_min=vol_min, vol_ratio_max=vol_max,
                                                        require_ma5=require_ma5, require_ma20=require_ma20,
                                                        confluence_min=confluence_min):
                            logger.debug(f"  {symbol}: filtered out rsi={indicators.get('rsi')} vol={indicators.get('vol_ratio')} confluence={indicators.get('confluence', 0)}")
                            continue
                    ict_data = analyze_a_share_with_ict(symbol, lookback=50)
                    if ict_data:
                        record['ict'] = ict_data
                        record['long_signal'] = ict_data.get('long_signal')
                        record['short_signal'] = ict_data.get('short_signal')
                        record['mss_active'] = ict_data.get('mss_active', False)
                        record['mss_direction'] = ict_data.get('mss_direction')
                        record['bos_count'] = ict_data.get('bos_count', 0)
                        record['fvg_count'] = ict_data.get('fvg_count', 0)
                        record['ob_count'] = ict_data.get('order_blocks', 0)
                        record['liquidity_sweeps'] = ict_data.get('liquidity_sweeps', 0)
                        # Update confluence with ICT signals
                        ict_conf = record.get('confluence', 0)
                        if ict_data.get('mss_active'):
                            ict_conf += 25
                        if ict_data.get('bos_count', 0) > 0:
                            ict_conf += 20
                        if ict_data.get('fvg_count', 0) > 0:
                            ict_conf += 20
                        record['confluence'] = min(ict_conf, 100)
                    stocks.append(record)
            except:
                pass
        stocks.sort(key=lambda x: x["volume"], reverse=True)
        result = stocks[:sc["max_results"]]
        logger.info(f"  Sina Finance fallback: {len(result)} stocks -> {[s['code'] for s in result]}")
        return result
    except Exception as e:
        logger.error(f"Sina Finance fallback failed: {e}")
        return []


def fetch_a_share(cfg: dict):
    try:
        return fetch_a_share_primary(cfg)
    except Exception as e:
        logger.warning(f"AKShare failed: {e}, trying fallback...")
        return fetch_a_share_fallback(cfg)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=1, max=10))
def fetch_hk_stocks(cfg: dict):
    logger.info("Fetching HK stocks via yfinance...")
    tickers = cfg["hk_tickers"]
    sc = cfg["screening"]["hk"]
    min_change = sc["min_change_pct"]
    tf = cfg.get("technical_filters", {})
    rsi_max = tf.get("rsi_max", 70)
    rsi_min = tf.get("rsi_min", 0)
    vol_min = tf.get("vol_ratio_min", 0.5)
    vol_max = tf.get("vol_ratio_max", 3.0)
    confluence_min = tf.get("confluence_min", 40)
    results = []
    for ticker in tickers:
        try:
            info = yfinance.Ticker(ticker).info
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            change = info.get('regularMarketChangePercent', 0)
            logger.info(f"  {ticker}: price={price}, change={change}%, min_change={min_change}%")
            if price and change is not None and change >= min_change:
                indicators = compute_indicators_for_stock(ticker, lookback=25)
                record = {
                    'ticker': ticker, 'name': info.get('shortName', ticker),
                    'price': price, 'change_pct': round(change, 2),
                    'volume': info.get('averageVolume', 0),
                }
                if indicators:
                    record.update(indicators)
                    if not passes_technical_filters(record, rsi_max=rsi_max, rsi_min=rsi_min, vol_ratio_min=vol_min, vol_ratio_max=vol_max,
                                                    require_ma5=tf.get("ma5_required", False),
                                                    require_ma20=tf.get("ma20_required", True),
                                                    confluence_min=confluence_min):
                        logger.info(f"  {ticker}: FILTERED rsi={indicators.get('rsi'):.1f} vol={indicators.get('vol_ratio'):.2f} confluence={indicators.get('confluence', 0)}")
                        continue
                ict_data = analyze_with_ict(ticker, lookback=50)
                if ict_data:
                    record['ict'] = ict_data
                    record['long_signal'] = ict_data.get('long_signal')
                    record['short_signal'] = ict_data.get('short_signal')
                    record['mss_active'] = ict_data.get('mss_active', False)
                    record['mss_direction'] = ict_data.get('mss_direction')
                    record['bos_count'] = ict_data.get('bos_count', 0)
                    record['fvg_count'] = ict_data.get('fvg_count', 0)
                    record['ob_count'] = ict_data.get('order_blocks', 0)
                    record['liquidity_sweeps'] = ict_data.get('liquidity_sweeps', 0)
                results.append(record)
                logger.info(f"  {ticker}: ADDED change={change:.2f}%")
        except Exception as e:
            logger.warning(f"  {ticker}: ERROR {e}")
    results.sort(key=lambda x: x['change_pct'], reverse=True)
    result = results[:sc["max_results"]]
    logger.info(f"  HK: {len(result)} stocks passed screening")
    return result


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=1, max=10))
def fetch_us_stocks(cfg: dict):
    logger.info("Fetching US stocks via yfinance...")
    tickers = cfg["us_tickers"]
    sc = cfg["screening"]["us"]
    min_change = sc["min_change_pct"]
    tf = cfg.get("technical_filters", {})
    rsi_max = tf.get("rsi_max", 70)
    rsi_min = tf.get("rsi_min", 0)
    vol_min = tf.get("vol_ratio_min", 0.5)
    vol_max = tf.get("vol_ratio_max", 3.0)
    confluence_min = tf.get("confluence_min", 40)
    results = []
    for ticker in tickers:
        try:
            info = yfinance.Ticker(ticker).info
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            change = info.get('regularMarketChangePercent', 0)
            logger.info(f"  {ticker}: price={price}, change={change}%, min_change={min_change}%")
            if price and change is not None and change >= min_change:
                indicators = compute_indicators_for_stock(ticker, lookback=25)
                record = {
                    'ticker': ticker, 'name': info.get('shortName', ticker),
                    'price': price, 'change_pct': round(change, 2),
                    'volume': info.get('averageVolume', 0),
                }
                if indicators:
                    record.update(indicators)
                    if not passes_technical_filters(record, rsi_max=rsi_max, rsi_min=rsi_min, vol_ratio_min=vol_min, vol_ratio_max=vol_max,
                                                    require_ma5=tf.get("ma5_required", False),
                                                    require_ma20=tf.get("ma20_required", True),
                                                    confluence_min=confluence_min):
                        logger.info(f"  {ticker}: FILTERED rsi={indicators.get('rsi'):.1f} vol={indicators.get('vol_ratio'):.2f} confluence={indicators.get('confluence', 0)}")
                        continue
                ict_data = analyze_with_ict(ticker, lookback=50)
                if ict_data:
                    record['ict'] = ict_data
                    record['long_signal'] = ict_data.get('long_signal')
                    record['short_signal'] = ict_data.get('short_signal')
                    record['mss_active'] = ict_data.get('mss_active', False)
                    record['mss_direction'] = ict_data.get('mss_direction')
                    record['bos_count'] = ict_data.get('bos_count', 0)
                    record['fvg_count'] = ict_data.get('fvg_count', 0)
                    record['ob_count'] = ict_data.get('order_blocks', 0)
                    record['liquidity_sweeps'] = ict_data.get('liquidity_sweeps', 0)
                results.append(record)
                logger.info(f"  {ticker}: ADDED change={change:.2f}%")
        except Exception as e:
            logger.warning(f"  {ticker}: ERROR {e}")
    results.sort(key=lambda x: x['change_pct'], reverse=True)
    result = results[:sc["max_results"]]
    logger.info(f"  US: {len(result)} stocks passed screening")
    return result


def get_market_sentiment(cfg: dict) -> dict:
    logger.info("Fetching market sentiment...")
    sentiment = {"hk": "NEUTRAL", "us": "NEUTRAL", "a": "NEUTRAL"}
    try:
        hk_idx = yfinance.Ticker("^HSI").info
        hk_change = hk_idx.get('regularMarketChangePercent', 0)
        sentiment["hk"] = "BULLISH" if hk_change > 1 else ("BEARISH" if hk_change < -1 else "NEUTRAL")
    except:
        pass
    try:
        us_idx = yfinance.Ticker("^IXIC").info
        us_change = us_idx.get('regularMarketChangePercent', 0)
        sentiment["us"] = "BULLISH" if us_change > 1 else ("BEARISH" if us_change < -1 else "NEUTRAL")
    except:
        pass
    logger.info(f"  Sentiment -> HK: {sentiment['hk']}, US: {sentiment['us']}, A: {sentiment['a']}")
    return sentiment


def save_report(report: str, cfg: dict):
    date_str = datetime.now().strftime("%Y-%m-%d")
    reports_dir = os.path.join(BASE_DIR, cfg["output"]["reports_dir"])
    os.makedirs(reports_dir, exist_ok=True)

    md_path = os.path.join(reports_dir, f"{date_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Report saved: {md_path}")

    latest_path = os.path.join(BASE_DIR, cfg["output"]["latest_report"])
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Latest report updated: {latest_path}")

    return md_path


def get_gumroad_tokens(permalink: str):
    s = requests.Session()
    r = s.get(f'https://gumroad.com/products/{permalink}/edit', timeout=10)
    m = re.search(r'csrf-token["\s]+content=["\']([^"\']+)["\']', r.text)
    csrf = m.group(1) if m else None
    cookies = {c.name: c.value for c in s.cookies if c.name in ['_gumroad_app_session', '_gumroad_guid']}
    return csrf, cookies


def post_to_gumroad(content: str, title: str, cfg: dict) -> bool:
    permalink = cfg["gumroad"]["product_permalink"]
    csrf, cookies = get_gumroad_tokens(permalink)
    if not csrf:
        logger.error("CSRF token not found")
        return False
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html',
        'Referer': f'https://gumroad.com/products/{permalink}/edit'
    })
    data = {
        'authenticity_token': csrf,
        'post[title]': title,
        'post[content]': content
    }
    try:
        r = session.post(f"https://gumroad.com/products/{permalink}/posts", data=data, timeout=15)
        status = r.status_code
        logger.info(f"Gumroad post status: {status}")
        return status in [200, 201, 302]
    except Exception as e:
        logger.error(f"Post error: {e}")
        return False


def main():
    logger.info("=" * 50)
    logger.info("StockVue Daily Runner v2.0 starting...")
    logger.info("=" * 50)

    cfg = load_config()

    a_stocks = fetch_a_share(cfg)
    hk_stocks = fetch_hk_stocks(cfg)
    us_stocks = fetch_us_stocks(cfg)
    sentiment = get_market_sentiment(cfg)

    wr_threshold = cfg.get("display_win_rate_min", 75)
    report = generate_rich_report(a_stocks, hk_stocks, us_stocks, sentiment, cfg, wr_threshold)
    md_path = save_report(report, cfg)

    logger.info("Generating HTML dashboard...")
    html_dashboard = generate_html_dashboard(a_stocks, hk_stocks, us_stocks, sentiment, cfg, wr_threshold)
    html_path = os.path.join(BASE_DIR, "dashboard.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_dashboard)
    logger.info(f"HTML dashboard saved: {html_path}")

    logger.info("Posting to Gumroad...")
    date_str = datetime.now().strftime("%Y-%m-%d")
    title = f"{cfg['gumroad']['post_title_prefix']} {date_str}"
    success = post_to_gumroad(report, title, cfg)

    if success:
        logger.info("DONE - All steps completed successfully")
    else:
        logger.warning("DONE - Report saved but Gumroad posting failed (check logs)")

    logger.info("=" * 50)


if __name__ == "__main__":
    main()