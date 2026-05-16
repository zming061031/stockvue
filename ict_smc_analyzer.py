#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICT/SMC Trading Framework Analyzer v1.0
- BOS/CHoCH/MSS Detection
- Liquidity Sweep (SSS/B) Detection
- FVG (Fair Value Gap) Detection
- Order Block / Breaker Block Detection
- Premium/Discount Zone Classification
- Entry/Exit/Stop Loss/Take Profit Automation
- Confluence Scoring
"""

import sys
import io
import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def full_range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class SwingPoint:
    index: int
    price: float
    type: str  # 'high' or 'low'
    strength: float = 1.0  # 1.0=swing, 2.0=higher_high/lower_low, 3.0=break_of_structure


@dataclass
class BOS:
    direction: str  # 'bullish' or 'bearish'
    break_price: float
    prev_swing: SwingPoint
    current_swing: SwingPoint
    strength: float = 1.0


@dataclass
class CHoCH:
    direction: str
    break_price: float
    ms_description: str


@dataclass
class FVG:
    index: int
    direction: str  # 'bullish' or 'bearish'
    high: float
    low: float
    mid: float
    size: float
    fill_price: Optional[float] = None
    filled: bool = False


@dataclass
class OrderBlock:
    index: int
    direction: str  # 'bullish' or 'bearish'
    start_index: int
    end_index: int
    high: float
    low: float
    quality: str = 'normal'  # 'low', 'normal', 'high', 'premium', 'discount'


@dataclass
class LiquiditySweep:
    index: int
    sweep_type: str  # 'SSS' (Short Squeeze Squeeze), 'B' (Bank), 'stop_hunt'
    price: float
    target_swing: SwingPoint
    triggered: bool = False


@dataclass
class TradeSignal:
    direction: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward_1: float
    risk_reward_2: float
    risk_reward_3: float
    confidence: float  # 0-100
    triggers: List[str] = field(default_factory=list)
    confluence_score: int = 0
    zone: str = 'NEUTRAL'  # 'PREMIUM' or 'DISCOUNT'
    ob_reference: Optional[str] = None
    fvg_reference: Optional[str] = None
    liquidity_sweep: Optional[str] = None
    entry_type: str = 'market'  # 'market', 'limit', 'stop'
    notes: str = ''


class ICTSMCAnalyzer:
    def __init__(self, candles: List[Candle], config: Optional[Dict] = None):
        self.candles = candles
        self.config = config or self._default_config()
        self.swing_points: List[SwingPoint] = []
        self.bos_list: List[BOS] = []
        self.choch_list: List[CHoCH] = []
        self.mss_active = False
        self.mss_direction = None
        self.fvg_list: List[FVG] = []
        self.order_blocks: List[OrderBlock] = []
        self.breaker_blocks: List[OrderBlock] = []
        self.liquidity_sweeps: List[LiquiditySweep] = []
        self._detect_swing_points()
        self._detect_bos()
        self._detect_choch()
        self._detect_mss()
        self._detect_fvg()
        self._detect_order_blocks()
        self._detect_liquidity_sweeps()

    def _default_config(self) -> Dict:
        return {
            'swing_strength': 3,
            'ob_strength': 3,
            'fvg_min_size_pct': 0.3,
            'liquidity_sweep_threshold': 0.001,
        }

    def _detect_swing_points(self):
        if len(self.candles) < 5:
            return

        for i in range(2, len(self.candles) - 2):
            current = self.candles[i]
            prev_2 = self.candles[i - 2]
            prev_1 = self.candles[i - 1]
            next_1 = self.candles[i + 1]
            next_2 = self.candles[i + 2]

            if current.high > prev_1.high and current.high > prev_2.high and \
               current.high > next_1.high and current.high > next_2.high:
                strength = self._calc_swing_strength(i, 'high')
                self.swing_points.append(SwingPoint(i, current.high, 'high', strength))

            if current.low < prev_1.low and current.low < prev_2.low and \
               current.low < next_1.low and current.low < next_2.low:
                strength = self._calc_swing_strength(i, 'low')
                self.swing_points.append(SwingPoint(i, current.low, 'low', strength))

    def _calc_swing_strength(self, index: int, swing_type: str) -> float:
        strength = 1.0
        lookback = min(5, index)
        lookforward = min(5, len(self.candles) - index - 1)

        if swing_type == 'high':
            for i in range(index - lookback, index):
                if self.candles[i].high > self.candles[index].high:
                    strength = max(0.5, strength - 0.2)
            for i in range(index + 1, index + lookforward + 1):
                if self.candles[i].high > self.candles[index].high:
                    strength = max(0.5, strength - 0.2)
        else:
            for i in range(index - lookback, index):
                if self.candles[i].low < self.candles[index].low:
                    strength = max(0.5, strength - 0.2)
            for i in range(index + 1, index + lookforward + 1):
                if self.candles[i].low < self.candles[index].low:
                    strength = max(0.5, strength - 0.2)

        if lookback >= 4:
            strength += 0.5
        if lookforward >= 4:
            strength += 0.5

        return min(strength, 3.0)

    def _detect_bos(self):
        highs = [sp for sp in self.swing_points if sp.type == 'high']
        lows = [sp for sp in self.swing_points if sp.type == 'low']

        for i in range(1, len(highs)):
            if highs[i].price > highs[i - 1].price and highs[i].strength >= 1.5:
                candle_at_break = self.candles[highs[i].index]
                body_top = max(candle_at_break.open, candle_at_break.close)
                if body_top > highs[i - 1].price:
                    self.bos_list.append(BOS(
                        direction='bullish',
                        break_price=highs[i].price,
                        prev_swing=highs[i - 1],
                        current_swing=highs[i],
                        strength=highs[i].strength
                    ))

        for i in range(1, len(lows)):
            if lows[i].price < lows[i - 1].price and lows[i].strength >= 1.5:
                candle_at_break = self.candles[lows[i].index]
                body_bottom = min(candle_at_break.open, candle_at_break.close)
                if body_bottom < lows[i - 1].price:
                    self.bos_list.append(BOS(
                        direction='bearish',
                        break_price=lows[i].price,
                        prev_swing=lows[i - 1],
                        current_swing=lows[i],
                        strength=lows[i].strength
                    ))

    def _detect_choch(self):
        if len(self.bos_list) < 2:
            return

        for i in range(1, len(self.bos_list)):
            prev = self.bos_list[i - 1]
            curr = self.bos_list[i]

            if prev.direction == 'bullish' and curr.direction == 'bearish':
                self.choch_list.append(CHoCH(
                    direction='bullish',
                    break_price=curr.break_price,
                    ms_description='Bullish CHoCH - Trend Change to Upside'
                ))
            elif prev.direction == 'bearish' and curr.direction == 'bullish':
                self.choch_list.append(CHoCH(
                    direction='bearish',
                    break_price=curr.break_price,
                    ms_description='Bearish CHoCH - Trend Change to Downside'
                ))

    def _detect_mss(self):
        if len(self.bos_list) < 2:
            return

        last = self.bos_list[-1]
        prev = self.bos_list[-2]

        if last.direction == 'bullish' and prev.direction == 'bearish':
            self.mss_active = True
            self.mss_direction = 'bullish'
        elif last.direction == 'bearish' and prev.direction == 'bullish':
            self.mss_active = True
            self.mss_direction = 'bearish'

    def _detect_fvg(self):
        if len(self.candles) < 3:
            return

        for i in range(2, len(self.candles)):
            prev = self.candles[i - 2]
            curr = self.candles[i]
            mid = self.candles[i - 1]

            if curr.is_bullish and mid.close < prev.open and curr.close > prev.high:
                gap_size = curr.close - prev.high
                fvg = FVG(
                    index=i,
                    direction='bullish',
                    high=prev.high,
                    low=mid.low,
                    mid=(prev.high + mid.low) / 2,
                    size=gap_size
                )
                if self._is_valid_fvg(fvg):
                    self.fvg_list.append(fvg)

            elif curr.is_bearish and mid.close > prev.close and curr.close < prev.low:
                gap_size = prev.low - curr.close
                fvg = FVG(
                    index=i,
                    direction='bearish',
                    high=mid.high,
                    low=prev.low,
                    mid=(mid.high + prev.low) / 2,
                    size=gap_size
                )
                if self._is_valid_fvg(fvg):
                    self.fvg_list.append(fvg)

    def _is_valid_fvg(self, fvg: FVG) -> bool:
        min_size = fvg.mid * (self.config.get('fvg_min_size_pct', 0.3) / 100)
        return fvg.size >= min_size

    def _detect_order_blocks(self):
        if len(self.candles) < 5:
            return

        for i in range(2, len(self.candles) - 1):
            curr = self.candles[i]
            next_candle = self.candles[i + 1]

            if curr.is_bullish and next_candle.is_bearish and curr.close > next_candle.open:
                ob = OrderBlock(
                    index=i,
                    direction='bullish',
                    start_index=i,
                    end_index=i,
                    high=curr.high,
                    low=curr.low,
                    quality=self._assess_ob_quality(curr, 'bullish')
                )
                self.order_blocks.append(ob)

            elif curr.is_bearish and next_candle.is_bullish and curr.close < next_candle.open:
                ob = OrderBlock(
                    index=i,
                    direction='bearish',
                    start_index=i,
                    end_index=i,
                    high=curr.high,
                    low=curr.low,
                    quality=self._assess_ob_quality(curr, 'bearish')
                )
                self.order_blocks.append(ob)

    def _assess_ob_quality(self, candle: Candle, direction: str) -> str:
        body_ratio = candle.body_size / candle.full_range if candle.full_range > 0 else 0

        if direction == 'bullish':
            lower_wick_ratio = candle.lower_wick / candle.full_range if candle.full_range > 0 else 0
            if lower_wick_ratio > 0.6 and body_ratio < 0.3:
                return 'high'
            elif lower_wick_ratio > 0.4 and body_ratio < 0.5:
                return 'normal'
            else:
                return 'low'
        else:
            upper_wick_ratio = candle.upper_wick / candle.full_range if candle.full_range > 0 else 0
            if upper_wick_ratio > 0.6 and body_ratio < 0.3:
                return 'high'
            elif upper_wick_ratio > 0.4 and body_ratio < 0.5:
                return 'normal'
            else:
                return 'low'

    def _detect_liquidity_sweeps(self):
        if len(self.swing_points) < 2:
            return

        highs = [sp for sp in self.swing_points if sp.type == 'high']
        lows = [sp for sp in self.swing_points if sp.type == 'low']
        threshold = self.config.get('liquidity_sweep_threshold', 0.001)

        for i, high in enumerate(highs[:-1]):
            next_highs = [h for h in highs[i + 1:] if h.index > high.index]
            if not next_highs:
                continue
            next_high = next_highs[0]

            if next_high.price > high.price * (1 + threshold):
                sweep = LiquiditySweep(
                    index=next_high.index,
                    sweep_type='B',
                    price=next_high.price,
                    target_swing=high,
                    triggered=True
                )
                self.liquidity_sweeps.append(sweep)

        for i, low in enumerate(lows[:-1]):
            next_lows = [l for l in lows[i + 1:] if l.index > low.index]
            if not next_lows:
                continue
            next_low = next_lows[0]

            if next_low.price < low.price * (1 - threshold):
                sweep = LiquiditySweep(
                    index=next_low.index,
                    sweep_type='SSS',
                    price=next_low.price,
                    target_swing=low,
                    triggered=True
                )
                self.liquidity_sweeps.append(sweep)

    def detect_last_candle_before_bos(self, direction: str = 'bullish') -> Optional[int]:
        if not self.bos_list:
            return None

        relevant_bos = [b for b in self.bos_list if b.direction == direction]
        if not relevant_bos:
            return None

        last_bos = relevant_bos[-1]
        prev_swing_index = last_bos.prev_swing.index

        if prev_swing_index > 0:
            return prev_swing_index - 1
        return None

    def get_fib_zone(self, price: float, high: float, low: float) -> str:
        range_val = high - low
        if range_val <= 0:
            return 'NEUTRAL'

        equilibrium = low + range_val * 0.5

        if price > equilibrium:
            return 'PREMIUM'
        elif price < equilibrium:
            return 'DISCOUNT'
        else:
            return 'NEUTRAL'

    def get_ce_level(self, fvg: FVG) -> Optional[float]:
        if fvg.direction == 'bullish':
            return fvg.low + (fvg.high - fvg.low) * 0.79
        else:
            return fvg.high - (fvg.high - fvg.low) * 0.79

    def generate_trade_signal(self, direction: str = 'long') -> Optional[TradeSignal]:
        if len(self.candles) < 10:
            return None

        last_candle = self.candles[-1]
        current_price = last_candle.close
        high_20 = max(c.high for c in self.candles[-20:])
        low_20 = min(c.low for c in self.candles[-20:])
        high_50 = max(c.high for c in self.candles[-50:]) if len(self.candles) >= 50 else high_20
        low_50 = min(c.low for c in self.candles[-50:]) if len(self.candles) >= 50 else low_20

        zone = self.get_fib_zone(current_price, high_20, low_20)
        triggers = []
        confluence_score = 0
        entry_type = 'market'
        relevant_ob = None
        conf_cfg = self.config.get('confluence_scoring', {}) if self.config else {}

        if direction == 'long':
            bullish_obs = [ob for ob in self.order_blocks if ob.direction == 'bullish']
            if bullish_obs:
                relevant_ob = max(bullish_obs, key=lambda x: x.high)
                obs_score = conf_cfg.get('order_block_high', 25) if relevant_ob.quality == 'high' else \
                            conf_cfg.get('order_block_normal', 15) if relevant_ob.quality == 'normal' else 5
                confluence_score += obs_score
                triggers.append(f'Bullish OB at {relevant_ob.high:.2f}')
        else:
            bearish_obs = [ob for ob in self.order_blocks if ob.direction == 'bearish']
            if bearish_obs:
                relevant_ob = min(bearish_obs, key=lambda x: x.low)
                obs_score = conf_cfg.get('order_block_high', 25) if relevant_ob.quality == 'high' else \
                            conf_cfg.get('order_block_normal', 15) if relevant_ob.quality == 'normal' else 5
                confluence_score += obs_score
                triggers.append(f'Bearish OB at {relevant_ob.low:.2f}')

        relevant_fvg = None
        ifvg_active = False
        if direction == 'long':
            bullish_fvgs = [f for f in self.fvg_list if f.direction == 'bullish']
            if bullish_fvgs:
                relevant_fvg = bullish_fvgs[-1]
                confluence_score += conf_cfg.get('bullish_fvg', 20)
                triggers.append(f'Bullish FVG at {relevant_fvg.mid:.2f}')
                if relevant_fvg.filled:
                    ifvg_active = True
                    confluence_score += conf_cfg.get('ifvg', 30)
                    triggers.append('IFVG Confirmed - Strong Entry')
        else:
            bearish_fvgs = [f for f in self.fvg_list if f.direction == 'bearish']
            if bearish_fvgs:
                relevant_fvg = bearish_fvgs[-1]
                confluence_score += conf_cfg.get('bearish_fvg', 20)
                triggers.append(f'Bearish FVG at {relevant_fvg.mid:.2f}')
                if relevant_fvg.filled:
                    ifvg_active = True
                    confluence_score += conf_cfg.get('ifvg', 30)
                    triggers.append('IFVG Confirmed - Strong Entry')

        if zone == 'DISCOUNT':
            confluence_score += conf_cfg.get('discount_zone', 30)
            triggers.append('Discount Zone - Long Bias')
        elif zone == 'PREMIUM':
            confluence_score += conf_cfg.get('premium_zone', 10)
            triggers.append('Premium Zone - Short Bias')

        if self.mss_active and self.mss_direction == direction:
            confluence_score += conf_cfg.get('mss', 25)
            triggers.append('MSS Confirmed - Market Structure Shift')

        if self.choch_list:
            last_choch = self.choch_list[-1]
            if last_choch.direction == direction:
                confluence_score += conf_cfg.get('choch', 25)
                triggers.append(f'CHoCH {direction.upper()} - Trend Change Confirmed')

        if self.liquidity_sweeps:
            confluence_score += conf_cfg.get('liquidity_sweep', 25)
            triggers.append('Liquidity Sweep Detected')

        if direction == 'long' and current_price > high_20:
            confluence_score += conf_cfg.get('bos', 20)
            triggers.append('HTF Bullish BOS')
        elif direction == 'short' and current_price < low_20:
            confluence_score += conf_cfg.get('bos', 20)
            triggers.append('HTF Bearish BOS')

        if direction == 'long':
            entry_price = last_candle.close
            if relevant_fvg and relevant_fvg.low < entry_price:
                stop_loss = relevant_fvg.low * 0.998
            elif relevant_ob and relevant_ob.low < entry_price:
                stop_loss = relevant_ob.low * 0.998
            else:
                stop_loss = low_20 * 0.995
            risk = entry_price - stop_loss
            if risk <= 0:
                stop_loss = low_20 * 0.995
                risk = entry_price - stop_loss
            take_profit_1 = entry_price + risk * 2.0
            take_profit_2 = entry_price + risk * 3.0
            take_profit_3 = entry_price + risk * 5.0
        else:
            entry_price = last_candle.close
            if relevant_fvg and relevant_fvg.high > entry_price:
                stop_loss = relevant_fvg.high * 1.002
            elif relevant_ob and relevant_ob.high > entry_price:
                stop_loss = relevant_ob.high * 1.002
            else:
                stop_loss = high_20 * 1.005
            risk = stop_loss - entry_price
            if risk <= 0:
                stop_loss = high_20 * 1.005
                risk = stop_loss - entry_price
            take_profit_1 = entry_price - risk * 2.0
            take_profit_2 = entry_price - risk * 3.0
            take_profit_3 = entry_price - risk * 5.0

        confidence = min(100, confluence_score)
        if confidence < 40:
            return None

        rr1, rr2, rr3 = 2.0, 3.0, 5.0
        ob_ref = f"Bullish OB at {relevant_ob.high:.2f}" if (direction == 'long' and relevant_ob) else \
                 f"Bearish OB at {relevant_ob.low:.2f}" if (direction == 'short' and relevant_ob) else None
        fvg_ref = f"FVG at {relevant_fvg.mid:.2f}" if relevant_fvg else None
        notes = f"{direction.upper()} | R:R 1:{rr1}/1:{rr2}/1:{rr3} | "
        notes += f"IFVG " if ifvg_active else ""
        notes += f"Confluence {confluence_score}"

        return TradeSignal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            risk_reward_1=rr1,
            risk_reward_2=rr2,
            risk_reward_3=rr3,
            confidence=confidence,
            triggers=triggers,
            confluence_score=confluence_score,
            zone=zone,
            ob_reference=ob_ref,
            fvg_reference=fvg_ref,
            liquidity_sweep=str(self.liquidity_sweeps[-1].sweep_type) if self.liquidity_sweeps else None,
            entry_type=entry_type,
            notes=notes
        )

    def get_summary(self) -> Dict[str, Any]:
        return {
            'swing_points': len(self.swing_points),
            'bos_count': len(self.bos_list),
            'bullish_bos': len([b for b in self.bos_list if b.direction == 'bullish']),
            'bearish_bos': len([b for b in self.bos_list if b.direction == 'bearish']),
            'choch_count': len(self.choch_list),
            'mss_active': self.mss_active,
            'mss_direction': self.mss_direction,
            'fvg_count': len(self.fvg_list),
            'bullish_fvg': len([f for f in self.fvg_list if f.direction == 'bullish']),
            'bearish_fvg': len([f for f in self.fvg_list if f.direction == 'bearish']),
            'order_blocks': len(self.order_blocks),
            'bullish_ob': len([ob for ob in self.order_blocks if ob.direction == 'bullish']),
            'bearish_ob': len([ob for ob in self.order_blocks if ob.direction == 'bearish']),
            'liquidity_sweeps': len(self.liquidity_sweeps),
            'long_signal': self.generate_trade_signal('long'),
            'short_signal': self.generate_trade_signal('short'),
        }


def analyze_stock_ict(ticker: str, lookback: int = 50, config: Optional[Dict] = None) -> Dict[str, Any]:
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{lookback}d", auto_adjust=True)

        if len(hist) < 20:
            return {'error': 'Insufficient data'}

        candles = [
            Candle(
                open=row['Open'],
                high=row['High'],
                low=row['Low'],
                close=row['Close'],
                volume=row['Volume']
            )
            for _, row in hist.iterrows()
        ]

        analyzer = ICTSMCAnalyzer(candles, config)
        summary = analyzer.get_summary()

        last_candle = candles[-1]
        summary['current_price'] = last_candle.close
        summary['ticker'] = ticker
        summary['candle_count'] = len(candles)

        return summary

    except Exception as e:
        return {'error': str(e)}


if __name__ == '__main__':
    print("ICT/SMC Analyzer v1.0")
    print("=" * 50)

    sample_candles = [
        Candle(open=100, high=105, low=99, close=104, volume=1000000),
        Candle(open=104, high=106, low=103, close=105, volume=1100000),
        Candle(open=105, high=108, low=104, close=107, volume=1200000),
        Candle(open=107, high=110, low=106, close=109, volume=1300000),
        Candle(open=109, high=112, low=108, close=108, volume=1400000),
    ]

    for i, c in enumerate(sample_candles):
        print(f"Candle {i}: O={c.open} H={c.high} L={c.low} C={c.close} Bullish={c.is_bullish}")

    analyzer = ICTSMCAnalyzer(sample_candles)
    print(f"\nSwing Points: {len(analyzer.swing_points)}")
    print(f"BOS Count: {len(analyzer.bos_list)}")
    print(f"FVG Count: {len(analyzer.fvg_list)}")
    print(f"Order Blocks: {len(analyzer.order_blocks)}")

    long_signal = analyzer.generate_trade_signal('long')
    if long_signal:
        print(f"\nLong Signal:")
        print(f"  Entry: {long_signal.entry_price}")
        print(f"  Stop Loss: {long_signal.stop_loss}")
        print(f"  TP1: {long_signal.take_profit_1} (R:R = 1:{long_signal.risk_reward_1})")
        print(f"  TP2: {long_signal.take_profit_2} (R:R = 1:{long_signal.risk_reward_2})")
        print(f"  Zone: {long_signal.zone}")
        print(f"  Confluence: {long_signal.confluence_score}")
        print(f"  Triggers: {', '.join(long_signal.triggers)}")