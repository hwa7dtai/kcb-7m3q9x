/**
 * 云端静态版契约测试（零依赖，只需 Node.js）：
 *   node demo/test/cloud.test.js
 *
 * 模拟 GitHub Pages 环境：没有后端（api/health 404），但存在 schedule.json。
 * 验证「数据存本地 + 点按更新」的核心行为。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const code = fs.readFileSync(path.join(__dirname, '..', 'js', 'store.js'), 'utf8');

const sample = {
  generatedAt: '2026-10-19 05:30',
  semester: {
    id: '2026-2027-1', name: '2026—2027 学年 第一学期',
    startDate: '2026-08-31', totalWeeks: 19,
    weekdayLabels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
    totalPeriods: 10,
    periodTimes: Array.from({ length: 10 }, (_, i) => ({ start: '08:10', end: '09:05' }))
  },
  courses: [
    { id: 'j1', name: '高等数学AⅠ', teacher: '张林', location: 'A6-306', credit: 5,
      dayOfWeek: 2, startPeriod: 7, endPeriod: 8,
      weekRule: { from: 4, to: 17, pattern: 'all' }, weeks: [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
      category: '必修', color: 'blue', note: '', source: 'jwxt' },
    { id: 'j2', name: '大学英语AⅠ', teacher: '吴珂', location: 'A6-304', credit: 2,
      dayOfWeek: 2, startPeriod: 1, endPeriod: 2,
      weekRule: { from: 5, to: 13, pattern: 'odd' }, weeks: [5, 7, 9, 11, 13],
      category: '必修', color: 'teal', note: '', source: 'jwxt' }
  ]
};

/* 极简 localStorage */
function makeStorage() {
  const data = {};
  return {
    getItem: k => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: k => { delete data[k]; }
  };
}

/* 模拟静态站点：health 404，schedule.json 200 */
function makeFetch(state) {
  return function (url) {
    if (String(url).indexOf('health') !== -1) {
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ error: '接口不存在' }) });
    }
    if (String(url).indexOf('schedule.json') !== -1) {
      state.calls += 1;
      if (state.empty) {
        return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(sample) });
    }
    return Promise.reject(new Error('unexpected ' + url));
  };
}

let passed = 0;
let failed = 0;
function check(name, ok, detail) {
  if (ok) { passed++; console.log('  PASS  ' + name); }
  else { failed++; console.log('  FAIL  ' + name + (detail === undefined ? '' : '  → ' + detail)); }
}

(async function run() {
  console.log('\n课程表 · 云端静态版契约测试\n');

  const state = { calls: 0, empty: false };
  const win = { fetch: makeFetch(state), localStorage: makeStorage() };
  new Function('window', code)(win);
  const Store = win.CourseStore;

  const mode = await Store.describeMode();
  check('无后端时判定为离线/静态模式', mode.remote === false, JSON.stringify(mode));

  const before = await Store.listCourses({});
  check('首次打开是本地种子数据（未联网）', before.length === 10, before.length);

  const result = await Store.pullCloudSchedule();
  check('同步返回课程数', result.total === 2, result.total);
  check('携带生成时间', result.generatedAt === '2026-05-19 05:30' || result.generatedAt === '2026-10-19 05:30', result.generatedAt);

  const after = await Store.listCourses({});
  check('同步后课程替换为云端数据', after.length === 2 && after.some(c => c.name === '高等数学AⅠ'), after.map(c => c.name).join(','));
  check('上课时间使用云端作息表（10 节 08:10 起）', after[0].timeText === '08:10-09:05', after[0].timeText);

  const sem = await Store.getSemester();
  check('同步后学期起始日更新', sem.startDate === '2026-08-31', sem.startDate);
  check('同步后使用 10 节制（与学校一致）', sem.totalPeriods === 10, sem.totalPeriods);

  const w7 = await Store.getSchedule(7);
  check('按周过滤使用云端周次', w7.courses.length === 2, w7.courses.length);
  const w8 = await Store.getSchedule(8);
  check('单周课在双周不出现', w8.courses.length === 1 && w8.courses[0].name === '高等数学AⅠ', w8.courses.map(c => c.name).join(','));

  const cached = win.localStorage.getItem('kcb.cache.v1');
  check('数据已写入本地存储（关网页也不丢）', !!cached && JSON.parse(cached).courses.length === 2);

  state.empty = true;
  let err = null;
  try { await Store.pullCloudSchedule(); } catch (e) { err = e; }
  check('云端无数据时给出可操作提示', !!err && /Actions|还没有课表/.test(err.message), err && err.message);

  const offline = {};
  new Function('window', code)(offline);
  const OfflineStore = offline.CourseStore;
  let err2 = null;
  try { await OfflineStore.pullCloudSchedule(); } catch (e) { err2 = e; }
  check('不支持联网的环境给出明确提示', !!err2 && /不支持联网/.test(err2.message), err2 && err2.message);

  console.log('\n结果： ' + passed + ' 通过，' + failed + ' 失败\n');
  process.exit(failed ? 1 : 0);
})().catch(err => {
  console.error('测试异常：', err);
  process.exit(1);
});
