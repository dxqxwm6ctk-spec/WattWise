// "الأجهزة" tab: manual control of every device, AC set point, and the add-device wizard.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import 'add_plug_wizard.dart';

const deviceTypes = [
  (k: 'ac', label: 'مكيّف', locked: false),
  (k: 'light', label: 'إنارة', locked: false),
  (k: 'heater', label: 'دفاية / سخّان', locked: false),
  (k: 'tv', label: 'تلفزيون / شاشة', locked: false),
  (k: 'washer', label: 'غسالة / جلاية', locked: false),
  (k: 'pc', label: 'كمبيوتر', locked: false),
  (k: 'router', label: 'راوتر / إنترنت', locked: false),
  (k: 'fridge', label: 'ثلاجة / فريزر', locked: true),
  (k: 'medical', label: 'جهاز طبي', locked: true),
  (k: 'other', label: 'إشي ثاني', locked: false),
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
    final onCount = devices.where((d) => d['is_on'] == true).length;
    final comfort = st['comfort'] as Map<String, dynamic>;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SizedBox(
        height: 52,
        child: FilledButton(
          onPressed: () => setState(() => plugOpen = true),
          style: FilledButton.styleFrom(backgroundColor: WW.ink, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
          child: const Text('🔌 + ضيفي مقبس ذكي (Wi-Fi)', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
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
          child: const Text('+ ضيفي جهاز بالعدّاد الرئيسي', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        ),
      ),
      if (st['agent']['safe_mode'] == true) ...[
        const SizedBox(height: 8),
        const WWBox(
          color: WW.pendingBg,
          border: WW.pendingBorder,
          child: Text('الراوتر مطفي، بالحقيقة التطبيق رح ينقطع هون. WattWise بوضع آمن وما رح ينفّذ إشي.',
              style: TextStyle(fontSize: 13.5, height: 1.6, color: Color(0xFF6B4A00))),
        ),
      ],
      const SizedBox(height: 8),
      Text('$onCount شغّال من ${devices.length}', style: const TextStyle(fontSize: 13, color: WW.sub)),
      for (final d in devices) ...[
        const SizedBox(height: 8),
        _DeviceTile(d: d, comfort: comfort, api: widget.api, run: widget.run),
      ],
    ]);
  }
}

class _DeviceTile extends StatelessWidget {
  const _DeviceTile({required this.d, required this.comfort, required this.api, required this.run});
  final dynamic d;
  final Map<String, dynamic> comfort;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;

  Future<void> _toggle(BuildContext context) async {
    final on = d['is_on'] == true;
    if (d['sensitive'] == true && on) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: Text('نطفي ${d['name']}؟'),
          content: const Text('رح ينقطع التطبيق ولا رح توصلك طلبات موافقة لحد ما ترجعي تشغّليه من الجهاز نفسه.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('لا')),
            FilledButton(onPressed: () => Navigator.pop(c, true), style: FilledButton.styleFrom(backgroundColor: WW.ink), child: const Text('إيه، طفّيه')),
          ],
        ),
      );
      if (ok == true) await run(() => api.toggle(d['id'], false, confirmed: true));
      return;
    }
    await run(() => api.toggle(d['id'], !on));
  }

  Future<void> _remove(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('نشيل ${d['name']}؟'),
        content: const Text('رح ينشال الجهاز ومقبسه من WattWise. المقبس نفسه بيضل متل ما هو.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('لا')),
          FilledButton(onPressed: () => Navigator.pop(c, true), style: FilledButton.styleFrom(backgroundColor: WW.ink), child: const Text('إيه، شيله')),
        ],
      ),
    );
    if (ok == true) await run(() => api.removePlug(d['id']));
  }

  @override
  Widget build(BuildContext context) {
    final on = d['is_on'] == true;
    final locked = d['tier'] == 'T2';
    final state = locked ? 'محمي · دايمًا شغّال' : on ? 'شغّال' : 'مطفي';
    return WWBox(
      padding: 14,
      child: Column(children: [
        Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${d['name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text('${d['room_name']} · $state', style: const TextStyle(fontSize: 12, color: WW.sub)),
            ]),
          ),
          WWToggle(on: on, locked: locked, onTap: () => _toggle(context)),
        ]),
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

  static const titles = ['شو نوع الجهاز؟', 'وين حطّيتيه؟', 'خلّينا نتعرّف عليه', 'شو مسموح لـWattWise؟'];

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
          const Text('سمّيه (اختياري)', style: TextStyle(fontSize: 13, color: WW.sub)),
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
              Text('١. تأكّدي إنو الجهاز موصول بمقبس ذكي (بيركّبه كهربائي).', style: TextStyle(fontSize: 14, height: 1.7)),
              Text('٢. لما تكوني جاهزة، شغّلي الجهاز من زرّه واضغطي «شغّلته».', style: TextStyle(fontSize: 14, height: 1.7)),
              Text('WattWise بيقيس قفزة الواط على العدّاد الرئيسي، هاي بصمة الجهاز.', style: TextStyle(fontSize: 13, height: 1.7, color: WW.sub)),
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
              child: const Text('عم نقيس…', style: TextStyle(fontSize: 15, color: WW.greenText, fontWeight: FontWeight.w600)),
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
                    Text('≈ ${WW.fmt(learnedW / 1000 * (widget.st['bill']['price_jod_per_kwh'] as num), 3)} دينار بالساعة',
                        style: const TextStyle(fontSize: 12, color: WW.greenText)),
                  ]),
                ),
                OutlinedButton(
                  onPressed: () => widget.run(() => widget.api.startLearning(type!)),
                  style: OutlinedButton.styleFrom(foregroundColor: WW.ink, side: const BorderSide(color: Color(0xFFB8DB7A), width: 1.5)),
                  child: const Text('قيس مرة ثانية'),
                ),
              ]),
            ),
        ]);
      default:
        if (t != null && t.locked) {
          return const WWBox(
            color: Color(0xFFFBE3DD),
            radius: 20,
            child: Text('هاد جهاز حرج (T2). رح نراقب استهلاكه بس، وما حدا (ولا الوكيل ولا التطبيق) بيقدر يطفيه. محمي بالكود.',
                style: TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF7A2A1C))),
          );
        }
        return WWBox(
          radius: 20,
          child: Row(children: [
            const Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('الوكيل يقترح إطفاءه لما يلاقي هدر', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                SizedBox(height: 4),
                Text('دايمًا بيسألك قبل. إذا سكّرتيها، بيضل التحكم يدوي بس.', style: TextStyle(fontSize: 12.5, height: 1.6, color: WW.sub)),
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
              child: Text(step == 3 ? 'ضيف الجهاز' : 'التالي', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ]),
    ]);
  }
}
