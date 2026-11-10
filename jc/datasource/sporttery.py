"""sporttery 官方接口适配器：解析完全由 spec 驱动。

代码内的转换只有"领域归一化"（字符串赔率→float、'[英超2]'→2、
日期+时间→datetime），这些与接口端点无关，不随接口变更。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import config
from ..models import Match, Odds3Way
from . import specio
from .specio import SpecError

_RANK_RE = re.compile(r"(\d+)")


@dataclass
class FetchResult:
    matches: list[Match] = field(default_factory=list)
    odds: dict[str, Odds3Way] = field(default_factory=dict)   # match_id -> 最新赔率
    last_update: str | None = None                             # 官方 lastUpdateTime
    spec_version: int = 0
    source: str = "sporttery_on_sale"


def _norm_rank(raw) -> int | None:
    """'[英超2]' -> 2；空/无数字 -> None。"""
    if raw is None:
        return None
    m = _RANK_RE.search(str(raw))
    return int(m.group(1)) if m else None


def _to_float(raw) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _to_datetime(date_str, clock_str) -> datetime | None:
    if not date_str or not clock_str:
        return None
    try:
        return datetime.strptime(f"{date_str} {clock_str}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _pick_single(match_raw: dict, single_spec: dict) -> bool | None:
    entries = specio.resolve_list(match_raw, single_spec.get("list_path", ""))
    where = single_spec.get("where", {})
    field_name = single_spec.get("field", "single")
    for e in entries:
        if isinstance(e, dict) and all(e.get(k) == v for k, v in where.items()):
            v = e.get(field_name)
            if v is None:
                return None
            return str(v) in ("1", "True", "true", "Y")
    return None


class SportteryClient:
    def __init__(self, fixture: Path | str | None = None, save_raw: bool = True):
        """fixture 提供时走离线模式（测试/调试），不触网。"""
        self.spec = specio.load_spec("sporttery_on_sale")
        self.fixture = Path(fixture) if fixture else None
        self.save_raw = save_raw

    # ---- 报文获取 ----
    def _payload(self) -> dict:
        if self.fixture is not None:
            return json.loads(self.fixture.read_text(encoding="utf-8"))
        req = self.spec["request"]
        payload = specio.http_get_json(
            req["url"], params=req.get("params"), extra_headers=req.get("headers")
        )
        if self.save_raw:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            (config.DATA_DIR / "last_onsale.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        return payload

    # ---- 解析 ----
    def fetch_on_sale(self) -> FetchResult:
        payload = self._payload()
        specio.check_success(payload, self.spec)

        result = FetchResult(
            last_update=specio.resolve(payload, "value.lastUpdateTime"),
            spec_version=self.spec.get("spec_version", 0),
        )
        fmap = self.spec["field_map"]
        days = specio.resolve_list(payload, self.spec["days_path"])
        problems: list[str] = []

        for day in days:
            for raw in specio.resolve_list(day, self.spec["matches_path"]):
                if not isinstance(raw, dict):
                    continue
                vals = {k: specio.resolve(raw, src) for k, src in fmap.items()}
                missing = [k for k in self.spec["required_fields"] if vals.get(k) in (None, "")]
                if missing:
                    problems.append(f"字段缺失{missing}: {raw.get('matchNumStr', '?')}")
                    continue
                mt = _to_datetime(vals["match_date"], vals["match_clock"])
                if mt is None:
                    problems.append(f"时间无法解析: {vals['match_date']} {vals['match_clock']}")
                    continue
                m = Match(
                    match_id=str(vals["match_id"]),
                    match_num=str(vals["match_num"]),
                    league=str(vals["league"]),
                    league_id=vals["league_id"],
                    home=str(vals["home"]),
                    away=str(vals["away"]),
                    home_rank=_norm_rank(vals["home_rank"]),
                    away_rank=_norm_rank(vals["away_rank"]),
                    match_time=mt,
                    single_sellable=_pick_single(raw, self.spec.get("single", {})),
                    status=str(vals["status"]),
                )
                result.matches.append(m)
                odds = self._parse_odds(m.match_id, raw)
                if odds is not None:
                    result.odds[m.match_id] = odds

        if problems:
            # 记录但不中断：个别场次字段缺失不应拖垮整批采集
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            (config.DATA_DIR / "last_parse_problems.txt").write_text(
                "\n".join(problems), encoding="utf-8"
            )
        return result

    def _parse_odds(self, match_id: str, raw: dict) -> Odds3Way | None:
        had = self.spec["had"]
        win = _to_float(specio.resolve(raw, had["win"]))
        draw = _to_float(specio.resolve(raw, had["draw"]))
        lose = _to_float(specio.resolve(raw, had["lose"]))
        if win is None or draw is None or lose is None:
            return None  # 该场暂无胜平负赔率（池未开/已关）

        # 快照时间戳优先用官方"最后调整时间"，轨迹时点精度不受轮询间隔限制
        ts = _to_datetime(
            specio.resolve(raw, had["update_date"]),
            specio.resolve(raw, had["update_time"]),
        ) or datetime.now()

        hhad = self.spec.get("hhad", {})
        return Odds3Way(
            match_id=match_id,
            ts=ts,
            win=win,
            draw=draw,
            lose=lose,
            goal_line=specio.resolve(raw, hhad.get("goal_line", "")) or None,
            hhad_win=_to_float(specio.resolve(raw, hhad.get("win", ""))),
            hhad_draw=_to_float(specio.resolve(raw, hhad.get("draw", ""))),
            hhad_lose=_to_float(specio.resolve(raw, hhad.get("lose", ""))),
        )
