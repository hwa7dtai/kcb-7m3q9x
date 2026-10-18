"""阶段三 · 一键刷新脚本（命令行入口）。

从系统钥匙串读取上次保存的凭据，自动登录教务系统重抓课表并覆盖入库。
首次使用请先通过前端「从教务系统导入」成功抓取一次（凭据会自动存入钥匙串）。

运行：python server/scripts/refresh.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # server/

import requests  # noqa: E402

from config import JW_BASE_URL  # noqa: E402
from core import credentials  # noqa: E402
from core.service import ScheduleService  # noqa: E402
from core.storage import Storage  # noqa: E402
from adapters.zf import ZhengfangAdapter  # noqa: E402


def main() -> int:
    student_id = input("学号（回车使用上次保存的账号）: ").strip()
    if not student_id:
        print("请输入学号以从钥匙串读取凭据。")
        return 1
    password = credentials.get_credentials(student_id)
    if not password:
        print("钥匙串中未找到该学号的凭据。请先在前端「从教务系统导入」成功抓取一次。")
        return 1

    session = requests.Session()
    service = ScheduleService(Storage(), ZhengfangAdapter(JW_BASE_URL, session))
    try:
        result = service.fetch_from_jwxt(student_id, password)
    except Exception as exc:
        print("刷新失败：{}".format(exc))
        return 1

    imported = service.import_courses(result["courses"])
    print("读取到 {} 门课程；本次导入 {} 门，跳过 {} 门（冲突/重复）。".format(
        len(result["courses"]), len(imported["imported"]), len(imported["skipped"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
