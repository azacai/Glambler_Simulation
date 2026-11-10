"""智能采集调度（D5/D14，2026-11-02 确认）。

节奏：
- 基础：每 4 小时一次全量快照（已知场次的赔率轨迹采样）；
- 加密：任一在售场次开赛前 8 小时内 → 每 2 小时；
- 新场次发现：每 30 分钟巡检一次（同一个官方接口，但只写入新出现
  场次的场次信息与初赔；已知场次的赔率轨迹仍按基础/加密节奏采样），
  专门对付"临开售才挂出"的比赛（体彩开售时间不保证提前）。

调度状态（上次全量快照时间）持久化在 SQLite collector_state 表：
计划任务每 30 分钟调用一次 `python -m jc autopoll` 即可，断电重启不丢状态。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import config
from .sporttery import SportteryClient

KEY_LAST_FULL = "last_full_snapshot"


def full_interval_min(db, now: datetime | None = None) -> int:
    """当前应采用的全量节奏：有场次进入开赛前 8h 窗口则加密。"""
    now = now or datetime.now()
    for m in db.get_matches(status="Selling"):
        delta = m.match_time - now
        # 已开赛但状态未刷新的场次不触发加密
        if timedelta(0) <= delta <= timedelta(hours=config.ACCEL_WINDOW_H):
            return config.ACCEL_INTERVAL_MIN
    return config.BASE_INTERVAL_MIN


def minutes_until_full_due(db, now: datetime | None = None) -> float:
    """距下次全量快照还有多少分钟（0 = 立即应做）。"""
    now = now or datetime.now()
    last = db.get_state_dt(KEY_LAST_FULL)
    if last is None:
        return 0.0
    interval = timedelta(minutes=full_interval_min(db, now))
    remaining = interval - (now - last)
    return max(0.0, remaining.total_seconds() / 60.0)


def autopoll_once(client: SportteryClient, db, now: datetime | None = None) -> dict:
    """一次智能采集周期：一次接口调用同时完成发现与（到期的）全量。

    - 全量模式：所有场次 upsert + 所有最新赔率入库（官方时间戳幂等去重）；
    - 发现模式：只入库新出现的场次与其初赔，不动已知场次轨迹。
    """
    now = now or datetime.now()
    fetched = client.fetch_on_sale()
    known = db.match_ids()
    new_matches = [m for m in fetched.matches if m.match_id not in known]

    # 宽限：计划任务启动时刻有秒级抖动，若严格按 <=0 判定，本轮比上次全量
    # 早几秒启动就会差一口气错过，全量被整体推迟一个巡检周期（4h 变 4.5h）
    due = minutes_until_full_due(db, now) <= config.FULL_DUE_GRACE_MIN

    if due:
        for m in fetched.matches:
            db.upsert_match(m)
        odds_added = sum(db.add_odds(o) for o in fetched.odds.values())
        db.set_state(KEY_LAST_FULL, now.isoformat(timespec="seconds"))
        mode = "full"
        from ..analysis.persist import persist_signals
        signals_added = persist_signals(db)
    else:
        new_ids = {m.match_id for m in new_matches}
        for m in new_matches:
            db.upsert_match(m)
        odds_added = sum(db.add_odds(o) for o in fetched.odds.values()
                         if o.match_id in new_ids)
        mode = "discovery"
        signals_added = 0   # 巡检不动已知场次轨迹，信号不可能变化

    return {
        "mode": mode,
        "interval_min": full_interval_min(db, now),
        "new_matches": new_matches,
        "odds_added": odds_added,
        "signals_added": signals_added,
        "next_full_in_min": round(minutes_until_full_due(db, now), 1),
        "ran_at": now.isoformat(timespec="seconds"),
    }
