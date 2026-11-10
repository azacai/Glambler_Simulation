import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from jc.models import Match, MatchResult, Odds3Way
from jc.storage.db import DB


def make_match(match_id="m1", league="英超", status="Selling",
               match_time="2026-10-31T20:30:00") -> Match:
    return Match(
        match_id=match_id, match_num="周六006", league=league, league_id=25,
        home="切尔西", away="曼联", home_rank=4, away_rank=7,
        match_time=datetime.fromisoformat(match_time),
        single_sellable=True, status=status,
    )


def make_odds(match_id="m1", ts="2026-10-30T11:00:00") -> Odds3Way:
    return Odds3Way(match_id=match_id, ts=datetime.fromisoformat(ts),
                    win=1.71, draw=3.62, lose=3.60, goal_line="-1",
                    hhad_win=3.10, hhad_draw=4.10, hhad_lose=1.75)


class TestDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_schema_idempotent(self):
        db2 = DB(Path(self.tmp.name) / "t.db")   # 二次打开不报错
        db2.close()

    def test_upsert_insert_and_update(self):
        m = make_match()
        self.db.upsert_match(m)
        self.assertIsNone(self.db.get_match("m2"))
        got = self.db.get_match("m1")
        self.assertEqual((got.home, got.status, got.home_rank), ("切尔西", "Selling", 4))

        m.status = "Finished"
        self.db.upsert_match(m)
        self.assertEqual(self.db.get_match("m1").status, "Finished")

    def test_add_odds_idempotent(self):
        self.assertEqual(self.db.add_odds(make_odds()), 1)
        self.assertEqual(self.db.add_odds(make_odds()), 0)   # 同 (match_id, ts) 去重

        o2 = make_odds(ts="2026-10-30T13:00:00")
        o2.win = 1.66
        self.assertEqual(self.db.add_odds(o2), 1)
        self.assertEqual(self.db.snapshot_count("m1"), 2)

    def test_odds_history_ordered(self):
        self.db.add_odds(make_odds(ts="2026-10-30T13:00:00"))
        self.db.add_odds(make_odds(ts="2026-10-30T11:00:00"))
        hist = self.db.get_odds_history("m1")
        self.assertEqual([o.ts.hour for o in hist], [11, 13])
        self.assertEqual(self.db.latest_odds("m1").win, 1.71)

    def test_get_matches_filters(self):
        self.db.upsert_match(make_match("m1", "英超", "Selling"))
        self.db.upsert_match(make_match("m2", "荷甲", "Selling"))
        self.db.upsert_match(make_match("m3", "法甲", "Finished",
                                        match_time="2026-11-01T03:00:00"))
        self.assertEqual(len(self.db.get_matches()), 3)
        self.assertEqual(len(self.db.get_matches(leagues=["英超"])), 1)
        self.assertEqual(len(self.db.get_matches(dates=["2026-10-31"])), 2)
        self.assertEqual(len(self.db.get_matches(status="Selling")), 2)

    def test_save_match_result(self):
        self.db.save_match_result(MatchResult("m1", "2:1", "W"))
        self.db.save_match_result(MatchResult("m1", "2:2", "D"))   # upsert 覆盖
        row = self.db.conn.execute("SELECT score,outcome FROM match_results").fetchone()
        self.assertEqual(tuple(row), ("2:2", "D"))

    def test_backup_to_is_consistent_copy(self):
        self.db.upsert_match(make_match())
        self.db.add_odds(make_odds())
        dest = Path(self.tmp.name) / "bk" / "copy.db"
        self.db.backup_to(dest)
        copy = DB(dest)
        try:
            self.assertIsNotNone(copy.get_match("m1"))
            self.assertEqual(copy.snapshot_count("m1"), 1)
        finally:
            copy.close()
        # 源库在备份后仍可正常写入（在线备份不锁库）
        self.assertEqual(self.db.add_odds(make_odds(ts="2026-10-30T15:00:00")), 1)


if __name__ == "__main__":
    unittest.main()
