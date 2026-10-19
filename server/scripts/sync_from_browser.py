"""从浏览器会话同步课表到本地数据库（WAF 拦截程序化登录时的更新通道）。

前提：已运行过 recon_playwright.py 并在浏览器里登录过教务系统（登录态保存在
      server/.browser-profile）。会话过期时重新跑一次 recon 脚本登录即可。

运行：python server/scripts/sync_from_browser.py

行为：读取教务系统 -> 解析（含同时段多周次合并）-> 移除旧教务课程 -> 导入新数据。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # server/

from adapters.zf import ZhengfangAdapter  # noqa: E402
from config import JW_BASE_URL, JW_KB_CANDIDATES  # noqa: E402
from core import browser_fetch  # noqa: E402
from core.service import ScheduleService  # noqa: E402
from core.storage import Storage  # noqa: E402


def main() -> int:
    storage = Storage()
    service = ScheduleService(storage, ZhengfangAdapter(JW_BASE_URL))
    term = service._term_params()

    print("[同步] 正在通过浏览器会话读取教务系统课表 …")
    raw = browser_fetch.fetch_raw_via_profile(JW_BASE_URL, JW_KB_CANDIDATES, term)
    if raw is None:
        print("[同步] ✗ 浏览器会话不可用（未登录或已过期）。")
        print("[同步]   请双击「登录教务系统.bat」登录一次后重试。")
        return 1

    courses = service.adapter.parse(raw)
    if not courses:
        print("[同步] ✗ 读取成功但未解析出课程，接口可能已改版。")
        return 1
    print("[同步] ✓ 读取到 {} 条排课（合并后 {} 个课表格位）".format(len(raw.get("kbList") or []), len(courses)))

    # 移除上一次从教务系统导入的课程（保留手动添加的课程；删除前自动快照）
    service.backup_snapshot()
    removed = 0
    for c in storage.list_courses():
        if c.get("source") == "jwxt":
            storage.delete_course(c["id"])
            removed += 1
    if removed:
        print("[同步] 已清除上次导入的 {} 门课程".format(removed))

    result = service.import_courses(courses)
    print("[同步] ✓ 导入 {} 门，跳过 {} 门".format(len(result["imported"]), len(result["skipped"])))
    for skip in result["skipped"]:
        print("[同步]   跳过：{}（{}）".format(skip["name"], skip["reason"]))

    # 学期总周数自动补齐（以数据里出现的最大周为准）
    weeks = [w for c in courses for w in c.get("weeks", [])]
    if weeks:
        sem = storage.get_semester()
        if max(weeks) > sem["totalWeeks"]:
            sem["totalWeeks"] = max(weeks)
            storage.save_semester(sem)
            print("[同步] 学期总周数已调整为 {} 周".format(sem["totalWeeks"]))

    print("[同步] 完成。刷新网页即可看到最新课表。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
