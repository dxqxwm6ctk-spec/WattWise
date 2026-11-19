"""Savings report: one self-contained HTML page (print it to PDF from the browser).

Everything in it comes from the database: the M&V result, the meter-verified
actions, every approval request and the audit log. No number is typed by hand.
"""

import html
import time

from backend import actions, billing, config, db, mv

STATUS_AR = {
    "approved": "وافقت ✓", "rejected": "رفضت", "expired": "ما في رد (ما عملنا إشي)",
    "blocked": "منعه الـ Policy Guard", "cancelled": "إنلغى", "skipped": "الوكيل قرّر ما يسأل", "pending": "بانتظار",
}


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _num(x, digits=2) -> str:
    return "—" if x is None else f"{x:,.{digits}f}"


def _chart(series: list[dict]) -> str:
    """Inline SVG: measured power vs the baseline model, per interval."""
    pts = [s for s in series if s["actual_w"] is not None]
    if len(pts) < 2:
        return '<p class="muted">لسا ما في بيانات كفاية للرسم.</p>'
    w, h, pad = 900, 260, 36
    vals = [p["actual_w"] for p in pts] + [p["baseline_w"] for p in pts if p["baseline_w"] is not None]
    vmax = max(vals) * 1.1 or 1
    x = lambda i: pad + i * (w - 2 * pad) / (len(pts) - 1)
    y = lambda v: h - pad - v / vmax * (h - 2 * pad)
    actual = " ".join(f"{x(i):.1f},{y(p['actual_w']):.1f}" for i, p in enumerate(pts))
    base = " ".join(f"{x(i):.1f},{y(p['baseline_w']):.1f}" for i, p in enumerate(pts) if p["baseline_w"] is not None)
    switch = next((i for i, p in enumerate(pts) if p["period"] != "baseline"), None)
    marks = []
    if switch is not None:
        marks.append(f'<line x1="{x(switch):.1f}" y1="{pad - 10}" x2="{x(switch):.1f}" y2="{h - pad}" '
                     f'stroke="#b07a00" stroke-dasharray="4 4"/>'
                     f'<text x="{x(switch) - 4:.1f}" y="{pad - 14}" font-size="12" fill="#b07a00" text-anchor="end">'
                     f'أول إجراء وافقت عليه</text>')
    step = max(1, len(pts) // 8)
    labels = "".join(f'<text x="{x(i):.1f}" y="{h - pad + 18}" font-size="11" fill="#777" text-anchor="middle">'
                     f'{_e(p["label"])}</text>' for i, p in enumerate(pts) if i % step == 0)
    grid = "".join(f'<line x1="{pad}" y1="{y(vmax * k / 4):.1f}" x2="{w - pad}" y2="{y(vmax * k / 4):.1f}" stroke="#eee"/>'
                   f'<text x="{pad - 6}" y="{y(vmax * k / 4) + 4:.1f}" font-size="10" fill="#999" text-anchor="end">'
                   f'{vmax * k / 4 / 1000:.1f}</text>' for k in range(5))
    return f'''<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="الاستهلاك المقاس مقابل خط الأساس" direction="ltr">
  {grid}{labels}{"".join(marks)}
  <polyline points="{base}" fill="none" stroke="#999" stroke-width="2" stroke-dasharray="6 4"/>
  <polyline points="{actual}" fill="none" stroke="#3d6b12" stroke-width="2.5"/>
</svg>
<div class="legend"><span><i style="background:#3d6b12"></i>المقاس بالعدّاد (kW)</span>
<span><i style="background:#999"></i>خط الأساس: المتوقّع بدون الوكيل</span></div>'''


def build(conn, site: str) -> str:
    actions.require_site(site)
    cfg = config.load_sites()[site]
    r = mv.compute(conn, site)
    goal = actions.active_goal(conn, site)
    tariff = config.load_tariff()
    ttype = db.get_state(conn, f"tariff_type:{site}", tariff["default_type"])
    meter = db.latest_meter(conn, site) or {}
    price = billing.marginal_price(meter.get("energy_kwh") or 0.0, tariff, ttype)
    saved_kwh = db.get_state(conn, f"saved_wh:{site}", 0.0) / 1000
    co2 = billing.co2_factor()

    names = {d["id"]: d["name"] for d in db.devices(conn, site)}
    apps = db.rows(conn.execute("SELECT * FROM approvals WHERE site=? ORDER BY id", (site,)))
    counts: dict[str, int] = {}
    for a in apps:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    log = db.rows(conn.execute("SELECT clock, tier, actor, message FROM audit_log WHERE site=? ORDER BY id DESC LIMIT 40",
                               (site,)))

    if r["status"] == "ok":
        mv_main = f'<div class="big">{_num(r["saved_kwh"], 2)} <small>ك.و.س</small></div>'
        mv_sub = (f'± {_num(r["saved_band_kwh"], 2)} ك.و.س (تقريبًا ٩٥٪) · {_num(r["saved_pct"], 1)}٪ من خط الأساس · '
                  f'≈ {_num(r["saved_jod"], 3)} دينار · CO₂: {"—" if r["saved_co2_kg"] is None else _num(r["saved_co2_kg"], 2) + " كغ"}')
    else:
        mv_main = '<div class="big">—</div>'
        mv_sub = _e(r["message_ar"])

    m = r.get("model")
    model_rows = "" if not m else f'''
      <tr><td>عدد الفترات بخط الأساس</td><td>{m["n"]} × {r["interval_min"]} دقيقة</td><td>≥ {mv.MIN_BASELINE_INTERVALS}</td></tr>
      <tr><td>CV(RMSE)</td><td>{_num(m["cv_rmse_pct"], 2)}٪</td><td>≤ {mv.CV_RMSE_MAX:g}٪</td></tr>
      <tr><td>NMBE</td><td>{_num(m["nmbe_pct"], 2)}٪</td><td>بين ±{mv.NMBE_MAX:g}٪</td></tr>
      <tr><td>R²</td><td>{_num(m["r2"], 3)}</td><td>للمعلومية</td></tr>
      <tr><td>النتيجة</td><td colspan="2">{"النموذج مقبول ✓" if m["passes"] else "النموذج مش مقبول، فما في رقم توفير"}</td></tr>'''

    action_rows = "".join(
        f'<tr><td>{_e(names.get(a["device_id"], a["device_id"]))}</td><td>{_e(STATUS_AR.get(a["status"], a["status"]))}</td>'
        f'<td>{_num(a["power_before"], 0) if a["power_before"] else "—"}</td>'
        f'<td>{_num(a["power_after"], 0) if a["power_after"] else "—"}</td>'
        f'<td>{_num(a["power_before"] - a["power_after"], 0) if a["power_before"] and a["power_after"] is not None else "—"}</td></tr>'
        for a in apps) or '<tr><td colspan="5" class="muted">لسا ما في طلبات.</td></tr>'
    log_rows = "".join(f'<tr><td>{_e(x["clock"])}</td><td>{_e(x["tier"])}</td><td>{_e(x["message"])}</td></tr>' for x in log)
    synthetic = cfg["source"] == "simulator"
    now = db.site_clock(conn, site)

    return f'''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>تقرير التوفير · WattWise</title>
<style>
  body {{ font-family: system-ui, "Segoe UI", Tahoma, sans-serif; color: #1a1b16; background: #fff; margin: 0; padding: 24px 16px; }}
  main {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }} h2 {{ font-size: 17px; margin: 28px 0 10px; }}
  .muted {{ color: #777; }} .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; background: #fff4d9; color: #8a5a00; font-size: 12px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
  .card {{ border: 1px solid #e6e3d8; border-radius: 14px; padding: 14px 16px; }}
  .card h3 {{ margin: 0 0 6px; font-size: 13px; color: #555; font-weight: 600; }}
  .big {{ font-size: 30px; font-weight: 600; direction: ltr; text-align: right; }} .big small {{ font-size: 14px; color: #777; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  td, th {{ border-bottom: 1px solid #eee; padding: 7px 6px; text-align: right; vertical-align: top; }}
  th {{ color: #555; font-weight: 600; }}
  .legend {{ display: flex; gap: 18px; font-size: 12px; color: #555; }} .legend i {{ display: inline-block; width: 14px; height: 3px; margin-left: 6px; vertical-align: middle; }}
  ul {{ line-height: 1.8; padding-right: 20px; }}
  .print {{ float: left; padding: 8px 14px; border-radius: 10px; border: 1px solid #ccc; background: #fff; cursor: pointer; }}
  @media print {{ .print {{ display: none; }} body {{ padding: 0; }} }}
</style></head>
<body><main>
  <button class="print" onclick="window.print()">اطبع / احفظ PDF</button>
  <h1>تقرير التوفير · WattWise</h1>
  <div class="muted">{_e(cfg["name"])} · ساعة الموقع {_e(now)} · انطبع {_e(time.strftime("%Y-%m-%d %H:%M"))}</div>
  {'<p><span class="badge">بيانات تركيبية من المحاكي (synthetic)، مش قياسات حقيقية</span></p>' if synthetic else ''}
  <p><b>الهدف:</b> {_e(goal["text"]) if goal else '<span class="muted">ما في هدف</span>'}</p>

  <h2>الخلاصة</h2>
  <div class="cards">
    <div class="card"><h3>التوفير حسب M&amp;V (مقارنة بخط الأساس المعدّل)</h3>{mv_main}<div class="muted">{mv_sub}</div></div>
    <div class="card"><h3>التوفير من الإجراءات اللي أكّدها العدّاد</h3><div class="big">{_num(saved_kwh, 2)} <small>ك.و.س</small></div>
      <div class="muted">≈ {_num(saved_kwh * price, 3)} دينار بسعر شريحتك ({_num(price, 3)} دينار/ك.و.س) · CO₂: {"—" if co2 is None else _num(saved_kwh * co2, 2) + " كغ"}</div></div>
    <div class="card"><h3>طلبات الموافقة</h3>
      <div>وافقت: <b>{counts.get("approved", 0)}</b> · رفضت: <b>{counts.get("rejected", 0)}</b> · ما في رد: <b>{counts.get("expired", 0)}</b></div>
      <div class="muted">منعها الكود: {counts.get("blocked", 0)} · الوكيل قرّر ما يسأل: {counts.get("skipped", 0)}</div></div>
  </div>

  <h2>الاستهلاك المقاس مقابل خط الأساس</h2>
  {_chart(r["series"])}

  <h2>جودة نموذج خط الأساس</h2>
  {'<table><tr><th>المقياس</th><th>القيمة</th><th>الحد (ASHRAE Guideline 14)</th></tr>' + model_rows + '</table>' if m else '<p class="muted">' + _e(r["message_ar"]) + '</p>'}

  <h2>كل الطلبات ونتيجتها</h2>
  <table><tr><th>الجهاز</th><th>القرار</th><th>قبل (واط)</th><th>بعد (واط)</th><th>الفرق المقاس</th></tr>{action_rows}</table>

  <h2>سجل القرارات (آخر ٤٠)</h2>
  <table><tr><th>الوقت</th><th>المستوى</th><th>الرسالة</th></tr>{log_rows}</table>

  <h2>الطريقة وملاحظات الصراحة</h2>
  <ul>
    <li>خط الأساس = نموذج انحدار (Ridge) بيتوقّع الاستهلاك من الساعة، نسبة الغرف المشغولة، ومعدّل الحرارة، متدرّب على الفترة قبل أول إجراء وافقت عليه (بروح IPMVP Option C). التوفير = خط الأساس المعدّل − المقاس.</li>
    <li>ما بنعرض رقم توفير إلا إذا النموذج مقبول وفي بيانات كفاية. التوفير السالب بينعرض متل ما هو.</li>
    <li>الهامش ± تقريبي (بافتراض أخطاء مستقلة بين الفترات).</li>
    <li>التوفير من الإجراءات بينحسب بس بعد ما العدّاد يأكّد الانخفاض.</li>
    <li>القيمة بالدينار = قيمة الطاقة بسعر الشريحة الحالية، بدون الدعم أو الرسوم. شرايح التعرفة لازم تتأكّد من فاتورة حقيقية.</li>
    <li>معامل CO₂ لسا مش مُعبّى من مصدر رسمي، فبيبيّن «—».</li>
    <li>الـ 15٪ هدف تصميمي، مش نتيجة.</li>
  </ul>
</main></body></html>'''
