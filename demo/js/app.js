/**
 * 交互层：负责渲染与事件处理。
 * 所有数据均通过 window.CourseStore 获取，本文件不持有任何业务数据。
 */
(function () {
  'use strict';

  var Store = window.CourseStore;

  var COLORS = ['blue', 'teal', 'amber', 'purple', 'rose', 'green', 'cyan'];

  var state = {
    view: 'schedule',
    semester: null,
    week: 1,
    weekDates: [],
    scheduleCourses: [],
    courses: [],
    keyword: '',
    loadingSchedule: false,
    loadingList: false,
    editingId: null,
    detailId: null,
    formColor: 'blue',
    confirmHandler: null,
    importStep: 'form',        // form | loading | preview
    importForm: { studentId: '', password: '' },
    importFetched: null
  };

  /* ============================ 通用工具 ============================ */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function esc(value) {
    if (value == null) { return ''; }
    return String(value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function pad(n) { return n < 10 ? '0' + n : String(n); }

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  /** "08:00" → 分钟数，用于判断当前进行到第几节 */
  function parseHM(str) {
    var parts = String(str || '').split(':');
    return (Number(parts[0]) || 0) * 60 + (Number(parts[1]) || 0);
  }

  function currentPeriodIndex() {
    var times = (state.semester && state.semester.periodTimes) || [];
    var now = new Date();
    var minutes = now.getHours() * 60 + now.getMinutes();
    for (var i = 0; i < times.length; i++) {
      if (minutes >= parseHM(times[i].start) && minutes < parseHM(times[i].end)) { return i + 1; }
    }
    return 0;
  }

  function toast(message, type) {
    var el = document.createElement('div');
    el.className = 'toast' + (type ? ' is-' + type : '');
    el.textContent = message;
    $('#toastWrap').appendChild(el);
    setTimeout(function () {
      el.style.transition = 'opacity .25s';
      el.style.opacity = '0';
      setTimeout(function () { if (el.parentNode) { el.parentNode.removeChild(el); } }, 260);
    }, 2400);
  }

  function openModal(id) { $('#' + id).classList.add('is-open'); }
  function closeModal(id) { $('#' + id).classList.remove('is-open'); }

  function closeAllModals() {
    $$('.modal-backdrop').forEach(function (m) { m.classList.remove('is-open'); });
  }

  var emptyIcon =
    '<svg width="76" height="76" viewBox="0 0 76 76" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<rect x="11" y="15" width="54" height="50" rx="7" stroke="rgba(29,223,255,.55)" stroke-width="2"/>' +
    '<path d="M11 28h54" stroke="rgba(29,223,255,.55)" stroke-width="2"/>' +
    '<path d="M23 9v10M53 9v10" stroke="rgba(29,223,255,.55)" stroke-width="2" stroke-linecap="round"/>' +
    '<rect x="21" y="36" width="15" height="10" rx="2.5" fill="rgba(255,255,255,.07)"/>' +
    '<rect x="40" y="36" width="15" height="10" rx="2.5" fill="rgba(255,255,255,.07)"/>' +
    '<rect x="21" y="50" width="15" height="8" rx="2.5" fill="rgba(255,255,255,.05)"/>' +
    '</svg>';

  function emptyState(icon, title, desc, actions) {
    return '<div class="empty-state">' + icon +
      '<div class="empty-title">' + esc(title) + '</div>' +
      '<div class="empty-desc">' + esc(desc) + '</div>' +
      (actions || '') + '</div>';
  }

  function skeleton(rows) {
    var html = '<div class="skeleton-wrap">';
    for (var i = 0; i < rows; i++) {
      html += '<div class="sk-row"><div class="sk-box w1"></div><div class="sk-box w1"></div>' +
        '<div class="sk-box w1"></div><div class="sk-box w2"></div></div>';
    }
    return html + '</div>';
  }

  /* ============================ 数据加载 ============================ */

  function loadSemester() {
    return Store.getSemester().then(function (s) {
      state.semester = s;
      state.week = s.currentWeek;
      $('#brandSemester').textContent = s.name;
      buildStaticOptions();
    });
  }

  function loadWeekDates() {
    return Store.getWeekDates(state.week).then(function (dates) {
      state.weekDates = dates;
      renderWeekBar();
    });
  }

  function loadSchedule() {
    state.loadingSchedule = true;
    renderSchedule();
    return Store.getSchedule(state.week).then(function (res) {
      state.scheduleCourses = res.courses;
      state.loadingSchedule = false;
      renderSchedule();
    }).catch(function (err) {
      state.loadingSchedule = false;
      renderSchedule();
      toast(err.message || '课表加载失败', 'error');
    });
  }

  function loadCourses() {
    state.loadingList = true;
    renderCourseList();
    return Store.listCourses({ keyword: state.keyword }).then(function (list) {
      state.courses = list;
      state.loadingList = false;
      renderCourseList();
    }).catch(function (err) {
      state.loadingList = false;
      renderCourseList();
      toast(err.message || '课程列表加载失败', 'error');
    });
  }

  function refreshAll() {
    return Promise.all([loadWeekDates(), loadSchedule(), loadCourses()]);
  }

  /* ============================ 渲染：周次条 ============================ */

  function renderWeekBar() {
    if (!state.semester || !state.weekDates.length) { return; }
    var isCurrent = state.week === state.semester.currentWeek;
    var first = state.weekDates[0];
    var last = state.weekDates[6];

    $('#weekTitle').textContent = '第 ' + state.week + ' 周';
    $('#weekNowBadge').hidden = !isCurrent;
    $('#weekRange').textContent = first.label + ' — ' + last.label;
    $('#weekCount').textContent = '本周 ' + state.scheduleCourses.length + ' 门课';

    $('#btnPrevWeek').disabled = state.week <= 1;
    $('#btnNextWeek').disabled = state.week >= state.semester.totalWeeks;
    $('#btnThisWeek').disabled = isCurrent;
  }

  /* ============================ 渲染：课表 ============================ */

  function renderSchedule() {
    var box = $('#scheduleCard');
    if (state.loadingSchedule) { box.innerHTML = skeleton(5); return; }

    if (!state.scheduleCourses.length) {
      box.innerHTML = emptyState(
        emptyIcon,
        '第 ' + state.week + ' 周没有排课',
        '该周没有匹配的课程安排，可切换周次查看，或新增一门课程。',
        '<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">' +
        '<button class="btn" data-action="goto-current-week">回到本周</button>' +
        '<button class="btn btn-primary" data-action="add-course">新增课程</button></div>'
      );
      return;
    }

    var s = state.semester;
    var dates = state.weekDates;
    var today = todayIso();

    /* 今天是否落在当前查看的这一周 */
    var todayCol = 0;
    for (var ti = 0; ti < dates.length; ti++) {
      if (dates[ti].iso === today) { todayCol = ti + 1; break; }
    }
    var nowPeriod = todayCol ? currentPeriodIndex() : 0;

    var html = '<div class="schedule-grid"><div class="grid-corner"><span>时间</span></div>';

    for (var d = 1; d <= 7; d++) {
      var isToday = d === todayCol;
      html += '<div class="grid-head' + (isToday ? ' is-today' : '') + (d === 7 ? ' is-last' : '') + '">' +
        esc(s.weekdayLabels[d - 1]) +
        '<span class="head-date">' + esc(dates[d - 1] ? dates[d - 1].label : '') + '</span>' +
        (isToday ? '<span class="head-today">今天</span>' : '') + '</div>';
    }

    for (var p = 1; p <= s.totalPeriods; p++) {
      var t = s.periodTimes[p - 1];
      html += '<div class="grid-period' + (p === nowPeriod ? ' is-now' : '') + (p % 4 === 0 ? ' is-slot-end' : '') + '">' +
        '<span class="period-time">' + esc(t ? t.start : '') + '</span>' +
        '<span class="period-no">第 ' + p + ' 节</span></div>';
      for (var d2 = 1; d2 <= 7; d2++) {
        html += '<div class="grid-cell' + (d2 === 7 ? ' is-row-end' : '') +
          (d2 >= 6 ? ' col-weekend' : '') +
          (p % 4 === 0 ? ' is-slot-end' : '') +
          (d2 === todayCol ? ' is-today-col' : '') + '"></div>';
      }
    }

    state.scheduleCourses.forEach(function (c, idx) {
      var span = c.endPeriod - c.startPeriod + 1;
      html += '<button type="button" class="course-block c-' + esc(c.color) + '" ' +
        'data-id="' + esc(c.id) + '" data-action="open-course" ' +
        'style="grid-column:' + (c.dayOfWeek + 1) + ';grid-row:' + (c.startPeriod + 1) + ' / span ' + span +
        ';animation-delay:' + Math.min(idx * 45, 540) + 'ms">' +
        '<span class="cb-name">' + esc(c.name) + '</span>' +
        '<span class="cb-meta cb-teacher">' + esc(c.teacher || '教师待定') + '</span>' +
        '<span class="cb-meta">' + esc(c.location || '地点待定') + '</span>' +
        '<span class="cb-weeks">' + esc(c.weekText) +
        (c.timeText ? ' · <span class="cb-time">' + esc(c.timeText) + '</span>' : '') + '</span>' +
        '</button>';
    });

    html += '</div>';
    box.innerHTML = html;
  }

  /* ============================ 渲染：课程列表 ============================ */

  function renderCourseList() {
    var box = $('#courseListCard');
    var count = $('#listCount');

    if (state.loadingList) { box.innerHTML = skeleton(4); count.textContent = '加载中'; return; }

    count.textContent = state.keyword
      ? '匹配 ' + state.courses.length + ' 门'
      : '共 ' + state.courses.length + ' 门课程';

    if (!state.courses.length) {
      var html = state.keyword
        ? emptyState(emptyIcon, '没有找到匹配的课程',
          '没有与「' + state.keyword + '」相关的课程，试试更换关键词。',
          '<button class="btn" data-action="clear-search">清除搜索</button>')
        : emptyState(emptyIcon, '本学期还没有课程',
          '手动新增第一门课程，或从教务系统一键导入。',
          '<div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">' +
          '<button class="btn btn-primary" data-action="add-course">新增课程</button>' +
          '<button class="btn" data-action="import-jwxt">从教务系统导入</button></div>');
      box.innerHTML = html;
      return;
    }

    var items = state.courses.map(function (c, idx) {
      return '<div class="course-item c-' + esc(c.color) + '" data-id="' + esc(c.id) + '" ' +
        'style="animation-delay:' + Math.min(idx * 40, 480) + 'ms">' +
        '<div class="item-when">' +
        '<div class="when-day">' + esc(c.dayText) + '</div>' +
        '<div class="when-period">' + esc(c.startPeriod + '-' + c.endPeriod + ' 节') + '</div>' +
        (c.timeText ? '<div class="when-time">' + esc(c.timeText) + '</div>' : '') +
        '</div>' +
        '<div class="item-main">' +
        '<div class="item-name">' + esc(c.name) +
        '<span class="tag">' + esc(c.category) + '</span>' +
        '<span class="tag">' + c.credit + ' 学分</span></div>' +
        '<div class="item-sub">' + esc(c.teacher) + ' · ' + esc(c.location || '地点待定') +
        ' · ' + esc(c.weekText) + '</div>' +
        '</div>' +
        '<div class="item-actions">' +
        '<button class="btn btn-sm" data-action="open-course" data-id="' + esc(c.id) + '">详情</button>' +
        '<button class="btn btn-sm" data-action="edit-course" data-id="' + esc(c.id) + '">编辑</button>' +
        '<button class="btn btn-sm" data-action="delete-course" data-id="' + esc(c.id) + '">删除</button>' +
        '</div></div>';
    }).join('');

    box.innerHTML = '<div class="course-list">' + items + '</div>';
  }

  /* ============================ 课程详情 ============================ */

  function openDetail(id) {
    Store.getCourse(id).then(function (c) {
      state.detailId = c.id;
      var weeksText = c.weeks.length
        ? c.weeks.join('、') + '（共 ' + c.weeks.length + ' 周）'
        : '未设置';

      $('#detailBody').innerHTML =
        '<div class="detail-hero c-' + esc(c.color) + '">' +
        '<h3>' + esc(c.name) + '</h3>' +
        '<p>' + esc(c.teacher) + ' · ' + esc(c.dayText) + ' ' + esc(c.periodText) +
        (c.timeText ? '（' + esc(c.timeText) + '）' : '') + ' · ' + esc(c.location || '地点待定') + '</p>' +
        '</div>' +
        '<dl class="detail-grid">' +
        '<dt>任课教师</dt><dd>' + esc(c.teacher) + '</dd>' +
        '<dt>上课时间</dt><dd>' + esc(c.dayText) + ' ' + esc(c.periodText) +
        (c.timeText ? '（' + esc(c.timeText) + '）' : '') + '</dd>' +
        '<dt>课程类别</dt><dd>' + esc(c.category) + '</dd>' +
        '<dt>学分</dt><dd>' + c.credit + ' 学分</dd>' +
        '<dt>上课周次</dt><dd>' + esc(c.weekText) + '</dd>' +
        '<dt>具体周次</dt><dd>' + esc(weeksText) + '</dd>' +
        '<dt>备注</dt><dd>' + esc(c.note || '—') + '</dd>' +
        '</dl>';

      openModal('modalDetail');
    }).catch(function (err) {
      toast(err.message || '课程详情加载失败', 'error');
    });
  }

  /* ============================ 新增 / 编辑 ============================ */

  function buildStaticOptions() {
    var s = state.semester;

    var dayOptions = s.weekdayLabels.map(function (label, i) {
      return '<option value="' + (i + 1) + '">' + label + '</option>';
    }).join('');
    $('#fDay').innerHTML = dayOptions;

    var periodOptions = '';
    for (var p = 1; p <= s.totalPeriods; p++) {
      periodOptions += '<option value="' + p + '">第 ' + p + ' 节</option>';
    }
    $('#fStart').innerHTML = periodOptions;
    $('#fEnd').innerHTML = periodOptions;

    $('#fWeekFrom').max = s.totalWeeks;
    $('#fWeekTo').max = s.totalWeeks;
    $('#fWeekTo').value = s.totalWeeks - 2 > 0 ? s.totalWeeks - 2 : s.totalWeeks;

    $('#colorPicker').innerHTML = COLORS.map(function (color) {
      return '<button type="button" class="color-dot c-' + color + '" data-color="' + color + '" ' +
        'aria-label="颜色 ' + color + '"></button>';
    }).join('');
  }

  function setFormColor(color) {
    state.formColor = color;
    $$('#colorPicker .color-dot').forEach(function (dot) {
      dot.classList.toggle('is-active', dot.getAttribute('data-color') === color);
    });
  }

  function openForm(id) {
    $('#formError').textContent = '';
    state.editingId = id || null;
    $('#formTitle').textContent = id ? '编辑课程' : '新增课程';

    if (!id) {
      $('#fName').value = '';
      $('#fTeacher').value = '';
      $('#fLocation').value = '';
      $('#fDay').value = '1';
      $('#fCategory').value = '必修';
      $('#fStart').value = '1';
      $('#fEnd').value = '2';
      $('#fWeekFrom').value = '1';
      $('#fWeekTo').value = String(state.semester.totalWeeks - 2);
      $('#fPattern').value = 'all';
      $('#fCredit').value = '3';
      $('#fNote').value = '';
      setFormColor('blue');
      openModal('modalForm');
      return;
    }

    Store.getCourse(id).then(function (c) {
      $('#fName').value = c.name;
      $('#fTeacher').value = c.teacher;
      $('#fLocation').value = c.location || '';
      $('#fDay').value = String(c.dayOfWeek);
      $('#fCategory').value = c.category;
      $('#fStart').value = String(c.startPeriod);
      $('#fEnd').value = String(c.endPeriod);
      $('#fWeekFrom').value = String(c.weekRule.from);
      $('#fWeekTo').value = String(c.weekRule.to);
      $('#fPattern').value = c.weekRule.pattern;
      $('#fCredit').value = String(c.credit);
      $('#fNote').value = c.note || '';
      setFormColor(c.color);
      openModal('modalForm');
    }).catch(function (err) {
      toast(err.message || '课程信息加载失败', 'error');
    });
  }

  function collectForm() {
    return {
      name: $('#fName').value,
      teacher: $('#fTeacher').value,
      location: $('#fLocation').value,
      dayOfWeek: Number($('#fDay').value),
      category: $('#fCategory').value,
      startPeriod: Number($('#fStart').value),
      endPeriod: Number($('#fEnd').value),
      weekRule: {
        from: Number($('#fWeekFrom').value),
        to: Number($('#fWeekTo').value),
        pattern: $('#fPattern').value
      },
      credit: Number($('#fCredit').value),
      color: state.formColor,
      note: $('#fNote').value
    };
  }

  function submitForm() {
    var payload = collectForm();
    var btn = $('#btnFormSave');
    btn.disabled = true;
    btn.textContent = '保存中…';

    var task = state.editingId
      ? Store.updateCourse(state.editingId, payload)
      : Store.createCourse(payload);

    task.then(function () {
      btn.disabled = false;
      btn.textContent = '保存';
      closeModal('modalForm');
      toast(state.editingId ? '课程已更新' : '课程已添加', 'success');
      return refreshAll();
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = '保存';
      $('#formError').textContent = err.message || '保存失败，请检查填写内容';
      if (err.conflict) { toast('时间冲突，请调整节次或周次', 'error'); }
    });
  }

  /* ============================ 删除 ============================ */

  function confirmDialog(opts) {
    $('#confirmTitle').textContent = opts.title;
    $('#confirmBody').innerHTML = opts.body;
    $('#btnConfirmOk').textContent = opts.okText || '确认';
    state.confirmHandler = opts.onOk;
    openModal('modalConfirm');
  }

  function askDelete(id) {
    Store.getCourse(id).then(function (c) {
      confirmDialog({
        title: '删除课程',
        body: '<p style="margin:0">确定要删除《' + esc(c.name) + '》吗？</p>' +
          '<p style="margin:8px 0 0;color:var(--text-muted);font-size:13px">' +
          esc(c.dayText) + ' ' + esc(c.periodText) + ' · ' + esc(c.teacher) + '</p>',
        okText: '确认删除',
        onOk: function () {
          Store.deleteCourse(id).then(function () {
            closeModal('modalConfirm');
            closeModal('modalDetail');
            toast('课程已删除', 'success');
            return refreshAll();
          }).catch(function (err) {
            toast(err.message || '删除失败', 'error');
          });
        }
      });
    }).catch(function (err) {
      toast(err.message || '课程不存在', 'error');
    });
  }

  /* ============================ 从教务系统导入 ============================ */

  function openImport() {
    state.importStep = 'form';
    state.importFetched = null;
    renderImport();
    openModal('modalImport');
  }

  function renderImport() {
    var body = $('#importBody');
    var foot = $('#importFoot');

    /* ---- 第一步：填写教务系统账号 ---- */
    if (state.importStep === 'form') {
      body.innerHTML =
        '<div class="import-tip">演示模式不会真正连接教务系统，读取到的是模拟数据。' +
        '正式版将按 PLAN.md 的方案自动登录教务系统并抓取课表。</div>' +
        '<div class="field"><label for="impStudent">学号</label>' +
        '<input id="impStudent" type="text" placeholder="请输入学号" autocomplete="off"></div>' +
        '<div class="field"><label for="impPassword">教务系统密码</label>' +
        '<input id="impPassword" type="password" placeholder="请输入密码" autocomplete="off"></div>' +
        '<div class="field full"><span class="field-error" id="importError"></span></div>';

      if (state.importForm.studentId || state.importForm.password) {
        $('#impStudent').value = state.importForm.studentId;
        $('#impPassword').value = state.importForm.password;
      }

      foot.innerHTML =
        '<button class="btn" data-close="modalImport">取消</button>' +
        '<button class="btn btn-primary" id="btnImportFetch">连接并读取课表</button>';
      $('#btnImportFetch').addEventListener('click', startImportFetch);
      return;
    }

    /* ---- 第二步：读取中 ---- */
    if (state.importStep === 'loading') {
      body.innerHTML =
        '<div class="import-loading">' +
        '<div class="imp-spinner"></div>' +
        '<ol class="imp-steps">' +
        '<li class="is-done">连接教务系统</li>' +
        '<li class="is-active">登录并读取课表…</li>' +
        '<li>解析排课数据</li>' +
        '</ol></div>';
      foot.innerHTML = '<button class="btn" data-close="modalImport">取消</button>';
      return;
    }

    /* ---- 第三步：预览与勾选 ---- */
    var fetched = state.importFetched || { courses: [] };
    var items = fetched.courses.map(function (raw, index) {
      return {
        raw: raw,
        index: index,
        conflict: Store.helpers.checkConflict(raw),
        color: COLORS[index % COLORS.length]
      };
    });
    var okCount = items.filter(function (it) { return !it.conflict; }).length;

    var listHtml = items.map(function (it) {
      var c = it.raw;
      var disabled = !!it.conflict;
      var timeText = Store.helpers.periodTimeRange(c.startPeriod, c.endPeriod);
      var meta = Store.helpers.weekdayLabel(c.dayOfWeek) + ' 第 ' + c.startPeriod + '-' + c.endPeriod + ' 节' +
        (timeText ? ' · ' + timeText : '') +
        ' · 第 ' + c.weekRule.from + '-' + c.weekRule.to + ' 周' +
        (c.weekRule.pattern === 'odd' ? '（单周）' : c.weekRule.pattern === 'even' ? '（双周）' : '');

      return '<label class="import-item c-' + it.color + (disabled ? ' is-disabled' : '') + '" ' +
        'style="animation-delay:' + Math.min(it.index * 45, 450) + 'ms">' +
        '<input type="checkbox" data-jwxt-index="' + it.index + '"' +
        (disabled ? ' disabled' : ' checked') + '>' +
        '<span class="import-item-main">' +
        '<span class="import-item-name">' + esc(c.name) +
        '<span class="tag">' + esc(c.category || '必修') + '</span>' +
        (disabled ? '<span class="conflict-badge">与《' + esc(it.conflict.name) + '》冲突</span>' : '') +
        '</span>' +
        '<span class="import-item-sub">' + esc(c.teacher) + ' · ' + esc(c.location || '地点待定') + ' · ' + esc(meta) + '</span>' +
        '</span></label>';
    }).join('');

    body.innerHTML =
      '<p class="import-summary">已从「' + esc(fetched.source || '教务系统') + '」读取到 <b>' + items.length +
      '</b> 门课程，其中 <b>' + okCount + '</b> 门与当前课表无冲突，勾选后即可导入。</p>' +
      '<div class="import-list">' + listHtml + '</div>';

    foot.innerHTML =
      '<button class="btn" data-close="modalImport">取消</button>' +
      '<button class="btn btn-primary" id="btnImportConfirm">导入所选 ' + okCount + ' 门</button>';
    $('#btnImportConfirm').addEventListener('click', confirmImport);
  }

  function startImportFetch() {
    var studentId = ($('#impStudent').value || '').trim();
    var password = $('#impPassword').value || '';
    if (!studentId || !password) {
      $('#importError').textContent = '请填写学号与密码（演示模式下可任意填写）';
      return;
    }
    state.importForm = { studentId: studentId, password: password };
    state.importStep = 'loading';
    renderImport();

    Store.fetchFromJwxt({ studentId: studentId, password: password }).then(function (res) {
      state.importFetched = res;
      state.importStep = 'preview';
      renderImport();
    }).catch(function (err) {
      state.importStep = 'form';
      renderImport();
      $('#importError').textContent = err.message || '读取失败，请重试';
    });
  }

  function confirmImport() {
    var boxes = $$('#importBody .import-item input[type="checkbox"]');
    var selected = boxes.filter(function (b) { return b.checked; }).map(function (b) {
      return state.importFetched.courses[Number(b.getAttribute('data-jwxt-index'))];
    });
    if (!selected.length) { toast('请先勾选要导入的课程', 'error'); return; }

    var btn = $('#btnImportConfirm');
    btn.disabled = true;
    btn.textContent = '导入中…';

    Store.importCourses(selected).then(function (res) {
      closeModal('modalImport');
      toast('成功导入 ' + res.imported.length + ' 门课程' +
        (res.skipped.length ? '，跳过 ' + res.skipped.length + ' 门冲突课程' : ''),
        res.imported.length ? 'success' : 'error');
      return refreshAll();
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = '导入';
      toast(err.message || '导入失败', 'error');
    });
  }

  /* ============================ 事件绑定 ============================ */

  function switchView(view) {
    state.view = view;
    $$('.nav-btn').forEach(function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-view') === view);
    });
    $$('.view').forEach(function (v) {
      v.classList.toggle('is-active', v.id === 'view-' + view);
    });
    moveNavIndicator();
  }

  /* 导航滑动指示器 */
  function moveNavIndicator() {
    var indicator = $('#navIndicator');
    var nav = $('.nav');
    var active = $('.nav-btn.is-active');
    if (!indicator || !nav || !active) { return; }
    var navRect = nav.getBoundingClientRect();
    var btnRect = active.getBoundingClientRect();
    indicator.style.width = btnRect.width + 'px';
    indicator.style.transform = 'translateX(' + (btnRect.left - navRect.left - nav.clientLeft) + 'px)';
  }

  var searchTimer = null;

  function bindEvents() {
    $$('.nav-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { switchView(btn.getAttribute('data-view')); });
    });

    $('#btnPrevWeek').addEventListener('click', function () {
      if (state.week > 1) { state.week--; refreshAll(); }
    });
    $('#btnNextWeek').addEventListener('click', function () {
      if (state.week < state.semester.totalWeeks) { state.week++; refreshAll(); }
    });
    $('#btnThisWeek').addEventListener('click', function () {
      state.week = state.semester.currentWeek;
      refreshAll();
    });

    $('#btnAdd').addEventListener('click', function () { openForm(null); });
    $('#btnImport').addEventListener('click', openImport);

    $('#searchInput').addEventListener('input', function (e) {
      var value = e.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.keyword = value.trim();
        loadCourses();
      }, 240);
    });

    $('#btnReset').addEventListener('click', function () {
      Store.resetDemo().then(function () {
        toast('已恢复演示数据', 'success');
        return refreshAll();
      });
    });

    $('#btnClear').addEventListener('click', function () {
      confirmDialog({
        title: '清空课程',
        body: '<p style="margin:0">将清空本学期全部课程，用于演示「空数据」状态。</p>',
        okText: '确认清空',
        onOk: function () {
          Store.clearCourses().then(function () {
            closeModal('modalConfirm');
            toast('已清空全部课程', 'success');
            return refreshAll();
          });
        }
      });
    });

    /* 事件委托：课表块与列表项 */
    document.addEventListener('click', function (e) {
      var closeEl = e.target.closest('[data-close]');
      if (closeEl) { closeModal(closeEl.getAttribute('data-close')); return; }

      var actionEl = e.target.closest('[data-action]');
      if (actionEl) {
        var action = actionEl.getAttribute('data-action');
        var id = actionEl.getAttribute('data-id');
        if (action === 'open-course') { openDetail(id); return; }
        if (action === 'edit-course') { openForm(id); return; }
        if (action === 'delete-course') { askDelete(id); return; }
        if (action === 'add-course') { openForm(null); return; }
        if (action === 'import-jwxt') { openImport(); return; }
        if (action === 'clear-search') {
          $('#searchInput').value = '';
          state.keyword = '';
          loadCourses();
          return;
        }
        if (action === 'goto-current-week') {
          state.week = state.semester.currentWeek;
          refreshAll();
          return;
        }
      }

      var colorDot = e.target.closest('.color-dot');
      if (colorDot) { setFormColor(colorDot.getAttribute('data-color')); return; }

      var row = e.target.closest('.course-item');
      if (row && !e.target.closest('.item-actions')) {
        openDetail(row.getAttribute('data-id'));
      }
    });

    $$('[data-close]').forEach(function (btn) {
      btn.addEventListener('click', function () { closeModal(btn.getAttribute('data-close')); });
    });

    $$('.modal-backdrop').forEach(function (backdrop) {
      backdrop.addEventListener('click', function (e) {
        if (e.target === backdrop) { closeModal(backdrop.id); }
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeAllModals(); }
    });

    $('#btnDetailEdit').addEventListener('click', function () {
      closeModal('modalDetail');
      openForm(state.detailId);
    });
    $('#btnDetailDelete').addEventListener('click', function () {
      askDelete(state.detailId);
    });

    $('#btnFormSave').addEventListener('click', submitForm);

    $('#btnConfirmOk').addEventListener('click', function () {
      if (typeof state.confirmHandler === 'function') { state.confirmHandler(); }
      else { closeModal('modalConfirm'); }
    });
  }

  /* ============================ 启动 ============================ */

  function init() {
    bindEvents();
    moveNavIndicator();
    window.addEventListener('resize', moveNavIndicator);
    if (window.CourseParticles) { window.CourseParticles.init(); }

    loadSemester().then(refreshAll).catch(function (err) {
      toast(err.message || '初始化失败', 'error');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
