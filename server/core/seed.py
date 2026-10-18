"""演示种子数据：与 demo/js/store.js 的 SEED_COURSES 完全一致。

刻意覆盖多种真实排课形态：连堂课、单双周、晚间课、短周期课、同时段多门课。
首次启动 / 演示重置时写入 SQLite。
"""
from __future__ import annotations

SEED_COURSES = [
    {
        "id": "c01", "name": "高等数学 A（上）", "teacher": "李文博", "location": "教学楼 A-301",
        "credit": 4, "dayOfWeek": 1, "startPeriod": 1, "endPeriod": 2,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "必修", "color": "blue", "note": "每周三有小测，需自备作业本。",
    },
    {
        "id": "c02", "name": "大学英语（三）", "teacher": "陈曦", "location": "外语楼 205",
        "credit": 3, "dayOfWeek": 1, "startPeriod": 3, "endPeriod": 4,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "必修", "color": "teal", "note": "需完成线上听力任务，第 8 周期中口语测试。",
    },
    {
        "id": "c03", "name": "数据结构", "teacher": "王振宇", "location": "信息楼 402",
        "credit": 3, "dayOfWeek": 2, "startPeriod": 1, "endPeriod": 2,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "必修", "color": "purple", "note": "",
    },
    {
        "id": "c04", "name": "线性代数", "teacher": "赵敏", "location": "教学楼 B-108",
        "credit": 3, "dayOfWeek": 2, "startPeriod": 9, "endPeriod": 10,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "必修", "color": "amber", "note": "晚间课程，注意教学楼闭楼时间。",
    },
    {
        "id": "c05", "name": "计算机网络", "teacher": "刘承志", "location": "信息楼 305",
        "credit": 3, "dayOfWeek": 3, "startPeriod": 3, "endPeriod": 4,
        "weekRule": {"from": 1, "to": 15, "pattern": "odd"},
        "category": "必修", "color": "rose", "note": "单周上课，双周为自主学习。",
    },
    {
        "id": "c06", "name": "体育（三）", "teacher": "孙浩", "location": "东田径场",
        "credit": 1, "dayOfWeek": 3, "startPeriod": 5, "endPeriod": 6,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "必修", "color": "green", "note": "雨天改为体育馆集中授课。",
    },
    {
        "id": "c07", "name": "计算机组成原理实验", "teacher": "周雅", "location": "实验楼 3-201",
        "credit": 1, "dayOfWeek": 4, "startPeriod": 5, "endPeriod": 8,
        "weekRule": {"from": 2, "to": 16, "pattern": "even"},
        "category": "实践", "color": "cyan", "note": "连堂四节，双周进行，需提前预习实验指导书。",
    },
    {
        "id": "c08", "name": "马克思主义基本原理", "teacher": "吴桐", "location": "文科楼 101",
        "credit": 3, "dayOfWeek": 5, "startPeriod": 3, "endPeriod": 4,
        "weekRule": {"from": 1, "to": 16, "pattern": "all"},
        "category": "必修", "color": "rose", "note": "",
    },
    {
        "id": "c09", "name": "专业英语", "teacher": "陈曦", "location": "外语楼 308",
        "credit": 2, "dayOfWeek": 5, "startPeriod": 7, "endPeriod": 8,
        "weekRule": {"from": 1, "to": 15, "pattern": "odd"},
        "category": "选修", "color": "teal", "note": "单周上课。",
    },
    {
        "id": "c10", "name": "形势与政策", "teacher": "郑立", "location": "文科楼 207",
        "credit": 1, "dayOfWeek": 5, "startPeriod": 5, "endPeriod": 6,
        "weekRule": {"from": 1, "to": 8, "pattern": "all"},
        "category": "必修", "color": "amber", "note": "前八周结课。",
    },
]
