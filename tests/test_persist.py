import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jc import config
from jc.analysis.persist import persist_signals
from jc.datasource.sporttery import SportteryClient
from jc.models import Odds3Way
from jc.storage.db import DB

FIXTURE = config.TESTS_DIR / "fixtures" / "on_sale_sample.json"


class TestPersistSignals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = DB(Path(self.tmp.name) / "t.db")
        client = SportteryClient(fixture=FIXTURE, save_raw=False)
        from jc.datasource.snapshot import snapshot_once
        snapshot_once(client, self.db)   # 每场 1 条快照 → 尚无信号

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _add_old_odds(self, win=2.30, hours_before=3.0):
        """在 2042401 现有快照(11:00, win=1.71)之前注入一条更早的快照。"""
        m = self.db.get_match("2042401")
        old_ts = datetime(2026, 10, 30, 11, 0, 0) - timedelta(hours=hours_before)
        self.db.add_odds(Odds3Way(match_id="2042401", ts=old_ts,
                                  win=win, draw=3.6, lose=3.4))
        return m

    def test_no_signal_with_single_snapshot(self):
        self.assertEqual(persist_signals(self.db), 0)
        self.assertEqual(self.db.count_signals(), 0)

    def test_persist_and_idempotent(self):
        self._add_old_odds()                    # 2.30 → 1.71，跌幅 -25.7%
        first = persist_signals(self.db)
        self.assertGreaterEqual(first, 1)
        self.assertEqual(self.db.count_signals("2042401"), first)
        # 同一轨迹重复计算 → 零新增
        self.assertEqual(persist_signals(self.db), 0)
        self.assertEqual(self.db.count_signals("2042401"), first)

    def test_new_odds_evolution_adds_new_basis(self):
        self._add_old_odds()
        persist_signals(self.db)
        # 赔率再降：注入一条"更晚"的快照，信号以新 basis_ts 留演变记录
        self.db.add_odds(Odds3Way(match_id="2042401",
                                  ts=datetime(2026, 10, 30, 12, 0, 0),
                                  win=1.65, draw=3.7, lose=3.7))
        second = persist_signals(self.db)
        self.assertGreaterEqual(second, 1)      # basis 变化 → 新行
        row = self.db.conn.execute(
            "SELECT COUNT(*) c FROM signals WHERE match_id='2042401'"
            " AND kind='open_move' AND side='win'").fetchone()
        self.assertGreaterEqual(row["c"], 2)    # 两个 basis 版本共存

    def test_signal_fields(self):
        self._add_old_odds()
        persist_signals(self.db)
        r = self.db.conn.execute(
            "SELECT kind, side, strength, detail, basis_ts FROM signals"
            " WHERE match_id='2042401' AND kind='open_move' AND side='win'"
        ).fetchone()
        self.assertEqual((r["kind"], r["side"]), ("open_move", "win"))
        self.assertIn("走低", r["detail"])
        self.assertEqual(r["basis_ts"], "2026-10-30T11:00:00")


class TestSignalsMigration(unittest.TestCase):
    def test_legacy_signals_table_upgraded(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "legacy.db"
            import sqlite3
            raw = sqlite3.connect(str(p))       # 手工建 v0.2.1 老结构
            raw.execute(
                "CREATE TABLE signals(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " match_id TEXT NOT NULL, kind TEXT NOT NULL, side TEXT NOT NULL,"
                " strength REAL NOT NULL, detail TEXT NOT NULL, created_at TEXT)")
            raw.commit()
            raw.close()

            db = DB(p)                           # 打开即迁移
            cols = {r[1] for r in db.conn.execute("PRAGMA table_info(signals)")}
            self.assertIn("basis_ts", cols)
            # 新式写入在迁移后的库上可用且幂等
            self.assertEqual(db.add_signal("m", "open_move", "win", 0.5, "d", "t1"), 1)
            self.assertEqual(db.add_signal("m", "open_move", "win", 0.5, "d", "t1"), 0)
            db.close()


if __name__ == "__main__":
    unittest.main()
