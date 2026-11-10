import unittest

from jc import config
from jc.datasource.snapshot import filter_big_five
from jc.datasource.sporttery import SportteryClient

FIXTURE = config.TESTS_DIR / "fixtures" / "on_sale_sample.json"


class TestBigFiveFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = SportteryClient(fixture=FIXTURE, save_raw=False).fetch_on_sale()
        cls.big_five = filter_big_five(cls.result.matches)

    def test_keeps_big_five_drops_others(self):
        leagues = {m.league for m in self.big_five}
        self.assertEqual(leagues, {"英超", "法甲"})     # fixture 中五大联赛只有这两场

    def test_custom_leagues(self):
        only_epl = filter_big_five(self.result.matches, leagues=("英超",))
        self.assertEqual([m.league for m in only_epl], ["英超"])

    def test_empty_input(self):
        self.assertEqual(filter_big_five([]), [])


if __name__ == "__main__":
    unittest.main()
