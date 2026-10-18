"""数据模型与业务规则：课程实体、字段校验、时间冲突检测。

模型与 demo/js/store.js 的 Course 结构保持一致：
  { id, name, teacher, location, credit, category, color, note,
    dayOfWeek, startPeriod, endPeriod, weekRule: {from,to,pattern},
    source?, weeks? }   # weeks 为离散周集合（仅教务系统离散排课时使用）
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config import PERIOD_TIMES, TOTAL_PERIODS, WEEKDAY_LABELS, SEMESTER_TOTAL_WEEKS
from core.weeks import expand_weeks, format_weeks_text, period_time_range


class ValidationError(Exception):
    """字段校验失败。message 与前端 mock 文案一致。"""


class ConflictError(Exception):
    """时间冲突。conflict 属性携带冲突课程。"""

    def __init__(self, message: str, conflict: Optional[Dict] = None):
        super().__init__(message)
        self.conflict = conflict


class NotFoundError(Exception):
    """课程不存在。"""


VALID_COLORS = ("blue", "teal", "amber", "purple", "rose", "green", "cyan")


def normalize_course(payload: Dict) -> Dict:
    """把任意输入（表单 / 教务系统）规整为内部课程结构（不含 id）。"""
    rule = payload.get("weekRule") or {}
    return {
        "name": str(payload.get("name") or "").strip(),
        "teacher": str(payload.get("teacher") or "").strip(),
        "location": str(payload.get("location") or "").strip(),
        "credit": float(payload.get("credit") or 0),
        "category": str(payload.get("category") or "必修"),
        "color": payload.get("color") if payload.get("color") in VALID_COLORS else "blue",
        "note": str(payload.get("note") or "").strip(),
        "dayOfWeek": int(payload.get("dayOfWeek") or 0),
        "startPeriod": int(payload.get("startPeriod") or 0),
        "endPeriod": int(payload.get("endPeriod") or 0),
        "weekRule": {
            "from": int(rule.get("from") or 0),
            "to": int(rule.get("to") or 0),
            "pattern": rule.get("pattern") or "all",
        },
        "source": payload.get("source"),
        # 分周次变化的教室/教师（合并导入时由适配层生成）：{"7": "A6-109", ...}
        "weekRooms": payload.get("weekRooms") or None,
        "weekTeachers": payload.get("weekTeachers") or None,
    }


def course_weeks(course: Dict) -> List[int]:
    """课程的具体上课周集合：离散集合优先，否则由规则展开。"""
    explicit = course.get("weeks")
    if explicit:
        return sorted(set(int(w) for w in explicit))
    return expand_weeks(course.get("weekRule"))


def validate(course: Dict, total_weeks: int = SEMESTER_TOTAL_WEEKS,
             total_periods: int = TOTAL_PERIODS) -> Optional[str]:
    """字段校验，返回错误文案或 None。文案与 demo/js/store.js validate 一致。"""
    if not course["name"]:
        return "课程名称不能为空"
    if not course["teacher"]:
        return "任课教师不能为空"
    if not (1 <= course["dayOfWeek"] <= 7):
        return "请选择正确的星期"
    sp, ep = course["startPeriod"], course["endPeriod"]
    if not (1 <= sp <= total_periods) or not (1 <= ep <= total_periods) or sp > ep:
        return "节次设置有误，需在 1-{} 节范围内，且开始节次不晚于结束节次".format(total_periods)
    rule = course["weekRule"]
    if not (1 <= rule["from"] <= total_weeks) or not (1 <= rule["to"] <= total_weeks) \
            or rule["from"] > rule["to"]:
        return "周次设置有误，需在 1-{} 周范围内".format(total_weeks)
    return None


def periods_overlap(a: Dict, b: Dict) -> bool:
    """同一天、节次区间重叠、且周次集合有交集，即为时间冲突。"""
    if a["dayOfWeek"] != b["dayOfWeek"]:
        return False
    if a["endPeriod"] < b["startPeriod"] or a["startPeriod"] > b["endPeriod"]:
        return False
    wa = set(course_weeks(a))
    wb = set(course_weeks(b))
    return bool(wa & wb)


def find_conflict(candidate: Dict, courses: List[Dict], exclude_id: Optional[str] = None) -> Optional[Dict]:
    """在课程列表中找出与 candidate 冲突的第一门课程。"""
    for c in courses:
        if exclude_id is not None and c.get("id") == exclude_id:
            continue
        if periods_overlap(candidate, c):
            return c
    return None


def decorate(course: Dict, period_times: Optional[List[Dict]] = None) -> Dict:
    """附加展示字段，输出与 demo/js/store.js decorate 一致的完整结构。"""
    period_times = period_times or PERIOD_TIMES
    out = dict(course)
    weeks = course_weeks(course)
    out["weeks"] = weeks
    out["weekText"] = format_weeks_text(weeks)
    out["periodText"] = "第 {}-{} 节".format(course["startPeriod"], course["endPeriod"])
    out["timeText"] = period_time_range(period_times, course["startPeriod"], course["endPeriod"])
    out["dayText"] = WEEKDAY_LABELS[course["dayOfWeek"] - 1] if 1 <= course["dayOfWeek"] <= 7 else ""
    return out


def sort_key(course: Dict):
    return (course["dayOfWeek"], course["startPeriod"])


def public_course(course: Dict) -> Dict:
    """输出对外的课程核心字段（去掉内部离散周集合等实现细节，保留前端契约字段）。"""
    keys = ("id", "name", "teacher", "location", "credit", "category", "color", "note",
            "dayOfWeek", "startPeriod", "endPeriod", "weekRule", "source")
    out = {k: course[k] for k in keys if course.get(k) is not None}
    return out
