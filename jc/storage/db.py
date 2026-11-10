"""SQLite 存储层。纯标准库 sqlite3，库文件单文件可携带。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ..models import Match, MatchResult, Odds3Way

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches(
    match_id TEXT PRIMARY KEY,
    match_num TEXT NOT NULL,
    league TEXT NOT NULL,
    league_id INTEGER,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    home_rank INTEGER,
    away_rank INTEGER,
    match_time TEXT NOT NULL,
    single_sellable INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_snapshots(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    odds_win REAL NOT NULL,
    odds_draw REAL NOT NULL,
    odds_lose REAL NOT NULL,
    goal_line TEXT,
    hhad_win REAL, hhad_draw REAL, hhad_lose REAL,
    UNIQUE(match_id, ts)
);

CREATE TABLE IF NOT EXISTS match_results(
    match_id TEXT PRIMARY KEY,
    score TEXT NOT NULL,
    outcome TEXT NOT NULL,
    settled_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    side TEXT NOT NULL,
    strength REAL NOT NULL,
    detail TEXT NOT NULL,
    basis_ts TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    style TEXT NOT NULL,
    portfolio_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bet_outcomes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
    match_id TEXT NOT NULL,
    legs_json TEXT NOT NULL,
    stake_bets INTEGER NOT NULL,
    result TEXT NOT NULL DEFAULT 'pending',
    payout REAL,
    settled_at TEXT
);

CREATE TABLE IF NOT EXISTS collector_state(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """轻量迁移：老库 signals 表缺 basis_ts 列/唯一索引时补齐（v0.2.2）。"""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(signals)")}
        if "basis_ts" not in cols:
            self.conn.execute("ALTER TABLE signals ADD COLUMN basis_ts TEXT")
            self.conn.execute(
                "UPDATE signals SET basis_ts=created_at WHERE basis_ts IS NULL")
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_signals "
            "ON signals(match_id, kind, side, basis_ts)")

    def close(self) -> None:
        self.conn.close()

    def backup_to(self, dest: Path | str) -> Path:
        """在线安全备份（sqlite backup API）：不锁库、不中断采集，得到一致性副本。"""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()
        return dest

    # ---------- 场次 ----------
    def upsert_match(self, m: Match) -> None:
        now = _now_iso()
        self.conn.execute(
            """
            INSERT INTO matches(match_id, match_num, league, league_id, home, away,
                                home_rank, away_rank, match_time, single_sellable,
                                status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(match_id) DO UPDATE SET
                match_num=excluded.match_num, league=excluded.league,
                league_id=excluded.league_id, home=excluded.home, away=excluded.away,
                home_rank=excluded.home_rank, away_rank=excluded.away_rank,
                match_time=excluded.match_time,
                single_sellable=excluded.single_sellable,
                status=excluded.status, updated_at=excluded.updated_at
            """,
            (m.match_id, m.match_num, m.league, m.league_id, m.home, m.away,
             m.home_rank, m.away_rank, m.match_time.isoformat(timespec="seconds"),
             None if m.single_sellable is None else int(m.single_sellable),
             m.status, now, now),
        )
        self.conn.commit()

    def _row_to_match(self, r: sqlite3.Row) -> Match:
        return Match(
            match_id=r["match_id"],
            match_num=r["match_num"],
            league=r["league"],
            league_id=r["league_id"],
            home=r["home"],
            away=r["away"],
            home_rank=r["home_rank"],
            away_rank=r["away_rank"],
            match_time=datetime.fromisoformat(r["match_time"]),
            single_sellable=None if r["single_sellable"] is None else bool(r["single_sellable"]),
            status=r["status"],
        )

    def get_match(self, match_id: str) -> Match | None:
        r = self.conn.execute(
            "SELECT * FROM matches WHERE match_id=?", (match_id,)).fetchone()
        return self._row_to_match(r) if r else None

    def get_matches(self, dates: list[str] | None = None, leagues: list[str] | None = None,
                    status: str | None = None) -> list[Match]:
        sql, args = "SELECT * FROM matches WHERE 1=1", []
        if dates:
            sql += f" AND substr(match_time,1,10) IN ({','.join('?' * len(dates))})"
            args += dates
        if leagues:
            sql += f" AND league IN ({','.join('?' * len(leagues))})"
            args += leagues
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY match_time, match_num"
        return [self._row_to_match(r) for r in self.conn.execute(sql, args)]

    def match_ids(self) -> set[str]:
        return {r["match_id"] for r in
                self.conn.execute("SELECT match_id FROM matches")}

    # ---------- 调度状态 ----------
    def get_state_dt(self, key: str) -> datetime | None:
        r = self.conn.execute(
            "SELECT value FROM collector_state WHERE key=?", (key,)).fetchone()
        if r is None:
            return None
        try:
            return datetime.fromisoformat(r["value"])
        except ValueError:
            return None

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO collector_state(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))
        self.conn.commit()

    # ---------- 赔率快照 ----------
    def add_odds(self, o: Odds3Way) -> int:
        """幂等追加（UNIQUE(match_id, ts)）；返回实际新增行数 0/1。"""
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO odds_snapshots(
                match_id, ts, odds_win, odds_draw, odds_lose,
                goal_line, hhad_win, hhad_draw, hhad_lose)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (o.match_id, o.ts.isoformat(timespec="seconds"), o.win, o.draw, o.lose,
             o.goal_line, o.hhad_win, o.hhad_draw, o.hhad_lose),
        )
        self.conn.commit()
        return cur.rowcount

    def _row_to_odds(self, r: sqlite3.Row) -> Odds3Way:
        return Odds3Way(
            match_id=r["match_id"],
            ts=datetime.fromisoformat(r["ts"]),
            win=r["odds_win"], draw=r["odds_draw"], lose=r["odds_lose"],
            goal_line=r["goal_line"],
            hhad_win=r["hhad_win"], hhad_draw=r["hhad_draw"], hhad_lose=r["hhad_lose"],
        )

    def get_odds_history(self, match_id: str) -> list[Odds3Way]:
        rows = self.conn.execute(
            "SELECT * FROM odds_snapshots WHERE match_id=? ORDER BY ts", (match_id,)
        ).fetchall()
        return [self._row_to_odds(r) for r in rows]

    def latest_odds(self, match_id: str) -> Odds3Way | None:
        r = self.conn.execute(
            "SELECT * FROM odds_snapshots WHERE match_id=? ORDER BY ts DESC LIMIT 1",
            (match_id,)).fetchone()
        return self._row_to_odds(r) if r else None

    def snapshot_count(self, match_id: str) -> int:
        r = self.conn.execute(
            "SELECT COUNT(*) AS c FROM odds_snapshots WHERE match_id=?",
            (match_id,)).fetchone()
        return int(r["c"])

    # ---------- 赛果（v0.2 启用）----------
    def save_match_result(self, r: MatchResult) -> None:
        self.conn.execute(
            """
            INSERT INTO match_results(match_id, score, outcome, settled_at)
            VALUES(?,?,?,?)
            ON CONFLICT(match_id) DO UPDATE SET
                score=excluded.score, outcome=excluded.outcome,
                settled_at=excluded.settled_at
            """,
            (r.match_id, r.score, r.outcome, _now_iso()),
        )
        self.conn.commit()

    # ---------- 信号 ----------
    def add_signal(self, match_id: str, kind: str, side: str,
                   strength: float, detail: str, basis_ts: str) -> int:
        """幂等追加（UNIQUE(match_id,kind,side,basis_ts)）；返回实际新增 0/1。

        basis_ts = 计算信号所依据的最新赔率快照时间戳：赔率再变时
        同类信号会以新 basis_ts 留下演变记录，重复计算不产生重复行。
        """
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO signals(match_id, kind, side, strength,"
            " detail, basis_ts, created_at) VALUES(?,?,?,?,?,?,?)",
            (match_id, kind, side, strength, detail, basis_ts, _now_iso()),
        )
        self.conn.commit()
        return cur.rowcount

    def count_signals(self, match_id: str | None = None) -> int:
        if match_id is None:
            r = self.conn.execute("SELECT COUNT(*) AS c FROM signals").fetchone()
        else:
            r = self.conn.execute(
                "SELECT COUNT(*) AS c FROM signals WHERE match_id=?",
                (match_id,)).fetchone()
        return int(r["c"])
