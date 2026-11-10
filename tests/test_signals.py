import unittest
from datetime import datetime, timedelta

from jc.analysis.signals import analyze_match, late_shift, open_move, steady_drop
from jc.models import Odds3Way

BASE = datetime(2026, 10, 31, 20, 30, 0)   # 假想开赛时间


def snap(ts: datetime, win: float, draw: float = 3.5, lose: float = 2.1) -> Odds3Way:
    return Odds3Way(match_id="m1", ts=ts, win=win, draw=draw, lose=lose)


def hist_desc(n: int, end: float, step: float, hours: float = 2.0) -> list[Odds3Way]:
    """按时间升序的 n 个快照，赔率从 end+step*(n-1) 单调降到 end。"""
    return [snap(BASE - timedelta(hours=hours * i), end + step * i)
            for i in range(n - 1, -1, -1)]


class TestOpenMove(unittest.TestCase):
    def test_flat_no_signal(self):
        h = [snap(BASE - timedelta(hours=4), 2.65), snap(BASE, 2.65)]
        self.assertEqual(open_move(h), [])

    def test_big_drop_signals(self):
        h = [snap(BASE - timedelta(hours=4), 2.65), snap(BASE, 2.10)]
        sigs = open_move(h)
        self.assertEqual(len(sigs), 1)
        s = sigs[0]
        self.assertEqual((s.kind, s.side), ("open_move", "win"))
        self.assertGreaterEqual(s.strength, 0.9)
        self.assertIn("走低", s.detail)

    def test_small_move_below_threshold(self):
        h = [snap(BASE - timedelta(hours=4), 2.65), snap(BASE, 2.64)]
        self.assertEqual(open_move(h), [])

    def test_needs_two_snapshots(self):
        self.assertEqual(open_move([snap(BASE, 2.65)]), [])


class TestSteadyDrop(unittest.TestCase):
    def test_monotonic_drop(self):
        h = hist_desc(4, 2.20, 0.15)   # 时间升序 2.65→2.50→2.35→2.20，累计 -17%
        sigs = steady_drop(h)
        self.assertTrue(any(s.kind == "steady_drop" and s.side == "win" for s in sigs))

    def test_non_monotonic_no_signal(self):
        h = [snap(BASE - timedelta(hours=6), 2.65),
             snap(BASE - timedelta(hours=4), 2.50),
             snap(BASE - timedelta(hours=2), 2.60),
             snap(BASE, 2.40)]
        self.assertFalse(any(s.side == "win" for s in steady_drop(h)))

    def test_needs_three_snapshots(self):
        h = [snap(BASE - timedelta(hours=4), 2.65), snap(BASE, 2.10)]
        self.assertFalse(any(s.side == "win" for s in steady_drop(h)))


class TestLateShift(unittest.TestCase):
    def test_shift_inside_window(self):
        h = [snap(BASE - timedelta(hours=2.5), 2.65), snap(BASE - timedelta(hours=1), 2.30)]
        sigs = late_shift(h, BASE)
        self.assertTrue(any(s.kind == "late_shift" and s.side == "win" for s in sigs))

    def test_shift_outside_window(self):
        h = [snap(BASE - timedelta(hours=6), 2.65), snap(BASE - timedelta(hours=4), 2.30),
             snap(BASE - timedelta(hours=1), 2.30)]
        sigs = late_shift(h, BASE)
        self.assertFalse(any(s.kind == "late_shift" for s in sigs))

    def test_small_late_change_no_signal(self):
        h = [snap(BASE - timedelta(hours=2), 2.65), snap(BASE - timedelta(hours=1), 2.63)]
        self.assertFalse(any(s.kind == "late_shift" for s in late_shift(h, BASE)))


class TestAnalyzeMatch(unittest.TestCase):
    def test_sorted_by_strength(self):
        h = [snap(BASE - timedelta(hours=6), 2.65, 3.5, 2.1),
             snap(BASE - timedelta(hours=3), 2.50, 3.5, 2.1),
             snap(BASE - timedelta(hours=1), 2.10, 3.5, 2.1)]
        sigs = analyze_match(h, BASE)
        self.assertTrue(all(a.strength >= b.strength for a, b in zip(sigs, sigs[1:])))


if __name__ == "__main__":
    unittest.main()
