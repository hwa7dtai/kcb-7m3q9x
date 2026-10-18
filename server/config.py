"""全局配置：常量、默认学期、教务系统参数。

与前端 demo/js/store.js 中的同名常量保持一致，确保前后端契约不漂移。
"""
from __future__ import annotations

import os
import pathlib

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
SERVER_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
DEMO_DIR = PROJECT_ROOT / "demo"
DATA_DIR = SERVER_DIR / "data"

# SQLite 数据库文件（个人数据，不入库）
DB_PATH = os.environ.get("KCB_DB_PATH", str(DATA_DIR / "schedule.db"))

# ---------------------------------------------------------------------------
# 学期（WeekEngine 的输入；可用 KCB_* 环境变量覆盖）
# ---------------------------------------------------------------------------
DEFAULT_SEMESTER = {
    "id": "2026-2027-1",
    "name": "2026—2027 学年 第一学期",
    "startDate": "2026-08-31",  # 实测：第 7 周对应 2026-10-12 ~ 10-18
    "totalWeeks": 19,           # 实测课表最深到第 19 周
}
SEMESTER_ID = os.environ.get("KCB_SEMESTER_ID", DEFAULT_SEMESTER["id"])
SEMESTER_NAME = os.environ.get("KCB_SEMESTER_NAME", DEFAULT_SEMESTER["name"])
SEMESTER_START_DATE = os.environ.get("KCB_SEMESTER_START", DEFAULT_SEMESTER["startDate"])
SEMESTER_TOTAL_WEEKS = int(os.environ.get("KCB_SEMESTER_WEEKS", DEFAULT_SEMESTER["totalWeeks"]))

# ---------------------------------------------------------------------------
# 节次时间表（gzmtu 实际作息：10 节，每节 55 分钟）
# 与前端 demo 的默认值不同，以此为准（前端从 /api/semester 读取）
# ---------------------------------------------------------------------------
PERIOD_TIMES = [
    {"start": "08:10", "end": "09:05"},
    {"start": "09:05", "end": "10:00"},
    {"start": "10:10", "end": "11:05"},
    {"start": "11:05", "end": "12:00"},
    {"start": "14:00", "end": "14:55"},
    {"start": "14:55", "end": "15:50"},
    {"start": "16:00", "end": "16:55"},
    {"start": "16:55", "end": "17:50"},
    {"start": "18:40", "end": "19:35"},
    {"start": "19:35", "end": "20:30"},
]
TOTAL_PERIODS = 10
WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ---------------------------------------------------------------------------
# 教务系统（正方新版）参数 —— 来自 PLAN.md 第二章实测结论
# ---------------------------------------------------------------------------
JW_BASE_URL = os.environ.get("KCB_JW_BASE_URL", "http://jwx.gzmtu.edu.cn")
JW_LOGIN_PATH = "/jwglxt/xtgl/login_slogin.html"
JW_PUBLIC_KEY_PATH = "/jwglxt/xtgl/login_getPublicKey.html"
JW_LOGOUT_PATH = "/jwglxt/xtgl/login_logoutAccount.html"
JW_XXCHECK_PATH = "/jwglxt/xtgl/yhgl_cxXxqrCheck.html"
JW_SCHOOL_CODE = "11106"  # xxdm

# 课表接口候选（按优先级尝试；真实地址以阶段一勘察结果为准）
JW_KB_CANDIDATES = [
    "/jwglxt/kbcx/xskbcx_cxXsKb.html",
    "/jwglxt/kbcx/xskbcx_cxXsgrKb.html",
    "/jwglxt/kbcx/xskbcx_cxXskb.html",
]

# 正方新版学期代码：第 n 学期 → (n-1)*12+3（1 学期=3，2 学期=15）
XQM_MAP = {1: 3, 2: 15}

# ---------------------------------------------------------------------------
# 自动登录保护（PLAN.md 4.4 / 2.4：连续失败 3 次锁号 3 分钟，严禁循环重试）
# ---------------------------------------------------------------------------
MAX_LOGIN_ATTEMPTS = 2  # 总尝试次数硬上限
REQUEST_TIMEOUT = 15    # 秒
REQUEST_INTERVAL = 1.2  # 请求间隔（秒），不做高频轮询

# ---------------------------------------------------------------------------
# 首次运行的演示种子数据（与 demo/js/store.js 的 SEED_COURSES 完全一致）
# 可用 KCB_SEED_DEMO=0 关闭
# ---------------------------------------------------------------------------
SEED_DEMO_DATA = os.environ.get("KCB_SEED_DEMO", "1") == "1"

# keyring 服务名（凭据存系统钥匙串，禁止明文落盘）
KEYRING_SERVICE = "kcb-jwxt"
