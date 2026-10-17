/**
 * 氛围粒子层：夜色花树背景上的动态粒子。
 * 四类粒子，全部用离屏 canvas 预渲染成精灵图，主循环只做 drawImage：
 *   - 花瓣：白色花瓣旋转飘落（带翻转 flutter），与雪点混合下落
 *   - 阵风：双正弦叠加的横向风力，作用于花瓣与雪点
 *   - 星星：偏向上半部，按正弦透明度闪烁
 *   - 萤火虫：暖金色，绕锚点 Lissajous 游荡，叠加发光（lighter 混合）
 * 另驱动背景照片的鼠标视差（反向、平滑插值、触屏跳过）。
 *
 * 性能与可访问性：
 *   - 粒子数量按屏幕面积自适应（移动端更少）
 *   - requestAnimationFrame + 页面隐藏时暂停
 *   - prefers-reduced-motion 时不启动
 *   - DPR 上限 2；resize 防抖
 *   - jsdom 等无 canvas 实现的环境静默降级（getContext 返回 null）
 */
(function (global) {
  'use strict';

  var BASE_W = 1440;
  var BASE_H = 900;

  function clamp(v, min, max) { return v < min ? min : (v > max ? max : v); }
  function rand(min, max) { return min + Math.random() * (max - min); }

  /* ---------------- 精灵图预渲染 ---------------- */

  function makeSprite(size, draw) {
    var c = document.createElement('canvas');
    c.width = size;
    c.height = size;
    var cx = c.getContext('2d');
    if (!cx) { return null; }
    draw(cx, size);
    return c;
  }

  // 白色花瓣：椭圆瓣身 + 一点高光，边缘柔化
  function drawPetal(cx, s) {
    var r = s / 2;
    cx.translate(r, r);
    cx.rotate(-Math.PI / 4);
    var g = cx.createLinearGradient(0, -r, 0, r);
    g.addColorStop(0, 'rgba(255, 255, 255, .95)');
    g.addColorStop(0.6, 'rgba(255, 255, 255, .78)');
    g.addColorStop(1, 'rgba(235, 242, 255, .55)');
    cx.fillStyle = g;
    cx.beginPath();
    cx.ellipse(0, 0, r * 0.42, r * 0.82, 0, 0, Math.PI * 2);
    cx.fill();
    // 瓣尖暗色一点，增加立体
    cx.fillStyle = 'rgba(200, 215, 240, .35)';
    cx.beginPath();
    cx.ellipse(0, -r * 0.42, r * 0.16, r * 0.2, 0, 0, Math.PI * 2);
    cx.fill();
  }

  // 雪点：柔边白圆（径向渐变做柔光）
  function drawSnow(cx, s) {
    var r = s / 2;
    var g = cx.createRadialGradient(r, r, 0, r, r, r);
    g.addColorStop(0, 'rgba(255, 255, 255, .95)');
    g.addColorStop(0.45, 'rgba(255, 255, 255, .55)');
    g.addColorStop(1, 'rgba(255, 255, 255, 0)');
    cx.fillStyle = g;
    cx.beginPath();
    cx.arc(r, r, r, 0, Math.PI * 2);
    cx.fill();
  }

  // 星星：中心亮点 + 十字微芒
  function drawStar(cx, s) {
    var r = s / 2;
    var g = cx.createRadialGradient(r, r, 0, r, r, r);
    g.addColorStop(0, 'rgba(255, 255, 255, 1)');
    g.addColorStop(0.3, 'rgba(255, 255, 255, .5)');
    g.addColorStop(1, 'rgba(255, 255, 255, 0)');
    cx.fillStyle = g;
    cx.beginPath();
    cx.arc(r, r, r, 0, Math.PI * 2);
    cx.fill();
    cx.strokeStyle = 'rgba(255, 255, 255, .55)';
    cx.lineWidth = Math.max(0.5, s * 0.045);
    cx.beginPath();
    cx.moveTo(r, r - r * 0.9); cx.lineTo(r, r + r * 0.9);
    cx.moveTo(r - r * 0.9, r); cx.lineTo(r + r * 0.9, r);
    cx.stroke();
  }

  // 萤火虫：暖金色光点 + 外圈光晕
  function drawFirefly(cx, s) {
    var r = s / 2;
    var g = cx.createRadialGradient(r, r, 0, r, r, r);
    g.addColorStop(0, 'rgba(255, 226, 150, 1)');
    g.addColorStop(0.25, 'rgba(255, 198, 92, .8)');
    g.addColorStop(0.6, 'rgba(255, 178, 60, .22)');
    g.addColorStop(1, 'rgba(255, 170, 50, 0)');
    cx.fillStyle = g;
    cx.beginPath();
    cx.arc(r, r, r, 0, Math.PI * 2);
    cx.fill();
  }

  /* ---------------- 主系统 ---------------- */

  function createScene(canvas) {
    var ctx = canvas.getContext('2d');
    if (!ctx) { return null; }

    var SPRITE_PETAL = makeSprite(48, drawPetal);
    var SPRITE_SNOW = makeSprite(24, drawSnow);
    var SPRITE_STAR = makeSprite(16, drawStar);
    var SPRITE_FIREFLY = makeSprite(48, drawFirefly);
    if (!SPRITE_PETAL || !SPRITE_SNOW || !SPRITE_STAR || !SPRITE_FIREFLY) { return null; }

    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    var width = 0;
    var height = 0;
    var petals = [];
    var snowflakes = [];
    var stars = [];
    var fireflies = [];

    /* ---- 数量按屏幕面积自适应 ---- */
    function targetCounts() {
      var k = (width * height) / (BASE_W * BASE_H);
      return {
        petals: Math.round(clamp(26 * k, 8, 40)),
        snow: Math.round(clamp(60 * k, 18, 90)),
        stars: Math.round(clamp(46 * k, 14, 70)),
        fireflies: Math.round(clamp(10 * k, 3, 16))
      };
    }

    /* ---- 各类粒子工厂 ---- */
    function spawnPetal(seedY) {
      return {
        x: rand(0, width),
        y: seedY == null ? rand(-height * 0.2, height) : seedY,
        size: rand(9, 20),                 // 精灵绘制边长（px）
        vy: rand(0.22, 0.62),              // 下落速度 px/帧@60fps
        rot: rand(0, Math.PI * 2),         // 当前旋转角
        vr: rand(-0.014, 0.014),           // 角速度
        swayAmp: rand(14, 34),             // 正弦摆动幅度
        swaySpeed: rand(0.008, 0.02),
        phase: rand(0, Math.PI * 2),
        gustK: rand(0.35, 1),              // 对阵风的敏感度
        alpha: rand(0.5, 0.95)
      };
    }

    function spawnSnow(seedY) {
      return {
        x: rand(0, width),
        y: seedY == null ? rand(-height * 0.2, height) : seedY,
        size: rand(2.5, 7),
        vy: rand(0.3, 1.0),
        swayAmp: rand(6, 20),
        swaySpeed: rand(0.012, 0.03),
        phase: rand(0, Math.PI * 2),
        gustK: rand(0.5, 1.3),
        alpha: rand(0.25, 0.7)
      };
    }

    function spawnStar() {
      // 偏向上半部
      return {
        x: rand(0, width),
        y: rand(0, height * 0.55),
        size: rand(1.6, 4.2),
        twinkleSpeed: rand(0.0011, 0.0026),
        phase: rand(0, Math.PI * 2),
        alpha: rand(0.35, 0.85)
      };
    }

    function spawnFirefly() {
      return {
        ax: rand(width * 0.1, width * 0.9),   // 锚点
        ay: rand(height * 0.2, height * 0.9),
        rx: rand(30, 110),                     // 游荡半径
        ry: rand(20, 80),
        sx: rand(0.00032, 0.0006),             // Lissajous 角速度
        sy: rand(0.00038, 0.0007),
        phase: rand(0, Math.PI * 2),
        pulseSpeed: rand(0.0014, 0.003),
        size: rand(10, 20),
        alpha: rand(0.5, 0.9)
      };
    }

    function syncCounts() {
      var t = targetCounts();
      while (petals.length < t.petals) { petals.push(spawnPetal()); }
      while (snowflakes.length < t.snow) { snowflakes.push(spawnSnow()); }
      while (fireflies.length < t.fireflies) { fireflies.push(spawnFirefly()); }
      petals.length = t.petals;
      snowflakes.length = t.snow;
      fireflies.length = t.fireflies;
    }

    function respawnStars() {
      stars = [];
      var t = targetCounts();
      for (var i = 0; i < t.stars; i++) { stars.push(spawnStar()); }
    }

    /* ---- 鼠标视差（背景反向平滑漂移） ---- */
    var photoLayer = document.querySelector('.bg-photo');
    var coarsePointer = global.matchMedia && global.matchMedia('(pointer: coarse)').matches;
    var parallax = { tx: 0, ty: 0, x: 0, y: 0 };   // 目标 / 当前
    var PARALLAX_RANGE = 14; // px

    if (photoLayer && !coarsePointer) {
      global.addEventListener('pointermove', function (e) {
        var nx = (e.clientX / (global.innerWidth || 1)) * 2 - 1;   // -1 ~ 1
        var ny = (e.clientY / (global.innerHeight || 1)) * 2 - 1;
        parallax.tx = -nx * PARALLAX_RANGE;   // 反向
        parallax.ty = -ny * PARALLAX_RANGE;
      }, { passive: true });

      global.addEventListener('pointerleave', function () {
        parallax.tx = 0;
        parallax.ty = 0;
      });
    }

    function applyParallax(dt) {
      if (!photoLayer) { return; }
      var k = clamp(0.075 * dt, 0, 1);        // 帧率无关的插值系数
      parallax.x += (parallax.tx - parallax.x) * k;
      parallax.y += (parallax.ty - parallax.y) * k;
      photoLayer.style.transform = 'translate3d(' + parallax.x.toFixed(2) + 'px, ' + parallax.y.toFixed(2) + 'px, 0)';
    }

    /* ---- 主循环 ---- */
    var running = false;
    var rafId = null;
    var last = 0;

    function frame(ts) {
      if (!running) { return; }
      var dt = last ? clamp((ts - last) / 16.67, 0.2, 3) : 1;   // 以 60fps 为基准
      last = ts;

      ctx.clearRect(0, 0, width, height);

      // 双正弦叠加阵风：全局共享的横向风力
      var gust = Math.sin(ts * 0.0006) * 0.9 + Math.sin(ts * 0.0017 + 1.7) * 0.45;

      var i, p, x, y, a;

      // 星星：固定位置，正弦闪烁（最底层先画）
      for (i = 0; i < stars.length; i++) {
        p = stars[i];
        a = p.alpha * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(ts * p.twinkleSpeed + p.phase)));
        ctx.globalAlpha = a;
        ctx.drawImage(SPRITE_STAR, p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
      }

      // 花瓣：旋转 + 翻转 flutter + 阵风
      for (i = 0; i < petals.length; i++) {
        p = petals[i];
        p.phase += p.swaySpeed * dt;
        p.rot += p.vr * dt;
        p.y += p.vy * dt;
        if (p.y - p.size > height) {          // 从顶部重新进入
          p.y = -p.size;
          p.x = rand(0, width);
        }
        x = p.x + Math.sin(p.phase) * p.swayAmp + gust * 26 * p.gustK * dt;
        if (x < -p.size) { x += width + p.size * 2; }
        if (x > width + p.size) { x -= width + p.size * 2; }

        var flutter = 0.45 + 0.55 * Math.abs(Math.cos(p.rot * 2.4));  // 边缘朝上的翻转感
        ctx.save();
        ctx.translate(x, p.y);
        ctx.rotate(p.rot);
        ctx.scale(flutter, 1);
        ctx.globalAlpha = p.alpha;
        ctx.drawImage(SPRITE_PETAL, -p.size / 2, -p.size / 2, p.size, p.size);
        ctx.restore();
      }

      // 雪点：混合下落
      for (i = 0; i < snowflakes.length; i++) {
        p = snowflakes[i];
        p.phase += p.swaySpeed * dt;
        p.y += p.vy * dt;
        if (p.y - p.size > height) {
          p.y = -p.size;
          p.x = rand(0, width);
        }
        x = p.x + Math.sin(p.phase) * p.swayAmp + gust * 16 * p.gustK * dt;
        if (x < -p.size) { x += width + p.size * 2; }
        if (x > width + p.size) { x -= width + p.size * 2; }
        ctx.globalAlpha = p.alpha;
        ctx.drawImage(SPRITE_SNOW, x - p.size / 2, p.y - p.size / 2, p.size, p.size);
      }

      // 萤火虫：绕锚点 Lissajous 游荡 + 发光
      ctx.globalCompositeOperation = 'lighter';
      for (i = 0; i < fireflies.length; i++) {
        p = fireflies[i];
        x = p.ax + Math.sin(ts * p.sx + p.phase) * p.rx
              + Math.sin(ts * p.sx * 2.7 + p.phase * 1.3) * p.rx * 0.35;
        y = p.ay + Math.cos(ts * p.sy + p.phase * 0.8) * p.ry
              + Math.sin(ts * p.sy * 2.3 + p.phase * 1.9) * p.ry * 0.35;
        a = p.alpha * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(ts * p.pulseSpeed + p.phase)));
        ctx.globalAlpha = a;
        ctx.drawImage(SPRITE_FIREFLY, x - p.size / 2, y - p.size / 2, p.size, p.size);
      }
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;

      applyParallax(dt);

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

    function resize() {
      width = global.innerWidth || 1280;
      height = global.innerHeight || 800;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = width + 'px';
      canvas.style.height = height + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    syncCounts();
    respawnStars();
    start();

    var resizeTimer = null;
    global.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        resize();
        syncCounts();
        respawnStars();
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

    createScene(canvas);
  }

  global.CourseParticles = { init: init };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
