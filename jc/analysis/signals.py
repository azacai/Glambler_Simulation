"""赔率轨迹信号（v1）。输入为按 ts 升序的赔率历史。

约定：赔率下降 = 市场资金压向该方向（该方向被加强）；
赔率上升 = 市场撤离该方向。信号只陈述事实与幅度，不做因果断言。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import config
from ..models import Odds3Way, Signal

SIDES = ("win", "draw", "lose")
SIDE_CN = {"win": "主胜", "draw": "平局", "lose": "客胜"}


def _odds_of(o: Odds3Way, side: str) -> float:
    return getattr(o, side)


def _pct_change(first: float, last: float) -> float:
    """相对变化，下降为负。"""
    return (last - first) / first


def _strength(delta: float) -> float:
    """|Δ| 达到 SIGNAL_STRENGTH_FULL 记满强度 1.0。"""
    return min(abs(delta) / config.SIGNAL_STRENGTH_FULL, 1.0)


def _fmt(side: str, first: float, last: float, delta: float) -> str:
    arrow = "走低" if delta < 0 else "走高"
    return (f"{SIDE_CN[side]}赔率 {first:.2f}→{last:.2f} "
            f"({delta * 100:+.1f}%，{arrow})")


def _sorted(history: list[Odds3Way]) -> list[Odds3Way]:
    return sorted(history, key=lambda o: o.ts)


def open_move(history: list[Odds3Way]) -> list[Signal]:
    """初赔（首快照）→ 现赔（最新快照）净变动 ≥ 阈值。"""
    hist = _sorted(history)
    if len(hist) < 2:
        return []
    out: list[Signal] = []
    for side in SIDES:
        first, last = _odds_of(hist[0], side), _odds_of(hist[-1], side)
        delta = _pct_change(first, last)
        if abs(delta) >= config.SIGNAL_OPEN_MOVE:
            out.append(Signal("open_move", side, _strength(delta), _fmt(side, first, last, delta)))
    return out


def steady_drop(history: list[Odds3Way]) -> list[Signal]:
    """≥3 次快照单调走低且累计 ≥ 阈值：持续单向资金。"""
    hist = _sorted(history)
    if len(hist) < 3:
        return []
    out: list[Signal] = []
    for side in SIDES:
        seq = [_odds_of(o, side) for o in hist]
        if all(a > b for a, b in zip(seq, seq[1:])):
            delta = _pct_change(seq[0], seq[-1])
            if delta <= -config.SIGNAL_STEADY_DROP:
                out.append(Signal(
                    "steady_drop", side, _strength(delta),
                    f"{SIDE_CN[side]}赔率经{len(seq)}次快照单调走低 " + _fmt(side, seq[0], seq[-1], delta)))
    return out


def late_shift(history: list[Odds3Way], kickoff: datetime) -> list[Signal]:
    """开赛前 N 小时窗口内的相邻变动 ≥ 阈值：临场异动。"""
    hist = _sorted(history)
    if len(hist) < 2:
        return []
    cutoff = kickoff - timedelta(hours=config.SIGNAL_LATE_WINDOW_H)
    late = [o for o in hist if o.ts >= cutoff]
    if len(late) < 2:
        return []
    out: list[Signal] = []
    for side in SIDES:
        first, last = _odds_of(late[-2], side), _odds_of(late[-1], side)
        delta = _pct_change(first, last)
        if abs(delta) >= config.SIGNAL_LATE_SHIFT:
            out.append(Signal(
                "late_shift", side, _strength(delta),
                f"临场{config.SIGNAL_LATE_WINDOW_H:.0f}h内 " + _fmt(side, first, last, delta)))
    return out


def analyze_match(history: list[Odds3Way], kickoff: datetime) -> list[Signal]:
    sigs = open_move(history) + steady_drop(history) + late_shift(history, kickoff)
    return sorted(sigs, key=lambda s: -s.strength)
