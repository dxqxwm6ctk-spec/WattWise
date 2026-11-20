// "الجدولة" tab: the smart water-heater schedule, plus timers and daily on/off
// schedules for any allowed device. They run on the server, and the Policy Guard
// checks each one when it is saved and again every time it fires.

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
  String? device;
  TimeOfDay? onTime, offTime;
  String formMsg = '';

  static String hhmm(TimeOfDay t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  static String minLabel(int n) => n == 30 ? '30 دقيقة' : n == 60 ? 'ساعة' : 'ساعتين';
  static String est(dynamic e) =>
      e == null ? '' : '≈ ${WW.fmt(e['kwh'], 1)} ك.و.س/يوم · ≈ ${WW.fmt(e['jod'], 2)} دينار/يوم (متوقّع مش مقاس)';

  @override
  void dispose() {
    hint.dispose();
    super.dispose();
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

  Future<void> addSchedule() async {
    try {
      await widget.api.addSchedule(device!, onTime == null ? null : hhmm(onTime!), offTime == null ? null : hhmm(offTime!));
      setState(() { onTime = null; offTime = null; formMsg = 'انضاف الجدول ✓'; });
    } catch (e) {
      setState(() => formMsg = '$e');
    }
  }

  Future<void> pick(bool isOn) async {
    final t = await showTimePicker(context: context, initialTime: (isOn ? onTime : offTime) ?? TimeOfDay.now());
    if (t != null) setState(() => isOn ? onTime = t : offTime = t);
  }

  @override
  Widget build(BuildContext context) {
    final a = (widget.st['automation'] as Map<String, dynamic>?) ?? const {'schedules': [], 'timers': [], 'devices': []};
    final devices = a['devices'] as List;
    if (devices.isNotEmpty && !devices.any((d) => d['id'] == device)) {
      device = '${(devices.firstWhere((d) => d['id'] == 'heater', orElse: () => devices.first))['id']}';
    }
    final hasHeater = (widget.st['devices'] as List).any((d) => d['kind'] == 'heater' && d['tier'] == 'T1' && d['sensitive'] != true);
    final p = proposal;
    const sub = TextStyle(fontSize: 13, color: WW.sub);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
      WWBox(
        radius: 22,
        padding: 18,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('جدول أو مؤقّت لجهاز', style: sub),
          const SizedBox(height: 10),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final d in devices)
              ChoiceChip(
                label: Text('${d['name']}'),
                selected: device == d['id'],
                onSelected: (_) => setState(() { device = '${d['id']}'; formMsg = ''; }),
                selectedColor: WW.ink,
                labelStyle: TextStyle(color: device == d['id'] ? WW.paper : WW.ink, fontWeight: FontWeight.w600),
                showCheckmark: false,
              ),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: lineButton(onTime == null ? 'يشتغل الساعة…' : 'يشتغل ${hhmm(onTime!)}', () => pick(true), height: 46)),
            const SizedBox(width: 8),
            Expanded(child: lineButton(offTime == null ? 'يطفي الساعة…' : 'يطفي ${hhmm(offTime!)}', () => pick(false), height: 46)),
          ]),
          const SizedBox(height: 10),
          darkButton('ضيف الجدول', device == null ? null : addSchedule, height: 48),
          if (formMsg.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Text(formMsg, style: const TextStyle(fontSize: 12.5, color: WW.pendingText))),
          const Divider(height: 22, color: Color(0xFFEFECE3)),
          for (final isFor in [false, true]) ...[
            Wrap(spacing: 6, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
              SizedBox(width: 78, child: Text(isFor ? 'شغّله لمدة' : 'طفّيه بعد', style: const TextStyle(fontSize: 12.5, color: WW.sub))),
              for (final n in [30, 60, 120])
                lineButton(minLabel(n), device == null ? null : () => widget.run(() => widget.api.addTimer(device!, n, runNow: isFor)), height: 38),
            ]),
            const SizedBox(height: 8),
          ],
        ]),
      ),
      if ((a['timers'] as List).isNotEmpty) ...[
        const SizedBox(height: 12),
        const Text('مؤقّتات شغّالة', style: sub),
        for (final t in a['timers'] as List) ...[
          const SizedBox(height: 8),
          WWBox(
            color: WW.pendingBg,
            border: WW.pendingBorder,
            padding: 12,
            child: Row(children: [
              Expanded(child: Text('${t['text']}', style: const TextStyle(fontSize: 14))),
              lineButton('إلغاء', () => widget.run(() => widget.api.deleteTimer(t['id'])), height: 36, border: const Color(0xFFD9C38A)),
            ]),
          ),
        ],
      ],
      const SizedBox(height: 12),
      const Text('جداولك', style: sub),
      if ((a['schedules'] as List).isEmpty)
        const Padding(padding: EdgeInsets.only(top: 6), child: Text('ما في جداول لسا.', style: sub)),
      for (final r in a['schedules'] as List) ...[
        const SizedBox(height: 8),
        WWBox(
          padding: 12,
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${r['device_name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                Text([if (r['on_time'] != null) 'تشغيل ${r['on_time']}', if (r['off_time'] != null) 'إطفاء ${r['off_time']}'].join(' ← '),
                    style: WW.mono.copyWith(fontSize: 13)),
                Text(est(r['estimate']), style: const TextStyle(fontSize: 11.5, color: WW.sub)),
              ]),
            ),
            WWToggle(on: r['enabled'] == true, onTap: () => widget.run(() => widget.api.setScheduleEnabled(r['id'], r['enabled'] != true))),
            const SizedBox(width: 8),
            lineButton('حذف', () => widget.run(() => widget.api.deleteSchedule(r['id'])), height: 36, border: const Color(0xFFF0C2B8)),
          ]),
        ),
      ],
    ]);
  }
}
