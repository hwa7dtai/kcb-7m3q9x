/**
 * UI 冒烟测试：用 jsdom 真实执行 index.html + store.js + app.js，
 * 走通「周次切换 → 空态 → 搜索 → 详情 → 新增（含冲突）→ 删除 → 清空 → 重置 → 教务系统导入」全流程。
 *
 * 运行（需要 Node.js 与 jsdom）：
 *   npm install jsdom            # 或使用已装好的 jsdom
 *   NODE_PATH=<jsdom 所在 node_modules> node demo/test/ui.smoke.js
 *
 * 本文件不参与页面运行，仅用于开发期验证。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const FILE = path.join(__dirname, '..', 'index.html');
const errors = [];

let passed = 0, failed = 0;
function check(name, ok, detail) {
  if (ok) { passed++; console.log('  PASS  ' + name); }
  else { failed++; console.log('  FAIL  ' + name + (detail === undefined ? '' : '  → ' + detail)); }
}
const wait = ms => new Promise(r => setTimeout(r, ms));

const vc = new VirtualConsole();
vc.on('jsdomError', e => {
  const msg = e.message || String(e);
  if (/Could not parse CSS/.test(msg)) return; // jsdom 不解析部分现代 CSS，忽略
  if (/HTMLCanvasElement|getContext|canvas npm package/i.test(msg)) return; // jsdom 无 canvas 包时的提示
  errors.push('jsdomError: ' + msg);
});
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));

JSDOM.fromFile(FILE, {
  runScripts: 'dangerously',
  resources: 'usable',
  pretendToBeVisual: true,
  virtualConsole: vc
}).then(async dom => {
  const { window } = dom;
  const doc = window.document;
  const $ = s => doc.querySelector(s);
  const $$ = s => Array.from(doc.querySelectorAll(s));
  const click = el => el && el.click();

  await wait(1600);

  console.log('\n课程表 Demo · UI 冒烟\n');

  /* 1. 无脚本错误 */
  check('页面无 JS 运行时错误', errors.length === 0, errors.join(' | '));

  /* 2. 首屏渲染 */
  const blocks = $$('.course-block');
  check('课表渲染出课程色块', blocks.length > 0, blocks.length);
  check('表头渲染 7 天', $$('.grid-head').length === 7, $$('.grid-head').length);
  check('学期信息已填充', $('#brandSemester').textContent !== '加载中…', $('#brandSemester').textContent);
  check('左上角品牌图标与标题已移除', $$('.brand-logo').length === 0 && !$('.brand').textContent.includes('课程表'));
  check('周次标题已渲染', /第 \d+ 周/.test($('#weekTitle').textContent), $('#weekTitle').textContent.trim());
  check('日期表头非空', $$('.head-date').some(e => e.textContent.trim().length > 0));
  check('氛围粒子画布已挂载', !!$('#particleCanvas'));
  check('导航滑动指示器存在', !!$('#navIndicator'));

  /* 3. 左侧时间列（课程时间） */
  const periodTimes = $$('.grid-period .period-time');
  check('左侧时间列渲染 12 行', periodTimes.length === 12, periodTimes.length);
  check('首行时间为 08:00', periodTimes[0] && periodTimes[0].textContent === '08:00',
    periodTimes[0] && periodTimes[0].textContent);
  check('时间列标注节次', /第 \d+ 节/.test(periodTimes[0] && periodTimes[0].parentNode.textContent || ''),
    periodTimes[0] && periodTimes[0].parentNode.textContent.trim());
  check('时间列不再出现上午/下午字样',
    $$('.grid-period').every(e => e.textContent.indexOf('上午') === -1 && e.textContent.indexOf('下午') === -1));
  check('左上角标注“时间”轴标题',
    !!$('.grid-corner') && $('.grid-corner').textContent.indexOf('时间') !== -1,
    $('.grid-corner') && $('.grid-corner').textContent.trim());

  /* 3.6 网格显式定位回归：课程块为显式定位，若 period/cell 依赖自动排布，
     自动布局会绕过被占用格子，导致节次标签与空格子窜到其他日期列 */
  const gridPeriods = $$('.grid-period');
  const gridCells = $$('.grid-cell');
  const gridHeads = $$('.grid-head');
  check('课表空格子数量为 12 节 × 7 天', gridCells.length === 84, gridCells.length);
  check('节次标签全部显式钉在第 1 列且行号连续',
    gridPeriods.every((e, i) => e.style.gridColumn === '1' && e.style.gridRow === String(i + 2)),
    gridPeriods.map(e => e.style.gridColumn + '/' + e.style.gridRow).join(' '));
  check('空格子全部显式定位（列 1-8、行号非空）',
    gridCells.every(e => /^[1-8]$/.test(e.style.gridColumn) && /^\d+$/.test(e.style.gridRow)),
    '未显式定位数量：' + gridCells.filter(e => !e.style.gridColumn || !e.style.gridRow).length);
  check('日期表头全部显式位于第 1 行',
    gridHeads.every((e, i) => e.style.gridRow === '1' && e.style.gridColumn === String(i + 2)),
    gridHeads.map(e => e.style.gridColumn + '/' + e.style.gridRow).join(' '));
  check('左上角“时间”轴显式位于 (1,1)',
    !!$('.grid-corner') && $('.grid-corner').style.gridColumn === '1' && $('.grid-corner').style.gridRow === '1');

  /* 3.7 重置 / 清空入口应位于课程管理板块，而非顶部栏 */
  check('重置数据按钮位于课程管理板块',
    !!$('#view-courses #btnReset') && !$('.app-header #btnReset'));
  check('清空课程按钮位于课程管理板块',
    !!$('#view-courses #btnClear') && !$('.app-header #btnClear'));
  check('数据管理按钮组存在', !!$('#view-courses .toolbar-danger'));

  /* 3.5 今天高亮（仅当本周包含今天时断言，保证测试长期稳定） */
  const todayHeads = $$('.grid-head.is-today');
  check('今天列最多高亮一列', todayHeads.length <= 1, todayHeads.length);
  if (todayHeads.length === 1) {
    check('今天列表头带“今天”标识', !!todayHeads[0].querySelector('.head-today'));
    check('今天列单元格有高亮底色', $$('.grid-cell.is-today-col').length > 0);
  }

  /* 4. 课程块含教师、地点、周次、时间 */
  const firstBlock = blocks[0];
  check('课程块包含教师姓名', firstBlock && firstBlock.textContent.indexOf('李文博') !== -1,
    firstBlock && firstBlock.textContent.trim());
  check('课程块包含上课地点', firstBlock && /教学楼|信息楼|外语楼|实验楼|文科楼|田径场/.test(firstBlock.textContent));
  check('课程块包含周次信息', firstBlock && firstBlock.textContent.indexOf('第') !== -1);
  check('课程块包含上课时间', firstBlock && /\d{2}:\d{2}-\d{2}:\d{2}/.test(firstBlock.textContent),
    firstBlock && firstBlock.textContent.trim());

  /* 5. 周次切换 */
  const weekBefore = $('#weekTitle').textContent;
  click($('#btnNextWeek'));
  await wait(900);
  check('下一周切换生效', $('#weekTitle').textContent !== weekBefore,
    weekBefore.trim() + ' → ' + $('#weekTitle').textContent.trim());

  /* 6. 切到第 17 周应出现空状态 */
  for (let i = 0; i < 20 && !/第 17 周/.test($('#weekTitle').textContent); i++) {
    click($('#btnNextWeek'));
    await wait(320);
  }
  await wait(500);
  check('第 17 周出现空数据状态', /第 17 周/.test($('#weekTitle').textContent) && !!$('.empty-state'),
    $('#weekTitle').textContent.trim());
  check('空状态含引导按钮', $$('.empty-state [data-action]').length >= 1);

  click($('#btnThisWeek'));
  await wait(900);
  check('回到本周按钮生效',
    $('#weekTitle').textContent.indexOf('第') !== -1 && !$('#weekNowBadge').hidden && $('#btnThisWeek').disabled,
    $('#weekTitle').textContent.trim());

  /* 7. 课程列表 */
  click($('.nav-btn[data-view="courses"]'));
  await wait(900);
  check('课程列表渲染 10 项', $$('.course-item').length === 10, $$('.course-item').length);
  check('列表计数已更新', $('#listCount').textContent.indexOf('10') !== -1, $('#listCount').textContent);
  check('列表项包含上课时间', /周/.test($('.when-day').textContent) && /\d{2}:\d{2}/.test($('.when-time').textContent),
    $('.when-time') && $('.when-time').textContent);

  /* 8. 搜索 */
  const input = $('#searchInput');
  input.value = '王振宇';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  await wait(900);
  check('搜索过滤生效', $$('.course-item').length === 1, $$('.course-item').length);

  input.value = '不存在的关键字';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  await wait(900);
  check('搜索无结果显示空状态',
    $$('#view-courses .course-item').length === 0 && !!$('#view-courses .empty-state'));
  check('搜索空态文案含关键词提示',
    $('#view-courses .empty-title').textContent.indexOf('没有找到匹配的课程') !== -1,
    $('#view-courses .empty-title').textContent);

  /* 9. 详情弹窗 */
  input.value = '';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  await wait(900);
  click($$('.course-item [data-action="open-course"]')[0]);
  await wait(700);
  check('详情弹窗已打开', $('#modalDetail').classList.contains('is-open'));
  check('详情含课程字段', $('.detail-grid') && $$('.detail-grid dt').length >= 5, $$('.detail-grid dt').length);
  check('详情含上课时间行', $$('.detail-grid dt').some(dt => dt.textContent === '上课时间'));

  click($('#modalDetail .modal-close'));
  await wait(300);
  check('详情弹窗可关闭', !$('#modalDetail').classList.contains('is-open'));

  /* 10. 新增（时间冲突） */
  click($('#btnAdd'));
  await wait(400);
  check('新增表单已打开', $('#modalForm').classList.contains('is-open'));
  $('#fName').value = '冲突测试课';
  $('#fTeacher').value = '测试';
  $('#fDay').value = '1';
  $('#fStart').value = '1';
  $('#fEnd').value = '2';
  $('#fWeekFrom').value = '1';
  $('#fWeekTo').value = '16';
  click($('#btnFormSave'));
  await wait(1000);
  check('冲突时表单内提示错误', $('#formError').textContent.indexOf('冲突') !== -1, $('#formError').textContent);

  /* 11. 新增成功 */
  $('#fDay').value = '7';
  $('#fStart').value = '1';
  $('#fEnd').value = '2';
  click($('#btnFormSave'));
  await wait(1200);
  check('新增成功后弹窗关闭', !$('#modalForm').classList.contains('is-open'));
  check('新增后列表变 11 项', $$('.course-item').length === 11, $$('.course-item').length);

  /* 12. 删除 */
  const delBtn = $$('.course-item [data-action="delete-course"]')[0];
  click(delBtn);
  await wait(700);
  check('删除确认弹窗打开', $('#modalConfirm').classList.contains('is-open'));
  click($('#btnConfirmOk'));
  await wait(1200);
  check('删除后列表回到 10 项', $$('.course-item').length === 10, $$('.course-item').length);

  /* 13. 清空 → 空状态 → 重置 */
  click($('#btnClear'));
  await wait(500);
  click($('#btnConfirmOk'));
  await wait(1200);
  check('清空后课程列表为空状态',
    $$('#view-courses .course-item').length === 0 && !!$('#view-courses .empty-state'));
  check('列表空态文案正确',
    $('#view-courses .empty-title').textContent.indexOf('本学期还没有课程') !== -1,
    $('#view-courses .empty-title').textContent);
  check('清空后课表同步为空状态', !!$('#view-schedule .empty-state'));
  check('空态提供教务系统导入入口',
    $$('#view-courses .empty-state [data-action="import-jwxt"]').length === 1);

  click($('#btnReset'));
  await wait(1200);
  check('重置后恢复 10 项', $$('.course-item').length === 10, $$('.course-item').length);

  /* 14. 从教务系统导入 */
  check('导入按钮带描边绘制动效', $('#btnImport').classList.contains('btn-trace'));
  click($('#btnImport'));
  await wait(400);
  check('导入弹窗已打开', $('#modalImport').classList.contains('is-open'));
  check('导入弹窗默认展示账号表单', !!$('#impStudent') && !!$('#impPassword'));

  click($('#btnImportFetch'));
  await wait(400);
  check('未填写账号时给出提示', ($('#importError') || {}).textContent.indexOf('学号') !== -1,
    ($('#importError') || {}).textContent);

  $('#impStudent').value = '2026001';
  $('#impPassword').value = 'demo123';
  click($('#btnImportFetch'));
  await wait(500);
  check('读取中显示加载步骤',
    !!$('.imp-steps') && $('.imp-steps').textContent.indexOf('读取课表') !== -1);
  check('读取中展示液态光球与环绕卫星',
    !!$('.imp-orb') && !!$('.imp-orb .imp-orbit'));
  check('步骤切换有过渡动画容器', !!$('#importBody .import-step'));

  await wait(1800);
  const importItems = $$('#importBody .import-item');
  check('预览列表渲染 10 门', importItems.length === 10, importItems.length);
  const disabledItems = importItems.filter(el => el.classList.contains('is-disabled'));
  check('其中 5 门与现有课表冲突并置灰', disabledItems.length === 5, disabledItems.length);
  check('冲突项标注冲突课程',
    disabledItems.every(el => /与《.+》冲突/.test(el.textContent)),
    disabledItems.map(el => el.textContent.trim().slice(0, 40)).join(' | '));
  const checkedBoxes = $$('#importBody .import-item input[type="checkbox"]').filter(b => b.checked);
  check('无冲突项默认勾选 5 门', checkedBoxes.length === 5, checkedBoxes.length);

  click($('#btnImportConfirm'));
  await wait(1400);
  check('导入后弹窗关闭', !$('#modalImport').classList.contains('is-open'));
  check('导入成功提示 Toast', !!$('.toast.is-success') && $('.toast.is-success').textContent.indexOf('导入') !== -1,
    $('.toast.is-success') && $('.toast.is-success').textContent);
  check('导入后列表为 15 项', $$('.course-item').length === 15, $$('.course-item').length);

  /* 15. 导入结果在课表视图可见 */
  click($('.nav-btn[data-view="schedule"]'));
  await wait(900);
  check('课表视图渲染导入的课程', $$('.course-block').some(b => b.textContent.indexOf('概率论与数理统计') !== -1));

  click($('#btnReset'));
  await wait(1200);
  check('最终重置后恢复 10 项', $$('.course-item').length === 10, $$('.course-item').length);

  check('全流程无新增 JS 错误', errors.length === 0, errors.join(' | '));

  console.log('\n结果： ' + passed + ' 通过，' + failed + ' 失败\n');
  window.close();
  process.exit(failed ? 1 : 0);
}).catch(err => {
  console.error('冒烟脚本异常：', err);
  process.exit(1);
});
