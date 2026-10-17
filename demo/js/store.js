/**
 * 数据层：集中管理全部数据访问。
 *
 * 当前为 Mock 实现，所有方法均返回 Promise 并模拟网络延迟，
 * 因此 UI 层已经按"异步接口"的方式编写。
 *
 * 接入真实后端时，只需把本文件中各方法的实现替换为 fetch 调用，
 * 保持方法名与返回结构不变，UI 层无需任何改动。
 */
(function (global) {
  'use strict';

  /* ============================ 基础配置 ============================ */

  var LATENCY = 260; // 模拟网络延迟（毫秒）

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

  /* ============================ 教务系统导入（Mock） ============================ */

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
  var importSeq = 500;

  /** 把教务系统读到的原始课程规整为内部数据结构 */
  function normalizeImported(raw, index) {
    return {
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
  }

  /* ============================ 内存数据库 ============================ */

  var db = {
    semester: SEMESTER,
    courses: deepClone(SEED_COURSES)
  };

  var idSeq = 100;

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

  /* ============================ 工具函数 ============================ */

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

  /** 周次规则的可读描述，如 "第 1-15 周(单周)" */
  function formatWeekRule(rule) {
    if (!rule) { return '未设置'; }
    var suffix = rule.pattern === 'odd' ? '(单周)' : (rule.pattern === 'even' ? '(双周)' : '');
    return '第 ' + rule.from + '-' + rule.to + ' 周' + suffix;
  }

  /** 起止节次对应的上课时间范围，如 "08:00-09:40" */
  function periodTimeRange(startPeriod, endPeriod) {
    var a = PERIOD_TIMES[startPeriod - 1];
    var b = PERIOD_TIMES[endPeriod - 1];
    if (!a || !b) { return ''; }
    return a.start + '-' + b.end;
  }

  /** 两个课程在具体周次上是否存在交集 */
  function hasWeekOverlap(a, b) {
    var wa = expandWeeks(a.weekRule);
    var wb = expandWeeks(b.weekRule);
    for (var i = 0; i < wa.length; i++) {
      if (wb.indexOf(wa[i]) !== -1) { return true; }
    }
    return false;
  }

  /** 同一天、时段重叠、且周次有交集，即为冲突 */
  function findConflict(candidate, excludeId) {
    for (var i = 0; i < db.courses.length; i++) {
      var c = db.courses[i];
      if (c.id === excludeId) { continue; }
      if (c.dayOfWeek !== candidate.dayOfWeek) { continue; }
      var overlapPeriod = !(candidate.endPeriod < c.startPeriod || candidate.startPeriod > c.endPeriod);
      if (overlapPeriod && hasWeekOverlap(candidate, c)) { return c; }
    }
    return null;
  }

  /** 按当前日期计算所处的教学周 */
  function computeCurrentWeek() {
    var start = new Date(db.semester.startDate + 'T00:00:00');
    var now = new Date();
    var diffDays = Math.floor((now - start) / 86400000);
    var week = Math.floor(diffDays / 7) + 1;
    if (week < 1) { week = 1; }
    if (week > db.semester.totalWeeks) { week = db.semester.totalWeeks; }
    return week;
  }

  /** 某一周中每一天对应的日期 */
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

  function sortCourses(list) {
    return list.slice().sort(function (a, b) {
      if (a.dayOfWeek !== b.dayOfWeek) { return a.dayOfWeek - b.dayOfWeek; }
      return a.startPeriod - b.startPeriod;
    });
  }

  function decorate(course) {
    var copy = deepClone(course);
    copy.weeks = expandWeeks(course.weekRule);
    copy.weekText = formatWeekRule(course.weekRule);
    copy.periodText = '第 ' + course.startPeriod + '-' + course.endPeriod + ' 节';
    copy.timeText = periodTimeRange(course.startPeriod, course.endPeriod);
    copy.dayText = WEEKDAY_LABELS[course.dayOfWeek - 1] || '';
    return copy;
  }

  function validate(payload) {
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
    if (!isFinite(from) || !isFinite(to) || from < 1 || to > db.semester.totalWeeks || from > to) {
      return '周次设置有误，需在 1-' + db.semester.totalWeeks + ' 周范围内';
    }
    return null;
  }

  /* ============================ 对外 API ============================ */

  var api = {
    /* ---------- 学期信息 ---------- */
    getSemester: function () {
      var data = deepClone(db.semester);
      data.currentWeek = computeCurrentWeek();
      data.weekdayLabels = WEEKDAY_LABELS.slice();
      data.totalPeriods = TOTAL_PERIODS;
      data.periodTimes = deepClone(PERIOD_TIMES);
      return delay(data, 120);
    },

    /** 某一周的日期列表，用于课表表头 */
    getWeekDates: function (week) {
      var dates = weekDates(week).map(function (d) {
        return {
          iso: d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()),
          label: (d.getMonth() + 1) + '/' + d.getDate()
        };
      });
      return delay(dates, 80);
    },

    /* ---------- 课程：查 ---------- */
    listCourses: function (params) {
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
      var found = db.courses.filter(function (c) { return c.id === id; })[0];
      if (!found) { return delay(fail('课程不存在或已被删除'), 120); }
      return delay(decorate(found), 120);
    },

    /* ---------- 课程：增 / 改 / 删 ---------- */
    createCourse: function (payload) {
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
      return delay(decorate(course), LATENCY);
    },

    updateCourse: function (id, payload) {
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
      return delay(decorate(updated), LATENCY);
    },

    deleteCourse: function (id) {
      var index = -1;
      for (var i = 0; i < db.courses.length; i++) {
        if (db.courses[i].id === id) { index = i; break; }
      }
      if (index === -1) { return delay(fail('课程不存在或已被删除'), 120); }
      db.courses.splice(index, 1);
      return delay({ id: id }, LATENCY);
    },

    /* ---------- 课表 ---------- */
    getSchedule: function (week) {
      var w = Number(week);
      var list = db.courses.filter(function (c) {
        return expandWeeks(c.weekRule).indexOf(w) !== -1;
      });
      return delay({
        week: w,
        courses: sortCourses(list).map(decorate)
      }, LATENCY);
    },

    /* ---------- 从教务系统导入（Mock） ---------- */

    /**
     * 模拟"连接教务系统并读取课表"。
     * 真实实现按 PLAN.md：requests 会话 + RSA 加密登录 + 解析课表接口，
     * 此处仅返回模拟数据，用于演示完整导入流程。
     */
    fetchFromJwxt: function (params) {
      params = params || {};
      var studentId = String(params.studentId || '').trim();
      var password = String(params.password || '');
      if (!studentId) { return delay(fail('请输入学号'), 120); }
      if (!password) { return delay(fail('请输入教务系统密码'), 120); }
      return delay({
        studentId: studentId,
        semesterName: SEMESTER.name,
        source: '正方教务系统（模拟数据）',
        courses: deepClone(JWXT_MOCK_COURSES)
      }, 1500);
    },

    /**
     * 批量导入教务系统课程：逐门做字段校验与时间冲突检测，
     * 返回 { imported, skipped }，skip 的课程带原因，不影响其他课程导入。
     */
    importCourses: function (list) {
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
      return delay(result, LATENCY);
    },

    /* ---------- 演示控制（仅 Demo 使用） ---------- */
    resetDemo: function () {
      db.courses = deepClone(SEED_COURSES);
      idSeq = 100;
      importSeq = 500;
      return delay({ total: db.courses.length }, 160);
    },

    clearCourses: function () {
      db.courses = [];
      return delay({ total: 0 }, 160);
    },

    /* ---------- 供 UI 复用的纯函数 ---------- */
    helpers: {
      expandWeeks: expandWeeks,
      formatWeekRule: formatWeekRule,
      periodTimeRange: periodTimeRange,
      weekdayLabel: function (day) { return WEEKDAY_LABELS[day - 1] || ''; },
      /** 传入一门课（payload 结构），返回与它时间冲突的已有课程或 null */
      checkConflict: function (course) {
        var c = findConflict(course, null);
        return c ? { id: c.id, name: c.name } : null;
      }
    }
  };

  global.CourseStore = api;
})(window);
