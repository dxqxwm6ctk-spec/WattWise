// "الجدولة" tab. On top: Home / Building / Lab. Each one shows its devices
// grouped by room. Tap a device to switch it now, add a quick timer, or add a
// detailed daily schedule (on time, off time, which days). A schedule is saved
// only after the person reviews it and taps "confirm" (the Policy Guard checks it
// first, and again every time it fires). Plus the smart water-heater schedule.

import 'dart:async';


import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/assistant_widgets.dart';

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

  static const sites = [('home', '🏠 البيت'), ('building', '🏢 المبنى'), ('lab', '🔬 المختبر')];
  // 0 = Sunday ... 6 = Saturday (the server's numbers). Shown from Saturday.
  static const dayNames = [(6, 'سبت'), (0, 'أحد'), (1, 'إثنين'), (2, 'ثلاثاء'), (3, 'أربعاء'), (4, 'خميس'), (5, 'جمعة')];
  static const allDays = [0, 1, 2, 3, 4, 5, 6];
  static const presets = [('كل يوم', allDays), ('أيام الدوام', [0, 1, 2, 3, 4]), ('الويكند', [5, 6])];

  static String hhmm(TimeOfDay t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  static String minLabel(int n) => n == 30 ? '30 دقيقة' : n == 60 ? 'ساعة' : 'ساعتين';
  static String est(dynamic e) =>
      e == null ? '' : '≈ ${WW.fmt(e['kwh'], 1)} ك.و.س/يوم · ≈ ${WW.fmt(e['jod'], 2)} دينار/يوم (متوقّع مش مقاس)';

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
    final t = p['total'];
    setState(() {
      proposal = null;
      heaterMsg = 'انحفظ جدول السخّان ✓ بيستهلك ≈ ${WW.fmt(t['kwh'], 1)} ك.و.س باليوم (≈ ${WW.fmt(t['jod'], 2)} دينار، متوقّع مش مقاس).';
    });
  }

  Future<void> previewSchedule() async {
    if (onTime == null && offTime == null) {
      setState(() => formMsg = 'اختار وقت تشغيل أو وقت إطفاء (أو الاثنين).');
      return;
    }
    if (days.isEmpty) {
      setState(() => formMsg = 'اختار يوم واحد على الأقل.');
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
      setState(() { resetForm(); formMsg = 'انحفظ الجدول ✓'; });
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
    final hasHeater = site == widget.api.site && dev == null &&
        (widget.st['devices'] as List).any((d) => d['kind'] == 'heater' && d['tier'] == 'T1' && d['sensitive'] != true);
    final p = proposal;
    const sub = TextStyle(fontSize: 13, color: WW.sub);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      siteTabs(),
      const SizedBox(height: 12),
      if (a == null)
        const Text('عم نحمّل…', style: sub)
      else if (dev != null)
        detail(a, dev)
      else
        ...rooms(a),
      const SizedBox(height: 12),
      if (hasHeater) ...[
        WWBox(
          color: WW.greenBg,
          radius: 22,
          padding: 18,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('سخّان الماء الذكي', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            const Text('من أكبر الأحمال. بنسخّنه قبل الحمّام بس، وما بيشتغل أكثر من ٣ ساعات متواصلة.',
                style: TextStyle(fontSize: 13, height: 1.65, color: WW.greenText)),
            const SizedBox(height: 10),
            TextField(controller: hint, decoration: wwField('متى بتحمّموا؟ مثلاً: الصبح ٦ ونص')),
            const SizedBox(height: 10),
            darkButton(busy ? 'عم نخطّط…' : 'اقترحلي جدول للسخّان', suggest),
            if (p != null) ...[
              const SizedBox(height: 10),
              Text('${p['reply']}', style: const TextStyle(fontSize: 14, height: 1.6)),
              for (final i in p['items'] as List) ...[
                const SizedBox(height: 8),
                WWBox(padding: 12, radius: 12, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Directionality(textDirection: TextDirection.ltr,
                      child: Text('${i['on_time']} → ${i['off_time']}', style: WW.mono.copyWith(fontSize: 14, fontWeight: FontWeight.w600))),
                  Text('${i['why']}', style: const TextStyle(fontSize: 13)),
                  Text(est(i['estimate']), style: const TextStyle(fontSize: 12, color: Color(0xFF5E5C55))),
                ])),
              ],
              const SizedBox(height: 8),
              Text('المجموع ≈ ${WW.fmt(p['total']['kwh'], 1)} ك.و.س باليوم ≈ ${WW.fmt(p['total']['jod'], 2)} دينار (متوقّع مش مقاس)',
                  style: const TextStyle(fontSize: 13, color: WW.greenText, fontWeight: FontWeight.w600)),
              const SizedBox(height: 10),
              Row(children: [
                Expanded(child: lineButton('لا', () => setState(() => proposal = null), height: 48, border: const Color(0xFFB8DB7A))),
                if ((p['items'] as List).isNotEmpty) ...[
                  const SizedBox(width: 8),
                  Expanded(flex: 14, child: darkButton('إيه، اعتمده', apply, height: 48)),
                ],
              ]),
            ],
            if (heaterMsg.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(heaterMsg, style: const TextStyle(fontSize: 13.5, height: 1.6, color: WW.greenText, fontWeight: FontWeight.w600)),
            ],
          ]),
        ),
        const SizedBox(height: 12),
      ],
    ]);
  }

  // ---------- Home / Building / Lab ----------

  Widget siteTabs() => Row(children: [
        for (final (i, x) in sites.indexed) ...[
          if (i > 0) const SizedBox(width: 8),
          Expanded(
            child: GestureDetector(
              onTap: () {
                if (site == x.$1) return;
                setState(() { site = x.$1; device = null; formMsg = ''; resetForm(); });
                load(x.$1);
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                decoration: BoxDecoration(
                  color: site == x.$1 ? const Color(0xFFEEF8DA) : Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: site == x.$1 ? const Color(0xFF8DBF3A) : WW.line, width: 1.5),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(x.$2, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(siteSub(data[x.$1]), maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 11, color: WW.sub)),
                ]),
              ),
            ),
          ),
        ],
      ]);

  static String siteSub(Map<String, dynamic>? d) {
    if (d == null) return '…';
    final r = (d['rooms'] as List).length, n = (d['devices'] as List).length, s = (d['schedules'] as List).length;
    return '$r ${r > 2 ? 'غرف' : 'غرفة'} · $n جهاز${s > 0 ? ' · $s جدول' : ''}';
  }

  static String span(dynamic r) => '${r['on_time'] ?? '··'}→${r['off_time'] ?? '··'}';
  static String when(dynamic r) =>
      [if (r['on_time'] != null) 'يشتغل ${r['on_time']}', if (r['off_time'] != null) 'يطفي ${r['off_time']}'].join(' ← ');

  // ---------- rooms and their devices ----------

  List<Widget> rooms(Map<String, dynamic> a) {
    final out = <Widget>[];
    for (final room in a['rooms'] as List) {
      final devs = (a['devices'] as List).where((d) => d['room'] == room['id']).toList();
      final locked = (a['locked'] as List).where((d) => d['room'] == room['id']).toList();
      if (devs.isEmpty && locked.isEmpty) continue;
      out.add(WWBox(
        radius: 16,
        padding: 12,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(child: Text('${room['name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
            Text('${devs.length + locked.length} ${devs.length + locked.length > 2 ? 'أجهزة' : 'جهاز'}',
                style: const TextStyle(fontSize: 11.5, color: WW.sub)),
          ]),
          for (final d in devs) ...[const SizedBox(height: 6), deviceRow(a, d)],
          for (final d in locked) ...[
            const SizedBox(height: 6),
            Opacity(
              opacity: 0.6,
              child: greyBox([
                Text('🔒 ${d['name']}', style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
                Text('${d['why']}', style: const TextStyle(fontSize: 11.5, color: WW.sub)),
              ]),
            ),
          ],
        ]),
      ));
      out.add(const SizedBox(height: 10));
    }
    if (out.isEmpty) out.add(const Text('ما في أجهزة بهالموقع.', style: TextStyle(fontSize: 13, color: WW.sub)));
    return out;
  }

  Widget deviceRow(Map<String, dynamic> a, dynamic d) {
    final mine = (a['schedules'] as List).where((r) => r['device_id'] == d['id']).toList();
    final hasTimer = (a['timers'] as List).any((t) => t['device_id'] == d['id']);
    final line = mine.isEmpty ? 'بدون جدول' : mine.map(span).join('  ');
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => setState(() { device = '${d['id']}'; formMsg = ''; resetForm(); }),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
        decoration: BoxDecoration(color: WW.paper, borderRadius: BorderRadius.circular(12)),
        child: Row(children: [
          Container(width: 9, height: 9, decoration: BoxDecoration(
              shape: BoxShape.circle, color: d['is_on'] == true ? const Color(0xFF7BC33A) : const Color(0x5577756C))),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${d['name']}', style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
              Text(hasTimer ? '$line  ⏱ مؤقّت' : line,
                  style: (mine.isEmpty ? const TextStyle(color: WW.sub) : WW.mono).copyWith(fontSize: 11.5)),
            ]),
          ),
          const Text('جدولة ‹', style: TextStyle(fontSize: 11.5, color: WW.sub)),
        ]),
      ),
    );
  }

  // ---------- one device: control now, its schedules, a new schedule, quick timers ----------

  Widget detail(Map<String, dynamic> a, Map<String, dynamic> d) {
    const sub = TextStyle(fontSize: 11.5, color: WW.sub);
    const sec = TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: WW.sub);
    final mine = (a['schedules'] as List).where((r) => r['device_id'] == d['id']).toList();
    final timers = (a['timers'] as List).where((t) => t['device_id'] == d['id']).toList();
    final on = d['is_on'] == true;
    final r = review;
    Widget chip(String label, bool sel, VoidCallback onTap) => ChoiceChip(
          label: Text(label),
          selected: sel,
          onSelected: (_) => onTap(),
          selectedColor: WW.ink,
          labelStyle: TextStyle(color: sel ? WW.paper : WW.ink, fontWeight: FontWeight.w600, fontSize: 12.5),
          showCheckmark: false,
        );
    return WWBox(
      radius: 18,
      padding: 14,
      border: const Color(0xFF8DBF3A),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton(
            onPressed: () => setState(() { device = null; formMsg = ''; resetForm(); }),
            child: const Text('→ كل الأجهزة', style: TextStyle(color: WW.sub, fontWeight: FontWeight.w600)),
          ),
        ),
        Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${d['name']}', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              Text('${d['room_name']} · ≈ ${d['watts']} واط · ${on ? 'شغّال هسا' : 'مطفي هسا'}', style: sub),
            ]),
          ),
          on
              ? lineButton('طفّيه هسا', () => runHere(() => api.toggle('${d['id']}', false)), height: 40)
              : darkButton('شغّله هسا', () => runHere(() => api.toggle('${d['id']}', true)), height: 40),
        ]),
        const Divider(height: 22, color: Color(0xFFEFECE3)),
        const Text('جداول هالجهاز', style: sec),
        const SizedBox(height: 6),
        if (mine.isEmpty) const Text('ما في جداول لهالجهاز لسا.', style: TextStyle(fontSize: 12.5, color: WW.sub)),
        for (final s in mine) ...[
          greyBox([
            Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(when(s), style: WW.mono.copyWith(fontSize: 13)),
                  Text('${s['days_text'] ?? 'كل يوم'}', style: sub),
                  if (s['estimate'] != null) Text(est(s['estimate']), style: sub),
                ]),
              ),
              WWToggle(on: s['enabled'] == true, onTap: () => runHere(() => api.setScheduleEnabled(s['id'], s['enabled'] != true))),
              const SizedBox(width: 6),
              lineButton('حذف', () => runHere(() => api.deleteSchedule(s['id'])), height: 34, border: const Color(0xFFF0C2B8)),
            ]),
          ]),
          const SizedBox(height: 6),
        ],
        for (final t in timers) ...[
          WWBox(
            color: WW.pendingBg,
            border: WW.pendingBorder,
            padding: 10,
            radius: 12,
            child: Row(children: [
              Expanded(child: Text('⏱ ${t['text']}', style: const TextStyle(fontSize: 13))),
              lineButton('إلغاء', () => runHere(() => api.deleteTimer(t['id'])), height: 34, border: const Color(0xFFD9C38A)),
            ]),
          ),
          const SizedBox(height: 6),
        ],
        const Divider(height: 22, color: Color(0xFFEFECE3)),
        const Text('جدول جديد', style: sec),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: lineButton(onTime == null ? 'يشتغل الساعة…' : 'يشتغل ${hhmm(onTime!)}', () => pick(true), height: 46)),
          const SizedBox(width: 8),
          Expanded(child: lineButton(offTime == null ? 'يطفي الساعة…' : 'يطفي ${hhmm(offTime!)}', () => pick(false), height: 46)),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final (label, ds) in presets)
            chip(label, ds.length == days.length && ds.every(days.contains), () => setState(() { days = [...ds]; review = null; })),
        ]),
        const SizedBox(height: 6),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final (n, label) in dayNames)
            chip(label, days.contains(n), () => setState(() {
                  days = days.contains(n) ? days.where((x) => x != n).toList() : [...days, n];
                  review = null;
                })),
        ]),
        const SizedBox(height: 10),
        if (r == null)
          darkButton('راجع الجدول', previewSchedule, height: 46)
        else
          WWBox(
            color: WW.pendingBg,
            border: WW.pendingBorder,
            radius: 14,
            padding: 12,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('راجع قبل ما نحفظ', style: TextStyle(fontWeight: FontWeight.w700, color: WW.pendingText)),
              const SizedBox(height: 4),
              Text('${r['device_name']} · ${r['room_name']}', style: const TextStyle(fontSize: 13.5)),
              Text(when(r), style: WW.mono.copyWith(fontSize: 13.5)),
              Text('${r['days_text']}', style: const TextStyle(fontSize: 13.5)),
              if (r['estimate'] != null) Text(est(r['estimate']), style: sub),
              const SizedBox(height: 4),
              const Text('✓ حارس السياسات فحصه ووافق. رح يفحصه كمان مرة كل ما ييجي وقته.',
                  style: TextStyle(fontSize: 12, color: WW.greenText)),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(flex: 14, child: darkButton('أكّد واحفظ', confirmSchedule, height: 44)),
                const SizedBox(width: 8),
                Expanded(child: lineButton('عدّل', () => setState(() => review = null), height: 44)),
              ]),
            ]),
          ),
        if (formMsg.isNotEmpty)
          Padding(padding: const EdgeInsets.only(top: 6), child: Text(formMsg, style: const TextStyle(fontSize: 12.5, color: WW.pendingText))),
        const Divider(height: 22, color: Color(0xFFEFECE3)),
        const Text('مؤقّت سريع', style: sec),
        const SizedBox(height: 8),
        for (final isFor in [false, true]) ...[
          Wrap(spacing: 6, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
            SizedBox(width: 74, child: Text(isFor ? 'شغّله لمدة' : 'طفّيه بعد', style: const TextStyle(fontSize: 12.5, color: WW.sub))),
            for (final n in [30, 60, 120])
              lineButton(minLabel(n), () => runHere(() => api.addTimer('${d['id']}', n, runNow: isFor)), height: 36),
          ]),
          const SizedBox(height: 6),
        ],
      ]),
    );
  }
}
