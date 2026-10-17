# 课程表工具 · 前端 Demo

一个**纯前端**的课程表产品原型：不接后端、不写服务端接口，全部数据来自内置模拟数据（mock data），增删改查只在浏览器内存中生效。

## 运行方式

两种方式任选：

1. **直接打开**：双击 `index.html` 即可运行（无需构建、无需安装依赖）。
2. **本地服务**（推荐，便于手机同局域网访问）：

   ```bash
   cd demo
   python -m http.server 8080
   # 浏览器打开 http://localhost:8080
   ```

> 数据保存在内存中，刷新页面即恢复到初始 mock 数据，不会写入任何持久化存储。

## 目录结构

```
demo/
├── index.html          页面骨架（课表视图 / 课程视图 / 四个弹窗）
├── css/style.css       全部样式，含响应式与移动端适配
├── js/store.js         数据层：mock 数据 + 异步 CRUD API（唯一需要替换的文件）
├── js/app.js           交互层：渲染与事件处理，不含任何业务数据
└── test/
    ├── store.test.js   数据层自检（零依赖）
    └── ui.smoke.js     UI 冒烟测试（需 jsdom）
```

## 核心页面

| 页面 | 内容 |
|---|---|
| 周课表 | 7 天 × 12 节次网格、左侧为每节课的上下课时间、周次切换、今日高亮、日期表头、点击课程查看 |
| 课程管理 | 搜索、课程列表、查看详情、编辑、删除、新增、从教务系统导入 |

## 演示路径（可完整走通）

1. 打开后进入**本周课表**（按当前日期自动定位教学周，加载时显示骨架屏）
2. 切换**上一周 / 下一周**，或点「回到本周」；翻到**第 17、18 周**时展示**空数据状态**
3. 点击任意课程块 → 弹出**课程详情**（教师、地点、学分、周次规则、具体上课周次、备注）
4. 切换到**课程管理**：搜索「王」「信息楼」等关键词实时过滤；清空搜索后恢复
5. 点「详情 / 编辑 / 删除」完成**查、改、删**；删除带二次确认
6. 点「新增课程」→ 填写表单 → 保存后课表与列表**立即同步更新**
7. **故意填一个冲突时间**（如周一第 1-2 节、第 1-16 周），保存时会提示「与已有课程时间冲突」
8. 点「**从教务系统导入**」→ 填写学号密码（演示模式任意填写）→ 读取到 10 门模拟课程，其中 5 门与现有课表**冲突并置灰**，勾选其余 5 门导入，课表与列表同步更新
9. 点右上角「清空课程」→ 展示**整体空数据状态**；再点「重置数据」恢复

## 覆盖的状态

- 加载中：骨架屏
- 列表：有数据 / 搜索无结果 / 完全无数据
- 详情：正常详情
- 空数据：某周无排课、搜索无匹配、清空后的整体空状态
- 反馈：新增、更新、删除、冲突、校验失败均有 Toast 提示

## 模拟数据设计

数据刻意贴近真实排课场景，10 门课程覆盖了：

- 连堂课（跨 2 节）
- 连堂四节的实验课（第 5-8 节，双周）
- 单周 / 双周排课
- 晚间课程（第 9-10 节）
- 短周期课程（前 8 周结课）
- 同一时段多门课（靠不同周次规则区分）
- 空周次（第 17、18 周无课，用于展示空状态）

数据模型：

```
Course {
  id, name, teacher, location, credit, category, color, note,
  dayOfWeek: 1-7,
  startPeriod, endPeriod,            // 1-12 节
  weekRule: { from, to, pattern },   // pattern: all | odd | even
  source?: 'jwxt'                    // 来自教务系统导入的课程带此标记
}

Semester { id, name, startDate, totalWeeks, currentWeek, periodTimes }
```

`periodTimes` 为 12 节课各自的上下课时间（如第 1 节 08:00-08:45），
用于课表左侧时间列、课程列表与详情中的上课时间展示。

## 数据层的替换方式（重点）

所有数据访问都集中在 `js/store.js`，对外暴露的方法如下，**全部返回 Promise**：

```js
getSemester()                 // 学期信息（含当前周、各节次上下课时间）
getWeekDates(week)            // 某一周每天的日期
listCourses({ keyword })      // 课程列表，支持关键词过滤
getCourse(id)                 // 课程详情
createCourse(payload)         // 新增
updateCourse(id, payload)     // 更新
deleteCourse(id)              // 删除
getSchedule(week)             // 某一周的课表
fetchFromJwxt({ studentId, password })   // 模拟连接教务系统读取课表
importCourses(list)           // 批量导入，逐门校验与冲突检测，返回导入/跳过明细
```

因此 UI 层已按「异步接口」的方式编写，**接入真实后端时只需替换 `store.js` 内部实现，UI 层无需改动**。例如：

```js
// 替换前（Mock）
listCourses: function (params) {
  var keyword = String(params.keyword || '').trim().toLowerCase();
  var list = db.courses.filter(/* ... */);
  return delay(list.map(decorate), 260);
}

// 替换后（真实接口）
listCourses: function (params) {
  return fetch('/api/courses?keyword=' + encodeURIComponent(params.keyword || ''))
    .then(function (res) { return res.json(); });
}
```

只要保持方法名与返回结构不变，`js/app.js` 一行都不用改。

`resetDemo()` 与 `clearCourses()` 仅为演示空数据状态而存在，接入真实接口后可删除。

## 自检

**数据层自检**（零依赖，只需 Node.js）：

```bash
node demo/test/store.test.js
```

覆盖 53 项：节次时间、周次展开（单周 / 双周）、按周过滤、空周次、搜索、新增、字段校验、
时间冲突检测、更新、删除、教务系统导入（含冲突跳过与重复导入拦截）、清空与重置。
接入真实接口后，该脚本可作为数据层的契约测试继续使用。

**UI 冒烟测试**（需 jsdom，真实执行页面脚本）：

```bash
npm install jsdom        # 任选方式装好 jsdom
NODE_PATH=<jsdom 所在 node_modules> node demo/test/ui.smoke.js
```

覆盖 52 项：首屏渲染、时间列、课程块信息完整度、周次切换、空态、搜索、详情、
新增（含冲突拦截）、删除、清空、重置，以及完整的教务系统导入流程。

## 已知边界

- 数据仅存于内存，刷新即重置
- 「从教务系统导入」为**模拟流程**（不连接真实系统），用于演示交互与冲突处理；
  真实抓取按 PLAN.md 的方案在阶段一/三实现
- 未实现登录、多学期切换、课表导出（ICS/HTML）等，属于后续接入真实教务系统后的范围
- 课表在窄屏下横向滚动查看，未做专门的移动端网格重排
