/* WattWise phone page: "add a WiFi smart plug" wizard.
   Loaded after app.js and uses its globals (ui, st, renderAll, act, TYPES, showError).
   3 steps: pick the plug (scan the Wi-Fi, or type it by hand) -> what is plugged in ->
   connection + safety check -> add. After that the agent controls it like any relay,
   always with the same approval step. */

const PLUG_KINDS = [{ k: 'fan', label: 'مروحة' }, ...TYPES];

const plugChip = sel => `border:1.5px solid ${sel ? '#1A1B16' : '#E2DFD4'};background:${sel ? '#1A1B16' : '#FFFFFF'};color:${sel ? '#F3F1EA' : '#1A1B16'}`;
const plugInput = 'height:48px;border-radius:14px;border:1.5px solid #E2DFD4;background:#FFFFFF;padding:0 12px;font-size:15px;color:#1A1B16;outline:none;width:100%;box-sizing:border-box';

function plugTarget(z) {
  if (z.pick) return { brand: z.pick.brand, host: z.pick.host, options: { ...z.pick.options, max_a: z.maxA || z.pick.options.max_a } };
  return { brand: z.brand, host: z.host.trim(), options: { ...z.opts, max_a: z.maxA } };
}

function plugStepOk(z) {
  if (z.step === 0) {
    if (z.pick) return true;
    const b = (z.brands || []).find(x => x.key === z.brand);
    return !!(b && z.host.trim() && b.fields.every(f => f.optional || (z.opts[f.key] || '').trim()));
  }
  if (z.step === 1) return !!(z.type && z.room);
  const c = z.check;
  return !!(c && c.safety.level !== 'block' && (!c.safety.needs_confirm || z.confirm));
}

function plugStep0(z) {
  const found = (z.found || []).filter(f => !f.added);
  const list = z.scanning
    ? `<div style="height:56px;border-radius:18px;background:#E6F5C8;display:flex;align-items:center;justify-content:center;gap:10px;font-size:15px;color:#4A6418;font-weight:600"><span style="width:10px;height:10px;border-radius:50%;background:#5E7A1C;animation:ww-pulse 0.8s infinite"></span>جارٍ البحث في شبكة الـ Wi-Fi…</div>`
    : found.length ? found.map(f => {
      const sel = z.pick && z.pick.host === f.host;
      return `<button data-act="plug-pick" data-host="${esc(f.host)}" style="text-align:right;border-radius:18px;${plugChip(sel)};padding:12px 14px;cursor:pointer;display:flex;flex-direction:column;gap:3px">
        <span style="font-size:15px;font-weight:700">${esc(f.model)}</span>
        <span style="font-size:12px;opacity:.75">${esc(f.brand_name)} · <span dir="ltr">${esc(f.host)}</span></span>
        <span style="font-size:12px;opacity:.75">${f.meters === false ? 'تشغيل وإطفاء فقط (لا يقيس الواط)' : f.meters ? 'يقيس الواط ✓' : 'نعرف إن كان يقيس بعد الفحص'}${(f.needs || []).length ? ' · يحتاج Local Key' : ''}</span>
      </button>`;
    }).join('') : `<div style="border-radius:18px;background:#FFFFFF;padding:14px;font-size:13.5px;color:#77756C">لم نجد مقابس على هذه الشبكة. تأكّد أن المقبس والهاتف على شبكة الـ Wi-Fi نفسها، أو أضفه يدويًا.</div>`;

  let manual = '';
  if (z.manual) {
    const b = (z.brands || []).find(x => x.key === z.brand);
    manual = `<div style="display:flex;flex-direction:column;gap:10px;border-radius:18px;background:#FFFFFF;padding:14px">
      <span style="font-size:14px;font-weight:700">ما ماركة المقبس؟</span>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">${(z.brands || []).filter(x => x.key !== 'simulated').map(x =>
        `<button data-act="plug-brand" data-k="${x.key}" style="min-height:46px;border-radius:14px;${plugChip(z.brand === x.key)};font-size:13px;font-weight:600;cursor:pointer;padding:6px">${esc(x.name)}</button>`).join('')}</div>
      ${b ? `<span style="font-size:12.5px;line-height:1.6;color:#77756C">${esc(b.how)}</span>
        <label style="display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:#77756C">عنوان المقبس (IP) من تطبيق الشركة أو الراوتر
          <input id="plug-host" dir="ltr" value="${esc(z.host)}" placeholder="192.168.1.50" style="${plugInput}"></label>
        ${b.fields.map(f => `<label style="display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:#77756C">${esc(f.label)}${f.optional ? ' (اختياري)' : ''}
          <input id="plug-opt-${f.key}" dir="ltr" ${f.secret ? 'type="password"' : ''} value="${esc(z.opts[f.key] || '')}" style="${plugInput}"></label>`).join('')}` : ''}
    </div>`;
  }
  return `<div style="display:flex;flex-direction:column;gap:10px">
    <span style="font-size:13px;line-height:1.6;color:#77756C">صِل المقبس الذكي بالكهرباء وصِل الجهاز به. يجب أن يكون المقبس قد أُعدّ أول مرة من تطبيق الشركة على شبكة الـ Wi-Fi نفسها.</span>
    ${list}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <button data-act="plug-scan" class="btn-line" style="height:46px;font-size:14px">ابحث مجددًا</button>
      <button data-act="plug-manual" class="btn-line" style="height:46px;font-size:14px">${z.manual ? 'إخفاء الإدخال اليدوي' : 'إضافة يدويًا'}</button>
    </div>
    ${manual}
    <label style="display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;color:#77756C">حد المقبس (مكتوب عليه)
      <select id="plug-maxa" style="height:40px;border-radius:12px;border:1.5px solid #E2DFD4;background:#FFF;padding:0 8px">
        ${[10, 13, 16].map(a => `<option value="${a}" ${Number(z.maxA || (z.pick && z.pick.options.max_a) || 10) === a ? 'selected' : ''}>${a}A</option>`).join('')}
      </select></label>
  </div>`;
}

function plugStep1(z) {
  const t = PLUG_KINDS.find(x => x.k === z.type);
  const ph = t && z.room ? t.label.split(' / ')[0] + ' ' + (st.rooms.find(r => r.id === z.room) || {}).name : 'اسم الجهاز';
  return `<div style="display:flex;flex-direction:column;gap:12px">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">${PLUG_KINDS.map(x =>
      `<button data-act="plug-type" data-k="${x.k}" style="min-height:46px;border-radius:14px;${plugChip(z.type === x.k)};font-size:13.5px;font-weight:600;cursor:pointer;padding:6px">${x.label}</button>`).join('')}</div>
    <span style="font-size:14px;font-weight:700">في أي غرفة؟</span>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">${st.rooms.map(r =>
      `<button data-act="plug-room" data-id="${esc(r.id)}" style="min-height:46px;border-radius:14px;${plugChip(z.room === r.id)};font-size:13.5px;font-weight:600;cursor:pointer">${esc(r.name)}</button>`).join('')}</div>
    <label style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:#77756C">الاسم (مثلًا: سخّان الحمّام)
      <input id="plug-name" value="${esc(z.name)}" placeholder="${esc(ph)}" style="${plugInput}"></label>
  </div>`;
}

function plugStep2(z) {
  const c = z.check, t = PLUG_KINDS.find(x => x.k === z.type) || {};
  if (z.checking) return `<div style="height:56px;border-radius:18px;background:#E6F5C8;display:flex;align-items:center;justify-content:center;gap:10px;font-size:15px;color:#4A6418;font-weight:600"><span style="width:10px;height:10px;border-radius:50%;background:#5E7A1C;animation:ww-pulse 0.8s infinite"></span>جارٍ الاتصال بالمقبس…</div>`;
  if (!c) return `<div style="border-radius:18px;background:#FBE3DD;padding:14px;font-size:14px;line-height:1.7;color:#7A2A1C">${esc(z.msg || 'تعذّر الوصول إلى المقبس.')}</div>
    <button data-act="plug-check" class="btn-line" style="height:46px;font-size:14px">حاول مجددًا</button>`;
  const s = c.safety;
  const colors = { block: ['#FBE3DD', '#7A2A1C'], heater: ['#FFF4D9', '#6B4A00'], warn: ['#FFF4D9', '#6B4A00'] }[s.level];
  const safetyBox = s.level === 'ok' ? '' : `<div style="border-radius:18px;background:${colors[0]};border:1.5px solid ${s.level === 'block' ? '#E8553F' : '#E8B23A'};padding:14px;display:flex;flex-direction:column;gap:10px">
      <span style="font-size:15px;font-weight:700;color:${colors[1]}">${s.level === 'block' ? 'ممنوع على هذا المقبس' : '⚠️ تحذير أمان'}</span>
      <span style="font-size:13.5px;line-height:1.7;color:${colors[1]}">${esc(s.message)}</span>
      ${s.needs_confirm ? `<button data-act="plug-confirm" style="display:flex;align-items:center;gap:10px;background:transparent;border:none;cursor:pointer;font-size:14px;font-weight:600;color:${colors[1]};padding:0">
        <span style="width:22px;height:22px;border-radius:6px;border:2px solid ${colors[1]};display:grid;place-items:center">${z.confirm ? '✓' : ''}</span>فهمت التحذير وأريد المتابعة</button>` : ''}
    </div>`;
  const allow = t.locked
    ? `<div style="border-radius:18px;background:#FBE3DD;padding:14px;font-size:13.5px;line-height:1.7;color:#7A2A1C">جهاز حرج (T2): سنراقب استهلاكه من المقبس فقط، ولا يمكن لأحد إطفاؤه. محمي برمجيًا.</div>`
    : `<div style="border-radius:18px;background:#FFFFFF;padding:14px;display:flex;align-items:center;gap:12px">
        <div style="flex:1;display:flex;flex-direction:column;gap:4px">
          <span style="font-size:15px;font-weight:600">يقترح الوكيل إطفاءه عند وجود هدر</span>
          <span style="font-size:12.5px;line-height:1.6;color:#77756C">يسألك دائمًا قبل أي إجراء، ولا يفعل شيئًا إن لم تردّ.</span>
        </div>
        <button data-act="plug-allow" style="width:52px;height:32px;border-radius:16px;border:none;background:${z.allow ? '#1A1B16' : '#D8D5CA'};position:relative;cursor:pointer;flex:none;padding:0">
          <span style="position:absolute;top:4px;${z.allow ? 'left' : 'right'}:4px;width:24px;height:24px;border-radius:50%;background:${z.allow ? '#B8F04A' : '#FFFFFF'};box-shadow:0 1px 3px rgba(0,0,0,0.2)"></span>
        </button>
      </div>`;
  return `<div style="display:flex;flex-direction:column;gap:12px">
    <div style="border-radius:18px;background:#E6F5C8;padding:14px;display:flex;flex-direction:column;gap:4px">
      <span style="font-size:13px;color:#4A6418">تم الاتصال بالمقبس ✓ ${c.on ? 'يعمل' : 'مطفأ'}</span>
      ${c.meters
        ? `<span class="mono" style="font-size:24px;font-weight:500" dir="ltr">${c.power_w == null ? '—' : fmt(c.power_w, 0)} W</span>
           <span style="font-size:12px;color:#4A6418">${c.measured ? 'هذه بصمة الجهاز من المقبس نفسه.' : `سنقيس بصمته عند تشغيله. التقدير الحالي ≈ ${c.est_w} واط.`}</span>`
        : `<span style="font-size:12.5px;line-height:1.6;color:#4A6418">هذا المقبس لا يقيس الواط. نتحكّم به ونقيس بصمته على العدّاد الرئيسي (≈ ${c.est_w} واط حاليًا).</span>`}
      <span style="font-size:12px;color:#4A6418">حد المقبس: ${fmt(c.max_w, 0)} واط</span>
    </div>
    ${safetyBox}${allow}
  </div>`;
}

function plugWizard() {
  const z = ui.plugWiz;
  const titles = ['اختر المقبس الذكي', 'ما الجهاز الموصول به؟', 'فحص الاتصال والأمان'];
  const ok = plugStepOk(z) && !z.busy;
  const body = [plugStep0, plugStep1, plugStep2][z.step](z);
  return `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;flex-direction:column;gap:8px">
        <div style="display:flex;justify-content:space-between;font-size:12px;color:#77756C"><span>مقبس ذكي (Wi-Fi)</span><span class="mono" dir="ltr">${z.step + 1} / 3</span></div>
        <div style="height:4px;border-radius:2px;background:#E2DFD4;overflow:hidden;display:flex"><div style="width:${(z.step + 1) * 33.4}%;background:#1A1B16"></div></div>
      </div>
      <span style="font-size:22px;font-weight:700">${titles[z.step]}</span>
      ${body}
      <div style="display:grid;grid-template-columns:1fr 1.5fr;gap:8px;padding-top:4px">
        <button data-act="plug-back" class="btn-line" style="height:52px;font-size:15px">${z.step === 0 ? 'إلغاء' : 'رجوع'}</button>
        <button data-act="plug-next" style="height:52px;border-radius:18px;border:none;background:${ok ? '#1A1B16' : '#D8D5CA'};color:${ok ? '#F3F1EA' : '#8E8C82'};font-size:15px;font-weight:700;cursor:pointer">${z.step === 2 ? 'إضافة الجهاز' : 'التالي'}</button>
      </div>
    </div>`;
}

/* A short line under each device that sits on a smart plug. */
function plugLine(d) {
  const p = d.plug;
  if (!p) return '';
  const live = p.online ? (p.meters && p.power_w != null ? `<span class="mono" dir="ltr">${fmt(p.power_w, 0)} W</span> من المقبس` : 'متصل') : 'المقبس غير متصل';
  return `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;color:${p.online ? '#4A6418' : '#B5452F'}">
    <span>🔌 ${esc(p.simulated && p.model ? p.model : p.brand_name)} · ${live}</span>
    <button data-act="plug-remove" data-id="${esc(d.id)}" style="border:none;background:transparent;color:#9A988E;font-size:12px;cursor:pointer;padding:0">إزالة</button>
  </div>`;
}

async function plugScan() {
  const z = ui.plugWiz;
  z.scanning = true; renderAll();
  try { z.found = (await WW.api('GET', `/api/sites/${WW.site}/plugs/scan`)).plugs; } catch (e) { showError(e.message); }
  z.scanning = false;
  if (ui.plugWiz === z) renderAll();
}

async function plugCheck() {
  const z = ui.plugWiz;
  z.checking = true; z.check = null; z.msg = ''; z.confirm = false; renderAll();
  try { z.check = await WW.post('/plugs/check', { ...plugTarget(z), kind: z.type }); } catch (e) { z.msg = e.message; }
  z.checking = false;
  if (ui.plugWiz === z) renderAll();
}

function openPlugWizard() {
  ui.tab = 'devices'; ui.wiz = null;
  ui.plugWiz = { step: 0, found: [], scanning: false, pick: null, manual: false, brands: [], brand: null, host: '', opts: {},
    maxA: null, type: null, room: null, name: '', allow: true, check: null, checking: false, confirm: false, busy: false, msg: '' };
  WW.api('GET', '/api/plugs/brands').then(r => { if (ui.plugWiz) { ui.plugWiz.brands = r.brands; renderAll(); } }).catch(() => {});
  plugScan();
}

WW.onAction({
  onError: e => showError(e.message),
  'open-plug': openPlugWizard,
  'plug-scan': () => plugScan(),
  'plug-manual': () => { const z = ui.plugWiz; z.manual = !z.manual; z.pick = null; renderAll(); },
  'plug-pick': d => { const z = ui.plugWiz; z.pick = z.found.find(f => f.host === d.host) || null; z.manual = false; renderAll(); },
  'plug-brand': d => { ui.plugWiz.brand = d.k; renderAll(); },
  'plug-type': d => { ui.plugWiz.type = d.k; renderAll(); },
  'plug-room': d => { ui.plugWiz.room = d.id; renderAll(); },
  'plug-allow': () => { ui.plugWiz.allow = !ui.plugWiz.allow; renderAll(); },
  'plug-confirm': () => { ui.plugWiz.confirm = !ui.plugWiz.confirm; renderAll(); },
  'plug-check': () => plugCheck(),
  'plug-back': () => { const z = ui.plugWiz; if (z.step === 0) ui.plugWiz = null; else z.step--; renderAll(); },
  'plug-next': () => {
    const z = ui.plugWiz;
    if (!plugStepOk(z) || z.busy) return;
    if (z.step < 2) { z.step++; renderAll(); if (z.step === 2) plugCheck(); return; }
    const t = PLUG_KINDS.find(x => x.k === z.type);
    const roomName = (st.rooms.find(r => r.id === z.room) || {}).name || '';
    const name = z.name.trim() || (t.label.split(' / ')[0] + ' ' + roomName);
    z.busy = true;
    return act(async () => {
      try {
        await WW.post('/plugs', { ...plugTarget(z), kind: z.type, room: z.room, name, allow: z.allow,
          confirm_high_power: z.confirm, model: z.pick ? z.pick.model : null });
        ui.plugWiz = null;
      } finally { z.busy = false; }
    });
  },
  'plug-remove': d => {
    const dev = st.devices.find(x => x.id === d.id);
    if (!confirm(`إزالة ${dev ? dev.name : 'الجهاز'} من المقابس الذكية؟`)) return;
    return act(() => WW.api('DELETE', `/api/sites/${WW.site}/plugs/${d.id}`));
  },
});

document.addEventListener('input', ev => {
  const z = ui.plugWiz;
  if (!z) return;
  const id = ev.target.id;
  if (id === 'plug-host') z.host = ev.target.value;
  else if (id === 'plug-name') z.name = ev.target.value;
  else if (id.startsWith('plug-opt-')) z.opts[id.slice(9)] = ev.target.value;
});
document.addEventListener('change', ev => {
  if (ev.target.id === 'plug-maxa' && ui.plugWiz) { ui.plugWiz.maxA = Number(ev.target.value); }
});
window.addEventListener('message', ev => {
  if (ev.origin === location.origin && ev.data && ev.data.type === 'open-plug') openPlugWizard();
});
