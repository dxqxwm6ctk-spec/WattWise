/* WattWise dashboard: polls the backend every second and renders the page.

   Page order follows the demo story:
     1. give the agent a goal  ->  2. approve or reject its request  ->  3. see the measured saving
   then the devices, a few extra tools (closed by default) and the audit log.
*/

const { esc, fmt } = WW;
const $ = id => document.getElementById(id);

const SITE_SCALE = { home: { unit: 'kW' }, building: { unit: 'kW' }, lab: { unit: 'W' } };
const scale = SITE_SCALE[WW.site] || SITE_SCALE.home;
const SITES = [['home', 'البيت'], ['building', 'المبنى (١٠ غرف)'], ['lab', 'المختبر']];
const ui = {
  confirmId: null, goalText: 'أبقِ فاتورة هذا الشهر تحت 30 دينارًا دون إزعاج أحد في البيت',
  cmd: { text: '', res: null, busy: false, msg: '' }, listening: false,
  heater: { hint: '', res: null, busy: false, msg: '' },
  why: { res: null, busy: false }, rep: { text: '', busy: false },
  bill: { status: null, busy: false, res: null, msg: '', manual: false, kwh: '', days: '', amount: '' },
  teach: { room: null, text: '', busy: false, lastMsg: 0 },
  logAll: false,
};
let st = null;
let chart = null;

const powerStr = w => scale.unit === 'kW' ? fmt((w || 0) / 1000, 2) : fmt(w, 0);
const isSim = () => st && st.source === 'simulator';

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove('show'), 3500);
}

// ---------------- header ----------------

function sitesNav() {
  return SITES.map(([k, label]) =>
    `<a href="index.html?site=${k}" class="${k === WW.site ? 'sel' : ''}"${k === WW.site ? ' aria-current="page"' : ''}>${label}</a>`).join('');
}

function agentStatus() {
  const a = WW.agentLabel(st);
  const col = a.color === '#E8553F' ? 'var(--red)' : a.color === '#F2B544' ? 'var(--warn)' : a.color === '#8E8C82' ? 'var(--muted)' : 'var(--acc)';
  return `<span style="color:${col};display:inline-flex;align-items:center;gap:7px"><i></i>الوكيل: ${esc(a.label)}</span>`;
}

function menuList() {
  return `
    <a href="stage.html?site=${WW.site}">شاشة العرض للحكّام</a>
    <a href="house.html?site=${WW.site}">البيت التفاعلي (ثلاثي الأبعاد)</a>
    <button type="button" data-act="phone">معاينة تطبيق الهاتف</button>
    <a href="/api/sites/${WW.site}/report" target="_blank" rel="noopener">تقرير التوفير (للطباعة)</a>
    <hr>
    <button type="button" data-act="reset">إعادة ضبط العرض</button>`;
}

function intro() {
  if (!isSim()) return 'غرفة المختبر: قراءات حقيقية من ESP32 وعدّاد PZEM-004T. ابدأ بإعطاء الوكيل هدفًا، ثم وافق على اقتراحه أو ارفضه.';
  const where = WW.site === 'building' ? 'مبنى من ١٠ غرف (الكود نفسه)' : 'بيت كامل';
  return `وكيل ذكي يخفّض استهلاك الكهرباء: يراقب العدّاد، يقترح إجراءً، وينتظر موافقتك قبل أن يطفئ أي جهاز. المعروض الآن ${where} ببيانات تركيبية من المحاكي.`;
}

// Simulator scenarios (only when the data comes from the simulator).
function demoBar() {
  return `<span class="demo-label">تجربة العرض (المحاكي):</span>
    <button class="btn btn-quiet btn-sm" data-act="scenario" data-name="bedroom_empty_window">${esc(st.demo_label || 'غرفة فارغة والشباك مفتوح')}</button>
    <select id="scenario-pick" aria-label="سيناريوهات أخرى">
      <option value="">سيناريو آخر…</option>
      <option value="heat_wave">موجة حر</option>
      <option value="holiday">عطلة (البيت فارغ)</option>
      <option value="sensor_fault">عطل في الحسّاسات</option>
      <option value="unknown_load">حمل غريب (جهاز غير مسجّل)</option>
      <option value="ev_arrives">وصول السيارة الكهربائية وبدء الشحن</option>
      <option value="overload">حمل زائد (تيار قريب من الحد)</option>
      <option value="stranger_device">جهاز غريب ٦٠ واط في المطبخ</option>
      <option value="normal">العودة إلى الوضع الطبيعي</option>
    </select>`;
}

// ---------------- key numbers ----------------

function kpis() {
  const b = st.bill, s = st.savings, m = st.meter;
  const goalJd = st.goal && st.goal.bill_target_jd;
  const over = goalJd && b.bill_projected > goalJd;
  return `
    <div class="kpi">
      <span class="kpi-label">الاستهلاك الآن</span>
      <span class="kpi-val" dir="ltr">${powerStr(m.power_w)}<small>${scale.unit}</small></span>
      <span class="kpi-sub" dir="ltr">${fmt(m.voltage_v, 0)} V · ${fmt(m.current_a, 1)} A</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">فاتورة الشهر حتى الآن</span>
      <span class="kpi-val">${fmt(b.bill_now, 2)}<small>دينار</small></span>
      <span class="kpi-sub">${fmt(b.kwh_now)} ك.و.س</span>
    </div>
    <div class="kpi ${over ? 'warn' : ''}">
      <span class="kpi-label">المتوقع آخر الشهر</span>
      <span class="kpi-val">${fmt(b.bill_projected, 1)}<small>دينار</small></span>
      <span class="kpi-sub">${goalJd ? (over ? `أعلى من هدفك (${fmt(goalJd)} دينار)` : `ضمن هدفك (${fmt(goalJd)} دينار)`) : 'لا يوجد هدف بعد'}</span>
    </div>
    <div class="kpi good">
      <span class="kpi-label">التوفير المُقاس</span>
      <span class="kpi-val">${fmt(s.jod, 3)}<small>دينار</small></span>
      <span class="kpi-sub">${fmt(s.kwh, 2)} ك.و.س${s.co2_kg === null ? '' : ` · ${fmt(s.co2_kg, 2)} كغ CO₂`}</span>
    </div>`;
}

// ---------------- 1. goal ----------------

function goal() {
  const form = `<div class="goal-form">
      <input class="field grow" id="goal-text" value="${esc(ui.goalText)}" aria-label="اكتب هدفك بكلماتك"
        placeholder="مثلًا: أريد ألّا تتجاوز الفاتورة ٢٥ دينارًا دون أن يشعر أحد بفرق">
      <button class="btn btn-primary" style="height:42px" data-act="set-goal">${st.goal ? 'غيّر الهدف' : 'ابدأ'}</button>
    </div>`;
  const steps = WW.goalSteps(st).map((s, i) =>
    `<li class="${s.state}${s.state === 'active' && i === 4 ? ' wait' : ''}">${esc(s.label)}${s.tag && s.state !== 'done' ? ` · ${esc(s.tag)}` : ''}</li>`).join('');
  const body = st.goal
    ? `<div class="goal-text">«${esc(st.goal.text)}»</div>${form}${planBox()}`
    : `<div class="hint" style="font-size:14px">اكتب هدفًا (لا سؤالًا)، وسيقسّمه الوكيل إلى خطوات بنفسه. يمكنك استخدام المثال الجاهز.</div>${form}`;
  return `
    <div class="card-head"><h2><span class="num">١</span> أعطِ الوكيل هدفًا</h2><span class="hint">ابدأ من هنا</span></div>
    ${body}
    ${st.goal ? `<ol class="steps" aria-label="مراحل عمل الوكيل">${steps}</ol>` : ''}
    ${anomalyBox()}
    ${brainLine()}`;
}

// The agent's own plan for this goal (from the LLM, or the rule-based template).
function planBox() {
  const p = st.plan;
  if (!p || !p.steps.length) return '';
  const by = p.by === 'llm' ? 'من النموذج الذكي، ويراجعها حارس السياسات' : 'من القواعد (دون ذكاء اصطناعي)';
  const tag = i => (p.tags || [])[i] === 'T1'
    ? '<span class="tag ok">بموافقتك</span>' : '<span class="tag auto">تلقائي</span>';
  return `<div class="plan">
      <div class="plan-head"><span>خطة الوكيل</span><span>${by}</span></div>
      ${p.summary ? `<div class="plan-sum">${esc(p.summary)}</div>` : ''}
      ${p.steps.map((x, i) => `<div class="plan-step">${tag(i)}<span>${esc(x)}</span></div>`).join('')}
    </div>`;
}

// AI layer 1: the meter reads something the known devices do not explain.
function anomalyBox() {
  const a = st.anomaly;
  if (!a || !a.open) return '';
  const what = a.kind === 'extra'
    ? `العدّاد ≈ ${a.power_w} واط والمتوقع ≈ ${a.expected_w} واط: زيادة ≈ ${a.residual_w} واط مصدرها غير معروف.`
    : `العدّاد أقل من المتوقع بنحو ${-a.residual_w} واط: ربما يوجد جهاز مفصول أو معطّل.`;
  return `<div class="box warn"><span class="box-title" style="color:var(--warn)">استهلاك غير طبيعي (تنبيه فقط، لن نطفئ شيئًا)</span><span>${what}</span></div>`;
}

// Which brain is planning, the LLM budget, the weather, and the anomaly model state.
function brainLine() {
  const b = st.agent.brain || {};
  const w = st.weather || {};
  const a = st.anomaly;
  const parts = [
    b.mode === 'llm' ? `يخطّط بـ: ${esc(b.model || 'النموذج الذكي')}` : 'يخطّط بـ: القواعد',
    b.model ? `تكلفة الشهر <span dir="ltr">$${fmt(b.spent_usd, 2)} / $${fmt(b.budget_usd, 0)}</span>` : '',
    w.available ? `الطقس ${fmt(w.outdoor_temp_c, 1)}° (${esc(w.place || '')})` : 'الطقس: لا إنترنت، نكمل دونه',
    a && !a.open ? (a.ready ? 'كشف الشذوذ: طبيعي' : `كشف الشذوذ يتعلّم (${a.samples} قراءة)`) : '',
  ].filter(Boolean);
  return `<div class="meta" title="${esc(b.reason_ar || '')}">${parts.map(p => `<span>${p}</span>`).join('')}</div>`;
}

// ---------------- 2. approvals and alerts ----------------

function approvalCard() {
  const p = st.pending;
  const pct = (p.expires_in_s / p.timeout_s * 100).toFixed(1);
  return `<div class="ask">
      <div class="ask-top"><span>الوكيل يطلب موافقتك</span><span class="n" dir="ltr">${p.expires_in_s}s</span></div>
      <div class="ask-title">${esc(p.title)}</div>
      <div>${esc(p.reason)}</div>
      ${p.details.alternative ? `<div class="hint">البديل: ${esc(p.details.alternative)}</div>` : ''}
      <div class="hint">التوفير التقريبي: <span class="n" dir="ltr">${fmt(p.details.saving_jod_per_hour, 3)} JD/h</span></div>
      <div class="ask-bar"><div style="width:${pct}%"></div></div>
      <div class="ask-btns">
        <button class="btn btn-quiet btn-lg" data-act="reject" data-id="${p.id}">لا، اتركه</button>
        <button class="btn btn-primary btn-lg" data-act="approve" data-id="${p.id}">نعم، نفّذ</button>
      </div>
      <span class="hint" style="text-align:center">يصل الطلب نفسه إلى الهاتف. إن لم يردّ أحد قبل انتهاء الوقت، لن يُنفَّذ شيء.</span>
    </div>`;
}

function statusBox() {
  const a = st.agent, last = st.last_approval;
  const dev = last && last.device_name ? last.device_name : 'الجهاز';
  let m;
  if (!st.online) m = ['red', 'لا توجد قراءات', 'انقطعت القراءات، فعادت الأجهزة إلى وضعها الطبيعي دون إجراءات تلقائية.'];
  else if (a.estop) m = ['red', 'الوكيل متوقف (إيقاف طوارئ)', 'عادت كل الأجهزة إلى وضعها الطبيعي. اضغط «إعادة ضبط العرض» من قائمة «المزيد» لتشغيله من جديد.'];
  else if (a.safe_mode) m = ['red', 'الوضع الآمن', 'لا يوجد اتصال بالهاتف، لذا لن نطلب موافقة ولن ننفّذ شيئًا.'];
  else if (!st.goal) m = ['', 'لا توجد طلبات بعد', 'عندما يجد الوكيل هدرًا سيظهر هنا طلب موافقة بزرّين: «نعم» و«لا».'];
  else m = {
    analyzing: ['warn', 'جارٍ التحليل', 'لاحظ الوكيل جهازًا يعمل في غرفة فارغة. سيصل طلب الموافقة بعد لحظات.'],
    executing: ['good', 'جارٍ التنفيذ', 'وصلت موافقتك.'],
    verified: ['good', 'تم وتحقّق العدّاد', `أُطفئ ${dev} وأكّد العدّاد انخفاض الاستهلاك. يظهر التوفير في القسم ٣.`],
    rejected: ['red', 'رفضت الطلب، فلم يتغيّر شيء', `بقي ${dev} كما هو.`],
    expired: ['red', 'انتهى الوقت دون رد', 'لذا لم يُنفَّذ شيء. عدم الرد لا يعني الموافقة.'],
  }[a.phase] || ['', 'لا توجد طلبات الآن', 'الوكيل يراقب، ولا يوجد هدر يحتاج قرارك.'];
  return `<div class="box ${m[0]}"><span class="box-title">${m[1]}</span><span class="hint" style="font-size:14px;color:var(--sub)">${m[2]}</span></div>`;
}

function approveSection() {
  const al = st.alerts || { items: [] };
  const active = al.items.filter(a => a.active);
  const rows = al.items.slice(0, 6).map(a => {
    const off = !a.active || a.user_state;
    const status = !a.active ? 'انتهى' : a.user_state === 'acted' ? 'أُرسل طلب موافقة' : a.user_state === 'dismissed' ? 'تم التجاهل' : '';
    const lv = { danger: 'danger', warn: 'warn' }[a.level] || 'info';
    return `<div class="row${off ? ' off' : ''}">
      <span class="row-time" dir="ltr">${esc(a.clock)}</span>
      <div><div class="row-title ${lv}">${esc(a.title)}</div><div class="row-body">${esc(a.body)}</div></div>
      <div class="row-act">
        ${status ? `<span class="hint">${status}</span>` : ''}
        ${a.can_act ? `<button class="btn btn-primary btn-sm" data-act="alert-act" data-id="${a.id}">اطلب إطفاءه</button>` : ''}
        ${a.active && !a.user_state ? `<button class="btn btn-quiet btn-sm" data-act="alert-dismiss" data-id="${a.id}">تجاهل</button>` : ''}
      </div>
    </div>`;
  }).join('');
  const perm = ('Notification' in window) && Notification.permission === 'default'
    ? '<button class="btn btn-quiet btn-sm" data-act="alert-perm">فعّل إشعارات المتصفح</button>' : '';
  return `
    <div class="card-head"><h2><span class="num">٢</span> وافق أو ارفض</h2><span class="hint">لا يطفئ الوكيل أي جهاز دون موافقتك</span></div>
    ${st.pending ? approvalCard() : statusBox()}
    <div class="card-head"><span class="sub-h">التنبيهات${active.length ? ` (${active.length})` : ''}</span>${perm}</div>
    ${rows ? `<div class="rows">${rows}</div>` : '<div class="hint">لا توجد تنبيهات. كل شيء طبيعي.</div>'}`;
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

// ---------------- 3. savings (bill side panel) ----------------

// AI layer 2: expected load for this hour and the next 5, plus our measured accuracy.
function forecastBlock() {
  const f = st.forecast;
  if (!f) return '';
  const max = Math.max(...f.steps.map(x => x.power_w), 1);
  const bars = f.steps.map(x => `<div><span>${fmt(x.power_w / 1000, 1)}</span>
      <i class="${x.method === 'now' ? 'now' : ''}" style="height:${Math.max(4, x.power_w / max * 40).toFixed(0)}px"></i><span>${x.hour}</span></div>`).join('');
  const a = f.accuracy;
  const acc = a.hours ? `الخطأ ≈ ${fmt(a.mean_err_pct, 0)}% في آخر ${a.hours} ساعة` : 'تُقاس الدقة بعد أول ساعة كاملة';
  return `<div style="display:flex;flex-direction:column;gap:6px">
      <div class="card-head"><span class="sub-h" style="margin:0">التوقّع للساعات القادمة (kW)</span><span class="hint" dir="ltr">${fmt(f.kwh, 1)} kWh ≈ ${fmt(f.jod, 2)} JD</span></div>
      <div class="fc">${bars}</div>
      <div class="note">${acc}</div>
    </div>`;
}

function bill() {
  const b = st.bill, s = st.savings, m = st.mv;
  const goalJd = st.goal && st.goal.bill_target_jd;
  const projColor = goalJd && b.bill_projected > goalJd ? '#E3A33A' : 'var(--acc)';
  const shades = b.type === 'unsub' ? ['#E9D9A8', '#EDB8AE'] : ['#C7E2C8', '#E9D9A8', '#EDB8AE'];
  const segs = b.segments.map((t, i) => `<div style="width:${t.width_pct}%;background:${shades[i] || '#EDB8AE'}"></div>`).join('');
  const segLabels = b.segments.map(t => `<span style="width:${t.width_pct}%">${t.fils} فلس</span>`).join('');
  const opts = b.types.map(o => `<button data-act="tariff" data-type="${o.key}" class="${b.type === o.key ? 'sel' : ''}">${esc(o.label)}</button>`).join('');
  const mv = m ? `<div class="note" style="color:${m.status === 'ok' ? 'var(--acc)' : 'var(--muted)'}">قياس التوفير (M&amp;V): ${esc(m.message_ar)}${m.model ? ` · CV(RMSE) ${fmt(m.model.cv_rmse_pct, 1)}%` : ''}</div>` : '';
  return `<div class="bill">
    <div class="card-head"><span class="sub-h" style="margin:0">شرائح التعرفة</span><div class="seg">${opts}</div></div>
    <div>
      <div class="tiers">
        <div class="tiers-bar">${segs}</div>
        <div class="tiers-mark" style="right:${b.now_pos}%;background:var(--text)"></div>
        <div class="tiers-mark" style="right:${b.proj_pos}%;background:${projColor}"></div>
      </div>
      <div class="tiers-labels">${segLabels}</div>
      <div class="meta" style="margin-top:4px">
        <span><b style="color:var(--text)">|</b> الآن</span>
        <span><b style="color:${projColor}">|</b> متوقّع آخر الشهر ${fmt(b.projected_kwh)} ك.و.س</span>
      </div>
    </div>
    <div class="sub-box" style="font-size:14px">${esc(b.message)}</div>
    ${forecastBlock()}
    ${mv}
    <div class="big-save">
      <div><b style="color:var(--acc)">${fmt(s.jod, 3)}</b><span>دينار مُوفَّر (مُقاس)</span></div>
      <div><b>${fmt(s.kwh, 2)}</b><span>ك.و.س${s.co2_kg === null ? '' : ` · ${fmt(s.co2_kg, 2)} كغ CO₂`}</span></div>
    </div>
    <div class="note">${esc(b.source || '')} قيمة الطاقة فقط، دون الدعم أو الرسوم الأخرى.${isSim() ? ' الاستهلاك هنا من المحاكي (بيانات تركيبية).' : ''}</div>
  </div>`;
}

// ---------------- devices, grouped by room ----------------

function devicesSection() {
  const onCount = st.devices.filter(d => d.is_on).length;
  const confirmDev = st.devices.find(d => d.id === ui.confirmId);
  const confirm = confirmDev ? `<div class="box warn">
      <span class="box-title">هل تريد إطفاء ${esc(confirmDev.name)} فعلًا؟</span>
      <span>سينقطع تطبيق الموافقة على الهاتف، ويدخل الوكيل الوضع الآمن: لن يطلب موافقة ولن ينفّذ أي إجراء حتى يعود الاتصال.</span>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button class="btn btn-quiet btn-sm" data-act="confirm-cancel">لا، اتركه</button>
        <button class="btn btn-danger btn-sm" data-act="confirm-off" data-id="${esc(confirmDev.id)}">أطفئه</button>
      </div></div>` : '';
  const learning = st.learn ? '<div class="box">تجري إضافة جهاز جديد من تطبيق الهاتف. أكمل الخطوات هناك.</div>' : '';
  const contact = WW.site === 'lab' ? 'الباب' : 'الشباك';
  const rooms = st.rooms.map(r => {
    const devs = st.devices.filter(d => d.room === r.id).map(deviceRow).join('');
    const occ = r.occupied === null ? '' : r.occupied ? '<span>مشغولة</span>' : '<span class="empty">فارغة</span>';
    const win = r.window_open === null ? '' : `<span>${contact} ${r.window_open ? 'مفتوح' : 'مغلق'} (محاكى)</span>`;
    return `<div class="room${r.waste ? ' waste' : ''}">
        <div class="room-h"><span class="room-name">${esc(r.name)}</span><span class="room-w" dir="ltr">${r.power_w} W</span></div>
        <div class="room-meta">${occ}${r.temp_c == null ? '' : `<span dir="ltr">${fmt(r.temp_c, 1)}°C</span>`}${win}</div>
        ${devs || '<div class="hint">لا توجد أجهزة</div>'}
      </div>`;
  }).join('');
  return `
    <div class="card-head">
      <h2>الأجهزة</h2>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="hint">يعمل ${onCount} من ${st.devices.length}</span>
        <button class="btn btn-quiet btn-sm" data-act="open-plug">+ مقبس ذكي</button>
        <button class="btn btn-quiet btn-sm" data-act="open-wiz">+ جهاز عبر العدّاد</button>
      </div>
    </div>
    ${learning}${confirm}${commandBar()}
    <div class="rooms">${rooms}</div>
    <div class="note">الإشغال فقط (مشغولة/فارغة)، بلا كاميرات ولا تتبّع للأشخاص. الأجهزة الحرجة (مثل الثلاجة وإنذار الحريق) محمية ولا يمكن إطفاؤها. * بصمة تقديرية لم تُقَس على العدّاد بعد.</div>`;
}

function deviceRow(d) {
  const on = d.is_on, locked = d.tier === 'T2';
  const sub = [
    locked ? 'محمي، يعمل دائمًا' : on ? 'يعمل' : 'مطفأ',
    d.agent_off ? 'أطفأه الوكيل بموافقتك' : '',
    d.sensitive && !locked ? 'إطفاؤه يقطع تطبيق الموافقة' : '',
    !d.allow && !locked ? 'يدوي فقط' : '',
    d.plug ? `مقبس ${d.plug.online ? 'متصل' : 'غير متصل'}` : '',
    d.added ? 'جديد' : '',
  ].filter(Boolean).join(' · ');
  const sw = locked
    ? '<span class="lock">محمي</span>'
    : `<button class="switch${on ? ' on' : ''}" role="switch" aria-checked="${on}" data-act="toggle" data-id="${esc(d.id)}" aria-label="${esc(d.name)}"></button>`;
  return `<div class="dev">
      <div class="dev-main"><span class="dev-name">${esc(d.name)}</span><span class="dev-sub">${sub}</span></div>
      <span class="dev-w" dir="ltr">${on ? d.est_w : 0} W${d.signature_measured ? '' : ' *'}</span>
      ${sw}
    </div>`;
}

// Typed or spoken orders. The server understands them, the Policy Guard checks each
// action, and NOTHING runs until the user presses "yes".
const micOk = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
function commandBar() {
  const c = ui.cmd, r = c.res;
  let result = '';
  if (r) {
    const items = r.items.map(i => `<div class="plan-step"><span class="tag ${i.ok ? 'auto' : 'no'}">${i.ok ? 'مسموح' : 'ممنوع'}</span>
        <span>${esc(i.label)} <span class="hint">${esc(i.why)}</span></span></div>`).join('');
    const canRun = r.items.some(i => i.ok);
    result = `<div class="plan">
        <span>${esc(r.clarify || r.reply)}</span>${items}
        <span class="note">فحص حارس السياسات كل إجراء. لن يُنفَّذ شيء قبل أن تضغط «نعم».</span>
        <div style="display:flex;gap:8px">
          ${canRun ? '<button class="btn btn-primary btn-sm" data-act="cmd-run">نعم، نفّذ</button>' : ''}
          <button class="btn btn-quiet btn-sm" data-act="cmd-cancel">لا</button>
        </div></div>`;
  }
  return `<div class="cmd-box">
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <input class="field grow" id="cmd-text" value="${esc(c.text)}" aria-label="اكتب أمرك للوكيل"
          placeholder="أمر سريع، مثلًا: أطفئ مكيّف غرفة النوم بعد نصف ساعة">
        ${micOk ? `<button class="mic${ui.listening ? ' on' : ''}" data-act="cmd-mic" aria-label="${ui.listening ? 'أستمع إليك، اضغط للإيقاف' : 'تحدّث'}">🎤</button>` : ''}
        <button class="btn btn-quiet" style="height:42px" data-act="cmd-parse">${c.busy ? 'جارٍ الفهم…' : 'أرسل'}</button>
      </div>${result}
      ${c.msg ? `<span style="color:var(--acc)">${esc(c.msg)}</span>` : ''}
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

// ---------------- extra tools (collapsed) ----------------

// Timers and daily schedules (on/off only), and the smart water-heater schedule.
const estText = e => e ? `≈ ${fmt(e.kwh, 1)} ك.و.س/يوم · ≈ ${fmt(e.jod, 2)} دينار/يوم (تقديري)` : '';

function heaterPanel() {
  const h = ui.heater, hr = h.res;
  const hasHeater = st.devices.some(d => d.kind === 'heater' && d.tier === 'T1' && !d.sensitive);
  if (!hasHeater) return '';
  const proposal = !hr ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <span>${esc(hr.reply)}</span>
      ${hr.items.map(i => `<div class="sub-box"><span class="n" dir="ltr">${esc(i.on_time)} → ${esc(i.off_time)}</span>
        <span>${esc(i.why)}</span><span class="note">${estText(i.estimate)}</span></div>`).join('')}
      <span class="hint">المجموع ≈ ${fmt(hr.total.kwh, 1)} ك.و.س يوميًا ≈ ${fmt(hr.total.jod, 2)} دينار (تقديري)</span>
      <div style="display:flex;gap:8px">
        ${hr.items.length ? '<button class="btn btn-primary btn-sm" data-act="heater-apply">نعم، اعتمده</button>' : ''}
        <button class="btn btn-quiet btn-sm" data-act="heater-cancel">لا</button>
      </div></div>`;
  return `<div class="panel">
      <span class="panel-title">سخّان الماء</span>
      <span class="hint">يقترح الوكيل تشغيله قبل الاستحمام فقط، ويمنع الحارس أي فترة أطول من ٣ ساعات.</span>
      <input class="field" id="heater-hint" value="${esc(h.hint)}" aria-label="متى تستحمّون؟" placeholder="متى تستحمّون؟ مثلًا: الصباح ٦:٣٠ والمساء ٩">
      <button class="btn btn-quiet" data-act="heater-suggest">${h.busy ? 'جارٍ التخطيط…' : 'اقترح جدولًا للسخّان'}</button>
      ${proposal}
      ${h.msg ? `<span style="color:var(--acc)">${esc(h.msg)}</span>` : ''}
    </div>`;
}

function schedSection() {
  const heater = WWSched.state.site === WW.site ? heaterPanel() : '';
  return `${WWSched.render({ theme: 'light', layout: 'side' })}
    ${heater ? `<div class="panels" style="margin-top:12px">${heater}</div>` : ''}
    <div class="note" style="margin-top:8px">تُراجع كل جدول وتؤكّده قبل الحفظ، ويفحصه الحارس في كل مرة يعمل.${isSim() ? ' ساعة المحاكي أسرع ×60.' : ''}</div>`;
}

// Teach mode: the AI learns the room's appliances from the meter and asks the user.
function teachSection() {
  const t = st.teach || { messages: [], fingerprints: [], unknown: [] };
  const s = t.session;
  if (!ui.teach.room || !st.rooms.some(r => r.id === ui.teach.room)) ui.teach.room = st.rooms[0] && st.rooms[0].id;
  const room = s ? s.room : ui.teach.room;
  const chips = st.rooms.map(r => `<button class="chip ${r.id === room ? 'sel' : ''}" data-act="teach-room" data-id="${esc(r.id)}"${s ? ' disabled' : ''}>${esc(r.name)}</button>`).join('');
  const status = !s ? 'اختر الغرفة واضغط «علّمني».'
    : s.status === 'listening' ? `أستمع إلى العدّاد في ${esc(s.room_name)}… (${s.candidates} جهاز حتى الآن)`
      : s.status === 'asking' ? 'بانتظار تأكيدك أو تصحيحك.' : 'بانتظار موافقتك على الحفظ.';
  const buttons = !s
    ? '<button class="btn btn-primary btn-sm" data-act="teach-start">علّمني أجهزة هذه الغرفة</button>'
    : `${s.status === 'listening' ? '<button class="btn btn-primary btn-sm" data-act="teach-done">انتهيت</button>' : ''}
       <button class="btn btn-quiet btn-sm" data-act="teach-cancel">إيقاف دون حفظ</button>`;
  const msgs = t.messages.map(m => `<div class="msg ${m.role === 'ai' ? 'ai' : 'me'}">${esc(m.text)}</div>`).join('')
    || '<div class="hint">لا توجد محادثة بعد.</div>';
  const quick = t.waiting_for === 'teach_confirm' ? ['صحيح'] : ['teach_save', 'label_save'].includes(t.waiting_for) ? ['احفظ', 'لا'] : t.waiting_for === 'label' ? ['تجاهل'] : [];
  const fps = t.fingerprints.map(f => `
    <div class="dev">
      <div class="dev-main"><span class="dev-name">${esc(f.name)}</span><span class="dev-sub">${esc(f.room_name)}</span></div>
      <span class="dev-w" dir="ltr">${fmt(f.watts, 0)} W${f.pf != null ? ' · PF ' + fmt(f.pf, 2) : ''}</span>
      <button class="btn btn-quiet btn-sm" data-act="fp-del" data-id="${f.id}" title="احذف البصمة" aria-label="احذف البصمة">×</button>
    </div>`).join('') || '<div class="hint">لا توجد بصمات محفوظة. لا تُحفظ البصمة إلا بموافقتك.</div>';
  const unk = t.unknown.length ? `<span class="pill" style="background:var(--warn-soft);color:var(--warn)">${t.unknown.length} جهاز مجهول</span>` : '';
  return `
    <div class="panels">
      <div class="panel" style="flex:1 1 260px">
        <span class="panel-title">الغرفة ${unk}</span>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${chips}</div>
        <div class="hint">${status}</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">${buttons}</div>
        <span class="panel-title" style="margin-top:6px">البصمات المحفوظة</span>
        <div>${fps}</div>
      </div>
      <div class="panel" style="flex:2 1 380px">
        <span class="panel-title">المحادثة</span>
        <div id="teach-chat" class="chat">${msgs}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${quick.map(q => `<button class="chip" data-act="teach-quick" data-text="${esc(q)}">${esc(q)}</button>`).join('')}</div>
        <div style="display:flex;gap:8px">
          <input class="field grow" id="teach-text" placeholder="اكتب ردّك… مثلًا: الأول لابتوب، الثاني مصباح المكتب" value="${esc(ui.teach.text)}">
          <button class="btn btn-quiet" style="height:42px" data-act="teach-send">${ui.teach.busy ? '…' : 'إرسال'}</button>
        </div>
      </div>
    </div>
    <div class="note" style="margin-top:8px">بصمة الجهاز = قفزة الواط على العدّاد + معامل القدرة (PF).</div>`;
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
  const why = !w ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <div>${esc(w.headline)}</div>
      ${w.causes.map(c => `<div class="sub-box"><span>${esc(c.what)}</span><span class="note">${esc(c.evidence)}</span></div>`).join('')}
      <div style="color:var(--acc)">${esc(w.action)}</div>
      <div class="note">${esc(w.note)}</div></div>`;
  const report = !rep.text ? '' : `<div class="report-text">${esc(rep.text)}</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <a class="btn btn-quiet btn-sm" href="/api/sites/${WW.site}/weekly.txt" download>تنزيل الملف</a>
        <a class="btn btn-quiet btn-sm" href="/api/sites/${WW.site}/report" target="_blank" rel="noopener">تقرير التوفير للطباعة</a>
      </div>`;
  return `
    <div class="panels">
      <div class="panel">
        <span class="panel-title">لماذا الفاتورة بهذا المبلغ؟</span>
        <button class="btn btn-quiet" style="align-self:flex-start" data-act="why">${ui.why.busy ? 'جارٍ التحليل…' : w ? 'أعد التحليل' : 'حلّل'}</button>
        ${why}
      </div>
      <div class="panel">${billPanel()}</div>
      <div class="panel">
        <span class="panel-title">التقرير الأسبوعي</span>
        <button class="btn btn-quiet" style="align-self:flex-start" data-act="report">${rep.busy ? 'جارٍ التجهيز…' : rep.text ? 'جهّز تقريرًا جديدًا' : 'جهّز التقرير'}</button>
        ${report}
      </div>
    </div>
    <div class="note" style="margin-top:8px">الأرقام محسوبة برمجيًا من القياسات.</div>`;
}

// Bill photo: Claude reads it (when there is a key), the code checks it. Or type 3 numbers by hand.
function billPanel() {
  const b = ui.bill, r = b.res, noPhoto = b.status && !b.status.photo;
  const bn = r && r.bill;
  const nums = !bn ? '' : [
    bn.kwh != null && `${fmt(bn.kwh, 0)} ك.و.س`, bn.days && `${bn.days} يوم`,
    bn.amount_jod != null && `${fmt(bn.amount_jod, 2)} دينار`,
    bn.period_from && bn.period_to && `${bn.period_from} ← ${bn.period_to}`,
  ].filter(Boolean).map(x => `<span class="pill">${esc(x)}</span>`).join('');
  const result = !r ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;flex-wrap:wrap;gap:6px">${nums}</div>
      ${r.explanation.map(x => `<div>${esc(x)}</div>`).join('')}
      ${r.checks.map(x => `<div class="sub-box">${esc(x)}</div>`).join('')}
      ${r.ideas.map(x => `<div style="color:var(--acc)">• ${esc(x)}</div>`).join('')}
      <div class="note">${esc(r.note)}</div></div>`;
  const manual = !(b.manual || noPhoto) ? '' : `<div style="display:flex;flex-wrap:wrap;gap:8px">
      <input class="field" style="flex:1 1 90px" id="bill-kwh" inputmode="decimal" value="${esc(b.kwh)}" placeholder="ك.و.س" aria-label="الاستهلاك بالكيلوواط ساعة">
      <input class="field" style="flex:1 1 90px" id="bill-days" inputmode="numeric" value="${esc(b.days)}" placeholder="عدد الأيام" aria-label="عدد أيام الفاتورة">
      <input class="field" style="flex:1 1 90px" id="bill-amount" inputmode="decimal" value="${esc(b.amount)}" placeholder="المبلغ (دينار)" aria-label="مبلغ الفاتورة بالدينار">
      <button class="btn btn-primary" style="height:42px" data-act="bill-manual">حلّل الأرقام</button></div>`;
  return `
    <span class="panel-title">حلّل فاتورتك</span>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <label class="btn btn-quiet btn-sm" style="${noPhoto ? 'opacity:.5;pointer-events:none' : ''}">
        ${b.busy ? 'جارٍ القراءة…' : 'ارفع صورة'}<input id="bill-file" type="file" accept="image/*" hidden></label>
      <button class="btn btn-quiet btn-sm" data-act="bill-toggle-manual">أدخل الأرقام يدويًا</button>
    </div>
    ${noPhoto ? `<div class="note" style="color:var(--warn)">${esc(b.status.reason_ar)}</div>` : ''}
    ${b.msg ? `<div class="note" style="color:var(--warn)">${esc(b.msg)}</div>` : ''}
    ${manual}${result}
    <div class="note">تُقرأ الصورة مرة واحدة ولا تُحفظ. نحتفظ بالأرقام فقط.</div>`;
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

// ---------------- audit log ----------------

function auditLog() {
  const color = t => ({ T1: 'var(--warn)', STOP: 'var(--red)', OK: 'var(--acc)', MANUAL: 'var(--info)', SCHED: 'var(--info)', T2: 'var(--red)' }[t] || 'var(--muted)');
  const tierLabel = t => ({ MANUAL: 'يدوي', SCHED: 'جدول', OK: 'تم', STOP: 'إيقاف', T0: 'تلقائي', T1: 'موافقة', T2: 'ممنوع' }[t] || t);
  const list = ui.logAll ? st.log : st.log.slice(0, 8);
  const rows = list.map(e => `
    <div class="row log-row">
      <span class="row-time" dir="ltr">${esc(e.clock)}</span>
      <span class="log-tier" style="color:${color(e.tier)}">${esc(tierLabel(e.tier))}</span>
      <span class="row-body">${esc(e.message)}</span>
    </div>`).join('') || '<div class="hint">لا توجد قرارات بعد.</div>';
  const more = st.log.length > 8 ? `<button class="btn btn-quiet btn-sm" style="align-self:flex-start" data-act="log-all">${ui.logAll ? 'اعرض أقل' : `اعرض الكل (${st.log.length})`}</button>` : '';
  return `
    <div class="card-head"><h2>سجل القرارات</h2><span class="hint">كل قرار وسببه وهل وافقت عليه ونتيجته</span></div>
    <div class="rows">${rows}</div>${more}`;
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
          { label: 'الفعلي', data: actual, borderColor: '#2E7D32', backgroundColor: 'rgba(46,125,50,0.08)', fill: 'origin', borderWidth: 2, pointRadius: 0, tension: 0.25 },
          { label: 'دون الوكيل', data: base, borderColor: '#9AA096', borderDash: [5, 5], borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.25 },
        ],
      },
      options: {
        animation: false, maintainAspectRatio: false, responsive: true,
        plugins: { legend: { display: false }, tooltip: { rtl: true } },
        scales: {
          x: { ticks: { color: '#6E736B', maxTicksLimit: 6 }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: '#6E736B', callback: v => scale.unit === 'kW' ? (v / 1000).toFixed(1) + ' kW' : v + ' W' }, grid: { color: '#ECEEEA' } },
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
  WW.render($('sites'), sitesNav());
  WW.render($('agent-status'), agentStatus());
  WW.render($('menu-list'), menuList());
  $('intro').textContent = intro();
  $('demo').hidden = !isSim();
  if (isSim() && (!document.activeElement || document.activeElement.id !== 'scenario-pick')) WW.render($('demo'), demoBar());
  WW.render($('kpis'), kpis());
  WW.render($('goal'), goal());
  WW.render($('approve'), approveSection());
  notifyNewAlerts();
  WW.render($('bill'), bill());
  WW.render($('devices'), devicesSection());
  // The collapsed tools are only rendered while open (less work every second).
  if ($('more-teach').open) {
    WW.render($('teach'), teachSection());
    const last = (st.teach && st.teach.messages.length) ? st.teach.messages[st.teach.messages.length - 1].id : 0;
    if (last !== ui.teach.lastMsg) { ui.teach.lastMsg = last; const c = $('teach-chat'); if (c) c.scrollTop = c.scrollHeight; }
  }
  if ($('more-sched').open) WW.render($('sched'), schedSection());
  if ($('more-analyst').open) WW.render($('analyst'), analystSection());
  WW.render($('log'), auditLog());
  $('meter-clock').textContent = st.clock + (isSim() ? ' · محاكي ×60' : '');
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
  reset: () => { $('menu').open = false; return act(() => WW.post('/reset')); },
  estop: () => act(() => WW.post('/estop')),
  phone: () => { $('menu').open = false; openPhone(); },
  approve: d => act(() => WW.post(`/approvals/${d.id}/approve`)),
  reject: d => act(() => WW.post(`/approvals/${d.id}/reject`)),
  'log-all': () => { ui.logAll = !ui.logAll; renderAll(); },
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
      msg: `حُفظ جدول السخّان ✓ يستهلك ≈ ${fmt(r.total.kwh, 1)} ك.و.س يوميًا (≈ ${fmt(r.total.jod, 2)} دينار، تقديري).` };
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
  tariff: d => act(() => WW.post('/tariff', { type: d.type })),
  'alert-act': d => act(async () => { await WW.post(`/alerts/${d.id}/act`); toast('أُرسل طلب الموافقة. لن نطفئ شيئًا قبل موافقتك.'); }),
  'alert-dismiss': d => act(() => WW.post(`/alerts/${d.id}/dismiss`)),
  'alert-perm': () => Notification.requestPermission().then(renderAll),
  // The "add device" and "add smart plug" wizards live in the phone app (js/app.js, js/plugs.js).
  'open-wiz': () => {
    const f = openPhone();
    const send = () => f.contentWindow && f.contentWindow.postMessage({ type: 'open-wizard' }, location.origin);
    if (f.dataset.loaded) send(); else f.addEventListener('load', send, { once: true });
  },
  'open-plug': () => {
    const f = openPhone();
    const send = () => f.contentWindow && f.contentWindow.postMessage({ type: 'open-plug' }, location.origin);
    if (f.dataset.loaded) send(); else f.addEventListener('load', send, { once: true });
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
// Opening a collapsed tool renders it at once (not on the next second).
for (const id of ['more-teach', 'more-sched', 'more-analyst']) $(id).addEventListener('toggle', () => st && renderAll());
// Close the "More" menu when clicking elsewhere.
document.addEventListener('click', ev => { if (!ev.target.closest('#menu')) $('menu').open = false; });

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
$('phone-drawer').addEventListener('click', ev => { if (ev.target.closest('[data-close]')) $('phone-drawer').hidden = true; });
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') { $('phone-drawer').hidden = true; $('menu').open = false; } });
// Show the address that is inside the QR code (for typing it by hand if needed).
fetch('/api/connect').then(r => r.json()).then(d => { $('connect-url').textContent = d.url; }).catch(() => {});
WW.billStatus().then(x => { ui.bill.status = x; }).catch(() => {});
WWSched.init({ rerender: () => st && renderAll(), refresh, toast });
refresh();
setInterval(refresh, 1000);
