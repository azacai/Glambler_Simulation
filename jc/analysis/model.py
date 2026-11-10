"""概率融合模型（v0.4 交付完整版；v2 将接入 xG 回归，见设计文档 D11）。

v0.1 占位契约：
    fuse_probabilities(base: Prob3, signals: list[Signal]) -> Prob3
规则（v0.4 实现）：赔率走低方向按信号强度上调概率、走高方向下调，
单方向累计修正 ≤ FUSE_MAX_ADJUST（默认 ±8 个百分点），修正后归一化。
"""

from __future__ import annotations

from ..models import Prob3, Signal


def fuse_probabilities(base: Prob3, signals: list[Signal]) -> Prob3:
    raise NotImplementedError("v0.4 交付")
