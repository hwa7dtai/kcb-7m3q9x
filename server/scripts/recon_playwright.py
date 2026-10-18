"""阶段一 · 接口勘察脚本（一次性工具）。

流程（PLAN.md 阶段一）：
1. 打开真实浏览器窗口，由你**像平时一样登录教务系统**
2. 登录后回终端按回车，脚本接管会话
3. 遍历候选课表接口，记录首个成功返回的地址与响应
4. 响应脱敏（替换姓名/学号/教室）后存为 tests/fixtures/real_xskbcx_sample.json

依赖：pip install playwright && python -m playwright install chromium
运行：python server/scripts/recon_playwright.py

注意：本脚本只读不改（只取课表查询接口），不做高频请求。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # server/

from config import JW_BASE_URL, JW_KB_CANDIDATES, JW_LOGIN_PATH, XQM_MAP  # noqa: E402

OUT_FILE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "real_xskbcx_sample.json"


def sanitize(payload: object) -> object:
    """脱敏：姓名、学号、教室名替换为虚构值，保留结构不变。"""
    fake = {"XM": "某同学", "XH": "2026******", "xm": "某教师"}
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            if k in ("XM", "XH", "xm", "YHM", "yhmc"):
                out[k] = fake.get(k, "已脱敏")
            elif k in ("jsmc", "cdmc", "jxcdmcs"):
                out[k] = "教学楼 X-XXX"
            else:
                out[k] = sanitize(v)
        return out
    if isinstance(payload, list):
        return [sanitize(i) for i in payload]
    return payload


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺少依赖：pip install playwright && python -m playwright install chromium")
        return 1

    term = {"xnm": "2026", "xqm": XQM_MAP[1]}
    print("=" * 60)
    print("  阶段一 · 教务系统接口勘察")
    print("  1. 浏览器窗口打开后，请像平时一样登录教务系统")
    print("  2. 登录成功、能看到课表页面后，回到本终端按回车")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(JW_BASE_URL + JW_LOGIN_PATH)
        input("\n  登录完成后请按回车，开始接管会话探测接口 …")

        cookies = {c["name"]: c["value"] for c in context.cookies()}
        if "JSESSIONID" not in cookies:
            print("未检测到 JSESSIONID，可能尚未登录成功。")
            browser.close()
            return 1

        # 用浏览器会话的 Cookie 发起课表候选接口探测（不走 requests，避免再登录）
        import urllib.parse
        import urllib.request

        hit = None
        for path in JW_KB_CANDIDATES:
            req = urllib.request.Request(
                JW_BASE_URL + path,
                data=urllib.parse.urlencode(term).encode(),
                headers={"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", "replace")
            except Exception as exc:
                print("  ✗ {} → {}".format(path, exc))
                continue
            try:
                payload = json.loads(body)
            except ValueError:
                print("  ✗ {} → 非 JSON（长度 {}）".format(path, len(body)))
                continue
            kb = payload.get("kbList") if isinstance(payload, dict) else payload
            if isinstance(kb, list) and kb:
                print("  ✓ {} → 课表数据 {} 条".format(path, len(kb)))
                hit = {"path": path, "payload": payload}
                break
            print("  ✗ {} → JSON 但无课表字段".format(path))
        browser.close()

    if not hit:
        print("\n所有候选接口均未命中。请在浏览器中打开课表页面，用 F12 观察实际请求地址后")
        print("把它加入 server/config.py 的 JW_KB_CANDIDATES，再运行本脚本。")
        return 1

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"_kb_path": hit["path"], "_fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "payload": sanitize(hit["payload"])}, f, ensure_ascii=False, indent=2)
    print("\n命中接口：{}".format(hit["path"]))
    print("脱敏样本已保存：{}".format(OUT_FILE))
    print("请把该路径写入 server/config.py 的 JW_KB_CANDIDATES 首位，并检查 server/adapters/zf.py 的解析字段。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
