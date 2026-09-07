/* ════════════════════════════════════════
   CCTV Detective AI – dashboard.js
   Real-time via SSE. Gauge = Canvas 2D.
   PPE focus: Person / Helmet / Boots only
   ════════════════════════════════════════ */
'use strict';

const $  = id  => document.getElementById(id);
const qs = sel => document.querySelector(sel);

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', ms = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  $('toastWrap').appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// ── Clock ─────────────────────────────────────────────────────────────────────
setInterval(() => {
  const now = new Date();
  const s = `${now.toLocaleDateString('th-TH')} ${now.toLocaleTimeString('th-TH',{hour12:false})}`;
  if ($('sysClock')) $('sysClock').textContent = s;
}, 1000);

// ── Sidebar ───────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    item.classList.add('active');
    $(`page-${item.dataset.page}`)?.classList.add('active');
  });
});
$('bellBtn')?.addEventListener('click', () => {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  qs('[data-page="alerts"]')?.classList.add('active');
  $('page-alerts')?.classList.add('active');
  $('notifDot')?.classList.remove('show');
});

// ════════════════════════════════════════
//  GAUGE — Canvas 2D  (clean half-circle)
//  canvas is ONLY the arc+needle zone.
//  Text (% + label) lives in separate DOM
//  elements BELOW the canvas, never overlap.
// ════════════════════════════════════════
function drawGauge(canvas, pct) {
  if (!canvas) return;

  // Use the canvas's actual CSS pixel size via devicePixelRatio
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth  || 260;
  const cssH = canvas.clientHeight || 140;

  // Only resize backing store when needed
  if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
    canvas.width  = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
  }

  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.scale(dpr, dpr);

  // Centre-bottom with 10 px bottom padding so needle tip is visible
  const cx  = cssW / 2;
  const cy  = cssH - 10;
  const r   = Math.min(cx - 14, cy - 4);
  const lw  = 18;

  // ── Thin background track ──────────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, 0);
  ctx.strokeStyle = 'rgba(255,255,255,0.07)';
  ctx.lineWidth   = lw;
  ctx.lineCap     = 'butt';
  ctx.stroke();

  // ── Coloured zone arcs (red / amber / green) ───────────────────────────────
  const zones = [
    { f: 0,    t: 0.33, c: '#f43f5e' },
    { f: 0.33, t: 0.66, c: '#f59e0b' },
    { f: 0.66, t: 1.00, c: '#10b981' },
  ];
  zones.forEach(z => {
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI + z.f * Math.PI, Math.PI + z.t * Math.PI);
    ctx.strokeStyle = z.c;
    ctx.lineWidth   = lw;
    ctx.lineCap     = 'butt';
    ctx.globalAlpha = 0.30;
    ctx.stroke();
    ctx.globalAlpha = 1;
  });

  // ── Active filled arc (brighter, follows pct) ─────────────────────────────
  if (pct > 0) {
    const activeColor = pct >= 0.66 ? '#10b981' : pct >= 0.33 ? '#f59e0b' : '#f43f5e';
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, Math.PI + pct * Math.PI);
    ctx.strokeStyle = activeColor;
    ctx.lineWidth   = lw;
    ctx.lineCap     = 'round';
    ctx.globalAlpha = 1;
    ctx.stroke();

    // subtle outer glow
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI, Math.PI + pct * Math.PI);
    ctx.strokeStyle = activeColor;
    ctx.lineWidth   = lw + 10;
    ctx.lineCap     = 'round';
    ctx.globalAlpha = 0.08;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  // ── Tick marks (9 marks, every ~20°) ─────────────────────────────────────
  for (let i = 0; i <= 8; i++) {
    const a     = Math.PI + (i / 8) * Math.PI;
    const inner = r - lw / 2 - 2;
    const outer = r - lw / 2 - (i % 4 === 0 ? 10 : 6);
    ctx.beginPath();
    ctx.moveTo(cx + inner * Math.cos(a), cy + inner * Math.sin(a));
    ctx.lineTo(cx + outer * Math.cos(a), cy + outer * Math.sin(a));
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth   = i % 4 === 0 ? 2 : 1;
    ctx.lineCap     = 'round';
    ctx.stroke();
  }

  // ── Needle ────────────────────────────────────────────────────────────────
  const angle = Math.PI + pct * Math.PI;
  const nLen  = r - lw / 2 - 16;          // shorter than arc inner edge
  const nTip  = { x: cx + nLen * Math.cos(angle), y: cy + nLen * Math.sin(angle) };

  // needle shadow
  ctx.save();
  ctx.shadowColor  = 'rgba(0,0,0,0.6)';
  ctx.shadowBlur   = 6;
  ctx.shadowOffsetY = 2;

  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(nTip.x, nTip.y);
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth   = 3;
  ctx.lineCap     = 'round';
  ctx.stroke();
  ctx.restore();

  // center hub
  ctx.beginPath();
  ctx.arc(cx, cy, 7, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();

  ctx.beginPath();
  ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
  ctx.fillStyle = '#0a0e1a';
  ctx.fill();

  ctx.restore();
}

// ── Smooth animation ──────────────────────────────────────────────────────────
const gaugeState = {};

function animateGauge(key, canvasId, valueId, labelId, targetPct) {
  if (!gaugeState[key]) gaugeState[key] = 0;
  const cur   = gaugeState[key];
  const delta = (targetPct - cur) * 0.12;
  const next  = Math.abs(delta) < 0.0005 ? targetPct : cur + delta;
  gaugeState[key] = next;

  drawGauge($(canvasId), next);

  // Update text below canvas
  const pctInt = Math.round(targetPct * 100);
  const valEl  = $(valueId);
  const lblEl  = $(labelId);
  if (valEl) valEl.textContent = `${pctInt}%`;
  if (lblEl) {
    if      (pctInt >= 90) { lblEl.textContent = 'EXCELLENT'; lblEl.dataset.level = 'green';  }
    else if (pctInt >= 70) { lblEl.textContent = 'GOOD';      lblEl.dataset.level = 'yellow'; }
    else if (pctInt >= 50) { lblEl.textContent = 'FAIR';      lblEl.dataset.level = 'yellow'; }
    else                   { lblEl.textContent = 'WARNING';   lblEl.dataset.level = 'red';    }
  }

  if (Math.abs(delta) >= 0.0005) {
    requestAnimationFrame(() => animateGauge(key, canvasId, valueId, labelId, targetPct));
  }
}

// Initial draw (pct = 0 = needle at far left)
['gaugeChart','gaugeChart2'].forEach(id => {
  const c = $(id);
  if (c) {
    // Let the browser lay out first so clientWidth is correct
    requestAnimationFrame(() => drawGauge(c, 0));
  }
});

// Redraw on resize (responsive)
window.addEventListener('resize', () => {
  Object.keys(gaugeState).forEach(k => {
    const id = k === 'g1' ? 'gaugeChart' : 'gaugeChart2';
    drawGauge($(id), gaugeState[k] ?? 0);
  });
});

// ════════════════════════════════════════
//  LINE CHARTS  (rolling 60 pts)
// ════════════════════════════════════════
Chart.defaults.color       = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

const MAX_PTS = 60;

function buildLine(id) {
  const el = $(id);
  if (!el) return null;
  return new Chart(el, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label:'Violations', data:[], borderColor:'#f43f5e',
          backgroundColor:'rgba(244,63,94,.12)', borderWidth:2,
          tension:.4, fill:true, pointRadius:0, pointHoverRadius:4 },
        { label:'Safe PPE',   data:[], borderColor:'#10b981',
          backgroundColor:'rgba(16,185,129,.10)', borderWidth:2,
          tension:.4, fill:true, pointRadius:0, pointHoverRadius:4 },
        { label:'Persons',    data:[], borderColor:'#06b6d4',
          backgroundColor:'transparent', borderWidth:1.5,
          tension:.4, borderDash:[5,3], pointRadius:0, pointHoverRadius:4 },
      ],
    },
    options: {
      responsive:true, animation:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{
        legend:{ labels:{ color:'#94a3b8', boxWidth:10, padding:14,
          font:{ size:11, family:'Inter,system-ui,sans-serif' } } },
        tooltip:{ backgroundColor:'rgba(17,24,39,0.95)', borderColor:'rgba(255,255,255,.1)',
          borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8', padding:10 },
      },
      scales:{
        x:{ grid:{color:'rgba(255,255,255,.04)'}, border:{display:false},
            ticks:{color:'#64748b', maxTicksLimit:6, maxRotation:0, font:{size:10}} },
        y:{ grid:{color:'rgba(255,255,255,.04)'}, border:{display:false},
            ticks:{color:'#64748b', font:{size:10}}, beginAtZero:true },
      },
    },
  });
}

function pushLine(chart, label, v, sp, p) {
  if (!chart) return;
  const d = chart.data;
  d.labels.push(label);
  d.datasets[0].data.push(v);
  d.datasets[1].data.push(sp);
  d.datasets[2].data.push(p);
  if (d.labels.length > MAX_PTS) {
    d.labels.shift();
    d.datasets.forEach(ds => ds.data.shift());
  }
  chart.update('none');
}

const lineDaily    = buildLine('dailyChart');
const lineAnalytic = buildLine('analyticLineChart');

// ════════════════════════════════════════
//  BAR CHART  (Analytics)
// ════════════════════════════════════════
const BAR_KEYS   = ['Person','Helmet','Boots','no_helmet','no_boots'];
const BAR_LABELS = ['บุคคล','Helmet ✅','Boots ✅','No Helmet ❌','No Boots ❌'];
const BAR_COLORS = ['#06b6d4','#10b981','#10b981','#f43f5e','#f43f5e'];

const barChart = $('barChart') ? new Chart($('barChart'), {
  type: 'bar',
  data: {
    labels: BAR_LABELS,
    datasets:[{ data: new Array(5).fill(0), backgroundColor: BAR_COLORS,
                borderRadius:6, barThickness:20 }],
  },
  options:{
    indexAxis:'y', responsive:true, animation:{ duration:300 },
    plugins:{ legend:{display:false},
      tooltip:{ backgroundColor:'rgba(17,24,39,0.95)', borderColor:'rgba(255,255,255,.1)',
        borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8', padding:10 } },
    scales:{
      x:{ grid:{color:'rgba(255,255,255,.04)'}, border:{display:false},
          ticks:{color:'#64748b', font:{size:10}}, beginAtZero:true },
      y:{ grid:{display:false}, border:{display:false},
          ticks:{color:'#e2e8f0', font:{size:12, weight:'600'}} },
    },
  },
  plugins:[{
    id:'barVals',
    afterDatasetsDraw(chart) {
      const {ctx} = chart;
      chart.data.datasets.forEach((ds,di) => {
        chart.getDatasetMeta(di).data.forEach((bar,i) => {
          if (!ds.data[i]) return;
          ctx.fillStyle = 'rgba(255,255,255,0.7)';
          ctx.font = '600 11px Inter,system-ui,sans-serif';
          ctx.textAlign = 'left';
          ctx.fillText(ds.data[i], bar.x + 6, bar.y + 4);
        });
      });
    },
  }],
}) : null;

function updateBar(c) {
  if (!barChart) return;
  barChart.data.datasets[0].data = BAR_KEYS.map(k => c[k] ?? 0);
  barChart.update('none');
}

// ════════════════════════════════════════
//  TIMELINE  (Alerts page)
// ════════════════════════════════════════
const MAX_TL = 120;
const tlChart = $('timelineChart') ? new Chart($('timelineChart'), {
  type:'bar',
  data:{
    labels:[],
    datasets:[
      {label:'Violations', data:[], backgroundColor:'rgba(244,63,94,0.7)', stack:'a', barThickness:5, borderRadius:2},
      {label:'Safe PPE',   data:[], backgroundColor:'rgba(16,185,129,0.7)', stack:'b', barThickness:5, borderRadius:2},
      {label:'Persons',    data:[], backgroundColor:'rgba(6,182,212,0.5)',  stack:'c', barThickness:5, borderRadius:2},
    ],
  },
  options:{
    responsive:true, animation:false,
    plugins:{
      legend:{ labels:{ color:'#94a3b8', boxWidth:10, font:{size:11} } },
      tooltip:{ backgroundColor:'rgba(17,24,39,0.95)', borderColor:'rgba(255,255,255,.1)',
        borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8', padding:10 },
    },
    scales:{
      x:{ display:false, grid:{display:false} },
      y:{ display:false, beginAtZero:true },
    },
  },
}) : null;

function pushTimeline(ts, v, sp, p) {
  if (!tlChart) return;
  const label = new Date(ts).toLocaleTimeString('th-TH',{hour12:false});
  tlChart.data.labels.push(label);
  tlChart.data.datasets[0].data.push(v);
  tlChart.data.datasets[1].data.push(sp);
  tlChart.data.datasets[2].data.push(p);
  if (tlChart.data.labels.length > MAX_TL) {
    tlChart.data.labels.shift();
    tlChart.data.datasets.forEach(d => d.data.shift());
  }
  tlChart.update('none');
}

// ════════════════════════════════════════
//  PPE tick helper
// ════════════════════════════════════════
function setPPE(id, state) {   // state: 'ok' | 'fail' | 'none'
  const el = $(id);
  if (!el) return;
  el.className = `ppe-check ${state}`;
  el.textContent = state === 'ok' ? '✔' : state === 'fail' ? '✖' : '—';
}

// ════════════════════════════════════════
//  SESSION TOTALS
// ════════════════════════════════════════
let totalFrames = 0, totalViol = 0;

// ════════════════════════════════════════
//  applyStats  – main SSE handler
// ════════════════════════════════════════
function applyStats(s) {
  const c   = s.counts     || {};
  const ppe = s.ppe_status || {};
  const v   = s.violations ?? 0;
  const sp  = s.safe_ppe   ?? 0;
  const p   = s.persons    ?? 0;
  const ts  = s.timestamp  || new Date().toISOString();
  const tLabel = new Date(ts).toLocaleTimeString('th-TH',{hour12:false});

  totalFrames++;  totalViol += v;

  // ── Gauge ──────────────────────────────────────────────────────────────────
  const total   = sp + v;
  const safePct = total > 0 ? sp / total : 1;
  animateGauge('g1', 'gaugeChart',  'gaugeValue',  'gaugeLabel',  safePct);
  animateGauge('g2', 'gaugeChart2', 'gaugeValue2', 'gaugeLabel2', safePct);

  // ── Dashboard count strip ─────────────────────────────────────────────────
  set('dashPersons',    p);
  set('dashSafe',       sp);
  set('dashViolations', v);
  set('dashBoots',      c['Boots'] ?? 0);

  // ── PPE panel (Dashboard) — คน / Helmet / Boots ───────────────────────────
  set('cntPerson',  p);
  set('cntHelmet',  c['Helmet'] ?? 0);
  set('cntBoots',   c['Boots']  ?? 0);

  const hPpe = ppe.helmet  || {};
  const bPpe = ppe.boots   || {};
  const ovPpe = ppe.overall || {};
  setPPE('ppeCheck',  ovPpe.fail ? 'fail' : ovPpe.ok ? 'ok' : 'none');
  setPPE('ppeHelmet', hPpe.fail  ? 'fail' : hPpe.ok  ? 'ok' : 'none');
  setPPE('ppeBoots',  bPpe.fail  ? 'fail' : bPpe.ok  ? 'ok' : 'none');

  // ── Analytics counts (คน / Helmet / Boots) ────────────────────────────────
  set('countPerson',  p);
  set('countHelmet',  c['Helmet'] ?? 0);
  set('countBoots',   c['Boots']  ?? 0);

  // ── Line charts ───────────────────────────────────────────────────────────
  pushLine(lineDaily,    tLabel, v, sp, p);
  pushLine(lineAnalytic, tLabel, v, sp, p);

  // ── Bar chart ─────────────────────────────────────────────────────────────
  updateBar(c);

  // ── Timeline ─────────────────────────────────────────────────────────────
  pushTimeline(ts, v, sp, p);

  // ── Barrier gate (ไม้กั้น) ────────────────────────────────────────────────
  if (s.gate) applyGate(s.gate);

  // ── Settings stats ────────────────────────────────────────────────────────
  const camSt = s.camera_status || {};
  set('sysCams',      Object.values(camSt).filter(x => x === 'running').length);
  set('sysFrames',    totalFrames);
  set('sysTotalViol', totalViol);
}

// ════════════════════════════════════════
//  BARRIER GATE  (ไม้กั้น) — สถานะเปิด/ปิด + การเชื่อมต่อบอร์ด
// ════════════════════════════════════════
function boardLabel(s) {
  return s === 'online' ? '🟢 เชื่อมต่อแล้ว'
       : s === 'offline' ? '🔴 ไม่ได้เชื่อมต่อ'
       : '⚙ โหมดจำลอง (ยังไม่ตั้ง ESP32_URL)';
}

let _lastGateStatus = null;
function applyGate(g) {
  const box = $('gateBox');
  if (!box) return;

  box.dataset.state = g.status === 'open' ? 'open' : 'closed';
  set('gateStatusText', g.status === 'open' ? 'เปิด' : 'ปิด');
  set('gateBoard', '● บอร์ด: ' + boardLabel(g.board));

  if (_lastGateStatus !== null && g.status !== _lastGateStatus) {
    addAlert(new Date().toLocaleTimeString('th-TH', { hour12: false }),
             `🚧 ไม้กั้น${g.status === 'open' ? 'เปิด' : 'ปิด'}`, true);
  }
  _lastGateStatus = g.status;

  // Settings mirror
  set('setGateStatus', g.status === 'open' ? '🟢 เปิด' : '🔴 ปิด');
  set('setGateBoard',  boardLabel(g.board));
  if (g.changed_at) {
    set('setGateChanged',
        new Date(g.changed_at).toLocaleTimeString('th-TH', { hour12: false }));
  }
}

async function gatePost(path) {
  try {
    const r = await fetch(path, { method: 'POST' });
    const d = await r.json();
    if (d.gate) applyGate(d.gate);
    return d;
  } catch (e) { toast(`Gate error: ${e}`, 'err'); }
}

$('btnGateOpen') ?.addEventListener('click', () => gatePost('/api/gate/open'));
$('btnGateClose')?.addEventListener('click', () => gatePost('/api/gate/close'));

async function initGate() {
  try {
    const r = await fetch('/api/gate/status');
    const d = await r.json();
    if (d.gate) applyGate(d.gate);
  } catch {}
}

function set(id, val) {
  const el = $(id);
  if (el) el.textContent = val;
}

// ════════════════════════════════════════
//  SSE #1 – STATS
// ════════════════════════════════════════
function connectStatsSSE() {
  const src = new EventSource('/api/stats/stream');

  src.onopen = () => {
    const b = $('sseBadge');
    if (b) { b.textContent = '🟢 LIVE'; b.className = 'sse-badge live'; }
    set('sseStatus', '🟢 Real-time');
  };

  src.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.ping) return;
    applyStats(data);
  };

  src.onerror = () => {
    const b = $('sseBadge');
    if (b) { b.textContent = '🔴 Offline'; b.className = 'sse-badge dead'; }
    set('sseStatus', '🔴 กำลังเชื่อมต่อใหม่…');
    src.close();
    setTimeout(connectStatsSSE, 3000);
  };
}

// ════════════════════════════════════════
//  SSE #2 – ALERTS
// ════════════════════════════════════════
let _lastAlert = { msg: '', ts: 0 };
function connectAlertsSSE() {
  const src = new EventSource('/api/alerts/stream');
  src.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.ping) return;
    // guard against SSE replay / multi-camera repeats: skip an identical
    // message seen within the last 8s
    const now = Date.now();
    if (d.msg === _lastAlert.msg && now - _lastAlert.ts < 8000) return;
    _lastAlert = { msg: d.msg, ts: now };
    addAlert(d.time, d.msg);
    toast(d.msg, d.level === 'danger' ? 'err' : 'info', 4500);
  };
  src.onerror = () => { src.close(); setTimeout(connectAlertsSSE, 3000); };
}

function addAlert(time, msg, silent = false) {
  const list = $('alertList');
  if (!list) return;
  const item = document.createElement('div');
  item.className = 'alert-list-item';
  item.innerHTML =
    `<span class="alert-dot"></span>` +
    `<span class="alert-time">${time ?? ''} </span>` +
    `<span>${msg}</span>`;
  list.prepend(item);
  while (list.children.length > 50) list.lastChild.remove();
  if (!silent) $('notifDot')?.classList.add('show');
}

function eventText(ev) {
  if (ev.kind === 'gate') return `🚧 ไม้กั้น${ev.status === 'open' ? 'เปิด' : 'ปิด'}`;
  return ev.msg || '(event)';
}

// Populate the alert list from the persisted log on page load
async function loadAlertHistory() {
  try {
    const r = await fetch('/api/events?n=30');
    const d = await r.json();
    (d.events || []).forEach(ev => {
      const t = new Date(ev.ts).toLocaleTimeString('th-TH', { hour12: false });
      addAlert(t, eventText(ev), true);
    });
  } catch {}
}

$('btnClearAlerts')?.addEventListener('click', () => {
  const l = $('alertList');
  if (l) l.innerHTML = '';
  $('notifDot')?.classList.remove('show');
});

// ════════════════════════════════════════
//  MODEL
// ════════════════════════════════════════
async function checkModel() {
  try {
    const r = await fetch('/api/model/status');
    const d = await r.json();
    set('sysModel', d.loaded ? (d.path || 'best.pt').split(/[/\\]/).pop() : '⏳ กำลังโหลด…');
    if (d.conf != null) {
      const rng = $('confRange');
      if (rng) rng.value = d.conf;
      set('confVal', parseFloat(d.conf).toFixed(2));
    }
  } catch {}
}
// Poll a few times right after load so the auto-loading model shows up
let _modelPolls = 0;
const _modelPoll = setInterval(() => {
  checkModel();
  if (++_modelPolls >= 10) clearInterval(_modelPoll);
}, 3000);

$('btnLoadModel')?.addEventListener('click', async () => {
  const path = ($('modelPath')?.value ?? '').trim();
  const msgEl = $('settingsMsg');
  if (msgEl) { msgEl.textContent = 'กำลังโหลด…'; msgEl.style.color = '#a0b0e0'; }
  try {
    const r = await fetch('/api/model/load', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ path }),
    });
    const d = await r.json();
    if (d.ok) {
      if (msgEl) { msgEl.textContent = '✔ โหลดสำเร็จ'; msgEl.style.color = '#22c55e'; }
      checkModel();
      toast('โหลดโมเดลสำเร็จ', 'ok');
    } else {
      if (msgEl) { msgEl.textContent = `✖ ${d.message}`; msgEl.style.color = '#ef4444'; }
      toast(d.message, 'err');
    }
  } catch(e) {
    if (msgEl) { msgEl.textContent = `✖ ${e}`; msgEl.style.color = '#ef4444'; }
  }
});

$('confRange')?.addEventListener('input', function() {
  set('confVal', parseFloat(this.value).toFixed(2));
});
$('confRange')?.addEventListener('change', async function() {
  const conf = parseFloat(this.value);
  try {
    const r = await fetch('/api/model/conf', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conf }),
    });
    const d = await r.json();
    if (d.ok) toast(`ตั้ง Confidence = ${d.conf.toFixed(2)}`, 'ok');
    else toast(d.message || 'ตั้งค่าไม่สำเร็จ', 'err');
  } catch (e) { toast(`Error: ${e}`, 'err'); }
});

// ════════════════════════════════════════
//  CAMERA  (webcam / RTSP / HTTP source)
// ════════════════════════════════════════
const openSlots = new Set();               // cam ids currently streaming

async function startCam(camId, source, label = '') {
  const r = await fetch('/api/camera/start', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ cam_id: camId, source, label }),
  });
  return r.json();
}
async function stopCam(camId) {
  await fetch('/api/camera/stop', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ cam_id: camId }),
  });
}
async function testCam(source) {
  const r = await fetch('/api/camera/test', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ source }),
  });
  return r.json();
}

function slotIdx(camId) { return parseInt(String(camId).replace('cam',''), 10) || 0; }

function hookFeed(camId, label = '') {
  const idx = slotIdx(camId);
  const url = `/video_feed/${camId}`;
  if (idx === 0) {
    if ($('feed-cam1'))  $('feed-cam1').src  = url;
    if ($('alert-feed')) $('alert-feed').src = url;
    if (label && $('camLabel1')) $('camLabel1').textContent = `📍 Camera 1 : ${label}`;
  }
  if (idx === 1) {
    if ($('feed-cam2')) $('feed-cam2').src = url;
    if (label && $('camLabel2')) $('camLabel2').textContent = `📍 Camera 2 : ${label}`;
  }
  openSlots.add(camId);
}
function unhookFeed(camId) {
  const idx = slotIdx(camId);
  const ph  = '/static/img/placeholder.svg';
  if (idx === 0) {
    if ($('feed-cam1'))  $('feed-cam1').src  = ph;
    if ($('alert-feed')) $('alert-feed').src = ph;
  }
  if (idx === 1 && $('feed-cam2')) $('feed-cam2').src = ph;
  openSlots.delete(camId);
}

function showMsg(id, text, kind = 'info') {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.style.color = kind === 'ok' ? '#22c55e' : kind === 'err' ? '#ef4444' : '#a0b0e0';
}

async function connectSource(camId, source, label, msgId) {
  showMsg(msgId, '⏳ กำลังเชื่อมต่อ…');
  try {
    const d = await startCam(camId, source, label);
    if (d.ok) {
      hookFeed(camId, label);
      showMsg(msgId, `✔ ส่งเข้า ${camId} แล้ว — กำลังดึงภาพ`, 'ok');
      toast(`เปิด ${camId} สำเร็จ`, 'ok');
    } else {
      showMsg(msgId, `✖ ${d.message || 'เปิดไม่สำเร็จ'}`, 'err');
    }
  } catch (e) {
    showMsg(msgId, `✖ Backend ไม่ตอบสนอง: ${e}`, 'err');
  }
}

async function probeAndReport(source, msgId) {
  if (!source) { showMsg(msgId, 'ใส่ URL ก่อน', 'err'); return; }
  showMsg(msgId, '⏳ กำลังทดสอบ…');
  try {
    const d = await testCam(source);
    showMsg(msgId, (d.ok ? '✔ ' : '✖ ') + d.message, d.ok ? 'ok' : 'err');
  } catch (e) {
    showMsg(msgId, `✖ ${e}`, 'err');
  }
}

// ── Remote Camera (Settings) — remembers the friend's URL ────────────────────
const RC_KEY = 'cctv.remoteCam';
(function restoreRemoteCam() {
  try {
    const s = JSON.parse(localStorage.getItem(RC_KEY) || '{}');
    if (s.url   && $('remoteCamUrl'))   $('remoteCamUrl').value   = s.url;
    if (s.label && $('remoteCamLabel')) $('remoteCamLabel').value = s.label;
    if (s.slot  && $('remoteCamSlot'))  $('remoteCamSlot').value  = s.slot;
  } catch {}
})();
function saveRemoteCam() {
  try {
    localStorage.setItem(RC_KEY, JSON.stringify({
      url:   $('remoteCamUrl')?.value.trim()   || '',
      label: $('remoteCamLabel')?.value.trim() || '',
      slot:  $('remoteCamSlot')?.value         || 'cam0',
    }));
  } catch {}
}

$('btnRemoteCamTest')?.addEventListener('click', () => {
  saveRemoteCam();
  probeAndReport(($('remoteCamUrl')?.value ?? '').trim(), 'remoteCamMsg');
});

$('btnRemoteCamConnect')?.addEventListener('click', () => {
  saveRemoteCam();
  const url   = ($('remoteCamUrl')?.value ?? '').trim();
  const label = ($('remoteCamLabel')?.value ?? '').trim();
  const camId = $('remoteCamSlot')?.value || 'cam0';
  if (!url) { showMsg('remoteCamMsg', 'ใส่ URL ก่อน', 'err'); return; }
  connectSource(camId, url, label, 'remoteCamMsg');
});

$('btnRemoteCamStop')?.addEventListener('click', async () => {
  const camId = $('remoteCamSlot')?.value || 'cam0';
  try {
    await stopCam(camId);
    unhookFeed(camId);
    showMsg('remoteCamMsg', `หยุด ${camId} แล้ว`, 'info');
  } catch (e) { toast(`Error: ${e}`, 'err'); }
});

// ── ⚙ per-camera quick source change ────────────────────────────────────────
document.querySelectorAll('.cam-arrow').forEach(arrow => {
  arrow.addEventListener('click', () => {
    const idx = parseInt(arrow.dataset.idx ?? '0', 10);
    let last = '0';
    try { last = JSON.parse(localStorage.getItem(RC_KEY) || '{}').url || '0'; } catch {}
    const src = prompt(`source กล้อง ${idx + 1}  (0 = webcam,  rtsp://… ,  http://…/video ,  https://youtu.be/…):`, last);
    if (src === null) return;
    connectSource(`cam${idx}`, src.trim(), '', 'remoteCamMsg');
  });
});

// ── Extra CSS injected at runtime ─────────────────────────────────────────────
document.head.insertAdjacentHTML('beforeend', `<style>
  .ppe-check.ok   { background:#22c55e !important; color:#fff; }
  .ppe-check.fail { background:#ef4444 !important; color:#fff; }
  .ppe-check.none { background:#374151 !important; color:#9ca3af; }
  .alert-time     { font-size:.75rem; color:#a0b0e0; margin-right:6px; white-space:nowrap; }
</style>`);

const LIVE_CAM_STATES = new Set(['running', 'starting', 'connecting', 'reconnecting']);
async function initCameras() {
  try {
    const r = await fetch('/api/camera/status');
    const d = await r.json();
    const cams = d.cams || {};
    for (const [camId, info] of Object.entries(cams)) {
      if (LIVE_CAM_STATES.has(info.status)) hookFeed(camId, info.label || '');
      else                                  unhookFeed(camId);
    }
  } catch {}
}

// ── Init ─────────────────────────────────────────────────────────────────────
checkModel();
initGate();
initCameras();
setTimeout(initCameras, 4000);   // re-check once restored cams have connected
loadAlertHistory();
connectStatsSSE();
connectAlertsSSE();
