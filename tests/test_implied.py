import unittest

from jc.analysis.implied import edge, implied_probs, payout_ratio, sum_inverse
from jc.models import Prob3


class TestImplied(unittest.TestCase):
    def test_sum_inverse(self):
        self.assertAlmostEqual(sum_inverse(2.0, 4.0, 4.0), 1.0)

    def test_payout_ratio_in_range(self):
        pr = payout_ratio(2.55, 3.15, 2.33)
        self.assertAlmostEqual(pr, 1 / 1.138806, places=5)
        self.assertTrue(0 < pr < 1)

    def test_implied_probs_normalized(self):
        p = implied_probs(2.55, 3.15, 2.33)
        self.assertAlmostEqual(p.win + p.draw + p.lose, 1.0, places=9)

    def test_implied_probs_ordering(self):
        # 赔率越低概率越高
        p = implied_probs(1.5, 4.0, 6.0)
        self.assertGreater(p.win, p.draw)
        self.assertGreater(p.draw, p.lose)

    def test_edge_sign(self):
        self.assertAlmostEqual(edge(0.5, 2.2), 0.10)
        self.assertAlmostEqual(edge(0.4, 2.2), -0.12)

    def test_prob3_make_rejects_zero_sum(self):
        with self.assertRaises(ValueError):
            Prob3.make(0.0, 0.0, 0.0)


if __name__ == "__main__":
    unittest.main()
