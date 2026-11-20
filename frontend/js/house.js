/* WattWise interactive house.
 *
 * A real 3D house (three.js, in frontend/vendor/three, so it works offline); the drawing
 * itself is in js/house3d.js. This file reads the state, fills the side panels, places
 * the HTML labels over the 3D scene and runs the guided tour.
 * It reads the SAME state as the dashboard (GET /api/sites/<site>/state, once a second)
 * and sends the SAME commands (toggle, approve, reject, goal, scenario).
 * Nothing here decides anything: the backend agent and the Policy Guard decide.
 * This page only shows what is happening, and lets the owner act.
 *
 * Works offline: no internet, no external library. Served by our own backend.
 */

import { createHouse } from './house3d.js';

const { esc, fmt } = WW;
const $ = id => document.getElementById(id);

let st = null;                       // latest state from the backend
let built = '';                      // signature of the drawn layout (rebuild when it changes)
let scene3d = null;                  // the three.js scene (house3d.js)
let pinEls = [];                     // [key, element] HTML labels glued to 3D points
const ui = {
  view: localGet('ww-house-view3') || 'iso',
  tourFocus: null,                   // the tour step the camera last flew to
  room: null, device: null,
  tour: null,                        // index of the tour step, or null
  busy: false,
};

function localGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function localSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove('show'), 3500);
}

// ---------- device drawings (small SVGs, animated with CSS classes) ----------
const ICON = {
  ac: `<rect x="4" y="10" width="40" height="15" rx="4" class="body"/><path d="M9 20h30" class="slot"/>
       <g class="air"><path d="M12 30q2 5 0 10"/><path d="M24 30q2 5 0 10"/><path d="M36 30q2 5 0 10"/></g>`,
  fan: `<path d="M24 26v16M16 44h16" class="stand"/><circle cx="24" cy="18" r="14" class="cage"/>
        <g class="spin"><path d="M24 18c-2-9 6-11 6-5s-4 5-6 5zM24 18c8 4 3 10-1 7s-1-6 1-7zM24 18c-7 5-11-2-6-4s6 2 6 4z" class="blade"/></g>
        <circle cx="24" cy="18" r="2.2" class="hub"/>`,
  light: `<path d="M24 2v6" class="stand"/><path d="M14 18a10 10 0 0 1 20 0c0 4-3 6-4 9h-12c-1-3-4-5-4-9z" class="bulb"/>
          <path d="M19 31h10M20 35h8" class="stand"/><g class="rays"><path d="M6 16h-4M46 16h-4M10 5l-3-3M38 5l3-3"/></g>`,
  heater: `<rect x="12" y="6" width="24" height="34" rx="10" class="body"/><circle cx="24" cy="30" r="4" class="dial"/>
           <g class="heat"><path d="M17 4q-3-3 0-6"/><path d="M24 4q-3-3 0-6"/><path d="M31 4q-3-3 0-6"/></g>`,
  tv: `<rect x="3" y="8" width="42" height="26" rx="3" class="body"/><rect x="6" y="11" width="36" height="20" rx="1" class="screen"/>
       <path d="M18 40h12M24 34v6" class="stand"/>`,
  washer: `<rect x="8" y="4" width="32" height="38" rx="4" class="body"/><path d="M8 12h32" class="slot"/>
           <circle cx="24" cy="27" r="10" class="dial"/><g class="spin"><path d="M18 27a6 6 0 0 1 12 0" class="blade"/></g>`,
  fridge: `<rect x="12" y="2" width="24" height="42" rx="4" class="body"/><path d="M12 17h24M16 8v5M16 22v8" class="slot"/>`,
  fire_alarm: `<circle cx="24" cy="22" r="14" class="body"/><circle cx="24" cy="22" r="4" class="led"/>`,
  emergency_light: `<rect x="6" y="14" width="36" height="14" rx="3" class="body"/><path d="M14 21h20" class="led-line"/>`,
  router: `<rect x="6" y="22" width="36" height="14" rx="3" class="body"/><path d="M14 22l-4-14M34 22l4-14" class="stand"/>
           <circle cx="15" cy="29" r="2" class="led"/><circle cx="22" cy="29" r="2" class="led d2"/><circle cx="29" cy="29" r="2" class="led d3"/>`,
  pc: `<rect x="5" y="6" width="38" height="24" rx="3" class="body"/><rect x="8" y="9" width="32" height="18" class="screen"/>
       <path d="M18 40h12M24 30v10" class="stand"/>`,
  other: `<rect x="14" y="14" width="20" height="20" rx="5" class="body"/><path d="M20 8v6M28 8v6M24 34v8" class="stand"/>`,
};
const icon = kind => `<svg viewBox="0 0 48 48" class="ico k-${esc(kind)}" aria-hidden="true">${ICON[kind] || ICON.other}</svg>`;
const KIND_AR = { ac: 'مكيّف', fan: 'مروحة', light: 'إنارة', heater: 'سخّان', tv: 'تلفزيون', washer: 'غسالة', fridge: 'ثلاجة',
  fire_alarm: 'إنذار حريق', emergency_light: 'إنارة طوارئ', router: 'راوتر', pc: 'كمبيوتر', other: 'جهاز' };

// ---------- labels over the 3D scene ----------
function buildPins() {
  const pins = [];
  for (const r of st.rooms) {
    pins.push(['room:' + r.id, `<div class="rl" data-act="room" data-id="${esc(r.id)}" data-rl="${esc(r.id)}">
      <div class="rl-name">${esc(r.name)}</div>
      <div class="rl-row"><span class="rl-occ"></span><span class="rl-temp mono" dir="ltr"></span><span class="rl-w mono" dir="ltr"></span></div></div>`, 'room']);
    pins.push(['tag:' + r.id, `<div class="rl-tag" data-rt="${esc(r.id)}"></div>`, 'rtag']);
  }
  for (const d of st.devices) {
    pins.push(['dev:' + d.id, `<button class="chip" data-act="device" data-id="${esc(d.id)}" data-dev="${esc(d.id)}" aria-label="${esc(d.name)}">
      <span class="chip-badge"></span><span class="chip-w mono" dir="ltr"></span></button>`, 'dev']);
  }
  pins.push(['meter', `<div class="meter-in" data-act="meter"><div class="m-lab">العدّاد الرئيسي${st.source === 'device' ? ' · PZEM' : ''}</div><div class="m-w mono" dir="ltr" id="m-w">—</div></div>`, 'meter']);
  if (st.ev) pins.push(['car', '<div class="car-card" id="car-card"></div>', 'car']);
  $('pins').innerHTML = pins.map(([k, html, cls]) => `<div class="pin ${cls}" data-pin="${k}">${html}</div>`).join('');
  pinEls = pins.map(([k]) => [k, $('pins').querySelector(`[data-pin="${k}"]`)]);
}

// Put every label where its 3D point is on screen (called every animation frame).
function placePins() {
  if (!scene3d) return;
  for (const [k, el] of pinEls) {
    const p = scene3d.project(k);
    if (!p || p.behind) { el.style.display = 'none'; continue; }
    el.style.display = '';
    const sc = Math.max(0.55, Math.min(1, 24 / p.dist));
    el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px) scale(${sc.toFixed(3)})`;
    el.style.zIndex = String(1000 - Math.round(p.dist * 10));
  }
}

function build() {
  if (!scene3d) {
    scene3d = createHouse($('scene'), {
      onRoom: id => { ui.room = id; ui.device = null; scene3d.focusRoom(id); update(); },
      onDevice: id => { const d = st.devices.find(x => x.id === id); ui.device = id; ui.room = d && d.room; update(); },
      onFrame: placePins,
    });
  }
  scene3d.build(st, { narrow: $('scene').clientWidth < 600 });
  scene3d.setView(ui.view, true);
  buildPins();
}

// ---------- update every second (no rebuild: CSS transitions stay smooth) ----------
function pendingDeviceId() {
  const p = st.pending;
  if (!p) return null;
  return p.device_id || (p.details && p.details.device_id) || (st.devices.find(d => p.title && p.title.includes(d.name)) || {}).id || null;
}

function update() {
  $('v-iso').classList.toggle('sel', ui.view === 'iso');
  $('v-flat').classList.toggle('sel', ui.view !== 'iso');
  const pend = pendingDeviceId();
  const pendRoom = pend && (st.devices.find(d => d.id === pend) || {}).room;
  scene3d.update(st, { pendingDevice: pend, room: ui.room });

  for (const r of st.rooms) {
    const L = $('pins').querySelector(`[data-rl="${r.id}"]`);
    if (!L) continue;
    const hot = r.temp_c != null && r.temp_c > st.comfort.max_c, cold = r.temp_c != null && r.temp_c < st.comfort.min_c;
    L.classList.toggle('sel', ui.room === r.id);
    const occ = L.querySelector('.rl-occ');
    occ.textContent = r.occupied == null ? '' : r.occupied ? '● فيها حدا' : '○ فاضية';
    occ.className = 'rl-occ ' + (r.occupied ? 'on' : 'off');
    const tEl = L.querySelector('.rl-temp');
    tEl.textContent = r.temp_c == null ? '' : fmt(r.temp_c, 1) + '°';
    tEl.className = 'rl-temp mono' + (hot ? ' hot' : cold ? ' cold' : '');
    L.querySelector('.rl-w').textContent = fmt(r.power_w, 0) + ' W';
    const tag = pendRoom === r.id ? '<b class="t-pend">بانتظار موافقتك</b>'
      : r.waste ? '<b class="t-waste">هدر!</b>'
      : r.window_open ? '<b class="t-win">الشباك مفتوح</b>' : '';
    const tagEl = $('pins').querySelector(`[data-rt="${r.id}"]`);
    if (tagEl.innerHTML !== tag) tagEl.innerHTML = tag;
  }
  for (const d of st.devices) {
    const c = $('pins').querySelector(`[data-dev="${d.id}"]`);
    if (!c) continue;
    const locked = d.tier === 'T2';
    c.classList.toggle('on', d.is_on); c.classList.toggle('off', !d.is_on && !locked); c.classList.toggle('pend', pend === d.id); c.classList.toggle('sel', ui.device === d.id);
    c.classList.toggle('agent-off', d.agent_off > 0); c.classList.toggle('locked', locked);
    c.querySelector('.chip-w').textContent = d.kind === 'ev' && st.ev && st.ev.charging ? `${fmt(st.ev.power_w / 1000, 1)} kW`
      : d.is_on ? (d.est_w >= 1000 ? `${fmt(d.est_w / 1000, 1)} kW` : `${d.est_w} W`) : (locked ? '' : 'مطفي');
    c.querySelector('.chip-badge').textContent = locked ? '🔒' : !d.allow ? '⚠' : d.agent_off === 2 ? '✓' : d.agent_off === 1 ? '…' : '';
  }
  renderCar();
  const mw = st.meter.power_w;
  $('m-w').textContent = mw == null ? '—' : mw >= 1000 ? fmt(mw / 1000, 2) + ' kW' : fmt(mw, 0) + ' W';
  renderHud();
  renderPipe();
  renderApproval();
  renderRoom();
  renderPrint();
  if (ui.tour !== null) renderTour();
}

// The car in the driveway: battery, power, time to the target.
function renderCar() {
  const el = $('car-card');
  if (!el || !st.ev) return;
  const e = st.ev, soc = e.soc_pct == null ? null : Math.round(e.soc_pct);
  const state = e.charging ? `⚡ عم تشحن · <b class="mono" dir="ltr">${fmt(e.power_w / 1000, 1)} kW</b>`
    : e.resume_at ? `⏸ موقوف · بيكمّل <b class="mono" dir="ltr">${esc(e.resume_at)}</b>` : soc != null && soc >= 99 ? '✓ مشحونة' : 'مش عم تشحن';
  const eta = !e.charging ? '' : e.minutes_to_target > 0 ? `${Math.floor(e.minutes_to_target / 60)}س ${e.minutes_to_target % 60}د لـ ${e.target_soc}٪` : `وصلت ${e.target_soc}٪`;
  WW.render(el, `
    <div class="car-top"><span>🚗 السيارة</span><span class="mono" dir="ltr">${soc == null ? '—' : soc + '%'}</span></div>
    <div class="car-bar"><i style="width:${soc || 0}%"></i><u style="left:${e.target_soc}%"></u></div>
    <div class="car-sub">${state}</div>
    ${eta ? `<div class="car-sub dim">${eta}${e.session_kwh != null ? ` · ${fmt(e.session_kwh, 1)} kWh` : ''}</div>` : ''}`);
  el.classList.toggle('charging', !!e.charging);
}

// ---------- top: meter + agent ----------
function renderHud() {
  const s = st.savings, mw = st.meter.power_w || 0;
  WW.render($('hud-meter'), `
    <div class="label">الآن</div>
    <div class="hud-big mono" dir="ltr">${mw >= 1000 ? fmt(mw / 1000, 2) + '<small>kW</small>' : fmt(mw, 0) + '<small>W</small>'}</div>
    <div class="hud-sub">وفّرنا (مقاس بالعدّاد): <b class="mono" dir="ltr">${fmt(s.kwh, 2)} kWh</b> · <b class="mono" dir="ltr">${fmt(s.jod, 3)} JD</b>${s.co2_kg != null ? ` · <b class="mono" dir="ltr">${fmt(s.co2_kg, 2)} kg CO₂</b>` : ''}</div>`);
  const a = WW.agentLabel(st);
  const brain = st.agent.brain && st.agent.brain.mode === 'llm' ? 'نموذج ذكاء اصطناعي + حارس سياسات' : 'وضع القواعد (بدون إنترنت) + حارس سياسات';
  WW.render($('hud-agent'), `
    <div class="label">الوكيل</div>
    <div class="hud-state"><i class="dot" style="background:${a.color}"></i>${esc(a.label)}</div>
    <div class="hud-sub">${st.goal ? 'الهدف: ' + esc(st.goal.text) : 'ما في هدف لسا. اكبس «كيف بيشتغل؟» وابدأ.'}</div>
    <div class="hud-sub dim">${esc(brain)}</div>`);
  $('data-note').textContent = st.source === 'simulator'
    ? 'بيانات اصطناعية من المحاكي (Digital Twin)' : 'قراءات حقيقية من ESP32 + PZEM';
}

// ---------- the process strip ----------
const PIPE_TOUR = [1, 2, 2, 3, 4, 5, 6];   // which tour step explains each goal step
function renderPipe() {
  const steps = WW.goalSteps(st);
  WW.render($('pipe'), steps.map((s, i) => `
    <button class="pipe-s s-${s.tag ? (s.tag === 'تم' ? 'done' : s.color === '#E8553F' ? 'halt' : 'act') : 'todo'}" data-act="tour-go" data-step="${PIPE_TOUR[i]}">
      <span class="pn mono">${s.n}</span><span class="pl">${esc(s.label)}</span>${s.tag ? `<span class="pt">${esc(s.tag)}</span>` : ''}
    </button>`).join('<span class="pipe-arrow">‹</span>'));
}

// ---------- approval card (same API as the phone) ----------
function renderApproval() {
  const p = st.pending, la = st.last_approval;
  let html;
  if (p) {
    const pct = Math.max(0, Math.min(100, p.expires_in_s / p.timeout_s * 100));
    html = `
      <div class="ap-head"><span class="ap-pill">بانتظار موافقتك</span><span class="mono" dir="ltr">${p.expires_in_s}s</span></div>
      <div class="ap-title">${esc(p.title)}</div>
      <div class="ap-reason">${esc(p.reason)}</div>
      <div class="ap-bar"><i style="width:${pct}%"></i></div>
      <div class="ap-btns">
        <button class="btn-lime" data-act="approve" data-id="${p.id}">موافق</button>
        <button class="btn-ghost" data-act="reject" data-id="${p.id}">ارفض</button>
      </div>
      <div class="note">إذا خلصت المهلة بدون رد ← ما بصير إشي. السكوت مش موافقة.</div>`;
  } else {
    const msg = !la ? 'ما في طلبات. الوكيل بيطلب موافقتك قبل ما يطفي أي جهاز.'
      : { approved: `آخر طلب: وافقت ✓ (${esc(la.device_name || '')})`, rejected: `آخر طلب: رفضت ← ما صار إشي (${esc(la.device_name || '')})`,
          expired: 'آخر طلب: خلصت المهلة ← ما صار إشي', blocked: 'آخر طلب: حارس السياسات منع التنفيذ', cancelled: 'آخر طلب: انلغى' }[la.status] || '';
    html = `<div class="label">الموافقة</div><div class="ap-idle">${msg}</div>`;
  }
  WW.render($('p-approval'), html);
  $('p-approval').classList.toggle('hot', !!p);
}

// ---------- room / device panel ----------
function renderRoom() {
  const room = st.rooms.find(r => r.id === ui.room) || st.rooms.find(r => r.waste) || st.rooms[0];
  if (!room) return;
  const devs = st.devices.filter(d => d.room === room.id);
  const list = devs.map(d => {
    const locked = d.tier === 'T2';
    const status = locked ? 'ممنوع: جهاز حرج، محمي بالكود' : !d.allow ? 'حسّاس: بدّه تأكيد' : d.agent_off === 2 ? 'طفّاه الوكيل وتأكّد العدّاد' : d.agent_off === 1 ? 'طفّاه الوكيل، عم نتأكّد…' : '';
    return `
      <div class="dv${ui.device === d.id ? ' sel' : ''}" data-act="device" data-id="${esc(d.id)}">
        <div class="dv-ico${d.is_on ? ' on' : ''}">${icon(d.kind)}</div>
        <div class="dv-txt">
          <div class="dv-name">${esc(d.name)}</div>
          <div class="dv-sub"><span class="mono" dir="ltr">${d.is_on ? d.est_w + ' W' : '0 W'}</span> · بصمة <span class="mono" dir="ltr">${d.signature_w} W</span>${d.signature_measured ? ' (مقاسة)' : ' (تقدير)'}${d.setpoint != null ? ` · <span class="mono" dir="ltr">${fmt(d.setpoint, 0)}°</span>` : ''}</div>
          ${status ? `<div class="dv-st">${status}</div>` : ''}
        </div>
        <button class="switch${d.is_on ? ' on' : ''}${locked ? ' lock' : ''}" data-act="toggle" data-id="${esc(d.id)}" aria-label="${d.is_on ? 'طفّي' : 'شغّل'} ${esc(d.name)}"><i></i></button>
      </div>`;
  }).join('');
  const conf = ui.confirm && st.devices.find(d => d.id === ui.confirm);
  WW.render($('p-room'), `
    <div class="head"><div class="label">الغرفة</div><div class="room-name">${esc(room.name)}</div></div>
    <div class="conds">
      <div><span>الحركة (PIR)</span><b>${room.occupied == null ? '—' : room.occupied ? 'فيها حدا' : 'فاضية'}</b></div>
      <div><span>الحرارة</span><b class="mono" dir="ltr">${room.temp_c == null ? '—' : fmt(room.temp_c, 1) + '°C'}</b></div>
      <div><span>الإضاءة</span><b class="mono" dir="ltr">${room.light == null ? '—' : fmt(room.light, 0) + ' lx'}</b></div>
      <div><span>الشباك</span><b>${room.window_open == null ? '—' : room.window_open ? 'مفتوح' : 'مسكّر'}</b></div>
      <div><span>الاستهلاك</span><b class="mono" dir="ltr">${fmt(room.power_w, 0)} W</b></div>
      <div><span>حدود الراحة</span><b class="mono" dir="ltr">${st.comfort.min_c}–${st.comfort.max_c}°C</b></div>
    </div>
    ${conf ? `<div class="confirm">«${esc(conf.name)}» جهاز حسّاس. متأكد بدك تطفيه؟
      <div class="ap-btns"><button class="btn-amber" data-act="confirm-off" data-id="${esc(conf.id)}">طفّيه</button><button class="btn-ghost" data-act="confirm-cancel">لا</button></div></div>` : ''}
    <div class="dvs">${list || '<div class="note">ما في أجهزة بهالغرفة.</div>'}</div>
    <div class="note">أنت صاحب البيت: كبستك هي الموافقة، وبتنسجّل بسجل القرارات. الوكيل نفسه ما بيطفي إشي إلا بعد موافقتك.</div>`);
}

// ---------- NILM-lite: recognise the last step on the meter ----------
function lastStep() {
  const h = st.history || [];
  if (h.length < 6) return null;
  // Ignore normal meter noise: a real step must be clearly bigger than the usual wiggle.
  const diffs = h.slice(1).map((x, i) => Math.abs(x.power_w - h[i].power_w)).sort((a, b) => a - b);
  const noise = diffs[Math.floor(diffs.length / 2)] || 0;
  const minStep = Math.max(15, noise * 5);
  let best = null;
  for (let i = Math.max(2, h.length - 40); i < h.length - 1; i++) {
    const before = (h[i - 2].power_w + h[i - 1].power_w) / 2;
    const after = (h[i].power_w + h[i + 1].power_w) / 2;
    const d = after - before;
    if (Math.abs(d) >= minStep && (!best || Math.abs(d) > Math.abs(best.d) * 1.5 || i > best.i + 3 && Math.abs(d) > Math.abs(best.d) * 0.6)) best = { i, d };
  }
  if (!best) return null;
  // Closest known signature among devices whose state matches the direction of the step.
  const cands = st.devices.filter(x => (best.d < 0 ? !x.is_on : x.is_on) && x.signature_w > 0);
  let match = null;
  for (const x of cands) {
    const err = Math.abs(Math.abs(best.d) - x.signature_w) / x.signature_w;
    if (!match || err < match.err) match = { dev: x, err };
  }
  return { ...best, match: match && match.err < 0.35 ? match : null };
}

function renderPrint() {
  const h = st.history || [];
  if (h.length < 2) { WW.render($('p-print'), '<div class="label">بصمة الأجهزة</div><div class="note">عم نستنى قراءات العدّاد…</div>'); return; }
  const W = 300, H = 90;
  const vals = h.map(x => x.power_w);
  const lo = Math.min(...vals) * 0.95, hi = Math.max(...vals) * 1.05 + 1;
  const X = i => (i / (h.length - 1) * W).toFixed(1), Y = v => (H - (v - lo) / (hi - lo) * H).toFixed(1);
  const line = vals.map((v, i) => `${i ? 'L' : 'M'}${X(i)} ${Y(v)}`).join('');
  const s = lastStep();
  let mark = '', text = 'لما جهاز يشتغل أو يطفى، العدّاد بيعمل «درجة» بالواط. حجم الدرجة هو بصمة الجهاز.';
  if (s) {
    const x = X(s.i);
    mark = `<line x1="${x}" x2="${x}" y1="0" y2="${H}" class="pm-line"/><circle cx="${x}" cy="${Y(vals[s.i])}" r="4" class="pm-dot"/>`;
    const sign = s.d < 0 ? '−' : '+';
    text = s.match
      ? `آخر درجة: <b class="mono" dir="ltr">${sign}${Math.abs(Math.round(s.d))} W</b> ← بتطابق بصمة <b>${esc(s.match.dev.name)}</b> (<span class="mono" dir="ltr">${s.match.dev.signature_w} W</span>، فرق ${Math.round(s.match.err * 100)}٪). يعني ${s.d < 0 ? 'انطفى' : 'اشتغل'}.`
      : `آخر درجة: <b class="mono" dir="ltr">${sign}${Math.abs(Math.round(s.d))} W</b> ← ما بتطابق ولا بصمة معروفة. ممكن جهاز جديد أو غريب.`;
  }
  WW.render($('p-print'), `
    <div class="head"><div class="label">بصمة الأجهزة · NILM-lite</div><div class="note">عدّاد واحد للبيت كله</div></div>
    <svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${line}" class="sp-line"/>${mark}</svg>
    <div class="pm-text">${text}</div>`);
}

// ---------- guided tour: explains the whole process using the REAL system ----------
const GOAL_TEXT = 'خفّض استهلاك البيت ١٥٪ هالأسبوع بدون ما نكسر حدود الراحة';
const TOUR = [
  { t: 'هاد بيت رقمي (Digital Twin)', spot: ['#stage'], cam: () => scene3d.home(),
    body: () => `كل غرفة فيها حسّاسات (حركة، حرارة، إضاءة) وأجهزة. الخطوط المضيئة هي الكهربا طالعة من <b>عدّاد واحد</b> لكل جهاز شغّال، وكل ما زاد الاستهلاك بتسرع. ${st.source === 'simulator' ? 'هون البيانات اصطناعية من المحاكي، وبنفس الـ API تبع الجهاز الحقيقي.' : 'هون القراءات حقيقية من ESP32 والعدّاد PZEM.'}` },
  { t: '١ · بنعطي الوكيل هدف، مش سؤال', spot: ['#hud-agent', '.pipe'], cam: () => scene3d.home(),
    body: () => st.goal ? `الهدف الحالي: «${esc(st.goal.text)}». الوكيل قسّمه لحاله لـ${st.steps.length} خطوات، شوفها فوق.`
      : `اكبس الزر وبنعطيه هدف: «${GOAL_TEXT}». هو بيقسّمه لخطوات لحاله.`,
    action: () => !st.goal && { label: 'أعطِ الوكيل الهدف', run: () => WW.post('/goal', { text: GOAL_TEXT }) } },
  { t: '٢ · بيقرأ العدّاد والحسّاسات', spot: ['.pin.meter', '#hud-meter', '.pin.room'], cam: () => scene3d.focusPoint(scene3d.anchors.meter, 7),
    body: () => `العدّاد الآن: <b class="mono" dir="ltr">${fmt(st.meter.power_w, 0)} W</b>، فولتية <b class="mono" dir="ltr">${fmt(st.meter.voltage_v, 0)} V</b>. فوق كل غرفة: فيها حدا ولا لأ (حسّاس الحركة بيعطي بس فاضية/مشغولة، بدون كاميرات)، والحرارة، والاستهلاك.` },
  { t: '٣ · بيعرف كل جهاز من بصمته', spot: ['#p-print'], cam: () => scene3d.home(),
    body: () => `ما عنا عدّاد لكل جهاز. لما جهاز ينطفي، العدّاد بينزل «درجة». الوكيل بيقارن حجم الدرجة مع البصمات اللي تعلّمها وبيعرف مين الجهاز. هاد اسمه NILM.` },
  { t: '٤ · بيكشف الهدر', spot: () => [demoRoomSel(), '#p-room'], cam: () => scene3d.focusRoom(demoRoomId()),
    body: () => { const w = st.rooms.find(r => r.waste);
      return w ? `لقى هدر بـ<b>${esc(w.name)}</b>: فاضية وفي جهاز شغّال. لاحظ الغرفة صارت حمرا.`
        : st.source === 'simulator' ? 'اكبس الزر وبنعمل هدر: غرفة فاضية والمكيّف شغّال والشباك مفتوح. استنى ثواني والوكيل بيكتشفه.'
        : 'بالمختبر: غطّي حسّاس الحركة (الغرفة فاضية) والمروحة شغّالة، واستنى شوي.'; },
    action: () => st.source === 'simulator' && !st.pending && { label: 'اعمل هدر', run: () => WW.post('/scenario', { name: 'bedroom_empty_window' }) } },
  { t: '٥ · بيطلب موافقتك قبل أي إجراء', spot: ['#p-approval'], cam: () => scene3d.focusRoom(demoRoomId()),
    body: () => st.pending ? `هاي بطاقة الموافقة (نفسها بتطلع عالتلفون، والجهاز بيزمّر). <b>اكبس موافق أو ارفض بنفسك.</b> إذا رفضت أو سكتت ← ما بصير إشي.`
      : st.last_approval ? `آخر قرار: ${esc({ approved: 'وافقت', rejected: 'رفضت، فما صار إشي', expired: 'خلصت المهلة، فما صار إشي', blocked: 'حارس السياسات منعه', cancelled: 'انلغى' }[st.last_approval.status] || '')}.`
      : 'لسا ما في طلب. ارجع خطوة واعمل هدر، أو استنى الوكيل.' },
  { t: '٦ · الريليه بينفّذ والعدّاد بيتأكّد', spot: () => [pendingOrLastDevSel(), '#p-print', '.pin.meter'], cam: () => scene3d.focusRoom(demoRoomId()),
    body: () => { const s = lastStep(); const v = st.devices.find(d => d.agent_off === 2);
      return `بعد موافقتك، الوكيل بيبعت أمر للريليه، والجهاز بينطفي فعليًا (شوف الأنيميشن وقف والخط انطفى). بعدها بيقيس العدّاد: ${s && s.match ? `نزل <b class="mono" dir="ltr">${Math.abs(Math.round(s.d))} W</b> وطابق بصمة ${esc(s.match.dev.name)}.` : 'لازم يشوف نزول بحجم بصمة الجهاز.'} ${v ? `✓ ${esc(v.name)}: متأكّد بالعدّاد.` : ''}`; } },
  { t: '🚗 · شاحن السيارة الكهربائية', when: () => !!st.ev, spot: ['.pin.car', '.pin[data-pin^="dev:ev"]'],
    cam: () => scene3d.anchors.car && scene3d.focusPoint(scene3d.anchors.car, 8),
    body: () => { const e = st.ev;
      return e.charging
        ? `السيارة عم تشحن <b class="mono" dir="ltr">${fmt(e.power_w / 1000, 1)} kW</b>. الوكيل عرف إنه الشاحن من <b>البصمة</b>: درجة +${fmt((e.recognized_step_w || 0) / 1000, 1)} kW على العدّاد. البطارية ${Math.round(e.soc_pct || 0)}٪ ${e.minutes_to_target > 0 ? `وبدها ${Math.floor(e.minutes_to_target / 60)} س و ${e.minutes_to_target % 60} د لـ ${e.target_soc}٪.` : `ووصلت الهدف (${e.target_soc}٪).`} بيبعتلك إشعار لما يبلّش ولما يخلص (kWh والدنانير). وبالمسا إذا البيت قرّب من حد القاطع، بيقترح يأجّل الشحن لنص الليل، <b>بشرط</b> السيارة تكون جاهزة قبل ${esc(e.ready_by)}، وبيستنى موافقتك.`
        : `اكبس الزر: السيارة بتوصل والبطارية ٣٠٪ وبتنشبك عالشاحن (7.4 kW). شوف الكابل بيضوي والعدّاد بيقفز، والوكيل بيعرفها من بصمتها.`; },
    action: () => st.ev && !st.ev.charging && st.source === 'simulator' && { label: 'السيارة وصلت', run: () => WW.post('/scenario', { name: 'ev_arrives' }) } },
  { t: '٧ · التوفير مقاس، والأمان بالكود', spot: ['#hud-meter', '.chip.locked'], cam: () => scene3d.home(),
    body: () => `التوفير اللي بنعرضه بس اللي العدّاد قاسه: <b class="mono" dir="ltr">${fmt(st.savings.kwh, 2)} kWh</b> = <b class="mono" dir="ltr">${fmt(st.savings.jod, 3)} JD</b>. الأجهزة اللي عليها 🔒 (ثلاجة، إنذار حريق) ممنوع حدا يطفيها، والمنع مكتوب بالكود مش بالذكاء الاصطناعي. وزر الطوارئ بيرجّع كل إشي طبيعي.` },
];

function demoRoomId() {
  const pendDev = st.devices.find(d => d.id === pendingDeviceId());
  const w = st.rooms.find(r => r.waste);
  return pendDev ? pendDev.room : w ? w.id : (st.rooms.find(r => r.id === 'bedroom') || st.rooms.find(r => r.id === 'meeting') || st.rooms[0]).id;
}
function demoRoomSel() { return `.pin[data-pin="room:${demoRoomId()}"]`; }
function pendingOrLastDevSel() {
  const id = pendingDeviceId() || (st.devices.find(d => d.agent_off > 0) || {}).id;
  return id ? `.pin[data-pin="dev:${id}"]` : '.chip.on';
}

function renderTour() {
  if (TOUR[ui.tour].when && !TOUR[ui.tour].when()) { ui.tour = Math.min(TOUR.length - 1, ui.tour + 1); }
  const step = TOUR[ui.tour];
  const spots = typeof step.spot === 'function' ? step.spot() : step.spot;
  document.querySelectorAll('.spot').forEach(e => e.classList.remove('spot'));
  for (const sel of spots) document.querySelectorAll(sel).forEach(e => e.classList.add('spot'));
  document.body.classList.add('touring');
  if (ui.tourFocus !== ui.tour) { ui.tourFocus = ui.tour; if (step.cam) step.cam(); }
  const act = step.action && step.action();
  const dots = TOUR.map((_, i) => `<button class="td${i === ui.tour ? ' on' : ''}" data-act="tour-go" data-step="${i}" aria-label="خطوة ${i + 1}"></button>`).join('');
  WW.render($('tour'), `
    <div class="tour-card">
      <div class="tour-top"><div class="tour-dots">${dots}</div><button class="tour-x" data-act="tour-close" aria-label="سكّر">✕</button></div>
      <div class="tour-t">${step.t}</div>
      <div class="tour-b">${step.body()}</div>
      <div class="tour-btns">
        ${act ? `<button class="btn-lime" data-act="tour-do">${act.label}</button>` : ''}
        <span class="grow"></span>
        <button class="btn-ghost" data-act="tour-prev" ${ui.tour === 0 ? 'disabled' : ''}>السابق</button>
        <button class="btn-ghost" data-act="${ui.tour === TOUR.length - 1 ? 'tour-close' : 'tour-next'}">${ui.tour === TOUR.length - 1 ? 'خلصنا' : 'التالي'}</button>
      </div>
    </div>`);
  $('tour').hidden = false;
}
function closeTour() {
  ui.tour = null; ui.tourFocus = null;
  if (scene3d) scene3d.home();
  $('tour').hidden = true;
  document.body.classList.remove('touring');
  document.querySelectorAll('.spot').forEach(e => e.classList.remove('spot'));
}

// ---------- actions ----------
async function act(fn, ok) {
  if (ui.busy) return;
  ui.busy = true;
  try { await fn(); if (ok) toast(ok); await refresh(); }
  catch (e) {
    if (e.message === 'confirm_required') return;
    toast(e.message);
  } finally { ui.busy = false; }
}

WW.onAction({
  onError: e => toast(e.message),
  room: d => { ui.room = d.id; ui.device = null; update(); },
  device: d => { const dev = st.devices.find(x => x.id === d.id); ui.device = d.id; ui.room = dev && dev.room; update(); },
  meter: () => { ui.tour = 2; update(); },
  view: d => { ui.view = d.v; localSet('ww-house-view3', d.v); scene3d.setView(d.v); update(); },
  toggle: d => {
    const dev = st.devices.find(x => x.id === d.id);
    if (!dev) return;
    ui.device = dev.id; ui.room = dev.room;
    if (dev.sensitive && dev.is_on) { ui.confirm = dev.id; update(); return; }
    return act(() => WW.post(`/devices/${dev.id}/toggle`, { on: !dev.is_on }), `${dev.is_on ? 'طفّيت' : 'شغّلت'} ${dev.name}`);
  },
  'confirm-off': d => { ui.confirm = null; return act(() => WW.post(`/devices/${d.id}/toggle`, { on: false, confirmed: true })); },
  'confirm-cancel': () => { ui.confirm = null; update(); },
  approve: d => act(() => WW.post(`/approvals/${d.id}/approve`), 'وافقت ✓ الريليه عم ينفّذ'),
  reject: d => act(() => WW.post(`/approvals/${d.id}/reject`), 'رفضت ← ما صار إشي'),
  'tour-open': () => { ui.tour = 0; update(); },
  'tour-go': d => { ui.tour = Number(d.step); update(); },
  'tour-next': () => { ui.tour = Math.min(TOUR.length - 1, ui.tour + 1); update(); },
  'tour-prev': () => { ui.tour = Math.max(0, ui.tour - 1); update(); },
  'tour-close': () => closeTour(),
  'tour-do': () => { const a = TOUR[ui.tour].action && TOUR[ui.tour].action(); if (a) return act(a.run, 'تمام ✓'); },
});
document.addEventListener('keydown', ev => {
  if (ui.tour === null) return;
  if (ev.key === 'Escape') closeTour();
  if (ev.key === 'ArrowLeft') { ui.tour = Math.min(TOUR.length - 1, ui.tour + 1); update(); }
  if (ev.key === 'ArrowRight') { ui.tour = Math.max(0, ui.tour - 1); update(); }
});

// ---------- loop ----------
async function refresh() {
  try {
    st = await WW.getState();
  } catch (e) {
    $('site-sub').textContent = 'ما في اتصال بالسيرفر… بنحاول كمان مرة';
    return;
  }
  const sig = ($('scene').clientWidth < 600 ? 'n|' : 'w|') + st.rooms.map(r => r.id).join() + '|' + st.devices.map(d => d.id + d.room + d.kind).join();
  if (sig !== built) { built = sig; build(); }
  $('site-name').textContent = '· ' + st.site_name;
  $('site-sub').textContent = `${st.clock}${st.source === 'simulator' ? ' · محاكاة ×60' : ' · جهاز حقيقي'} · ${st.online ? 'متصل' : 'ما في قراءات (وضع آمن)'}`;
  update();
}

function initSites() {
  const SITES = [['home', 'البيت'], ['building', 'المبنى'], ['lab', 'المختبر']];
  $('site-seg').innerHTML = SITES.map(([k, l]) => `<a class="seg-b${k === WW.site ? ' sel' : ''}" href="house.html?site=${k}">${l}</a>`).join('');
  $('dash-link').href = 'index.html?site=' + encodeURIComponent(WW.site);
  $('back-link').href = $('dash-link').href;
}

initSites();
window.addEventListener('resize', () => {
  clearTimeout(refresh.t);   // rebuild when switching between phone and wide layouts
  refresh.t = setTimeout(() => { const n = $('scene').clientWidth < 600; if (n !== refresh.narrow) { refresh.narrow = n; built = ''; refresh(); } }, 250);
});
refresh.narrow = $('scene').clientWidth < 600;
refresh();
setInterval(refresh, 1000);
