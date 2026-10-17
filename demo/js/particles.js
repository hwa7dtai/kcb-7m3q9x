/**
 * 环境粒子层：参考视频中"飘落光点"的氛围动效。
 * 全屏 canvas，粒子缓慢下落并带正弦摆动，透明度呼吸闪烁。
 * 性能与可访问性处理：
 *   - 粒子上限随屏幕宽度调整（移动端更少）
 *   - requestAnimationFrame + 页面隐藏时暂停
 *   - prefers-reduced-motion 时不启动
 */
(function (global) {
  'use strict';

  var PARTICLE_COLORS = [
    'rgba(29, 223, 255, ',   // 青（主色）
    'rgba(255, 255, 255, ',  // 白
    'rgba(139, 124, 255, '   // 紫
  ];

  function createParticles(canvas) {
    var ctx = canvas.getContext('2d');
    if (!ctx) { return null; }

    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    var particles = [];
    var rafId = null;
    var running = false;
    var width = 0;
    var height = 0;

    function targetCount() {
      var w = global.innerWidth || 1280;
      if (w < 640) { return 22; }
      if (w < 1024) { return 34; }
      return 46;
    }

    function spawn(seedY) {
      var depth = Math.random();          // 0 远 → 1 近
      return {
        x: Math.random() * width,
        y: seedY == null ? Math.random() * height : seedY,
        r: 0.6 + depth * 1.8,             // 近大远小
        vy: 0.12 + depth * 0.42,          // 近快远慢
        sway: 0.3 + Math.random() * 0.7,  // 摆动幅度
        swaySpeed: 0.4 + Math.random() * 0.8,
        phase: Math.random() * Math.PI * 2,
        alpha: 0.12 + depth * 0.3,
        twinkle: 0.6 + Math.random() * 1.4,
        color: PARTICLE_COLORS[Math.random() < 0.62 ? 0 : (Math.random() < 0.6 ? 1 : 2)]
      };
    }

    function resize() {
      width = global.innerWidth || 1280;
      height = global.innerHeight || 800;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function ensureCount() {
      var target = targetCount();
      while (particles.length < target) { particles.push(spawn()); }
      if (particles.length > target) { particles.length = target; }
    }

    var last = 0;

    function frame(ts) {
      if (!running) { return; }
      var dt = last ? Math.min((ts - last) / 16.67, 3) : 1; // 以 60fps 为基准的步长
      last = ts;

      ctx.clearRect(0, 0, width, height);

      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        p.phase += 0.02 * p.swaySpeed * dt;
        p.y += p.vy * dt;
        var x = p.x + Math.sin(p.phase) * p.sway * 12;

        if (p.y - p.r > height) {
          // 从顶部重新进入，保持密度均匀
          p.y = -p.r * 2;
          p.x = Math.random() * width;
        }

        var flicker = 0.72 + 0.28 * Math.sin(ts / 1000 * p.twinkle + p.phase);
        ctx.beginPath();
        ctx.arc(x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color + (p.alpha * flicker).toFixed(3) + ')';
        ctx.fill();
      }

      rafId = global.requestAnimationFrame(frame);
    }

    function start() {
      if (running) { return; }
      running = true;
      last = 0;
      rafId = global.requestAnimationFrame(frame);
    }

    function stop() {
      running = false;
      if (rafId) { global.cancelAnimationFrame(rafId); rafId = null; }
    }

    resize();
    ensureCount();
    start();

    var resizeTimer = null;
    global.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        resize();
        ensureCount();
      }, 150);
    });

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { stop(); } else { start(); }
    });

    return { start: start, stop: stop };
  }

  function init() {
    var canvas = document.getElementById('particleCanvas');
    if (!canvas) { return; }

    // 尊重系统"减弱动态效果"偏好
    var reduce = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) { return; }

    createParticles(canvas);
  }

  global.CourseParticles = { init: init };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
