// "الأجهزة" tab: manual control of every device, AC set point, and the add-device wizard.

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/device_visuals.dart';
import 'add_plug_wizard.dart';

const deviceTypes = [
  (k: 'ac', label: 'مكيّف', locked: false),
  (k: 'light', label: 'إنارة', locked: false),
  (k: 'heater', label: 'مدفأة / سخّان', locked: false),
  (k: 'tv', label: 'تلفزيون / شاشة', locked: false),
  (k: 'washer', label: 'غسالة ملابس / صحون', locked: false),
  (k: 'pc', label: 'كمبيوتر', locked: false),
  (k: 'router', label: 'راوتر / إنترنت', locked: false),
  (k: 'fridge', label: 'ثلاجة / فريزر', locked: true),
  (k: 'medical', label: 'جهاز طبي', locked: true),
  (k: 'other', label: 'جهاز آخر', locked: false),
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
  bool wizardOpen = false;
  bool onlyRunning = false;

  Widget _filterChip(String label, bool selected, VoidCallback onTap) => GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: selected ? WW.ink : Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: selected ? WW.ink : WW.line, width: 1.5),
          ),
          child: Text(label, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: selected ? WW.paper : WW.ink)),
        ),
      );
  bool plugOpen = false;

  @override
  Widget build(BuildContext context) {
    if (plugOpen) {
      return AddPlugWizard(st: widget.st, api: widget.api, run: widget.run, onClose: () => setState(() => plugOpen = false));
    }
    if (wizardOpen) {
      return AddDeviceWizard(st: widget.st, api: widget.api, run: widget.run, onClose: () => setState(() => wizardOpen = false));
    }
    final st = widget.st;
    final devices = st['devices'] as List<dynamic>;
    final comfort = st['comfort'] as Map<String, dynamic>;
    final pending = st['pending'] as Map<String, dynamic>?;
    final pendingId = pending?['device_id'] as String?;
    final pendingOn = pending?['turn_on'] == true;
    final shown = onlyRunning ? devices.where((d) => d['is_on'] == true).toList() : devices;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (st['agent']['safe_mode'] == true) ...[
        const SizedBox(height: 8),
        const WWBox(
          color: WW.pendingBg,
          border: WW.pendingBorder,
          child: Text('الوضع الآمن: لن ينفّذ WattWise شيئًا حتى يعود الاتصال.',
              style: TextStyle(fontSize: 13.5, height: 1.6, color: Color(0xFF6B4A00))),
        ),
      ],
      const SizedBox(height: 10),
      Row(children: [
        _filterChip('الكل', !onlyRunning, () => setState(() => onlyRunning = false)),
        const SizedBox(width: 8),
        _filterChip('العاملة فقط', onlyRunning, () => setState(() => onlyRunning = true)),
      ]),
      for (final d in shown) ...[
        const SizedBox(height: 8),
        _DeviceTile(key: ValueKey(d['id']), d: d, comfort: comfort, api: widget.api, run: widget.run, pending: d['id'] == pendingId, pendingTurnOn: pendingOn),
      ],
      if (shown.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child: Text('لا يوجد جهاز يعمل الآن.', textAlign: TextAlign.center, style: TextStyle(color: WW.sub)),
        ),
      const SizedBox(height: 16),
      SizedBox(
        height: 52,
        child: FilledButton(
          onPressed: () => setState(() => plugOpen = true),
          style: FilledButton.styleFrom(backgroundColor: WW.ink, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
          child: const Text('+ إضافة مقبس ذكي', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
        ),
      ),
      const SizedBox(height: 8),
      SizedBox(
        height: 52,
        child: OutlinedButton(
          onPressed: () => setState(() => wizardOpen = true),
          style: OutlinedButton.styleFrom(
            foregroundColor: WW.ink,
            side: const BorderSide(color: Color(0xFFB9B6AA), width: 1.5),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
          ),
          child: const Text('+ إضافة جهاز عبر العدّاد الرئيسي', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        ),
      ),
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
      final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: Text('إطفاء ${d['name']}؟'),
          content: const Text('سينقطع التطبيق ولن تصلك طلبات موافقة حتى تعيد تشغيله من الجهاز نفسه.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('لا')),
            FilledButton(onPressed: () => Navigator.pop(c, true), style: FilledButton.styleFrom(backgroundColor: WW.ink), child: const Text('نعم، أطفئه')),
          ],
        ),
      );
      if (ok == true) await _send(false, confirmed: true);
      return;
    }
    await _send(!on);
  }

  Future<void> _remove(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('إزالة ${d['name']}؟'),
        content: const Text('سيُزال الجهاز ومقبسه من WattWise، ويبقى المقبس نفسه كما هو.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('لا')),
          FilledButton(onPressed: () => Navigator.pop(c, true), style: FilledButton.styleFrom(backgroundColor: WW.ink), child: const Text('نعم، أزله')),
        ],
      ),
    );
    if (ok == true) await widget.run(() => widget.api.removePlug(d['id']));
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
    const dur = Duration(milliseconds: 450);

    return AnimatedContainer(
      duration: dur,
      curve: Curves.easeInOutCubic,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topRight,
          end: Alignment.bottomLeft,
          colors: on ? const [WW.darkCard1, WW.darkCard2] : const [Colors.white, Colors.white],
        ),
        border: Border.all(
          color: widget.pending ? WW.amber : on ? Color.lerp(WW.darkCard1, accent, 0.35)! : WW.line,
          width: widget.pending ? 2 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: on ? accent.withValues(alpha: 0.22) : Colors.transparent,
            blurRadius: 22,
            spreadRadius: -6,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          DeviceIcon(kind: kind, on: on, locked: locked, size: 54, dark: on),
          const SizedBox(width: 12),
          Expanded(
            child: AnimatedDefaultTextStyle(
              duration: dur,
              style: TextStyle(color: on ? WW.paper : WW.ink, fontFamily: DefaultTextStyle.of(context).style.fontFamily),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${d['name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                const SizedBox(height: 2),
                Row(children: [
                  if (on) ...[LiveDot(color: accent, size: 6), const SizedBox(width: 2)],
                  Flexible(
                    child: Text('${d['room_name']} · $state',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: on ? const Color(0xFFA9A79D) : WW.sub)),
                  ),
                ]),
              ]),
            ),
          ),
          const SizedBox(width: 8),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            WWToggle(on: on, locked: locked, onDark: on, onTap: () => _toggle(context)),
            const SizedBox(height: 6),
            AnimatedWatts(
              watts: watts,
              style: WW.mono.copyWith(fontSize: 13, fontWeight: FontWeight.w600, color: on ? accent : const Color(0xFFB9B6AA)),
              unitStyle: WW.mono.copyWith(fontSize: 10, color: on ? const Color(0xFF8E8C82) : const Color(0xFFB9B6AA)),
            ),
          ]),
        ]),
        AnimatedSize(
          duration: dur,
          curve: Curves.easeOutCubic,
          child: widget.pending
              ? Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    decoration: BoxDecoration(color: WW.pendingBg, borderRadius: BorderRadius.circular(12)),
                    child: Row(children: [
                      const LiveDot(color: Color(0xFFE8A21A), size: 6),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text('WattWise يريد ${widget.pendingTurnOn ? 'تشغيله' : 'إطفاءه'} · بانتظار موافقتك في صفحة البيت',
                            style: const TextStyle(fontSize: 12, color: WW.pendingText, fontWeight: FontWeight.w600)),
                      ),
                    ]),
                  ),
                )
              : const SizedBox(width: double.infinity),
        ),
        PlugLine(d: d, onRemove: () => _remove(context)),
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

  static const titles = ['ما نوع الجهاز؟', 'أين يوجد؟', 'لنتعرّف عليه', 'ما المسموح لـWattWise؟'];

  Map<String, dynamic>? get learn => widget.st['learn'] as Map<String, dynamic>?;
  int get learnedW => learn != null && learn!['status'] == 'done' ? (learn!['learned_w'] as num).toInt() : 0;
  bool get measuring => learn != null && learn!['status'] == 'measuring';
  bool get canNext => [type != null, room != null, learnedW > 0, true][step];

  Future<void> _cancel() async {
    await widget.run(() => widget.api.cancelLearning());
    widget.onClose();
  }

  Future<void> _finish() async {
    final t = deviceTypes.firstWhere((x) => x.k == type);
    final roomName = (widget.st['rooms'] as List).firstWhere((r) => r['id'] == room)['name'];
    final name = nameCtrl.text.trim().isEmpty ? '${t.label.split(' / ').first} $roomName' : nameCtrl.text.trim();
    var ok = false;
    await widget.run(() async {
      await widget.api.addDevice(kind: type!, room: room!, name: name, allow: allow);
      ok = true;
    });
    if (ok) widget.onClose();
  }

  Widget _chip(String label, bool selected, VoidCallback onTap) => Material(
        color: selected ? WW.ink : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: selected ? WW.ink : WW.line, width: 1.5)),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Container(
            constraints: const BoxConstraints(minHeight: 50),
            padding: const EdgeInsets.all(8),
            alignment: Alignment.center,
            child: Text(label, textAlign: TextAlign.center, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: selected ? WW.paper : WW.ink)),
          ),
        ),
      );

  Widget _grid(List<Widget> children) => GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 8,
        crossAxisSpacing: 8,
        childAspectRatio: 2.8,
        children: children,
      );

  Widget _body() {
    final t = type == null ? null : deviceTypes.firstWhere((x) => x.k == type);
    switch (step) {
      case 0:
        return _grid([for (final x in deviceTypes) _chip(x.label, type == x.k, () => setState(() => type = x.k))]);
      case 1:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _grid([for (final r in widget.st['rooms'] as List) _chip('${r['name']}', room == r['id'], () => setState(() => room = r['id']))]),
          const SizedBox(height: 12),
          const Text('الاسم (اختياري)', style: TextStyle(fontSize: 13, color: WW.sub)),
          const SizedBox(height: 6),
          TextField(
            controller: nameCtrl,
            decoration: InputDecoration(
              hintText: 'اسم الجهاز',
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: const BorderSide(color: WW.line, width: 1.5)),
            ),
          ),
        ]);
      case 2:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const WWBox(
            radius: 20,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('١. تأكّد أن الجهاز موصول بمقبس ذكي (يركّبه كهربائي).', style: TextStyle(fontSize: 14, height: 1.7)),
              Text('٢. عندما تكون جاهزًا، شغّل الجهاز من زرّه ثم اضغط «شغّلته».', style: TextStyle(fontSize: 14, height: 1.7)),
              Text('يقيس WattWise قفزة الواط على العدّاد الرئيسي، وهذه هي بصمة الجهاز.', style: TextStyle(fontSize: 13, height: 1.7, color: WW.sub)),
            ]),
          ),
          const SizedBox(height: 12),
          if (!measuring && learnedW == 0)
            SizedBox(
              height: 56,
              child: FilledButton(
                onPressed: () => widget.run(() => widget.api.startLearning(type!)),
                style: FilledButton.styleFrom(backgroundColor: WW.ink, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
                child: const Text('شغّلته', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
          if (measuring)
            Container(
              height: 56,
              decoration: BoxDecoration(color: WW.greenBg, borderRadius: BorderRadius.circular(18)),
              alignment: Alignment.center,
              child: const Text('جارٍ القياس…', style: TextStyle(fontSize: 15, color: WW.greenText, fontWeight: FontWeight.w600)),
            ),
          if (learnedW > 0)
            WWBox(
              color: WW.greenBg,
              radius: 20,
              child: Row(children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('تعرّفنا عليه ✓', style: TextStyle(fontSize: 13, color: WW.greenText)),
                    Text('+$learnedW W', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 26, fontWeight: FontWeight.w500)),
                    Text('≈ ${WW.fmt(learnedW / 1000 * (widget.st['bill']['price_jod_per_kwh'] as num), 3)} دينار في الساعة',
                        style: const TextStyle(fontSize: 12, color: WW.greenText)),
                  ]),
                ),
                OutlinedButton(
                  onPressed: () => widget.run(() => widget.api.startLearning(type!)),
                  style: OutlinedButton.styleFrom(foregroundColor: WW.ink, side: const BorderSide(color: Color(0xFFB8DB7A), width: 1.5)),
                  child: const Text('أعد القياس'),
                ),
              ]),
            ),
        ]);
      default:
        if (t != null && t.locked) {
          return const WWBox(
            color: Color(0xFFFBE3DD),
            radius: 20,
            child: Text('جهاز حرج: لا يمكن إطفاؤه.',
                style: TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF7A2A1C))),
          );
        }
        return WWBox(
          radius: 20,
          child: Row(children: [
            const Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('يقترح الوكيل إطفاءه عند وجود هدر', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                SizedBox(height: 4),
                Text('يسألك قبل أي إجراء.', style: TextStyle(fontSize: 12.5, height: 1.6, color: WW.sub)),
              ]),
            ),
            WWToggle(on: allow, onTap: () => setState(() => allow = !allow)),
          ]),
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        const Expanded(child: Text('جهاز جديد', style: TextStyle(fontSize: 12, color: WW.sub))),
        Text('${step + 1} / 4', style: WW.mono.copyWith(fontSize: 12, color: WW.sub)),
      ]),
      const SizedBox(height: 8),
      ClipRRect(
        borderRadius: BorderRadius.circular(2),
        child: LinearProgressIndicator(value: (step + 1) / 4, minHeight: 4, backgroundColor: WW.line, color: WW.ink),
      ),
      const SizedBox(height: 14),
      Text(titles[step], style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
      const SizedBox(height: 14),
      _body(),
      const SizedBox(height: 14),
      Row(children: [
        Expanded(
          flex: 10,
          child: SizedBox(
            height: 52,
            child: OutlinedButton(
              onPressed: () => step == 0 ? _cancel() : setState(() => step--),
              style: OutlinedButton.styleFrom(foregroundColor: WW.ink, side: const BorderSide(color: Color(0xFFD8D5CA), width: 1.5), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
              child: Text(step == 0 ? 'إلغاء' : 'رجوع', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          flex: 15,
          child: SizedBox(
            height: 52,
            child: FilledButton(
              onPressed: canNext ? () => step == 3 ? _finish() : setState(() => step++) : null,
              style: FilledButton.styleFrom(
                backgroundColor: WW.ink,
                disabledBackgroundColor: const Color(0xFFD8D5CA),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              ),
              child: Text(step == 3 ? 'إضافة الجهاز' : 'التالي', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ]),
    ]);
  }
}
