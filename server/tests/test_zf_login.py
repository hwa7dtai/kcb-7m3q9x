"""正方登录链路测试：假会话 + 真 RSA 加密验证，不触网。

覆盖：csrftoken 提取、公钥获取、RSA PKCS#1 v1.5 加解密一致、
登录表单字段完整、登录失败/锁定识别、课表接口候选尝试与命中缓存。
"""
from __future__ import annotations

import base64
import json

import pytest
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

import adapters.zf as zf_module
from adapters.zf import ZhengfangAdapter, extract_csrftoken, extract_login_error

BASE = "http://jwx.example.edu.cn"


def _b64_of_int(value: int) -> str:
    return base64.b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big")).decode()


LOGIN_HTML = (
    '<html><body><form id="loginForm" method="post">'
    '<input type="hidden" name="csrftoken" value="b1639244-446d-4dcc-87c9-1db1b1fa5b56"/>'
    '<input id="yhm" name="yhm"/><input id="mm" name="mm" type="password"/>'
    "</form></body></html>"
)

LOGGED_IN_HTML = '<html><body><div id="app">主页框架</div></body></html>'

WRONG_PASSWORD_HTML = (
    '<html><body><div class="zf-tip">用户名或密码不正确，请重新输入</div>'
    '<input type="hidden" name="csrftoken" value="t2"/>'
    '<input id="yhm" name="yhm"/><input id="mm" name="mm" type="password"/>'
    "</body></html>"
)

LOCKED_HTML = (
    '<html><body><div class="zf-tip">账号已被锁定，请稍后再试</div>'
    '<input type="hidden" name="csrftoken" value="t3"/>'
    '<input id="yhm" name="yhm"/><input id="mm" name="mm" type="password"/>'
    "</body></html>"
)

KB_SAMPLE = {"kbList": [{"kcmc": "数据结构", "xm": "王振宇", "jsmc": "信息楼 402",
                         "xqj": 2, "jcdm": "0102", "zcd": "1-16周"}]}


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """按 URL 前缀分发响应；记录全部请求供断言。密码错误/锁定可注入。"""

    def __init__(self, login_outcome="ok", kb_paths=None):
        self.login_outcome = login_outcome  # ok | wrong | locked
        self.kb_paths = kb_paths  # dict path→payload；None 表示全部返回样本
        self.get_calls = []
        self.post_calls = []

    def get(self, url, timeout=None, **kw):
        self.get_calls.append(url)
        if "login_slogin" in url:
            return FakeResponse(200, LOGIN_HTML)
        if "login_getPublicKey" in url:
            return FakeResponse(200, payload=self.public_key)
        raise AssertionError("unexpected GET " + url)

    def post(self, url, data=None, timeout=None, **kw):
        self.post_calls.append((url, data))
        if "yhgl_cxXxqrCheck" in url:
            return FakeResponse(200, payload={"isSuccess": True})
        if "login_slogin" in url:
            if self.login_outcome == "ok":
                return FakeResponse(200, LOGGED_IN_HTML)
            if self.login_outcome == "wrong":
                return FakeResponse(200, WRONG_PASSWORD_HTML)
            return FakeResponse(200, LOCKED_HTML)
        if "/kbcx/" in url:
            path = url[len(BASE):]
            if self.kb_paths is None or path in self.kb_paths:
                return FakeResponse(200, json.dumps(self.kb_paths.get(path) if self.kb_paths else KB_SAMPLE))
            return FakeResponse(200, "")
        if "logout" in url:
            return FakeResponse(200, "ok")
        raise AssertionError("unexpected POST " + url)

    # 由测试注入公钥（配套私钥用于解密验证）
    public_key = {"modulus": "", "exponent": "AQAB"}


@pytest.fixture(autouse=True)
def no_request_interval(monkeypatch):
    monkeypatch.setattr(zf_module, "REQUEST_INTERVAL", 0)


@pytest.fixture
def keypair():
    key = RSA.generate(1024)
    pub = {
        "modulus": _b64_of_int(key.n),
        "exponent": _b64_of_int(key.e),
    }
    return key, pub


@pytest.fixture
def adapter(keypair):
    key, pub = keypair
    session = FakeSession()
    session.public_key = pub
    session.private_key = key
    return ZhengfangAdapter(BASE, session)


class TestCsrftoken:
    def test_extract(self):
        assert extract_csrftoken(LOGIN_HTML) == "b1639244-446d-4dcc-87c9-1db1b1fa5b56"

    def test_missing(self):
        assert extract_csrftoken("<html></html>") is None

    def test_fetch_session(self, adapter):
        info = adapter.fetch_session()
        assert info["csrftoken"] == "b1639244-446d-4dcc-87c9-1db1b1fa5b56"


class TestLoginErrorExtraction:
    def test_wrong_password(self):
        assert extract_login_error(WRONG_PASSWORD_HTML) is not None

    def test_locked(self):
        assert "锁定" in extract_login_error(LOCKED_HTML)

    def test_no_error(self):
        assert extract_login_error(LOGGED_IN_HTML) is None


class TestRsaEncrypt:
    def test_roundtrip(self, keypair):
        key, pub = keypair
        encrypted = ZhengfangAdapter.rsa_encrypt("S3cret密码!", pub["modulus"], pub["exponent"])
        raw = base64.b64decode(encrypted)
        cipher = PKCS1_v1_5.new(key)
        sentinel = object()
        decrypted = cipher.decrypt(raw, sentinel)
        assert decrypted != sentinel
        assert decrypted.decode("utf-8") == "S3cret密码!"

    def test_output_is_base64(self, keypair):
        _, pub = keypair
        encrypted = ZhengfangAdapter.rsa_encrypt("x", pub["modulus"], pub["exponent"])
        base64.b64decode(encrypted)  # 不抛错即为合法 base64


class TestLoginFlow:
    def test_login_success_posts_full_form(self, adapter):
        adapter.fetch_session()
        adapter.login("20260001", "pass123")

        login_posts = [c for c in adapter.session.post_calls if "login_slogin" in c[0]]
        # 有且只有一次登录提交
        assert len(login_posts) == 1
        url, form = login_posts[0]
        assert form["yhm"] == "20260001"
        assert form["mm"] != "pass123"  # 密码必须已加密
        assert form["csrftoken"] == "b1639244-446d-4dcc-87c9-1db1b1fa5b56"
        assert form["mmsfjm"] == "1"
        assert form["xxdm"] == "11106"
        for field in ("dlmmsfknt", "ydappsfbldlzt", "yzcskz", "dlsbsdsj", "language"):
            assert field in form

    def test_encrypted_password_matches_rsa(self, adapter):
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        _, form = [c for c in adapter.session.post_calls if "login_slogin" in c[0]][0]
        cipher = PKCS1_v1_5.new(adapter.session.private_key)
        decrypted = cipher.decrypt(base64.b64decode(form["mm"]), b"FAIL")
        assert decrypted == b"pass123"

    def test_precheck_called_before_login(self, adapter):
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        urls = [u for u, _ in adapter.session.post_calls]
        check_idx = next(i for i, u in enumerate(urls) if "yhgl_cxXxqrCheck" in u)
        login_idx = next(i for i, u in enumerate(urls) if "login_slogin" in u)
        assert check_idx < login_idx
        assert adapter.session.post_calls[check_idx][1] == {"yhm": "20260001"}

    def test_wrong_password_raises_login_error(self, adapter):
        adapter.session.login_outcome = "wrong"
        adapter.fetch_session()
        from adapters.base import LoginError
        with pytest.raises(LoginError) as exc:
            adapter.login("20260001", "bad")
        assert "用户名或密码" in str(exc.value)

    def test_locked_account_message(self, adapter):
        adapter.session.login_outcome = "locked"
        adapter.fetch_session()
        from adapters.base import LoginError
        with pytest.raises(LoginError) as exc:
            adapter.login("20260001", "bad")
        assert "锁定" in str(exc.value)


class TestLazySession:
    def test_session_created_on_demand(self, monkeypatch):
        """未注入会话时自动创建 requests.Session（修复线上 500：session=None）。"""
        import requests
        adapter = ZhengfangAdapter(BASE)  # 不传 session
        assert adapter.session is None
        sess = adapter._ensure_session()
        assert isinstance(sess, requests.Session)
        assert adapter._ensure_session() is sess  # 复用同一会话

    def test_default_session_mimics_browser(self):
        """默认会话携带浏览器 User-Agent（学校 WAF 会拦截 python-requests 特征）。"""
        adapter = ZhengfangAdapter(BASE)
        sess = adapter._ensure_session()
        ua = sess.headers.get("User-Agent", "")
        assert "python-requests" not in ua.lower()
        assert "Mozilla" in ua and "Chrome" in ua


class TestFetchSchedule:
    def test_tries_candidates_and_caches(self, adapter):
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        raw = adapter.fetch_schedule_raw({"xnm": "2026", "xqm": 3})
        assert adapter.kb_path == zf_module.JW_KB_CANDIDATES[0]

        kb_posts = [c for c in adapter.session.post_calls if "/kbcx/" in c[0]]
        assert len(kb_posts) >= 1
        url, data = kb_posts[0]
        assert data["xnm"] == "2026" and data["xqm"] == 3

    def test_second_candidate_hit(self, adapter):
        # 只让第二个候选返回数据
        session = adapter.session
        second = zf_module.JW_KB_CANDIDATES[1]
        session.kb_paths = {second: KB_SAMPLE}
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        adapter.fetch_schedule_raw({"xnm": "2026", "xqm": 3})
        assert adapter.kb_path == second
        tried = [u for u, _ in session.post_calls if "/kbcx/" in u]
        assert len(tried) == 2

    def test_cached_path_skips_candidates(self, adapter):
        adapter.kb_path = "/jwglxt/kbcx/xskbcx_cxXsKb.html"
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        adapter.fetch_schedule_raw({"xnm": "2026", "xqm": 3})
        tried = [u for u, _ in adapter.session.post_calls if "/kbcx/" in u]
        assert len(tried) == 1

    def test_session_expired_when_login_page_returned(self, adapter):
        session = adapter.session
        # 所有课表候选都返回登录页 → 判定会话失效
        session.kb_paths = {}
        session.post = lambda url, data=None, timeout=None, **kw: (
            FakeResponse(200, LOGIN_HTML) if "/kbcx/" in url
            else FakeSession.post(session, url, data, timeout, **kw))
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        from adapters.base import SessionExpiredError
        with pytest.raises(SessionExpiredError):
            adapter.fetch_schedule_raw({"xnm": "2026", "xqm": 3})

    def test_no_candidate_raises(self, adapter):
        session = adapter.session
        session.kb_paths = {}
        adapter.fetch_session()
        adapter.login("20260001", "pass123")
        from adapters.base import JwxtError
        with pytest.raises(JwxtError):
            adapter.fetch_schedule_raw({"xnm": "2026", "xqm": 3})
