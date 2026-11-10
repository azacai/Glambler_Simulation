"""快照与过滤。"""

from __future__ import annotations

from ..models import Match
from .sporttery import FetchResult, SportteryClient


def filter_big_five(matches: list[Match], leagues: tuple[str, ...] | None = None) -> list[Match]:
    from .. import config

    leagues = leagues or config.BIG_FIVE
    return [m for m in matches if m.league in leagues]


def snapshot_once(client: SportteryClient, db) -> dict:
    """拉取在售场次 → 场次 upsert + 赔率快照追加（幂等）+ 信号落库。返回采集报告。"""
    from ..analysis.persist import persist_signals

    fetched: FetchResult = client.fetch_on_sale()
    now_iso = _now_iso()
    new_cnt, upd_cnt = 0, 0
    for m in fetched.matches:
        existed = db.get_match(m.match_id) is not None
        db.upsert_match(m)
        if existed:
            upd_cnt += 1
        else:
            new_cnt += 1

    odds_added = 0
    for odds in fetched.odds.values():
        odds_added += db.add_odds(odds)  # UNIQUE(match_id, ts) 去重

    signals_added = persist_signals(db)

    return {
        "fetched_matches": len(fetched.matches),
        "new_matches": new_cnt,
        "updated_matches": upd_cnt,
        "odds_snapshots_added": odds_added,
        "signals_added": signals_added,
        "official_last_update": fetched.last_update,
        "ran_at": now_iso,
    }


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")
