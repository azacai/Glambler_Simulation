"""SQLite → CSV 导出。

编码用 utf-8-sig（带 BOM）：Windows Excel 双击打开中文不乱码。
默认导出"odds_full"宽表（赔率轨迹 JOIN 场次信息，人工分析最常用）
以及全部数据表；可用 --table 只导某一张。
"""

from __future__ import annotations

import csv
from pathlib import Path

TABLES = ("matches", "odds_snapshots", "match_results", "signals",
          "recommendations", "bet_outcomes", "collector_state")

VIEW_ODDS_FULL = """
SELECT o.match_id, m.match_num, m.league, m.home, m.away, m.match_time,
       o.ts, o.odds_win, o.odds_draw, o.odds_lose,
       o.goal_line, o.hhad_win, o.hhad_draw, o.hhad_lose
FROM odds_snapshots o
JOIN matches m ON m.match_id = o.match_id
ORDER BY m.match_time, o.ts
"""

DEFAULT_EXPORTS = ("odds_full",) + TABLES


def export_sql(db, sql: str, out_path: Path) -> int:
    """执行查询写 CSV，返回数据行数。"""
    cur = db.conn.execute(sql)
    cols = [d[0] for d in cur.description]
    n = 0
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for row in cur:
            writer.writerow(["" if v is None else v for v in row])
            n += 1
    return n


def export_tables(db, names: list[str] | None, out_dir: Path) -> list[tuple[str, int]]:
    """导出指定表（None=默认全部）到 out_dir，返回 [(文件路径, 行数)]。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = names or list(DEFAULT_EXPORTS)
    results: list[tuple[str, int]] = []
    for name in todo:
        if name == "odds_full":
            sql = VIEW_ODDS_FULL
        elif name in TABLES:
            sql = f"SELECT * FROM {name}"
        else:
            raise ValueError(f"未知表名: {name}（可选: {'/'.join(DEFAULT_EXPORTS)}）")
        path = out_dir / f"{name}.csv"
        results.append((str(path), export_sql(db, sql, path)))
    return results
