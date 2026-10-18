"""REST API + 静态托管：把 demo/ 前端与本后端整合为同一个服务。

接口契约与 demo/js/store.js 的 mock 行为一一对应（方法名 / 返回结构 / 错误文案），
前端数据层（store.js）替换为 fetch 调用后 UI 层无需改动。

运行：
    python app.py                 # 本机访问 http://127.0.0.1:8080
    python app.py --lan           # 局域网可访问（手机同 WiFi 打开）
    python app.py --port 9000
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# 让 server/ 下的模块可直接导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters.base import JwxtError  # noqa: E402
from adapters.zf import ZhengfangAdapter  # noqa: E402
from config import DEMO_DIR, JW_BASE_URL  # noqa: E402
from core import credentials  # noqa: E402
from core.models import ConflictError, NotFoundError, ValidationError  # noqa: E402
from core.service import ScheduleService  # noqa: E402
from core.storage import Storage  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("kcb")


def create_app(storage: Storage = None, adapter: ZhengfangAdapter = None) -> Flask:
    """工厂函数；测试时可注入内存库与假适配器。"""
    app = Flask(__name__, static_folder=str(DEMO_DIR), static_url_path="")
    app.json.ensure_ascii = False
    service = ScheduleService(storage or Storage(), adapter or ZhengfangAdapter(JW_BASE_URL))
    app.config["SERVICE"] = service

    # ------------------------------------------------------------------
    # 错误契约：与 store.js mock 的 reject(Error) 行为对齐
    # ------------------------------------------------------------------
    def error_response(status: int, message: str, conflict=None):
        payload = {"error": message}
        if conflict:
            payload["conflict"] = conflict
        return jsonify(payload), status

    @app.errorhandler(404)
    def _not_found(_e):
        # API 之外的 404（静态资源缺失）交由 Flask 默认处理
        if request.path.startswith("/api/"):
            return error_response(404, "接口不存在")
        return send_from_directory(DEMO_DIR, "index.html")

    @app.errorhandler(500)
    def _internal(_e):
        logger.exception("内部错误：%s", request.path)
        return error_response(500, "服务器内部错误，请查看服务端日志")

    def handle(fn, *args, **kwargs):
        """统一异常 → HTTP 错误契约。"""
        try:
            return jsonify(fn(*args, **kwargs))
        except ValidationError as exc:
            return error_response(400, str(exc))
        except ConflictError as exc:
            return error_response(400, str(exc), exc.conflict)
        except NotFoundError as exc:
            return error_response(404, str(exc))
        except JwxtError as exc:
            return error_response(502, str(exc))
        except credentials.CredentialError as exc:
            return error_response(500, str(exc))

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------
    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "version": "1.0.0"})

    @app.get("/api/semester")
    def api_semester():
        return handle(service.get_semester)

    @app.get("/api/week-dates")
    def api_week_dates():
        return handle(service.get_week_dates, request.args.get("week", 1))

    @app.get("/api/courses")
    def api_list_courses():
        return handle(service.list_courses, request.args.get("keyword", ""))

    @app.get("/api/courses/<course_id>")
    def api_get_course(course_id):
        return handle(service.get_course, course_id)

    @app.post("/api/courses")
    def api_create_course():
        return handle(service.create_course, request.get_json(force=True, silent=True) or {})

    @app.put("/api/courses/<course_id>")
    def api_update_course(course_id):
        return handle(service.update_course, course_id, request.get_json(force=True, silent=True) or {})

    @app.delete("/api/courses/<course_id>")
    def api_delete_course(course_id):
        return handle(service.delete_course, course_id)

    @app.get("/api/schedule")
    def api_schedule():
        return handle(service.get_schedule, request.args.get("week", 1))

    @app.post("/api/jwxt/fetch")
    def api_jwxt_fetch():
        payload = request.get_json(force=True, silent=True) or {}
        return handle(service.fetch_from_jwxt,
                      payload.get("studentId", ""), payload.get("password", ""))

    @app.post("/api/jwxt/import")
    def api_jwxt_import():
        payload = request.get_json(force=True, silent=True) or {}
        return handle(service.import_courses, payload.get("courses", []))

    @app.post("/api/jwxt/check-conflict")
    def api_check_conflict():
        payload = request.get_json(force=True, silent=True) or {}
        return handle(service.check_conflict, payload)

    @app.post("/api/demo/reset")
    def api_demo_reset():
        return handle(service.reset_demo)

    @app.post("/api/demo/clear")
    def api_demo_clear():
        return handle(service.clear_courses)

    # ------------------------------------------------------------------
    # 静态前端（demo/）
    # ------------------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(DEMO_DIR, "index.html")

    return app


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="大学课程表查看工具 · 本地服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(__import__("os").environ.get("KCB_PORT", 8080)))
    parser.add_argument("--lan", action="store_true", help="监听 0.0.0.0，允许手机同局域网访问")
    args = parser.parse_args()

    host = "0.0.0.0" if args.lan else args.host
    app = create_app()

    print("=" * 56)
    print("  课程表工具已启动")
    print("  本机访问:    http://127.0.0.1:{}".format(args.port))
    if host == "0.0.0.0":
        print("  局域网访问:  http://{}:{}（手机连同一 WiFi 打开）".format(_lan_ip(), args.port))
    print("  数据文件:    SQLite（个人数据，不部署公网）")
    print("=" * 56)
    app.run(host=host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
