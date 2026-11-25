// "الجدولة" tab. On top: Home / Building / Lab. Each one shows its devices
// grouped by room. Tap a device to switch it now, add a quick timer, or add a
// detailed daily schedule (on time, off time, which days). A schedule is saved
// only after the person reviews it and taps "confirm" (the Policy Guard checks it
// first, and again every time it fires). Plus the smart water-heater schedule.

import 'dart:async';


import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/assistant_widgets.dart' show showError;
import '../widgets/wizard.dart' show kindIcon;

class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key, required this.st, required this.api, required this.run});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  final hint = TextEditingController();
  Map<String, dynamic>? proposal;
  bool busy = false;
  String heaterMsg = '';
  // Which site's devices we show, and the latest listing of each site.
  late String site = widget.api.site;
  final Map<String, Map<String, dynamic>> data = {};
  Timer? poll;
  String? device;
  TimeOfDay? onTime, offTime;
  List<int> days = [...allDays];
  Map<String, dynamic>? review;
  String formMsg = '';

  static const sites = [('home', 'البيت'), ('building', 'المبنى'), ('lab', 'المختبر')];
  // 0 = Sunday ... 6 = Saturday (the server's numbers). Shown from Saturday.
  static const dayNames = [(6, 'سبت'), (0, 'أحد'), (1, 'إثنين'), (2, 'ثلاثاء'), (3, 'أربعاء'), (4, 'خميس'), (5, 'جمعة')];
  static const allDays = [0, 1, 2, 3, 4, 5, 6];
  static const presets = [('كل يوم', allDays), ('أيام العمل', [0, 1, 2, 3, 4]), ('العطلة', [5, 6])];

  static String hhmm(TimeOfDay t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  static String minLabel(int n) => n == 30 ? '30 د' : n == 60 ? 'ساعة' : 'ساعتان';
  static String est(dynamic e) =>
      e == null ? '' : '≈ ${WW.fmt(e['kwh'], 1)} ك.و.س/يوم · ≈ ${WW.fmt(e['jod'], 2)} دينار/يوم (تقديري، غير مُقاس)';

  @override
  void initState() {
    super.initState();
    for (final x in sites) {
      load(x.$1);
    }
    // Another site's devices are not in the app's state, so we ask for them every 2 seconds.
    poll = Timer.periodic(const Duration(seconds: 2), (_) {
      if (site != widget.api.site) load(site);
    });
  }

  @override
  void dispose() {
    poll?.cancel();
    hint.dispose();
    super.dispose();
  }

  WattWiseApi get api => widget.api.forSite(site);

  Future<void> load(String s) async {
    try {
      final d = await widget.api.forSite(s).schedules();
      if (mounted) setState(() => data[s] = d);
    } catch (_) {}
  }

  /// Run an action on the selected site, then reload its listing.
  Future<void> runHere(Future<void> Function() action) async {
    await widget.run(action);
    await load(site);
  }

  void resetForm() {
    onTime = null;
    offTime = null;
    days = [...allDays];
    review = null;
  }

  Future<void> suggest() async {
    setState(() { busy = true; heaterMsg = ''; });
    try {
      proposal = await widget.api.suggestHeater(hint.text);
    } catch (e) {
      if (mounted) showError(context, e);
    }
    if (mounted) setState(() => busy = false);
  }

  Future<void> apply() async {
    final p = proposal!;
    await widget.run(() => widget.api.applyHeater('${p['device_id']}', p['items'] as List));
    setState(() {
      proposal = null;
      heaterMsg = 'حُفظ جدول السخّان ✓';
    });
  }

  Future<void> previewSchedule() async {
    if (onTime == null && offTime == null) {
      setState(() => formMsg = 'اختر وقت تشغيل أو إطفاء (أو كليهما).');
      return;
    }
    if (days.isEmpty) {
      setState(() => formMsg = 'اختر يومًا واحدًا على الأقل.');
      return;
    }
    try {
      final r = await api.previewSchedule(device!, onTime == null ? null : hhmm(onTime!), offTime == null ? null : hhmm(offTime!), days);
      setState(() { review = r; formMsg = ''; });
    } catch (e) {
      setState(() => formMsg = '$e');
    }
  }

  Future<void> confirmSchedule() async {
    final r = review!;
    try {
      await api.addSchedule('${r['device_id']}', r['on_time'] as String?, r['off_time'] as String?, days: days);
      setState(() { resetForm(); formMsg = 'حُفظ الجدول ✓'; });
    } catch (e) {
      setState(() => formMsg = '$e');
    }
    await load(site);
  }

  Future<void> pick(bool isOn) async {
    final t = await showTimePicker(context: context, initialTime: (isOn ? onTime : offTime) ?? TimeOfDay.now());
    if (t != null) setState(() { isOn ? onTime = t : offTime = t; review = null; });
  }

  @override
  Widget build(BuildContext context) {
    // The app's own site comes inside its state every second; other sites from load().
    if (widget.st['automation'] is Map<String, dynamic> && (widget.st['automation'] as Map)['rooms'] != null) {
      data[widget.api.site] = widget.st['automation'] as Map<String, dynamic>;
    }
    final a = data[site];
    final devices = (a?['devices'] as List?) ?? const [];
    final dev = devices.where((d) => d['id'] == device).firstOrNull as Map<String, dynamic>?;
    if (dev == null) device = null;
    final heater = site == widget.api.site && dev == null
        ? (widget.st['devices'] as List).where((d) => d['kind'] == 'heater' && d['tier'] == 'T1' && d['sensitive'] != true).firstOrNull
        : null;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (dev == null) ...[
        const Text('الجدولة', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 14),
        siteCards(),
        const SizedBox(height: 14),
      ],
      if (a == null)
        const Padding(padding: EdgeInsets.all(8), child: Text('جارٍ التحميل…', style: TextStyle(fontSize: 13, color: WW.sub)))
      else if (dev != null)
        ...detail(a, dev)
      else
        ...rooms(a),
      if (heater != null) ...heaterCards(),
    ]);
  }

  // ---------- smart water heater ----------

  List<Widget> heaterCards() {
    final p = proposal;
    final items = (p?['items'] as List?) ?? const [];
    return [
      const SizedBox(height: 4),
      WWBox(
        color: WW.ink,
        dark: true,
        radius: 24,
        padding: 18,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Row(children: [
            IconTile(icon: Icons.hot_tub_outlined, bg: WW.darkChip, fg: WW.accentText, size: 48, iconSize: 26, radius: 15),
            SizedBox(width: 12),
            Text('سخّان الماء الذكي', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white)),
          ]),
          const SizedBox(height: 14),
          const Text('من أكبر الأحمال في البيت. نشغّله فقط قبل الاستحمام، ولا يزيد عن 3 ساعات متواصلة.',
              style: TextStyle(fontSize: 14.5, height: 1.65, color: WW.darkBody)),
          const SizedBox(height: 14),
          const Text('متى تستحمّون؟', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Colors.white)),
          const SizedBox(height: 8),
          TextField(controller: hint, style: const TextStyle(color: Colors.white, fontSize: 15), decoration: wwField('مثلًا: الصبح 6:30 والمساء 8:30', dark: true)),
          const SizedBox(height: 14),
          WWButton(busy ? 'جارٍ التخطيط…' : 'اقترح جدولًا للسخّان', busy ? null : suggest, kind: BtnKind.accent, height: 54, fontSize: 16),
          if (heaterMsg.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(heaterMsg, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: WW.greenBright)),
          ],
        ]),
      ),
      if (p != null) ...[
        const SizedBox(height: 14),
        WWBox(
          border: WW.accent,
          borderWidth: 1.5,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Row(children: [
              Expanded(child: Text('الاقتراح', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700))),
              Pill('AI'),
            ]),
            if ('${p['reply'] ?? ''}'.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('${p['reply']}', style: const TextStyle(fontSize: 14, height: 1.6, color: WW.body)),
            ],
            for (final i in items) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(color: WW.soft, borderRadius: BorderRadius.circular(14)),
                child: Row(children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${i['on_time']} → ${i['off_time']}', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 18, fontWeight: FontWeight.w700)),
                      Text('${i['why']}', style: const TextStyle(fontSize: 13, color: WW.sub)),
                    ]),
                  ),
                  if (spanMinutes(i) != null) Text('${spanMinutes(i)} د', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: WW.body)),
                ]),
              ),
            ],
            if (items.isNotEmpty) ...[
              const SizedBox(height: 12),
              dayBar(items),
            ],
            const Divider(height: 24, color: WW.line),
            const Text('المجموع اليومي', style: TextStyle(fontSize: 13, color: WW.sub)),
            const SizedBox(height: 2),
            Text('≈ ${WW.fmt(p['total']['kwh'] as num?, 1)} kWh/day ≈ ${WW.fmt(p['total']['jod'] as num?, 2)} JD',
                textDirection: TextDirection.ltr, textAlign: TextAlign.end, style: WW.mono.copyWith(fontSize: 20, fontWeight: FontWeight.w700)),
            const Text('تقديري، غير مقاس', style: TextStyle(fontSize: 12, color: WW.pendingFg)),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: WWButton('لا', () => setState(() => proposal = null), kind: BtnKind.ghost)),
              if (items.isNotEmpty) ...[
                const SizedBox(width: 10),
                Expanded(child: WWButton('نعم، طبّقه', apply)),
              ],
            ]),
          ]),
        ),
      ],
    ];
  }

  static int? toMin(dynamic hhmm) {
    final p = '$hhmm'.split(':');
    if (p.length != 2) return null;
    final h = int.tryParse(p[0]), m = int.tryParse(p[1]);
    return h == null || m == null ? null : h * 60 + m;
  }

  static int? spanMinutes(dynamic i) {
    final a = toMin(i['on_time']), b = toMin(i['off_time']);
    if (a == null || b == null) return null;
    return (b - a + 1440) % 1440;
  }

  /// A 24-hour strip with the heating windows in lavender.
  Widget dayBar(List items) => Column(children: [
        Directionality(
          textDirection: TextDirection.ltr,
          child: LayoutBuilder(
            builder: (_, c) => Container(
              height: 28,
              decoration: BoxDecoration(color: WW.neutralBg, borderRadius: BorderRadius.circular(8)),
              clipBehavior: Clip.antiAlias,
              child: Stack(children: [
                for (final i in items)
                  if (toMin(i['on_time']) != null && spanMinutes(i) != null)
                    Positioned(
                      left: c.maxWidth * toMin(i['on_time'])! / 1440,
                      width: c.maxWidth * spanMinutes(i)! / 1440,
                      top: 0,
                      bottom: 0,
                      child: const ColoredBox(color: WW.accent),
                    ),
              ]),
            ),
          ),
        ),
        const SizedBox(height: 4),
        Directionality(
          textDirection: TextDirection.ltr,
          child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            for (final h in ['00', '06', '12', '18', '24']) Text(h, style: const TextStyle(fontSize: 11, color: WW.sub)),
          ]),
        ),
      ]);

  // ---------- Home / Building / Lab ----------

  Widget siteCards() => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        clipBehavior: Clip.none,
        child: Row(children: [
          for (final (i, x) in sites.indexed) ...[
            if (i > 0) const SizedBox(width: 8),
            GestureDetector(
              onTap: () {
                if (site == x.$1) return;
                setState(() { site = x.$1; device = null; formMsg = ''; resetForm(); });
                load(x.$1);
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 150,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: site == x.$1 ? WW.ink : Colors.white,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: site == x.$1 ? WW.accent : WW.line, width: site == x.$1 ? 2 : 1),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(x.$2, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: site == x.$1 ? Colors.white : WW.ink)),
                  const SizedBox(height: 4),
                  Text(siteSub(data[x.$1]),
                      maxLines: 2,
                      style: TextStyle(fontSize: 12, height: 1.5, color: (site == x.$1 ? Colors.white : WW.ink).withValues(alpha: 0.85))),
                ]),
              ),
            ),
          ],
        ]),
      );

  static String siteSub(Map<String, dynamic>? d) {
    if (d == null) return '…';
    final r = (d['rooms'] as List).length, n = (d['devices'] as List).length + ((d['locked'] as List?)?.length ?? 0), s = (d['schedules'] as List).length;
    return '$r ${r > 2 ? 'غرف' : 'غرفة'} · $n ${n > 10 || n < 3 ? 'جهاز' : 'أجهزة'}${s > 0 ? ' · $s ${s > 10 || s < 3 ? 'جدول' : 'جداول'}' : ''}';
  }

  static String span(dynamic r) => '${r['on_time'] ?? '··'}→${r['off_time'] ?? '··'}';
  static String when(dynamic r) => '${r['on_time'] ?? '··'} → ${r['off_time'] ?? '··'}';

  // ---------- rooms and their devices ----------

  List<Widget> rooms(Map<String, dynamic> a) {
    final out = <Widget>[];
    for (final room in a['rooms'] as List) {
      final devs = (a['devices'] as List).where((d) => d['room'] == room['id']).toList();
      final locked = (a['locked'] as List).where((d) => d['room'] == room['id']).toList();
      if (devs.isEmpty && locked.isEmpty) continue;
      final n = devs.length + locked.length;
      final rows = <Widget>[for (final d in devs) deviceRow(a, d), for (final d in locked) lockedRow(d)];
      out.add(Container(
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22), border: Border.all(color: WW.line)),
        clipBehavior: Clip.antiAlias,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: const BoxDecoration(color: WW.soft, border: Border(bottom: BorderSide(color: WW.line))),
            child: Row(children: [
              Expanded(child: Text('${room['name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
              Text('$n ${n > 2 ? 'أجهزة' : 'جهاز'}', style: const TextStyle(fontSize: 12.5, color: WW.sub)),
            ]),
          ),
          for (final (i, r) in rows.indexed) ...[
            if (i > 0) const Divider(height: 1, color: WW.line),
            r,
          ],
        ]),
      ));
      out.add(const SizedBox(height: 14));
    }
    if (out.isEmpty) out.add(const Text('لا توجد أجهزة في هذا الموقع.', style: TextStyle(fontSize: 13, color: WW.sub)));
    return out;
  }

  Widget deviceRow(Map<String, dynamic> a, dynamic d) {
    final mine = (a['schedules'] as List).where((r) => r['device_id'] == d['id']).toList();
    final hasTimer = (a['timers'] as List).any((t) => t['device_id'] == d['id']);
    return InkWell(
      onTap: () => setState(() { device = '${d['id']}'; formMsg = ''; resetForm(); }),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 64),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(children: [
            Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: d['is_on'] == true ? WW.accentDeep : const Color(0xFFCFCFD7))),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${d['name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                const SizedBox(height: 3),
                Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  mine.isEmpty
                      ? const Text('بلا جدول', style: TextStyle(fontSize: 12.5, color: WW.sub))
                      : Text(mine.map(span).join('  '), textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 12.5, color: WW.sub)),
                  if (hasTimer) const Pill('مؤقّت', bg: WW.pendingBg, fg: WW.pendingFg, size: 11.5, icon: Icons.timer_outlined),
                ]),
              ]),
            ),
            const Text('جدولة', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            const Icon(Icons.chevron_left_rounded, size: 18),
          ]),
        ),
      ),
    );
  }

  Widget lockedRow(dynamic d) => ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 64),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(children: [
            Container(width: 10, height: 10, decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFF9DB4CC))),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${d['name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Color(0xFF8A8A94))),
                const SizedBox(height: 3),
                Text('${d['why'] ?? 'محمي · لا يُجدول'}', style: const TextStyle(fontSize: 12.5, color: WW.sub)),
              ]),
            ),
            const Icon(Icons.lock_outline_rounded, size: 16, color: Color(0xFF8A8A94), semanticLabel: 'محمي'),
          ]),
        ),
      );

  // ---------- one device: control now, its schedules, a new schedule, quick timers ----------

  List<Widget> detail(Map<String, dynamic> a, Map<String, dynamic> d) {
    const h2 = TextStyle(fontSize: 17, fontWeight: FontWeight.w700);
    const label = TextStyle(fontSize: 13, fontWeight: FontWeight.w600);
    final mine = (a['schedules'] as List).where((r) => r['device_id'] == d['id']).toList();
    final timers = (a['timers'] as List).where((t) => t['device_id'] == d['id']).toList();
    final on = d['is_on'] == true;
    final r = review;

    Widget timeBox(String title, TimeOfDay? t, bool isOn) => Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: label),
            const SizedBox(height: 6),
            InkWell(
              onTap: () => pick(isOn),
              borderRadius: BorderRadius.circular(14),
              child: Container(
                height: 54,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                alignment: AlignmentDirectional.centerStart,
                decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14), border: Border.all(color: WW.field, width: 1.5)),
                child: t == null
                    ? const Text('اختر…', style: TextStyle(fontSize: 15, color: WW.muted))
                    : Text(hhmm(t), textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 18, fontWeight: FontWeight.w700)),
              ),
            ),
          ]),
        );

    Widget dayBtn(int n, String name) {
      final sel = days.contains(n);
      return Expanded(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2.5),
          child: GestureDetector(
            onTap: () => setState(() {
              days = sel ? days.where((x) => x != n).toList() : [...days, n];
              review = null;
            }),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              height: 44,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: sel ? WW.ink : Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: sel ? WW.accent : WW.field, width: sel ? 1.5 : 1),
              ),
              child: FittedBox(
                child: Text(name, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: sel ? Colors.white : WW.ink)),
              ),
            ),
          ),
        ),
      );
    }

    Widget reviewRow(String k, Widget v, {bool last = false}) => Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(border: last ? null : const Border(bottom: BorderSide(color: WW.line))),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(k, style: const TextStyle(fontSize: 14, color: WW.sub)),
            const SizedBox(width: 12),
            Expanded(child: Align(alignment: AlignmentDirectional.centerEnd, child: v)),
          ]),
        );

    Widget quick(String title, bool isFor) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: WW.sub)),
          const SizedBox(height: 8),
          Row(children: [
            for (final (i, n) in [30, 60, 120].indexed) ...[
              if (i > 0) const SizedBox(width: 8),
              Expanded(
                child: SizedBox(
                  height: 48,
                  child: OutlinedButton(
                    onPressed: () => runHere(() => api.addTimer('${d['id']}', n, runNow: isFor)),
                    style: OutlinedButton.styleFrom(
                      backgroundColor: WW.soft,
                      foregroundColor: WW.ink,
                      side: const BorderSide(color: WW.field),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                    child: Text(minLabel(n), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                  ),
                ),
              ),
            ],
          ]),
        ]);

    return [
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: TextButton.icon(
          onPressed: () => setState(() { device = null; formMsg = ''; resetForm(); }),
          style: TextButton.styleFrom(foregroundColor: WW.ink, minimumSize: const Size(0, 44), padding: const EdgeInsets.symmetric(horizontal: 4)),
          icon: const Icon(Icons.chevron_right_rounded, size: 20),
          label: const Text('كل الأجهزة', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        ),
      ),
      const SizedBox(height: 6),
      WWBox(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            IconTile(icon: _kindIcon('${d['kind']}'), bg: WW.accentBg, fg: WW.ink, size: 52, iconSize: 28),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${d['name']}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                Text.rich(TextSpan(children: [
                  TextSpan(text: '${d['room_name']} · '),
                  TextSpan(text: '≈ ${d['watts']} W', style: WW.mono),
                  const TextSpan(text: ' · '),
                  TextSpan(text: on ? 'يعمل' : 'مطفأ', style: const TextStyle(color: WW.ink, fontWeight: FontWeight.w600)),
                ]), style: const TextStyle(fontSize: 13, color: WW.sub)),
              ]),
            ),
          ]),
          const SizedBox(height: 14),
          on
              ? WWButton('أطفئه الآن', () => runHere(() => api.toggle('${d['id']}', false)), kind: BtnKind.outline, height: 50, radius: 14)
              : WWButton('شغّله الآن', () => runHere(() => api.toggle('${d['id']}', true)), height: 50, radius: 14),
        ]),
      ),
      const SizedBox(height: 14),
      const SectionTitle('جداوله'),
      const SizedBox(height: 8),
      if (mine.isEmpty && timers.isEmpty)
        const Padding(padding: EdgeInsets.symmetric(horizontal: 4), child: Text('لا توجد جداول لهذا الجهاز بعد.', style: TextStyle(fontSize: 13, color: WW.sub))),
      for (final s in mine) ...[
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: WW.line)),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(when(s), textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 17, fontWeight: FontWeight.w700)),
                Text('${s['days_text'] ?? 'كل يوم'}', style: const TextStyle(fontSize: 13, color: WW.sub)),
                if (s['estimate'] != null) Text(est(s['estimate']), style: const TextStyle(fontSize: 12, color: WW.sub)),
              ]),
            ),
            WWToggle(on: s['enabled'] == true, onTap: () => runHere(() => api.setScheduleEnabled(s['id'], s['enabled'] != true))),
            TextButton(
              onPressed: () => runHere(() => api.deleteSchedule(s['id'])),
              style: TextButton.styleFrom(foregroundColor: WW.red, minimumSize: const Size(0, 44)),
              child: const Text('حذف', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            ),
          ]),
        ),
        const SizedBox(height: 8),
      ],
      for (final t in timers) ...[
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(color: WW.warnBg, borderRadius: BorderRadius.circular(18), border: Border.all(color: WW.warnBorder)),
          child: Row(children: [
            const Icon(Icons.timer_outlined, size: 20, color: WW.pendingFg),
            const SizedBox(width: 12),
            Expanded(child: Text('مؤقّت نشط: ${t['text']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: WW.pendingText))),
            TextButton(
              onPressed: () => runHere(() => api.deleteTimer(t['id'])),
              style: TextButton.styleFrom(foregroundColor: WW.pendingText, minimumSize: const Size(0, 44)),
              child: const Text('إلغاء', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, decoration: TextDecoration.underline, decorationColor: WW.pendingText)),
            ),
          ]),
        ),
        const SizedBox(height: 8),
      ],
      const SizedBox(height: 6),
      WWBox(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('جدول جديد', style: h2),
          const SizedBox(height: 14),
          Row(children: [
            timeBox('وقت التشغيل', onTime, true),
            const SizedBox(width: 10),
            timeBox('وقت الإطفاء', offTime, false),
          ]),
          const SizedBox(height: 14),
          const Text('الأيام', style: label),
          const SizedBox(height: 8),
          Row(children: [for (final (n, name) in dayNames) dayBtn(n, name)]),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final (name, ds) in presets)
              GestureDetector(
                onTap: () => setState(() { days = [...ds]; review = null; }),
                child: Container(
                  constraints: const BoxConstraints(minHeight: 36),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: ds.length == days.length && ds.every(days.contains) ? WW.accentSel2 : Colors.white,
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: WW.field),
                  ),
                  child: Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                ),
              ),
          ]),
          const SizedBox(height: 14),
          if (r == null)
            WWButton('راجع الجدول', previewSchedule, kind: BtnKind.outline)
          else
            Container(
              decoration: BoxDecoration(borderRadius: BorderRadius.circular(18), border: Border.all(color: WW.accent, width: 1.5)),
              clipBehavior: Clip.antiAlias,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Container(
                  color: WW.ink,
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  child: const Text('راجع قبل الحفظ', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Colors.white)),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    reviewRow('الجهاز', Text('${r['device_name']} · ${r['room_name']}', textAlign: TextAlign.end, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                    reviewRow('الوقت', Text(when(r), textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 14, fontWeight: FontWeight.w600))),
                    reviewRow('الأيام', Text('${r['days_text']}', textAlign: TextAlign.end, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                    if (r['estimate'] != null)
                      Container(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: WW.line))),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          const Text('التقدير', style: TextStyle(fontSize: 14, color: WW.sub)),
                          const SizedBox(height: 2),
                          Text('≈ ${WW.fmt(r['estimate']['kwh'] as num?, 1)} kWh/day ≈ ${WW.fmt(r['estimate']['jod'] as num?, 2)} JD/day',
                              textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 14, fontWeight: FontWeight.w700)),
                          const Text('تقديري، غير مقاس', style: TextStyle(fontSize: 12, color: WW.pendingFg)),
                        ]),
                      ),
                    reviewRow('حارس السياسة', const Pill('✓ مسموح', fg: WW.ink), last: true),
                  ]),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
                  child: Row(children: [
                    Expanded(child: WWButton('تعديل', () => setState(() => review = null), kind: BtnKind.ghost, height: 50, radius: 14)),
                    const SizedBox(width: 8),
                    Expanded(child: WWButton('أكّد واحفظ', confirmSchedule, height: 50, radius: 14)),
                  ]),
                ),
              ]),
            ),
          if (formMsg.isNotEmpty)
            Padding(padding: const EdgeInsets.only(top: 8), child: Text(formMsg, style: const TextStyle(fontSize: 13, color: WW.pendingFg))),
        ]),
      ),
      const SizedBox(height: 14),
      WWBox(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('مؤقّت سريع', style: h2),
          const SizedBox(height: 12),
          quick('أطفئه بعد', false),
          const SizedBox(height: 12),
          quick('شغّله لمدة', true),
        ]),
      ),
      const SizedBox(height: 14),
    ];
  }

  static IconData _kindIcon(String kind) => kindIcon(kind);
}
