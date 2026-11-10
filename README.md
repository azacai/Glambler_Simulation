# 竞彩足球策略分析工具

中国体育彩票竞彩足球投注策略分析工具。**仅五大联赛、仅胜平负玩法**，数据全部来自体彩官方接口，投注标的仅限官方在售场次。设计文档见 [docs/00-框架设计方案.md](docs/00-框架设计方案.md)。

> 现实约束：竞彩长期随机投注期望为负（按赔率隐含口径约 -12%~-13%/注）。本工具的价值在纪律化、信息整合与负 EV 过滤，不承诺盈利。**本项目不含前端页面**（远期 ≥v2.0 再议）。

## 环境

- Python 3.11+，纯标准库，零第三方依赖
- Windows / macOS / Linux 均可

## 快速开始

```bash
cd 竞彩足球策略工具
python -m jc autopoll        # 一键智能采集（推荐日常入口）
python -m jc list            # 今日起3天五大联赛场次一览
python -m jc analyze         # 隐含概率 + 赔率轨迹信号
python -m jc selftest        # 全量测试（53项）
```

## 采集调度（v0.2）

`autopoll` 单次执行一个智能周期，逻辑：

| 机制 | 节奏 | 说明 |
|------|------|------|
| 全量快照 | 基础每 **4 小时**；任一在售场次**开赛前 8 小时内**加密到每 **2 小时** | 已知场次的赔率轨迹采样 |
| 新场次发现 | 每 **30 分钟**巡检 | 同一官方接口，但**只写入新挂出场次**的数据（应对临开售才挂出的比赛，尽快捕捉初赔） |
| 状态持久化 | SQLite `collector_state` | 计划任务/断电/重启不丢调度节奏 |

部署二选一：

- **计划任务（推荐）**：每 30 分钟跑一次 `autopoll`（见下）
- **常驻进程**：`python -m jc watch`（同样逻辑，前台循环）

## 命令一览

| 命令 | 说明 | 版本 |
|------|------|------|
| `autopoll [--fixture xx.json]` | 单周期智能采集（发现+按节奏全量） | v0.2 ✅ |
| `watch` | 常驻采集（同上逻辑循环执行） | v0.2 ✅ |
| `snapshot [--fixture xx.json]` | 手动全量快照（忽略节奏，立即全量） | v0.1 ✅ |
| `list [--date today,+1,+2\|all] [--all-leagues] [--all-status]` | 场次列表（含赔率/返奖率/单关/快照数） | v0.1 ✅ |
| `analyze [--date ...]` | 去水概率 + 赔率轨迹信号（open_move/steady_drop/late_shift） | v0.1 ✅ |
| `selftest` | 运行测试套件 | v0.1 ✅ |
| `export [--table xx] [--out 目录]` | SQLite → CSV 导出（odds_full 赔率宽表+全部表，Excel 友好） | v0.2 ✅ |
| `backup [--out 文件.db]` | 数据库在线安全备份（不停采集，双机同步/迁移用） | v0.2 ✅ |
| `settle` | 赛果结算 | v0.3 |
| `recommend` | 每日 17:00 投注策略日报（三方案，预算≤15元） | v0.4 |
| `stats` | 命中率/ROI 统计 | v0.5 |

## 定时采集（Windows 计划任务，每 30 分钟）

先建 `run_autopoll.bat`（按实际路径调整）：

```bat
@echo off
cd /d "D:\系统部工作\竞彩足球策略工具"
python -m jc autopoll >> data\autopoll.log 2>&1
```

管理员 CMD 注册任务（09:00 起每 30 分钟，全天 48 次）：

```bat
schtasks /Create /TN "JC-Autopoll" /TR "\"D:\系统部工作\竞彩足球策略工具\run_autopoll.bat\"" /SC MINUTE /MO 30 /ST 09:00 /F
```

删除任务：`schtasks /Delete /TN "JC-Autopoll" /F`

（本机已于 2026-11-02 注册 `JC-Autopoll`：每 30 分钟执行 `run_autopoll.bat`，日志在 `data\autopoll.log`）

## 数据导出 CSV

```bash
python -m jc export                       # 全部表 + odds_full 赔率宽表 → exports/
python -m jc export --table odds_full     # 只导赔率轨迹宽表（含场次信息）
python -m jc export --out D:\某目录        # 指定输出目录
```

编码 utf-8-sig，Excel 双击打开中文不乱码。`odds_full` 是人工分析最常用的宽表：场次编号/联赛/主客队/开赛时间 JOIN 全部赔率快照，按开赛时间和快照时间排序。

## 备份与双机同步

```bash
python -m jc backup                 # 在线安全备份 → data/backups/jingcai_时间戳.db
```

双击 `run_backup.bat` 效果相同并自动打开备份目录。SQLite backup API 保证任意时刻执行都得到一致性副本，不锁库、不停采集。跨机器同步/迁移的完整操作说明见 [HANDOVER.md](HANDOVER.md) §2（原则：采集机唯一，备份文件单向覆盖）。

## 目录结构

```
jc/            主包（datasource/storage/analysis/strategy/tracker/report/cli）
data/          jingcai.db（SQLite）+ last_onsale.json（原始报文留档）+ 采集日志
docs/          设计文档
reports/       每日策略报告（v0.4 起）
tests/         unittest 套件（fixtures 为真实报文裁剪，不打网络）
```

## 工程约定

1. **接口规则不写进代码**：端点/字段映射在 `jc/datasource/specs/*.json`；接口变更改 spec，失效时由 LLM 自愈流程重生成（v0.3，见设计文档 D12）。
2. **测试随版本刷新**：每个版本交付时测试套件必须全绿，`python -m jc selftest` 一键回归。
3. 快照时间戳优先用官方"赔率最后调整时间"，赔率轨迹精度不受轮询间隔限制。
4. 采集节奏参数集中在 `jc/config.py`（BASE/ACCEL/DISCOVERY），改配置不改代码。
