"""浏览器通道：真实浏览器登录 + 页面内取课表（绕过 WAF，无需 bat）。

两条能力：
1. fetch_raw_via_profile()：复用已登录的浏览器配置（server/.browser-profile）直接取数。
   适合定时刷新、用户此前登录过且会话未过期。
2. login_and_fetch()：用网页表单提交的学号密码，在无头浏览器里**自动填表登录**再取数。
   这是「网页点一下就能抓课表」的主通道——教务系统 WAF 只放行真实浏览器，
   而真实浏览器能执行 JS 质询、携带完整指纹，所以这条路最稳。

出错时返回 (None, 人话错误)，由上层转成用户提示；不会重试，避免触发锁号。
"""
from __future__ import annotations

import json
import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(__file__).resolve().parent.parent / ".browser-profile"

PROBE_JS = """async (args) => {
  try {
    const res = await fetch(args.path, {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: args.body
    });
    const text = await res.text();
    return {status: res.status, text: text};
  } catch (e) {
    return {status: 0, text: String(e)};
  }
}"""

LOGIN_ERROR_KEYWORDS = [
    ("验证码", "教务系统要求输入验证码（失败次数过多）。请在电脑浏览器手动登录一次后再试。"),
    ("锁定", "账号已被锁定（连续失败 3 次锁 3 分钟），请稍后再试。"),
    ("密码不正确", "用户名或密码不正确，请核对后重试。"),
    ("密码错误", "用户名或密码不正确，请核对后重试。"),
    ("用户不存在", "用户名或密码不正确，请核对后重试。"),
]


def profile_exists() -> bool:
    return (PROFILE_DIR / "Default").is_dir() or (PROFILE_DIR / "Local State").is_file()


@contextmanager
def _browser_context(p):
    """优先用持久化配置（保留登录态）；被占用时退化为临时配置。"""
    ctx = None
    if profile_exists():
        try:
            ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        except Exception as exc:
            logger.warning("持久化浏览器配置不可用（%s），改用临时配置", exc)
    if ctx is None:
        ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(prefix="kcb-"), headless=True)
    try:
        yield ctx
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def _term_body(term: Dict) -> str:
    return "xnm={}&xqm={}&kcxszc=3".format(term.get("xnm", ""), term.get("xqm", ""))


def _fetch_in_pages(ctx, kb_paths: List[str], term: Dict) -> Optional[Dict]:
    """在已登录的页面里逐页尝试候选接口。"""
    body = _term_body(term)
    for page in reversed(ctx.pages):
        try:
            url = page.url or ""
        except Exception:
            continue
        if "login_slogin" in url or not url.startswith("http"):
            continue
        for path in kb_paths:
            try:
                result = page.evaluate(PROBE_JS, {"path": path, "body": body})
            except Exception:
                continue
            if result.get("status") != 200:
                continue
            try:
                payload = json.loads(result.get("text", ""))
            except ValueError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("kbList"), list) and payload["kbList"]:
                logger.info("浏览器通道命中课表接口：%s（%s 条）", path, len(payload["kbList"]))
                return payload
    return None


def _logged_in_pages(ctx) -> List:
    pages = []
    for page in ctx.pages:
        try:
            if "login_slogin" not in (page.url or ""):
                pages.append(page)
        except Exception:
            continue
    return pages


def fetch_raw_via_profile(base_url: str, kb_paths: List[str], term: Dict,
                          entry_path: str = "/jwglxt/xtgl/index_initMenu.html") -> Optional[Dict]:
    """复用已登录会话直接取数；会话失效/未登录返回 None。"""
    if not profile_exists():
        logger.info("浏览器配置不存在，跳过会话复用")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("未安装 playwright，跳过浏览器通道")
        return None

    with sync_playwright() as p:
        with _browser_context(p) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(base_url + entry_path, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                logger.warning("打开主页失败：%s", exc)
                return None
            if "login_slogin" in (page.url or ""):
                logger.info("浏览器会话已失效，需要重新登录")
                return None
            return _fetch_in_pages(ctx, kb_paths, term)


def login_and_fetch(base_url: str, student_id: str, password: str, kb_paths: List[str],
                    term: Dict, login_path: str = "/jwglxt/xtgl/login_slogin.html",
                    entry_path: str = "/jwglxt/xtgl/index_initMenu.html",
                    timeout_ms: int = 25000) -> Tuple[Optional[Dict], Optional[str]]:
    """自动登录并取课表。返回 (raw, error)；成功时 error 为 None。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "服务端缺少 playwright，无法使用浏览器登录。请在项目虚拟环境安装：pip install playwright"

    with sync_playwright() as p:
        with _browser_context(p) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(base_url + login_path, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                return None, "无法打开教务系统登录页（{}）。请检查网络或校园网/VPN。".format(exc)

            # 已有有效会话：直接取数
            if "login_slogin" not in (page.url or ""):
                raw = _fetch_in_pages(ctx, kb_paths, term)
                return (raw, None) if raw else (None, "已登录但未取到课表数据，教务系统接口可能已改版。")

            # 填表登录
            try:
                page.fill("#yhm", student_id)
                page.fill("#mm", password)
                page.click("#dl")
            except Exception as exc:
                return None, "登录页结构异常（{}），教务系统可能已改版。".format(exc)

            # 等待跳转（登录成功常会新开窗口）或错误提示
            waited = 0
            while waited < timeout_ms:
                page.wait_for_timeout(800)
                waited += 800
                for pg in ctx.pages:
                    try:
                        if "login_slogin" not in (pg.url or "") and pg.url:
                            raw = _fetch_in_pages(ctx, kb_paths, term)
                            if raw:
                                return raw, None
                            break
                    except Exception:
                        continue
                text = ""
                try:
                    text = page.inner_text("body")
                except Exception:
                    pass
                # 只认明确的错误提示，避免把页面固有文案（如隐藏的"验证码"标签）误判
                specific = ""
                try:
                    specific = page.inner_text(".alert-danger, .errorInfo, #tips, .tip-danger")
                except Exception:
                    specific = ""
                if any(k in specific for k, _ in LOGIN_ERROR_KEYWORDS):
                    text = specific
                else:
                    text = text if any(k in text for k in ("密码不正确", "密码错误", "锁定", "用户不存在")) else ""
                for keyword, message in LOGIN_ERROR_KEYWORDS:
                    if keyword in text:
                        if keyword == "验证码":
                            try:
                                if not page.is_visible("#yzm"):
                                    continue
                            except Exception:
                                continue
                        return None, message
            return None, "登录超时：教务系统未在预期时间内返回（可能需要验证码或网络较慢）。"

    return None, "浏览器通道异常结束。"
