"""浏览器会话取数（WAF 拦截程序化访问时的兜底通道）。

背景：gzmtu 教务系统对 requests 的登录链路返回 403（WAF），但真实浏览器可正常登录。
思路：复用 server/.browser-profile（勘察脚本登录后持久化的配置），用无头浏览器
在页面内 fetch 课表接口——与用户浏览器同指纹、同 Cookie，WAF 视为正常访问。

约束：
- 需要用户先用 recon_playwright.py 登录过一次（Cookie 存在 profile 中）
- 会话过期时返回 None，由上层提示用户重新登录
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

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


def profile_exists() -> bool:
    return (PROFILE_DIR / "Default").is_dir() or (PROFILE_DIR / "Local State").is_file()


def fetch_raw_via_profile(base_url: str, kb_paths: List[str], term: Dict,
                          entry_path: str = "/jwglxt/xtgl/index_initMenu.html") -> Optional[Dict]:
    """用持久化浏览器配置取课表原始 JSON；会话失效/未登录返回 None。"""
    if not profile_exists():
        logger.info("浏览器配置不存在，跳过浏览器通道")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("未安装 playwright，跳过浏览器通道")
        return None

    body = "xnm={}&xqm={}&kcxszc=3".format(term.get("xnm", ""), term.get("xqm", ""))
    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        except Exception as exc:
            logger.warning("浏览器配置被占用或不可用：%s", exc)
            return None
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(base_url + entry_path, wait_until="domcontentloaded", timeout=30000)
            if "login_slogin" in (page.url or ""):
                logger.info("浏览器会话已失效，需要重新登录")
                return None
            for path in kb_paths:
                result = page.evaluate(PROBE_JS, {"path": path, "body": body})
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
        finally:
            try:
                ctx.close()
            except Exception:
                pass
