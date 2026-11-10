"""全局配置：所有阈值/白名单/路径集中于此，改配置不改代码。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "jingcai.db"
RAW_DIR = DATA_DIR                      # 原始报文留档（接口失效时供 LLM 自愈分析）
SPEC_DIR = Path(__file__).parent / "datasource" / "specs"
REPORTS_DIR = ROOT / "reports"
TESTS_DIR = ROOT / "tests"

# ---- 联赛与玩法（D1/D2）----
BIG_FIVE = ("英超", "西甲", "意甲", "德甲", "法甲")

# ---- 采集调度（D5/D14，2026-11-02 确认）----
BASE_INTERVAL_MIN = 240             # 基础全量快照：每 4 小时
ACCEL_INTERVAL_MIN = 120            # 任一在售场次开赛前 8 小时内：加密到每 2 小时
ACCEL_WINDOW_H = 8.0
DISCOVERY_INTERVAL_MIN = 30         # 新场次发现巡检：每 30 分钟（只写新出现场次）
FULL_DUE_GRACE_MIN = 5              # 全量到期宽限：吸收计划任务启动时刻的秒级抖动
REPORT_HOUR = 17                    # 每日 17:00 出投注建议
REQUEST_MIN_INTERVAL_SEC = 30       # 同进程内对官方接口的最小请求间隔

# ---- 预算与串关（D4/D6）----
BET_UNIT_YUAN = 2.0
BUDGET_MAX_YUAN = 15.0                  # 单次投注预算上限（≈7 注）
MAX_PARLAY_LEGS = 4                     # 串关分析上限 4 串

# ---- 分析阈值（v1）----
MIN_EDGE = 0.03                         # 价值阈值：edge ≥ 3% 才出腿
SIGNAL_OPEN_MOVE = 0.03                 # 初赔→现赔变动 ≥3%
SIGNAL_STEADY_DROP = 0.05               # ≥3 次快照单调累计 ≥5%
SIGNAL_LATE_SHIFT = 0.04                # 开赛 3h 内相邻变动 ≥4%
SIGNAL_LATE_WINDOW_H = 3.0
SIGNAL_STRENGTH_FULL = 0.15             # 变动幅度达到 15% 记满强度 1.0
FUSE_MAX_ADJUST = 0.08                  # 概率融合修正上限 ±8 个百分点

# ---- HTTP ----
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
HTTP_TIMEOUT_SEC = 15

# ---- LLM spec 自愈（D12，v0.2 启用）：任意 OpenAI 兼容端点 ----
LLM_BASE_URL = ""                       # 例：https://open.bigmodel.cn/api/paas/v4
LLM_API_KEY = ""
LLM_MODEL = ""
