/* "Schedule a device" screen, shared by the dashboard and the phone page.

   Tabs on top: Home / Building / Lab. Each tab shows that site's devices grouped
   by room. Pick a device to see its schedules and timers, switch it on/off now,
   or add a detailed schedule (on time, off time, which days).

   A new schedule is never saved in one click: "Review" asks the server, the
   Policy Guard checks it and returns an estimate, and only "Confirm and save"
   stores it (the human approval step). The guard checks it again every time it fires.
*/

const WWSched = (() => {
  const { esc, fmt } = WW;
  const SITES = [
    { id: 'home', name: 'البيت', icon: '🏠' },
    { id: 'building', name: 'المبنى', icon: '🏢' },
    { id: 'lab', name: 'المختبر', icon: '🔬' },
  ];
  // 0 = Sunday ... 6 = Saturday (JavaScript getDay). Shown from Saturday.
  const DAYS = [[6, 'سبت'], [0, 'أحد'], [1, 'إثنين'], [2, 'ثلاثاء'], [3, 'أربعاء'], [4, 'خميس'], [5, 'جمعة']];
  const ALL = [0, 1, 2, 3, 4, 5, 6];
  const PRESETS = [['كل يوم', ALL], ['أيام الدوام', [0, 1, 2, 3, 4]], ['عطلة نهاية الأسبوع', [5, 6]]];
  const KIND_ICON = { ac: '❄️', light: '💡', tv: '📺', heater: '🔥', washer: '🧺', fan: '🌀', pc: '💻', ev: '🚗', router: '📶', fridge: '🧊', fire_alarm: '🚨', emergency_light: '🚨' };

  const s = {
    site: SITES.some(x => x.id === WW.site) ? WW.site : 'home',
    data: {},            // site id -> listing from /api/sites/{site}/schedules
    loadedAt: {},
    dev: null,           // selected device id
    on: '', off: '', days: ALL.slice(),
    review: null,        // the server's preview, waiting for "confirm"
    msg: '', busy: false,
  };
  let hooks = { rerender: () => {}, refresh: () => {}, toast: m => console.warn(m) };

  const api = (method, path, body) => WW.api(method, `/api/sites/${s.site}${path}`, body);
  const cur = () => s.data[s.site];
  const estText = e => e ? `≈ ${fmt(e.kwh, 1)} ك.و.س/يوم · ≈ ${fmt(e.jod, 2)} دينار/يوم (تقديري، غير مُقاس)` : '';
  const minLabel = n => n === 30 ? '30 دقيقة' : n === 60 ? 'ساعة' : 'ساعتين';
  const when = r => [r.on_time && 'تشغيل ' + r.on_time, r.off_time && 'إطفاء ' + r.off_time].filter(Boolean).join(' ← ');

  async function load(site) {
    s.loadedAt[site] = Date.now();
    try {
      s.data[site] = await WW.api('GET', `/api/sites/${site}/schedules`);
    } catch (e) { hooks.toast(e.message); }
  }

  // Called by the page after each poll. The page's own site comes inside its state;
  // another site is fetched on its own, at most every 2 seconds.
  function sync(st) {
    if (st && st.automation) s.data[WW.site] = { site: WW.site, ...st.automation };
    if (s.site !== WW.site && Date.now() - (s.loadedAt[s.site] || 0) > 2000) {
      load(s.site).then(() => hooks.rerender());
    }
  }

  function resetForm() { s.on = ''; s.off = ''; s.days = ALL.slice(); s.review = null; }

  // ---------- render ----------

  function siteTabs() {
    return `<div class="sch-sites" role="tablist">${SITES.map(x => {
      const d = s.data[x.id];
      const sub = d ? `${d.rooms.length} ${d.rooms.length > 2 ? 'غرف' : 'غرفة'} · ${d.devices.length} جهاز${d.schedules.length ? ` · ${d.schedules.length} جدول` : ''}` : '…';
      return `<button class="sch-site${s.site === x.id ? ' sel' : ''}" role="tab" aria-selected="${s.site === x.id}" data-act="sc-site" data-id="${x.id}">
        <span class="sch-site-name">${x.icon} ${x.name}</span><span class="sch-site-sub">${sub}</span></button>`;
    }).join('')}</div>`;
  }

  function devRow(d, a) {
    const mine = a.schedules.filter(r => r.device_id === d.id);
    const timers = a.timers.filter(t => t.device_id === d.id);
    const line = mine.length
      ? mine.map(r => `<span class="mono${r.enabled ? '' : ' off'}" dir="ltr">${esc(r.on_time || '··')}→${esc(r.off_time || '··')}</span>`).join(' ')
      : '<span class="sch-none">دون جدول</span>';
    return `<button class="sch-dev${s.dev === d.id ? ' sel' : ''}" data-act="sc-dev" data-id="${esc(d.id)}">
      <span class="sch-dot${d.is_on ? ' on' : ''}" title="${d.is_on ? 'يعمل' : 'مطفأ'}"></span>
      <span class="sch-dev-main"><span class="sch-dev-name">${KIND_ICON[d.kind] || '🔌'} ${esc(d.name)}</span>
        <span class="sch-dev-line">${line}${timers.length ? ' <span class="sch-timer-tag">⏱ مؤقّت</span>' : ''}</span></span>
      <span class="sch-go">${s.dev === d.id ? '●' : 'جدولة ‹'}</span></button>`;
  }

  function rooms(a) {
    return `<div class="sch-rooms">${a.rooms.map(room => {
      const devs = a.devices.filter(d => d.room === room.id);
      const locked = a.locked.filter(d => d.room === room.id);
      if (!devs.length && !locked.length) return '';
      return `<div class="sch-room">
        <div class="sch-room-h"><span>${esc(room.name)}</span><span class="sch-count">${devs.length + locked.length} ${devs.length + locked.length > 2 ? 'أجهزة' : 'جهاز'}</span></div>
        ${devs.map(d => devRow(d, a)).join('')}
        ${locked.map(d => `<div class="sch-dev locked" title="${esc(d.why)}"><span class="sch-dot lock">🔒</span>
          <span class="sch-dev-main"><span class="sch-dev-name">${KIND_ICON[d.kind] || '🔌'} ${esc(d.name)}</span><span class="sch-dev-line">${esc(d.why)}</span></span></div>`).join('')}
      </div>`;
    }).join('')}</div>`;
  }

  function detail(a, d, drill) {
    const mine = a.schedules.filter(r => r.device_id === d.id);
    const timers = a.timers.filter(t => t.device_id === d.id);
    const rows = mine.map(r => `<div class="sch-item">
        <div class="sch-item-main"><span class="mono">${esc(when(r))}</span>
          <span class="sch-item-sub">${esc(r.days_text || 'كل يوم')}${r.source === 'suggested' ? ' · مقترح ومعتمد' : r.source === 'command' ? ' · من أمر صوتي' : ''}</span>
          <span class="sch-item-sub">${estText(r.estimate)}</span></div>
        <button class="sch-switch${r.enabled ? ' on' : ''}" data-act="sc-enable" data-id="${r.id}" data-on="${r.enabled ? 1 : 0}" aria-label="${r.enabled ? 'إيقاف الجدول' : 'تفعيل الجدول'}"><i></i></button>
        <button class="sch-btn danger sm" data-act="sc-del" data-id="${r.id}">حذف</button></div>`).join('');
    const tRows = timers.map(t => `<div class="sch-item timer"><span class="sch-item-main">⏱ ${esc(t.text)}</span>
        <button class="sch-btn sm" data-act="sc-timer-del" data-id="${t.id}">إلغاء</button></div>`).join('');
    const dayChips = DAYS.map(([n, label]) => `<button class="sch-chip${s.days.includes(n) ? ' sel' : ''}" data-act="sc-day" data-n="${n}">${label}</button>`).join('');
    const presets = PRESETS.map(([label, ds]) => {
      const sel = ds.length === s.days.length && ds.every(x => s.days.includes(x));
      return `<button class="sch-chip ghost${sel ? ' sel' : ''}" data-act="sc-preset" data-days="${ds.join(',')}">${label}</button>`;
    }).join('');
    const timerBtns = isFor => [30, 60, 120].map(n => `<button class="sch-btn sm" data-act="sc-timer" data-min="${n}"${isFor ? ' data-for="1"' : ''}>${minLabel(n)}</button>`).join('');
    const rv = s.review;
    const review = !rv ? '' : `<div class="sch-review" role="alertdialog" aria-label="راجع الجدول">
        <span class="sch-review-t">راجع قبل الحفظ</span>
        <span>${esc(rv.device_name)} · ${esc(rv.room_name)}</span>
        <span class="mono">${esc(when(rv))}</span>
        <span>${esc(rv.days_text)}</span>
        ${rv.estimate ? `<span class="sch-item-sub">${estText(rv.estimate)}</span>` : ''}
        <span class="sch-ok">✓ فحصه حارس السياسات ووافق عليه، وسيفحصه مجددًا عند كل موعد.</span>
        <div class="sch-row"><button class="sch-btn primary" data-act="sc-confirm">${s.busy ? '…' : 'أكّد واحفظ'}</button>
          <button class="sch-btn" data-act="sc-edit">عدّل</button></div></div>`;
    return `<div class="sch-detail">
      ${drill ? '<button class="sch-back" data-act="sc-back">→ كل الأجهزة</button>' : ''}
      <div class="sch-detail-h">
        <div class="sch-dev-main"><span class="sch-detail-name">${KIND_ICON[d.kind] || '🔌'} ${esc(d.name)}</span>
          <span class="sch-item-sub">${esc(d.room_name)} · ≈ ${fmt(d.watts)} واط · ${d.is_on ? '<b class="sch-on">يعمل الآن</b>' : 'مطفأ الآن'}</span></div>
        <button class="sch-btn${d.is_on ? '' : ' primary'}" data-act="sc-toggle" data-id="${esc(d.id)}" data-on="${d.is_on ? 1 : 0}">${d.is_on ? 'أطفئه الآن' : 'شغّله الآن'}</button>
      </div>
      <div class="sch-sec">جداول هذا الجهاز</div>
      ${rows || '<span class="sch-none">لا توجد جداول لهذا الجهاز بعد.</span>'}
      ${tRows}
      <div class="sch-sec">جدول جديد</div>
      <div class="sch-times">
        <label>وقت التشغيل<input class="sch-field" type="time" id="sc-on" value="${esc(s.on)}"></label>
        <label>وقت الإطفاء<input class="sch-field" type="time" id="sc-off" value="${esc(s.off)}"></label>
      </div>
      <div class="sch-chips">${presets}</div>
      <div class="sch-chips">${dayChips}</div>
      ${review || `<button class="sch-btn primary wide" data-act="sc-preview">${s.busy ? 'جارٍ الفحص…' : 'راجع الجدول'}</button>`}
      ${s.msg ? `<span class="sch-msg">${esc(s.msg)}</span>` : ''}
      <div class="sch-sec">مؤقّت سريع</div>
      <div class="sch-row"><span class="sch-lbl">إطفاء بعد</span>${timerBtns(false)}</div>
      <div class="sch-row"><span class="sch-lbl">تشغيل لمدة</span>${timerBtns(true)}</div>
    </div>`;
  }

  // layout: 'side' (dashboard: rooms + detail side by side) or 'drill' (phone: tap a device to open it)
  function render({ theme = 'dark', layout = 'side' } = {}) {
    const a = cur();
    if (!a) return `<div class="sch ${theme}">${siteTabs()}<span class="sch-none">جارٍ التحميل…</span></div>`;
    const d = a.devices.find(x => x.id === s.dev);
    if (!d) s.dev = null;
    const empty = !a.devices.length && !a.locked.length ? '<span class="sch-none">لا توجد أجهزة في هذا الموقع.</span>' : '';
    let body;
    if (layout === 'drill') {
      body = d ? detail(a, d, true) : rooms(a);
    } else {
      body = `<div class="sch-body">${rooms(a)}${d ? detail(a, d, false)
        : '<div class="sch-detail hint"><span>اختر جهازًا من أي غرفة لعرض جداوله أو إضافة جدول أو التحكم به.</span></div>'}</div>`;
    }
    return `<div class="sch ${theme}">${siteTabs()}${empty}${body}</div>`;
  }

  // ---------- actions ----------

  async function act(fn) {
    try { await fn(); } catch (e) { hooks.toast(e.message); }
    await load(s.site);
    hooks.rerender();
    hooks.refresh();
  }

  const actions = {
    'sc-site': x => {
      if (s.site === x.id) return;
      s.site = x.id; s.dev = null; s.msg = ''; resetForm();
      hooks.rerender();
      load(s.site).then(() => hooks.rerender());
    },
    'sc-dev': x => { s.dev = x.id; s.msg = ''; resetForm(); hooks.rerender(); },
    'sc-back': () => { s.dev = null; s.msg = ''; resetForm(); hooks.rerender(); },
    'sc-day': x => {
      const n = Number(x.n);
      s.days = s.days.includes(n) ? s.days.filter(v => v !== n) : [...s.days, n];
      s.review = null; hooks.rerender();
    },
    'sc-preset': x => { s.days = x.days.split(',').map(Number); s.review = null; hooks.rerender(); },
    'sc-preview': async () => {
      if (!s.on && !s.off) { s.msg = 'اختر وقت تشغيل أو إطفاء (أو كليهما).'; hooks.rerender(); return; }
      if (!s.days.length) { s.msg = 'اختر يومًا واحدًا على الأقل.'; hooks.rerender(); return; }
      s.busy = true; s.msg = ''; hooks.rerender();
      try {
        s.review = await api('POST', '/schedules', { device_id: s.dev, on_time: s.on || null, off_time: s.off || null, days: s.days, preview: true });
      } catch (e) { s.msg = e.message; }
      s.busy = false; hooks.rerender();
    },
    'sc-edit': () => { s.review = null; hooks.rerender(); },
    'sc-confirm': () => act(async () => {
      const rv = s.review;
      if (!rv) return;
      s.busy = true;
      try {
        await api('POST', '/schedules', { device_id: rv.device_id, on_time: rv.on_time, off_time: rv.off_time, days: s.days });
        resetForm(); s.msg = 'حُفظ الجدول ✓';
      } catch (e) { s.msg = e.message; }
      s.busy = false;
    }),
    'sc-enable': x => act(() => api('POST', `/schedules/${x.id}/enabled`, { enabled: x.on !== '1' })),
    'sc-del': x => act(() => api('DELETE', `/schedules/${x.id}`)),
    'sc-timer': x => act(async () => {
      await api('POST', '/timers', { device_id: s.dev, minutes: Number(x.min), turn_on: false, run_now: x.for === '1' });
      s.msg = 'أُضيف المؤقّت ✓';
    }),
    'sc-timer-del': x => act(() => api('DELETE', `/timers/${x.id}`)),
    'sc-toggle': x => act(() => api('POST', `/devices/${x.id}/toggle`, { on: x.on !== '1' })),
  };

  document.addEventListener('input', ev => {
    if (ev.target.id === 'sc-on') { s.on = ev.target.value; s.review = null; }
    if (ev.target.id === 'sc-off') { s.off = ev.target.value; s.review = null; }
  });

  function init(h) {
    hooks = { ...hooks, ...h };
    for (const x of SITES) load(x.id).then(() => hooks.rerender());   // fill the counts on the tabs
  }

  return { init, sync, render, actions, state: s };
})();
