"""隐含概率与价值数学（纯函数，无 IO）。

赔率 o_i 的隐含概率 = 1/o_i；三向之和 > 1 的部分即抽水。
去水（devig）：按比例归一化。返奖率 = 1 / Σ(1/o_i)。
"""

from __future__ import annotations

from ..models import Prob3


def sum_inverse(win: float, draw: float, lose: float) -> float:
    return 1.0 / win + 1.0 / draw + 1.0 / lose


def payout_ratio(win: float, draw: float, lose: float) -> float:
    """该组赔率的返奖率（0~1），≈0.73 是竞彩常态。"""
    return 1.0 / sum_inverse(win, draw, lose)


def implied_probs(win: float, draw: float, lose: float) -> Prob3:
    return Prob3.make(1.0 / win, 1.0 / draw, 1.0 / lose)


def edge(prob: float, odds: float) -> float:
    """投注价值：p×o−1。>0 表示模型概率高于市场定价。"""
    return prob * odds - 1.0
