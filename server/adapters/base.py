"""适配层抽象：隔离教务系统差异（PLAN.md 第三章）。

向上只暴露四个动作：
    fetch_session()          建立会话，取 JSESSIONID 与 csrftoken
    login(credentials)       取公钥、加密密码、提交登录
    fetch_schedule_raw(term)  携带会话取课表原始数据
    parse(raw)               解析为结构化课表

教务系统改版时只需新增/修改一个 Adapter，其余层不动。
"""
from __future__ import annotations

import abc
from typing import Dict, List


class JwxtError(Exception):
    """教务系统交互失败（网络 / 会话 / 解析）。"""


class LoginError(JwxtError):
    """登录失败（账号密码错误 / 锁定）。"""


class SessionExpiredError(JwxtError):
    """会话失效（响应被重定向回登录页）。"""


class BaseAdapter(abc.ABC):
    """教务系统适配器基类。session 由外部注入，便于测试时替换为假会话。"""

    name = "base"

    def __init__(self, base_url: str, session=None):
        self.base_url = base_url.rstrip("/")
        self.session = session  # requests.Session 或测试假件

    @abc.abstractmethod
    def fetch_session(self) -> Dict:
        """返回 {'csrftoken': ...}；JSESSIONID 由注入的 session 自行持有。"""

    @abc.abstractmethod
    def login(self, student_id: str, password: str) -> None:
        """登录成功返回 None，失败抛 LoginError。"""

    @abc.abstractmethod
    def fetch_schedule_raw(self, term: Dict) -> object:
        """term: {'xnm': 学年, 'xqm': 学期} 或适配器自定义；返回原始数据。"""

    @abc.abstractmethod
    def parse(self, raw) -> List[Dict]:
        """解析原始数据为课程列表（demo Course 结构，不含 id/color）。"""
