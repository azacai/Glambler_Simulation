import unittest
from datetime import datetime

from jc import config
from jc.datasource import specio
from jc.datasource.specio import SpecError
from jc.datasource.sporttery import SportteryClient

FIXTURE = config.TESTS_DIR / "fixtures" / "on_sale_sample.json"


class TestSpecIO(unittest.TestCase):
    def test_load_missing_spec_raises(self):
        with self.assertRaises(SpecError):
            specio.load_spec("no_such_source")

    def test_resolve_nested(self):
        obj = {"a": {"b": {"c": 7}}}
        self.assertEqual(specio.resolve(obj, "a.b.c"), 7)
        self.assertIsNone(specio.resolve(obj, "a.x.c"))

    def test_resolve_list_wildcard_flatten(self):
        obj = {"value": {"rows": [[{"id": 1}, {"id": 2}], [{"id": 3}]]}}
        items = specio.resolve_list(obj, "value.rows.*")
        self.assertEqual([i["id"] for i in items], [1, 2, 3])

    def test_check_success_rejects(self):
        spec = {"success_checks": [{"path": "success", "equals": True}]}
        with self.assertRaises(SpecError):
            specio.check_success({"success": False, "errorMessage": "x"}, spec)
        specio.check_success({"success": True}, spec)   # 不抛即通过


class TestParseOnSale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = SportteryClient(fixture=FIXTURE, save_raw=False)
        cls.result = cls.client.fetch_on_sale()

    def test_match_count_and_leagues(self):
        self.assertEqual(len(self.result.matches), 4)
        self.assertEqual({m.league for m in self.result.matches},
                         {"英超", "荷甲", "法甲", "葡超"})

    def test_field_normalization(self):
        m = next(x for x in self.result.matches if x.match_id == "2042401")
        self.assertEqual(m.match_num, "周六006")
        self.assertEqual(m.home, "切尔西")
        self.assertEqual(m.match_time, datetime(2026, 10, 31, 20, 30, 0))
        self.assertEqual((m.home_rank, m.away_rank), (4, 7))
        self.assertEqual(m.league_id, 25)
        self.assertTrue(m.single_sellable)

    def test_single_false_when_flag_zero(self):
        m = next(x for x in self.result.matches if x.match_id == "2042403")
        self.assertFalse(m.single_sellable)

    def test_odds_parsed_with_official_ts(self):
        o = self.result.odds["2042401"]
        self.assertAlmostEqual(o.win, 1.71)
        self.assertAlmostEqual(o.draw, 3.62)
        self.assertAlmostEqual(o.lose, 3.60)
        self.assertEqual(o.ts, datetime(2026, 10, 30, 11, 0, 0))
        self.assertEqual(o.goal_line, "-1")
        self.assertAlmostEqual(o.hhad_lose, 1.75)

    def test_match_without_odds_still_recorded(self):
        # 葡超场次 had 为空串 → 场次保留、赔率不产出
        self.assertIn("2042404", {m.match_id for m in self.result.matches})
        self.assertNotIn("2042404", self.result.odds)

    def test_official_last_update(self):
        self.assertEqual(self.result.last_update, "2026-10-30 14:29:57")


if __name__ == "__main__":
    unittest.main()
