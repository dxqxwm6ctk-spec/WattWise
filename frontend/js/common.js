/* Shared helpers for the dashboard and the phone page. Plain JS, no framework. */

const WW = (() => {
  const params = new URLSearchParams(location.search);
  const site = params.get('site') || 'home';

  // ---------- API ----------
  async function api(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
    return data;
  }
  const getState = () => api('GET', `/api/sites/${site}/state`);
  const post = (path, body) => api('POST', `/api/sites/${site}${path}`, body || {});

  // ---------- tiny DOM "morph" ----------
  // We render HTML strings, then copy only the differences into the live DOM.
  // Elements are kept, so CSS transitions (needle, bars, odometer) animate smoothly.
  function morph(from, to) {
    if (from.nodeType !== to.nodeType || from.nodeName !== to.nodeName) {
      from.replaceWith(to.cloneNode(true));
      return;
    }
    if (from.nodeType === 3 || from.nodeType === 8) {
      if (from.nodeValue !== to.nodeValue) from.nodeValue = to.nodeValue;
      return;
    }
    if (from.hasAttribute && from.hasAttribute('data-keep')) return; // e.g. the chart canvas
    for (const a of [...from.attributes]) if (!to.hasAttribute(a.name)) from.removeAttribute(a.name);
    for (const a of [...to.attributes]) if (from.getAttribute(a.name) !== a.value) from.setAttribute(a.name, a.value);
    if (from.tagName === 'INPUT' && document.activeElement !== from && from.value !== (to.getAttribute('value') || '')) {
      from.value = to.getAttribute('value') || '';
    }
    const f = [...from.childNodes], t = [...to.childNodes];
    for (let i = 0; i < Math.max(f.length, t.length); i++) {
      if (!f[i]) from.appendChild(t[i].cloneNode(true));
      else if (!t[i]) f[i].remove();
      else morph(f[i], t[i]);
    }
  }
  function render(root, html) {
    const tpl = document.createElement(root.tagName);
    tpl.innerHTML = html;
    for (const a of [...root.attributes]) tpl.setAttribute(a.name, a.value);
    morph(root, tpl);
  }

  // ---------- formatting ----------
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(d);

  // Gauge and odometer numbers shared by both views.
  function gauge(w, maxW) {
    const frac = Math.max(0, Math.min(1, (w || 0) / maxW));
    const color = frac > 0.75 ? '#E8553F' : frac > 0.5 ? '#F2B544' : '#B8F04A';
    return { frac, color, needleDeg: (-90 + frac * 180).toFixed(1) };
  }
  function odometer(kwh) {
    return Number(kwh || 0).toFixed(1).replace('.', '').padStart(6, '0').slice(-6).split('').map(Number);
  }

  // Steps of the goal plan, coloured by the agent's phase (same rules as the design).
  function goalSteps(st) {
    const order = { normal: 2, analyzing: 3, pending: 4, executing: 5, verified: 7, rejected: 4, expired: 4, offline: 4, stopped: -1 };
    const phase = st.agent.phase;
    const cur = st.goal ? (order[phase] ?? 2) : -1;
    const halted = ['rejected', 'expired', 'offline'].includes(phase);
    return st.steps.map((label, i) => {
      let s = i < cur ? 'done' : i === cur ? 'active' : 'todo';
      if (st.goal && halted && i === 4) s = 'halt';
      const m = {
        done: { tag: 'تم', color: '#B8F04A', text: '#D9D7CF', bg: '#161812', border: '#2E3A1C' },
        active: { tag: i === 4 ? 'ينتظر' : 'جارٍ', color: i === 4 ? '#F2B544' : '#B8F04A', text: '#ECEBE4', bg: i === 4 ? '#1E1A10' : '#1A2011', border: i === 4 ? '#5A4518' : '#4C6A20' },
        halt: { tag: phase === 'rejected' ? 'مرفوض' : phase === 'offline' ? 'بلا اتصال' : 'انتهت المهلة', color: '#E8553F', text: '#ECEBE4', bg: '#1E1412', border: '#4A2620' },
        todo: { tag: '', color: '#5E5C55', text: '#8E8C82', bg: 'transparent', border: '#23251F' },
      }[s];
      return { n: String(i + 1).padStart(2, '0'), label, ...m };
    });
  }

  function agentLabel(st) {
    const a = st.agent;
    if (!st.online) return { label: 'لا توجد قراءات · الوضع الآمن', color: '#E8553F' };
    if (a.estop) return { label: 'متوقف (طوارئ)', color: '#E8553F' };
    if (a.safe_mode) return { label: 'الوضع الآمن · بلا اتصال', color: '#F2B544' };
    if (!st.goal) return { label: 'بانتظار هدف', color: '#8E8C82' };
    const label = { pending: 'بانتظار موافقة', analyzing: 'يحلّل', executing: 'ينفّذ', verified: 'تحقّق' }[a.phase] || 'يراقب';
    return { label, color: a.phase === 'pending' ? '#F2B544' : '#B8F04A' };
  }

  // Delegated click handling: <button data-act="name" data-id="..">
  function onAction(handlers) {
    document.addEventListener('click', async ev => {
      const el = ev.target.closest('[data-act]');
      if (!el) return;
      const fn = handlers[el.dataset.act];
      if (!fn) return;
      ev.preventDefault();
      try { await fn(el.dataset, el); } catch (e) { handlers.onError ? handlers.onError(e) : console.error(e); }
    });
  }

  // ---------- bill photo ----------
  // Shrink the photo in the browser (max 1600 px, JPEG) so it uploads fast on a hotspot.
  // Works for any image the browser can open (also iPhone photos). Nothing is kept on the phone.
  function shrinkPhoto(file, maxSide = 1600) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, maxSide / Math.max(img.width, img.height));
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('تعذّر فتح الصورة.')); };
      img.src = url;
    });
  }
  const billStatus = () => api('GET', '/api/bill/status');
  const billPhoto = async file => post('/bill/photo', { image_b64: await shrinkPhoto(file) });
  const billManual = m => post('/bill/manual', {
    kwh: Number(m.kwh), days: m.days ? Number(m.days) : null, amount_jod: m.amount ? Number(m.amount) : null });

  return { site, api, getState, post, render, esc, fmt, gauge, odometer, goalSteps, agentLabel, onAction,
           billStatus, billPhoto, billManual };
})();
