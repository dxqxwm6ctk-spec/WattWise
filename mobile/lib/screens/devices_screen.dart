// "الأجهزة" tab: every device with its on/off switch, and the two add-device wizards.

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/device_visuals.dart';
import '../widgets/wizard.dart';
import 'add_plug_wizard.dart';

const deviceTypes = [
  (k: 'ac', label: 'مكيّف', locked: false),
  (k: 'light', label: 'إضاءة', locked: false),
  (k: 'heater', label: 'سخّان', locked: false),
  (k: 'tv', label: 'تلفاز', locked: false),
  (k: 'washer', label: 'غسالة', locked: false),
  (k: 'pc', label: 'حاسوب', locked: false),
  (k: 'router', label: 'راوتر', locked: false),
  (k: 'fridge', label: 'ثلاجة', locked: true),
  (k: 'medical', label: 'جهاز طبي', locked: true),
  (k: 'other', label: 'آخر', locked: false),
];

class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key, required this.st, required this.api, required this.run});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;

  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  bool onlyRunning = false;

  void _openPlug() => openWizard(context, widget.st, (s) => AddPlugWizard(st: s, api: widget.api, run: widget.run, onClose: () => Navigator.pop(context)));
  void _openMeter() => openWizard(context, widget.st, (s) => AddDeviceWizard(st: s, api: widget.api, run: widget.run, onClose: () => Navigator.pop(context)));

  @override
  Widget build(BuildContext context) {
    final st = widget.st;
    final devices = st['devices'] as List<dynamic>;
    final comfort = st['comfort'] as Map<String, dynamic>;
    final pending = st['pending'] as Map<String, dynamic>?;
    final pendingId = pending?['device_id'] as String?;
    final pendingOn = pending?['turn_on'] == true;
    final running = devices.where((d) => d['is_on'] == true).toList();
    final total = running.fold<num>(0, (s, d) => s + (d['est_w'] as num));
    final shown = onlyRunning ? running.where((d) => d['tier'] != 'T2').toList() : devices;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (st['agent']['safe_mode'] == true) ...[
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(color: WW.pendingBg, borderRadius: BorderRadius.circular(16), border: Border.all(color: WW.warnBorder)),
          child: const Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(padding: EdgeInsets.only(top: 2), child: Icon(Icons.gpp_maybe_outlined, size: 20, color: WW.pendingText)),
            SizedBox(width: 10),
            Expanded(
              child: Text.rich(TextSpan(children: [
                TextSpan(text: 'وضع الأمان: ', style: TextStyle(fontWeight: FontWeight.w700)),
                TextSpan(text: 'لن يفعل WattWise شيئًا حتى يعود الاتصال.'),
              ]), style: TextStyle(fontSize: 14, height: 1.6, color: WW.pendingText)),
            ),
          ]),
        ),
        const SizedBox(height: 12),
      ],
      Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('الأجهزة', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
            Text.rich(TextSpan(children: [
              TextSpan(text: '${running.length} تعمل · '),
              TextSpan(text: WW.watts(total), style: WW.mono),
            ]), style: const TextStyle(fontSize: 13, color: WW.sub)),
          ]),
        ),
        Segmented(labels: const ['الكل', 'العاملة فقط'], selected: onlyRunning ? 1 : 0, expand: false, onTap: (i) => setState(() => onlyRunning = i == 1)),
      ]),
      const SizedBox(height: 12),
      for (final d in shown) ...[
        _DeviceTile(key: ValueKey(d['id']), d: d, comfort: comfort, api: widget.api, run: widget.run, pending: d['id'] == pendingId, pendingTurnOn: pendingOn),
        const SizedBox(height: 10),
      ],
      if (shown.isEmpty) ...[
        DashedBox(
          color: WW.field,
          padding: 0,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 20),
            child: Column(children: [
              IconTile(icon: Icons.power_outlined, bg: WW.neutralBg, fg: WW.sub, size: 56, iconSize: 26, radius: 18),
              const SizedBox(height: 10),
              const Text('لا يوجد جهاز يعمل الآن.', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              const Text('كل الأجهزة مطفأة، ما عدا المحمية.', textAlign: TextAlign.center, style: TextStyle(fontSize: 14, color: WW.sub)),
            ]),
          ),
        ),
        const SizedBox(height: 10),
      ],
      const SizedBox(height: 4),
      WWButton('+ إضافة مقبس ذكي', _openPlug),
      const SizedBox(height: 8),
      WWButton('+ إضافة جهاز عبر العدّاد الرئيسي', _openMeter, kind: BtnKind.outline),
    ]);
  }
}

class _DeviceTile extends StatefulWidget {
  const _DeviceTile({super.key, required this.d, required this.comfort, required this.api, required this.run, required this.pending, this.pendingTurnOn = false});
  final dynamic d;
  final Map<String, dynamic> comfort;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  final bool pendingTurnOn;
  final bool pending; // the agent asked to switch this device and waits for the owner

  @override
  State<_DeviceTile> createState() => _DeviceTileState();
}

class _DeviceTileState extends State<_DeviceTile> {
  // Shown right away when the owner taps, so the animation starts at once.
  // Cleared when the server answers (if it refuses, the card goes back).
  bool? optimistic;

  dynamic get d => widget.d;

  Future<void> _send(bool on, {bool confirmed = false}) async {
    HapticFeedback.lightImpact();
    setState(() => optimistic = on);
    await widget.run(() => widget.api.toggle(d['id'], on, confirmed: confirmed));
    if (mounted) setState(() => optimistic = null);
  }

  Future<void> _toggle(BuildContext context) async {
    final on = d['is_on'] == true;
    if (d['tier'] == 'T2') {
      HapticFeedback.heavyImpact();
      return widget.run(() => widget.api.toggle(d['id'], !on)); // the server explains why it is blocked
    }
    if (d['sensitive'] == true && on) {
      final ok = await confirmSheet(context,
          title: 'إطفاء ${d['name']}؟',
          body: 'سينقطع الإنترنت هنا، وسيفقد التطبيق اتصاله بالخادم حتى تعيد تشغيله يدويًا.',
          ok: 'نعم، أطفئه');
      if (ok) await _send(false, confirmed: true);
      return;
    }
    await _send(!on);
  }

  Future<void> _remove(BuildContext context) async {
    final ok = await confirmSheet(context,
        title: 'إزالة ${d['name']}؟',
        body: 'سيتوقف WattWise عن قراءة هذا المقبس ولن يقترح له أي إجراء. يبقى المقبس نفسه كما هو، ويمكنك إضافته مرة أخرى لاحقًا.',
        ok: 'إزالة',
        icon: Icons.delete_outline_rounded);
    if (ok) await widget.run(() => widget.api.removePlug(d['id']));
  }

  @override
  Widget build(BuildContext context) {
    final locked = d['tier'] == 'T2';
    final on = optimistic ?? (d['is_on'] == true);
    final kind = '${d['kind']}';
    final accent = deviceAccent(kind);
    // While waiting for the server we show the device's known signature.
    final watts = optimistic == null ? (d['est_w'] as num) : (on ? d['signature_w'] as num : 0);
    final state = locked
        ? 'محمي · يعمل دائمًا'
        : on
            ? runningWord(kind)
            : d['agent_off'] != 0
                ? 'أطفأه WattWise بموافقتك'
                : 'مطفأ';
    const dur = Duration(milliseconds: 350);

    return AnimatedContainer(
      duration: dur,
      curve: Curves.easeInOutCubic,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: on ? WW.dark : Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: widget.pending ? WW.accent : on ? WW.accent.withValues(alpha: 0.24) : WW.line,
          width: widget.pending ? 2 : 1,
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          SizedBox(
            width: 52,
            height: 52,
            child: Stack(clipBehavior: Clip.none, children: [
              DeviceIcon(kind: kind, on: on, locked: locked, size: 48, dark: on),
              if (locked)
                PositionedDirectional(
                  bottom: 0,
                  end: 0,
                  child: Container(
                    width: 22,
                    height: 22,
                    decoration: const BoxDecoration(color: WW.ink, shape: BoxShape.circle),
                    child: const Icon(Icons.lock_outline_rounded, size: 12, color: Colors.white),
                  ),
                ),
            ]),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${d['name']}', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: on ? Colors.white : WW.ink)),
              const SizedBox(height: 1),
              Text('${d['room_name']} · $state',
                  overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 13, color: on ? WW.darkSub : WW.sub)),
            ]),
          ),
          const SizedBox(width: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(minWidth: 62),
            child: AnimatedWatts(
              watts: on ? watts : 0,
              style: WW.mono.copyWith(fontSize: 16, fontWeight: FontWeight.w700, color: on ? accent : const Color(0xFF8A8A94)),
              unitStyle: WW.mono.copyWith(fontSize: 16, fontWeight: FontWeight.w700, color: on ? accent : const Color(0xFF8A8A94)),
            ),
          ),
          WWToggle(on: on, locked: locked, onDark: on, onTap: () => _toggle(context)),
        ]),
        AnimatedSize(
          duration: dur,
          curve: Curves.easeOutCubic,
          child: widget.pending
              ? Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(color: WW.pendingBg, borderRadius: BorderRadius.circular(12)),
                    child: Row(children: [
                      Container(width: 8, height: 8, decoration: const BoxDecoration(color: WW.pendingFg, shape: BoxShape.circle)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text('يريد WattWise ${widget.pendingTurnOn ? 'تشغيله' : 'إطفاءه'} · بانتظار موافقتك في البيت',
                            style: const TextStyle(fontSize: 13, color: WW.pendingText, fontWeight: FontWeight.w600)),
                      ),
                    ]),
                  ),
                )
              : const SizedBox(width: double.infinity),
        ),
        PlugLine(d: d, dark: on, onRemove: () => _remove(context)),
      ]),
    );
  }
}

/// 4 steps: type -> room -> measure the signature on the main meter -> what the agent may do.
class AddDeviceWizard extends StatefulWidget {
  const AddDeviceWizard({super.key, required this.st, required this.api, required this.run, required this.onClose});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  final VoidCallback onClose;

  @override
  State<AddDeviceWizard> createState() => _AddDeviceWizardState();
}

class _AddDeviceWizardState extends State<AddDeviceWizard> {
  int step = 0;
  String? type;
  String? room;
  bool allow = true;
  final nameCtrl = TextEditingController();

  static const meterKinds = [
    (k: 'ac', label: 'مكيّف', locked: false),
    (k: 'light', label: 'إضاءة', locked: false),
    (k: 'heater', label: 'سخّان', locked: false),
    (k: 'tv', label: 'تلفاز', locked: false),
    (k: 'washer', label: 'غسالة', locked: false),
    (k: 'pc', label: 'حاسوب', locked: false),
    (k: 'router', label: 'راوتر', locked: false),
    (k: 'fridge', label: 'ثلاجة', locked: true),
    (k: 'other', label: 'آخر', locked: false),
  ];

  Map<String, dynamic>? get learn => widget.st['learn'] as Map<String, dynamic>?;
  int get learnedW => learn != null && learn!['status'] == 'done' ? (learn!['learned_w'] as num).toInt() : 0;
  bool get measuring => learn != null && learn!['status'] == 'measuring';
  bool get canNext => [type != null, room != null, learnedW > 0, true][step];
  bool get lockedType => deviceTypes.any((x) => x.k == type && x.locked);

  @override
  void dispose() {
    nameCtrl.dispose();
    super.dispose();
  }

  Future<void> _cancel() async {
    await widget.run(() => widget.api.cancelLearning());
    widget.onClose();
  }

  Future<void> _finish() async {
    final t = deviceTypes.firstWhere((x) => x.k == type);
    final roomName = (widget.st['rooms'] as List).firstWhere((r) => r['id'] == room)['name'];
    final name = nameCtrl.text.trim().isEmpty ? '${t.label} $roomName' : nameCtrl.text.trim();
    var ok = false;
    await widget.run(() async {
      await widget.api.addDevice(kind: type!, room: room!, name: name, allow: allow && !lockedType);
      ok = true;
    });
    if (ok) widget.onClose();
  }

  List<Widget> _body() {
    switch (step) {
      case 0:
        return [
          ...stepHead('ما نوع الجهاز؟', 'سيتعرّف WattWise على الجهاز من بصمته على العدّاد الرئيسي.'),
          KindGrid(kinds: meterKinds, selected: type, onPick: (k) => setState(() => type = k)),
        ];
      case 1:
        return [
          ...stepHead('أين هو؟'),
          for (final r in widget.st['rooms'] as List) ...[
            RadioRow(on: room == r['id'], title: '${r['name']}', dotFirst: false, onTap: () => setState(() => room = '${r['id']}')),
            const SizedBox(height: 8),
          ],
          const SizedBox(height: 8),
          const Text.rich(TextSpan(children: [
            TextSpan(text: 'الاسم '),
            TextSpan(text: '(اختياري)', style: TextStyle(fontWeight: FontWeight.w400, color: WW.sub, fontSize: 13)),
          ]), style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          TextField(controller: nameCtrl, decoration: wwField('مثال: غسالة الحمّام')),
        ];
      case 2:
        Widget badge(String n) => Container(
              width: 26,
              height: 26,
              alignment: Alignment.center,
              decoration: const BoxDecoration(color: WW.ink, shape: BoxShape.circle),
              child: Text(n, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Colors.white)),
            );
        final price = (widget.st['bill']['price_jod_per_kwh'] as num).toDouble();
        return [
          ...stepHead('لنتعرّف عليه'),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            badge('1'),
            const SizedBox(width: 12),
            const Expanded(child: Text('تأكّد أن الجهاز موصول بمقبس ذكي أو مرحّل (يركّبه كهربائي)، وأطفئ الأجهزة الكبيرة الأخرى إن استطعت.', style: TextStyle(fontSize: 14.5, height: 1.6))),
          ]),
          const SizedBox(height: 10),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            badge('2'),
            const SizedBox(width: 12),
            const Expanded(child: Text('شغّل الجهاز الآن من زرّه، ثم اضغط «شغّلته».', style: TextStyle(fontSize: 14.5, height: 1.6))),
          ]),
          const SizedBox(height: 14),
          WWBox(
            padding: 0,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 22),
              child: Column(children: [
                if (measuring) ...[
                  const _MeasureBars(),
                  const SizedBox(height: 14),
                  const Text('جارٍ القياس…', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  const Text('نقارن العدّاد قبل التشغيل وبعده.', textAlign: TextAlign.center, style: TextStyle(fontSize: 13.5, color: WW.sub)),
                ] else if (learnedW > 0) ...[
                  const IconTile(icon: Icons.check_rounded, bg: WW.accentBg, fg: WW.ink, size: 72, iconSize: 34, radius: 36),
                  const SizedBox(height: 14),
                  const Text('تم التعلّم ✓', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: WW.green)),
                  const SizedBox(height: 6),
                  Text.rich(
                    TextSpan(children: [
                      TextSpan(text: '≈ ${WW.fmt(learnedW / 1000 * price, 3)} JD'),
                      const TextSpan(text: ' / hr', style: TextStyle(fontSize: 15, color: WW.sub, fontWeight: FontWeight.w500)),
                    ]),
                    textDirection: TextDirection.ltr,
                    style: WW.mono.copyWith(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text.rich(TextSpan(children: [
                    TextSpan(text: '+$learnedW W', style: WW.mono),
                    const TextSpan(text: ' · مقاس من العدّاد'),
                  ]), style: const TextStyle(fontSize: 13.5, color: WW.sub)),
                  LinkButton('قِس مرة أخرى', () => widget.run(() => widget.api.startLearning(type!))),
                ] else ...[
                  const IconTile(icon: Icons.power_settings_new_rounded, bg: WW.accentBg, fg: WW.ink, size: 72, iconSize: 34, radius: 36),
                  const SizedBox(height: 14),
                  SizedBox(width: double.infinity, child: WWButton('شغّلته', () => widget.run(() => widget.api.startLearning(type!)), height: 56, fontSize: 17)),
                ],
              ]),
            ),
          ),
        ];
      default:
        if (lockedType) {
          return [
            ...stepHead('ماذا يُسمح لـ WattWise أن يفعل؟'),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: WW.redBg, borderRadius: BorderRadius.circular(16)),
              child: const Text('جهاز حرج: لا يمكن إطفاؤه. نحسب تكلفته فقط.', style: TextStyle(fontSize: 14, height: 1.6, color: WW.red)),
            ),
          ];
        }
        return [
          ...stepHead('ماذا يُسمح لـ WattWise أن يفعل؟'),
          RadioRow(
            on: allow,
            onTap: () => setState(() => allow = true),
            title: 'اقترح إطفاءه وأنا أوافق',
            body: const Text('يحتاج مرحّلًا أو مقبسًا ذكيًا. نسألك في كل مرة، وإن لم تردّ لا نفعل شيئًا.', style: TextStyle(fontSize: 13.5, height: 1.6, color: WW.body)),
          ),
          const SizedBox(height: 10),
          RadioRow(
            on: !allow,
            onTap: () => setState(() => allow = false),
            title: 'احسب تكلفته فقط',
            body: const Text('يظهر في تفصيل الفاتورة، وتتحكم به أنت يدويًا.', style: TextStyle(fontSize: 13.5, height: 1.6, color: WW.body)),
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(color: WW.blueBg, borderRadius: BorderRadius.circular(16)),
            child: const Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Padding(padding: EdgeInsets.only(top: 2), child: Icon(Icons.shield_outlined, size: 18, color: Color(0xFF1F3A57))),
              SizedBox(width: 10),
              Expanded(child: Text('مهما اخترت، لن نشغّل أو نطفئ أي جهاز دون موافقتك.', style: TextStyle(fontSize: 13.5, height: 1.6, color: Color(0xFF1F3A57)))),
            ]),
          ),
        ];
    }
  }

  @override
  Widget build(BuildContext context) => WizardScaffold(
        title: 'جهاز عبر العدّاد الرئيسي',
        step: step,
        steps: 4,
        onClose: _cancel,
        onBack: () => setState(() => step--),
        nextLabel: step == 3 ? 'أضف الجهاز' : 'التالي',
        onNext: canNext ? () => step == 3 ? _finish() : setState(() => step++) : null,
        children: _body(),
      );
}

/// Five bars going up and down while the meter is measured.
class _MeasureBars extends StatefulWidget {
  const _MeasureBars();

  @override
  State<_MeasureBars> createState() => _MeasureBarsState();
}

class _MeasureBarsState extends State<_MeasureBars> with SingleTickerProviderStateMixin {
  late final AnimationController c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))..repeat();

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 56,
        child: AnimatedBuilder(
          animation: c,
          builder: (_, _) => Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.end, children: [
            for (var i = 0; i < 5; i++) ...[
              if (i > 0) const SizedBox(width: 6),
              Container(
                width: 10,
                height: 56 * (0.35 + 0.65 * (0.5 - 0.5 * math.cos((c.value - i * 0.15) * 2 * math.pi))),
                decoration: BoxDecoration(color: WW.ink, borderRadius: BorderRadius.circular(5)),
              ),
            ],
          ]),
        ),
      );
}
