"""应用层：课表服务、缓存策略、教务系统导入（自动登录 + 重试保护）。

向上对接 REST API，向下调度存储层与适配层。
自动登录保护（PLAN.md 4.2）：
- 总尝试次数硬上限 2（连续失败 3 次锁号 3 分钟，绝不循环重试）
- 明确的账号密码错误不重试，立即终止
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from adapters.base import JwxtError, LoginError
from adapters.zf import ZhengfangAdapter
from config import (
    JW_BASE_URL,
    JW_KB_CANDIDATES,
    MAX_LOGIN_ATTEMPTS,
    PERIOD_TIMES,
    SEED_DEMO_DATA,
    TOTAL_PERIODS,
    WEEKDAY_LABELS,
    XQM_MAP,
)
from core import credentials
from core.models import (
    ConflictError,
    NotFoundError,
    ValidationError,
    decorate,
    find_conflict,
    normalize_course,
    public_course,
    sort_key,
    validate,
)
from core.seed import SEED_COURSES
from core.storage import Storage
from core.weeks import compute_current_week, expand_weeks, week_dates_payload

logger = logging.getLogger(__name__)

IMPORT_COLORS = ["blue", "teal", "amber", "purple", "rose", "green", "cyan"]


class ScheduleService:
    """课表应用服务（单例语义由 Flask app 持有）。"""

    def __init__(self, storage: Storage, adapter: Optional[ZhengfangAdapter] = None):
        self.storage = storage
        self.adapter = adapter or ZhengfangAdapter(JW_BASE_URL)
        self._id_seq = 100
        self._import_seq = 500
        self._maybe_seed()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def _maybe_seed(self) -> None:
        if not SEED_DEMO_DATA:
            return
        seeded = self.storage.get_meta("seeded")
        if not seeded:
            self.reset_demo()

    def reset_demo(self) -> Dict:
        """恢复演示种子数据。"""
        self.storage.replace_all(SEED_COURSES)
        self.storage.set_meta("seeded", "1")
        self._id_seq = 100
        self._import_seq = 500
        return {"total": len(SEED_COURSES)}

    # ------------------------------------------------------------------
    # 学期与周次（WeekEngine）
    # ------------------------------------------------------------------
    def get_semester(self) -> Dict:
        sem = self.storage.get_semester()
        sem["currentWeek"] = compute_current_week(sem["startDate"], sem["totalWeeks"])
        sem["weekdayLabels"] = list(WEEKDAY_LABELS)
        sem["totalPeriods"] = TOTAL_PERIODS
        sem["periodTimes"] = [dict(p) for p in PERIOD_TIMES]
        return sem

    def get_week_dates(self, week: int) -> List[Dict]:
        sem = self.storage.get_semester()
        week = min(max(int(week or 1), 1), sem["totalWeeks"])
        return week_dates_payload(sem["startDate"], week)

    # ------------------------------------------------------------------
    # 课程 CRUD
    # ------------------------------------------------------------------
    def list_courses(self, keyword: str = "") -> List[Dict]:
        return [decorate(c) for c in
                sorted(self.storage.list_courses(keyword), key=sort_key)]

    def get_course(self, course_id: str) -> Dict:
        found = self.storage.get_course(course_id)
        if not found:
            raise NotFoundError("课程不存在或已被删除")
        return decorate(found)

    def create_course(self, payload: Dict) -> Dict:
        course = normalize_course(payload)
        error = validate(course)
        if error:
            raise ValidationError(error)
        conflict = find_conflict(course, self.storage.list_courses())
        if conflict:
            raise ConflictError(
                "与已有课程《{}》时间冲突，请调整节次或周次".format(conflict["name"]),
                public_course(conflict),
            )
        course["id"] = self._next_id("c")
        self.storage.insert_course(course)
        return decorate(course)

    def update_course(self, course_id: str, payload: Dict) -> Dict:
        if not self.storage.get_course(course_id):
            raise NotFoundError("课程不存在或已被删除")
        course = normalize_course(payload)
        error = validate(course)
        if error:
            raise ValidationError(error)
        conflict = find_conflict(course, self.storage.list_courses(), exclude_id=course_id)
        if conflict:
            raise ConflictError(
                "与已有课程《{}》时间冲突，请调整节次或周次".format(conflict["name"]),
                public_course(conflict),
            )
        # 表单编辑只能表达 from/to/pattern；编辑动作总是以规则为准，清除离散周
        course.pop("weeks", None)
        if course["weekRule"]["pattern"] == "discrete":
            course["weekRule"] = {"from": 1, "to": 1, "pattern": "all"}
        self.storage.update_course(course_id, course)
        return decorate(self.storage.get_course(course_id))

    def delete_course(self, course_id: str) -> Dict:
        if not self.storage.delete_course(course_id):
            raise NotFoundError("课程不存在或已被删除")
        return {"id": course_id}

    def clear_courses(self) -> Dict:
        self.storage.clear_courses()
        return {"total": 0}

    # ------------------------------------------------------------------
    # 课表
    # ------------------------------------------------------------------
    def get_schedule(self, week: int) -> Dict:
        w = int(week or 1)
        courses = []
        for c in self.storage.list_courses():
            item = decorate(c)
            if w in set(item["weeks"]):
                courses.append(item)
        courses.sort(key=lambda c: (c["dayOfWeek"], c["startPeriod"]))
        return {"week": w, "courses": courses}

    # ------------------------------------------------------------------
    # 教务系统：自动登录 + 抓取（阶段三）
    # ------------------------------------------------------------------
    def _next_id(self, prefix: str) -> str:
        if prefix == "c":
            self._id_seq += 1
            return "c{}".format(self._id_seq)
        self._import_seq += 1
        return "j{}".format(self._import_seq)

    def _term_params(self) -> Dict:
        """由学期 id（形如 '2026-2027-1'）推算正方 xnm/xqm。"""
        sem = self.storage.get_semester()
        try:
            year_part, term_no = sem["id"].rsplit("-", 1)
            xnm = year_part.split("-")[0]
            return {"xnm": xnm, "xqm": XQM_MAP.get(int(term_no), 3)}
        except ValueError:
            return {"xnm": "", "xqm": ""}

    def fetch_from_jwxt(self, student_id: str, password: str) -> Dict:
        """自动登录教务系统并读取课表（总尝试次数硬上限 MAX_LOGIN_ATTEMPTS）。"""
        student_id = str(student_id or "").strip()
        password = str(password or "")
        if not student_id:
            raise ValidationError("请输入学号")
        if not password:
            raise ValidationError("请输入教务系统密码")

        term = self._term_params()
        last_error: Optional[Exception] = None
        courses: Optional[List[Dict]] = None
        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            try:
                self.adapter.fetch_session()
                self.adapter.login(student_id, password)
                raw = self.adapter.fetch_schedule_raw(term)
                courses = self.adapter.parse(raw)
                break
            except LoginError as exc:
                # 明确的登录失败（密码错误/锁定）不重试，防止触发锁号
                logger.warning("教务系统登录失败（学号 %s）：%s", student_id, exc)
                raise JwxtError(
                    "登录失败：{}。已停止自动重试（连续失败 3 次将锁号 3 分钟），"
                    "请核对账号密码或稍后手动登录一次。".format(exc)
                ) from exc
            except (JwxtError, ConnectionError, TimeoutError, OSError) as exc:
                last_error = exc
                logger.info("抓取失败（第 %s/%s 次）：%s", attempt, MAX_LOGIN_ATTEMPTS, exc)

        if courses is None:
            # 程序化登录被 WAF 拦截时，走浏览器会话兜底（需先用勘察脚本登录过一次）
            browser_result = self._fetch_via_browser(term)
            if browser_result is not None:
                return browser_result
            raise JwxtError(
                "未能从教务系统读取课表：{}。若教务系统开启了访问防护，请运行 "
                "「同步课表.bat / server/scripts/sync_from_browser.py」通过浏览器会话同步。".format(last_error)
            )
        if not courses:
            raise JwxtError("教务系统返回了课表但未解析出任何课程（接口可能改版，"
                            "请运行 server/scripts/recon_playwright.py 重新勘察）")
        from datetime import datetime
        self.storage.set_meta("last_fetch", datetime.now().isoformat(timespec="seconds"))
        # 登录成功后把凭据存入系统钥匙串，供一键刷新脚本使用（不含明文落盘）
        try:
            credentials.save_credentials(student_id, password)
        except credentials.CredentialError as exc:
            logger.warning("凭据未存入钥匙串：%s", exc)
        sem = self.storage.get_semester()
        return {
            "studentId": student_id,
            "semesterName": sem["name"],
            "source": "正方教务系统（{}）".format(self.adapter.name),
            "courses": courses,
        }

    def _fetch_via_browser(self, term: Dict) -> Optional[Dict]:
        """浏览器会话兜底取数；不可用时返回 None（不抛错，交由上层给最终提示）。"""
        from core import browser_fetch
        kb_path = getattr(self.adapter, "kb_path", None)
        try:
            raw = browser_fetch.fetch_raw_via_profile(
                JW_BASE_URL, [kb_path] if kb_path else JW_KB_CANDIDATES, term)
        except Exception as exc:  # 浏览器通道异常不掩盖原始错误
            logger.warning("浏览器通道失败：%s", exc)
            return None
        if raw is None:
            return None
        courses = self.adapter.parse(raw)
        if not courses:
            return None
        from datetime import datetime
        self.storage.set_meta("last_fetch", datetime.now().isoformat(timespec="seconds"))
        sem = self.storage.get_semester()
        logger.info("通过浏览器会话读取课表 %s 门", len(courses))
        return {
            "studentId": "",
            "semesterName": sem["name"],
            "source": "正方教务系统（浏览器会话）",
            "courses": courses,
        }

    # ------------------------------------------------------------------
    # 教务系统：批量导入（逐门校验 + 冲突检测，互不影响）
    # ------------------------------------------------------------------
    def import_courses(self, raw_list: List[Dict]) -> Dict:
        result = {"imported": [], "skipped": []}
        existing = self.storage.list_courses()
        for index, raw in enumerate(raw_list or []):
            course = normalize_course(raw)
            course["color"] = IMPORT_COLORS[index % len(IMPORT_COLORS)]
            course["source"] = "jwxt"
            if raw.get("weeks"):
                course["weeks"] = sorted(set(int(w) for w in raw["weeks"]))
                if course["weekRule"]["pattern"] == "all" and course["weeks"] != expand_weeks(course["weekRule"]):
                    course["weekRule"] = dict(course["weekRule"], pattern="discrete")
            error = validate(course)
            if error:
                result["skipped"].append({"name": course["name"], "reason": error})
                continue
            conflict = find_conflict(course, existing)
            if conflict:
                result["skipped"].append({
                    "name": course["name"],
                    "reason": "与《{}》时间冲突".format(conflict["name"]),
                    "conflictWith": conflict["name"],
                })
                continue
            course["id"] = self._next_id("j")
            self.storage.insert_course(course)
            existing.append(course)
            result["imported"].append(decorate(course))
        return result

    # ------------------------------------------------------------------
    # 冲突查询（前端导入预览用）
    # ------------------------------------------------------------------
    def check_conflict(self, payload: Dict) -> Optional[Dict]:
        course = normalize_course(payload)
        if payload.get("weeks"):
            course["weeks"] = sorted(set(int(w) for w in payload["weeks"]))
        conflict = find_conflict(course, self.storage.list_courses())
        return {"id": conflict["id"], "name": conflict["name"]} if conflict else None
