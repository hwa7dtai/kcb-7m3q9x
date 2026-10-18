"""阶段一 · 接口勘察脚本（真实浏览器版，全自动）。

背景：教务系统 WAF 会拦截程序化访问（实测 403），因此用真实浏览器完成登录，
脚本在旁边捕获真实课表接口。

流程（全程无需任何按键）：
1. 弹出真实 Chrome 窗口 → 你像平时一样登录教务系统
2. 脚本同时做两件事：
   a. 监听页面发出的课表请求（URL 含 /kbcx/）——你登录后随便点开"我的课表"即可
   b. 检测到登录后，自动在页面内探测候选课表接口
3. 命中后自动脱敏（姓名/学号/教室替换为虚构值）保存样本，窗口自动关闭

产出：server/tests/fixtures/real_xskbcx_sample.json（含确认的接口地址）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # server/

from config import JW_BASE_URL, JW_KB_CANDIDATES, JW_LOGIN_PATH, XQM_MAP  # noqa: E402

OUT_FILE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "real_xskbcx_sample.json"
TIMEOUT_SECONDS = 900  # 最多等 15 分钟


def sanitize(payload: object) -> object:
    """脱敏：姓名、学号、教室替换为虚构值，保留结构不变。"""
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            if k in ("XM", "XH", "xm", "YHM", "yhmc", "xh"):
                out[k] = "已脱敏"
            elif k in ("jsmc", "cdmc", "jxcdmcs"):
                out[k] = "教学楼 X-XXX"
            else:
                out[k] = sanitize(v)
        return out
    if isinstance(payload, list):
        return [sanitize(i) for i in payload]
    return payload


def parse_body(text: str):
    """解析响应体，返回 (payload, kb 条数)。"""
    try:
        payload = json.loads(text)
    except ValueError:
        return None, 0
    if isinstance(payload, dict):
        for key in ("kbList", "kbmcList", "items", "rows"):
            lst = payload.get(key)
            if isinstance(lst, list):
                return payload, len(lst)
        return payload, 0
    if isinstance(payload, list):
        return {"kbList": payload}, len(payload)
    return None, 0


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[勘察] 缺少依赖：请在项目虚拟环境运行（已随 .venv 安装）")
        return 1

    xnm, xqm = "2026", XQM_MAP[1]
    print("[勘察] 即将打开真实浏览器，请在窗口中登录教务系统（账号密码自己输）")
    print("[勘察] 登录后不用做任何操作；若 60 秒后还没结果，请在系统里点开一次「我的课表」")
    print("[勘察] 命中接口后会自动脱敏保存并关闭窗口，最长等待 {} 秒".format(TIMEOUT_SECONDS))
    print("=" * 60, flush=True)

    captured = {"url": None, "payload": None, "count": 0}
    logged_in_at = [None]

    with sync_playwright() as p:
        # 持久化浏览器配置：登录状态会保留，后续再跑无需重复登录
        profile_dir = OUT_FILE.parents[2] / ".browser-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        browser = p.chromium.launch_persistent_context(str(profile_dir), headless=False)
        context = browser  # 持久化上下文本身就是 context，接口一致
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(JW_BASE_URL + JW_LOGIN_PATH, wait_until="domcontentloaded", timeout=30000)
        print("[勘察] 已打开登录页：{}".format(page.url), flush=True)

        # ---- 通道 A：监听页面自己发出的课表请求（最可信） ----
        def on_response(resp):
            url = resp.url
            if "/kbcx/" not in url or captured["payload"] is not None:
                return
            try:
                text = resp.text()
            except Exception:
                return
            payload, count = parse_body(text)
            if payload is not None and count > 0:
                captured.update({"url": url, "payload": payload, "count": count})
                print("[勘察] ✓（监听到页面请求）{} → {} 条课表".format(url, count), flush=True)

        page.on("response", on_response)

        # 教务系统登录后会新开窗口/标签页（原登录页标签仍停在登录页），
        # 因此必须监听 context 的全部页面，不能只盯第一个标签。
        def watch_new_page(pg):
            pg.on("response", on_response)

        context.on("page", watch_new_page)

        def active_page():
            """取最新的、非登录页的同源页面；没有则回退到第一个页面。"""
            pages = [pg for pg in context.pages if not pg.is_closed()]
            for pg in reversed(pages):
                try:
                    url = pg.url or ""
                except Exception:
                    continue
                if url.startswith(JW_BASE_URL) and "login_slogin" not in url:
                    return pg, url
            if pages:
                try:
                    return pages[0], pages[0].url or ""
                except Exception:
                    return None, ""
            return None, ""

        # ---- 通道 B：登录后自动在页面内 fetch 探测候选接口 ----
        PROBE_JS = """
        async (path) => {
            try {
                const res = await fetch(path, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'xnm=__XNM__&xqm=__XQM__&kcxszc=3'
                });
                const text = await res.text();
                return {status: res.status, text: text};
            } catch (e) {
                return {status: 0, text: String(e)};
            }
        }
        """.replace("__XNM__", xnm).replace("__XQM__", str(xqm))

        start = time.time()
        tried = set()
        last_report = 0.0
        while time.time() - start < TIMEOUT_SECONDS:
            if captured["payload"] is not None:
                break
            pg, current = active_page()
            if pg is None:
                print("[勘察] 浏览器窗口已被关闭，脚本退出", flush=True)
                return 1
            on_login_page = "login_slogin" in current
            if on_login_page and time.time() - last_report > 20:
                last_report = time.time()
                print("[勘察] 仍在登录页等待登录…（{:.0f}s，页面：{}）".format(
                    time.time() - start, current), flush=True)
            if not on_login_page and current.startswith(JW_BASE_URL):
                if logged_in_at[0] is None:
                    logged_in_at[0] = time.time()
                    print("[勘察] 检测到已登录（{}），开始自动探测候选接口 …".format(current), flush=True)
                for path in JW_KB_CANDIDATES:
                    if path in tried or captured["payload"] is not None:
                        continue
                    tried.add(path)
                    try:
                        result = pg.evaluate(PROBE_JS, path)
                    except Exception as exc:
                        print("[勘察]   探测 {} 异常：{}".format(path, exc), flush=True)
                        continue
                    payload, count = parse_body(result.get("text", ""))
                    if result.get("status") == 200 and payload is not None and count > 0:
                        captured.update({"url": JW_BASE_URL + path, "payload": payload, "count": count})
                        print("[勘察] ✓（自动探测）{} → {} 条课表".format(path, count), flush=True)
                        break
                    print("[勘察]   {} → HTTP {}，无课表数据".format(path, result.get("status")), flush=True)
            time.sleep(3)

        browser.close()

    if captured["payload"] is None:
        print("[勘察] ✗ 超时未捕获课表接口。可能原因：未登录成功 / 学校接口不在候选清单。")
        print("[勘察]   请在浏览器登录后手动打开一次课表页面再运行本脚本。")
        return 1

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    real_path = captured["url"].replace(JW_BASE_URL, "")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "_kb_path": real_path,
            "_fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "_xnm": xnm, "_xqm": xqm,
            "payload": sanitize(captured["payload"]),
        }, f, ensure_ascii=False, indent=2)
    print("=" * 60)
    print("[勘察] ✓ 接口确认：{}".format(real_path))
    print("[勘察] ✓ 课表条数：{}".format(captured["count"]))
    print("[勘察] ✓ 脱敏样本已保存：{}".format(OUT_FILE))

    # ---- 顺手把真实课表同步进本地数据库（登录一次 = 全自动更新）----
    try:
        from adapters.zf import ZhengfangAdapter
        from core.service import ScheduleService
        from core.storage import Storage

        storage = Storage()
        service = ScheduleService(storage, ZhengfangAdapter(JW_BASE_URL))
        removed = 0
        for c in storage.list_courses():
            if c.get("source") == "jwxt":
                storage.delete_course(c["id"])
                removed += 1
        result = service.import_courses(service.adapter.parse(captured["payload"]))
        weeks = [w for c in result["imported"] for w in c.get("weeks", [])]
        if weeks:
            sem = storage.get_semester()
            if max(weeks) > sem["totalWeeks"]:
                sem["totalWeeks"] = max(weeks)
                storage.save_semester(sem)
        print("[勘察] ✓ 已同步到本地课表：导入 {} 门（清除旧导入 {} 门，跳过 {} 门）".format(
            len(result["imported"]), removed, len(result["skipped"])))
        print("[勘察] 打开 http://127.0.0.1:8080 刷新即可看到你的真实课表")
    except Exception as exc:
        print("[勘察] ! 自动同步失败（可稍后运行 sync_from_browser.py 重试）：{}".format(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
