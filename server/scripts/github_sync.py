"""GitHub Actions 云端抓取：登录教务系统 -> 解析 -> 输出可发布的课表快照。

由 .github/workflows/publish.yml 调用，产物是 public-schedule.json，
流水线会把它复制为站点根目录的 schedule.json。

凭据来自 GitHub Secrets（JWXT_SID / JWXT_PWD），不落盘、不进日志。
抓取策略：先走 requests（快），被 WAF 拦则用无头 Chromium 自动登录（稳）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from adapters.zf import ZhengfangAdapter  # noqa: E402
from config import (  # noqa: E402
    JW_BASE_URL,
    JW_KB_CANDIDATES,
    PERIOD_TIMES,
    SEMESTER_ID,
    SEMESTER_NAME,
    SEMESTER_START_DATE,
    SEMESTER_TOTAL_WEEKS,
    TOTAL_PERIODS,
    WEEKDAY_LABELS,
    XQM_MAP,
)
from core.weeks import weeks_to_rule  # noqa: E402

OUT_FILE = ROOT / "public-schedule.json"
COLORS = ["blue", "teal", "amber", "purple", "rose", "green", "cyan"]


def fail(message: str) -> int:
    print("[云端同步] ✗ " + message, flush=True)
    return 1


def fetch_raw(sid: str, pwd: str, term: dict):
    """先程序化登录，失败再用无头浏览器。返回 (raw, how)。"""
    adapter = ZhengfangAdapter(JW_BASE_URL)
    try:
        adapter.fetch_session()
        adapter.login(sid, pwd)
        raw = adapter.fetch_schedule_raw(term)
        return raw, "http"
    except Exception as exc:
        print("[云端同步] 程序化登录失败（{}），改用无头浏览器 …".format(exc), flush=True)

    from core import browser_fetch
    raw, error = browser_fetch.login_and_fetch(JW_BASE_URL, sid, pwd, JW_KB_CANDIDATES, term)
    if raw is None:
        raise RuntimeError(error or "浏览器登录失败")
    return raw, "browser"


def build_payload(courses: list) -> dict:
    weeks = [w for c in courses for w in c.get("weeks", [])]
    total_weeks = max([SEMESTER_TOTAL_WEEKS] + weeks)
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "semester": {
            "id": SEMESTER_ID,
            "name": SEMESTER_NAME,
            "startDate": SEMESTER_START_DATE,
            "totalWeeks": total_weeks,
            "weekdayLabels": WEEKDAY_LABELS,
            "totalPeriods": TOTAL_PERIODS,
            "periodTimes": PERIOD_TIMES,
        },
        # 注意：不包含学号、姓名（脱敏后才发布到公网）
        "courses": courses,
    }


def main() -> int:
    sid = os.environ.get("JWXT_SID", "").strip()
    pwd = os.environ.get("JWXT_PWD", "")
    if not sid or not pwd:
        return fail("缺少 JWXT_SID / JWXT_PWD（请在仓库 Settings → Secrets 中配置）")

    try:
        xnm = SEMESTER_ID.split("-")[0]
        xqm = XQM_MAP.get(int(SEMESTER_ID.rsplit("-", 1)[1]), 3)
    except (ValueError, IndexError):
        xnm, xqm = "2026", 3
    xnm = os.environ.get("JWXT_XNM", xnm)
    xqm = int(os.environ.get("JWXT_XQM", xqm))
    term = {"xnm": xnm, "xqm": xqm}
    print("[云端同步] 学期参数：xnm={} xqm={}".format(xnm, xqm), flush=True)

    try:
        raw, how = fetch_raw(sid, pwd, term)
    except Exception as exc:
        return fail("无法从教务系统取数：{}".format(exc))

    courses = ZhengfangAdapter(JW_BASE_URL).parse(raw)
    if not courses:
        return fail("取到数据但未解析出课程，接口可能改版")

    for index, course in enumerate(courses):
        course["id"] = "j{}".format(index + 1)
        course["color"] = COLORS[index % len(COLORS)]
        course["source"] = "jwxt"
        if course.get("weekRule", {}).get("pattern") == "discrete" or not course.get("weekRule"):
            course["weekRule"] = weeks_to_rule(course.get("weeks", []))

    payload = build_payload(courses)
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[云端同步] ✓ 通道 {}，{} 门课程 → {}".format(how, len(courses), OUT_FILE.name), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
