import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jc import config
from jc.datasource.collector import (
    KEY_LAST_FULL,
    autopoll_once,
    full_interval_min,
    minutes_until_full_due,
)
from jc.datasource.sporttery import SportteryClient
from jc.storage.db import DB

FIXTURE = config.TESTS_DIR / "fixtures" / "on_sale_sample.json"
NOW = datetime(2026, 11, 2, 12, 0, 0)


def make_db() -> tuple[DB, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    return DB(Path(tmp.name) / "t.db"), tmp


def seed_match(db: DB, match_id: str, kickoff: datetime, status: str = "Selling"):
    """直接用 SQL 插入最小场次行，用于调度判定。"""
    db.conn.execute(
        "INSERT INTO matches(match_id, match_num, league, league_id, home, away,"
        " match_time, status, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (match_id, "周六001", "英超", 25, "A", "B",
         kickoff.isoformat(timespec="seconds"), status, NOW.isoformat(), NOW.isoformat()),
    )
    db.conn.commit()


class TestInterval(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = make_db()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_base_when_no_upcoming(self):
        seed_match(self.db, "m1", NOW + timedelta(hours=30))
        self.assertEqual(full_interval_min(self.db, NOW), config.BASE_INTERVAL_MIN)

    def test_accel_inside_8h_window(self):
        seed_match(self.db, "m1", NOW + timedelta(hours=5))
        self.assertEqual(full_interval_min(self.db, NOW), config.ACCEL_INTERVAL_MIN)

    def test_accel_at_window_edge(self):
        seed_match(self.db, "m1", NOW + timedelta(hours=config.ACCEL_WINDOW_H))
        self.assertEqual(full_interval_min(self.db, NOW), config.ACCEL_INTERVAL_MIN)

    def test_no_accel_for_already_kicked_off(self):
        # 已开赛但状态未刷新的场次不触发加密
        seed_match(self.db, "m1", NOW - timedelta(hours=1))
        self.assertEqual(full_interval_min(self.db, NOW), config.BASE_INTERVAL_MIN)

    def test_empty_db_uses_base(self):
        self.assertEqual(full_interval_min(self.db, NOW), config.BASE_INTERVAL_MIN)


class TestAutopoll(unittest.TestCase):
    def setUp(self):
        self.db, self.tmp = make_db()
        self.client = SportteryClient(fixture=FIXTURE, save_raw=False)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_first_run_is_full_and_discovers_all(self):
        r = autopoll_once(self.client, self.db, now=NOW)
        self.assertEqual(r["mode"], "full")
        self.assertEqual(len(r["new_matches"]), 4)
        self.assertEqual(r["odds_added"], 3)          # 葡超无赔率
        self.assertEqual(r["signals_added"], 0)       # 每场仅1条快照，无轨迹
        self.assertIsNotNone(self.db.get_state_dt(KEY_LAST_FULL))
        self.assertGreater(minutes_until_full_due(self.db, NOW), 0)

    def test_full_round_persists_signals(self):
        # 预置一场的早期快照，使全量轮后该场有 2 条轨迹 → 信号落库
        first = self.client.fetch_on_sale()
        m1 = next(m for m in first.matches if m.match_id == "2042401")
        self.db.upsert_match(m1)
        self.db.add_odds(first.odds["2042401"])
        from jc.models import Odds3Way
        self.db.add_odds(Odds3Way(match_id="2042401",
                                  ts=datetime(2026, 10, 30, 8, 0, 0),
                                  win=2.30, draw=3.6, lose=3.4))
        self.db.set_state(KEY_LAST_FULL,
                          (NOW - timedelta(hours=5)).isoformat())   # 已到期 → 全量
        r = autopoll_once(self.client, self.db, now=NOW)
        self.assertEqual(r["mode"], "full")
        self.assertGreaterEqual(r["signals_added"], 1)              # 2.30→1.71 大跌
        self.assertGreaterEqual(self.db.count_signals("2042401"), 1)

    def test_second_run_is_discovery_only(self):
        autopoll_once(self.client, self.db, now=NOW)
        r = autopoll_once(self.client, self.db, now=NOW + timedelta(minutes=10))
        self.assertEqual(r["mode"], "discovery")
        self.assertEqual(r["new_matches"], [])
        self.assertEqual(r["odds_added"], 0)
        # 已知场次的赔率轨迹不被巡检模式重复采样
        self.assertEqual(self.db.snapshot_count("2042401"), 1)

    def test_full_due_again_after_interval(self):
        autopoll_once(self.client, self.db, now=NOW)
        r = autopoll_once(self.client, self.db, now=NOW + timedelta(hours=4, minutes=1))
        self.assertEqual(r["mode"], "full")

    def test_start_jitter_does_not_skip_full(self):
        # 回归：本轮比上次全量早 1 秒启动，不应错过全量而推迟 30 分钟
        autopoll_once(self.client, self.db, now=NOW)
        r = autopoll_once(self.client, self.db,
                          now=NOW + timedelta(hours=4) - timedelta(seconds=1))
        self.assertEqual(r["mode"], "full")

    def test_well_before_due_stays_discovery(self):
        autopoll_once(self.client, self.db, now=NOW)
        r = autopoll_once(self.client, self.db,
                          now=NOW + timedelta(hours=3, minutes=30))
        self.assertEqual(r["mode"], "discovery")

    def test_discovery_catches_late_listed_match(self):
        # 模拟晚开售：库里先只有 1 场，随后官方挂出全部 4 场
        first = self.client.fetch_on_sale()
        m1 = next(m for m in first.matches if m.match_id == "2042401")
        self.db.upsert_match(m1)
        self.db.add_odds(first.odds["2042401"])
        self.db.set_state(KEY_LAST_FULL, (NOW - timedelta(hours=1)).isoformat())

        r = autopoll_once(self.client, self.db, now=NOW)
        self.assertEqual(r["mode"], "discovery")       # 未到全量周期
        self.assertEqual(len(r["new_matches"]), 3)
        self.assertEqual(r["odds_added"], 2)           # 新场次中2场有赔率
        self.assertEqual(self.db.snapshot_count("2042401"), 1)  # 老场次轨迹未被扰动

    def test_state_survives_reopen(self):
        autopoll_once(self.client, self.db, now=NOW)
        path = self.db.path
        self.db.close()
        db2 = DB(path)
        r = autopoll_once(self.client, db2, now=NOW + timedelta(minutes=5))
        self.assertEqual(r["mode"], "discovery")
        db2.close()


if __name__ == "__main__":
    unittest.main()
