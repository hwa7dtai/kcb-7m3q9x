"""API 契约测试：Flask test client，断言与 demo/test/store.test.js 一致的前端契约。

前端 store.js 替换为 fetch 后，本文件是「UI 不改」承诺的保障。
"""
from __future__ import annotations

import pytest

from app import create_app
from core.storage import Storage
from tests.test_service import FakeAdapter


@pytest.fixture
def client():
    app = create_app(storage=Storage(":memory:"), adapter=FakeAdapter())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def base_payload(**overrides):
    payload = {
        "name": "软件工程", "teacher": "测试教师", "location": "教学楼 Z-999",
        "credit": 2, "dayOfWeek": 6, "startPeriod": 1, "endPeriod": 2,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "选修", "color": "blue", "note": "",
    }
    payload.update(overrides)
    return payload


class TestHealthAndSemester:
    def test_health(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.get_json()["ok"] is True

    def test_semester_contract(self, client):
        res = client.get("/api/semester")
        data = res.get_json()
        assert res.status_code == 200
        assert data["totalWeeks"] == 19
        assert 1 <= data["currentWeek"] <= 19
        assert len(data["weekdayLabels"]) == 7
        assert data["totalPeriods"] == 10
        assert len(data["periodTimes"]) == 10
        assert data["periodTimes"][0] == {"start": "08:10", "end": "09:05"}

    def test_week_dates(self, client):
        res = client.get("/api/week-dates?week=1")
        dates = res.get_json()
        assert len(dates) == 7
        assert dates[0]["iso"] == "2026-08-31"
        assert dates[0]["label"] == "8/31"


class TestCoursesContract:
    def test_list_seed_10(self, client):
        data = client.get("/api/courses").get_json()
        assert len(data) == 10
        first = data[0]
        # decorate 契约字段
        for key in ("id", "name", "teacher", "location", "credit", "category", "color",
                    "note", "dayOfWeek", "startPeriod", "endPeriod", "weekRule",
                    "weeks", "weekText", "periodText", "timeText", "dayText"):
            assert key in first, "缺少字段 " + key
        assert first["periodText"] == "第 1-2 节"
        assert first["dayText"] == "周一"

    def test_search(self, client):
        assert len(client.get("/api/courses?keyword=王振宇").get_json()) == 1
        assert len(client.get("/api/courses?keyword=信息楼").get_json()) == 2
        assert client.get("/api/courses?keyword=不存在的课程").get_json() == []

    def test_get_one_and_404(self, client):
        data = client.get("/api/courses/c01").get_json()
        assert data["name"] == "高等数学 A（上）"
        res = client.get("/api/courses/not-exist")
        assert res.status_code == 404
        assert res.get_json()["error"] == "课程不存在或已被删除"

    def test_create(self, client):
        res = client.post("/api/courses", json=base_payload())
        assert res.status_code == 200
        created = res.get_json()
        assert created["id"]
        assert len(client.get("/api/courses").get_json()) == 11

    def test_create_validation_error(self, client):
        res = client.post("/api/courses", json=base_payload(name=""))
        assert res.status_code == 400
        assert res.get_json()["error"] == "课程名称不能为空"

    def test_create_conflict_with_conflict_payload(self, client):
        client.post("/api/courses", json=base_payload())
        res = client.post("/api/courses", json=base_payload(name="冲突课"))
        assert res.status_code == 400
        data = res.get_json()
        assert "冲突" in data["error"]
        assert data["conflict"]["name"] == "软件工程"

    def test_update(self, client):
        created = client.post("/api/courses", json=base_payload()).get_json()
        res = client.put("/api/courses/" + created["id"],
                         json=base_payload(name="软件工程（已改名）", location="教学楼 A-101"))
        assert res.status_code == 200
        assert res.get_json()["name"] == "软件工程（已改名）"

    def test_update_404(self, client):
        res = client.put("/api/courses/not-exist", json=base_payload())
        assert res.status_code == 404

    def test_delete(self, client):
        created = client.post("/api/courses", json=base_payload()).get_json()
        res = client.delete("/api/courses/" + created["id"])
        assert res.status_code == 200
        assert res.get_json()["id"] == created["id"]
        assert client.get("/api/courses/" + created["id"]).status_code == 404


class TestScheduleContract:
    def test_week_filtering(self, client):
        w1 = client.get("/api/schedule?week=1").get_json()
        w2 = client.get("/api/schedule?week=2").get_json()
        names1 = {c["name"] for c in w1["courses"]}
        names2 = {c["name"] for c in w2["courses"]}
        assert "计算机网络" in names1 and "计算机网络" not in names2
        assert "计算机组成原理实验" in names2 and "计算机组成原理实验" not in names1
        assert w1["week"] == 1

    def test_empty_week(self, client):
        data = client.get("/api/schedule?week=17").get_json()
        assert data["courses"] == []

    def test_time_text_contract(self, client):
        w1 = client.get("/api/schedule?week=1").get_json()
        math = [c for c in w1["courses"] if c["name"] == "高等数学 A（上）"][0]
        assert math["timeText"] == "08:10-10:00"
        w2 = client.get("/api/schedule?week=2").get_json()
        lab = [c for c in w2["courses"] if c["name"] == "计算机组成原理实验"][0]
        assert lab["timeText"] == "14:00-17:50"


class TestImportContract:
    def test_fetch_requires_credentials(self, client):
        res = client.post("/api/jwxt/fetch", json={"studentId": "", "password": "x"})
        assert res.status_code == 400
        assert res.get_json()["error"] == "请输入学号"
        res = client.post("/api/jwxt/fetch", json={"studentId": "2026001", "password": ""})
        assert res.get_json()["error"] == "请输入教务系统密码"

    def test_fetch_with_fake_adapter(self, client):
        app = client.application
        app.config["SERVICE"].adapter.courses = [
            {"name": "教务课程", "teacher": "教师", "location": "信息楼 1",
             "credit": 2, "dayOfWeek": 6, "startPeriod": 3, "endPeriod": 4,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "必修"}]
        res = client.post("/api/jwxt/fetch", json={"studentId": "20260001", "password": "x"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["studentId"] == "20260001"
        assert len(data["courses"]) == 1
        assert "教务系统" in data["source"]

    def test_import_flow(self, client):
        raw = [
            {"name": "高等数学 A（上）", "teacher": "李文博", "location": "教学楼 A-301",
             "credit": 4, "dayOfWeek": 1, "startPeriod": 1, "endPeriod": 2,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "必修"},
            {"name": "全新课程", "teacher": "新教师", "location": "新楼 1",
             "credit": 2, "dayOfWeek": 6, "startPeriod": 3, "endPeriod": 4,
             "weekRule": {"from": 1, "to": 16, "pattern": "all"}, "category": "选修"},
        ]
        before = len(client.get("/api/courses").get_json())
        res = client.post("/api/jwxt/import", json={"courses": raw})
        data = res.get_json()
        assert res.status_code == 200
        assert len(data["imported"]) == 1
        assert len(data["skipped"]) == 1
        assert data["skipped"][0]["conflictWith"] == "高等数学 A（上）"
        assert data["imported"][0]["source"] == "jwxt"
        after = len(client.get("/api/courses").get_json())
        assert after == before + 1

    def test_check_conflict_endpoint(self, client):
        res = client.post("/api/jwxt/check-conflict", json={
            "name": "x", "teacher": "y", "dayOfWeek": 1, "startPeriod": 1, "endPeriod": 2,
            "weekRule": {"from": 1, "to": 16, "pattern": "all"}})
        assert res.get_json()["name"] == "高等数学 A（上）"


class TestDemoControl:
    def test_clear_and_reset(self, client):
        assert client.post("/api/demo/clear").status_code == 200
        assert client.get("/api/courses").get_json() == []
        assert client.get("/api/schedule?week=1").get_json()["courses"] == []
        res = client.post("/api/demo/reset")
        assert res.get_json()["total"] == 10


class TestStaticFrontend:
    def test_index_served(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert b"\xe8\xaf\xbe\xe7\xa8\x8b\xe8\xa1\xa8" in res.data or "课程表".encode() in res.data

    def test_store_js_served(self, client):
        res = client.get("/js/store.js")
        assert res.status_code == 200
        assert b"CourseStore" in res.data

    def test_manifest_and_sw(self, client):
        assert client.get("/manifest.webmanifest").status_code == 200
        assert client.get("/sw.js").status_code == 200
