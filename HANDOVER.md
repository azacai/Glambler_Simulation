# 竞彩足球策略分析工具 · 交接文档（HANDOVER）

| 项 | 值 |
|---|---|
| 软件版本 | v0.2.3（68 项 unittest 全绿） |
| 文档时点 | 2026-11-09 |
| 权威文档 | `docs/00-框架设计方案.md`（设计决策 D1~D14 + 数据源实测记录） |

---

## 0. 新环境 5 分钟部署

```bat
1. 安装 Python 3.11 或更高（安装时勾选 "Add python.exe to PATH"）
2. 克隆或解压本仓库到任意目录（路径可含中文）
3. 打开 CMD：
   cd /d "你的目录\竞彩足球策略工具"          ← 换成实际目录
   python -m jc selftest                      ← 应显示 Ran 68 tests ... OK（离线）
   python -m jc autopoll                      ← 联网采集一次官方在售场次+赔率
   python -m jc list / analyze                ← 场次一览 / 隐含概率 + 轨迹信号
```

零第三方依赖（纯 Python 标准库：sqlite3/urllib/csv/unittest），无需 pip install 任何东西。
运行数据（`data/`）不入 Git：克隆后为空库，首次 `autopoll` 后即有当日数据；多机数据同步见 §2。

---

## 1. 项目是什么

中国体育彩票**竞彩足球**投注策略分析工具。

- **边界**：投注标的仅限体彩官方在售场次；玩法仅**胜平负**（不让球）；分析范围仅**五大联赛**（英超/西甲/意甲/德甲/法甲）。境外平台赔率（懂球帝聚合，v0.3 接入）仅作分析参考，不构成投注标的。
- **预算约束**：单次投注 ≤15 元（≤7 注，1 注=2 元）；串关上限 4 串。
- **目标输出**（v0.4）：每日 17:00 生成三套方案（稳健/平衡/进取）的 Markdown 日报——投哪几场、押什么、单场还是 N 串、各几注、为什么。
- **无前端页面**（决策 D8）：CLI + Markdown 文件交付；可视化 ≥v2.0 再议。
- **期望管理**：竞彩赔率隐含返还率约 88%，即按去水概率投注长期期望约 **-12%~-13%/注**。工具价值 = 纪律化（强制预算/复盘）+ 信息整合 + 负 EV 过滤，**不承诺盈利**。

---

## 2. 数据同步与多机使用

**原则：同一时间只在一台机器运行采集**——两台机器同时采集会产生两份分叉的数据库，当前没有合并工具。其余机器只做分析（`list` / `analyze` / `export`），用备份文件同步数据。

**同步操作（采集机 → 其他机器）**：
```bat
采集机：双击 run_backup.bat（或 python -m jc backup）
        → 生成 data\backups\jingcai_日期时间.db（在线备份，不停采集）
拷贝该文件到目标机器，覆盖其 data/jingcai.db
目标机：python -m jc list / analyze / export 即基于最新数据
```
建议频率：每周一次或需要分析前。备份用的是 SQLite backup API，任何时刻执行都是一致性副本，不锁库、不影响采集。

> ⚠️ v0.4 起分析机会产生自己的推荐/结算数据，届时"整库覆盖"会冲掉这些记录，需换成增量同步方案（已列入 v0.4 待办）。现阶段（v0.2.x）分析机不产生自有数据，整库覆盖无风险。

---

## 3. 运行环境

| 项 | 要求 |
|---|---|
| Python | 3.11+（3.10 也可，需支持 `TemporaryDirectory(ignore_cleanup_errors=True)`） |
| 第三方依赖 | **无** |
| 操作系统 | Windows（当前）/ macOS / Linux 均可 |
| 网络 | 仅采集命令（autopoll/snapshot）需访问 webapi.sporttery.cn；分析/导出/测试全离线 |
| 数据库 | SQLite 单文件 `data/jingcai.db`，Python 内置，无需安装任何软件 |

---

## 4. 命令手册（`python -m jc <命令>`，均需先 cd 到项目目录）

| 命令 | 作用 | 引入版本 |
|------|------|---------|
| `autopoll` | **采集主入口**：单个智能周期=新场次巡检(30min节奏)+到期的全量快照(4h基础/开赛前8h内2h)。计划任务每30分钟调它 | v0.2.0 |
| `watch` | 常驻采集（同 autopoll 逻辑的前台循环，Ctrl+C 退出） | v0.2.0 |
| `snapshot` | 手动全量快照（忽略节奏立即全量，含信号落库） | v0.1 |
| `list` | 场次列表（默认今日起3天五大联赛；`--date all`/`--all-leagues`/`--all-status`） | v0.1 |
| `analyze` | 每场：去水概率/返奖率/轨迹信号（open_move/steady_drop/late_shift） | v0.1 |
| `export` | SQLite→CSV（`--table odds_full` 赔率宽表最常用；utf-8-sig，Excel 直开） | v0.2.1 |
| `backup` | 数据库在线安全备份（`--out 路径` 可指定文件名） | v0.2.3 |
| `selftest` | 运行全部 68 项测试（离线，不打网络） | v0.1 |
| `settle` | 赛果结算 | v0.3（占位） |
| `recommend` | 17:00 三方案策略日报 | v0.4（占位） |
| `stats` | 命中率/ROI 统计 | v0.5（占位） |

双击入口（资源管理器）：`run_autopoll.bat`（单次采集）、`run_export.bat`（导出+打开目录）、`run_backup.bat`（备份+打开目录）。

---

## 5. 代码工程逐文件说明

```
竞彩足球策略工具/
├── HANDOVER.md              ← 本文档
├── AGENTS.md                ← 跨会话/跨设备交接入口（每次阶段性变更更新"当前状态"）
├── README.md                ← 快速上手 + 计划任务注册命令
├── run_autopoll.bat         ← 计划任务调用的采集脚本（%~dp0 自定位，全 ASCII）
├── run_export.bat           ← 双击导出 CSV
├── run_backup.bat           ← 双击备份数据库
├── .gitignore
├── docs/
│   └── 00-框架设计方案.md    ← 唯一权威设计文档：六层架构/接口定义/表结构/
│                               决策 D1~D14/版本路线/数据源实测记录(§12)/确认历史(§13)
├── jc/                      ← 主包（所有代码）
├── tests/                   ← unittest 套件（fixtures 用真实报文裁剪，不打网络）
├── data/                    ← 运行数据：jingcai.db + autopoll.log + last_onsale.json
│                               （原始报文留档，接口失效时供 LLM 自愈分析）
├── exports/                 ← CSV 导出输出（可随时重新生成，不入包）
└── reports/                 ← 每日策略报告输出目录（v0.4 起使用）
```

### `jc/` 包内逐模块

| 文件 | 作用与目的 | 关键点 |
|------|-----------|--------|
| `__init__.py` | 版本号 | 当前 0.2.3 |
| `__main__.py` | `python -m jc` 入口 | |
| `config.py` | **全部可调参数**：五大联赛白名单、采集节奏（BASE=240/ACCEL=120/DISCOVERY=30min、ACCEL_WINDOW_H=8）、预算（15元/4串）、信号阈值、LLM 端点留位 | 改配置不改代码；路径常量也在这 |
| `models.py` | 全部数据结构：Match/Odds3Way/Prob3/Signal/Leg/Bet/Portfolio | Prob3.make 自动归一化 |
| `datasource/specio.py` | spec 机制通用件：加载 spec JSON、路径解析（含通配符拍平）、HTTP GET（浏览器头+≥30s 间隔）、成功判据 | SpecError 是接口失效的统一信号 |
| `datasource/sporttery.py` | 体彩官方接口适配器：解析**完全由 spec 驱动**，代码只含领域归一化（'[英超2]'→2、字符串赔率→float 等） | 离线 fixture 模式供测试；原始报文留档 data/last_onsale.json |
| `datasource/specs/sporttery_on_sale.json` | **在售+赔率接口规则**（端点/参数/字段映射/单关定位），verified_at=2026-10-30 | 接口变了改这个文件，代码不动 |
| `datasource/snapshot.py` | 手动全量快照：场次 upsert + 赔率幂等入库 + 信号落库 | |
| `datasource/collector.py` | **智能采集调度核心**：full_interval_min（节奏判定）/autopoll_once（单周期：一次请求同时做发现+到期全量）；状态存 collector_state 表 | 巡检模式只写新场次，不动已知轨迹 |
| `datasource/healer.py` | LLM spec 自愈占位（v0.3）：接口失效时大模型读报文重生成 spec，人工确认后生效 | 需在 config 填 LLM_BASE_URL/KEY/MODEL |
| `storage/db.py` | SQLite 全部 7 张表的建表/迁移/读写；在线备份 backup_to | 打开老库自动迁移（signals.basis_ts） |
| `storage/csv_export.py` | CSV 导出：odds_full 宽表（赔率 JOIN 场次）+ 全部表 | utf-8-sig（Excel 中文不乱码） |
| `analysis/implied.py` | 隐含概率数学：sum_inverse/payout_ratio/implied_probs（去水）/edge | 纯函数 |
| `analysis/signals.py` | 轨迹信号 v1：open_move（初→现≥3%）/steady_drop（≥3快照单调累计≥5%）/late_shift（开赛3h内相邻≥4%） | 强度=幅度/15% 封顶 1.0；detail 是人话 |
| `analysis/persist.py` | 信号落库：全量轮后对全部有轨迹场次计算并持久化 | basis_ts 幂等去重，赔率演变留痕 |
| `analysis/model.py` | 概率融合模型占位（v0.4）：去水概率+信号修正±8pp | v2 接 xG 回归 |
| `strategy/` `tracker/` `report/` | 空占位包：v0.4 策略层 / v0.3+v0.5 结算统计 / v0.4 日报 | 设计文档 §4/§5 有接口契约 |
| `cli.py` | 命令行（argparse）：全部子命令、智能日期解析（today/+N/YYYY-MM-DD/all）、selftest | stdout 强制 utf-8 |

### `tests/` 测试套件（68 项）

| 文件 | 覆盖 |
|------|------|
| test_implied.py | 概率数学（归一/排序/edge 符号） |
| test_signals.py | 三类信号的触发/不触发/阈值边界/排序 |
| test_db.py | 建表幂等/upsert/赔率去重/历史排序/赛果 upsert/**备份一致性** |
| test_filter.py | 五大联赛过滤 |
| test_parse.py | spec 机制（加载/路径/通配符/成功判据）+ 官方报文解析（字段归一/官方时戳/单关/无赔率场） |
| test_collector.py | 节奏判定（8h窗口/边界/已开赛不触发）、autopoll 全量与巡检、晚挂出捕获、状态跨重启、**启动抖动回归** |
| test_persist.py | 信号落库幂等/演变留痕/字段正确性/老库迁移 |
| test_export.py | CSV 导出（宽表 JOIN/BOM/非法表名拒绝） |
| test_snapshot_cli.py | CLI 端到端（list/analyze/autopoll/export 离线跑通） |

约定：**每个版本交付时测试必须刷新并全绿**（用户决策 D13）。

---

## 6. 数据库表（`data/jingcai.db`，7 张）

| 表 | 内容 | 填充者 |
|----|------|--------|
| `matches` | 全部在售过场次（含非五大联赛，分析时过滤）：编号/联赛/主客/排名/开赛时间/单关标识/状态 | 采集自动 |
| `odds_snapshots` | 赔率轨迹时间序列；**ts 用官方"最后调整时间"**，UNIQUE(match_id,ts) 幂等 | 采集自动 |
| `match_results` | 赛果（比分+W/D/L） | v0.3 settle（可回补历史） |
| `signals` | 轨迹信号；basis_ts=计算依据的最新快照时戳，UNIQUE(场次,类型,方向,basis_ts) | 全量轮自动（v0.2.2 起） |
| `recommendations` | 每日推荐方案 | v0.4 |
| `bet_outcomes` | 逐注结算明细 | v0.4/v0.5 |
| `collector_state` | 采集调度状态（上次全量时间），断电重启不丢节奏 | 采集自动 |

历史数据积累参考（2026-11-09 时点）：**177 场**（五大联赛 80）/ **569 条赔率快照** / **336 条信号**；轨迹覆盖 2026-10-29 ~ 2026-11-09（其中 10-31、11-01 缺失，见 §10）。

---

## 7. 版本记录

| 版本 | 日期 | 内容 | 测试 |
|------|------|------|------|
| v0.1.0 | 2026-10-30 | 骨架：六层架构、spec 驱动适配器、SQLite、隐含概率+轨迹信号、CLI；实机验证 55 场入库 | 42 |
| v0.2.0 | 2026-11-02 | **智能采集调度**：4h 基础全量/开赛前 8h 内 2h/30min 新场次巡检（只写新挂出场次）；调度状态持久化；采集上线（计划任务 JC-Autopoll）；实机捕获 17 场晚挂出 | 53 |
| v0.2.1 | 2026-11-02 | `export` CSV 命令（odds_full 宽表，Excel 友好）+ run_export.bat | 59 |
| v0.2.2 | 2026-11-09 | **signals 落库接线**（修复"信号即算即显不落库"缺口）：basis_ts 幂等去重、演变留痕、老库自动迁移；存量一周轨迹回补 335 条 | 65 |
| v0.2.3 | 2026-11-09 | `backup` 在线安全备份命令 + run_backup.bat（本次交接配套）；**修复**：计划任务秒级抖动导致全量被推迟一个巡检周期（4h 变 4.5h）——增加 5 分钟到期宽限 | 68 |

版本关系：v0.1 骨架 → v0.2.x 数据闭环完善（调度/导出/信号/备份）。**尚无分析结论类功能**（settle/recommend/stats 分别在 v0.3/v0.4/v0.5）。

---

## 8. 核心工作要点（接手必读）

1. **官方 updateTime 做快照时戳**：官方接口只给"当前赔率"，但每条赔率自带最后调整时间（`had.updateDate/updateTime`）——快照用它入库，赔率轨迹的时点精度**不受轮询间隔限制**。这是整个信号体系的基石。
2. **单关标识** = `poolList[poolCode=="HAD"].single == 1`（bettingSingle 是冗余字段）。
3. **接口规则外置 spec**（D12）：端点/字段映射在 `jc/datasource/specs/*.json`，代码只含通用解析。接口变更→改 spec；失效→按 `docs/00` §12 的方法逆向新端点（先抓官方页面 JS 找 XHR），v0.3 后由 LLM 自愈生成候选 spec。
4. **幂等去重三处**：赔率 UNIQUE(match_id, ts)；信号 UNIQUE(…, basis_ts)；采集可重复执行无副作用——所有命令都是"随时重跑安全"。
5. **新场次巡检**（D14）：体彩存在"当天中午才挂出、当晚开赛"的场次（实测捕获过 17 场/次），巡检只写新场次数据以尽快捕捉初赔，不扰乱已知场次轨迹节奏。
6. **测试约定**（D13）：每版交付必须刷新测试且全绿；fixtures 是真实报文裁剪，全程不打网络。
7. **请求礼貌**：对官方接口带浏览器 UA+Referer，同进程 ≥30s 间隔，2h/30min 级频率，个人使用无反爬风险。
8. **设计决策 D1~D14 全表**在 `docs/00-框架设计方案.md` §9，改任何行为先看这张表、有冲突先确认再动手（提纲确认制）。

---

## 9. 数据源与接口维护

| 用途 | 端点 | 状态 |
|------|------|------|
| 在售场次+赔率（胜平负+让球+排名+单关） | `GET webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=hhad,had&channel=c` | ✅ spec 已驱动，2026-10-30 验证 |
| 赛果（按日期回查，可回补历史） | `GET webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry?matchBeginDate=..&matchEndDate=..&leagueId=&pageSize=&pageNo=&isFix=0&matchPage=1&pcOrWap=1` | ✅ 2026-10-30 验证；**必须带**浏览器 UA + `Referer: https://www.sporttery.cn/jc/zqsgkj/`（旧路径 getMatchResultV1 已 403） |
| 懂球帝聚合欧赔（参考源） | `m.dongdianqiu.com/matchDetail/{id}/lotteryOddsNew` 页面可达，赔率需 JS 渲染 | v0.3 逆向其 XHR |

LLM 自愈（v0.3）：`config.py` 的 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` 填任意 OpenAI 兼容端点即可启用。

---

## 10. 已知问题与注意事项

1. **完赛场次 status 滞留 Selling**：在售接口不再返回已完赛场次，状态无从更新。无实害（调度已防护：已开赛场次不触发加密节奏）；v0.3 settle 拉赛果时顺带修正。
2. **10-31、11-01 两天轨迹缺失**：计划任务 11-02 才注册。赔率轨迹不可回补（官方无历史赔率接口）；这两天**赛果**仍可由 v0.3 回补。
3. **"四串三"不是官方过关方式**：v0.4 策略层落地时按官网过关表映射（预算内可选：4串1=2元、4串5=10元、4串6=12元）。
4. **返奖率口径**：`list` 显示的 ~87.8% 是单场赔率组合的数学隐含返还率；政策口径 ~73% 含发行费等。对单注 EV 计算以前者为准。
5. Windows 下直接复制使用中的 `.db` 文件可能碰到句柄占用——**同步一律用 `jc backup` 产物**，不要直接拷 `data\jingcai.db`。
6. 采集 bat 用 `%~dp0` 自定位且全 ASCII——移动/改名目录、路径含中文都不受影响；但**不要**在 bat 里硬编码路径。

---

## 11. 路线图与待办

| 版本 | 内容 | 前置条件 |
|------|------|---------|
| v0.3 | 赛果结算 settle + 10-30 以来历史赛果回补 + 完赛 status 修正；懂球帝参考源（逆向 XHR）；LLM spec 自愈 | LLM 部分需提供 API 配置，其余无 |
| v0.4 | 策略层：候选筛选→价值检测(edge≥3%)→组合生成(≤4串,官方过关表)→15元注分配→**17:00 三方案日报**；跨源背离信号；增量同步方案 | v0.3 建议先行 |
| v0.5 | 复盘统计：命中率/ROI/分串关档位 | v0.4 |
| v1.0+ | xG 回归模型（两队预期进球→泊松→比分矩阵→胜平负），与市场概率融合 | 用户提出（D11），不急 |

## 12. 文档索引

- `README.md` — 上手 + 计划任务注册/删除命令
- `AGENTS.md` — 滚动交接入口（新会话先读它）
- `docs/00-框架设计方案.md` — 权威设计：架构/接口/表结构/决策 D1~D14/路线/实测记录（§12）/确认历史（§13）
- 本文档 — 一次性完整快照（打包时点），日常滚动更新看 AGENTS.md
