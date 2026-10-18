"""共享 fixtures。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # server/

import core.credentials as credentials  # noqa: E402
from core.storage import Storage  # noqa: E402


@pytest.fixture(autouse=True)
def safe_keyring(monkeypatch):
    """全部测试隔离系统钥匙串：绝不真读写凭据管理器。"""
    monkeypatch.setattr(credentials, "save_credentials", lambda sid, pwd: None)
    monkeypatch.setattr(credentials, "get_credentials", lambda sid: None)
    monkeypatch.setattr(credentials, "delete_credentials", lambda sid: None)


@pytest.fixture
def storage():
    """内存库，每个测试独立。"""
    return Storage(":memory:")


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def zf_sample(fixture_dir):
    with open(fixture_dir / "zf_xskbcx_sample.json", encoding="utf-8") as f:
        return json.load(f)
