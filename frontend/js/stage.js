/* WattWise judge screen. Plain JS, polls /state every second (same API as the dashboard).

   The story on one screen:
     1. a judge gives the goal (voice or typing),
     2. the agent splits it into steps (live status),
     3. the approval card goes to the judge's own phone (QR code opens the phone page),
     4. approve -> the real relay switches, the meter confirms, and the saving counter moves.
   A red banner appears when the internet is gone, with what WattWise keeps doing locally. */

const $ = id => document.getElementById(id);
const { esc, fmt } = WW;
let st = null;
const ui = { goal: '', listening: false, connectUrl: '' };

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove('show'), 3500);
}

const phonePath = () => `/app.html?site=${encodeURIComponent(WW.site)}`;
const mmss = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

// ---------------- sections ----------------

function bar() {
  const net = st.internet || {};
  const netPill = !net.checked
    ? `<span class="pill" style="--c:#8E8C82"><i></i>جارٍ فحص الإنترنت…</span>`
    : net.online
      ? `<span class="pill big" style="--c:#B8F04A"><i></i>متصل بالإنترنت</span>`
      : `<span class="pill big live" style="--c:#E8553F"><i></i>دون إنترنت · يعمل محليًا${net.forced ? ' (محاكاة)' : ''}</span>`;
  const meterPill = st.online
    ? `<span class="pill live" style="--c:#B8F04A"><i></i>العدّاد متصل · <b class="mono" dir="ltr">${fmt(st.meter.power_w, 0)} W</b></span>`
    : `<span class="pill" style="--c:#E8553F"><i></i>لا توجد قراءات · الوضع الآمن</span>`;
  const brain = st.agent.brain || {};
  const brainPill = `<span class="pill" style="--c:${brain.mode === 'llm' ? '#8FC7FF' : '#F2B544'}" title="${esc(brain.reason_ar)}"><i></i>${brain.mode === 'llm' ? 'العقل: نموذج ذكاء اصطناعي' : 'العقل: قواعد محلية'}</span>`;
  const sim = st.source === 'simulator';
  return `
    <div class="brand"><div class="logo">W/</div><div><b>WattWise</b><small>${esc(st.site_name)} · شاشة العرض للحكّام</small></div></div>
    <div class="pills">${netPill}${meterPill}${brainPill}</div>
    <div class="pills">
      <button class="btn warn" data-act="net" title="للتجربة فقط. أمام الحكّام: افصلوا كابل الإنترنت عن الراوتر.">${net.forced ? 'إعادة الإنترنت (محاكاة)' : 'فصل الإنترنت (محاكاة)'}</button>
      ${sim ? `<button class="btn" data-act="waste">اصنع هدرًا (غرفة فارغة)</button>` : ''}
      <a class="btn ghost" href="index.html?site=${encodeURIComponent(WW.site)}">اللوحة الكاملة</a>
      <button class="btn ghost" data-act="reset">إعادة الضبط</button>
      <button class="btn stop" data-act="estop">إيقاف طوارئ</button>
    </div>`;
}

function offlineBanner() {
  const net = st.internet || {};
  if (!net.checked || net.online) return '';
  const w = net.local_work || {};
  return `
    <div class="offline">
      <div class="ttl"><i></i>الإنترنت مقطوع منذ <span class="mono" dir="ltr">${mmss(net.since_s || 0)}</span> · وWattWise لم يتوقف${net.forced ? ' <span class="tag">محاكاة للتجربة</span>' : ''}</div>
      <div class="sub">الذكاء الأساسي كله يعمل على اللابتوب والشبكة المحلية: القياس، وكشف الهدر، وبطاقة الموافقة على الهاتف، والإطفاء الحقيقي، والتحقق بالعدّاد.</div>
      <div class="cnt">
        <div><b>${w.readings ?? 0}</b><span>قراءة عدّاد محفوظة</span></div>
        <div><b>${w.detections ?? 0}</b><span>حالة هدر أو استهلاك غريب مكتشفة</span></div>
        <div><b>${w.actions ?? 0}</b><span>إجراء نُفِّذ بعد الموافقة</span></div>
        <div><b>${w.verified ?? 0}</b><span>تحقّق بالعدّاد</span></div>
      </div>
      <div class="ok">
        ${(net.works_offline || []).map(x => `<span>${esc(x)}</span>`).join('')}
        ${(net.needs_internet || []).map(x => `<span class="x">${esc(x)} (يعود مع عودة الإنترنت)</span>`).join('')}
      </div>
    </div>`;
}

const micOk = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
const EXAMPLES = ['وفّر ٢٠٪ هذا الشهر دون المساس بالراحة', 'أبقِ الفاتورة تحت ٢٥ دينارًا', 'وفّر قدر الإمكان ولا تلمس الثلاجة'];

function goalPanel() {
  const offline = st.internet && st.internet.checked && !st.internet.online;
  const g = st.goal, plan = st.plan;
  return `
    <div class="h"><div class="t"><span class="n">1</span>أعطِ الوكيل هدفًا (لا سؤالًا)</div>
      ${g ? '<span class="tag">الهدف مفعّل</span>' : ''}</div>
    <div class="goal-row">
      <input id="goal-in" class="goal-in" placeholder="مثلًا: وفّر ٢٠٪ هذا الشهر" value="${esc(ui.goal)}" autocomplete="off">
      ${micOk ? `<button class="mic${ui.listening ? ' on' : ''}" data-act="mic" ${offline ? 'disabled title="الإدخال الصوتي في كروم يحتاج إنترنت. اكتب الهدف."' : ''} aria-label="قل الهدف بصوتك">🎤</button>` : ''}
      <button class="send" data-act="goal">إرسال</button>
    </div>
    <div class="chips">${EXAMPLES.map(e => `<button class="chip" data-act="example" data-text="${esc(e)}">${esc(e)}</button>`).join('')}</div>
    ${g ? `<div class="goal-now"><q>${esc(g.text)}</q>${plan && plan.summary ? `<p>${esc(plan.summary)}</p>` : ''}</div>` : ''}
    <div class="note">${micOk ? (offline ? 'الميكروفون في كروم يحتاج إنترنت، لذا اكتب الهدف الآن. الوكيل نفسه يعمل محليًا.' : 'اضغط 🎤 ليقول الحكم الهدف بصوته (بالعربية).') : 'هذا المتصفح لا يدعم الميكروفون. اكتب الهدف.'}</div>`;
}

function planPanel() {
  if (!st.goal) {
    return `<div class="h"><div class="t"><span class="n">2</span>يقسّم الوكيل الهدف إلى خطوات</div></div>
      <div class="muted" style="font-size:16px">بانتظار هدف. فور وصوله تظهر الخطوات هنا أثناء تنفيذها.</div>`;
  }
  const steps = WW.goalSteps(st).map((s, i) => `
    <div class="step ${s.tag === 'جارٍ' || s.tag === 'ينتظر' ? 'active' : ''}" style="--b:${s.border};--bg2:${s.bg};--tx:${s.text};--c:${s.color};animation-delay:${i * 0.08}s">
      <span class="k">${s.n}</span><span class="lbl">${esc(s.label)}</span><span class="st">${esc(s.tag)}</span>
    </div>`).join('');
  const p = st.plan;
  const list = p && p.steps ? `
    <ul class="plan-list">${p.steps.map((x, i) => `<li style="animation-delay:${0.6 + i * 0.1}s"><span class="tag ${p.tags[i] === 'T1' ? 't1' : ''}">${p.tags[i]}</span>${esc(x)}</li>`).join('')}</ul>` : '';
  return `
    <div class="h"><div class="t"><span class="n">2</span>قسّم الوكيل الهدف إلى خطوات</div>
      <span class="tag ${p && p.by === 'llm' ? 'llm' : ''}">${p && p.by === 'llm' ? 'خطة من النموذج' : 'خطة من القواعد'}</span></div>
    <div class="steps">${steps}</div>
    ${list}
    <div class="note">T0 = تلقائي (قراءة، تحليل، تنبيه). T1 = يحتاج موافقة بشرية قبل أي إطفاء.</div>`;
}

function approvePanel() {
  const p = st.pending, last = st.last_approval;
  let card = '';
  if (p) {
    const pct = (p.expires_in_s / p.timeout_s * 100).toFixed(1);
    card = `
      <div class="card pending">
        <div style="display:flex;justify-content:space-between;color:#F2B544;font-weight:600"><span>📱 وصلت البطاقة إلى الهاتف · بانتظار الحكم</span><span class="mono" dir="ltr">${p.expires_in_s}s</span></div>
        <div class="ttl">${esc(p.title)}</div>
        <div class="why">${esc(p.reason)}</div>
        <div class="why" style="margin-top:6px">يوفّر ≈ <b class="mono" dir="ltr">${fmt(p.details.saving_jod_per_hour, 3)} JD/h</b> · ${p.details.signature_measured ? 'البصمة مقاسة بالعدّاد' : 'البصمة تقديرية حتى الآن'}</div>
        <div class="bar-t"><div style="width:${pct}%"></div></div>
        <div class="note">إن لم يردّ أحد قبل انتهاء الوقت فلن يحدث شيء. عدم الرد لا يعني الموافقة.</div>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn ghost" data-act="reject" data-id="${p.id}">(احتياطي) رفض من هنا</button>
          <button class="btn ghost" data-act="approve" data-id="${p.id}">(احتياطي) موافقة من هنا</button>
        </div>
      </div>`;
  } else if (last) {
    const ok = last.status === 'approved';
    const verified = (st.log || []).find(l => l.tier === 'OK' && /العدّاد أكّد/.test(l.message));
    const label = { approved: '✓ وافق الحكم وأطفأ الريليه الجهاز فعليًا', rejected: '✕ رفض الحكم، فلم يُطفأ شيء', expired: '⏱ لم يردّ أحد، فلم يحدث شيء (عدم الرد لا يعني الموافقة)', blocked: '⛔ الحارس منع الإجراء', cancelled: 'أُلغي الطلب (الوضع الآمن أو إيقاف الطوارئ)' }[last.status] || last.status;
    card = `
      <div class="card ${ok ? 'ok' : 'no'}">
        <div class="ttl" style="font-size:20px">${esc(label)}</div>
        <div class="why">${esc(last.device_name || '')}${ok && verified ? ` · ${esc(verified.message)}` : ''}</div>
      </div>`;
  }
  return `
    <div class="h"><div class="t"><span class="n">3</span>الموافقة من هاتف الحكم</div></div>
    <div class="join">
      <div class="qr"><img src="api/connect/qr.svg?path=${encodeURIComponent(phonePath())}" alt="رمز QR يفتح صفحة الموافقة على الهاتف"></div>
      <div class="join-txt">
        <span>امسح الرمز بكاميرا الهاتف وهو على شبكة الـ Wi-Fi نفسها. ستُفتح صفحة البيت، وعندما يجد الوكيل هدرًا تصلك بطاقة موافقة.</span>
        <span class="join-url">${esc((ui.connectUrl || '') + phonePath())}</span>
        <span class="muted" style="font-size:13px">يعمل دون إنترنت أيضًا: يكفي أن يكون اللابتوب والهاتف على الراوتر نفسه أو نقطة اتصال.</span>
      </div>
    </div>
    ${card}`;
}

function savingsPanel() {
  const s = st.savings || {};
  const p = s.projection;
  return `
    <div class="h"><div class="t"><span class="n">4</span>التوفير المُقاس اليوم</div>
      ${s.rate_w ? `<span class="pill live" style="--c:#B8F04A;height:30px"><i></i>نوفّر الآن <b class="mono" dir="ltr">${s.rate_w} W</b></span>` : ''}</div>
    <div class="big"><span class="v" id="c-jod" data-keep>0.0000</span><span class="u">دينار</span></div>
    <div class="kpis">
      <div class="kpi"><div class="v" id="c-co2" data-keep>0.000</div><div class="l">كغ CO₂ لم تنبعث</div></div>
      <div class="kpi"><div class="v" id="c-kwh" data-keep>0.000</div><div class="l">ك.و.س اليوم</div></div>
      <div class="kpi"><div class="v mono" dir="ltr">${fmt(s.jod, 3)}</div><div class="l">دينار منذ بدء التشغيل</div></div>
    </div>
    <div class="proj">
      <div class="ttl">لو استخدم ١٠٠٠ بيت أردني WattWise</div>
      ${p ? `
        <div class="row">
          <div><div class="v" dir="ltr">${Number(p.jod_year).toLocaleString('en')}</div><div class="l">دينار بالسنة</div></div>
          <div><div class="v" dir="ltr">${fmt(p.mwh_year, 1)}</div><div class="l">ميغاواط ساعة بالسنة</div></div>
          <div><div class="v" dir="ltr">${p.co2_t_year == null ? '—' : fmt(p.co2_t_year, 1)}</div><div class="l">طن CO₂ بالسنة</div></div>
        </div>
        <div class="src">${esc(p.how_ar)}</div>` : `<div class="muted" style="font-size:15px">يظهر الرقم فور تأكيد العدّاد لأول توفير. لا نعرض أرقامًا غير مُقاسة.</div>`}
    </div>
    <div class="src">تُحسب فقط الإجراءات التي أكّدها العدّاد. السعر حسب شريحة هذا البيت (${fmt(s.price_jod_per_kwh * 1000, 0)} فلس/ك.و.س). عامل CO₂: ${s.co2_kg_per_kwh ?? '—'} كغ/ك.و.س، المصدر: ${esc(s.co2_source || '')}</div>`;
}

function logPanel() {
  const lines = (st.log || []).slice(0, 6).map(l => `<div class="line"><span class="clk" dir="ltr">${esc(l.clock)}</span><span class="tag ${l.tier === 'T1' ? 't1' : ''}">${esc(l.tier)}</span><span>${esc(l.message)}</span></div>`).join('');
  return `<div class="h"><div class="t">تفكير الوكيل مباشرة (سجل القرارات)</div></div>${lines || '<span class="muted">لا شيء بعد.</span>'}`;
}

// ---------------- animated numbers ----------------
const shown = {};
function tween(id, to, dec) {
  const el = $(id);
  if (!el || to == null) { if (el) el.textContent = '—'; return; }
  const from = shown[id] ?? 0;
  if (Math.abs(from - to) < Math.pow(10, -dec) / 2) { el.textContent = to.toFixed(dec); shown[id] = to; return; }
  const t0 = performance.now();
  const step = now => {
    const k = Math.min(1, (now - t0) / 900);
    const v = from + (to - from) * (1 - Math.pow(1 - k, 3));
    el.textContent = v.toFixed(dec);
    if (k < 1) requestAnimationFrame(step); else shown[id] = to;
  };
  requestAnimationFrame(step);
}

function renderAll() {
  if (!st) return;
  const typing = document.activeElement && document.activeElement.id === 'goal-in';
  WW.render($('bar'), bar());
  WW.render($('offline'), offlineBanner());
  if (!typing) WW.render($('goal'), goalPanel());
  WW.render($('plan'), planPanel());
  WW.render($('approve'), approvePanel());
  WW.render($('savings'), savingsPanel());
  WW.render($('log'), logPanel());
  const s = st.savings || {};
  tween('c-jod', s.today_jod ?? 0, 4);
  tween('c-co2', s.today_co2_kg, 3);
  tween('c-kwh', s.today_kwh ?? 0, 3);
}

async function refresh() {
  try { st = await WW.getState(); renderAll(); } catch (e) { console.error(e); }
}
async function act(fn, okMsg) {
  try { await fn(); if (okMsg) toast(okMsg); } catch (e) { toast(e.message); }
  refresh();
}

// ---------------- voice ----------------
let recog = null;
function listen() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  if (recog) { try { recog.stop(); } catch (e) { /* already stopped */ } return; }
  recog = new SR();
  recog.lang = 'ar-JO'; recog.interimResults = true; recog.maxAlternatives = 1;
  recog.onresult = e => {
    ui.goal = [...e.results].map(r => r[0].transcript).join(' ');
    const input = $('goal-in'); if (input) input.value = ui.goal;
  };
  recog.onerror = e => toast(e.error === 'network' ? 'الإدخال الصوتي في كروم يحتاج إنترنت. اكتب الهدف، فالوكيل يعمل محليًا.' : 'الميكروفون غير متاح هنا. اكتب الهدف.');
  recog.onend = () => { recog = null; ui.listening = false; renderAll(); if (ui.goal.trim()) toast('راجع النص ثم اضغط "إرسال".'); };
  ui.listening = true; renderAll();
  try { recog.start(); } catch (e) { recog = null; ui.listening = false; }
}

function sendGoal() {
  const input = $('goal-in');
  const text = (input ? input.value : ui.goal).trim();
  if (!text) { toast('اكتب الهدف أو قله بصوتك.'); return; }
  ui.goal = '';
  if (input) { input.value = ''; input.blur(); }
  return act(() => WW.post('/goal', { text }), 'استلم الوكيل الهدف وقسّمه إلى خطوات.');
}

WW.onAction({
  onError: e => toast(e.message),
  mic: () => listen(),
  goal: () => sendGoal(),
  example: d => { ui.goal = d.text; const i = $('goal-in'); if (i) { i.value = d.text; i.focus(); } },
  net: () => act(() => WW.api('POST', '/api/internet/simulate', { offline: !(st.internet && st.internet.forced) })),
  waste: () => act(() => WW.post('/scenario', { name: 'bedroom_empty_window' }), 'أصبحت الغرفة فارغة والجهاز يعمل. راقبوا الوكيل.'),
  reset: () => act(() => WW.post('/reset')),
  estop: () => act(() => WW.post('/estop')),
  approve: d => act(() => WW.post(`/approvals/${d.id}/approve`)),
  reject: d => act(() => WW.post(`/approvals/${d.id}/reject`)),
});
document.addEventListener('input', ev => { if (ev.target.id === 'goal-in') ui.goal = ev.target.value; });
document.addEventListener('keydown', ev => { if (ev.target.id === 'goal-in' && ev.key === 'Enter') sendGoal(); });

WW.api('GET', '/api/connect').then(c => { ui.connectUrl = c.url; renderAll(); }).catch(() => {});
refresh();
setInterval(refresh, 1000);
