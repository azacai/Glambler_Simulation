"""核心数据结构。只放数据，不放行为（除纯函数归一化）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Match:
    match_id: str                 # 官方 matchId（数字字符串，全局唯一主键）
    match_num: str                # 展示编号，如 "周五003"
    league: str                   # 联赛标准名（英超/西甲/意甲/德甲/法甲/...）
    league_id: int | None
    home: str
    away: str
    home_rank: int | None         # 解析自官方 '[英超2]' 格式
    away_rank: int | None
    match_time: datetime          # 开赛时间（本地=北京）
    single_sellable: bool | None  # 胜平负是否可单关；None=未知
    status: str                   # Selling / Finished / ...


@dataclass
class Odds3Way:
    """胜平负（不让球）赔率快照。ts 优先取官方最后调整时间。"""

    match_id: str
    ts: datetime
    win: float                    # 主胜
    draw: float
    lose: float                   # 客胜
    goal_line: str | None = None          # 让球数（存而不用）
    hhad_win: float | None = None         # 让球三向（存而不用）
    hhad_draw: float | None = None
    hhad_lose: float | None = None


@dataclass
class MatchResult:
    match_id: str
    score: str                    # "2:1"
    outcome: str                  # W / D / L（主队视角）
    league: str = ""
    match_num: str = ""


@dataclass
class Prob3:
    """归一化三向概率（Σ=1）。命名与 Odds3Way 对齐：win/draw/lose。"""

    win: float
    draw: float
    lose: float

    @classmethod
    def make(cls, win: float, draw: float, lose: float) -> "Prob3":
        total = win + draw + lose
        if total <= 0:
            raise ValueError("概率和必须为正")
        return cls(win / total, draw / total, lose / total)


@dataclass
class Signal:
    kind: str                     # open_move / steady_drop / late_shift
    side: str                     # win / draw / lose
    strength: float               # 0~1
    detail: str                   # 报告用的人话描述

    def __post_init__(self) -> None:
        self.strength = max(0.0, min(1.0, self.strength))


@dataclass
class Leg:
    """一条候选投注腿（v0.4 策略层使用）。"""

    match_id: str
    side: str                     # win / draw / lose
    odds: float
    market_prob: float            # 去水市场概率
    model_prob: float             # 融合后模型概率
    edge: float                   # model_prob * odds - 1
    signals: list[Signal] = field(default_factory=list)


@dataclass
class Bet:
    """一注结构（v0.4）。legs 数量即串关数：1=单场，N=N串1。"""

    legs: list[Leg]
    stake_bets: int               # 此组合几注


@dataclass
class Portfolio:
    """一套当日方案（v0.4）。"""

    name: str                     # 稳健 / 平衡 / 进取
    bets: list[Bet]
    total_bets: int
    hit_prob: float               # 全部命中的联合概率
    ev: float                     # 期望回报率（相对总投入）
    max_payout: float             # 全中奖金（元）
    ruin_prob: float              # 全损概率
    rationale: str
