"""信号落库：对全部有轨迹的场次计算赔率信号并持久化（v0.2.2）。

幂等性：以"计算所基于的最新赔率快照时间戳(basis_ts)"为去重键——
同一轨迹状态下重复计算不产生新行；赔率再变后同类信号以新 basis_ts
留下演变记录（如 open_move 从 -20.8% 演进到 -23.5%）。
调用点：snapshot_once（手动全量）与 autopoll 全量轮，随采集自动积累。
"""

from __future__ import annotations

from ..models import Signal
from .signals import analyze_match


def persist_signals(db) -> int:
    """对所有快照数 ≥2 的场次计算信号并落库，返回本次新增条数。"""
    added = 0
    for m in db.get_matches():
        history = db.get_odds_history(m.match_id)
        if len(history) < 2:
            continue
        sigs: list[Signal] = analyze_match(history, m.match_time)
        if not sigs:
            continue
        basis = history[-1].ts.isoformat(timespec="seconds")
        for s in sigs:
            added += db.add_signal(m.match_id, s.kind, s.side,
                                   s.strength, s.detail, basis)
    return added
