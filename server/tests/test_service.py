"""应用层测试：CRUD、冲突检测、教务系统导入、自动登录重试保护。"""
from __future__ import annotations

import pytest

from adapters.base import JwxtError, LoginError
from core.models import ConflictError, NotFoundError, ValidationError
from core.service import ScheduleService
from core.storage import Storage


def make_service(storage=None, adapter=None):
    service = ScheduleService(storage or Storage(":memory:"), adapter)
    service.reset_demo()
    return service


def base_payload(**overrides):
    payload = {
        "name": "软件工程", "teacher": "测试教师", "location": "教学楼 Z-999",
        "credit": 2, "dayOfWeek": 6, "startPeriod": 1, "endPeriod": 2,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "选修", "color": "blue", "note": "",
    }
    payload.update(overrides)
    return payload


class FakeAdapter:
    """可控假适配器：记录调用次数，可注入失败。"""

    name = "zf"

    def __init__(self, failures=0, login_error=None, courses=None):
        self.failures = failures            # fetch_session 前 N 次网络失败
        self.login_error = login_error      # 明确登录错误（不重试）
        self.courses = courses or []
        self.fetch_session_calls = 0
        self.login_calls = 0

    def fetch_session(self):
        self.fetch_session_calls += 1
        if self.fetch_session_calls <= self.failures:
            raise ConnectionError("mock 网络故障")
        return {"csrftoken": "t"}

    def login(self, student_id, password):
        self.login_calls += 1
        if self.login_error:
            raise LoginError(self.login_error)

    def fetch_schedule_raw(self, term):
        return {"raw": True}

    def parse(self, raw):
        return list(self.courses)


class TestCrud:
    def test_seed_on_fresh_db(self):
        service = make_service()
        assert len(service.list_courses()) == 10

    def test_semester_shape(self):
        service = make_service()
        sem = service.get_semester()
        assert sem["totalWeeks"] == 18
        assert sem["startDate"] == "2026-09-07"
        assert 1 <= sem["currentWeek"] <= 18
        assert len(sem["weekdayLabels"]) == 7
        assert len(sem["periodTimes"]) == 12
        assert sem["totalPeriods"] == 12

    def test_create_and_conflict(self):
        service = make_service()
        created = service.create_course(base_payload())
        assert created["id"]
        assert created["weekText"] == "第 1-16 周"
        with pytest.raises(ConflictError) as exc:
            service.create_course(base_payload(name="冲突课"))
        assert exc.value.conflict["name"] == "软件工程"

    def test_validation_messages_match_frontend(self):
        service = make_service()
        with pytest.raises(ValidationError) as e:
            service.create_course(base_payload(name=""))
        assert str(e.value) == "课程名称不能为空"
        with pytest.raises(ValidationError) as e:
            service.create_course(base_payload(startPeriod=5, endPeriod=2))
        assert "节次" in str(e.value)
        with pytest.raises(ValidationError) as e:
            service.create_course(base_payload(weekRule={"from": 1, "to": 30, "pattern": "all"}))
        assert "周次" in str(e.value)

    def test_update_self_no_false_conflict(self):
        service = make_service()
        created = service.create_course(base_payload())
        updated = service.update_course(created["id"], base_payload(name="软件工程（改名）"))
        assert updated["name"] == "软件工程（改名）"

    def test_update_conflict_detected(self):
        service = make_service()
        a = service.create_course(base_payload())
        b = service.create_course(base_payload(dayOfWeek=7, name="另一门"))
        with pytest.raises(ConflictError):
            service.update_course(b["id"], base_payload(name="另一门改期", dayOfWeek=6))

    def test_delete_and_not_found(self):
        service = make_service()
        created = service.create_course(base_payload())
        assert service.delete_course(created["id"])["id"] == created["id"]
        with pytest.raises(NotFoundError):
            service.get_course(created["id"])
        with pytest.raises(NotFoundError):
            service.delete_course("not-exist")

    def test_schedule_week_filtering(self):
        service = make_service()
        w1 = service.get_schedule(1)
        w2 = service.get_schedule(2)
        names1 = {c["name"] for c in w1["courses"]}
        names2 = {c["name"] for c in w2["courses"]}
        assert "计算机网络" in names1 and "计算机网络" not in names2
        assert "计算机组成原理实验" in names2 and "计算机组成原理实验" not in names1
        assert service.get_schedule(17)["courses"] == []
        assert w1["courses"][0]["timeText"]  # decorate 携带时间文本

    def test_search(self):
        service = make_service()
        assert len(service.list_courses("王振宇")) == 1
        assert len(service.list_courses("信息楼")) == 2
        assert service.list_courses("不存在的课程") == []

    def test_clear_and_reset(self):
        service = make_service()
        service.clear_courses()
        assert service.list_courses() == []
        service.reset_demo()
        assert len(service.list_courses()) == 10


class TestImport:
    def test_import_with_conflicts(self):
        service = make_service()
        raw = [
            {"name": "高等数学 A（上）", "teacher": "李文博", "location": "教学楼 A-301",
             "credit": 4, "dayOfWeek": 1, "startPeriod": 1, "endPeriod": 2,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "必修"},
            {"name": "新课程", "teacher": "新教师", "location": "新楼 101",
             "credit": 2, "dayOfWeek": 6, "startPeriod": 3, "endPeriod": 4,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "选修"},
        ]
        result = service.import_courses(raw)
        assert len(result["imported"]) == 1
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["conflictWith"] == "高等数学 A（上）"
        assert result["imported"][0]["source"] == "jwxt"
        assert result["imported"][0]["color"]  # 自动分配颜色

    def test_reimport_blocked_by_conflict(self):
        service = make_service()
        raw = [{"name": "新课程", "teacher": "新教师", "location": "新楼 101",
                "credit": 2, "dayOfWeek": 6, "startPeriod": 3, "endPeriod": 4,
                "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "选修"}]
        first = service.import_courses(raw)
        second = service.import_courses(raw)
        assert len(first["imported"]) == 1
        assert len(second["imported"]) == 0
        assert "冲突" in second["skipped"][0]["reason"]

    def test_import_discrete_weeks(self):
        service = make_service()
        raw = [{"name": "离散周课", "teacher": "新教师", "location": "新楼 101",
                "credit": 2, "dayOfWeek": 6, "startPeriod": 3, "endPeriod": 4,
                "weekRule": {"from": 2, "to": 7, "pattern": "all"},
                "weeks": [2, 4, 7], "category": "选修"}]
        result = service.import_courses(raw)
        imported = result["imported"][0]
        assert imported["weeks"] == [2, 4, 7]
        assert imported["weekText"] == "第 2,4,7 周"
        # 第 4 周有、第 5 周无
        assert "离散周课" in {c["name"] for c in service.get_schedule(4)["courses"]}
        assert "离散周课" not in {c["name"] for c in service.get_schedule(5)["courses"]}

    def test_check_conflict_for_preview(self):
        service = make_service()
        conflict = service.check_conflict({
            "dayOfWeek": 1, "startPeriod": 1, "endPeriod": 2,
            "weekRule": {"from": 1, "to": 16, "pattern": "all"}})
        assert conflict and conflict["name"] == "高等数学 A（上）"
        assert service.check_conflict({
            "dayOfWeek": 7, "startPeriod": 1, "endPeriod": 2,
            "weekRule": {"from": 1, "to": 16, "pattern": "all"}}) is None


class TestFetchProtection:
    """PLAN.md 4.2：重试上限 2 次；密码错误不重试。"""

    def test_network_failure_retry_capped(self):
        adapter = FakeAdapter(failures=5)
        service = make_service(adapter=adapter)
        with pytest.raises(JwxtError) as exc:
            service.fetch_from_jwxt("20260001", "pass")
        # fetch_session 总调用次数 = MAX_LOGIN_ATTEMPTS
        assert adapter.fetch_session_calls == 2
        assert adapter.login_calls == 0

    def test_recovers_after_one_failure(self):
        adapter = FakeAdapter(failures=1, courses=[
            {"name": "教务课程", "teacher": "教师", "location": "楼",
             "credit": 2, "dayOfWeek": 6, "startPeriod": 5, "endPeriod": 6,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "必修"}])
        service = make_service(adapter=adapter)
        result = service.fetch_from_jwxt("20260001", "pass")
        assert len(result["courses"]) == 1
        assert adapter.fetch_session_calls == 2
        assert adapter.login_calls == 1

    def test_wrong_password_never_retries(self):
        adapter = FakeAdapter(login_error="用户名或密码不正确")
        service = make_service(adapter=adapter)
        with pytest.raises(JwxtError) as exc:
            service.fetch_from_jwxt("20260001", "bad")
        assert adapter.login_calls == 1          # 立即终止，绝不重试
        assert "锁号" in str(exc.value)           # 提示用户锁号风险

    def test_empty_credentials_rejected(self):
        service = make_service()
        with pytest.raises(ValidationError):
            service.fetch_from_jwxt("", "x")
        with pytest.raises(ValidationError):
            service.fetch_from_jwxt("20260001", "")

    def test_credentials_saved_to_keyring_on_success(self, monkeypatch):
        saved = {}
        monkeypatch.setattr("core.credentials.save_credentials",
                            lambda sid, pwd: saved.update({sid: pwd}))
        adapter = FakeAdapter(courses=[
            {"name": "教务课程", "teacher": "教师", "location": "楼",
             "credit": 2, "dayOfWeek": 6, "startPeriod": 5, "endPeriod": 6,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "必修"}])
        service = make_service(adapter=adapter)
        service.fetch_from_jwxt("20260001", "secret")
        assert saved == {"20260001": "secret"}

    def test_keyring_failure_does_not_break_fetch(self, monkeypatch):
        from core import credentials as cred
        monkeypatch.setattr(cred, "save_credentials",
                            lambda sid, pwd: (_ for _ in ()).throw(cred.CredentialError("无钥匙串")))
        adapter = FakeAdapter(courses=[
            {"name": "教务课程", "teacher": "教师", "location": "楼",
             "credit": 2, "dayOfWeek": 6, "startPeriod": 5, "endPeriod": 6,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "必修"}])
        service = make_service(adapter=adapter)
        result = service.fetch_from_jwxt("20260001", "secret")
        assert result["courses"]

    def test_empty_parse_result_raises_actionable_error(self):
        adapter = FakeAdapter(courses=[])
        service = make_service(adapter=adapter)
        with pytest.raises(JwxtError) as exc:
            service.fetch_from_jwxt("20260001", "pass")
        assert "recon" in str(exc.value)


class TestTermParams:
    def test_term_params_from_semester_id(self):
        service = make_service()
        assert service._term_params() == {"xnm": "2026", "xqm": 3}
