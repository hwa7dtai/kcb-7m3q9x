"""正方课表解析器测试：基于脱敏夹具断言课程数 / 节次 / 周次 / 教师 / 教室。"""
from __future__ import annotations

import pytest

from adapters.zf import parse_jcdm, parse_zcd, parse_zf_schedule


class TestParseZcd:
    def test_contiguous(self):
        assert parse_zcd("1-16周") == list(range(1, 17))

    def test_odd(self):
        assert parse_zcd("1-15周(单)") == [1, 3, 5, 7, 9, 11, 13, 15]

    def test_even(self):
        assert parse_zcd("2-16周(双)") == [2, 4, 6, 8, 10, 12, 14, 16]

    def test_discrete(self):
        assert parse_zcd("3,5,7周") == [3, 5, 7]

    def test_mixed(self):
        assert parse_zcd("1-3,5,7周") == [1, 2, 3, 5, 7]

    def test_short(self):
        assert parse_zcd("1-8周") == list(range(1, 9))

    def test_empty(self):
        assert parse_zcd("") == []
        assert parse_zcd(None) == []

    def test_fullwidth_paren(self):
        assert parse_zcd("1-6周（单）") == [1, 3, 5]


class TestParseJcdm:
    def test_standard(self):
        assert parse_jcdm("0102") == {"startPeriod": 1, "endPeriod": 2}

    def test_four_period_lab(self):
        assert parse_jcdm("0508") == {"startPeriod": 5, "endPeriod": 8}

    def test_ksjc_jsjc_fallback(self):
        assert parse_jcdm(None, ksjc=9, jsjc=10) == {"startPeriod": 9, "endPeriod": 10}

    def test_invalid(self):
        assert parse_jcdm("") is None
        assert parse_jcdm(None) is None


class TestParseSchedule:
    def test_course_count(self, zf_sample):
        courses = parse_zf_schedule(zf_sample)
        assert len(courses) == 12

    def test_field_mapping(self, zf_sample):
        courses = {c["name"]: c for c in parse_zf_schedule(zf_sample)}
        ds = courses["数据结构"]
        assert ds["teacher"] == "王振宇"
        assert ds["location"] == "信息楼 402"
        assert ds["dayOfWeek"] == 2
        assert ds["startPeriod"] == 1 and ds["endPeriod"] == 2
        assert ds["weekRule"] == {"from": 1, "to": 16, "pattern": "all"}
        assert ds["credit"] == 3
        assert ds["category"] == "必修"
        assert ds["source"] == "jwxt"

    def test_odd_week_course(self, zf_sample):
        courses = {c["name"]: c for c in parse_zf_schedule(zf_sample)}
        net = courses["计算机网络"]
        assert net["weekRule"]["pattern"] == "odd"
        assert net["weekRule"]["from"] == 1 and net["weekRule"]["to"] == 15

    def test_even_week_lab(self, zf_sample):
        courses = {c["name"]: c for c in parse_zf_schedule(zf_sample)}
        lab = courses["计算机组成原理实验"]
        assert lab["startPeriod"] == 5 and lab["endPeriod"] == 8
        assert lab["weekRule"]["pattern"] == "even"

    def test_discrete_week_course_keeps_explicit_weeks(self, zf_sample):
        courses = {c["name"]: c for c in parse_zf_schedule(zf_sample)}
        disc = courses["离散数学"]
        assert disc["weekRule"]["pattern"] == "discrete"
        assert disc["weeks"] == [2, 4, 7]

    def test_odd_list_weeks_reduce_to_rule(self, zf_sample):
        # "3,5,7周" 形态恰为 3-7 单周，应归约为规则；具体周集合始终保留
        courses = {c["name"]: c for c in parse_zf_schedule({"kbList": [
            {"kcmc": "短课", "xm": "教师", "jsmc": "楼", "xqj": 1, "jcdm": "0102", "zcd": "3,5,7周"}]})}
        assert courses["短课"]["weekRule"] == {"from": 3, "to": 7, "pattern": "odd"}
        assert courses["短课"]["weeks"] == [3, 5, 7]

    def test_night_course(self, zf_sample):
        courses = {c["name"]: c for c in parse_zf_schedule(zf_sample)}
        lin = courses["线性代数"]
        assert lin["startPeriod"] == 9 and lin["endPeriod"] == 10
        assert lin["note"] == "晚间课程"

    def test_short_course(self, zf_sample):
        courses = {c["name"]: c for c in parse_zf_schedule(zf_sample)}
        short = courses["形势与政策"]
        assert short["weekRule"] == {"from": 1, "to": 8, "pattern": "all"}

    def test_skips_unparseable_items(self):
        raw = {"kbList": [
            {"kcmc": "完整课程", "xqj": 1, "jcdm": "0102", "zcd": "1-16周"},
            {"kcmc": "缺星期", "jcdm": "0102", "zcd": "1-16周"},
            {"kcmc": "缺节次", "xqj": 1, "zcd": "1-16周"},
            {"kcmc": "缺周次", "xqj": 1, "jcdm": "0102"},
            {"xqj": 1, "jcdm": "0102", "zcd": "1-16周"},  # 缺名称
        ]}
        courses = parse_zf_schedule(raw)
        assert len(courses) == 1

    def test_accepts_list_payload(self):
        raw = [{"kcmc": "列表形态", "xqj": 3, "jcdm": "0506", "zcd": "2-16周(双)"}]
        courses = parse_zf_schedule(raw)
        assert len(courses) == 1 and courses[0]["weekRule"]["pattern"] == "even"

    def test_empty(self):
        assert parse_zf_schedule({"kbList": []}) == []
        assert parse_zf_schedule(None) == []


class TestRealGzmtuSample:
    """gzmtu 真实响应（脱敏）解析回归：jcs/zcd 字段风格 + 同时段合并。"""

    @pytest.fixture
    def real(self, fixture_dir):
        import json
        with open(fixture_dir / "zf_gzmtu_real_sample.json", encoding="utf-8") as f:
            return json.load(f)

    def test_merged_course_count(self, real):
        # 32 条排课 → 合并同课程同时段后 21 个课表格位
        courses = parse_zf_schedule(real)
        assert len(courses) == 21

    def test_teacher_rotation_merged(self, real):
        courses = {c["name"]: c for c in parse_zf_schedule(real) if c["dayOfWeek"] == 3}
        intro = courses["专业导论"]
        assert intro["startPeriod"] == 7 and intro["endPeriod"] == 8
        assert intro["weeks"] == [4, 5, 6, 7, 8, 9, 10, 11]
        assert intro["teacher"].count("、") == 7  # 8 位老师轮换
        assert "按周次安排不同" in intro["note"]

    def test_room_change_merged(self, real):
        courses = [c for c in parse_zf_schedule(real) if c["name"] == "工程制图与CAD"]
        monday = [c for c in courses if c["dayOfWeek"] == 1][0]
        assert monday["weeks"] == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
        assert monday["location"].count("、") == 2  # 三个教室分周次 → 两个顿号

    def test_english_odd_weeks(self, real):
        courses = [c for c in parse_zf_schedule(real) if c["name"] == "大学英语AⅠ"]
        tuesday = [c for c in courses if c["dayOfWeek"] == 2][0]
        assert tuesday["weeks"] == [5, 7, 9, 11, 13]
        assert tuesday["weekRule"]["pattern"] == "odd"

    def test_credit_and_category(self, real):
        courses = [c for c in parse_zf_schedule(real) if c["name"] == "高等数学AⅠ"]
        assert courses[0]["credit"] == 5
        assert courses[0]["category"] == "必修"

    def test_single_week_course(self, real):
        courses = [c for c in parse_zf_schedule(real) if c["name"] == "职业规划"]
        assert len(courses) == 1
        assert courses[0]["weeks"] == [8]

    def test_max_week_reaches_19(self, real):
        all_weeks = {w for c in parse_zf_schedule(real) for w in c["weeks"]}
        assert 19 in all_weeks
