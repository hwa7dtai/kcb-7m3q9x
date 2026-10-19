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
import base64
import json
import logging
import re
import socket
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

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


def _json_for_script(obj) -> str:
    """安全嵌入 <script> 的 JSON（转义 < 防止提前闭合）。"""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def build_offline_html(service) -> str:
    """生成单文件离线课表：内联 CSS / JS / 背景图 / 课表快照。

    打开方式：发给手机保存，用浏览器打开即可，无需联网、无需服务在运行。
    """
    index = (DEMO_DIR / "index.html").read_text(encoding="utf-8")
    css = (DEMO_DIR / "css" / "style.css").read_text(encoding="utf-8")
    store_js = (DEMO_DIR / "js" / "store.js").read_text(encoding="utf-8")
    particles_js = (DEMO_DIR / "js" / "particles.js").read_text(encoding="utf-8")
    app_js = (DEMO_DIR / "js" / "app.js").read_text(encoding="utf-8")
    image_b64 = base64.b64encode((DEMO_DIR / "assets" / "night-blossom.jpg").read_bytes()).decode("ascii")

    payload = {
        "semester": service.get_semester(),
        "courses": service.list_courses(),
        "exportedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    html = index
    html = html.replace("<title>课程表 · 个人版</title>", "<title>课程表 · 离线版</title>")
    html = re.sub(r'<link rel="stylesheet" href="css/style\.css"[^>]*>',
                  "<style>\n" + css + "\n</style>", html)
    html = re.sub(r'<link rel="manifest"[^>]*>', "", html)
    html = re.sub(r'<link rel="apple-touch-icon"[^>]*>', "", html)
    html = re.sub(r'<link rel="icon"[^>]*>', "", html)
    html = html.replace('src="assets/night-blossom.jpg"',
                        'src="data:image/jpeg;base64,' + image_b64 + '"')
    html = re.sub(r'<script src="js/store\.js"></script>',
                  "<script>window.__KCB_EMBEDDED__ = " + _json_for_script(payload) + ";</script>\n<script>\n"
                  + store_js + "\n</script>", html)
    html = re.sub(r'<script src="js/particles\.js"></script>',
                  "<script>\n" + particles_js + "\n</script>", html)
    html = re.sub(r'<script src="js/app\.js"></script>',
                  "<script>\n" + app_js + "\n</script>", html)
    # 移除 Service Worker 注册（file:// 下无意义）
    html = re.sub(r"<script>\s*/\* 注册 Service Worker[\s\S]*?</script>", "", html)
    return html


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

    @app.post("/api/demo/restore")
    def api_demo_restore():
        return handle(service.restore_backup)

    # ------------------------------------------------------------------
    # 离线单文件导出：把当前课表内联成一份 HTML（手机保存后可离线查看）
    # ------------------------------------------------------------------
    @app.get("/api/export/offline")
    def api_export_offline():
        html = build_offline_html(service)
        resp = Response(html, mimetype="text/html")
        resp.headers["Content-Disposition"] = (
            "attachment; filename=\"schedule-offline.html\"; "
            "filename*=UTF-8''%E8%AF%BE%E7%A8%8B%E8%A1%A8%E7%A6%BB%E7%BA%BF%E7%89%88.html")
        return resp

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
