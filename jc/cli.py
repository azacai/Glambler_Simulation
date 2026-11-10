"""命令行入口：python -m jc <command>."""

from __future__ import annotations

import argparse
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

from . import __version__, config
from .datasource.snapshot import filter_big_five, snapshot_once
from .datasource.sporttery import SportteryClient
from .storage.db import DB


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _parse_dates(spec: str) -> list[str]:
    """'today,+1,+2' / 'all' / '2026-10-31,2026-11-01' → 日期串列表。+N=今天起第N天。"""
    today = date.today()
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip().lower()
        if part == "all":
            return []
        if part == "today":
            out.append(today.isoformat())
        elif part == "tomorrow":
            out.append((today + timedelta(days=1)).isoformat())
        elif part == "yesterday":
            out.append((today - timedelta(days=1)).isoformat())
        elif part.startswith("+") and part[1:].isdigit():
            out.append((today + timedelta(days=int(part[1:]))).isoformat())
        else:
            out.append(part)  # 原样作为 YYYY-MM-DD
    return out


def cmd_snapshot(args) -> int:
    client = SportteryClient(fixture=args.fixture)
    db = DB(config.DB_PATH)
    try:
        report = snapshot_once(client, db)
    finally:
        db.close()
    print(f"快照完成 @ {report['ran_at']}")
    print(f"  场次: 拉取 {report['fetched_matches']}"
          f"（新增 {report['new_matches']}，更新 {report['updated_matches']}）")
    print(f"  赔率: 新增快照 {report['odds_snapshots_added']} 条"
          f"（同时间戳自动去重）；新增信号 {report['signals_added']} 条")
    if report["official_last_update"]:
        print(f"  官方赔率最后更新时间: {report['official_last_update']}")
    return 0


def cmd_list(args) -> int:
    db = DB(config.DB_PATH)
    dates = _parse_dates(args.date)
    leagues = None if args.all_leagues else list(config.BIG_FIVE)
    matches = db.get_matches(dates=dates or None, leagues=leagues,
                             status=None if args.all_status else "Selling")
    if not matches:
        db.close()
        print("（无匹配场次；试试 --all-leagues / --all-status / --date all）")
        return 0
    print(f"{'场次':<7}{'联赛':<5}{'主队':<10}{'客队':<10}{'开赛':<17}"
          f"{'胜':>5}{'平':>5}{'负':>5}{'返奖率':>7}{'单关':>4}{'快照':>4}")
    for m in matches:
        odds = db.latest_odds(m.match_id)
        if odds:
            from .analysis.implied import payout_ratio
            pr = payout_ratio(odds.win, odds.draw, odds.lose)
            odds_str = f"{odds.win:>5.2f}{odds.draw:>5.2f}{odds.lose:>5.2f}{pr:>7.1%}"
        else:
            odds_str = f"{'-':>5}{'-':>5}{'-':>5}{'-':>7}"
        single = {True: "是", False: "否", None: "?"}[m.single_sellable]
        snaps = db.snapshot_count(m.match_id)
        print(f"{m.match_num:<7}{m.league:<5}{m.home:<10}{m.away:<10}"
              f"{m.match_time.strftime('%m-%d %H:%M'):<17}{odds_str}{single:>4}{snaps:>4}")
    print(f"\n共 {len(matches)} 场（五大联赛: {'/'.join(config.BIG_FIVE)}）")
    db.close()
    return 0


def cmd_analyze(args) -> int:
    from .analysis.implied import implied_probs, payout_ratio
    from .analysis.signals import SIDE_CN, analyze_match

    db = DB(config.DB_PATH)
    try:
        dates = _parse_dates(args.date)
        matches = db.get_matches(dates=dates or None, leagues=list(config.BIG_FIVE),
                                 status=None if args.all_status else "Selling")
        if not matches:
            print("（无待分析场次，先运行 snapshot）")
            return 0
        for m in matches:
            odds = db.latest_odds(m.match_id)
            hist = db.get_odds_history(m.match_id)
            print(f"\n■ {m.match_num} {m.league} {m.home} vs {m.away}"
                  f"（{m.match_time.strftime('%m-%d %H:%M')} 开赛，快照 {len(hist)} 条）")
            if odds is None:
                print("  无胜平负赔率")
                continue
            p = implied_probs(odds.win, odds.draw, odds.lose)
            print(f"  赔率 {odds.win:.2f}/{odds.draw:.2f}/{odds.lose:.2f}"
                  f"  返奖率 {payout_ratio(odds.win, odds.draw, odds.lose):.1%}")
            print(f"  去水概率 主胜 {p.win:.1%} | 平 {p.draw:.1%} | 客胜 {p.lose:.1%}")
            if len(hist) < 2:
                print("  快照不足（<2），暂无轨迹信号——继续积累")
                continue
            sigs = analyze_match(hist, m.match_time)
            if not sigs:
                print("  赔率轨迹平稳，无信号")
            for s in sigs:
                print(f"  [信号 {s.kind}/{SIDE_CN[s.side]} 强度{s.strength:.2f}] {s.detail}")
    finally:
        db.close()
    return 0


def cmd_export(args) -> int:
    """SQLite → CSV 导出（默认 odds_full 宽表 + 全部表，utf-8-sig 适配 Excel）。"""
    from .storage.csv_export import export_tables

    out_dir = Path(args.out) if args.out else config.ROOT / "exports"
    db = DB(config.DB_PATH)
    try:
        results = export_tables(db, [args.table] if args.table else None, out_dir)
    finally:
        db.close()
    for path, n in results:
        print(f"  {path}  ({n} 行)")
    print(f"\n导出完成 → {out_dir}")
    return 0


def cmd_backup(args) -> int:
    """SQLite 在线安全备份：采集运行中也可执行，用于双机同步/迁移。"""
    from datetime import datetime as _dt

    dest = Path(args.out) if args.out else (
        config.DATA_DIR / "backups" / f"jingcai_{_dt.now().strftime('%Y%m%d_%H%M%S')}.db")
    db = DB(config.DB_PATH)
    try:
        db.backup_to(dest)
    finally:
        db.close()
    print(f"备份完成 → {dest}（{dest.stat().st_size / 1024:.0f} KB）")
    return 0


def cmd_selftest(args) -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(config.TESTS_DIR), pattern="test_*.py",
                            top_level_dir=str(config.ROOT))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def cmd_autopoll(args) -> int:
    """单个智能采集周期：供计划任务每 30 分钟调用（推荐部署方式）。"""
    from .datasource.collector import autopoll_once

    client = SportteryClient(fixture=args.fixture)
    db = DB(config.DB_PATH)
    try:
        r = autopoll_once(client, db)
    finally:
        db.close()
    mode_cn = {"full": "全量快照", "discovery": "新场次巡检"}[r["mode"]]
    print(f"[{r['ran_at']}] {mode_cn}"
          f"（当前节奏 {r['interval_min']}min，下次全量约 {r['next_full_in_min']:.0f} 分钟后）")
    for m in r["new_matches"]:
        print(f"  ★ 新场次 {m.match_num} {m.league} {m.home} vs {m.away}"
              f"（{m.match_time.strftime('%m-%d %H:%M')} 开赛）")
    print(f"  新增赔率快照 {r['odds_added']} 条；新增信号 {r['signals_added']} 条")
    return 0


def cmd_watch(args) -> int:
    """常驻模式：新场次巡检每 30 分钟，全量按 4h/赛前8h内2h 自适应。"""
    import time

    from .datasource.collector import minutes_until_full_due

    print(f"常驻采集：基础 {config.BASE_INTERVAL_MIN}min / 开赛前{config.ACCEL_WINDOW_H:.0f}h内 "
          f"{config.ACCEL_INTERVAL_MIN}min，新场次巡检 {config.DISCOVERY_INTERVAL_MIN}min。Ctrl+C 退出。")
    while True:
        try:
            cmd_autopoll(args)
        except Exception as e:  # 单轮失败不退出常驻进程
            print(f"本轮采集失败（继续下一轮）: {e}", file=sys.stderr)
        db = DB(config.DB_PATH)
        try:
            nap = minutes_until_full_due(db)
        finally:
            db.close()
        sleep_min = max(1.0, min(config.DISCOVERY_INTERVAL_MIN,
                                 nap if nap > 0 else config.DISCOVERY_INTERVAL_MIN))
        print(f"  休眠 {sleep_min:.0f} 分钟…")
        try:
            time.sleep(sleep_min * 60)
        except KeyboardInterrupt:
            print("已停止。")
            return 0


def cmd_not_implemented(version: str):
    def handler(args) -> int:
        print(f"该命令按版本路线在 {version} 交付（见 docs/00-框架设计方案.md 第 10 节）。")
        return 2
    return handler


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jc", description="竞彩足球策略分析工具（五大联赛·胜平负）")
    p.add_argument("--version", action="version", version=f"jc {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="手动全量快照（在售场次+全部最新赔率）")
    sp.add_argument("--fixture", default=None, help="离线模式：指定报文 JSON（测试用）")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("autopoll", help="单个智能采集周期（计划任务每30分钟调用）")
    sp.add_argument("--fixture", default=None, help="离线模式：指定报文 JSON（测试用）")
    sp.set_defaults(func=cmd_autopoll)

    sp = sub.add_parser("watch", help="常驻采集（巡检30min + 全量4h/赛前8h内2h）")
    sp.add_argument("--fixture", default=None)
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("list", help="列出在售场次（默认今日起3天五大联赛）")
    sp.add_argument("--date", default="today,+1,+2",
                    help="today,+1,+2 / YYYY-MM-DD / all")
    sp.add_argument("--all-leagues", action="store_true", help="不限于五大联赛")
    sp.add_argument("--all-status", action="store_true", help="含非在售状态")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("analyze", help="隐含概率+赔率轨迹信号")
    sp.add_argument("--date", default="today,+1,+2")
    sp.add_argument("--all-status", action="store_true")
    sp.set_defaults(func=cmd_analyze)

    sub.add_parser("selftest", help="运行全量测试套件").set_defaults(func=cmd_selftest)

    sp = sub.add_parser("export", help="SQLite 数据导出 CSV（Excel 友好）")
    sp.add_argument("--table", default=None,
                    help="只导这张表：odds_full(赔率宽表)/matches/odds_snapshots/...；缺省=全部")
    sp.add_argument("--out", default=None, help="输出目录（缺省 exports/）")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("backup", help="数据库在线安全备份（不停采集，双机同步用）")
    sp.add_argument("--out", default=None, help="备份文件路径（缺省 data/backups/jingcai_时间戳.db）")
    sp.set_defaults(func=cmd_backup)

    sub.add_parser("recommend", help="生成投注策略日报（v0.4）") \
        .set_defaults(func=cmd_not_implemented("v0.4"))
    sub.add_parser("settle", help="赛果结算（v0.3）") \
        .set_defaults(func=cmd_not_implemented("v0.3"))
    sub.add_parser("stats", help="命中率/ROI 统计（v0.5）") \
        .set_defaults(func=cmd_not_implemented("v0.5"))
    return p


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
