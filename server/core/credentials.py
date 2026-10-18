"""凭据管理：学号密码存系统钥匙串（Windows 凭据管理器 / macOS Keychain / Secret Service）。

PLAN.md 5.2 / 第十章：凭据禁止明文落盘。keyring 后端不可用时显式报错，
绝不降级为文件存储。日志与异常信息不回显密码。
"""
from __future__ import annotations

from typing import Optional, Tuple

import keyring
from keyring.errors import KeyringError

from config import KEYRING_SERVICE


class CredentialError(Exception):
    """钥匙串不可用或操作失败。"""


def _user_key(student_id: str) -> str:
    """凭据条目名（含学号，便于未来多账号；学号本身不是机密）。"""
    return "jwxt-{}".format(student_id)


def save_credentials(student_id: str, password: str) -> None:
    if not student_id or not password:
        raise CredentialError("学号与密码不能为空")
    try:
        keyring.set_password(KEYRING_SERVICE, _user_key(student_id), password)
    except KeyringError as exc:
        raise CredentialError("系统钥匙串不可用，凭据未保存：{}".format(exc)) from exc


def get_credentials(student_id: str) -> Optional[str]:
    try:
        return keyring.get_password(KEYRING_SERVICE, _user_key(student_id))
    except KeyringError as exc:
        raise CredentialError("系统钥匙串不可用：{}".format(exc)) from exc


def delete_credentials(student_id: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, _user_key(student_id))
    except keyring.errors.PasswordDeleteError:
        pass
    except KeyringError as exc:
        raise CredentialError("系统钥匙串不可用：{}".format(exc)) from exc
