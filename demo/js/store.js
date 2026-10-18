/**
 * 数据层：集中管理全部数据访问。
 *
 * 两种运行模式（自动探测，无需配置）：
 *   远程模式：后端服务可达（python server/app.py 启动），全部读写走 REST API + SQLite。
 *   本地模式：后端不可达（file:// 双击 / 手机离线 PWA），回退到内置实现：
 *             优先读 localStorage 中上次同步的真实数据，否则用演示种子数据。
 *
 * 两种模式对外暴露的方法名与返回结构完全一致，UI 层（app.js）无感知。
 */
(function (global) {
  'use strict';

  /* ============================ 基础配置 ============================ */

  var LATENCY = 260;          // 本地模式模拟网络延迟（毫秒）
  var CACHE_KEY = 'kcb.cache.v1'; // localStorage：上次同步的真实数据（离线兜底）
  var API_BASE = 'api/';      // 相对路径，与页面同源

  var SEMESTER = {
    id: '2026-2027-1',
    name: '2026—2027 学年 第一学期',
    startDate: '2026-09-07', // 学期第一周的周一
    totalWeeks: 18
  };

  var WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  /* 每一节课的上下课时间，用于课表左侧时间列与课程详情 */
  var PERIOD_TIMES = [
    { start: '08:00', end: '08:45' },
    { start: '08:55', end: '09:40' },
    { start: '10:00', end: '10:45' },
    { start: '10:55', end: '11:40' },
    { start: '14:00', end: '14:45' },
    { start: '14:55', end: '15:40' },
    { start: '16:00', end: '16:45' },
    { start: '16:55', end: '17:40' },
    { start: '19:00', end: '19:45' },
    { start: '19:55', end: '20:40' },
    { start: '21:00', end: '21:45' },
    { start: '21:55', end: '22:40' }
  ];

  var TOTAL_PERIODS = 12;

  /* ============================ 种子数据 ============================ */
  /* 刻意覆盖多种真实排课形态：连堂课、单双周、晚间课、短周期课、同时段多门课 */

  var SEED_COURSES = [
    {
      id: 'c01', name: '高等数学 A（上）', teacher: '李文博', location: '教学楼 A-301',
      credit: 4, dayOfWeek: 1, startPeriod: 1, endPeriod: 2,
      weekRule: { from: 1, to: 16, pattern: 'all' },
      category: '必修', color: 'blue', note: '每周三有小测，需自备作业本。'
    },
    {
      id: 'c02', name: '大学英语（三）', teacher: '陈曦', location: '外语楼 205',
      credit: 3, dayOfWeek: 1, startPeriod: 3, endPeriod: 4,
      weekRule: { from: 1, to: 16, pattern: 'all' },
      category: '必修', color: 'teal', note: '需完成线上听力任务，第 8 周期中口语测试。'
    },
    {
      id: 'c03', name: '数据结构', teacher: '王振宇', location: '信息楼 402',
      credit: 3, dayOfWeek: 2, startPeriod: 1, endPeriod: 2,
      weekRule: { from: 1, to: 16, pattern: 'all' },
      category: '必修', color: 'purple', note: ''
    },
    {
      id: 'c04', name: '线性代数', teacher: '赵敏', location: '教学楼 B-108',
      credit: 3, dayOfWeek: 2, startPeriod: 9, endPeriod: 10,
      weekRule: { from: 1, to: 16, pattern: 'all' },
      category: '必修', color: 'amber', note: '晚间课程，注意教学楼闭楼时间。'
    },
    {
      id: 'c05', name: '计算机网络', teacher: '刘承志', location: '信息楼 305',
      credit: 3, dayOfWeek: 3, startPeriod: 3, endPeriod: 4,
      weekRule: { from: 1, to: 15, pattern: 'odd' },
      category: '必修', color: 'rose', note: '单周上课，双周为自主学习。'
    },
    {
      id: 'c06', name: '体育（三）', teacher: '孙浩', location: '东田径场',
      credit: 1, dayOfWeek: 3, startPeriod: 5, endPeriod: 6,
      weekRule: { from: 1, to: 16, pattern: 'all' },
      category: '必修', color: 'green', note: '雨天改为体育馆集中授课。'
    },
    {
      id: 'c07', name: '计算机组成原理实验', teacher: '周雅', location: '实验楼 3-201',
      credit: 1, dayOfWeek: 4, startPeriod: 5, endPeriod: 8,
      weekRule: { from: 2, to: 16, pattern: 'even' },
      category: '实践', color: 'cyan', note: '连堂四节，双周进行，需提前预习实验指导书。'
    },
    {
      id: 'c08', name: '马克思主义基本原理', teacher: '吴桐', location: '文科楼 101',
      credit: 3, dayOfWeek: 5, startPeriod: 3, endPeriod: 4,
      weekRule: { from: 1, to: 16, pattern: 'all' },
      category: '必修', color: 'rose', note: ''
    },
    {
      id: 'c09', name: '专业英语', teacher: '陈曦', location: '外语楼 308',
      credit: 2, dayOfWeek: 5, startPeriod: 7, endPeriod: 8,
      weekRule: { from: 1, to: 15, pattern: 'odd' },
      category: '选修', color: 'teal', note: '单周上课。'
    },
    {
      id: 'c10', name: '形势与政策', teacher: '郑立', location: '文科楼 207',
      credit: 1, dayOfWeek: 5, startPeriod: 5, endPeriod: 6,
      weekRule: { from: 1, to: 8, pattern: 'all' },
      category: '必修', color: 'amber', note: '前八周结课。'
    }
  ];

  /* ============================ 教务系统导入（本地模式模拟） ============================ */
  /* 模拟"从教务系统读到的课表"：刻意与现有课表部分冲突，用于演示冲突跳过逻辑 */
  var JWXT_MOCK_COURSES = [
    { name: '高等数学 A（上）', teacher: '李文博', location: '教学楼 A-301', credit: 4, dayOfWeek: 1, startPeriod: 1, endPeriod: 2, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '大学英语（三）', teacher: '陈曦', location: '外语楼 205', credit: 3, dayOfWeek: 1, startPeriod: 3, endPeriod: 4, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '大学物理（二）', teacher: '何静', location: '教学楼 C-205', credit: 3.5, dayOfWeek: 1, startPeriod: 5, endPeriod: 6, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '数据结构', teacher: '王振宇', location: '信息楼 402', credit: 3, dayOfWeek: 2, startPeriod: 1, endPeriod: 2, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '概率论与数理统计', teacher: '罗颖', location: '教学楼 B-302', credit: 3, dayOfWeek: 2, startPeriod: 3, endPeriod: 4, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '中国近现代史纲要', teacher: '吴桐', location: '文科楼 201', credit: 3, dayOfWeek: 3, startPeriod: 1, endPeriod: 2, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '体育（三）', teacher: '孙浩', location: '东田径场', credit: 1, dayOfWeek: 3, startPeriod: 5, endPeriod: 6, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '工程训练', teacher: '周雅', location: '工程中心 102', credit: 2, dayOfWeek: 4, startPeriod: 9, endPeriod: 10, weekRule: { from: 3, to: 15, pattern: 'odd' }, category: '实践' },
    { name: '马克思主义基本原理', teacher: '吴桐', location: '文科楼 101', credit: 3, dayOfWeek: 5, startPeriod: 3, endPeriod: 4, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '必修' },
    { name: '大学生心理健康', teacher: '冯晓', location: '文科楼 207', credit: 2, dayOfWeek: 5, startPeriod: 9, endPeriod: 10, weekRule: { from: 1, to: 16, pattern: 'all' }, category: '选修' }
  ];

  var IMPORT_COLORS = ['blue', 'teal', 'amber', 'purple', 'rose', 'green', 'cyan'];

  /* ============================ 通用工具 ============================ */

  function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function delay(value, ms) {
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        if (value instanceof Error) { reject(value); } else { resolve(value); }
      }, ms == null ? LATENCY : ms);
    });
  }

  function fail(message, extra) {
    var err = new Error(message);
    if (extra) { Object.keys(extra).forEach(function (k) { err[k] = extra[k]; }); }
    return err;
  }

  function pad(n) { return n < 10 ? '0' + n : String(n); }

  /** 展开周次规则为具体周次数组 */
  function expandWeeks(rule) {
    var weeks = [];
    if (!rule) { return weeks; }
    var from = Number(rule.from);
    var to = Number(rule.to);
    if (!isFinite(from) || !isFinite(to) || from > to) { return weeks; }
    for (var w = from; w <= to; w++) {
      if (rule.pattern === 'all') { weeks.push(w); }
      else if (rule.pattern === 'odd' && w % 2 === 1) { weeks.push(w); }
      else if (rule.pattern === 'even' && w % 2 === 0) { weeks.push(w); }
    }
    return weeks;
  }

  /** 课程的具体上课周：离散集合优先，否则由规则展开 */
  function courseWeeks(course) {
    if (course.weeks && course.weeks.length) {
      return course.weeks.slice();
    }
    return expandWeeks(course.weekRule);
  }

  /** 周次规则的可读描述，如 "第 1-15 周(单周)" */
  function formatWeekRule(rule) {
    if (!rule) { return '未设置'; }
    var suffix = rule.pattern === 'odd' ? '(单周)' : (rule.pattern === 'even' ? '(双周)' : '');
    return '第 ' + rule.from + '-' + rule.to + ' 周' + suffix;
  }

  /** 具体周次集合的可读描述（离散周输出紧凑列表） */
  function formatWeeksText(weeks) {
    if (!weeks || !weeks.length) { return '未设置'; }
    var uniq = weeks.slice().sort(function (a, b) { return a - b; });
    var from = uniq[0], to = uniq[uniq.length - 1];
    var full = []; var odd = []; var even = [];
    for (var w = from; w <= to; w++) {
      full.push(w);
      if (w % 2 === 1) { odd.push(w); } else { even.push(w); }
    }
    var same = function (a, b) { return a.length === b.length && a.join(',') === b.join(','); };
    if (same(uniq, full)) { return '第 ' + from + '-' + to + ' 周'; }
    if (same(uniq, odd)) { return '第 ' + from + '-' + to + ' 周(单周)'; }
    if (same(uniq, even)) { return '第 ' + from + '-' + to + ' 周(双周)'; }
    return '第 ' + uniq.join(',') + ' 周';
  }

  /** 起止节次对应的上课时间范围，如 "08:00-09:40" */
  function periodTimeRangeWith(times, startPeriod, endPeriod) {
    var a = times && times[startPeriod - 1];
    var b = times && times[endPeriod - 1];
    if (!a || !b) { return ''; }
    return a.start + '-' + b.end;
  }

  /** 同一天、时段重叠、且周次有交集，即为冲突 */
  function findConflictIn(list, candidate, excludeId) {
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      if (excludeId != null && c.id === excludeId) { continue; }
      if (c.dayOfWeek !== candidate.dayOfWeek) { continue; }
      var overlapPeriod = !(candidate.endPeriod < c.startPeriod || candidate.startPeriod > c.endPeriod);
      if (!overlapPeriod) { continue; }
      var wa = courseWeeks(candidate);
      var wb = courseWeeks(c);
      var hit = false;
      for (var j = 0; j < wa.length; j++) {
        if (wb.indexOf(wa[j]) !== -1) { hit = true; break; }
      }
      if (hit) { return c; }
    }
    return null;
  }

  function sortCourses(list) {
    return list.slice().sort(function (a, b) {
      if (a.dayOfWeek !== b.dayOfWeek) { return a.dayOfWeek - b.dayOfWeek; }
      return a.startPeriod - b.startPeriod;
    });
  }

  function validateWith(totalWeeks, payload) {
    if (!payload.name || !String(payload.name).trim()) { return '课程名称不能为空'; }
    if (!payload.teacher || !String(payload.teacher).trim()) { return '任课教师不能为空'; }
    if (!payload.dayOfWeek || payload.dayOfWeek < 1 || payload.dayOfWeek > 7) { return '请选择正确的星期'; }
    var sp = Number(payload.startPeriod);
    var ep = Number(payload.endPeriod);
    if (!isFinite(sp) || !isFinite(ep) || sp < 1 || ep > TOTAL_PERIODS || sp > ep) {
      return '节次设置有误，需在 1-' + TOTAL_PERIODS + ' 节范围内，且开始节次不晚于结束节次';
    }
    var rule = payload.weekRule || {};
    var from = Number(rule.from);
    var to = Number(rule.to);
    if (!isFinite(from) || !isFinite(to) || from < 1 || to > totalWeeks || from > to) {
      return '周次设置有误，需在 1-' + totalWeeks + ' 周范围内';
    }
    return null;
  }

  /** 把教务系统读到的原始课程规整为内部数据结构 */
  function normalizeImported(raw, index) {
    var course = {
      name: String(raw.name || '').trim(),
      teacher: String(raw.teacher || '').trim(),
      location: String(raw.location || '').trim(),
      credit: Number(raw.credit) || 0,
      dayOfWeek: Number(raw.dayOfWeek),
      startPeriod: Number(raw.startPeriod),
      endPeriod: Number(raw.endPeriod),
      weekRule: {
        from: Number(raw.weekRule && raw.weekRule.from),
        to: Number(raw.weekRule && raw.weekRule.to),
        pattern: (raw.weekRule && raw.weekRule.pattern) || 'all'
      },
      category: raw.category || '必修',
      color: IMPORT_COLORS[index % IMPORT_COLORS.length],
      note: String(raw.note || '').trim(),
      source: 'jwxt'
    };
    if (raw.weeks && raw.weeks.length) { course.weeks = raw.weeks.slice(); }
    return course;
  }

  /* ============================ 模式探测 ============================ */

  var modePromise = null;   // Promise<boolean>：后端是否可达
  var backendMode = null;   // 同步可读的模式状态（helpers 用）

  function probeBackend() {
    if (modePromise) { return modePromise; }
    modePromise = new Promise(function (resolve) {
      function settle(ok) { backendMode = ok; resolve(ok); }
      if (typeof global.fetch !== 'function') { settle(false); return; }
      var settled = false;
      var timer = setTimeout(function () {
        if (!settled) { settled = true; settle(false); }
      }, 800);
      global.fetch(API_BASE + 'health', { method: 'GET', cache: 'no-store' }).then(function (res) {
        if (!settled) { settled = true; clearTimeout(timer); settle(!!(res && res.ok)); }
      }).catch(function () {
        if (!settled) { settled = true; clearTimeout(timer); settle(false); }
      });
    });
    return modePromise;
  }

  /** 按模式路由：remoteFn / localFn 均返回 Promise */
  function route(remoteFn, localFn) {
    return probeBackend().then(function (remoteMode) {
      return remoteMode ? remoteFn() : localFn();
    });
  }

  /* ============================ 远程模式 ============================ */

  var lastKnownSemester = null;  // 最近一次 getSemester 结果（helpers 用）
  var lastKnownCourses = [];     // 最近一次完整课程列表（helpers.checkConflict 用）

  function readCache() {
    try {
      var raw = global.localStorage && global.localStorage.getItem(CACHE_KEY);
      if (raw) {
        var cache = JSON.parse(raw);
        if (cache && Array.isArray(cache.courses)) { return cache; }
      }
    } catch (e) { /* 缓存损坏即忽略 */ }
    return null;
  }

  function writeCache() {
    try {
      if (!global.localStorage) { return; }
      var courses = lastKnownCourses.map(function (c) {
        var keys = ['id', 'name', 'teacher', 'location', 'credit', 'category', 'color', 'note',
          'dayOfWeek', 'startPeriod', 'endPeriod', 'weekRule', 'weeks', 'source'];
        var out = {};
        keys.forEach(function (k) { if (c[k] !== undefined) { out[k] = c[k]; } });
        return out;
      });
      global.localStorage.setItem(CACHE_KEY, JSON.stringify({
        semester: lastKnownSemester || SEMESTER,
        courses: courses
      }));
    } catch (e) { /* 存储不可用时忽略 */ }
  }

  function apiFetch(path, options) {
    options = options || {};
    if (options.body) { options.headers = { 'Content-Type': 'application/json' }; }
    return global.fetch(API_BASE + path, options).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error(data.error || ('请求失败 HTTP ' + res.status));
          if (data.conflict) { err.conflict = data.conflict; }
          throw err;
        }
        return data;
      });
    });
  }

  /** 变更后刷新本地缓存（离线兜底数据与服务器保持一致） */
  function refreshRemoteCache() {
    return apiFetch('courses').then(function (list) {
      lastKnownCourses = list;
      writeCache();
    });
  }

  var remote = {
    getSemester: function () {
      return apiFetch('semester').then(function (s) {
        lastKnownSemester = s;
        writeCache();
        return s;
      });
    },
    getWeekDates: function (week) {
      return apiFetch('week-dates?week=' + encodeURIComponent(week));
    },
    listCourses: function (params) {
      params = params || {};
      return apiFetch('courses?keyword=' + encodeURIComponent(params.keyword || ''))
        .then(function (list) {
          if (!String(params.keyword || '').trim()) {
            lastKnownCourses = list;
            writeCache();
          }
          return list;
        });
    },
    getCourse: function (id) { return apiFetch('courses/' + encodeURIComponent(id)); },
    createCourse: function (payload) {
      return apiFetch('courses', { method: 'POST', body: JSON.stringify(payload) })
        .then(function (created) { return refreshRemoteCache().then(function () { return created; }); });
    },
    updateCourse: function (id, payload) {
      return apiFetch('courses/' + encodeURIComponent(id), { method: 'PUT', body: JSON.stringify(payload) })
        .then(function (updated) { return refreshRemoteCache().then(function () { return updated; }); });
    },
    deleteCourse: function (id) {
      return apiFetch('courses/' + encodeURIComponent(id), { method: 'DELETE' })
        .then(function (res) { return refreshRemoteCache().then(function () { return res; }); });
    },
    getSchedule: function (week) { return apiFetch('schedule?week=' + encodeURIComponent(week)); },
    fetchFromJwxt: function (params) {
      params = params || {};
      if (!String(params.studentId || '').trim()) { return Promise.reject(fail('请输入学号')); }
      if (!String(params.password || '')) { return Promise.reject(fail('请输入教务系统密码')); }
      return apiFetch('jwxt/fetch', {
        method: 'POST',
        body: JSON.stringify({ studentId: params.studentId, password: params.password })
      });
    },
    importCourses: function (list) {
      return apiFetch('jwxt/import', { method: 'POST', body: JSON.stringify({ courses: list || [] }) })
        .then(function (res) { return refreshRemoteCache().then(function () { return res; }); });
    },
    resetDemo: function () {
      return apiFetch('demo/reset', { method: 'POST' })
        .then(function (res) { return refreshRemoteCache().then(function () { return res; }); });
    },
    clearCourses: function () {
      return apiFetch('demo/clear', { method: 'POST' })
        .then(function (res) { return refreshRemoteCache().then(function () { return res; }); });
    }
  };

  /* ============================ 本地模式 ============================ */

  var db = null; // 懒初始化：{ semester, courses }
  var idSeq = 100;
  var importSeq = 500;

  function ensureLocalDb() {
    if (db) { return; }
    var cached = readCache();
    if (cached && cached.courses.length) {
      db = { semester: cached.semester || SEMESTER, courses: cached.courses };
    } else {
      db = { semester: deepClone(SEMESTER), courses: deepClone(SEED_COURSES) };
    }
  }

  /** 本地模式同样持久化到 localStorage，页面刷新不丢改动 */
  function persistAnd(value) {
    lastKnownSemester = db.semester;
    lastKnownCourses = db.courses;
    writeCache();
    return value;
  }

  function validate(payload) {
    return validateWith(db.semester.totalWeeks, payload);
  }

  function decorate(course) {
    var copy = deepClone(course);
    var weeks = courseWeeks(course);
    copy.weeks = weeks;
    copy.weekText = formatWeeksText(weeks);
    copy.periodText = '第 ' + course.startPeriod + '-' + course.endPeriod + ' 节';
    copy.timeText = periodTimeRangeWith(PERIOD_TIMES, course.startPeriod, course.endPeriod);
    copy.dayText = WEEKDAY_LABELS[course.dayOfWeek - 1] || '';
    return copy;
  }

  function findConflict(candidate, excludeId) {
    return findConflictIn(db.courses, candidate, excludeId);
  }

  function computeCurrentWeek() {
    var start = new Date(db.semester.startDate + 'T00:00:00');
    var now = new Date();
    var diffDays = Math.floor((now - start) / 86400000);
    var week = Math.floor(diffDays / 7) + 1;
    if (week < 1) { week = 1; }
    if (week > db.semester.totalWeeks) { week = db.semester.totalWeeks; }
    return week;
  }

  function weekDates(week) {
    var start = new Date(db.semester.startDate + 'T00:00:00');
    start.setDate(start.getDate() + (week - 1) * 7);
    var dates = [];
    for (var i = 0; i < 7; i++) {
      var d = new Date(start.getTime());
      d.setDate(d.getDate() + i);
      dates.push(d);
    }
    return dates;
  }

  var local = {
    getSemester: function () {
      ensureLocalDb();
      var data = deepClone(db.semester);
      data.currentWeek = computeCurrentWeek();
      data.weekdayLabels = WEEKDAY_LABELS.slice();
      data.totalPeriods = TOTAL_PERIODS;
      data.periodTimes = deepClone(PERIOD_TIMES);
      return delay(data, 120);
    },
    getWeekDates: function (week) {
      ensureLocalDb();
      var dates = weekDates(week).map(function (d) {
        return {
          iso: d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()),
          label: (d.getMonth() + 1) + '/' + d.getDate()
        };
      });
      return delay(dates, 80);
    },
    listCourses: function (params) {
      ensureLocalDb();
      params = params || {};
      var keyword = String(params.keyword || '').trim().toLowerCase();
      var list = db.courses.slice();
      if (keyword) {
        list = list.filter(function (c) {
          return (c.name + ' ' + c.teacher + ' ' + c.location + ' ' + c.category)
            .toLowerCase().indexOf(keyword) !== -1;
        });
      }
      return delay(sortCourses(list).map(decorate), LATENCY);
    },
    getCourse: function (id) {
      ensureLocalDb();
      var found = db.courses.filter(function (c) { return c.id === id; })[0];
      if (!found) { return delay(fail('课程不存在或已被删除'), 120); }
      return delay(decorate(found), 120);
    },
    createCourse: function (payload) {
      ensureLocalDb();
      var error = validate(payload);
      if (error) { return delay(fail(error), 120); }
      var conflict = findConflict(payload, null);
      if (conflict) {
        return delay(fail('与已有课程《' + conflict.name + '》时间冲突，请调整节次或周次', { conflict: conflict }), LATENCY);
      }
      var course = deepClone(payload);
      course.id = 'c' + (++idSeq);
      course.name = String(course.name).trim();
      course.teacher = String(course.teacher).trim();
      course.location = String(course.location || '').trim();
      course.credit = Number(course.credit) || 0;
      course.note = String(course.note || '').trim();
      db.courses.push(course);
      return delay(decorate(persistAnd(course)), LATENCY);
    },
    updateCourse: function (id, payload) {
      ensureLocalDb();
      var index = -1;
      for (var i = 0; i < db.courses.length; i++) {
        if (db.courses[i].id === id) { index = i; break; }
      }
      if (index === -1) { return delay(fail('课程不存在或已被删除'), 120); }
      var error = validate(payload);
      if (error) { return delay(fail(error), 120); }
      var conflict = findConflict(payload, id);
      if (conflict) {
        return delay(fail('与已有课程《' + conflict.name + '》时间冲突，请调整节次或周次', { conflict: conflict }), LATENCY);
      }
      var updated = deepClone(payload);
      updated.id = id;
      updated.name = String(updated.name).trim();
      updated.teacher = String(updated.teacher).trim();
      updated.location = String(updated.location || '').trim();
      updated.credit = Number(updated.credit) || 0;
      updated.note = String(updated.note || '').trim();
      db.courses[index] = updated;
      return delay(decorate(persistAnd(updated)), LATENCY);
    },
    deleteCourse: function (id) {
      ensureLocalDb();
      var index = -1;
      for (var i = 0; i < db.courses.length; i++) {
        if (db.courses[i].id === id) { index = i; break; }
      }
      if (index === -1) { return delay(fail('课程不存在或已被删除'), 120); }
      db.courses.splice(index, 1);
      return delay(persistAnd({ id: id }), LATENCY);
    },
    getSchedule: function (week) {
      ensureLocalDb();
      var w = Number(week);
      var list = db.courses.filter(function (c) {
        return courseWeeks(c).indexOf(w) !== -1;
      });
      return delay({
        week: w,
        courses: sortCourses(list).map(decorate)
      }, LATENCY);
    },
    fetchFromJwxt: function (params) {
      params = params || {};
      var studentId = String(params.studentId || '').trim();
      var password = String(params.password || '');
      if (!studentId) { return delay(fail('请输入学号'), 120); }
      if (!password) { return delay(fail('请输入教务系统密码'), 120); }
      return delay({
        studentId: studentId,
        semesterName: db.semester.name,
        source: '正方教务系统（演示模拟数据）',
        courses: deepClone(JWXT_MOCK_COURSES)
      }, 1500);
    },
    importCourses: function (list) {
      ensureLocalDb();
      var result = { imported: [], skipped: [] };
      (list || []).forEach(function (raw, index) {
        var payload = normalizeImported(raw, index);
        var error = validate(payload);
        if (error) {
          result.skipped.push({ name: payload.name, reason: error });
          return;
        }
        var conflict = findConflict(payload, null);
        if (conflict) {
          result.skipped.push({
            name: payload.name,
            reason: '与《' + conflict.name + '》时间冲突',
            conflictWith: conflict.name
          });
          return;
        }
        payload.id = 'j' + (++importSeq);
        db.courses.push(payload);
        result.imported.push(decorate(payload));
      });
      return delay(persistAnd(result), LATENCY);
    },
    resetDemo: function () {
      ensureLocalDb();
      db.courses = deepClone(SEED_COURSES);
      idSeq = 100;
      importSeq = 500;
      return delay(persistAnd({ total: db.courses.length }), 160);
    },
    clearCourses: function () {
      ensureLocalDb();
      db.courses = [];
      return delay(persistAnd({ total: 0 }), 160);
    }
  };

  /* ============================ 对外 API ============================ */

  var api = {
    getSemester: function () { return route(remote.getSemester, local.getSemester); },
    getWeekDates: function (week) { return route(function () { return remote.getWeekDates(week); }, function () { return local.getWeekDates(week); }); },
    listCourses: function (params) { return route(function () { return remote.listCourses(params); }, function () { return local.listCourses(params); }); },
    getCourse: function (id) { return route(function () { return remote.getCourse(id); }, function () { return local.getCourse(id); }); },
    createCourse: function (payload) { return route(function () { return remote.createCourse(payload); }, function () { return local.createCourse(payload); }); },
    updateCourse: function (id, payload) { return route(function () { return remote.updateCourse(id, payload); }, function () { return local.updateCourse(id, payload); }); },
    deleteCourse: function (id) { return route(function () { return remote.deleteCourse(id); }, function () { return local.deleteCourse(id); }); },
    getSchedule: function (week) { return route(function () { return remote.getSchedule(week); }, function () { return local.getSchedule(week); }); },
    fetchFromJwxt: function (params) { return route(function () { return remote.fetchFromJwxt(params); }, function () { return local.fetchFromJwxt(params); }); },
    importCourses: function (list) { return route(function () { return remote.importCourses(list); }, function () { return local.importCourses(list); }); },
    resetDemo: function () { return route(remote.resetDemo, local.resetDemo); },
    clearCourses: function () { return route(remote.clearCourses, local.clearCourses); },

    /** 当前模式说明（UI 提示文案用，不改交互结构） */
    describeMode: function () {
      return probeBackend().then(function (remoteMode) {
        return remoteMode
          ? { remote: true, importTip: '将自动登录教务系统并读取课表；自动重试上限 2 次，连续失败 3 次教务系统会锁号 3 分钟，请确认账号密码正确。' }
          : { remote: false, importTip: '未连接后端服务，当前为演示模式，读取到的是模拟数据。启动后端（python server/app.py）后将自动登录真实教务系统。' };
      });
    },

    /* 供 UI 复用的纯函数（两模式通用） */
    helpers: {
      expandWeeks: expandWeeks,
      formatWeekRule: formatWeekRule,
      periodTimeRange: function (startPeriod, endPeriod) {
        var times = (backendMode && lastKnownSemester && lastKnownSemester.periodTimes) || PERIOD_TIMES;
        return periodTimeRangeWith(times, startPeriod, endPeriod);
      },
      weekdayLabel: function (day) { return WEEKDAY_LABELS[day - 1] || ''; },
      /** 传入一门课（payload 结构），返回与它时间冲突的已有课程或 null */
      checkConflict: function (course) {
        if (backendMode) {
          var c = findConflictIn(lastKnownCourses, course, null);
          return c ? { id: c.id, name: c.name } : null;
        }
        ensureLocalDb();
        var found = findConflict(course, null);
        return found ? { id: found.id, name: found.name } : null;
      }
    }
  };

  global.CourseStore = api;
})(window);
