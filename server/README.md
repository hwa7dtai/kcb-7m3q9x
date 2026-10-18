# 课程表工具 · 后端服务

按 PLAN.md 的分层架构实现：REST API + SQLite 存储 + 正方教务系统适配层。
前端复用 `demo/` 的 PWA 界面，本服务直接托管之——一个端口同时提供页面与数据。

## 运行

```bash
pip install -r server/requirements.txt
python server/app.py            # 本机访问 http://127.0.0.1:8080
python server/app.py --lan      # 局域网可访问（手机同 WiFi 打开，可加为 PWA）
```

- 数据文件：`server/data/schedule.db`（SQLite，个人数据，不部署公网）
- 学期配置：`KCB_SEMESTER_ID / KCB_SEMESTER_NAME / KCB_SEMESTER_START / KCB_SEMESTER_WEEKS` 环境变量
- 首次启动会写入 10 门演示课程（可用 `KCB_SEED_DEMO=0` 关闭，界面里可一键清空）

## 架构（对应 PLAN.md 五层）

```
展示层   demo/ 前端（PWA，原样复用）
应用层   core/service.py      课表服务、冲突检测、导入、重试保护
适配层   adapters/base.py     四动作抽象（fetch_session / login / fetch_schedule_raw / parse）
         adapters/zf.py       正方新版实现：RSA 加密登录 + 课表 JSON 解析
抓取层   service.fetch_from_jwxt（自动模式）+ scripts/recon_playwright.py（手动勘察）
存储层   core/storage.py      SQLite；core/credentials.py 凭据存系统钥匙串
```

## REST API（与 demo/js/store.js 的契约一一对应）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（前端模式探测） |
| GET | `/api/semester` | 学期信息（含当前周、节次时间表） |
| GET | `/api/week-dates?week=N` | 某周 7 天日期 |
| GET | `/api/courses?keyword=` | 课程列表（关键词过滤） |
| GET | `/api/courses/<id>` | 课程详情 |
| POST | `/api/courses` | 新增（校验 + 冲突检测） |
| PUT | `/api/courses/<id>` | 更新 |
| DELETE | `/api/courses/<id>` | 删除 |
| GET | `/api/schedule?week=N` | 某周课表 |
| POST | `/api/jwxt/fetch` | 自动登录教务系统读取课表 `{studentId, password}` |
| POST | `/api/jwxt/import` | 批量导入 `{courses: [...]}` |
| POST | `/api/jwxt/check-conflict` | 冲突预检 |
| POST | `/api/demo/reset` / `/api/demo/clear` | 演示重置 / 清空 |

错误契约：校验/冲突 → `400 {error, conflict?}`；不存在 → `404 {error}`；
教务系统交互失败 → `502 {error}`。前端 `store.js` 据此 reject 出与原 mock 一致的 `Error`。

## 自动登录保护（PLAN.md 4.2 / 2.4）

- 总尝试次数硬上限 2 次（连续失败 3 次会锁号 3 分钟）
- 明确的账号密码错误**不重试**，立即终止并提示手动登录
- 请求间隔 1.2s、超时 15s，无并发、无轮询

## 阶段一勘察（首次使用真实教务系统前）

课表接口地址是 PLAN.md 中唯一未确认项。请配合完成一次手动勘察：

```bash
pip install playwright
python -m playwright install chromium
python server/scripts/recon_playwright.py
```

浏览器打开后手动登录教务系统，回车接管，脚本会确认课表接口并把脱敏样本写入
`server/tests/fixtures/real_xskbcx_sample.json`，随后按提示调整 `JW_KB_CANDIDATES` 与解析字段。

## 一键刷新（阶段三）

前端成功导入一次后，凭据存入系统钥匙串（Windows 凭据管理器），此后可命令行刷新：

```bash
python server/scripts/refresh.py
```

## 测试

```bash
cd server && python -m pytest tests/ -q     # 111 项（周次引擎 / 解析器 / 登录链路 / 服务层 / API 契约）
```

登录链路测试全部走假会话，不触网、不读写真实钥匙串。
