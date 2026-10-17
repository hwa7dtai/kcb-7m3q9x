/**
 * 数据层自检脚本（不参与页面运行，仅用于开发期验证）。
 *
 * 运行： node demo/test/store.test.js
 *
 * 覆盖：学期信息、节次时间、周次展开（单周/双周）、课表按周过滤、空周次、
 *       搜索、新增、校验、时间冲突、更新、删除、教务系统导入、清空与重置。
 * 接入真实接口后，本脚本可继续作为数据层的契约测试使用。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const storePath = path.join(__dirname, '..', 'js', 'store.js');
const code = fs.readFileSync(storePath, 'utf8');
const windowStub = {};
new Function('window', code)(windowStub);
const Store = windowStub.CourseStore;

let passed = 0;
let failed = 0;

function check(name, ok, detail) {
  if (ok) {
    passed++;
    console.log('  PASS  ' + name);
  } else {
    failed++;
    console.log('  FAIL  ' + name + (detail === undefined ? '' : '  → ' + detail));
  }
}

async function expectReject(name, task, pattern) {
  try {
    await task;
    check(name, false, '预期报错但成功了');
  } catch (err) {
    const ok = !pattern || pattern.test(err.message);
    check(name, ok, err.message);
    return err;
  }
  return null;
}

function basePayload(overrides) {
  return Object.assign({
    name: '软件工程',
    teacher: '测试教师',
    location: '教学楼 Z-999',
    credit: 2,
    dayOfWeek: 6,
    startPeriod: 1,
    endPeriod: 2,
    weekRule: { from: 1, to: 16, pattern: 'all' },
    category: '选修',
    color: 'blue',
    note: ''
  }, overrides || {});
}

(async function run() {
  console.log('\n课程表 Demo · 数据层自检\n');

  /* ---------- 学期 ---------- */
  const semester = await Store.getSemester();
  check('学期信息可读且共 18 周', semester.totalWeeks === 18, semester.totalWeeks);
  check('当前周落在 1-18 之间', semester.currentWeek >= 1 && semester.currentWeek <= 18, semester.currentWeek);
  check('星期标签 7 个', semester.weekdayLabels.length === 7);

  /* ---------- 列表与周次展开 ---------- */
  const all = await Store.listCourses({});
  check('初始课程共 10 门', all.length === 10, all.length);

  const odd = all.filter(c => c.name === '计算机网络')[0];
  check('单周课程展开为奇数周', odd.weeks.join(',') === '1,3,5,7,9,11,13,15', odd.weeks.join(','));

  const even = all.filter(c => c.name === '计算机组成原理实验')[0];
  check('双周课程展开为偶数周', even.weeks.join(',') === '2,4,6,8,10,12,14,16', even.weeks.join(','));
  check('连堂四节课程节次为 5-8', even.startPeriod === 5 && even.endPeriod === 8);

  /* ---------- 按周过滤 ---------- */
  const w1 = await Store.getSchedule(1);
  const w2 = await Store.getSchedule(2);
  const w17 = await Store.getSchedule(17);

  check('第 1 周有单周课程', w1.courses.some(c => c.name === '计算机网络'));
  check('第 2 周无单周课程', !w2.courses.some(c => c.name === '计算机网络'));
  check('第 1 周无双周实验课', !w1.courses.some(c => c.name === '计算机组成原理实验'));
  check('第 2 周有双周实验课', w2.courses.some(c => c.name === '计算机组成原理实验'));
  check('第 17 周为空（覆盖空数据态）', w17.courses.length === 0, w17.courses.length);
  check('第 1 周有课', w1.courses.length > 0, w1.courses.length);

  /* ---------- 搜索 ---------- */
  const byTeacher = await Store.listCourses({ keyword: '王振宇' });
  check('按教师搜索命中 1 门', byTeacher.length === 1 && byTeacher[0].name === '数据结构', byTeacher.length);

  const byPlace = await Store.listCourses({ keyword: '信息楼' });
  check('按教室搜索命中 2 门', byPlace.length === 2, byPlace.length);

  const noMatch = await Store.listCourses({ keyword: '不存在的课程' });
  check('无匹配时返回空列表', noMatch.length === 0);

  /* ---------- 新增 ---------- */
  const created = await Store.createCourse(basePayload());
  check('新增课程返回 id', !!created.id, created.id);
  const afterCreate = await Store.listCourses({});
  check('新增后列表为 11 门', afterCreate.length === 11, afterCreate.length);

  /* ---------- 校验 ---------- */
  await expectReject('课程名为空时报错', Store.createCourse(basePayload({ name: '' })), /课程名称/);
  await expectReject('教师为空时报错', Store.createCourse(basePayload({ teacher: '  ' })), /任课教师/);
  await expectReject('节次倒置时报错', Store.createCourse(basePayload({ startPeriod: 5, endPeriod: 2 })), /节次/);
  await expectReject('周次超出学期时报错',
    Store.createCourse(basePayload({ weekRule: { from: 1, to: 30, pattern: 'all' } })), /周次/);

  /* ---------- 时间冲突 ---------- */
  const conflictErr = await expectReject('同一时段重复排课触发冲突',
    Store.createCourse(basePayload({ name: '冲突课程' })), /冲突/);
  check('冲突错误信息带冲突课程', !!(conflictErr && conflictErr.conflict && conflictErr.conflict.name),
    conflictErr && conflictErr.conflict && conflictErr.conflict.name);

  /* 不同星期 → 不冲突；周次完全不重叠 → 也不冲突 */
  const noConflictDay = await Store.createCourse(basePayload({ name: '周日课程', dayOfWeek: 7 }));
  check('星期不同时不冲突', !!noConflictDay.id);

  const noConflictWeek = await Store.createCourse(
    basePayload({ name: '期末短课', weekRule: { from: 17, to: 18, pattern: 'all' } }));
  check('周次不重叠时不冲突', !!noConflictWeek.id);

  /* ---------- 更新 ---------- */
  const updated = await Store.updateCourse(created.id, basePayload({ name: '软件工程（已改名）', location: '教学楼 A-101' }));
  check('更新后名称生效', updated.name === '软件工程（已改名）', updated.name);
  check('更新后地点生效', updated.location === '教学楼 A-101');

  await expectReject('更新后与已有课程冲突时报错',
    Store.updateCourse(noConflictWeek.id,
      basePayload({ name: '期末短课', weekRule: { from: 1, to: 16, pattern: 'all' } })), /冲突/);

  const selfUpdate = await Store.updateCourse(noConflictWeek.id,
    basePayload({ name: '期末短课（改名）', weekRule: { from: 17, to: 18, pattern: 'all' } }));
  check('更新自身不误判为冲突', selfUpdate.name === '期末短课（改名）', selfUpdate.name);

  /* ---------- 删除 ---------- */
  await Store.deleteCourse(created.id);
  await Store.deleteCourse(noConflictDay.id);
  await Store.deleteCourse(noConflictWeek.id);
  const afterDelete = await Store.listCourses({});
  check('删除后恢复为 10 门', afterDelete.length === 10, afterDelete.length);
  await expectReject('删除不存在的课程报错', Store.deleteCourse('not-exist'), /不存在/);
  await expectReject('查询不存在的课程报错', Store.getCourse('not-exist'), /不存在/);

  /* ---------- 演示控制 ---------- */
  await Store.clearCourses();
  const cleared = await Store.listCourses({});
  check('清空后列表为空', cleared.length === 0, cleared.length);
  const clearedSchedule = await Store.getSchedule(1);
  check('清空后课表为空', clearedSchedule.courses.length === 0);

  await Store.resetDemo();
  const reset = await Store.listCourses({});
  check('重置后恢复 10 门', reset.length === 10, reset.length);

  /* ---------- 节次时间 ---------- */
  check('提供 12 个节次的上下课时间', semester.periodTimes.length === 12, semester.periodTimes.length);
  const timeCourse = w1.courses.filter(c => c.name === '高等数学 A（上）')[0];
  check('第 1-2 节时间为 08:00-09:40', !!timeCourse && timeCourse.timeText === '08:00-09:40',
    timeCourse && timeCourse.timeText);
  const timeLong = w2.courses.filter(c => c.name === '计算机组成原理实验')[0];
  check('第 5-8 节连堂时间为 14:00-17:40', !!timeLong && timeLong.timeText === '14:00-17:40',
    timeLong && timeLong.timeText);

  /* ---------- 教务系统导入（Mock） ---------- */
  await expectReject('学号为空时拒绝读取', Store.fetchFromJwxt({ studentId: '  ', password: 'x' }), /学号/);
  await expectReject('密码为空时拒绝读取', Store.fetchFromJwxt({ studentId: '2026001', password: '' }), /密码/);

  const fetched = await Store.fetchFromJwxt({ studentId: '2026001', password: 'demo' });
  check('模拟读取到 10 门课程', fetched.courses.length === 10, fetched.courses.length);
  check('读取结果带来源标识', fetched.source.indexOf('教务系统') !== -1, fetched.source);

  const beforeImport = await Store.listCourses({});
  const importResult = await Store.importCourses(fetched.courses);
  check('冲突课程被跳过 5 门', importResult.skipped.length === 5, importResult.skipped.length);
  check('无冲突课程导入 5 门', importResult.imported.length === 5, importResult.imported.length);
  check('跳过原因标注冲突课程',
    importResult.skipped.every(s => /冲突/.test(s.reason) && !!s.conflictWith),
    importResult.skipped.map(s => s.reason).join(' | '));
  check('导入课程带教务系统来源标记', importResult.imported.every(c => c.source === 'jwxt'));
  const afterImport = await Store.listCourses({});
  check('导入后列表增加 5 门', afterImport.length === beforeImport.length + 5, afterImport.length);

  const reimport = await Store.importCourses(fetched.courses);
  check('重复导入全部被冲突检测拦截',
    reimport.imported.length === 0 && reimport.skipped.length === 10,
    reimport.imported.length + '/' + reimport.skipped.length);

  /* 清理导入数据，恢复初始状态 */
  const jwxtImported = afterImport.filter(c => c.source === 'jwxt');
  for (const c of jwxtImported) { await Store.deleteCourse(c.id); }
  const afterCleanup = await Store.listCourses({});
  check('清理导入课程后恢复 10 门', afterCleanup.length === 10, afterCleanup.length);

  /* ---------- 供 UI 复用的纯函数 ---------- */
  check('checkConflict 能识别冲突',
    !!Store.helpers.checkConflict({ dayOfWeek: 1, startPeriod: 1, endPeriod: 2, weekRule: { from: 1, to: 16, pattern: 'all' } }));
  check('checkConflict 对空闲时段返回 null',
    Store.helpers.checkConflict({ dayOfWeek: 7, startPeriod: 1, endPeriod: 2, weekRule: { from: 1, to: 16, pattern: 'all' } }) === null);
  check('periodTimeRange 计算连堂时间', Store.helpers.periodTimeRange(5, 8) === '14:00-17:40',
    Store.helpers.periodTimeRange(5, 8));

  /* ---------- 结果 ---------- */
  console.log('\n结果： ' + passed + ' 通过，' + failed + ' 失败\n');
  process.exit(failed ? 1 : 0);
})().catch(err => {
  console.error('自检脚本异常：', err);
  process.exit(1);
});
