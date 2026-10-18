"""正方课表解析器测试：基于脱敏夹具断言课程数 / 节次 / 周次 / 教师 / 教室。"""
from __future__ import annotations

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
        # "3,5,7周" 形态恰为 3-7 单周，应归约为规则而非离散集合
        courses = {c["name"]: c for c in parse_zf_schedule({"kbList": [
            {"kcmc": "短课", "xm": "教师", "jsmc": "楼", "xqj": 1, "jcdm": "0102", "zcd": "3,5,7周"}]})}
        assert courses["短课"]["weekRule"] == {"from": 3, "to": 7, "pattern": "odd"}
        assert "weeks" not in courses["短课"]

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
