"""存储层：SQLite 持久化（课表 + 学期 + 元信息）。

设计要点：
- 单文件 SQLite，便于多学期管理与查询（PLAN.md 5.2）。
- 周次集合双轨存储：week_from/week_to/week_pattern 支撑表单编辑的规则表达，
  weeks_json 存储教务系统导入的离散周集合（pattern='discrete' 时生效）。
- 不存任何凭据（凭据走系统钥匙串，见 core/credentials.py）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Dict, List, Optional

from config import DB_PATH, DATA_DIR, SEMESTER_ID, SEMESTER_NAME, SEMESTER_START_DATE, SEMESTER_TOTAL_WEEKS


class Storage:
    """线程安全的 SQLite 封装（Flask 多线程 + 个人工具规模足够）。"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self.init_db()

    # ------------------------------------------------------------------
    # 连接与建库
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if self.db_path != ":memory:":
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._lock:
            if self._conn is None:
                self._conn = self._connect()
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS semester (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    total_weeks INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS courses (
                    id           TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    teacher      TEXT NOT NULL,
                    location     TEXT NOT NULL DEFAULT '',
                    credit       REAL NOT NULL DEFAULT 0,
                    category     TEXT NOT NULL DEFAULT '必修',
                    color        TEXT NOT NULL DEFAULT 'blue',
                    note         TEXT NOT NULL DEFAULT '',
                    day_of_week  INTEGER NOT NULL,
                    start_period INTEGER NOT NULL,
                    end_period   INTEGER NOT NULL,
                    week_from    INTEGER NOT NULL,
                    week_to      INTEGER NOT NULL,
                    week_pattern TEXT NOT NULL DEFAULT 'all',
                    weeks_json   TEXT,
                    source       TEXT,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    updated_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_courses_day ON courses(day_of_week, start_period);
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # 学期
    # ------------------------------------------------------------------
    def get_semester(self) -> Dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, name, start_date, total_weeks FROM semester WHERE id = ?", (SEMESTER_ID,)
            ).fetchone()
        if row:
            return {"id": row["id"], "name": row["name"],
                    "startDate": row["start_date"], "totalWeeks": row["total_weeks"]}
        # 首次运行写入默认学期（可用环境变量覆盖）
        sem = {"id": SEMESTER_ID, "name": SEMESTER_NAME,
               "startDate": SEMESTER_START_DATE, "totalWeeks": SEMESTER_TOTAL_WEEKS}
        self.save_semester(sem)
        return sem

    def save_semester(self, sem: Dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO semester (id, name, start_date, total_weeks) VALUES (?,?,?,?)",
                (sem["id"], sem["name"], sem["startDate"], int(sem["totalWeeks"])),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # 课程
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_course(row: sqlite3.Row) -> Dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "teacher": row["teacher"],
            "location": row["location"],
            "credit": row["credit"],
            "category": row["category"],
            "color": row["color"],
            "note": row["note"],
            "dayOfWeek": row["day_of_week"],
            "startPeriod": row["start_period"],
            "endPeriod": row["end_period"],
            "weekRule": {"from": row["week_from"], "to": row["week_to"], "pattern": row["week_pattern"]},
            "source": row["source"],
            **({"weeks": json.loads(row["weeks_json"])} if row["weeks_json"] else {}),
        }

    def list_courses(self, keyword: str = "") -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM courses ORDER BY day_of_week, start_period"
            ).fetchall()
        courses = [self._row_to_course(r) for r in rows]
        if keyword:
            kw = keyword.strip().lower()
            courses = [c for c in courses if kw in
                       "{} {} {} {}".format(c["name"], c["teacher"], c["location"], c["category"]).lower()]
        return courses

    def get_course(self, course_id: str) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        return self._row_to_course(row) if row else None

    def insert_course(self, course: Dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO courses
                   (id, name, teacher, location, credit, category, color, note,
                    day_of_week, start_period, end_period,
                    week_from, week_to, week_pattern, weeks_json, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    course["id"], course["name"], course["teacher"], course["location"],
                    float(course["credit"]), course["category"], course["color"], course["note"],
                    int(course["dayOfWeek"]), int(course["startPeriod"]), int(course["endPeriod"]),
                    int(course["weekRule"]["from"]), int(course["weekRule"]["to"]),
                    course["weekRule"]["pattern"],
                    json.dumps(course["weeks"]) if course.get("weeks") else None,
                    course.get("source"),
                ),
            )
            self._conn.commit()

    def update_course(self, course_id: str, course: Dict) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE courses SET
                     name=?, teacher=?, location=?, credit=?, category=?, color=?, note=?,
                     day_of_week=?, start_period=?, end_period=?,
                     week_from=?, week_to=?, week_pattern=?, weeks_json=?, source=?,
                     updated_at=datetime('now','localtime')
                   WHERE id=?""",
                (
                    course["name"], course["teacher"], course["location"],
                    float(course["credit"]), course["category"], course["color"], course["note"],
                    int(course["dayOfWeek"]), int(course["startPeriod"]), int(course["endPeriod"]),
                    int(course["weekRule"]["from"]), int(course["weekRule"]["to"]),
                    course["weekRule"]["pattern"],
                    json.dumps(course["weeks"]) if course.get("weeks") else None,
                    course.get("source"), course_id,
                ),
            )
            self._conn.commit()

    def delete_course(self, course_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def clear_courses(self) -> int:
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) AS n FROM courses").fetchone()["n"]
            self._conn.execute("DELETE FROM courses")
            self._conn.commit()
        return count

    def replace_all(self, courses: List[Dict]) -> int:
        """全量替换（演示重置 / 勘察脚本落库用）。"""
        with self._lock:
            self._conn.execute("DELETE FROM courses")
            for c in courses:
                c = dict(c)
                c.setdefault("source", None)
                self.insert_course(c)
            self._conn.commit()
        return len(courses)

    # ------------------------------------------------------------------
    # 元信息（上次抓取时间戳等）
    # ------------------------------------------------------------------
    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
            self._conn.commit()
