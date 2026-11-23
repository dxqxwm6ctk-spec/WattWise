/* WattWise dashboard: polls the backend every second and renders the design. */

const { esc, fmt } = WW;
const $ = id => document.getElementById(id);

const SITE_SCALE = { home: { maxW: 4000, unit: 'kW' }, building: { maxW: 12000, unit: 'kW' }, lab: { maxW: 200, unit: 'W' } };
const scale = SITE_SCALE[WW.site] || SITE_SCALE.home;
const ui = {
  confirmId: null, goalText: 'أبقِ فاتورة هذا الشهر تحت 30 دينارًا دون إزعاج أحد في البيت',
  cmd: { text: '', res: null, busy: false, msg: '' }, listening: false,
  heater: { hint: '', res: null, busy: false, msg: '' },
  why: { res: null, busy: false }, rep: { text: '', busy: false },
  bill: { status: null, busy: false, res: null, msg: '', manual: false, kwh: '', days: '', amount: '' },
  teach: { room: null, text: '', busy: false, lastMsg: 0 },
};
let st = null;
const lbl = (key, fallback) => (st && st.labels && st.labels[key]) || fallback;
let chart = null;

const powerStr = w => scale.unit === 'kW' ? fmt((w || 0) / 1000, 2) : fmt(w, 0);

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove('show'), 3500);
}

// ---------------- sections ----------------

function toolbar() {
  const sim = st.source === 'simulator';
  const SITES = [['home', 'البيت'], ['building', 'المبنى (١٠ غرف)'], ['lab', 'المختبر']];
  const other = SITES.filter(([k]) => k !== WW.site)
    .map(([k, label]) => `<a class="tb link" href="index.html?site=${k}">← ${label}</a>`).join('');
  const scen = sim ? `
    <button class="tb" data-act="scenario" data-name="bedroom_empty_window">${esc(st.demo_label || '١ · غرفة فارغة والشباك مفتوح')}</button>
    <select class="tb ghost" id="scenario-pick" aria-label="سيناريوهات المحاكي">
      <option value="">سيناريوهات أخرى…</option>
      <option value="heat_wave">موجة حر</option>
      <option value="holiday">عطلة (البيت فارغ)</option>
      <option value="sensor_fault">عطل في الحسّاسات</option>
      <option value="unknown_load">حمل غريب (جهاز غير مسجّل)</option>
      <option value="ev_arrives">وصول السيارة الكهربائية وبدء الشحن</option>
      <option value="overload">حمل زائد (تيار قريب من الحد)</option>
      <option value="stranger_device">جهاز غريب ٦٠ واط في المطبخ (بلا بصمة)</option>
      <option value="normal">العودة إلى الوضع الطبيعي</option>
    </select>` : '';
  return `${other}${scen}
    <a class="tb ghost" href="stage.html?site=${WW.site}">شاشة العرض للحكّام</a>
    <a class="tb ghost" href="/api/sites/${WW.site}/report" target="_blank" rel="noopener">تقرير التوفير</a>
    <button class="tb ghost" data-act="reset">إعادة الضبط</button>
    <button class="tb stop" data-act="estop">إيقاف طوارئ</button>`;
}

function hero() {
  const w = st.meter.power_w || 0;
  const g = WW.gauge(w, scale.maxW);
  const ticks = Array.from({ length: 41 }, (_, i) => {
    const major = i % 10 === 0, mid = i % 5 === 0;
    const lit = i / 40 <= g.frac;
    const color = lit ? (major ? '#ECEBE4' : '#8E8C82') : (major ? '#5E5C55' : '#33352D');
    return `<div style="position:absolute;left:150px;top:150px;width:${major ? 2 : 1}px;height:${major ? 14 : mid ? 10 : 6}px;background:${color};transform-origin:0 0;transform:rotate(${-90 + i * 4.5}deg) translate(-50%,-118px)"></div>`;
  }).join('');
  const labels = [0, 1, 2, 3, 4].map(k => {
    const th = (-90 + k * 45) * Math.PI / 180;
    const t = scale.unit === 'kW' ? k * scale.maxW / 4000 : k * scale.maxW / 4;
    return `<span style="position:absolute;left:${(150 + 94 * Math.sin(th)).toFixed(1)}px;top:${(150 - 94 * Math.cos(th)).toFixed(1)}px;transform:translate(-50%,-50%);font-family:var(--mono);font-size:11px;color:#6F6D64">${t}</span>`;
  }).join('');
  const odo = WW.odometer(st.meter.energy_kwh).map((d, i) => `
    <div style="width:34px;height:48px;overflow:hidden;border-radius:6px;background:${i === 5 ? '#3A1712' : '#16170F'};box-shadow:inset 0 10px 10px -6px rgba(0,0,0,0.7), inset 0 -10px 10px -6px rgba(0,0,0,0.7)">
      <div style="display:flex;flex-direction:column;transform:translateY(${-d * 48}px);transition:transform .9s cubic-bezier(.45,.05,.2,1)">
        ${[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<span style="height:48px;display:grid;place-items:center;font-family:var(--mono);font-size:26px;font-weight:500;color:${i === 5 ? '#FF8A70' : '#ECEBE4'}">${n}</span>`).join('')}
      </div>
    </div>`).join('');
  const v = st.meter.voltage_v, a = st.meter.current_a, pf = st.meter.pf;
  const mini = [
    { label: 'الجهد', v: fmt(v, 1) + ' V', pct: v ? (v - 200) / 50 * 100 : 0 },
    { label: 'التيار', v: fmt(a, 2) + ' A', pct: a ? Math.min(100, a / 20 * 100) : 0 },
    // Power factor of the whole circuit: the jump in it tells a lamp from a fan (NILM).
    { label: 'معامل القدرة PF', v: fmt(pf, 2), pct: pf ? pf * 100 : 0 },
  ].map(m => `
    <div style="padding:10px;border-radius:12px;background:#181A15;display:flex;flex-direction:column;gap:6px">
      <span style="font-size:11px;color:#8E8C82">${m.label}</span>
      <span style="font-family:var(--mono);font-size:15px" dir="ltr">${m.v}</span>
      <div style="height:3px;border-radius:2px;background:#23251F;overflow:hidden"><div style="height:100%;width:${m.pct.toFixed(0)}%;background:#B8F04A;transition:width 1s cubic-bezier(.34,1.3,.64,1)"></div></div>
    </div>`).join('');

  const roomMax = scale.maxW * 0.6;
  const bars = st.rooms.map(r => {
    const val = r.power_w, hot = r.waste;
    const color = hot ? '#F2B544' : val > 0 ? '#B8F04A' : '#3A3C33';
    const base = hot ? '#5A4518' : val > 0 ? '#2E3A1C' : '#23251F';
    const label = val >= 1000 ? (val / 1000).toFixed(2) + 'k' : String(val);
    const h = Math.max(1.5, Math.min(100, val / roomMax * 100)).toFixed(1);
    return `
      <div style="flex:1;min-width:0;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px">
        <span style="font-family:var(--mono);font-size:11px;color:${color};transition:color .6s" dir="ltr">${label}</span>
        <div style="width:100%;max-width:38px;height:${h}%;min-height:3px;border-radius:8px 8px 2px 2px;background:linear-gradient(to top,${base},${color});transition:height 1.1s cubic-bezier(.34,1.35,.64,1), background .6s;position:relative">
          <div style="position:absolute;inset:-6px -4px auto -4px;height:10px;border-radius:50%;background:${color};filter:blur(8px);animation:ww-glow 2.4s ease-in-out infinite"></div>
        </div>
      </div>`;
  }).join('');
  const names = st.rooms.map(r => `<span style="flex:1;min-width:0;text-align:center;font-size:11px;color:#8E8C82;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.name)}</span>`).join('');

  return `
    <div style="flex:1 1 320px;min-width:0;display:flex;flex-direction:column;gap:6px;align-items:center">
      <div class="label" style="align-self:stretch;display:flex;justify-content:space-between"><span>الحمل الآن</span></div>
      <div style="position:relative;width:300px;height:190px">
        <div style="position:absolute;left:60px;top:60px;width:180px;height:180px;border-radius:50%;background:${g.color};filter:blur(60px);opacity:.18;transition:background .8s"></div>
        <svg width="300" height="170" viewBox="0 0 300 170" style="position:absolute;inset:0;overflow:visible">
          <path d="M 20 150 A 130 130 0 0 1 280 150" fill="none" stroke="#23251F" stroke-width="14" stroke-linecap="round"></path>
          <path d="M 20 150 A 130 130 0 0 1 280 150" fill="none" stroke="${g.color}" stroke-width="14" stroke-linecap="round" stroke-dasharray="408.4" stroke-dashoffset="${(408.4 * (1 - g.frac)).toFixed(1)}" style="transition:stroke-dashoffset 1.1s cubic-bezier(.34,1.25,.64,1), stroke .8s"></path>
        </svg>
        ${ticks}${labels}
        <div style="position:absolute;left:148.5px;top:42px;width:3px;height:108px;border-radius:2px;background:linear-gradient(to top,#ECEBE4,${g.color});transform-origin:50% 100%;transform:rotate(${g.needleDeg}deg);transition:transform 1.1s cubic-bezier(.34,1.45,.64,1)"></div>
        <div style="position:absolute;left:140px;top:140px;width:20px;height:20px;border-radius:50%;background:#0C0D0A;border:3px solid #ECEBE4"></div>
        <div style="position:absolute;left:0;right:0;top:162px;display:flex;justify-content:center;align-items:baseline;gap:6px" dir="ltr">
          <span style="font-family:var(--mono);font-size:26px;font-weight:500">${powerStr(w)}</span><span style="font-family:var(--mono);font-size:12px;color:#8E8C82">${scale.unit}</span>
        </div>
      </div>
    </div>
    <div style="flex:1 1 260px;min-width:0;display:flex;flex-direction:column;gap:14px;justify-content:center">
      <div class="label" style="display:flex;justify-content:space-between"><span>عدّاد الشهر</span></div>
      <div style="display:flex;justify-content:center;gap:4px;padding:12px;border-radius:14px;background:#0A0B08;border:1px solid #2A2C25;box-shadow:inset 0 6px 14px rgba(0,0,0,0.6)" dir="ltr">
        ${odo}<span style="align-self:flex-end;font-family:var(--mono);font-size:12px;color:#6F6D64;padding:0 0 4px 6px">kWh</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px">${mini}</div>
    </div>
    <div style="flex:1.3 1 320px;min-width:0;display:flex;flex-direction:column;gap:10px">
      <div class="label" style="display:flex;justify-content:space-between"><span>الاستهلاك حسب الغرفة</span></div>
      <div style="flex:1;min-height:190px;display:flex;align-items:flex-end;gap:10px;padding-top:8px;border-bottom:1px solid #2A2C25">${bars}</div>
      <div style="display:flex;gap:10px">${names}</div>
    </div>`;
}

function goal() {
  const ag = WW.agentLabel(st);
  const steps = WW.goalSteps(st).map(s => `
    <div style="display:flex;flex-direction:column;gap:8px;padding:12px;border-radius:12px;border:1px solid ${s.border};background:${s.bg}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-family:var(--mono);font-size:12px;color:${s.color}">${s.n}</span>
        <span style="font-size:11px;color:${s.color}">${s.tag}</span>
      </div>
      <div style="font-size:13.5px;line-height:1.45;color:${s.text}">${esc(s.label)}</div>
    </div>`).join('');
  const form = `<div class="goal-form">
      <input class="text" id="goal-text" value="${esc(ui.goalText)}" aria-label="اكتب هدفك بكلماتك"
        placeholder="مثلًا: أريد ألّا تتجاوز الفاتورة ٢٥ دينارًا دون أن يشعر أحد بفرق">
      <button class="btn-lime" data-act="set-goal">${st.goal ? 'غيّر الهدف' : 'حوّله إلى خطة'}</button>
    </div>`;
  let body;
  if (st.goal) {
    const t = st.goal.bill_target_jd;
    body = `<div style="font-size:clamp(20px,2.2vw,28px);font-weight:600;line-height:1.45;text-wrap:pretty">«${esc(st.goal.text)}»</div>
      ${t ? `<div class="muted">سقف الفاتورة: <span style="color:#B8F04A" class="mono">${fmt(t)} JD</span></div>` : ''}
      ${form}${planBox()}`;
  } else {
    body = form;
  }
  return `
    <div class="head">
      <div class="label">${esc(lbl('goal', 'الهدف'))}</div>
      <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:${ag.color}"><span style="width:8px;height:8px;border-radius:50%;background:${ag.color}"></span>${ag.label}</div>
    </div>
    ${body}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px">${steps}</div>
    ${anomalyBox()}
    ${brainLine()}`;
}

// The agent's own plan for this goal (from the LLM, or the rule-based template).
function planBox() {
  const p = st.plan;
  if (!p || !p.steps.length) return '';
  const by = p.by === 'llm' ? 'خطة من النموذج الذكي · تُنفَّذ عبر حارس السياسات' : 'خطة من القواعد · دون ذكاء اصطناعي';
  const tag = i => (p.tags || [])[i] === 'T1'
    ? '<span class="mono" style="font-size:11px;color:#F2B544;flex:none;min-width:92px">T1 · بموافقتك</span>'
    : '<span class="mono" style="font-size:11px;color:#B8F04A;flex:none;min-width:92px">T0 · تلقائي</span>';
  return `<div style="border-radius:14px;border:1px solid #2E3A1C;background:#121609;padding:14px 16px;display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;font-size:11.5px;color:#8E8C82"><span>خطة الوكيل</span><span>${by}</span></div>
      ${p.summary ? `<div style="font-size:14.5px;line-height:1.6;color:#ECEBE4">${esc(p.summary)}</div>` : ''}
      ${p.steps.map((x, i) => `<div style="display:flex;gap:10px;align-items:baseline;font-size:13px;line-height:1.55">${tag(i)}<span style="color:#D9D7CF">${esc(x)}</span></div>`).join('')}
    </div>`;
}

// AI layer 1: the meter reads something the known devices do not explain.
function anomalyBox() {
  const a = st.anomaly;
  if (!a) return '';
  if (!a.open) {
    const learning = a.ready ? 'كشف الشذوذ: الاستهلاك ضمن الطبيعي' : `كشف الشذوذ: نتعلّم النمط الطبيعي (${a.samples} قراءة)`;
    return `<div class="muted" style="font-size:12px">${learning}</div>`;
  }
  const what = a.kind === 'extra'
    ? `العدّاد ≈ <span class="mono">${a.power_w}</span> واط والمتوقع ≈ <span class="mono">${a.expected_w}</span> واط: زيادة ≈ <span class="mono">${a.residual_w}</span> واط مصدرها غير معروف.`
    : `العدّاد أقل من المتوقع بنحو <span class="mono">${-a.residual_w}</span> واط: ربما يوجد جهاز مفصول أو معطّل.`;
  return `<div style="border:1px solid #F2B544;background:rgba(242,181,68,.08);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px">
      <div style="color:#F2B544;font-weight:600;font-size:13.5px">⚠ استهلاك غير طبيعي (تنبيه فقط، لن نُطفئ شيئًا)</div>
      <div style="font-size:13.5px;line-height:1.6">${what}</div>
    </div>`;
}

// Which brain is planning right now, how much of the monthly LLM budget is used, and the weather.
function brainLine() {
  const b = st.agent.brain || {};
  const w = st.weather || {};
  const mode = b.mode === 'llm' ? `النموذج: <span class="mono">${esc(b.model || '')}</span>` : 'القواعد';
  const spend = b.model ? ` · التكلفة <span class="mono" dir="ltr">$${fmt(b.spent_usd, 2)} / $${fmt(b.budget_usd, 0)}</span> هذا الشهر` : '';
  const wx = w.available ? ` · في الخارج ${fmt(w.outdoor_temp_c, 1)}° (${esc(w.place || '')}، Open-Meteo)` : ' · الطقس: لا إنترنت، نكمل دونه';
  return `<div class="muted" style="font-size:12px;line-height:1.6" title="${esc(b.reason_ar || '')}">العقل: ${mode}${spend}${wx}</div>`;
}

function roomsMap() {
  const cards = st.rooms.map(r => {
    const hot = r.waste;
    const devs = st.devices.filter(d => d.room === r.id).map(d => `
      <div style="display:flex;align-items:center;gap:8px;font-size:13px">
        <span style="width:7px;height:7px;border-radius:50%;background:${d.is_on ? '#B8F04A' : '#4A4C44'};flex:none"></span>
        <span style="color:${d.is_on ? '#ECEBE4' : '#6F6D64'}">${esc(d.name)}</span>
        <span style="margin-inline-start:auto;font-family:var(--mono);font-size:11px;color:${d.tier === 'T2' ? '#E8553F' : '#6F6D64'}">${d.tier}</span>
      </div>`).join('');
    const occ = r.occupied === null ? '—' : r.occupied ? 'مشغولة' : 'فارغة';
    const contact = WW.site === 'lab' ? 'باب' : 'شباك';
    const win = r.window_open === null ? '' : `<span style="font-size:11.5px;padding:3px 9px;border-radius:10px;background:#1E201B;color:${r.window_open ? '#F2B544' : '#8E8C82'}">${contact} ${r.window_open ? 'مفتوح' : 'مغلق'} · محاكى</span>`;
    return `
      <div style="border-radius:16px;border:1px solid ${hot ? '#5A4518' : '#23251F'};background:${hot ? '#1E1A10' : '#181A15'};padding:16px;display:flex;flex-direction:column;gap:12px;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">
          <span style="font-size:16px;font-weight:600">${esc(r.name)}</span>
          <span style="font-family:var(--mono);font-size:15px;color:${hot ? '#F2B544' : '#ECEBE4'}" dir="ltr">${r.power_w}W</span>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          <span style="font-size:11.5px;padding:3px 9px;border-radius:10px;background:#1E201B;color:${r.occupied === false ? '#F2B544' : '#ECEBE4'}">${occ}</span>
          <span style="font-size:11.5px;padding:3px 9px;border-radius:10px;background:#1E201B;color:#D9D7CF" dir="ltr">${fmt(r.temp_c, 1)}°</span>
          ${win}
        </div>
        <div style="display:flex;flex-direction:column;gap:6px">${devs}</div>
      </div>`;
  }).join('');
  return `
    <div class="head">
      <div class="label">${esc(lbl('map', 'الغرف'))}</div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px">${cards}</div>`;
}

function devicesGrid() {
  const onCount = st.devices.filter(d => d.is_on).length;
  const confirmDev = st.devices.find(d => d.id === ui.confirmId);
  const confirm = confirmDev ? `
    <div style="border-radius:14px;border:1px solid #5A4518;background:#1E1A10;padding:16px;display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between">
      <div style="flex:1 1 300px;display:flex;flex-direction:column;gap:4px">
        <span style="font-size:15px;font-weight:600;color:#F2B544">هل تريد إطفاء ${esc(confirmDev.name)} فعلًا؟</span>
        <span style="font-size:13px;line-height:1.6;color:#D9D7CF">سينقطع تطبيق الموافقة على الهاتف، ويدخل الوكيل الوضع الآمن: لن يطلب موافقة ولن ينفّذ أي إجراء حتى يعود الاتصال.</span>
      </div>
      <div style="display:flex;gap:8px">
        <button data-act="confirm-cancel" class="tb ghost" style="height:40px">لا، اتركه</button>
        <button data-act="confirm-off" data-id="${esc(confirmDev.id)}" style="height:40px;white-space:nowrap;padding:0 16px;border-radius:10px;border:none;background:#F2B544;color:#0C0D0A;font-size:14px;font-weight:600;cursor:pointer">أطفئه</button>
      </div>
    </div>` : '';
  const learning = st.learn ? `<div style="border-radius:14px;border:1px dashed #4C6A20;background:#151A0F;padding:12px 16px;font-size:13px;color:#D9D7CF">تجري إضافة جهاز جديد من تطبيق الهاتف، فأكمل الخطوات هناك. سيُظهر العدّاد هنا بصمته أثناء القياس.</div>` : '';
  const cards = st.devices.map(d => {
    const on = d.is_on, locked = d.tier === 'T2';
    const state = locked ? 'محمي · يعمل دائمًا' : on ? 'يعمل' : 'مطفأ';
    const note = (d.added ? 'جديد · ' : '') + (locked ? 'T2 · ممنوع برمجيًا' : d.sensitive ? 'حساس · إطفاؤه يقطع تطبيق الموافقة' : !d.allow ? 'يدوي فقط · لا يقترحه الوكيل' : 'T1 · تحكم يدوي')
      + (d.agent_off ? ' · أطفأه الوكيل بموافقتك' : '');
    const ac = '';   // on/off only: the AC set temperature is not controlled from the UI
    return `
      <div style="border-radius:14px;border:1px solid ${locked ? '#3A2A26' : on ? '#2E3A1C' : '#23251F'};background:#181A15;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0">
        <div style="display:flex;align-items:flex-start;gap:10px">
          <div style="flex:1;display:flex;flex-direction:column;gap:2px;min-width:0">
            <span style="font-size:14.5px;font-weight:600">${esc(d.name)}</span>
            <span style="font-size:11.5px;color:#8E8C82">${esc(d.room_name)} · ${state}</span>
          </div>
          <button data-act="toggle" data-id="${esc(d.id)}" aria-label="${esc(d.name)}" style="width:48px;height:28px;border-radius:14px;border:none;background:${locked ? '#3A2A26' : on ? '#3D5418' : '#2A2C25'};position:relative;cursor:pointer;flex:none;padding:0">
            <span style="position:absolute;top:4px;${on ? 'left' : 'right'}:4px;width:20px;height:20px;border-radius:50%;background:${locked ? '#E8553F' : on ? '#B8F04A' : '#6F6D64'}"></span>
          </button>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          <span style="font-family:var(--mono);font-size:13px;color:${on ? '#ECEBE4' : '#5E5C55'}" dir="ltr">${d.est_w} W${d.signature_pf != null ? ` · PF ${Number(d.signature_pf).toFixed(2)}` : ''}</span>
          ${ac}
        </div>
        ${d.plug ? `<span style="font-size:11px;color:${d.plug.online ? '#9CC85A' : '#E8553F'}">🔌 ${d.plug.simulated && d.plug.model ? esc(d.plug.model) : esc(d.plug.brand_name) + (d.plug.model ? ' · ' + esc(d.plug.model) : '')} · ${d.plug.online ? (d.plug.meters ? 'القراءة من المقبس نفسه' : 'تشغيل وإطفاء فقط') : 'المقبس غير متصل'}</span>` : ''}
        <span style="font-size:11px;color:#6F6D64">${note}</span>
      </div>`;
  }).join('');
  return `
    <div class="head">
      <div class="label">الأجهزة</div>
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:12px;color:#8E8C82">يعمل ${onCount} من ${st.devices.length}</span>
        <button class="btn-lime" data-act="open-plug" style="height:34px;font-size:13px">🔌 + مقبس ذكي</button>
        <button class="tb ghost" data-act="open-wiz" style="height:34px;font-size:13px">+ جهاز عبر العدّاد</button>
      </div>
    </div>
    ${learning}${confirm}${commandBar()}
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px">${cards}</div>`;
}

// Typed or spoken orders. The server understands them, the Policy Guard checks each
// action, and NOTHING runs until the user presses "yes".
const micOk = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
function commandBar() {
  const c = ui.cmd, r = c.res;
  let result = '';
  if (r) {
    const items = r.items.map(i => `<div style="display:flex;gap:10px;align-items:baseline;font-size:13.5px">
        <span style="font-weight:700;color:${i.ok ? '#B8F04A' : '#E8553F'}">${i.ok ? '✓' : '✕'}</span>
        <span style="color:#D9D7CF">${esc(i.label)}</span><span style="color:#A9A79D;font-size:12px">${esc(i.why)}</span></div>`).join('');
    const canRun = r.items.some(i => i.ok);
    result = `<div style="display:flex;flex-direction:column;gap:8px">
        <span style="font-size:14px;line-height:1.6;color:#ECEBE4">${esc(r.clarify || r.reply)}</span>${items}
        <span style="font-size:11.5px;color:#A9A79D">فُهم الأمر بالقواعد (دون ذكاء اصطناعي)، وفحص حارس السياسات كل إجراء.</span>
        <div style="display:flex;gap:8px">
          ${canRun ? '<button class="btn-lime" style="height:38px;font-size:13px" data-act="cmd-run">نعم، نفّذ</button>' : ''}
          <button class="btn-ghost" data-act="cmd-cancel">لا</button>
        </div></div>`;
  }
  return `<div class="cmd-box">
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <input class="field grow" id="cmd-text" value="${esc(c.text)}" aria-label="تحدّث أو اكتب أمرك للوكيل"
          placeholder="مثلًا: أطفئ مكيّف غرفة النوم، شغّل إنارة الصالون، أطفئ المكيّف بعد نصف ساعة">
        ${micOk ? `<button class="mic${ui.listening ? ' on' : ''}" data-act="cmd-mic" aria-label="${ui.listening ? 'أستمع إليك، اضغط للإيقاف' : 'تحدّث'}">🎤</button>` : ''}
        <button class="btn-lime" style="height:42px" data-act="cmd-parse">${c.busy ? 'جارٍ الفهم…' : 'نفّذ'}</button>
      </div>${result}
      ${c.msg ? `<span style="font-size:13px;color:#B8F04A">${esc(c.msg)}</span>` : ''}
    </div>`;
}

let recog = null;
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  if (recog) { try { recog.stop(); } catch (e) { /* already stopped */ } return; }
  recog = new SR();
  recog.lang = 'ar-JO'; recog.interimResults = false; recog.maxAlternatives = 1;
  recog.onresult = e => { ui.cmd.text = e.results[0][0].transcript; parseCommand(); };
  recog.onerror = () => toast('الميكروفون غير متاح هنا. اكتب الأمر بدلًا من ذلك.');
  recog.onend = () => { recog = null; ui.listening = false; renderAll(); };
  ui.listening = true; renderAll();
  try { recog.start(); } catch (e) { recog = null; ui.listening = false; }
}

async function parseCommand() {
  const text = ui.cmd.text.trim();
  if (!text || ui.cmd.busy) return;
  ui.cmd.busy = true; ui.cmd.msg = ''; renderAll();
  try { ui.cmd.res = await WW.post('/command/parse', { text }); } catch (e) { toast(e.message); }
  ui.cmd.busy = false; renderAll();
}

// Timers and daily schedules (on/off only), and the smart water-heater schedule.
const estText = e => e ? `≈ ${fmt(e.kwh, 1)} ك.و.س/يوم · ≈ ${fmt(e.jod, 2)} دينار/يوم (تقديري، غير مُقاس)` : '';

function heaterPanel() {
  const h = ui.heater, hr = h.res;
  const hasHeater = st.devices.some(d => d.kind === 'heater' && d.tier === 'T1' && !d.sensitive);
  if (!hasHeater) return '';
  const proposal = !hr ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <span style="font-size:14px;line-height:1.6;color:#ECEBE4">${esc(hr.reply)}</span>
      ${hr.items.map(i => `<div class="sub-box"><span class="mono" style="font-size:13px" dir="ltr">${esc(i.on_time)} → ${esc(i.off_time)}</span>
        <span style="font-size:12.5px;color:#D9D7CF">${esc(i.why)}</span><span style="font-size:11.5px;color:#A9A79D">${estText(i.estimate)}</span></div>`).join('')}
      <span style="font-size:12.5px;color:#C8E68A">المجموع ≈ ${fmt(hr.total.kwh, 1)} ك.و.س يوميًا ≈ ${fmt(hr.total.jod, 2)} دينار (تقديري، غير مُقاس)</span>
      <div style="display:flex;gap:8px">
        ${hr.items.length ? '<button class="btn-lime" style="height:38px;font-size:13px" data-act="heater-apply">نعم، اعتمده</button>' : ''}
        <button class="btn-ghost" data-act="heater-cancel">لا</button>
      </div></div>`;
  return `<div class="panel green">
      <span class="panel-title">سخّان الماء الذكي</span>
      <input class="field" id="heater-hint" value="${esc(h.hint)}" aria-label="متى تستحمّون؟" placeholder="متى تستحمّون؟ مثلًا: الصباح ٦:٣٠ والمساء ٩">
      <button class="btn-lime" data-act="heater-suggest">${h.busy ? 'جارٍ التخطيط…' : 'اقترح جدولًا للسخّان'}</button>
      ${proposal}
      ${h.msg ? `<span style="font-size:13px;line-height:1.6;color:#B8F04A">${esc(h.msg)}</span>` : ''}
    </div>`;
}

// Rooms and devices of Home / Building / Lab, with detailed schedules (js/schedule.js).
function schedSection() {
  const heater = WWSched.state.site === WW.site ? heaterPanel() : '';
  return `
    <div class="head">
      <div class="label">جدولة الأجهزة</div>
    </div>
    ${WWSched.render({ theme: 'dark', layout: 'side' })}
    ${heater ? `<div style="display:flex;flex-wrap:wrap;gap:12px">${heater}</div>` : ''}`;
}

// Teach mode: the AI learns the room's appliances from the meter and asks the user.
function teachSection() {
  const t = st.teach || { messages: [], fingerprints: [], unknown: [] };
  const s = t.session;
  if (!ui.teach.room || !st.rooms.some(r => r.id === ui.teach.room)) ui.teach.room = st.rooms[0] && st.rooms[0].id;
  const room = s ? s.room : ui.teach.room;
  const chips = st.rooms.map(r => `<button class="chip ${r.id === room ? 'sel' : ''}" data-act="teach-room" data-id="${esc(r.id)}"${s ? ' disabled' : ''}>${esc(r.name)}</button>`).join('');
  const status = !s ? 'جاهز. اختر الغرفة واضغط «علّمني».'
    : s.status === 'listening' ? `أستمع إلى العدّاد على قاطع ${esc(s.room_name)}… (${s.candidates} جهاز حتى الآن)`
      : s.status === 'asking' ? 'بانتظار تأكيدك أو تصحيحك.' : 'بانتظار موافقتك على الحفظ.';
  const buttons = !s
    ? `<button class="btn-lime" style="height:36px;font-size:13px" data-act="teach-start">علّمني أجهزة هذه الغرفة</button>`
    : `${s.status === 'listening' ? '<button class="btn-lime" style="height:36px;font-size:13px" data-act="teach-done">انتهيت</button>' : ''}
       <button class="btn-ghost" data-act="teach-cancel">إيقاف دون حفظ</button>`;
  const msgs = t.messages.map(m => `
    <div style="align-self:${m.role === 'ai' ? 'flex-start' : 'flex-end'};max-width:88%;white-space:pre-wrap;font-size:13.5px;line-height:1.6;padding:9px 12px;border-radius:12px;
      background:${m.role === 'ai' ? '#1E201B' : '#2E3A1C'};color:${m.role === 'ai' ? '#ECEBE4' : '#E6F5C8'}">${esc(m.text)}</div>`).join('')
    || '<div style="font-size:12.5px;color:#6F6D64">لا توجد محادثة بعد.</div>';
  const quick = t.waiting_for === 'teach_confirm' ? ['صحيح'] : ['teach_save', 'label_save'].includes(t.waiting_for) ? ['احفظ', 'لا'] : t.waiting_for === 'label' ? ['تجاهل'] : [];
  const fps = t.fingerprints.map(f => `
    <div style="display:flex;align-items:center;gap:8px;font-size:13px">
      <span style="width:7px;height:7px;border-radius:50%;background:${f.is_on ? '#B8F04A' : '#4A4C44'};flex:none"></span>
      <span>${esc(f.name)}</span><span style="color:#8E8C82;font-size:12px">${esc(f.room_name)}</span>
      <span class="mono" style="margin-inline-start:auto;font-size:11.5px;color:#A9A79D" dir="ltr">${fmt(f.watts, 0)}W${f.pf != null ? ' · pf ' + fmt(f.pf, 2) : ''}</span>
      <button class="btn-ghost btn-sm" data-act="fp-del" data-id="${f.id}" title="احذف البصمة">×</button>
    </div>`).join('') || '<div style="font-size:12.5px;color:#6F6D64">لا توجد بصمات محفوظة. لا تُحفظ البصمة إلا بموافقتك.</div>';
  const unk = t.unknown.length ? `<span style="font-size:12px;padding:3px 10px;border-radius:10px;background:#1E1A10;color:#F2B544">⚠️ ${t.unknown.length} جهاز مجهول</span>` : '';
  return `
    <div class="head">
      <div class="label">تعريف الأجهزة</div>
      <div style="display:flex;gap:8px;align-items:center">${unk}</div>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:stretch">
      <div class="panel" style="flex:1 1 260px">
        <span class="panel-title">١ · أين العدّاد؟</span>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${chips}</div>
        <div style="font-size:12.5px;color:#A9A79D;line-height:1.6">${status}</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">${buttons}</div>
        <span class="panel-title" style="margin-top:6px">البصمات المحفوظة</span>
        <div style="display:flex;flex-direction:column;gap:8px">${fps}</div>
      </div>
      <div class="panel" style="flex:2 1 380px">
        <span class="panel-title">٢ · المحادثة مع الذكاء الاصطناعي</span>
        <div id="teach-chat" style="display:flex;flex-direction:column;gap:8px;max-height:320px;overflow:auto;padding:4px">${msgs}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${quick.map(q => `<button class="chip" data-act="teach-quick" data-text="${esc(q)}">${esc(q)}</button>`).join('')}</div>
        <div style="display:flex;gap:8px">
          <input class="field grow" id="teach-text" placeholder="اكتب ردّك… مثلًا: الأول لابتوب، الثاني مصباح المكتب" value="${esc(ui.teach.text)}">
          <button class="btn-lime" data-act="teach-send">${ui.teach.busy ? '…' : 'إرسال'}</button>
        </div>
      </div>
    </div>`;
}

async function teachSay(text) {
  text = (text || '').trim();
  if (!text || ui.teach.busy) return;
  ui.teach.busy = true; renderAll();
  try {
    await WW.post('/teach/say', { text });
    ui.teach.text = '';
    const el = $('teach-text'); if (el) el.value = '';
  } catch (e) { toast(e.message); }
  ui.teach.busy = false;
  refresh();
}

// "Why is my bill like this?" and the weekly report. Numbers come from the code.
function analystSection() {
  const w = ui.why.res, rep = ui.rep;
  const why = !w ? '' : `<div style="display:flex;flex-direction:column;gap:10px">
      <div style="font-size:14px;line-height:1.6;color:#ECEBE4">${esc(w.headline)}</div>
      ${w.causes.map(c => `<div class="sub-box"><span style="font-size:13.5px;color:#D9D7CF">${esc(c.what)}</span><span style="font-size:12px;line-height:1.55;color:#A9A79D">${esc(c.evidence)}</span></div>`).join('')}
      <div style="font-size:13.5px;line-height:1.6;color:#C8E68A">${esc(w.action)}</div>
      <div style="font-size:11.5px;color:#A9A79D">${esc(w.note)}</div></div>`;
  const report = !rep.text ? '' : `<div class="report-text">${esc(rep.text)}</div>
      <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
        <a class="btn-ghost" style="display:inline-flex;align-items:center;text-decoration:none;color:#B8F04A;border-color:#4C6A20" href="/api/sites/${WW.site}/weekly.txt" download>تنزيل الملف</a>
        <a class="btn-ghost" style="display:inline-flex;align-items:center;text-decoration:none" href="/api/sites/${WW.site}/report" target="_blank" rel="noopener">تقرير التوفير للطباعة (PDF)</a>
      </div>`;
  return `
    <div class="head">
      <div class="label">الفاتورة والتقارير</div>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:stretch">
      <div class="panel">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <span class="panel-title">لماذا الفاتورة بهذا المبلغ؟</span>
          <button class="btn-lime" style="height:36px;font-size:13px" data-act="why">${ui.why.busy ? 'جارٍ التحليل…' : w ? 'أعد التحليل' : 'لماذا الفاتورة بهذا المبلغ؟'}</button>
        </div>${why}
      </div>
      <div class="panel">${billPanel()}</div>
      <div class="panel">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <span class="panel-title">التقرير الأسبوعي</span>
          <button class="btn-lime" style="height:36px;font-size:13px" data-act="report">${rep.busy ? 'جارٍ التجهيز…' : rep.text ? 'جهّز تقريرًا جديدًا' : 'جهّز التقرير الأسبوعي'}</button>
        </div>${report}
      </div>
    </div>`;
}

// Bill photo: Claude reads it (when there is a key), the code checks it. Or type 3 numbers by hand.
function billPanel() {
  const b = ui.bill, r = b.res, noPhoto = b.status && !b.status.photo;
  const inp = 'height:38px;border-radius:10px;border:1px solid #3A3C33;background:#0F100D;color:#ECEBE4;padding:0 10px;font-family:inherit;font-size:14px;min-width:0;flex:1 1 90px';
  const bn = r && r.bill;
  const nums = !bn ? '' : [
    bn.kwh != null && `${fmt(bn.kwh, 0)} ك.و.س`, bn.days && `${bn.days} يوم`,
    bn.amount_jod != null && `${fmt(bn.amount_jod, 2)} دينار`,
    bn.period_from && bn.period_to && `${bn.period_from} ← ${bn.period_to}`,
  ].filter(Boolean).map(x => `<span class="mono" style="padding:4px 10px;border-radius:999px;background:#1E201B;font-size:12px;color:#D9D7CF">${esc(x)}</span>`).join('');
  const result = !r ? '' : `<div style="display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;flex-wrap:wrap;gap:6px">${nums}</div>
      ${r.explanation.map(x => `<div style="font-size:13.5px;line-height:1.65;color:#ECEBE4">${esc(x)}</div>`).join('')}
      ${r.checks.map(x => `<div class="sub-box"><span style="font-size:12.5px;line-height:1.55;color:#D9D7CF">${esc(x)}</span></div>`).join('')}
      ${r.ideas.map(x => `<div style="font-size:13px;line-height:1.6;color:#C8E68A">• ${esc(x)}</div>`).join('')}
      <div style="font-size:11.5px;color:#A9A79D">${esc(r.note)}</div></div>`;
  const manual = !(b.manual || noPhoto) ? '' : `<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
      <input id="bill-kwh" inputmode="decimal" value="${esc(b.kwh)}" placeholder="ك.و.س" aria-label="الاستهلاك بالكيلوواط ساعة" style="${inp}">
      <input id="bill-days" inputmode="numeric" value="${esc(b.days)}" placeholder="عدد الأيام" aria-label="عدد أيام الفاتورة" style="${inp}">
      <input id="bill-amount" inputmode="decimal" value="${esc(b.amount)}" placeholder="المبلغ (دينار)" aria-label="مبلغ الفاتورة بالدينار" style="${inp}">
      <button class="btn-lime" style="height:38px;font-size:13px" data-act="bill-manual">حلّل الأرقام</button></div>`;
  return `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="panel-title">حلّل صورة الفاتورة</span>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <label class="btn-lime" style="height:36px;font-size:13px;display:inline-flex;align-items:center;cursor:pointer;${noPhoto ? 'opacity:.5;pointer-events:none' : ''}">
          ${b.busy ? 'جارٍ القراءة…' : '📷 ارفع صورة'}<input id="bill-file" type="file" accept="image/*" hidden></label>
        <button class="btn-ghost" style="height:36px" data-act="bill-toggle-manual">أدخل الأرقام يدويًا</button>
      </div>
    </div>
    ${noPhoto ? `<div style="font-size:12px;line-height:1.55;color:#F2B544">${esc(b.status.reason_ar)}</div>` : ''}
    ${b.msg ? `<div style="font-size:12.5px;line-height:1.55;color:#F2B544">${esc(b.msg)}</div>` : ''}
    ${manual}${result}`;
}

async function billSend(promise) {
  ui.bill.busy = true; ui.bill.msg = ''; renderAll();
  try {
    const r = await promise;
    if (r.needs_manual) { ui.bill.manual = true; ui.bill.msg = r.message; }
    else ui.bill.res = r;
  } catch (e) { ui.bill.msg = e.message; }
  ui.bill.busy = false; renderAll();
}

// AI layer 2: expected load for this hour and the next 5, plus our measured accuracy.
function forecastBlock() {
  const f = st.forecast;
  if (!f) return '';
  const max = Math.max(...f.steps.map(x => x.power_w), 1);
  const bars = f.steps.map(x => `
    <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px">
      <span class="mono" style="font-size:10.5px;color:#D9D7CF">${fmt(x.power_w / 1000, 1)}</span>
      <div style="width:100%;height:${Math.max(4, x.power_w / max * 54)}px;border-radius:4px;background:${x.method === 'now' ? '#3A3C34' : '#6B8F2A'}"></div>
      <span class="mono" style="font-size:10.5px;color:#8E8C82">${x.hour}</span>
    </div>`).join('');
  const a = f.accuracy;
  const acc = a.hours ? `الدقة: خطأ ≈ ${fmt(a.mean_err_pct, 0)}% (آخر ${a.hours} ساعة، مقارنة بالعدّاد)` : 'الدقة: تُقاس بعد أول ساعة كاملة';
  return `<div style="display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#8E8C82"><span>توقّع الساعات الـ${f.steps.length} القادمة (kW)</span>
        <span dir="ltr" class="mono" style="color:#D9D7CF">${fmt(f.kwh, 1)} kWh ≈ ${fmt(f.jod, 2)} JD</span></div>
      <div style="display:flex;align-items:flex-end;gap:6px;height:86px">${bars}</div>
      <div style="font-size:11.5px;color:#8E8C82">${acc}${f.profile_hours ? '' : ' · لا يوجد سجل يومي بعد، لذا التوقّع = الاستهلاك الحالي'}</div>
    </div>`;
}

// M&V: savings against the baseline model (only shown when the model passes).
function mvLine() {
  const m = st.mv;
  if (!m) return '';
  const q = m.model ? ` · CV(RMSE) ${fmt(m.model.cv_rmse_pct, 1)}%` : '';
  const color = m.status === 'ok' ? (m.saved_kwh >= 0 ? '#B8F04A' : '#F2B544') : '#8E8C82';
  return `<div style="font-size:12.5px;line-height:1.6;color:${color}">M&amp;V: ${esc(m.message_ar)}<span style="color:#8E8C82">${q}</span></div>`;
}

function bill() {
  const b = st.bill, s = st.savings;
  const goalJd = st.goal && st.goal.bill_target_jd;
  const projColor = goalJd && b.bill_projected > goalJd ? '#F2B544' : '#B8F04A';
  const shades = b.type === 'unsub' ? ['#6B5A1E', '#6A2A1E'] : ['#3D5418', '#6B5A1E', '#6A2A1E'];
  const segs = b.segments.map((t, i) => `<div style="width:${t.width_pct}%;background:${shades[i] || '#6A2A1E'};border-left:1px solid #131411"></div>`).join('');
  const segLabels = b.segments.map(t => `<span style="width:${t.width_pct}%;font-size:11px;color:#8E8C82;font-family:var(--mono)">${t.fils} فلس</span>`).join('');
  const opts = b.types.map(o => `<button data-act="tariff" data-type="${o.key}" style="height:28px;white-space:nowrap;padding:0 10px;border-radius:8px;border:none;background:${b.type === o.key ? '#B8F04A' : 'transparent'};color:${b.type === o.key ? '#0C0D0A' : '#D9D7CF'};font-size:12px;font-weight:600;cursor:pointer">${esc(o.label)}</button>`).join('');
  return `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
      <div class="label">الفاتورة</div>
      <div style="display:flex;padding:3px;border-radius:10px;background:#1B1D17;gap:2px">${opts}</div>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px">
      <span style="font-size:12px;color:#8E8C82">حتى اليوم · ${fmt(b.kwh_now)} ك.و.س</span>
      <span style="font-family:var(--mono);font-size:34px;font-weight:500" dir="ltr">${fmt(b.bill_now, 2)} <span style="font-size:15px;color:#8E8C82">JD</span></span>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px">
      <div style="position:relative;height:30px">
        <div style="position:absolute;inset:8px 0 auto 0;height:14px;border-radius:7px;overflow:hidden;display:flex">${segs}</div>
        <div style="position:absolute;top:2px;right:${b.now_pos}%;width:3px;height:26px;border-radius:2px;background:#ECEBE4;transition:right 1s"></div>
        <div style="position:absolute;top:2px;right:${b.proj_pos}%;width:3px;height:26px;border-radius:2px;background:${projColor};transition:right 1s"></div>
      </div>
      <div style="display:flex">${segLabels}</div>
      <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:11.5px;color:#8E8C82">
        <span style="display:flex;align-items:center;gap:6px"><span style="width:3px;height:12px;background:#ECEBE4"></span>الآن</span>
        <span style="display:flex;align-items:center;gap:6px"><span style="width:3px;height:12px;background:${projColor}"></span>متوقّع آخر الشهر ${fmt(b.projected_kwh)} ك.و.س ≈ ${fmt(b.bill_projected, 1)} JD</span>
      </div>
    </div>
    <div style="font-size:13px;line-height:1.6;color:#D9D7CF;padding:10px 12px;border-radius:10px;background:#181A15">${esc(b.message)}</div>
    ${forecastBlock()}
    ${mvLine()}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;padding-top:6px;border-top:1px solid #1E201B">
      <div style="display:flex;flex-direction:column;gap:4px"><span style="font-family:var(--mono);font-size:20px;color:#B8F04A" dir="ltr">${fmt(s.jod, 3)}</span><span style="font-size:11.5px;color:#8E8C82">دينار مُوفَّر (مُقاس · بسعر شريحتك)</span></div>
      <div style="display:flex;flex-direction:column;gap:4px"><span style="font-family:var(--mono);font-size:20px" dir="ltr">${fmt(s.kwh, 2)}</span><span style="font-size:11.5px;color:#8E8C82">ك.و.س · ${s.co2_kg === null ? '—' : fmt(s.co2_kg, 2)} كغ CO₂</span></div>
    </div>
    `;
}

// Warnings from the agent (the same ones the phone app shows as notifications).
function alertsSection() {
  const al = st.alerts || { items: [] };
  const col = l => ({ danger: '#E8553F', warn: '#F2B544' }[l] || '#8FC7FF');
  const rows = al.items.map(a => {
    const off = !a.active || a.user_state;
    const status = !a.active ? 'انتهى' : a.user_state === 'acted' ? 'أُرسل طلب موافقة' : a.user_state === 'dismissed' ? 'تم التجاهل' : '';
    return `<div style="display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 0;border-top:1px solid #1E201B;opacity:${off ? 0.55 : 1}">
      <span style="font-family:var(--mono);font-size:12px;color:#6F6D64" dir="ltr">${esc(a.clock)}</span>
      <div style="display:flex;flex-direction:column;gap:2px">
        <span style="font-size:14px;font-weight:600;color:${col(a.level)}">${esc(a.title)}</span>
        <span style="font-size:13px;line-height:1.55;color:#D9D7CF">${esc(a.body)}</span>
      </div>
      <div style="display:flex;gap:6px;align-items:center">
        ${status ? `<span class="muted" style="font-size:11.5px">${status}</span>` : ''}
        ${a.can_act ? `<button class="btn-lime" style="height:34px" data-act="alert-act" data-id="${a.id}">أطفئه؟</button>` : ''}
        ${a.active && !a.user_state ? `<button class="tb ghost" style="height:34px" data-act="alert-dismiss" data-id="${a.id}">تجاهل</button>` : ''}
      </div>
    </div>`;
  }).join('') || '<div class="muted">لا توجد تنبيهات. كل شيء طبيعي.</div>';
  const perm = ('Notification' in window) && Notification.permission === 'default'
    ? '<button class="tb ghost" style="height:32px" data-act="alert-perm">فعّل إشعارات المتصفح</button>' : '';
  return `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
      <div class="label">التنبيهات</div>
      <div style="display:flex;gap:8px;align-items:center">${perm}</div>
    </div>${rows}`;
}

// New warnings: a toast on the page, and a browser notification when allowed
// (browsers allow it on localhost or https; the phone app uses its own notifications).
let lastAlertId = null;
function notifyNewAlerts() {
  const al = st.alerts;
  if (!al) return;
  if (lastAlertId === null) { lastAlertId = al.last_id; return; }   // not for old ones on page load
  const fresh = al.items.filter(a => a.id > lastAlertId && a.active).reverse();
  lastAlertId = Math.max(lastAlertId, al.last_id);
  for (const a of fresh) {
    toast(`${a.title} · ${a.body}`);
    if ('Notification' in window && Notification.permission === 'granted') {
      try { new Notification('WattWise · ' + a.title, { body: a.body, tag: 'ww-alert-' + a.id, icon: 'icon.svg' }); } catch (e) { /* not supported here */ }
    }
  }
}

function auditLog() {
  const color = t => ({ T1: '#F2B544', STOP: '#E8553F', OK: '#B8F04A', MANUAL: '#8FC7FF', SCHED: '#8FC7FF', T2: '#E8553F' }[t] || '#8E8C82');
  const tierLabel = t => t === 'MANUAL' ? 'يدوي' : t === 'SCHED' ? 'جدول' : t;
  const rows = st.log.map(e => `
    <div style="display:grid;grid-template-columns:52px 64px minmax(0,1fr);gap:12px;align-items:baseline;padding:8px 0;border-top:1px solid #1E201B">
      <span style="font-family:var(--mono);font-size:12px;color:#6F6D64" dir="ltr">${esc(e.clock)}</span>
      <span style="font-family:var(--mono);font-size:11px;color:${color(e.tier)}">${tierLabel(e.tier)}</span>
      <span style="font-size:13.5px;line-height:1.55;color:#D9D7CF;text-wrap:pretty">${esc(e.message)}</span>
    </div>`).join('') || '<div class="muted">لا توجد قرارات بعد.</div>';
  return `
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <div class="label">سجل القرارات</div>
    </div>${rows}`;
}

// ---------------- chart (Chart.js) ----------------

function updateChart() {
  const labels = st.history.map(h => h.t);
  const actual = st.history.map(h => h.power_w);
  const base = st.history.map(h => h.baseline_w);
  if (!chart) {
    chart = new Chart($('chart'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'الفعلي', data: actual, borderColor: '#B8F04A', backgroundColor: 'rgba(184,240,74,0.10)', fill: 'origin', borderWidth: 2, pointRadius: 0, tension: 0.25 },
          { label: 'خط الأساس', data: base, borderColor: '#8E8C82', borderDash: [4, 5], borderWidth: 1, pointRadius: 0, fill: false, tension: 0.25 },
        ],
      },
      options: {
        animation: false, maintainAspectRatio: false, responsive: true,
        plugins: { legend: { display: false }, tooltip: { rtl: true } },
        scales: {
          x: { ticks: { color: '#6F6D64', maxTicksLimit: 6, font: { family: 'JetBrains Mono' } }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: '#6F6D64', font: { family: 'JetBrains Mono' }, callback: v => scale.unit === 'kW' ? (v / 1000).toFixed(1) + 'k' : v }, grid: { color: '#262822' } },
        },
      },
    });
  } else {
    chart.data.labels = labels;
    chart.data.datasets[0].data = actual;
    chart.data.datasets[1].data = base;
    chart.update('none');
  }
}

// ---------------- main loop ----------------

function renderAll() {
  $('mode-label').textContent = '· ' + lbl('mode', '');
  $('mode-sub').textContent = st.source !== 'simulator'
    ? 'قراءات حقيقية من العدّاد'
    : WW.site === 'building'
      ? 'بيانات محاكاة'
      : 'بيانات محاكاة';
  if (!document.activeElement || document.activeElement.id !== 'scenario-pick') WW.render($('toolbar'), toolbar());
  WW.render($('hero'), hero());
  WW.render($('goal'), goal());
  WW.render($('rooms'), roomsMap());
  WW.render($('devices'), devicesGrid());
  WW.render($('teach'), teachSection());
  const last = (st.teach && st.teach.messages.length) ? st.teach.messages[st.teach.messages.length - 1].id : 0;
  if (last !== ui.teach.lastMsg) { ui.teach.lastMsg = last; const c = $('teach-chat'); if (c) c.scrollTop = c.scrollHeight; }
  WW.render($('bill'), bill());
  WW.render($('sched'), schedSection());
  WW.render($('analyst'), analystSection());
  WW.render($('alerts'), alertsSection());
  notifyNewAlerts();
  WW.render($('log'), auditLog());
  $('meter-kw').textContent = powerStr(st.meter.power_w);
  $('meter-unit').textContent = scale.unit;
  $('meter-title').textContent = lbl('meter', 'العدّاد');
  $('meter-clock').textContent = st.clock + (st.source === 'simulator' ? ' · sim ×60' : '');
  $('phone-clock').textContent = st.clock;
  updateChart();
}

async function refresh() {
  try {
    st = await WW.getState();
    WWSched.sync(st);
    renderAll();
  } catch (e) {
    console.error(e);
  }
}

async function act(fn) {
  try { await fn(); } catch (e) { toast(e.message); }
  refresh();
}

WW.onAction({
  onError: e => toast(e.message),
  ...WWSched.actions,
  scenario: d => act(() => WW.post('/scenario', { name: d.name })),
  reset: () => act(() => WW.post('/reset')),
  estop: () => act(() => WW.post('/estop')),
  'set-goal': () => act(() => {
    const text = $('goal-text').value.trim();
    ui.goalText = text;
    return WW.post('/goal', { text });   // the server reads the bill target from the words
  }),
  'teach-room': d => { ui.teach.room = d.id; renderAll(); },
  'teach-start': () => act(() => WW.post('/teach/start', { room: ui.teach.room })),
  'teach-done': () => act(() => WW.post('/teach/done')),
  'teach-cancel': () => act(() => WW.post('/teach/cancel')),
  'teach-send': () => teachSay(ui.teach.text),
  'teach-quick': d => teachSay(d.text),
  'fp-del': d => act(() => WW.api('DELETE', `/api/sites/${WW.site}/fingerprints/${d.id}`)),
  'cmd-parse': () => parseCommand(),
  'cmd-mic': () => listen(),
  'cmd-cancel': () => { ui.cmd.res = null; renderAll(); },
  'cmd-run': () => act(async () => {
    const r = await WW.post('/command/run', { text: ui.cmd.text });
    ui.cmd = { text: '', res: null, busy: false, msg: r.done.length ? 'تم: ' + r.done.join('، ') : 'لم يُنفَّذ شيء.' };
  }),
  'heater-suggest': async () => {
    ui.heater.busy = true; ui.heater.msg = ''; renderAll();
    try { ui.heater.res = await WW.post('/heater/suggest', { hint: ui.heater.hint }); } catch (e) { toast(e.message); }
    ui.heater.busy = false; renderAll();
  },
  'heater-apply': () => act(async () => {
    const r = ui.heater.res;
    await WW.post('/heater/apply', { device_id: r.device_id, windows: r.items.map(i => ({ on_time: i.on_time, off_time: i.off_time })) });
    ui.heater = { hint: ui.heater.hint, res: null, busy: false,
      msg: `حُفظ جدول السخّان ✓ يستهلك ≈ ${fmt(r.total.kwh, 1)} ك.و.س يوميًا (≈ ${fmt(r.total.jod, 2)} دينار، تقديري وغير مُقاس).` };
  }),
  'heater-cancel': () => { ui.heater.res = null; renderAll(); },
  why: async () => {
    ui.why.busy = true; renderAll();
    try { ui.why.res = await WW.api('GET', `/api/sites/${WW.site}/why`); } catch (e) { toast(e.message); }
    ui.why.busy = false; renderAll();
  },
  'bill-toggle-manual': () => { ui.bill.manual = !ui.bill.manual; renderAll(); },
  'bill-manual': () => {
    if (!(Number(ui.bill.kwh) > 0)) { ui.bill.msg = 'أدخل الاستهلاك بالكيلوواط ساعة (ك.و.س) من الفاتورة.'; renderAll(); return; }
    return billSend(WW.billManual(ui.bill));
  },
  report: async () => {
    ui.rep.busy = true; renderAll();
    try {
      const res = await fetch(`/api/sites/${WW.site}/weekly.txt`);
      ui.rep.text = await res.text();
    } catch (e) { toast(e.message); }
    ui.rep.busy = false; renderAll();
  },
  toggle: d => {
    const dev = st.devices.find(x => x.id === d.id);
    if (dev.sensitive && dev.is_on) { ui.confirmId = dev.id; renderAll(); return; }
    return act(() => WW.post(`/devices/${d.id}/toggle`, { on: !dev.is_on }));
  },
  'confirm-off': d => { ui.confirmId = null; return act(() => WW.post(`/devices/${d.id}/toggle`, { on: false, confirmed: true })); },
  'confirm-cancel': () => { ui.confirmId = null; renderAll(); },
  setpoint: d => {
    const dev = st.devices.find(x => x.id === d.id);
    return act(() => WW.post(`/devices/${d.id}/setpoint`, { value: dev.setpoint + Number(d.delta) }));
  },
  tariff: d => act(() => WW.post('/tariff', { type: d.type })),
  'alert-act': d => act(async () => { await WW.post(`/alerts/${d.id}/act`); toast('أُرسل طلب الموافقة إلى الهاتف. لن نُطفئ شيئًا قبل موافقتك.'); }),
  'alert-dismiss': d => act(() => WW.post(`/alerts/${d.id}/dismiss`)),
  'alert-perm': () => Notification.requestPermission().then(renderAll),
  'open-wiz': () => {
    const f = openPhone();
    const send = () => f.contentWindow && f.contentWindow.postMessage({ type: 'open-wizard' }, location.origin);
    if (f.dataset.loaded) send(); else f.addEventListener('load', send, { once: true });
  },
  'open-plug': () => {   // the "add smart plug" wizard lives in the phone app (js/plugs.js)
    const f = $('phone-frame');
    if (f.contentWindow) f.contentWindow.postMessage({ type: 'open-plug' }, location.origin);
  },
});

document.addEventListener('change', ev => {
  if (ev.target.id === 'bill-file' && ev.target.files[0]) {
    const file = ev.target.files[0];
    ev.target.value = '';
    billSend(WW.billPhoto(file));
  }
  if (ev.target.id === 'scenario-pick' && ev.target.value) {
    const name = ev.target.value;
    ev.target.value = '';
    ev.target.blur();
    act(() => WW.post('/scenario', { name }));
  }
});
document.addEventListener('input', ev => {
  const id = ev.target.id, v = ev.target.value;
  if (id === 'goal-text') ui.goalText = v;
  if (id === 'cmd-text') ui.cmd.text = v;
  if (id === 'teach-text') ui.teach.text = v;
  if (id === 'heater-hint') ui.heater.hint = v;
  if (id === 'bill-kwh') ui.bill.kwh = v;
  if (id === 'bill-days') ui.bill.days = v;
  if (id === 'bill-amount') ui.bill.amount = v;
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Enter' && ev.target.id === 'cmd-text') parseCommand();
  if (ev.key === 'Enter' && ev.target.id === 'teach-text') teachSay(ui.teach.text);
  if (ev.key === 'Enter' && ev.target.id === 'goal-text') document.querySelector('[data-act="set-goal"]').click();
});

// Phone preview lives in a drawer and loads only when opened (saves polling when unused).
function openPhone() {
  const f = $('phone-frame');
  if (!f.src) {
    f.addEventListener('load', () => { f.dataset.loaded = '1'; }, { once: true });
    f.src = 'app.html?site=' + encodeURIComponent(WW.site) + '&embed=1';
  }
  $('phone-drawer').hidden = false;
  return f;
}
$('phone-open').addEventListener('click', openPhone);
$('phone-drawer').addEventListener('click', ev => { if (ev.target.closest('[data-close]')) $('phone-drawer').hidden = true; });
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') $('phone-drawer').hidden = true; });
$('house-link').href = 'house.html?site=' + encodeURIComponent(WW.site);
// Show the address that is inside the QR code (for typing it by hand if needed).
fetch('/api/connect').then(r => r.json()).then(d => { $('connect-url').textContent = d.url; }).catch(() => {});
WW.billStatus().then(x => { ui.bill.status = x; }).catch(() => {});
WWSched.init({ rerender: () => st && renderAll(), refresh, toast });
refresh();
setInterval(refresh, 1000);
