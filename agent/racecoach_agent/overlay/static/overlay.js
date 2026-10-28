/* RaceCoach – nakładki: delta, czasy, minimapa, wskazówki, instruktor.
   Logika rysowania przeniesiona z SimTrainer (overlay.js). Dwa źródła danych:
   - lokalnie u agenta (http://127.0.0.1:31399/): stan gry kilkadziesiąt razy na sekundę, ?gra=1 w oknie nad grą;
   - w panelu centrali (/overlay/<stanowisko>): podgląd ~1×/s i edycja układu zapisywana w centrali. */
'use strict';

const CENTRAL = !!window.RC_CENTRAL;
const STATION = CENTRAL ? decodeURIComponent(location.pathname.split('/').filter(Boolean).pop()) : 'local';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const params = new URLSearchParams(location.search);
const GAME = params.get('gra') === '1';           // okno nad grą: bez paska, bez tła, bez przeciągania
const EDIT = CENTRAL && !GAME;                      // przeciąganie zapisuje układ w centrali

const DEFAULTS = {
  'w-delta': { x: 0.5, y: 0.12, center: true },
  'w-times': { x: 0.02, y: 0.03 },
  'w-map': { x: 0.80, y: 0.62 },
  'w-tips': { x: 0.02, y: 0.66 },
  'w-msg': { x: 0.73, y: 0.03 },
};

let st = null;          // stan sesji: {state, session, live, pb_ms, ref, tips, message, race, layout, map}
let ref = null;         // przebieg wzorcowy {t, x, z, len_m, time_ms, meta}
let refId = -1;
let lastUpdate = 0;
let lastT = null;
let shownS = null;
let tipsLap = null;
let msgId = null;
let shownDelta = null;
let layoutId = null;

// ------------------------------------------------------------------ formatowanie
function fmtMs(ms) {
  if (!ms || ms <= 0) return '—';
  const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000), x = Math.floor(ms % 1000);
  return `${m}:${String(s).padStart(2, '0')}.${String(x).padStart(3, '0')}`;
}
function fmtRunning(ms) {
  if (!ms || ms <= 0) return '0:00.0';
  const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
  return `${m}:${String(s).padStart(2, '0')}.${Math.floor((ms % 1000) / 100)}`;
}

// ------------------------------------------------------------------ układ
const settings = { pos: {}, off: {}, scene: !GAME && params.get('tlo') !== '0' };
if (!settings.scene) {
  document.body.classList.add('transparent');
  document.documentElement.classList.add('transparent');
}
if (GAME) document.body.classList.add('game');

const REF_H = 900;   // rozmiar okienek rośnie z wysokością ekranu – podgląd i gra wyglądają tak samo
let K = 1;
function updateScale() {
  K = Math.max(0.6, Math.min(innerHeight / REF_H, 2.4));
  document.documentElement.style.setProperty('--k', String(K));
}
updateScale();

function applyLayout(layout) {
  if (!layout || layout.id === layoutId) return;
  layoutId = layout.id;
  settings.pos = layout.pos || {};
  settings.off = layout.off || {};
  for (const w of document.querySelectorAll('.widget')) w.hidden = !!settings.off[w.id];
  for (const cb of document.querySelectorAll('#toggles input')) cb.checked = !settings.off[cb.dataset.w];
  placeAll();
}
let saveTimer = null;
function saveLayout() {
  if (!EDIT) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const pos = {};
    for (const w of document.querySelectorAll('.widget')) pos[w.id] = { x: w.offsetLeft / innerWidth, y: w.offsetTop / innerHeight };
    fetch(`/api/stations/${encodeURIComponent(STATION)}/overlay`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
      body: JSON.stringify({ pos, off: settings.off }),
    }).then((r) => r.json()).then((l) => { layoutId = l.id; }).catch(() => {});
  }, 400);
}
function placeAll() {
  for (const w of document.querySelectorAll('.widget')) place(w);
}
function place(w) {
  const p = settings.pos[w.id] || DEFAULTS[w.id];
  const ww = w.offsetWidth * K, wh = w.offsetHeight * K;
  let x = p.x * innerWidth;
  if (!settings.pos[w.id] && DEFAULTS[w.id].center) x -= ww / 2;
  const y = p.y * innerHeight;
  w.style.left = `${Math.max(0, Math.min(x, innerWidth - ww))}px`;
  w.style.top = `${Math.max(0, Math.min(y, innerHeight - wh))}px`;
}
function buildToolbar() {
  $('#bar-title').textContent = CENTRAL ? 'Nakładki – układ dla stanowiska' : 'Nakładki – podgląd stanowiska';
  if (!EDIT) $('#bar-hint').textContent = 'układ ustawia się w panelu centrali (Stanowiska → Nakładki) · klawisz H ukrywa pasek';
  $('#toggles').innerHTML = [...document.querySelectorAll('.widget')].map((w) =>
    `<label class="tgl"><input type="checkbox" data-w="${w.id}" ${settings.off[w.id] ? '' : 'checked'} ${EDIT ? '' : 'disabled'}> ${esc(w.dataset.name)}</label>`).join('');
  $('#toggles').addEventListener('change', (e) => {
    const id = e.target.dataset.w;
    settings.off[id] = !e.target.checked;
    $(`#${id}`).hidden = settings.off[id];
    if (!settings.off[id]) place($(`#${id}`));
    saveLayout();
  });
  $('#opt-scene').checked = settings.scene;
  document.body.classList.toggle('scene', settings.scene);
  $('#opt-scene').onchange = (e) => {
    settings.scene = e.target.checked;
    document.body.classList.toggle('scene', settings.scene);
  };
  $('#reset').hidden = !EDIT;
  $('#reset').onclick = () => {
    settings.pos = {};
    settings.off = {};
    for (const w of document.querySelectorAll('.widget')) w.hidden = false;
    for (const cb of document.querySelectorAll('#toggles input')) cb.checked = true;
    placeAll();
    saveLayout();
  };
  let timer = null;
  const bar = $('#bar');
  const show = () => { bar.classList.remove('hidden'); clearTimeout(timer); timer = setTimeout(() => bar.classList.add('hidden'), 4000); };
  addEventListener('mousemove', show);
  addEventListener('keydown', (e) => { if (e.key === 'h' || e.key === 'H') bar.classList.toggle('hidden'); });
  show();
}
function enableDrag(w) {
  let sx = 0, sy = 0, ox = 0, oy = 0, id = null;
  w.addEventListener('pointerdown', (e) => {
    id = e.pointerId;
    w.setPointerCapture(id);
    w.classList.add('dragging');
    sx = e.clientX; sy = e.clientY;
    ox = w.offsetLeft; oy = w.offsetTop;
  });
  w.addEventListener('pointermove', (e) => {
    if (e.pointerId !== id) return;
    w.style.left = `${Math.max(0, Math.min(ox + e.clientX - sx, innerWidth - w.offsetWidth * K))}px`;
    w.style.top = `${Math.max(0, Math.min(oy + e.clientY - sy, innerHeight - w.offsetHeight * K))}px`;
  });
  const end = (e) => {
    if (e.pointerId !== id) return;
    id = null;
    w.classList.remove('dragging');
    settings.pos[w.id] = { x: w.offsetLeft / innerWidth, y: w.offsetTop / innerHeight };
    saveLayout();
  };
  w.addEventListener('pointerup', end);
  w.addEventListener('pointercancel', end);
}

// ------------------------------------------------------------------ wzorzec
function refPoint(s) {
  const n = ref.x.length;
  const pos = (((s % 1) + 1) % 1) * n;
  const i = Math.floor(pos) % n, j = (i + 1) % n, f = pos - Math.floor(pos);
  return [ref.x[i] + (ref.x[j] - ref.x[i]) * f, ref.z[i] + (ref.z[j] - ref.z[i]) * f];
}
async function loadReference() {
  try {
    const r = await (await fetch('reference')).json();
    ref = r && r.x ? r : null;
  } catch (_) { ref = null; }
}

// ------------------------------------------------------------------ dane na żywo
function predicted() {
  const lv = st.live || {};
  const onTrack = st.state === 'on_track';
  const dt = onTrack ? Math.min((performance.now() - lastUpdate) / 1000, CENTRAL ? 1.5 : 0.5) : 0;
  let s = lv.spline;
  if (s != null && ref && ref.len_m) {
    s += ((lv.speed_kmh || 0) / 3.6) * dt / ref.len_m;
    if (shownS != null && s < shownS && shownS - s < 0.01) s = shownS;
    shownS = s;
  }
  return { s, cur: (lv.current_ms || 0) + dt * 1000, onTrack };
}
function renderStatic() {
  if (!st) return;
  const lv = st.live || {};
  const session = st.session || {};
  const race = st.race;
  const lapNo = (lv.lap_no || 0) + 1;
  $('#t-lap').textContent = !st.active ? 'BRAK SESJI' : race && race.laps ? `OKRĄŻENIE ${Math.min(lapNo, race.laps)}/${race.laps}` : `OKRĄŻENIE ${lapNo}`;
  $('#t-pos').textContent = race && race.done ? 'META' : race ? 'WYŚCIG' : '';
  $('#t-last').textContent = fmtMs(lv.last_ms);
  $('#t-last').style.color = lv.last_ms && lv.last_valid === false ? 'var(--red)' : '';
  $('#t-best').textContent = fmtMs(lv.best_ms);
  $('#t-pb').textContent = fmtMs(st.pb_ms);
  $('#delta-vs').textContent = st.ref ? `vs ${st.ref.label}` : '';
  $('#msg-goal').textContent = session.goal ? `Cel: ${session.goal}` : session.exercise ? session.exercise : '';
  const msg = st.message;
  $('#msg-text').textContent = msg ? msg.text : '';
  if (msg && msg.id !== msgId) {
    msgId = msg.id;
    $('#w-msg').classList.add('fresh');
    setTimeout(() => $('#w-msg').classList.remove('fresh'), 8000);
  }
  if (!session.goal && !msg) $('#msg-text').textContent = 'Brak wiadomości.';
  $('#w-msg').style.opacity = session.goal || msg ? 1 : 0.55;
  const tips = st.tips;
  if (tips) {
    $('#tips-lap').textContent = `po okrążeniu ${tips.lap_no}`;
    $('#tips-body').innerHTML = `<div class="tips-sum">${esc(tips.summary)}</div>` + (tips.lines || []).map((l) =>
      `<div class="tip"><span class="num">${l.corner}</span><span>${esc(l.text.replace(/^Zakręt \d+, /, ''))}</span></div>`).join('');
    if (tipsLap !== tips.lap_no) {
      tipsLap = tips.lap_no;
      $('#w-tips').classList.add('fresh');
      setTimeout(() => $('#w-tips').classList.remove('fresh'), 8000);
    }
  }
}
function renderLive() {
  requestAnimationFrame(renderLive);
  if (!st) return;
  const p = predicted();
  $('#t-cur').textContent = p.onTrack || st.state === 'in_pit' ? fmtRunning(p.cur) : '—';
  const raw = (st.live || {}).delta_ms;
  shownDelta = raw == null ? null : (shownDelta == null ? raw : shownDelta + (raw - shownDelta) * 0.25);
  const delta = shownDelta == null ? null : Math.round(shownDelta);
  const num = $('#delta-num'), fill = $('#delta-fill');
  if (delta == null || !p.onTrack) {
    num.textContent = '—';
    num.className = 'delta-num';
    fill.style.width = '0';
  } else {
    num.textContent = `${delta >= 0 ? '+' : '−'}${(Math.abs(delta) / 1000).toFixed(2)}`;
    num.className = `delta-num ${delta < 0 ? 'neg' : 'pos'}`;
    const w = Math.min(Math.abs(delta) / 1000, 1) * 50;
    fill.style.width = `${w}%`;
    fill.style.left = delta < 0 ? `${50 - w}%` : '50%';
    fill.style.background = delta < 0 ? 'var(--green)' : 'var(--red)';
  }
  drawMap(p.s);
}

// ------------------------------------------------------------------ minimapa
const canvas = $('#map');
const ctx = canvas.getContext('2d');
(function hidpi() {
  const r = devicePixelRatio || 1;
  canvas.width = 240 * r;
  canvas.height = 240 * r;
  ctx.scale(r, r);
})();
const BACK_M = 120, AHEAD_M = 380;
const mapImg = new Image();
let mapUrl = null;
let mapReady = false;
mapImg.onload = () => { mapReady = true; };
mapImg.onerror = () => { mapReady = false; };
function ensureMapImage() {
  const url = st && st.map ? st.map.url : null;
  if (url !== mapUrl) {
    mapUrl = url;
    mapReady = false;
    if (url) mapImg.src = url;
  }
}
// Auto rysowane lekko „w przeszłości” i interpolowane krzywą Hermite'a między paczkami – bez przeskoków.
const RENDER_DELAY_MS = CENTRAL ? 1100 : 60;
const samples = [];
let clockOff = null;
const car = { hx: 0, hz: -1, x: null, z: null };
function pushSample(lv) {
  if (lv.x == null || lv.z == null || lv.t == null) return;
  const now = performance.now();
  const off = now - lv.t;
  const last = samples[samples.length - 1];
  if (last && (lv.t <= last.t - 1000 || lv.t - last.t > 3000 || Math.hypot(lv.x - last.x, lv.z - last.z) > 300)) {
    samples.length = 0;
    clockOff = null;
  } else if (last && lv.t <= last.t) {
    return;
  }
  if (clockOff == null || Math.abs(off - clockOff) > 300) clockOff = off;
  else if (off < clockOff) clockOff += (off - clockOff) * 0.15;
  else clockOff += 0.03;
  const smp = { t: lv.t, x: lv.x, z: lv.z, vx: lv.vx, vz: lv.vz, vok: lv.vx != null && lv.vz != null };
  const prev = samples[samples.length - 1];
  if (smp.vok && prev) {
    const dt = (smp.t - prev.t) / 1000;
    const fx = (smp.x - prev.x) / dt, fz = (smp.z - prev.z) / dt;
    const v = Math.hypot(smp.vx, smp.vz), f = Math.hypot(fx, fz);
    if (v > 3 && f > 3 && (smp.vx * fx + smp.vz * fz) / (v * f) < 0.7) smp.vok = false;
  }
  samples.push(smp);
  if (samples.length > 30) samples.shift();
}
function sampleVel(i) {
  const s = samples[i];
  if (s.vok) return [s.vx, s.vz];
  const a = samples[Math.max(0, i - 1)], b = samples[Math.min(samples.length - 1, i + 1)];
  const dt = (b.t - a.t) / 1000;
  return dt > 0 ? [(b.x - a.x) / dt, (b.z - a.z) / dt] : [0, 0];
}
function carAt(rt) {
  const n = samples.length;
  if (!n) return null;
  if (n === 1 || rt <= samples[0].t) {
    const v = n > 1 ? sampleVel(0) : [0, 0];
    return [samples[0].x, samples[0].z, v[0], v[1]];
  }
  const lastI = n - 1;
  if (rt >= samples[lastI].t) {
    const l = samples[lastI], v = sampleVel(lastI);
    const dt = st.state === 'on_track' ? Math.min(rt - l.t, 400) / 1000 : 0;
    return [l.x + v[0] * dt, l.z + v[1] * dt, v[0], v[1]];
  }
  let i = lastI - 1;
  while (i > 0 && samples[i].t > rt) i--;
  const a = samples[i], b = samples[i + 1];
  const h = (b.t - a.t) / 1000;
  const u = (rt - a.t) / (b.t - a.t);
  const va = sampleVel(i), vb = sampleVel(i + 1);
  const u2 = u * u, u3 = u2 * u;
  const h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u, h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
  return [h00 * a.x + h10 * h * va[0] + h01 * b.x + h11 * h * vb[0],
    h00 * a.z + h10 * h * va[1] + h01 * b.z + h11 * h * vb[1],
    va[0] + (vb[0] - va[0]) * u, va[1] + (vb[1] - va[1]) * u];
}
function carNow() {
  let p = null;
  if (samples.length && clockOff != null) p = carAt(performance.now() - clockOff - RENDER_DELAY_MS);
  if (!p) {
    const lv = st && st.live;
    if (!lv || lv.x == null || lv.z == null) return null;
    p = [lv.x, lv.z, 0, 0];
  }
  const v = Math.hypot(p[2], p[3]);
  if (v > 1) {
    const k = 0.35;
    car.hx = car.hx * (1 - k) + (p[2] / v) * k;
    car.hz = car.hz * (1 - k) + (p[3] / v) * k;
    const nrm = Math.hypot(car.hx, car.hz) || 1;
    car.hx /= nrm; car.hz /= nrm;
  }
  car.x = p[0]; car.z = p[1];
  return [p[0], p[1]];
}
function drawGameMap() {
  const W = 240, H = 240;
  const ini = st.map.ini;
  const sf = ini.SCALE_FACTOR || 1;
  const pos = carNow();
  if (!pos) return false;
  const px = (pos[0] + ini.X_OFFSET) / sf;
  const pz = (pos[1] + ini.Z_OFFSET) / sf;
  const rot = -Math.PI / 2 - Math.atan2(car.hz, car.hx);
  const q = (H * 0.68) / AHEAD_M;
  const k = q * sf;
  const ox = W / 2, oy = H * 0.74;
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(0, 0, W, H, 10); else ctx.rect(0, 0, W, H);
  ctx.clip();
  ctx.save();
  ctx.translate(ox, oy);
  ctx.rotate(rot);
  ctx.scale(k, k);
  ctx.translate(-px, -pz);
  ctx.globalAlpha = 0.9;
  ctx.drawImage(mapImg, 0, 0);
  ctx.restore();
  if (ref && ref.meta && ref.meta.corners) {
    const n = ref.x.length;
    const c0 = Math.cos(rot), s0 = Math.sin(rot);
    for (const c of ref.meta.corners) {
      const i = Math.round(c.s * n) % n;
      const mx = (ref.x[i] + ini.X_OFFSET) / sf - px, mz = (ref.z[i] + ini.Z_OFFSET) / sf - pz;
      const x = ox + (mx * c0 - mz * s0) * k, y = oy + (mx * s0 + mz * c0) * k;
      if (x < 8 || x > W - 8 || y < 8 || y > H - 8) continue;
      drawCornerBadge(x, y, c.n);
    }
  }
  drawCar(ox, oy);
  ctx.restore();
  return true;
}
function drawCornerBadge(x, y, num) {
  ctx.fillStyle = '#e77942';
  ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#1d0f07';
  ctx.font = 'bold 12px Segoe UI, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(num), x, y + 0.5);
}
function drawCar(ox, oy) {
  ctx.fillStyle = '#3dd68c';
  ctx.strokeStyle = '#06210f';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(ox, oy - 11); ctx.lineTo(ox + 8, oy + 8); ctx.lineTo(ox, oy + 4); ctx.lineTo(ox - 8, oy + 8); ctx.closePath();
  ctx.fill(); ctx.stroke();
}
function drawMap(s) {
  try {
    ensureMapImage();
    if (st && st.map && mapReady && drawGameMap()) return;
    drawRefMap(s);
  } catch (e) {
    console.error('minimapa:', e);
  }
}
function drawRefMap(s) {
  const W = 240, H = 240;
  ctx.clearRect(0, 0, W, H);
  if (!ref || s == null) {
    ctx.fillStyle = '#9aa1ab';
    ctx.font = '13px Segoe UI, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(CENTRAL ? 'Minimapa widoczna' : 'Mapa pojawi się po', W / 2, H / 2 - 8);
    ctx.fillText(CENTRAL ? 'na stanowisku' : 'pierwszym pełnym okrążeniu', W / 2, H / 2 + 10);
    return;
  }
  const n = ref.x.length;
  const mpp = ref.len_m / n;
  const [cx, cz] = refPoint(s);
  const [ax, az] = refPoint(s + 6 / ref.len_m);
  const [bx, bz] = refPoint(s - 6 / ref.len_m);
  const ang = Math.atan2(az - bz, ax - bx);
  const rot = -Math.PI / 2 - ang;
  const cos = Math.cos(rot), sin = Math.sin(rot);
  const scale = (H * 0.68) / AHEAD_M;
  const ox = W / 2, oy = H * 0.74;
  const tx = (x, z) => {
    const dx = x - cx, dz = z - cz;
    return [ox + (dx * cos - dz * sin) * scale, oy + (dx * sin + dz * cos) * scale];
  };
  const i0 = Math.floor(s * n);
  const from = -Math.round(BACK_M / mpp), to = Math.round(AHEAD_M / mpp);
  const at = (k) => tx(ref.x[((i0 + k) % n + n) % n], ref.z[((i0 + k) % n + n) % n]);
  ctx.save();
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(0, 0, W, H, 10); else ctx.rect(0, 0, W, H);
  ctx.clip();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (let k = from; k < to; k++) {
    const a = at(k), b = at(k + 1);
    const edge = Math.min(k - from, to - k) / 12;
    ctx.globalAlpha = Math.max(0.1, Math.min(1, edge));
    ctx.strokeStyle = '#4a515c';
    ctx.lineWidth = Math.max(12, 14 * scale);
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.strokeStyle = 'rgba(232,234,237,.55)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let k = 0; k < to; k++) {
    const p = at(k);
    if (k === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
  }
  ctx.stroke();
  const fin = ((0 - i0) % n + n) % n;
  if (fin < to || fin > n + from) {
    const p = at(fin < to ? fin : fin - n);
    ctx.fillStyle = '#e8eaed';
    ctx.fillRect(p[0] - 9, p[1] - 2, 18, 4);
  }
  for (const c of (ref.meta && ref.meta.corners) || []) {
    let k = Math.round(c.s * n) - i0;
    if (k < -n / 2) k += n;
    if (k > n / 2) k -= n;
    if (k < from + 4 || k > to - 4) continue;
    const p = at(k);
    drawCornerBadge(p[0], p[1], c.n);
  }
  drawCar(ox, oy);
  ctx.restore();
}

// ------------------------------------------------------------------ połączenie
function onState(state) {
  st = state;
  applyLayout(state.layout);
  const lv = state.live || {};
  if (lv.t != null && lv.t !== lastT) {
    lastT = lv.t;
    lastUpdate = performance.now();
    pushSample(lv);
  }
  const rid = state.ref ? state.ref.id : -1;
  if (!CENTRAL && rid !== refId) {
    refId = rid;
    shownS = null;
    if (state.ref) loadReference(); else ref = null;
  }
  renderStatic();
}
async function poll() {
  const url = CENTRAL ? `/api/stations/${encodeURIComponent(STATION)}/overlay-state` : 'state';
  try {
    const r = await fetch(url, { cache: 'no-store', credentials: 'same-origin' });
    if (r.status === 401) $('#bar-title').textContent = 'Zaloguj się w panelu RaceCoach, aby edytować nakładki';
    else if (r.ok) onState(await r.json());
  } catch (_) { /* agent lub centrala chwilowo niedostępne */ }
  setTimeout(poll, CENTRAL ? 700 : 40);
}

document.title = CENTRAL ? 'RaceCoach – układ nakładek' : 'RaceCoach – nakładki';
buildToolbar();
if (EDIT) for (const w of document.querySelectorAll('.widget')) enableDrag(w);
placeAll();
addEventListener('resize', () => { updateScale(); placeAll(); });
poll();
requestAnimationFrame(renderLive);
