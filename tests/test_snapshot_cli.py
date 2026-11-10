import contextlib
import io
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from jc import config
from jc.cli import main
from jc.datasource.snapshot import snapshot_once
from jc.datasource.sporttery import SportteryClient
from jc.storage.db import DB

FIXTURE = config.TESTS_DIR / "fixtures" / "on_sale_sample.json"


class TestSnapshotPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _snap(self) -> dict:
        client = SportteryClient(fixture=FIXTURE, save_raw=False)
        return snapshot_once(client, self.db)

    def test_first_snapshot(self):
        report = self._snap()
        self.assertEqual(report["fetched_matches"], 4)
        self.assertEqual(report["new_matches"], 4)
        self.assertEqual(report["odds_snapshots_added"], 3)   # 葡超无赔率

    def test_repeat_snapshot_dedupes(self):
        self._snap()
        report = self._snap()
        self.assertEqual(report["new_matches"], 0)
        self.assertEqual(report["updated_matches"], 4)
        self.assertEqual(report["odds_snapshots_added"], 0)   # 官方时间戳未变 → 不重复入库
        self.assertEqual(self.db.snapshot_count("2042401"), 1)


class TestCli(unittest.TestCase):
    def setUp(self):
        # Windows 下 SQLite 文件句柄释放有延迟，清理失败不影响测试结论
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._patch = unittest.mock.patch.object(config, "DB_PATH",
                                                 Path(self.tmp.name) / "t.db")
        self._patch.start()
        db = DB(config.DB_PATH)
        client = SportteryClient(fixture=FIXTURE, save_raw=False)
        snapshot_once(client, db)
        db.close()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def _run(self, *argv) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_list_shows_matches(self):
        out = self._run("list", "--date", "all", "--all-leagues", "--all-status")
        self.assertIn("切尔西", out)
        self.assertIn("英超", out)
        self.assertIn("1.71", out)
        self.assertIn("单关", out)

    def test_list_default_filters_big_five(self):
        out = self._run("list", "--date", "all", "--all-status")
        self.assertIn("尼斯", out)        # 法甲
        self.assertNotIn("阿贾克斯", out)  # 荷甲被过滤

    def test_analyze_single_snapshot_notes_insufficient_history(self):
        out = self._run("analyze", "--date", "all", "--all-status")
        self.assertIn("切尔西", out)
        self.assertIn("快照不足", out)
        self.assertIn("去水概率", out)

    def test_autopoll_offline(self):
        out = self._run("autopoll", "--fixture", str(FIXTURE))
        self.assertIn("全量快照", out)          # 尚无调度状态 → 首轮必为全量
        self.assertIn("下次全量", out)

    def test_export_command(self):
        out_dir = Path(self.tmp.name) / "exports"
        out = self._run("export", "--table", "odds_full", "--out", str(out_dir))
        self.assertIn("导出完成", out)
        self.assertTrue((out_dir / "odds_full.csv").exists())

    def test_unknown_command_exits(self):
        with self.assertRaises(SystemExit):
            main(["no-such-command"])


if __name__ == "__main__":
    unittest.main()
