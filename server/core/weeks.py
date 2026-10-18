"""周次引擎：周次规则展开、当前周换算、周日期推算。

对应 PLAN.md 阶段四 WeekEngine：基于学期起始日期 + 本地日期计算当前周。
所有函数均为纯函数，便于单元测试。

设计核心：一切周次信息最终都归约为「具体周次集合」（有序整数列表）。
- 规则 {from, to, pattern} 可精确表达的（连续 / 单周 / 双周）：展开为集合。
- 教务系统返回离散周的（如 3,5,7）：直接以集合存储，展示时紧凑列出。
"""
from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional


def expand_weeks(rule: Optional[Dict]) -> List[int]:
    """把周次规则 {from, to, pattern} 展开为具体周次数组。

    pattern: 'all' 每周 | 'odd' 单周 | 'even' 双周
    """
    if not rule:
        return []
    try:
        start = int(rule["from"])
        end = int(rule["to"])
    except (KeyError, TypeError, ValueError):
        return []
    if start > end:
        return []
    pattern = rule.get("pattern") or "all"
    weeks = []
    for w in range(start, end + 1):
        if pattern == "all" or (pattern == "odd" and w % 2 == 1) or (pattern == "even" and w % 2 == 0):
            weeks.append(w)
    return weeks


def weeks_to_rule(weeks: List[int]) -> Dict:
    """把周次集合归约为 {from, to, pattern} 规则。

    三种形态可精确表达：连续（all）、单周（odd）、双周（even）；
    离散集合（如 3,5,7）无法用 from/to/pattern 精确表达，返回 pattern='discrete'，
    此时调用方必须保留原始 weeks 集合。
    """
    uniq = sorted(set(int(w) for w in weeks))
    if not uniq:
        return {"from": 1, "to": 1, "pattern": "all"}
    start, end = uniq[0], uniq[-1]
    full = list(range(start, end + 1))
    if uniq == full:
        return {"from": start, "to": end, "pattern": "all"}
    if uniq == [w for w in full if w % 2 == 1]:
        return {"from": start, "to": end, "pattern": "odd"}
    if uniq == [w for w in full if w % 2 == 0]:
        return {"from": start, "to": end, "pattern": "even"}
    return {"from": start, "to": end, "pattern": "discrete"}


def format_weeks_text(weeks: List[int]) -> str:
    """把具体周次集合格式化为可读文本，风格与前端 demo 一致。

    连续：第 1-16 周；单周：第 1-15 周(单周)；双周：第 2-16 周(双周)；离散：第 3,5,7 周。
    """
    if not weeks:
        return "未设置"
    uniq = sorted(set(int(w) for w in weeks))
    rule = weeks_to_rule(uniq)
    if rule["pattern"] == "all":
        return "第 {}-{} 周".format(rule["from"], rule["to"])
    if rule["pattern"] == "odd":
        return "第 {}-{} 周(单周)".format(rule["from"], rule["to"])
    if rule["pattern"] == "even":
        return "第 {}-{} 周(双周)".format(rule["from"], rule["to"])
    return "第 " + ",".join(str(w) for w in uniq) + " 周"


def format_week_rule(rule: Optional[Dict]) -> str:
    """周次规则的可读描述，输出与 demo/js/store.js formatWeekRule 一致。"""
    if not rule:
        return "未设置"
    suffix = "(单周)" if rule.get("pattern") == "odd" else ("(双周)" if rule.get("pattern") == "even" else "")
    return "第 {}-{} 周{}".format(rule.get("from"), rule.get("to"), suffix)


def period_time_range(period_times: List[Dict], start_period: int, end_period: int) -> str:
    """起止节次对应的上课时间范围，如 '08:00-09:40'。"""
    if not (1 <= start_period <= len(period_times)) or not (1 <= end_period <= len(period_times)):
        return ""
    a = period_times[start_period - 1]
    b = period_times[end_period - 1]
    return "{}-{}".format(a["start"], b["end"])


def parse_date(value: str) -> _dt.date:
    """'YYYY-MM-DD' → date。"""
    return _dt.date.fromisoformat(str(value)[:10])


def compute_current_week(start_date: str, total_weeks: int, today: Optional[_dt.date] = None) -> int:
    """按本地日期计算当前教学周，越界收敛到 [1, total_weeks]。"""
    start = parse_date(start_date)
    today = today or _dt.date.today()
    diff_days = (today - start).days
    week = diff_days // 7 + 1
    if week < 1:
        week = 1
    if week > total_weeks:
        week = total_weeks
    return week


def week_dates(start_date: str, week: int) -> List[_dt.date]:
    """某一教学周（week 从 1 开始）的 7 个日期，周一开头。"""
    start = parse_date(start_date) + _dt.timedelta(days=(week - 1) * 7)
    return [start + _dt.timedelta(days=i) for i in range(7)]


def week_dates_payload(start_date: str, week: int) -> List[Dict]:
    """某一周每天的日期（前端 getWeekDates 契约：iso + label）。"""
    out = []
    for d in week_dates(start_date, week):
        out.append({
            "iso": "{:04d}-{:02d}-{:02d}".format(d.year, d.month, d.day),
            "label": "{}/{}".format(d.month, d.day),
        })
    return out
