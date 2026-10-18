"""周次引擎（WeekEngine）单元测试。"""
from __future__ import annotations

import datetime as dt

from core.weeks import (
    compute_current_week,
    expand_weeks,
    format_weeks_text,
    period_time_range,
    week_dates_payload,
    weeks_to_rule,
)


class TestExpandWeeks:
    def test_all(self):
        assert expand_weeks({"from": 1, "to": 5, "pattern": "all"}) == [1, 2, 3, 4, 5]

    def test_odd(self):
        assert expand_weeks({"from": 1, "to": 9, "pattern": "odd"}) == [1, 3, 5, 7, 9]

    def test_even(self):
        assert expand_weeks({"from": 2, "to": 8, "pattern": "even"}) == [2, 4, 6, 8]

    def test_even_from_odd_start(self):
        # 双周规则从奇数周开始：只保留范围内的偶数周
        assert expand_weeks({"from": 1, "to": 6, "pattern": "even"}) == [2, 4, 6]

    def test_invalid(self):
        assert expand_weeks(None) == []
        assert expand_weeks({"from": 5, "to": 1, "pattern": "all"}) == []
        assert expand_weeks({"from": "x", "to": 3, "pattern": "all"}) == []

    def test_missing_pattern_defaults_all(self):
        assert expand_weeks({"from": 1, "to": 2}) == [1, 2]


class TestWeeksToRule:
    def test_contiguous(self):
        assert weeks_to_rule([3, 4, 5]) == {"from": 3, "to": 5, "pattern": "all"}

    def test_odd_only(self):
        assert weeks_to_rule([1, 3, 5, 7]) == {"from": 1, "to": 7, "pattern": "odd"}

    def test_even_only(self):
        assert weeks_to_rule([2, 4, 6]) == {"from": 2, "to": 6, "pattern": "even"}

    def test_discrete(self):
        assert weeks_to_rule([3, 5, 7, 8]) == {"from": 3, "to": 8, "pattern": "discrete"}


class TestFormatWeeksText:
    def test_contiguous(self):
        assert format_weeks_text([1, 2, 3]) == "第 1-3 周"

    def test_odd(self):
        assert format_weeks_text([1, 3, 5]) == "第 1-5 周(单周)"

    def test_even(self):
        assert format_weeks_text([2, 4, 6]) == "第 2-6 周(双周)"

    def test_discrete(self):
        # 3,5,7 恰为 3-7 范围内的单周，可被规则精确表达
        assert format_weeks_text([3, 5, 7]) == "第 3-7 周(单周)"
        # 2,4,7 既非连续也非单双，走离散列表
        assert format_weeks_text([2, 4, 7]) == "第 2,4,7 周"

    def test_empty(self):
        assert format_weeks_text([]) == "未设置"


class TestCurrentWeek:
    def test_first_day(self):
        today = dt.date(2026, 9, 7)
        assert compute_current_week("2026-09-07", 18, today) == 1

    def test_mid_week1(self):
        assert compute_current_week("2026-09-07", 18, dt.date(2026, 9, 13)) == 1

    def test_week2_starts(self):
        assert compute_current_week("2026-09-07", 18, dt.date(2026, 9, 14)) == 2

    def test_before_start_clamps_to_1(self):
        assert compute_current_week("2026-09-07", 18, dt.date(2026, 8, 1)) == 1

    def test_after_end_clamps_to_total(self):
        assert compute_current_week("2026-09-07", 18, dt.date(2027, 3, 1)) == 18


class TestWeekDates:
    def test_week1_starts_on_monday(self):
        dates = week_dates_payload("2026-09-07", 1)
        assert dates[0]["iso"] == "2026-09-07"
        assert dates[6]["iso"] == "2026-09-13"

    def test_week5(self):
        dates = week_dates_payload("2026-09-07", 5)
        assert dates[0]["iso"] == "2026-10-05"
        assert dates[3]["label"] == "10/8"


class TestPeriodTimeRange:
    def test_periods_1_2(self):
        from config import PERIOD_TIMES
        assert period_time_range(PERIOD_TIMES, 1, 2) == "08:00-09:40"

    def test_periods_5_8(self):
        from config import PERIOD_TIMES
        assert period_time_range(PERIOD_TIMES, 5, 8) == "14:00-17:40"

    def test_out_of_range(self):
        from config import PERIOD_TIMES
        assert period_time_range(PERIOD_TIMES, 1, 13) == ""
