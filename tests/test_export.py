import csv
import tempfile
import unittest
from pathlib import Path

from jc import config
from jc.datasource.snapshot import snapshot_once
from jc.datasource.sporttery import SportteryClient
from jc.storage.csv_export import TABLES, export_tables
from jc.storage.db import DB

FIXTURE = config.TESTS_DIR / "fixtures" / "on_sale_sample.json"


class TestExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = DB(Path(self.tmp.name) / "t.db")
        client = SportteryClient(fixture=FIXTURE, save_raw=False)
        snapshot_once(client, self.db)
        self.out = Path(self.tmp.name) / "csv"

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _read(self, name: str) -> list[list[str]]:
        with open(self.out / f"{name}.csv", encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    def test_export_all_tables(self):
        results = export_tables(self.db, None, self.out)
        self.assertEqual({Path(p).stem for p, _ in results},
                         {"odds_full", *TABLES})
        by_name = {Path(p).stem: n for p, n in results}
        self.assertEqual(by_name["matches"], 4)
        self.assertEqual(by_name["odds_snapshots"], 3)

    def test_odds_full_joins_match_info(self):
        export_tables(self.db, ["odds_full"], self.out)
        rows = self._read("odds_full")
        header, data = rows[0], rows[1:]
        self.assertEqual(len(data), 3)
        self.assertIn("league", header)
        joined = any("切尔西" in r and "1.71" in r for r in data)
        self.assertTrue(joined)

    def test_single_table_export(self):
        results = export_tables(self.db, ["matches"], self.out)
        self.assertEqual(results[0][1], 4)

    def test_unknown_table_rejected(self):
        with self.assertRaises(ValueError):
            export_tables(self.db, ["no_such_table"], self.out)

    def test_bom_for_excel(self):
        export_tables(self.db, ["matches"], self.out)
        raw = (self.out / "matches.csv").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))   # utf-8-sig BOM


if __name__ == "__main__":
    unittest.main()
