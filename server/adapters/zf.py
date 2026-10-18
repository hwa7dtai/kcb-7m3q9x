"""正方新版教务系统适配器（jwx.gzmtu.edu.cn，/jwglxt/ 路径）。

实现依据 PLAN.md 第二章只读探测结论：
- 登录四步：取会话与 csrftoken → 取 RSA 公钥 → 加密密码 → 提交登录
- csrftoken 与 JSESSIONID 必须同会话配对，全程复用注入的 session
- 提交前需先过 yhgl_cxXxqrCheck.html 校验
- 验证码策略：连续失败 >= 3 次才触发验证码并锁号 3 分钟 → 自动登录严禁循环重试

课表接口（阶段一唯一未知项）按候选清单逐个尝试，命中后缓存到实例，
教务系统改版时只需更新 JW_KB_CANDIDATES 或本文件。
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Dict, List, Optional

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from adapters.base import BaseAdapter, JwxtError, LoginError, SessionExpiredError
from config import (
    JW_KB_CANDIDATES,
    JW_LOGIN_PATH,
    JW_LOGOUT_PATH,
    JW_PUBLIC_KEY_PATH,
    JW_SCHOOL_CODE,
    JW_XXCHECK_PATH,
    REQUEST_INTERVAL,
    REQUEST_TIMEOUT,
)
from core.weeks import format_weeks_text, weeks_to_rule

logger = logging.getLogger(__name__)


class ZhengfangAdapter(BaseAdapter):
    """正方新版（zftal-ui-v5）适配器。"""

    name = "zf"

    def __init__(self, base_url: str, session=None, kb_path: Optional[str] = None):
        super().__init__(base_url, session)
        self.kb_path = kb_path  # 已勘察确认的课表接口（跳过候选尝试）
        self._csrftoken: Optional[str] = None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _ensure_session(self):
        """session 惰性创建：未注入时用 requests.Session（全程单会话，Cookie 与 csrftoken 配对）。

        同时伪装成浏览器访问：部分学校 WAF 会拦截非浏览器特征（实测曾出现偶发 403）。
        """
        if self.session is None:
            import requests
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/130.0.0.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
        return self.session
    def _url(self, path: str) -> str:
        return self.base_url + path

    def _get(self, path: str, **kwargs):
        time.sleep(REQUEST_INTERVAL)  # 请求加间隔，避免压力（PLAN.md 4.4）
        return self._ensure_session().get(self._url(path), timeout=REQUEST_TIMEOUT, **kwargs)

    def _post(self, path: str, data=None, **kwargs):
        time.sleep(REQUEST_INTERVAL)
        return self._ensure_session().post(self._url(path), data=data, timeout=REQUEST_TIMEOUT, **kwargs)

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        """会话失效检测：响应为登录页或跳转（PLAN.md 4.4）。"""
        if not html:
            return False
        head = html[:4000]
        return ("login_slogin" in head) or ("id=\"yhm\"" in head and "id=\"mm\"" in head)

    # ------------------------------------------------------------------
    # 第 1 步：取会话与 csrftoken
    # ------------------------------------------------------------------
    def fetch_session(self) -> Dict:
        resp = self._get(JW_LOGIN_PATH)
        if resp.status_code == 403:
            raise JwxtError(
                "教务系统拒绝访问（HTTP 403）：可能触发了防护或非校园网络，"
                "请等一分钟再试；若持续失败，请运行 server/scripts/recon_playwright.py "
                "用真实浏览器手动登录一次"
            )
        if resp.status_code != 200:
            raise JwxtError("教务系统登录页不可访问（HTTP {}）".format(resp.status_code))
        token = extract_csrftoken(resp.text)
        if not token:
            raise JwxtError("登录页解析失败：未找到 csrftoken（教务系统可能已改版）")
        self._csrftoken = token
        return {"csrftoken": token}

    # ------------------------------------------------------------------
    # 第 2 步：取 RSA 公钥
    # ------------------------------------------------------------------
    def fetch_public_key(self) -> Dict:
        resp = self._get("{}?time={}".format(JW_PUBLIC_KEY_PATH, int(time.time() * 1000)))
        try:
            payload = resp.json()
            return {"modulus": payload["modulus"], "exponent": payload["exponent"]}
        except (ValueError, KeyError) as exc:
            raise JwxtError("公钥接口返回异常（教务系统可能已改版）") from exc

    # ------------------------------------------------------------------
    # 第 3 步：RSA 加密密码（PKCS#1 v1.5）
    # ------------------------------------------------------------------
    @staticmethod
    def rsa_encrypt(password: str, modulus_b64: str, exponent_b64: str) -> str:
        def b64_to_int(value: str) -> int:
            return int.from_bytes(base64.b64decode(value), "big")

        n = b64_to_int(modulus_b64)
        e = b64_to_int(exponent_b64)
        key = RSA.construct((n, e))
        cipher = PKCS1_v1_5.new(key)
        encrypted = cipher.encrypt(password.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    # ------------------------------------------------------------------
    # 第 4 步：登录
    # ------------------------------------------------------------------
    def login(self, student_id: str, password: str) -> None:
        if not self._csrftoken:
            self.fetch_session()

        # 4.1 提交前校验（部分部署要求先过这一步）
        try:
            self._post(JW_XXCHECK_PATH, data={"yhm": student_id})
        except Exception as exc:  # 校验失败不阻断登录，但要留痕
            logger.warning("yhgl_cxXxqrCheck 请求失败（继续尝试登录）：%s", exc)

        # 4.2 取公钥并加密密码
        pubkey = self.fetch_public_key()
        encrypted = self.rsa_encrypt(password, pubkey["modulus"], pubkey["exponent"])

        # 4.3 登录表单（字段清单来自 PLAN.md 2.3 实测）
        form = {
            "yhm": student_id,
            "mm": encrypted,
            "csrftoken": self._csrftoken,
            "dlmmsfknt": "1",
            "ydappsfbldlzt": "0",
            "yzcskz": "3",
            "mmsfjm": "1",
            "mmsrddcshkzfs": "0",
            "dlsbsdsj": "3",
            "sfxswechatlogin": "0",
            "scene_id": "",
            "authJwglxtLoginURL": "",
            "rzzxxs": "",
            "rzys": "",
            "sfzywqh": "0",
            "xxdm": JW_SCHOOL_CODE,
            "userPolicyOn": "0",
            "dxsyrz": "0",
            "language": "zh_CN",
            "ydType": "",
        }
        resp = self._post(JW_LOGIN_PATH, data=form)

        body = resp.text or ""
        if resp.status_code != 200:
            raise LoginError("教务系统登录接口异常（HTTP {}）".format(resp.status_code))
        if self._looks_like_login_page(body):
            reason = extract_login_error(body)
            if reason:
                raise LoginError("登录失败：{}".format(reason))
            raise LoginError("登录失败：用户名或密码错误（或会话已过期，请重试一次）")
        # 注意：登录成功后不再重新请求登录页取新 csrftoken——部分部署登录后
        # 访问登录页会跳转主页，重新解析反而会误判失败；课表接口也不依赖该 token。
        logger.info("教务系统登录成功（学号 %s）", student_id)

    def logout(self) -> None:
        if self._csrftoken:
            try:
                self._post(JW_LOGOUT_PATH, data={"csrfTokenLogout": self._csrftoken})
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 课表抓取
    # ------------------------------------------------------------------
    def fetch_schedule_raw(self, term: Optional[Dict] = None) -> object:
        """尝试候选课表接口，返回首个成功响应的原始数据。"""
        term = term or {}
        data = {
            "xnm": term.get("xnm", ""),
            "xqm": term.get("xqm", ""),
            "kcxszc": term.get("kcxszc", "3"),  # 查询维度：按周
        }
        candidates = [self.kb_path] if self.kb_path else JW_KB_CANDIDATES
        last_error: Optional[Exception] = None
        for path in candidates:
            try:
                resp = self._post(path, data=data)
                body = (resp.text or "").strip()
                if resp.status_code != 200:
                    last_error = JwxtError("接口 {} 返回 HTTP {}".format(path, resp.status_code))
                    continue
                if self._looks_like_login_page(body):
                    raise SessionExpiredError("会话已失效，请重新登录")
                payload = json.loads(body)
                if self._schedule_payload_ok(payload):
                    self.kb_path = path  # 命中缓存，后续直接用
                    logger.info("课表接口确认：%s", path)
                    return payload
                last_error = JwxtError("接口 {} 返回结构不含课表数据".format(path))
            except SessionExpiredError:
                raise
            except (ValueError, JwxtError) as exc:
                last_error = exc
        raise JwxtError("未能获取课表数据：{}".format(last_error))

    @staticmethod
    def _schedule_payload_ok(payload) -> bool:
        """判断响应是否含课表数据（正方各版本字段差异的容错判断）。"""
        if isinstance(payload, dict):
            for key in ("kbList", "kbmcList", "items", "rows"):
                lst = payload.get(key)
                if isinstance(lst, list) and lst:
                    return True
            return False
        return isinstance(payload, list) and bool(payload)

    # ------------------------------------------------------------------
    # 解析：正方 JSON → demo Course 结构
    # ------------------------------------------------------------------
    def parse(self, raw) -> List[Dict]:
        return parse_zf_schedule(raw)


# ==========================================================================
# 模块级纯函数（便于单元测试）
# ==========================================================================

_CSRF_RE = re.compile(r'name="csrftoken"\s+value="([^"]+)"')


def extract_csrftoken(html: str) -> Optional[str]:
    m = _CSRF_RE.search(html or "")
    return m.group(1) if m else None


_ERROR_PATTERNS = [
    (re.compile(r"用户名或密码不正确|密码错误|账号或密码"), "用户名或密码不正确"),
    (re.compile(r"锁定|被锁|禁止登录"), "账号已被锁定（连续失败将锁定 3 分钟），请稍后再试"),
    (re.compile(r"验证码"), "需要验证码（失败次数过多），请稍后在浏览器中手动登录一次"),
]


def extract_login_error(html: str) -> Optional[str]:
    for pattern, message in _ERROR_PATTERNS:
        if pattern.search(html or ""):
            return message
    return None


def parse_zcd(zcd: str) -> List[int]:
    """解析正方周次串为具体周次集合。

    支持：'1-16周'、'1-15周(单)'、'1-16周(双)'、'1,3,5周'、'1-3,5,7周'、'第1-8周'。
    """
    text = str(zcd or "").strip().replace(" ", "")
    if not text:
        return []
    text = text.strip("第")
    odd_only = bool(re.search(r"[（(]\s*单|单周", text))
    even_only = bool(re.search(r"[（(]\s*双|双周", text))
    if even_only:
        odd_only = False
    text = re.sub(r"[（(]单[）)]|单周|[（(]双[）)]|双周", "", text)
    text = text.replace("周", "").strip()
    weeks: List[int] = []
    for segment in text.split(","):
        segment = segment.strip()
        if not segment:
            continue
        m = re.match(r"^(\d+)-(\d+)$", segment)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b:
                weeks.extend(range(a, b + 1))
        elif re.match(r"^\d+$", segment):
            weeks.append(int(segment))
    if odd_only:
        weeks = [w for w in weeks if w % 2 == 1]
    elif even_only:
        weeks = [w for w in weeks if w % 2 == 0]
    return sorted(set(weeks))


def parse_jcdm(jcdm, ksjc=None, jsjc=None, jcs=None) -> Optional[Dict]:
    """解析节次，兼容多种字段风格：
    - jcdm '0102'（四方连续编码，多数学校）
    - jcs '1-2' / jc '1-2节'（部分学校，如 gzmtu 实测）
    - ksjc/jsjc 分列
    """
    try:
        if ksjc and jsjc:
            return {"startPeriod": int(ksjc), "endPeriod": int(jsjc)}
        for candidate in (jcdm, jcs, ""):
            text = str(candidate or "").strip().replace("节", "")
            if not text:
                continue
            m = re.match(r"^(\d{2})(\d{2})$", text)
            if m:
                return {"startPeriod": int(m.group(1)), "endPeriod": int(m.group(2))}
            m = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", text)
            if m:
                return {"startPeriod": int(m.group(1)), "endPeriod": int(m.group(2))}
    except (TypeError, ValueError):
        pass
    return None


def _period_range(item: Dict) -> Optional[Dict]:
    """从一条排课记录中尽力解析节次（jcs > jc > jcdm/jsjc）。"""
    return parse_jcdm(item.get("jcdm"), item.get("ksjc"), item.get("jsjc"), item.get("jcs") or item.get("jc"))


def _merge_same_slot(courses: List[Dict]) -> List[Dict]:
    """合并「同课程 + 同星期 + 同节次」的多条记录（周次/教室/教师按周不同的场景）。

    典型：专业导论 8 位老师各上一周、工程制图 A6-106/A6-109/A6-602 分周次。
    合并后：周次取并集，教师/教室用「、」连接，备注记录按周明细。
    """
    merged: Dict[tuple, Dict] = {}
    order: List[tuple] = []
    for course in courses:
        key = (course["name"], course["dayOfWeek"], course["startPeriod"], course["endPeriod"])
        if key not in merged:
            merged[key] = dict(course)
            merged[key]["_parts"] = [{
                "weeks": list(course.get("weeks") or []),
                "teacher": course.get("teacher", ""),
                "location": course.get("location", ""),
            }]
            order.append(key)
            continue
        target = merged[key]
        target["_parts"].append({
            "weeks": list(course.get("weeks") or []),
            "teacher": course.get("teacher", ""),
            "location": course.get("location", ""),
        })
        target["credit"] = max(target["credit"], course["credit"])

    result: List[Dict] = []
    for key in order:
        course = merged[key]
        parts = course.pop("_parts")
        all_weeks = sorted({w for part in parts for w in part["weeks"]})
        teachers = []
        locations = []
        for part in parts:
            if part["teacher"] and part["teacher"] not in teachers:
                teachers.append(part["teacher"])
            if part["location"] and part["location"] not in locations:
                locations.append(part["location"])
        course["teacher"] = "、".join(teachers) if teachers else ""
        course["location"] = "、".join(locations) if locations else ""
        course["weeks"] = all_weeks
        course["weekRule"] = weeks_to_rule(all_weeks)
        if len(parts) > 1:
            details = []
            for part in parts:
                week_text = format_weeks_text(part["weeks"]) if part["weeks"] else "—"
                details.append("{} {} {}".format(
                    week_text, part["teacher"] or "教师待定", part["location"] or "地点待定").strip())
            course["note"] = "按周次安排不同：" + "；".join(details)
        result.append(course)
    return result



def parse_zf_schedule(raw) -> List[Dict]:
    """把正方课表响应解析为 demo Course 结构（不含 id/color）。

    字段容错：不同学校对教师/教室/类别字段命名有差异，逐一尝试。
    """
    if isinstance(raw, dict):
        items: List[Dict] = []
        for key in ("kbList", "kbmcList", "items", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                items = value
                break
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    courses: List[Dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("kcmc") or "").strip()
        if not name:
            continue
        teacher = str(item.get("xm") or item.get("jgxx") or "").strip()
        location = str(item.get("cdmc") or item.get("jsmc") or item.get("jxcdmcs") or "").strip()
        day = int(item.get("xqj") or 0)
        jcd = _period_range(item)
        weeks = parse_zcd(item.get("zcd") or item.get("zcdmc") or "")
        if not (1 <= day <= 7) or not jcd or not weeks:
            logger.debug("跳过无法解析的排课项：%s", {k: item.get(k) for k in ("kcmc", "xqj", "jcdm", "jcs", "zcd")})
            continue
        credit = item.get("xf") or 0
        category = str(item.get("kcxzmc") or item.get("kcxz") or "").strip() or "必修"
        note = str(item.get("bz") or "").strip()

        # 周次集合归约为规则；离散集合保留 weeks 显式存储
        rule = weeks_to_rule(weeks)
        course = {
            "name": name,
            "teacher": teacher,
            "location": location,
            "credit": float(credit),
            "dayOfWeek": day,
            "startPeriod": jcd["startPeriod"],
            "endPeriod": jcd["endPeriod"],
            "weekRule": rule,
            "category": category,
            "note": note,
            "source": "jwxt",
            "weeks": weeks,
        }
        courses.append(course)
    return _merge_same_slot(courses)
