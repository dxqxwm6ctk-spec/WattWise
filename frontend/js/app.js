/* WattWise phone page: owner's view. Simple words, dinars instead of watts, one decision per tap.
   This is the web backup of the Flutter app; both call the same backend API. */

const { esc, fmt } = WW;
const $ = id => document.getElementById(id);

const OWNER = 'أهلًا 👋';   // generic greeting: no personal data
const MAX_W = { lab: 200, building: 12000 }[WW.site] || 4000;
const TYPES = [
  { k: 'ac', label: 'مكيّف' }, { k: 'light', label: 'إنارة' }, { k: 'heater', label: 'مدفأة / سخّان' },
  { k: 'tv', label: 'تلفزيون / شاشة' }, { k: 'washer', label: 'غسالة ملابس / صحون' }, { k: 'pc', label: 'كمبيوتر' },
  { k: 'router', label: 'راوتر / إنترنت' }, { k: 'fridge', label: 'ثلاجة / فريزر', locked: true },
  { k: 'medical', label: 'جهاز طبي', locked: true }, { k: 'other', label: 'جهاز آخر' },
];
const TIPS = [
  'السخّان: شغّله قبل الاستحمام بساعة بدل تركه يعمل طوال اليوم.',
  'أغلق الشبابيك أثناء تشغيل المكيّف، وسننبّهك تلقائيًا إن لاحظنا غير ذلك.',
  'ضبط المكيّف على ٢٤° بدل ٢٢° مريح ويقلّل الاستهلاك.',
];

const ui = {
  tab: 'home', wiz: null, confirmId: null,
  goalText: 'أبقِ فاتورة هذا الشهر تحت 30 دينارًا دون إزعاج أحد في البيت',
  cmd: { text: '', res: null, busy: false, msg: '' }, listening: false,
  heater: { hint: '', res: null, busy: false, msg: '' },
  why: { res: null, busy: false }, rep: { text: '', busy: false },
  bill: { status: null, busy: false, res: null, msg: '', manual: false, kwh: '', days: '', amount: '' },
};
let st = null;

function showError(msg) {
  let el = document.querySelector('.err');
  if (!el) { el = document.createElement('div'); el.className = 'err'; document.body.appendChild(el); }
  el.textContent = msg;
  clearTimeout(showError.h);
  showError.h = setTimeout(() => el.remove(), 3500);
}

// ---------------- home tab ----------------

function statusCard() {
  const a = st.agent, last = st.last_approval;
  const dev = last && last.device_name ? last.device_name : 'الجهاز';
  let m;
  if (!st.online) m = ['#A23A26', '#F0C2B8', 'لا توجد قراءات', 'انقطعت القراءات، فعادت الأجهزة إلى وضعها الطبيعي دون إجراءات تلقائية.'];
  else if (a.estop) m = ['#A23A26', '#F0C2B8', 'WattWise متوقف', 'عادت كل الأجهزة إلى وضعها الطبيعي. لن نقترح شيئًا حتى تعيد تشغيله.'];
  else if (a.safe_mode) m = ['#A23A26', '#F0C2B8', 'لا يوجد اتصال', 'الراوتر مطفأ، لذا لن نطلب موافقة ولن ننفّذ شيئًا.'];
  else if (!st.goal) m = ['#8A5A00', '#E8B23A', 'بانتظار هدف', 'أعطِ الوكيل هدفًا من لوحة التحكم ليبدأ.'];
  else m = {
    analyzing: ['#8A5A00', '#E8B23A', 'جارٍ التحليل', 'لاحظنا جهازًا يعمل في غرفة فارغة. لحظات ونعود إليك.'],
    executing: ['#4A6418', '#D6E8B0', 'جارٍ الإطفاء', 'وصلت موافقتك.'],
    verified: ['#4A6418', '#B8DB7A', 'تم ✓', `أطفأنا ${dev} وأكّد العدّاد ذلك. يظهر التوفير في قسم الفاتورة.`],
    rejected: ['#A23A26', '#F0C2B8', 'حسنًا، لم نغيّر شيئًا', `بقي ${dev} كما هو.`],
    expired: ['#A23A26', '#F0C2B8', 'لم يصل رد', 'لذا لم نفعل شيئًا. عدم الرد لا يعني الموافقة.'],
  }[a.phase] || ['#4A6418', '#D6E8B0', 'كل شيء على ما يرام', 'البيت يعمل بشكل طبيعي ولا يوجد هدر الآن.'];
  return `
    <div style="border-radius:20px;background:#FFFFFF;border:1.5px solid ${m[1]};padding:14px 16px;display:flex;flex-direction:column;gap:4px">
      <span style="font-size:14px;font-weight:700;color:${m[0]}">${m[2]}</span>
      <span style="font-size:14px;line-height:1.7;color:#4A4840">${m[3]}</span>
    </div>`;
}

function anomalyCard() {
  const a = st.anomaly;
  if (!a || !a.open) return '';
  // Already shown as a warning card (alertCards) unless the human dismissed it.
  if (((st.alerts || {}).items || []).some(x => x.active && ['unknown_device', 'anomaly'].includes(x.kind))) return '';
  const msg = a.kind === 'extra'
    ? `جهاز غير معروف يستهلك ≈ ${a.residual_w} واط. تحقّق إن كان هناك جهاز يعمل دون حاجة.`
    : `الاستهلاك أقل من المتوقع بنحو ${-a.residual_w} واط. ربما يوجد جهاز مفصول أو معطّل.`;
  return `
    <div style="border-radius:20px;background:#FFF4D9;border:1.5px solid #E8B23A;padding:14px 16px;display:flex;flex-direction:column;gap:4px">
      <span style="font-size:14px;font-weight:700;color:#8A5A00">استهلاك غير معتاد</span>
      <span style="font-size:14px;line-height:1.7;color:#4A4840">${msg}</span>
    </div>`;
}

// Agent warnings that are still true (high use, near the next tier, danger...).
function alertCards() {
  const items = ((st.alerts || {}).items || []).filter(a => a.active && !a.user_state);
  return items.map(a => {
    const c = a.level === 'danger' ? ['#FBE3DD', '#D9432E', '#7A2A1C'] : ['#FFF4D9', '#E8B23A', '#8A5A00'];
    return `
    <div style="border-radius:20px;background:${c[0]};border:1.5px solid ${c[1]};padding:14px 16px;display:flex;flex-direction:column;gap:6px">
      <span style="font-size:14px;font-weight:700;color:${c[2]}">${esc(a.title)}</span>
      <span style="font-size:14px;line-height:1.7;color:#4A4840">${esc(a.body)}</span>
      <div style="display:flex;gap:8px">
        ${a.can_act ? `<button data-act="alert-act" data-id="${a.id}" class="btn-dark" style="height:42px;flex:1.4;font-size:15px">أطفئه؟</button>` : ''}
        <button data-act="alert-dismiss" data-id="${a.id}" style="height:42px;flex:1;border-radius:14px;border:1.5px solid ${c[1]};background:transparent;font-size:14px;cursor:pointer">تجاهل</button>
      </div>
    </div>`;
  }).join('');
}

function approvalCard() {
  const p = st.pending;
  const pct = (p.expires_in_s / p.timeout_s * 100).toFixed(1);
  return `
    <div style="border-radius:24px;background:#FFF4D9;border:1.5px solid #E8B23A;padding:16px;display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="display:flex;align-items:center;gap:8px;font-size:13px;color:#8A5A00;font-weight:600"><span style="width:8px;height:8px;border-radius:50%;background:#E8A21A;animation:ww-pulse 1s infinite"></span>نحتاج موافقتك</span>
        <span class="mono" style="font-size:13px;color:#8A5A00" dir="ltr">${p.expires_in_s}s</span>
      </div>
      <div style="font-size:19px;font-weight:700;line-height:1.35">${esc(p.title)}</div>
      <div style="font-size:14px;line-height:1.7;color:#4A4536">${esc(p.reason)}</div>
      ${p.details.alternative ? `<div style="font-size:13px;line-height:1.6;color:#6B4A00">البديل: ${esc(p.details.alternative)}</div>` : ''}
      <div style="padding:10px 12px;border-radius:12px;background:#FBE7B5;display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:13px;color:#6B4A00">التوفير التقريبي</span>
        <span class="mono" style="font-size:15px;font-weight:600" dir="ltr">${fmt(p.details.saving_jod_per_hour, 3)} JD / hr</span>
      </div>
      <div style="height:4px;border-radius:2px;background:#F1D58E;overflow:hidden"><div style="height:100%;width:${pct}%;background:#E8A21A;transition:width 1s linear"></div></div>
      <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:8px">
        <button data-act="reject" data-id="${p.id}" style="height:54px;border-radius:18px;border:1.5px solid #D9C38A;background:transparent;color:#1A1B16;font-size:16px;font-weight:600;cursor:pointer">لا، اتركه</button>
        <button data-act="approve" data-id="${p.id}" class="btn-dark" style="height:54px;font-size:16px">نعم، أطفئه</button>
      </div>
      <span style="font-size:11.5px;color:#8A7A55;text-align:center">إن لم تردّ، لن نفعل شيئًا</span>
    </div>`;
}

function homeTab() {
  const w = st.meter.power_w || 0;
  const g = WW.gauge(w, MAX_W);
  const b = st.bill;
  const goalJd = st.goal && st.goal.bill_target_jd;
  const projColor = goalJd && b.bill_projected > goalJd ? '#F2B544' : '#B8F04A';
  const ticks = Array.from({ length: 21 }, (_, i) => {
    const major = i % 5 === 0, lit = i / 20 <= g.frac;
    return `<div style="position:absolute;left:75px;top:80px;width:${major ? 2 : 1}px;height:${major ? 7 : 4}px;background:${lit ? (major ? '#F3F1EA' : '#A9A79D') : (major ? '#5E5C55' : '#33352D')};transform-origin:0 0;transform:rotate(${-90 + i * 9}deg) translate(-50%,-54px)"></div>`;
  }).join('');
  const odo = WW.odometer(b.kwh_now).map((d, i) => `
    <div style="width:15px;height:22px;overflow:hidden;border-radius:3px;background:${i === 5 ? '#3A1712' : '#16170F'};box-shadow:inset 0 5px 5px -4px rgba(0,0,0,.8), inset 0 -5px 5px -4px rgba(0,0,0,.8)">
      <div style="display:flex;flex-direction:column;transform:translateY(${-d * 22}px);transition:transform .9s cubic-bezier(.45,.05,.2,1)">
        ${[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<span class="mono" style="height:22px;display:grid;place-items:center;font-size:13px;font-weight:600;color:${i === 5 ? '#FF8A70' : '#ECEBE4'}">${n}</span>`).join('')}
      </div>
    </div>`).join('');
  const roomMax = MAX_W * 0.6;
  const bars = st.rooms.map(r => {
    const color = r.waste ? '#F2B544' : r.power_w > 0 ? '#B8F04A' : '#3A3C33';
    const base = r.waste ? '#5A4518' : r.power_w > 0 ? '#2E3A1C' : '#23251F';
    return `<div style="flex:1;min-width:0;height:100%;display:flex;align-items:flex-end;justify-content:center"><div style="width:100%;max-width:26px;height:${Math.max(1.5, Math.min(100, r.power_w / roomMax * 100)).toFixed(1)}%;min-height:2px;border-radius:4px 4px 1px 1px;background:linear-gradient(to top,${base},${color});transition:height 1.1s cubic-bezier(.34,1.35,.64,1), background .5s"></div></div>`;
  }).join('');
  const names = st.rooms.map(r => `<span style="flex:1;min-width:0;text-align:center;font-size:9px;color:#A9A79D;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.name)}</span>`).join('');
  const projPct = goalJd ? Math.min(100, b.bill_projected / goalJd * 100) : 0;
  const kw = MAX_W > 1000 ? fmt(w / 1000, 2) : fmt(w, 0);
  return `
    <div style="display:flex;flex-direction:column;gap:12px">
      ${commandCard()}
      <div style="border-radius:24px;background:radial-gradient(120% 90% at 50% 0%,#2A2E22,#15160F);color:#F3F1EA;padding:14px;display:flex;flex-direction:column;gap:10px;box-shadow:0 14px 26px -18px rgba(20,20,10,0.6);animation:ww-rise .6s both">
        <div style="display:flex;align-items:center;gap:10px" dir="ltr">
          <div style="position:relative;width:150px;height:96px;flex:none">
            <div style="position:absolute;left:35px;top:30px;width:80px;height:80px;border-radius:50%;background:${g.color};filter:blur(34px);opacity:.28;transition:background .8s"></div>
            <svg width="150" height="86" viewBox="0 0 150 86" style="position:absolute;inset:0;overflow:visible">
              <path d="M 13 80 A 62 62 0 0 1 137 80" fill="none" stroke="#33352D" stroke-width="9" stroke-linecap="round"></path>
              <path d="M 13 80 A 62 62 0 0 1 137 80" fill="none" stroke="${g.color}" stroke-width="9" stroke-linecap="round" stroke-dasharray="194.8" stroke-dashoffset="${(194.8 * (1 - g.frac)).toFixed(1)}" style="transition:stroke-dashoffset 1.1s cubic-bezier(.34,1.25,.64,1), stroke .8s"></path>
            </svg>
            ${ticks}
            <div style="position:absolute;left:73.5px;top:30px;width:3px;height:50px;border-radius:2px;background:linear-gradient(to top,#F3F1EA,${g.color});transform-origin:50% 100%;transform:rotate(${g.needleDeg}deg);transition:transform 1.1s cubic-bezier(.34,1.45,.64,1)"></div>
            <div style="position:absolute;left:68px;top:73px;width:14px;height:14px;border-radius:50%;background:#15160F;border:2.5px solid #F3F1EA"></div>
            <span class="mono" style="position:absolute;left:6px;top:86px;font-size:9px;color:#8E8C82">0</span>
            <span class="mono" style="position:absolute;right:2px;top:86px;font-size:9px;color:#8E8C82">${MAX_W > 1000 ? MAX_W / 1000 + 'kW' : MAX_W + 'W'}</span>
          </div>
          <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;align-items:flex-end" dir="rtl">
            <span style="font-size:11px;color:#A9A79D">الحمل الآن</span>
            <div style="display:flex;align-items:baseline;gap:4px" dir="ltr"><span class="mono" style="font-size:28px;font-weight:600;line-height:1">${kw}</span><span class="mono" style="font-size:11px;color:#A9A79D">${MAX_W > 1000 ? 'kW' : 'W'}</span></div>
            <div style="display:flex;gap:2px;padding:4px;border-radius:7px;background:#0A0B08;border:1px solid #2A2C25" dir="ltr">${odo}</div>
            <span style="font-size:10px;color:#8E8C82">ك.و.س هذا الشهر</span>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <div style="height:40px;display:flex;align-items:flex-end;gap:6px;border-bottom:1px solid #33352D">${bars}</div>
          <div style="display:flex;gap:6px">${names}</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;padding-top:8px;border-top:1px solid #2A2C25">
          <div style="display:flex;justify-content:space-between;align-items:baseline">
            <span style="font-size:12px;color:#A9A79D">الفاتورة حتى الآن</span>
            <span class="mono" style="font-size:12px;white-space:nowrap" dir="ltr"><span style="font-size:18px;font-weight:600">${fmt(b.bill_now, 2)}</span> JD</span>
          </div>
          ${goalJd ? `
          <div style="height:4px;border-radius:2px;background:#33352D;overflow:hidden;display:flex"><div style="width:${projPct.toFixed(1)}%;background:${projColor};transition:width 1s"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:11px;color:#8E8C82"><span>متوقّع آخر الشهر</span><span class="mono" style="white-space:nowrap" dir="ltr"><span style="color:${projColor}">${fmt(b.bill_projected, 1)}</span> / ${fmt(goalJd)} JD</span></div>` : ''}
          <span style="font-size:12px;line-height:1.55;color:#C8E68A">${esc(b.message)}</span>
        </div>
      </div>
      ${st.pending ? approvalCard() : statusCard()}
      ${alertCards()}
      ${anomalyCard()}
    </div>`;
}

// ---------------- devices tab (with add-device wizard) ----------------

function wizard() {
  const z = ui.wiz;
  const learn = st.learn;
  const learnedW = learn && learn.status === 'done' ? learn.learned_w : 0;
  const measuring = learn && learn.status === 'measuring';
  const t = TYPES.find(x => x.k === z.type);
  const chip = sel => `border:1.5px solid ${sel ? '#1A1B16' : '#E2DFD4'};background:${sel ? '#1A1B16' : '#FFFFFF'};color:${sel ? '#F3F1EA' : '#1A1B16'}`;
  const canNext = [!!z.type, !!z.room, learnedW > 0, true][z.step];
  const titles = ['ما نوع الجهاز؟', 'أين يوجد؟', 'لنتعرّف عليه', 'ما المسموح لـWattWise؟'];
  let body = '';
  if (z.step === 0) {
    body = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">${TYPES.map(x =>
      `<button data-act="wiz-type" data-k="${x.k}" style="min-height:52px;border-radius:16px;${chip(z.type === x.k)};font-size:14px;font-weight:600;cursor:pointer;padding:8px">${x.label}</button>`).join('')}</div>`;
  } else if (z.step === 1) {
    const ph = t && z.room ? t.label.split(' / ')[0] + ' ' + (st.rooms.find(r => r.id === z.room) || {}).name : 'اسم الجهاز';
    body = `<div style="display:flex;flex-direction:column;gap:12px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">${st.rooms.map(r =>
        `<button data-act="wiz-room" data-id="${esc(r.id)}" style="min-height:48px;border-radius:16px;${chip(z.room === r.id)};font-size:14px;font-weight:600;cursor:pointer">${esc(r.name)}</button>`).join('')}</div>
      <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:#77756C">الاسم (اختياري)
        <input id="wiz-name" value="${esc(z.name)}" placeholder="${esc(ph)}" style="height:50px;border-radius:16px;border:1.5px solid #E2DFD4;background:#FFFFFF;padding:0 14px;font-size:15px;color:#1A1B16;outline:none">
      </label></div>`;
  } else if (z.step === 2) {
    body = `<div style="display:flex;flex-direction:column;gap:12px">
      <div style="border-radius:20px;background:#FFFFFF;padding:16px;display:flex;flex-direction:column;gap:10px;font-size:14px;line-height:1.7">
        <span>١. تأكّد أن الجهاز موصول بمقبس ذكي (يركّبه كهربائي).</span>
        <span>٢. عندما تكون جاهزًا، شغّل الجهاز من زرّه ثم اضغط «شغّلته».</span>
        <span style="color:#77756C;font-size:13px">يقيس WattWise قفزة الواط على العدّاد الرئيسي، وهذه هي بصمة الجهاز.</span>
      </div>
      ${!measuring && !learnedW ? `<button data-act="wiz-learn" class="btn-dark" style="height:56px;font-size:16px">شغّلته</button>` : ''}
      ${measuring ? `<div style="height:56px;border-radius:18px;background:#E6F5C8;display:flex;align-items:center;justify-content:center;gap:10px;font-size:15px;color:#4A6418;font-weight:600"><span style="width:10px;height:10px;border-radius:50%;background:#5E7A1C;animation:ww-pulse 0.8s infinite"></span>جارٍ القياس…</div>` : ''}
      ${learnedW ? `<div style="border-radius:20px;background:#E6F5C8;padding:16px;display:flex;justify-content:space-between;align-items:center">
          <div style="display:flex;flex-direction:column;gap:2px">
            <span style="font-size:13px;color:#4A6418">تعرّفنا عليه ✓</span>
            <span class="mono" style="font-size:26px;font-weight:500" dir="ltr">+${learnedW} W</span>
            <span style="font-size:12px;color:#4A6418">≈ ${fmt(learnedW / 1000 * st.bill.price_jod_per_kwh, 3)} دينار في الساعة</span>
          </div>
          <button data-act="wiz-learn" style="height:44px;padding:0 14px;border-radius:14px;border:1.5px solid #B8DB7A;background:transparent;font-size:13px;font-weight:600;cursor:pointer">أعد القياس</button>
        </div>` : ''}
      </div>`;
  } else {
    body = t && t.locked
      ? `<div style="border-radius:20px;background:#FBE3DD;padding:16px;font-size:14px;line-height:1.7;color:#7A2A1C">هذا جهاز حرج (T2). سنراقب استهلاكه فقط، ولا يمكن لأحد (لا الوكيل ولا التطبيق) إطفاؤه. محمي برمجيًا.</div>`
      : `<div style="border-radius:20px;background:#FFFFFF;padding:16px;display:flex;align-items:center;gap:12px">
          <div style="flex:1;display:flex;flex-direction:column;gap:4px">
            <span style="font-size:15px;font-weight:600">يقترح الوكيل إطفاءه عند وجود هدر</span>
            <span style="font-size:12.5px;line-height:1.6;color:#77756C">يسألك دائمًا قبل أي إجراء. إن عطّلت هذا الخيار، يبقى التحكم يدويًا فقط.</span>
          </div>
          <button data-act="wiz-allow" style="width:52px;height:32px;border-radius:16px;border:none;background:${z.allow ? '#1A1B16' : '#D8D5CA'};position:relative;cursor:pointer;flex:none;padding:0">
            <span style="position:absolute;top:4px;${z.allow ? 'left' : 'right'}:4px;width:24px;height:24px;border-radius:50%;background:${z.allow ? '#B8F04A' : '#FFFFFF'};box-shadow:0 1px 3px rgba(0,0,0,0.2)"></span>
          </button>
        </div>`;
  }
  return `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#77756C"><span>جهاز جديد</span><span class="mono" dir="ltr">${z.step + 1} / 4</span></div>
        <div style="height:4px;border-radius:2px;background:#E2DFD4;overflow:hidden;display:flex"><div style="width:${(z.step + 1) * 25}%;background:#1A1B16"></div></div>
      </div>
      <span style="font-size:22px;font-weight:700">${titles[z.step]}</span>
      ${body}
      <div style="display:grid;grid-template-columns:1fr 1.5fr;gap:8px;padding-top:4px">
        <button data-act="wiz-back" class="btn-line" style="height:52px;font-size:15px">${z.step === 0 ? 'إلغاء' : 'رجوع'}</button>
        <button data-act="wiz-next" style="height:52px;border-radius:18px;border:none;background:${canNext ? '#1A1B16' : '#D8D5CA'};color:${canNext ? '#F3F1EA' : '#8E8C82'};font-size:15px;font-weight:700;cursor:pointer">${z.step === 3 ? 'إضافة الجهاز' : 'التالي'}</button>
      </div>
    </div>`;
}

function devicesTab() {
  if (ui.plugWiz) return plugWizard();   // js/plugs.js
  if (ui.wiz) return wizard();
  const onCount = st.devices.filter(d => d.is_on).length;
  const confirmDev = st.devices.find(d => d.id === ui.confirmId);
  const items = st.devices.map(d => {
    const on = d.is_on, locked = d.tier === 'T2';
    return `
      <div style="border-radius:18px;background:#FFFFFF;padding:12px 14px;display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;align-items:center;gap:12px">
          <div style="flex:1;display:flex;flex-direction:column;gap:2px;min-width:0">
            <span style="font-size:15px;font-weight:600">${esc(d.name)}</span>
            <span style="font-size:12px;color:#77756C">${esc(d.room_name)} · ${locked ? 'محمي · يعمل دائمًا' : on ? 'يعمل' : 'مطفأ'}</span>
          </div>
          <button data-act="toggle" data-id="${esc(d.id)}" aria-label="${esc(d.name)}" style="width:52px;height:32px;border-radius:16px;border:none;background:${locked ? '#F0C2B8' : on ? '#1A1B16' : '#D8D5CA'};position:relative;cursor:pointer;flex:none;padding:0">
            <span style="position:absolute;top:4px;${on ? 'left' : 'right'}:4px;width:24px;height:24px;border-radius:50%;background:${locked ? '#D9432E' : on ? '#B8F04A' : '#FFFFFF'};box-shadow:0 1px 3px rgba(0,0,0,0.2)"></span>
          </button>
        </div>
        ${plugLine(d)}
      </div>`;
  }).join('');
  return `
    <div style="display:flex;flex-direction:column;gap:8px">
      <button data-act="open-plug" style="height:52px;border-radius:18px;border:none;background:#1A1B16;color:#F3F1EA;font-size:15px;font-weight:700;cursor:pointer">🔌 + إضافة مقبس ذكي (Wi-Fi)</button>
      <button data-act="open-wiz" style="height:52px;border-radius:18px;border:1.5px dashed #B9B6AA;background:transparent;color:#1A1B16;font-size:15px;font-weight:600;cursor:pointer">+ إضافة جهاز عبر العدّاد الرئيسي</button>
      ${st.agent.safe_mode ? `<div style="border-radius:18px;background:#FFF4D9;border:1.5px solid #E8B23A;padding:14px 16px;font-size:13.5px;line-height:1.6;color:#6B4A00">الراوتر مطفأ، وفي الواقع سينقطع التطبيق هنا. WattWise في الوضع الآمن ولن ينفّذ شيئًا.</div>` : ''}
      ${confirmDev ? `
      <div style="border-radius:20px;background:#FFF4D9;border:1.5px solid #E8B23A;padding:16px;display:flex;flex-direction:column;gap:10px">
        <span style="font-size:15px;font-weight:700">إطفاء ${esc(confirmDev.name)}؟</span>
        <span style="font-size:13.5px;line-height:1.6;color:#4A4536">سينقطع التطبيق ولن تصلك طلبات موافقة حتى تعيد تشغيله من الجهاز نفسه.</span>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <button data-act="confirm-cancel" style="height:48px;border-radius:16px;border:1.5px solid #D9C38A;background:transparent;font-size:15px;font-weight:600;cursor:pointer">لا</button>
          <button data-act="confirm-off" data-id="${esc(confirmDev.id)}" class="btn-dark" style="height:48px;font-size:15px">نعم، أطفئه</button>
        </div>
      </div>` : ''}
      <span class="sub">يعمل ${onCount} من ${st.devices.length}</span>
      ${items}
    </div>`;
}

// ---------------- bill tab ----------------

function billTab() {
  const b = st.bill, s = st.savings;
  const opts = b.types.map(o => `<button data-act="tariff" data-type="${o.key}" style="height:44px;border-radius:12px;border:none;background:${b.type === o.key ? '#FFFFFF' : 'transparent'};color:${b.type === o.key ? '#1A1B16' : '#77756C'};font-size:14.5px;font-weight:700;cursor:pointer;box-shadow:${b.type === o.key ? '0 1px 4px rgba(0,0,0,0.12)' : 'none'}">${esc(o.label)}</button>`).join('');
  const tiers = b.segments.map(t => {
    const range = t.to_kwh === null ? `أكثر من ${t.from_kwh} ك.و.س` : `${t.from_kwh + 1}–${t.to_kwh} ك.و.س`;
    return `<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;background:${t.active ? '#1A1B16' : '#F3F1EA'}">
      <span style="font-size:13px;flex:1;color:${t.active ? '#F3F1EA' : '#1A1B16'}">${range}</span>
      <span class="mono" style="font-size:13px;font-weight:600;color:${t.active ? '#F3F1EA' : '#1A1B16'}">${t.fils} فلس</span></div>`;
  }).join('');
  const breakdown = st.breakdown.map(x => `
    <div style="display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;justify-content:space-between;font-size:14px"><span>${esc(x.name)}</span><span class="mono" dir="ltr">${fmt(x.jod, 2)} JD</span></div>
      <div style="height:6px;border-radius:3px;background:#ECE9DF;overflow:hidden;display:flex"><div style="width:${x.pct}%;background:#1A1B16"></div></div>
    </div>`).join('') || '<span class="sub">لا توجد بيانات كافية بعد.</span>';
  return `
    <div style="display:flex;flex-direction:column;gap:12px">
      ${billExtras()}
      <div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:12px">
        <span class="sub">نوع اشتراكك (مذكور في فاتورتك)</span>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:4px;border-radius:16px;background:#F3F1EA">${opts}</div>
        <span style="font-size:12.5px;line-height:1.6;color:#77756C">${esc(b.who)}</span>
        <div style="display:flex;flex-direction:column;gap:6px">${tiers}</div>
        <span style="font-size:13px;line-height:1.6">${esc(b.message)}</span>
      </div>
      <div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:14px">
        <span class="sub">توزيع التكلفة (حسب بصمة كل جهاز)</span>
        ${breakdown}
      </div>
      <div style="border-radius:22px;background:#E6F5C8;padding:18px;display:flex;flex-direction:column;gap:6px">
        <span style="font-size:13px;color:#4A6418">التوفير (مُقاس فعليًا)</span>
        <span class="mono" style="font-size:30px;font-weight:500" dir="ltr">${fmt(s.jod, 3)} JD</span>
        <span style="font-size:12.5px;color:#4A6418">${fmt(s.kwh, 2)} ك.و.س · ${s.co2_kg === null ? '—' : fmt(s.co2_kg, 2)} كغ CO₂ أقل</span>
      </div>
      ${st.forecast ? `<div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:6px">
        <span class="sub">المتوقّع للساعات الـ${st.forecast.steps.length} القادمة</span>
        <span class="mono" style="font-size:22px;font-weight:500" dir="ltr">${fmt(st.forecast.jod, 2)} JD · ${fmt(st.forecast.kwh, 1)} kWh</span>
        <span style="font-size:12.5px;color:#77756C">${st.forecast.accuracy.hours ? `خطأ التوقّع ≈ ${fmt(st.forecast.accuracy.mean_err_pct, 0)}% (مقاس بالعدّاد)` : 'جارٍ قياس دقة التوقّع'}</span>
      </div>` : ''}
      <span class="sub" style="padding-top:4px">نصائح (لا ننفّذها تلقائيًا)</span>
      ${TIPS.map(t => `<div class="box" style="font-size:14px;line-height:1.65">${t}</div>`).join('')}
    </div>`;
}

// ---------------- new design: commands, schedules, goal, why, report ----------------

const micOk = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
const field = 'height:48px;border-radius:16px;border:1.5px solid #E2DFD4;background:#FFFFFF;padding:0 14px;font-size:15px;font-family:inherit;color:#1A1B16;outline:none;min-width:0';
const estText = e => e ? `≈ ${fmt(e.kwh, 1)} ك.و.س/يوم · ≈ ${fmt(e.jod, 2)} دينار/يوم (تقديري، غير مُقاس)` : '';

// Typed or spoken order: the server understands it, the Policy Guard checks it, you confirm.
function commandCard() {
  const c = ui.cmd, r = c.res;
  const result = !r ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <span style="font-size:14px;line-height:1.6">${esc(r.clarify || r.reply)}</span>
      ${r.items.map(i => `<div style="display:flex;gap:10px;align-items:baseline;padding:10px 12px;border-radius:12px;background:#F3F1EA">
        <span style="font-weight:700;color:${i.ok ? '#4A6418' : '#A23A26'}">${i.ok ? '✓' : '✕'}</span>
        <span style="display:flex;flex-direction:column;gap:2px"><span style="font-size:14px">${esc(i.label)}</span><span style="font-size:12px;color:#77756C">${esc(i.why)}</span></span></div>`).join('')}
      <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:8px">
        <button data-act="cmd-cancel" class="btn-line" style="height:48px;border-radius:16px;font-size:15px">لا</button>
        ${r.items.some(i => i.ok) ? '<button data-act="cmd-run" class="btn-dark" style="height:48px;border-radius:16px;font-size:15px">نعم، نفّذ</button>' : ''}
      </div></div>`;
  return `<div style="border-radius:22px;background:#FFFFFF;padding:14px;display:flex;flex-direction:column;gap:10px">
      <div style="display:flex;gap:8px">
        <input id="cmd-text" value="${esc(c.text)}" aria-label="تحدّث أو اكتب أمرك للوكيل" placeholder="مثلًا: أطفئ مكيّف غرفة النوم" style="flex:1;${field}">
        ${micOk ? `<button data-act="cmd-mic" aria-label="تحدّث" style="width:48px;height:48px;border-radius:16px;border:1.5px solid #1A1B16;background:${ui.listening ? '#E8553F' : 'transparent'};color:${ui.listening ? '#fff' : 'inherit'};font-size:18px;cursor:pointer;flex:none">🎤</button>` : ''}
        <button data-act="cmd-parse" class="btn-dark" style="height:48px;padding:0 14px;border-radius:16px;font-size:14px;flex:none">${c.busy ? 'جارٍ الفهم…' : 'نفّذ'}</button>
      </div>${result}
      ${c.msg ? `<span style="font-size:13.5px;color:#4A6418;font-weight:600">${esc(c.msg)}</span>` : ''}
    </div>`;
}

function schedTab() {
  const h = ui.heater, hr = h.res;
  const hasHeater = st.devices.some(d => d.kind === 'heater' && d.tier === 'T1' && !d.sensitive);
  const heater = !hasHeater ? '' : `<div style="border-radius:22px;background:#E6F5C8;padding:18px;display:flex;flex-direction:column;gap:10px">
      <span style="font-size:17px;font-weight:700">سخّان الماء الذكي</span>
      <span style="font-size:13px;line-height:1.65;color:#4A6418">من أكبر الأحمال. نشغّله قبل الاستحمام فقط، ولا يعمل أكثر من ٣ ساعات متواصلة.</span>
      <input id="heater-hint" value="${esc(h.hint)}" aria-label="متى تستحمّون؟" placeholder="متى تستحمّون؟ مثلًا: الصباح ٦:٣٠" style="${field};border-color:#B8DB7A">
      <button data-act="heater-suggest" class="btn-dark" style="height:50px;border-radius:16px;font-size:15px">${h.busy ? 'جارٍ التخطيط…' : 'اقترح جدولًا للسخّان'}</button>
      ${hr ? `<div style="display:flex;flex-direction:column;gap:8px">
        <span style="font-size:14px;line-height:1.6">${esc(hr.reply)}</span>
        ${hr.items.map(i => `<div style="padding:10px 12px;border-radius:12px;background:#FFFFFF;display:flex;flex-direction:column;gap:2px">
          <span class="mono" style="font-size:14px;font-weight:600" dir="ltr">${esc(i.on_time)} → ${esc(i.off_time)}</span>
          <span style="font-size:13px">${esc(i.why)}</span><span style="font-size:12px;color:#5E5C55">${estText(i.estimate)}</span></div>`).join('')}
        <span style="font-size:13px;color:#4A6418;font-weight:600">المجموع ≈ ${fmt(hr.total.kwh, 1)} ك.و.س يوميًا ≈ ${fmt(hr.total.jod, 2)} دينار (تقديري، غير مُقاس)</span>
        <div style="display:grid;grid-template-columns:1fr 1.4fr;gap:8px">
          <button data-act="heater-cancel" class="btn-line" style="height:48px;border-radius:16px;font-size:15px;border-color:#B8DB7A">لا</button>
          ${hr.items.length ? '<button data-act="heater-apply" class="btn-dark" style="height:48px;border-radius:16px;font-size:15px">نعم، اعتمده</button>' : ''}
        </div></div>` : ''}
      ${h.msg ? `<span style="font-size:13.5px;line-height:1.6;color:#4A6418;font-weight:600">${esc(h.msg)}</span>` : ''}
    </div>`;
  // Home / Building / Lab, devices grouped by room, detailed schedules (js/schedule.js).
  const showHeater = WWSched.state.site === WW.site && !WWSched.state.dev;
  return `<div style="display:flex;flex-direction:column;gap:12px">
      ${WWSched.render({ theme: 'light', layout: 'drill' })}
      ${showHeater ? heater : ''}
    </div>`;
}

// Goal in plain words, "why is my bill like this?" and the weekly report (top of the bill tab).
function billExtras() {
  const p = st.plan, w = ui.why.res, rep = ui.rep;
  const plan = !(st.goal && p && p.steps.length) ? '' : `<div style="display:flex;flex-direction:column;gap:8px;padding-top:4px">
      ${p.summary ? `<span style="font-size:14px;line-height:1.65">${esc(p.summary)}</span>` : ''}
      ${p.steps.map((x, i) => {
        const t1 = (p.tags || [])[i] === 'T1';
        return `<div style="padding:10px 12px;border-radius:12px;background:#F3F1EA;display:flex;flex-direction:column;gap:2px">
          <span style="font-size:11px;color:${t1 ? '#8A5A00' : '#4A6418'};font-weight:600">${t1 ? 'T1 · بموافقتك' : 'T0 · تلقائي'}</span>
          <span style="font-size:13.5px;line-height:1.55">${esc(x)}</span></div>`;
      }).join('')}</div>`;
  return `
    <div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:10px">
      <span class="sub">هدفك بكلماتك</span>
      ${st.goal ? `<span style="font-size:15px;font-weight:600;line-height:1.5">«${esc(st.goal.text)}»</span>` : ''}
      <input id="goal-text" value="${esc(ui.goalText)}" aria-label="اكتب هدفك بكلماتك" placeholder="مثلًا: الفاتورة تحت ٢٥ دينارًا" style="${field};height:50px">
      <button data-act="set-goal" class="btn-dark" style="height:50px;border-radius:16px;font-size:15px">${st.goal ? 'غيّر الهدف' : 'حوّله إلى خطة'}</button>
      ${plan}
    </div>
    <div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:10px">
      <button data-act="why" class="btn-line" style="height:50px;border-radius:16px;border-color:#1A1B16;font-size:15px;font-weight:700">${ui.why.busy ? 'جارٍ التحليل…' : w ? 'أعد التحليل' : 'لماذا الفاتورة بهذا المبلغ؟'}</button>
      ${w ? `<div style="display:flex;flex-direction:column;gap:8px">
        <span style="font-size:14px;line-height:1.65">${esc(w.headline)}</span>
        ${w.causes.map(c => `<div style="padding:10px 12px;border-radius:12px;background:#F3F1EA;display:flex;flex-direction:column;gap:2px">
          <span style="font-size:13.5px;font-weight:600">${esc(c.what)}</span><span style="font-size:12.5px;line-height:1.55;color:#5E5C55">${esc(c.evidence)}</span></div>`).join('')}
        <span style="font-size:13.5px;line-height:1.6;color:#4A6418">${esc(w.action)}</span>
        <span style="font-size:11.5px;color:#77756C">${esc(w.note)}</span></div>` : ''}
    </div>
    ${billCard()}
    <div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:10px">
      <button data-act="report" class="btn-line" style="height:50px;border-radius:16px;border-color:#1A1B16;font-size:15px;font-weight:700">${rep.busy ? 'جارٍ التجهيز…' : rep.text ? 'جهّز تقريرًا جديدًا' : 'جهّز التقرير الأسبوعي'}</button>
      ${rep.text ? `<div style="white-space:pre-wrap;font-size:12.5px;line-height:1.75;padding:12px;border-radius:12px;background:#F3F1EA;max-height:220px;overflow:auto">${esc(rep.text)}</div>
        <a href="/api/sites/${WW.site}/weekly.txt" download class="btn-dark" style="height:46px;border-radius:14px;font-size:14px;display:grid;place-items:center;text-decoration:none">تنزيل الملف</a>` : ''}
    </div>`;
}

// Bill photo from the camera or the gallery. Claude reads it when there is a key; otherwise type 3 numbers.
function billCard() {
  const b = ui.bill, r = b.res, noPhoto = b.status && !b.status.photo;
  const bn = r && r.bill;
  const nums = !bn ? '' : [
    bn.kwh != null && `${fmt(bn.kwh, 0)} ك.و.س`, bn.days && `${bn.days} يوم`,
    bn.amount_jod != null && `${fmt(bn.amount_jod, 2)} دينار`,
  ].filter(Boolean).map(x => `<span style="padding:4px 10px;border-radius:999px;background:#F3F1EA;font-size:12.5px;font-weight:600">${esc(x)}</span>`).join('');
  const pick = (id, label, cap) => `<label class="btn-line" style="flex:1;height:48px;border-radius:16px;border-color:#1A1B16;font-size:14px;display:grid;place-items:center;cursor:pointer;${noPhoto || b.busy ? 'opacity:.45;pointer-events:none' : ''}">
      ${label}<input id="${id}" type="file" accept="image/*" ${cap ? 'capture="environment"' : ''} hidden></label>`;
  const manual = !(b.manual || noPhoto) ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <input id="bill-kwh" inputmode="decimal" value="${esc(b.kwh)}" placeholder="الاستهلاك (ك.و.س)" aria-label="الاستهلاك بالكيلوواط ساعة" style="${field}">
      <div style="display:flex;gap:8px">
        <input id="bill-days" inputmode="numeric" value="${esc(b.days)}" placeholder="عدد الأيام" aria-label="عدد أيام الفاتورة" style="${field};flex:1">
        <input id="bill-amount" inputmode="decimal" value="${esc(b.amount)}" placeholder="المبلغ (دينار)" aria-label="مبلغ الفاتورة بالدينار" style="${field};flex:1">
      </div>
      <button data-act="bill-manual" class="btn-dark" style="height:48px;border-radius:16px;font-size:15px">حلّل الأرقام</button></div>`;
  const result = !r ? '' : `<div style="display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;flex-wrap:wrap;gap:6px">${nums}</div>
      ${r.explanation.map(x => `<span style="font-size:14px;line-height:1.65">${esc(x)}</span>`).join('')}
      ${r.checks.map(x => `<div style="padding:10px 12px;border-radius:12px;background:#F3F1EA;font-size:12.5px;line-height:1.55;color:#5E5C55">${esc(x)}</div>`).join('')}
      ${r.ideas.map(x => `<span style="font-size:13.5px;line-height:1.6;color:#4A6418">• ${esc(x)}</span>`).join('')}
      <span style="font-size:11.5px;color:#77756C">${esc(r.note)}</span></div>`;
  return `
    <div style="border-radius:22px;background:#FFFFFF;padding:18px;display:flex;flex-direction:column;gap:10px">
      <span class="sub">حلّل فاتورتك من صورة</span>
      <div style="display:flex;gap:8px">${pick('bill-cam', b.busy ? 'جارٍ القراءة…' : '📷 صوّر الفاتورة', true)}${pick('bill-gal', 'من المعرض', false)}</div>
      ${noPhoto ? `<span style="font-size:12.5px;line-height:1.55;color:#8A5A00">${esc(b.status.reason_ar)}</span>`
        : `<button data-act="bill-toggle-manual" style="background:none;border:none;color:#5E5C55;font-size:13px;text-decoration:underline;cursor:pointer;font-family:inherit">أو أدخل الأرقام يدويًا</button>`}
      ${b.msg ? `<span style="font-size:12.5px;line-height:1.55;color:#8A5A00">${esc(b.msg)}</span>` : ''}
      ${manual}${result}
    </div>`;
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

let recog = null;
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  if (recog) { try { recog.stop(); } catch (e) { /* already stopped */ } return; }
  recog = new SR();
  recog.lang = 'ar-JO'; recog.interimResults = false; recog.maxAlternatives = 1;
  recog.onresult = e => { ui.cmd.text = e.results[0][0].transcript; parseCommand(); };
  recog.onerror = () => showError('الميكروفون غير متاح هنا. اكتب الأمر بدلًا من ذلك.');
  recog.onend = () => { recog = null; ui.listening = false; renderAll(); };
  ui.listening = true; renderAll();
  try { recog.start(); } catch (e) { recog = null; ui.listening = false; }
}

async function parseCommand() {
  const text = ui.cmd.text.trim();
  if (!text || ui.cmd.busy) return;
  ui.cmd.busy = true; ui.cmd.msg = ''; renderAll();
  try { ui.cmd.res = await WW.post('/command/parse', { text }); } catch (e) { showError(e.message); }
  ui.cmd.busy = false; renderAll();
}

const newHandlers = {
  'set-goal': () => act(() => WW.post('/goal', { text: ui.goalText.trim() })),
  'cmd-parse': () => parseCommand(),
  'cmd-mic': () => listen(),
  'cmd-cancel': () => { ui.cmd.res = null; renderAll(); },
  'cmd-run': () => act(async () => {
    const r = await WW.post('/command/run', { text: ui.cmd.text });
    ui.cmd = { text: '', res: null, busy: false, msg: r.done.length ? 'تم: ' + r.done.join('، ') : 'لم يُنفَّذ شيء.' };
  }),
  'heater-suggest': async () => {
    ui.heater.busy = true; ui.heater.msg = ''; renderAll();
    try { ui.heater.res = await WW.post('/heater/suggest', { hint: ui.heater.hint }); } catch (e) { showError(e.message); }
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
    try { ui.why.res = await WW.api('GET', `/api/sites/${WW.site}/why`); } catch (e) { showError(e.message); }
    ui.why.busy = false; renderAll();
  },
  'bill-toggle-manual': () => { ui.bill.manual = !ui.bill.manual; renderAll(); },
  'bill-manual': () => {
    if (!(Number(ui.bill.kwh) > 0)) { ui.bill.msg = 'أدخل الاستهلاك بالكيلوواط ساعة (ك.و.س) من الفاتورة.'; renderAll(); return; }
    return billSend(WW.billManual(ui.bill));
  },
  report: async () => {
    ui.rep.busy = true; renderAll();
    try { ui.rep.text = await (await fetch(`/api/sites/${WW.site}/weekly.txt`)).text(); } catch (e) { showError(e.message); }
    ui.rep.busy = false; renderAll();
  },
};

document.addEventListener('input', ev => {
  const id = ev.target.id, v = ev.target.value;
  if (id === 'goal-text') ui.goalText = v;
  if (id === 'cmd-text') ui.cmd.text = v;
  if (id === 'heater-hint') ui.heater.hint = v;
  if (id === 'bill-kwh') ui.bill.kwh = v;
  if (id === 'bill-days') ui.bill.days = v;
  if (id === 'bill-amount') ui.bill.amount = v;
});
document.addEventListener('change', ev => {
  if ((ev.target.id === 'bill-cam' || ev.target.id === 'bill-gal') && ev.target.files[0]) {
    const file = ev.target.files[0];
    ev.target.value = '';
    billSend(WW.billPhoto(file));
  }
});
document.addEventListener('keydown', ev => { if (ev.key === 'Enter' && ev.target.id === 'cmd-text') parseCommand(); });

// ---------------- safety tab ----------------

function safetyTab() {
  const c = st.comfort;
  const rules = [
    'لا يُطفئ الوكيل أي جهاز دون موافقتك، ويمكنك التحكم بأي جهاز يدويًا.',
    `تبقى حرارة أي غرفة مشغولة ضمن ${fmt(c.min_c)}–${fmt(c.max_c)}°.`,
    'إذا انقطع الإنترنت أو الراوتر أو حدث عطل، يبقى كل شيء على وضعه الطبيعي دون أي إجراء تلقائي.',
    'نعرف فقط إن كانت الغرفة مشغولة أم فارغة، بلا كاميرات.',
  ];
  return `
    <div style="display:flex;flex-direction:column;gap:10px">
      <span class="sub">أجهزة لا نلمسها أبدًا</span>
      <div class="box" style="font-size:14px;line-height:1.7">الثلاجة وإنذار الحريق والأجهزة الطبية وإنارة الطوارئ: ممنوعة برمجيًا، حتى لو وافقت.</div>
      <span class="sub" style="padding-top:4px">قواعد البيت</span>
      ${rules.map((r, i) => `<div class="box" style="display:flex;gap:12px"><span class="mono" style="font-size:11px;color:#5E7A1C;padding-top:3px">0${i + 1}</span><span style="font-size:14px;line-height:1.6">${r}</span></div>`).join('')}
      ${st.agent.estop
        ? `<button data-act="reset" class="btn-dark" style="height:58px;border-radius:20px;font-size:16px">أعد تشغيل WattWise</button>`
        : `<button data-act="estop" style="height:58px;border-radius:20px;border:none;background:#D9432E;color:#fff;font-size:16px;font-weight:700;cursor:pointer">أوقف WattWise الآن</button>`}
    </div>`;
}

// ---------------- render loop ----------------

function renderAll() {
  const header = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div style="display:flex;flex-direction:column;gap:2px">
        <span class="sub">${esc(st.site_name)}</span>
        <span style="font-size:21px;font-weight:700">${OWNER}</span>
      </div>
      <div class="mono" style="width:40px;height:40px;border-radius:12px;background:#1A1B16;color:#B8F04A;display:grid;place-items:center;font-weight:700;font-size:14px">W/</div>
    </div>`;
  const body = { home: homeTab, devices: devicesTab, sched: schedTab, bill: billTab, safety: safetyTab }[ui.tab]();
  WW.render($('content'), header + body);
  WW.render($('tabs'), [['home', 'البيت'], ['devices', 'الأجهزة'], ['sched', 'الجدولة'], ['bill', 'الفاتورة'], ['safety', 'الأمان']].map(([k, label]) =>
    `<button class="tab" data-act="tab" data-k="${k}" style="color:${ui.tab === k ? '#1A1B16' : '#9A988E'}"><i style="background:${ui.tab === k ? '#1A1B16' : 'transparent'}"></i>${label}</button>`).join(''));
}

let lastPendingId = null;
async function refresh() {
  try {
    st = await WW.getState();
    WWSched.sync(st);
    // A new approval card: bring it to the front and buzz the phone (judge's phone in the demo).
    const pid = st.pending ? st.pending.id : null;
    if (pid && pid !== lastPendingId && !ui.wiz) {
      ui.tab = 'home';
      if (navigator.vibrate) { try { navigator.vibrate([250, 120, 250]); } catch (e) { /* not allowed yet */ } }
    }
    lastPendingId = pid;
    renderAll();
  } catch (e) { console.error(e); }
}
async function act(fn) {
  try { await fn(); } catch (e) { showError(e.message); }
  refresh();
}

function openWizard() {
  ui.tab = 'devices';
  ui.plugWiz = null;
  ui.wiz = { step: 0, type: null, room: null, name: '', allow: true };
  if (st) renderAll();
}
function closeWizard() {
  ui.wiz = null;
  act(() => WW.api('DELETE', `/api/sites/${WW.site}/learn`));
}

WW.onAction({
  onError: e => showError(e.message),
  ...newHandlers,
  ...WWSched.actions,
  tab: d => { ui.tab = d.k; renderAll(); },
  approve: d => act(() => WW.post(`/approvals/${d.id}/approve`)),
  'alert-act': d => act(() => WW.post(`/alerts/${d.id}/act`)),
  'alert-dismiss': d => act(() => WW.post(`/alerts/${d.id}/dismiss`)),
  reject: d => act(() => WW.post(`/approvals/${d.id}/reject`)),
  estop: () => act(() => WW.post('/estop')),
  reset: () => act(() => WW.post('/reset')),
  tariff: d => act(() => WW.post('/tariff', { type: d.type })),
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
  'open-wiz': openWizard,
  'wiz-type': d => { ui.wiz.type = d.k; renderAll(); },
  'wiz-room': d => { ui.wiz.room = d.id; renderAll(); },
  'wiz-allow': () => { ui.wiz.allow = !ui.wiz.allow; renderAll(); },
  'wiz-learn': () => act(() => WW.post('/learn', { kind: ui.wiz.type })),
  'wiz-back': () => { if (ui.wiz.step === 0) closeWizard(); else { ui.wiz.step--; renderAll(); } },
  'wiz-next': () => {
    const z = ui.wiz, learned = st.learn && st.learn.status === 'done' && st.learn.learned_w > 0;
    if (![!!z.type, !!z.room, learned, true][z.step]) return;
    if (z.step < 3) { z.step++; renderAll(); return; }
    const t = TYPES.find(x => x.k === z.type);
    const roomName = (st.rooms.find(r => r.id === z.room) || {}).name || '';
    const name = z.name.trim() || (t.label.split(' / ')[0] + ' ' + roomName);
    return act(async () => {
      await WW.post('/devices', { kind: z.type, room: z.room, name, allow: z.allow });
      ui.wiz = null;
    });
  },
});
document.addEventListener('input', ev => { if (ev.target.id === 'wiz-name' && ui.wiz) ui.wiz.name = ev.target.value; });
window.addEventListener('message', ev => {
  if (ev.origin === location.origin && ev.data && ev.data.type === 'open-wizard') openWizard();
});

WW.billStatus().then(x => { ui.bill.status = x; }).catch(() => {});
WWSched.init({ rerender: () => st && renderAll(), refresh, toast: showError });
refresh();
setInterval(refresh, 1000);
