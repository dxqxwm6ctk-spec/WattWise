// "Add a WiFi smart plug" wizard (same steps as the web page js/plugs.js).
//
// 1. pick the plug: the server scans the local Wi-Fi, or the user types brand + IP
// 2. what is plugged into it: type, room, name
// 3. connection + safety check (high-power warning, the heater should use a contactor)
// After that the agent controls it like the relay, always with the same approval step.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/wizard.dart';
import 'devices_screen.dart' show deviceTypes;

final plugKinds = [...deviceTypes.where((x) => x.k != 'other'), (k: 'fan', label: 'مروحة', locked: false), (k: 'other', label: 'آخر', locked: false)];

class AddPlugWizard extends StatefulWidget {
  const AddPlugWizard({super.key, required this.st, required this.api, required this.run, required this.onClose});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  final VoidCallback onClose;

  @override
  State<AddPlugWizard> createState() => _AddPlugWizardState();
}

class _AddPlugWizardState extends State<AddPlugWizard> {
  int step = 0;
  bool scanning = false, manual = false, checking = false, confirmed = false, allow = true, busy = false;
  List<dynamic> found = [];
  List<dynamic> brands = [];
  Map<String, dynamic>? pick;
  String? brand, type, room;
  int maxA = 10;
  Map<String, dynamic>? check;
  String error = '';
  final hostCtrl = TextEditingController();
  final nameCtrl = TextEditingController();
  final Map<String, TextEditingController> optCtrls = {};

  @override
  void initState() {
    super.initState();
    widget.api.plugBrands().then((r) {
      if (mounted) setState(() => brands = (r['brands'] as List?) ?? []);
    }).catchError((_) {});
    _scan();
  }

  @override
  void dispose() {
    hostCtrl.dispose();
    nameCtrl.dispose();
    for (final c in optCtrls.values) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic>? get brandInfo {
    for (final b in brands) {
      if (b['key'] == brand) return b as Map<String, dynamic>;
    }
    return null;
  }

  TextEditingController _opt(String key) => optCtrls.putIfAbsent(key, () => TextEditingController());

  Map<String, dynamic> get target {
    if (pick != null) {
      return {'brand': pick!['brand'], 'host': pick!['host'], 'options': {...(pick!['options'] as Map? ?? {}), 'max_a': maxA}};
    }
    return {
      'brand': brand,
      'host': hostCtrl.text.trim(),
      'options': {for (final e in optCtrls.entries) if (e.value.text.trim().isNotEmpty) e.key: e.value.text.trim(), 'max_a': maxA},
    };
  }

  bool get canNext {
    if (busy) return false;
    if (step == 0) {
      if (pick != null) return true;
      final b = brandInfo;
      if (b == null || hostCtrl.text.trim().isEmpty) return false;
      return (b['fields'] as List).every((f) => f['optional'] == true || _opt(f['key']).text.trim().isNotEmpty);
    }
    if (step == 1) return type != null && room != null;
    final c = check;
    if (c == null) return false;
    final s = c['safety'] as Map<String, dynamic>;
    return s['level'] != 'block' && (s['needs_confirm'] != true || confirmed);
  }

  Future<void> _scan() async {
    setState(() => scanning = true);
    try {
      final list = await widget.api.scanPlugs();
      if (mounted) setState(() => found = list.where((f) => f['added'] != true).toList());
    } catch (_) {}
    if (mounted) setState(() => scanning = false);
  }

  Future<void> _check() async {
    setState(() {
      checking = true;
      check = null;
      error = '';
      confirmed = false;
    });
    try {
      final c = await widget.api.checkPlug(target, type!);
      if (mounted) setState(() => check = c);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    }
    if (mounted) setState(() => checking = false);
  }

  Future<void> _finish() async {
    final t = plugKinds.firstWhere((x) => x.k == type);
    final roomName = (widget.st['rooms'] as List).firstWhere((r) => r['id'] == room)['name'];
    final name = nameCtrl.text.trim().isEmpty ? '${t.label} $roomName' : nameCtrl.text.trim();
    setState(() => busy = true);
    var ok = false;
    await widget.run(() async {
      await widget.api.addPlug({
        ...target,
        'kind': type,
        'room': room,
        'name': name,
        'allow': allow,
        'confirm_high_power': confirmed,
        'model': pick?['model'],
      });
      ok = true;
    });
    if (!mounted) return;
    setState(() => busy = false);
    if (ok) widget.onClose();
  }

  Widget _spinRow(String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [
          const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.4, color: WW.ink)),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
        ]),
      );

  Widget _label(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Text(t, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
      );

  List<Widget> _step0() {
    final b = brandInfo;
    return [
      ...stepHead('اختر المقبس', 'وصّل المقبس بالكهرباء وتأكد أن هاتفك على شبكة Wi-Fi نفسها. يجب أن يكون المقبس قد أُعدّ أول مرة من تطبيق الشركة.'),
      if (scanning) _spinRow('جارٍ البحث في شبكة Wi-Fi…'),
      if (!scanning && found.isEmpty)
        const WWBox(radius: 16, child: Text('لم نجد مقابس على هذه الشبكة. تأكّد أن المقبس والهاتف على شبكة Wi-Fi نفسها، أو أضفه يدويًا.', style: TextStyle(fontSize: 13.5, height: 1.6, color: WW.sub))),
      if (!scanning)
        for (final f in found) ...[
          const SizedBox(height: 8),
          _PlugCard(f: f, selected: pick != null && pick!['host'] == f['host'], onTap: () => setState(() {
                pick = f as Map<String, dynamic>;
                manual = false;
                final a = (f['options'] as Map?)?['max_a'];
                if (a is num) maxA = a.toInt();
              })),
        ],
      const SizedBox(height: 12),
      Row(children: [
        Expanded(child: WWButton('ابحث مجددًا', scanning ? null : _scan, kind: BtnKind.ghost, height: 46, fontSize: 14, radius: 14)),
        const SizedBox(width: 8),
        Expanded(
            child: WWButton(manual ? 'إخفاء الإدخال اليدوي' : 'أضف يدويًا', () => setState(() {
                  manual = !manual;
                  pick = null;
                }), kind: BtnKind.ghost, height: 46, fontSize: 14, radius: 14)),
      ]),
      if (manual) ...[
        const SizedBox(height: 12),
        WWBox(
          radius: 18,
          padding: 14,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('إضافة يدوية', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: WW.sub)),
            const SizedBox(height: 10),
            _label('نوع المقبس'),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final x in brands.where((x) => x['key'] != 'simulated'))
                GestureDetector(
                  onTap: () => setState(() => brand = x['key'] as String),
                  child: Container(
                    constraints: const BoxConstraints(minHeight: 40),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                    decoration: BoxDecoration(
                      color: brand == x['key'] ? WW.ink : Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: brand == x['key'] ? WW.accent : WW.field, width: brand == x['key'] ? 1.5 : 1),
                    ),
                    child: Text('${x['name']}',
                        textDirection: TextDirection.ltr,
                        style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: brand == x['key'] ? Colors.white : WW.ink)),
                  ),
                ),
            ]),
            if (b != null) ...[
              const SizedBox(height: 10),
              Text('${b['how']}', style: const TextStyle(fontSize: 12.5, height: 1.6, color: WW.sub)),
              const SizedBox(height: 10),
              _label('عنوان IP'),
              TextField(controller: hostCtrl, textDirection: TextDirection.ltr, onChanged: (_) => setState(() {}), decoration: wwField('192.168.1.23')),
              for (final f in b['fields'] as List) ...[
                const SizedBox(height: 10),
                _label('${f['label']}${f['optional'] == true ? ' (اختياري)' : ''}'),
                TextField(
                  controller: _opt(f['key'] as String),
                  textDirection: TextDirection.ltr,
                  obscureText: f['secret'] == true,
                  onChanged: (_) => setState(() {}),
                  decoration: wwField(''),
                ),
              ],
            ],
          ]),
        ),
      ],
      const SizedBox(height: 12),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: WW.line)),
        child: Row(children: [
          const Expanded(child: Text('الحد الأقصى للمقبس (مكتوب عليه)', style: TextStyle(fontSize: 13, color: WW.sub))),
          DropdownButton<int>(
            value: maxA,
            underline: const SizedBox.shrink(),
            style: WW.mono.copyWith(fontFamily: WW.font, fontSize: 15, fontWeight: FontWeight.w700, color: WW.ink),
            items: const [
              DropdownMenuItem(value: 10, child: Text('10 A · 2200 W', textDirection: TextDirection.ltr)),
              DropdownMenuItem(value: 13, child: Text('13 A · 2860 W', textDirection: TextDirection.ltr)),
              DropdownMenuItem(value: 16, child: Text('16 A · 3520 W', textDirection: TextDirection.ltr)),
            ],
            onChanged: (v) => setState(() => maxA = v ?? 10),
          ),
        ]),
      ),
    ];
  }

  List<Widget> _step1() => [
        ...stepHead('ما الموصول بالمقبس؟'),
        KindGrid(kinds: plugKinds, selected: type, onPick: (k) => setState(() => type = k)),
        const SizedBox(height: 14),
        const Text('الغرفة', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        RoomPills(rooms: widget.st['rooms'] as List, selected: room, onPick: (r) => setState(() => room = r)),
        const SizedBox(height: 14),
        const Text('الاسم', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        TextField(controller: nameCtrl, decoration: wwField('مثلًا: سخّان الحمّام')),
      ];

  List<Widget> _step2() {
    final head = stepHead('الاتصال وفحص الأمان');
    if (checking) {
      return [...head, WWBox(radius: 18, padding: 14, child: _spinRow('جارٍ الاتصال بالمقبس…'))];
    }
    final c = check;
    if (c == null) {
      return [
        ...head,
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: WW.redBg, borderRadius: BorderRadius.circular(18), border: Border.all(color: WW.redBorder)),
          child: Text(error.isEmpty ? 'تعذّر الوصول إلى المقبس.' : error, style: const TextStyle(fontSize: 14, height: 1.6, color: WW.red)),
        ),
        const SizedBox(height: 10),
        WWButton('حاول مجددًا', _check, kind: BtnKind.outline, height: 48),
      ];
    }
    final s = c['safety'] as Map<String, dynamic>;
    final level = s['level'];
    final locked = plugKinds.firstWhere((x) => x.k == type).locked;
    final block = level == 'block';
    final fg = block ? WW.red : WW.pendingText;
    return [
      ...head,
      WWBox(
        radius: 18,
        padding: 14,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Row(children: [
            Icon(Icons.check_rounded, size: 18, color: WW.sub),
            SizedBox(width: 10),
            Text('جارٍ الاتصال بالمقبس…', style: TextStyle(fontSize: 13.5, color: WW.sub, decoration: TextDecoration.lineThrough)),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Container(
              width: 28,
              height: 28,
              decoration: const BoxDecoration(color: WW.greenBg, shape: BoxShape.circle),
              child: const Icon(Icons.check_rounded, size: 16, color: WW.green),
            ),
            const SizedBox(width: 10),
            Text('متصل ✓ · ${c['on'] == true ? 'يعمل' : 'مطفأ'}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: WW.green)),
          ]),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(color: WW.paper, borderRadius: BorderRadius.circular(12)),
            child: c['meters'] == true
                ? Row(children: [
                    Expanded(
                        child: Text(c['measured'] == true ? 'البصمة المقاسة أثناء التشغيل' : 'سنقيس بصمته عند تشغيله (تقدير حالي)',
                            style: const TextStyle(fontSize: 13, color: WW.sub))),
                    Text(c['measured'] == true ? '${WW.fmt(c['power_w'] as num?)} W' : '≈ ${c['est_w']} W',
                        textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 16, fontWeight: FontWeight.w700)),
                  ])
                : Text('هذا المقبس لا يقيس الواط. نتحكّم به ونقيس بصمته على العدّاد الرئيسي (≈ ${c['est_w']} W حاليًا).',
                    style: const TextStyle(fontSize: 13, height: 1.6, color: WW.sub)),
          ),
          const SizedBox(height: 8),
          Row(children: [
            const Expanded(child: Text('حد المقبس', style: TextStyle(fontSize: 13, color: WW.sub))),
            Text('${WW.fmt(c['max_w'] as num?)} W', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 13, fontWeight: FontWeight.w700)),
          ]),
        ]),
      ),
      if (level != 'ok') ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: block ? WW.redBg : WW.warnBg,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: block ? WW.redBorder : WW.warnBorder),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.warning_amber_rounded, size: 22, color: block ? WW.red : WW.warnFg),
              const SizedBox(width: 10),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(block ? 'ممنوع على هذا المقبس' : 'تحذير أمان', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: fg)),
                  const SizedBox(height: 3),
                  Text('${s['message']}', style: TextStyle(fontSize: 13.5, height: 1.6, color: fg)),
                ]),
              ),
            ]),
            if (s['needs_confirm'] == true) ...[
              const SizedBox(height: 6),
              InkWell(
                onTap: () => setState(() => confirmed = !confirmed),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: 44),
                  child: Row(children: [
                    Checkbox(
                      value: confirmed,
                      activeColor: WW.accentDeep,
                      onChanged: (v) => setState(() => confirmed = v ?? false),
                    ),
                    const Expanded(child: Text('أفهم التحذير وأريد المتابعة', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                  ]),
                ),
              ),
            ],
          ]),
        ),
      ],
      const SizedBox(height: 12),
      WWBox(
        radius: 18,
        padding: 14,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('ماذا يُسمح لـ WattWise أن يفعل؟', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (locked)
            const Text('جهاز حرج: لا يمكن إطفاؤه.', style: TextStyle(fontSize: 14, height: 1.6, color: WW.red))
          else
            Row(children: [
              const Expanded(
                child: Text('يمكن للوكيل اقتراح إطفائه عند وجود هدر، ويسألك دائمًا أولًا.', style: TextStyle(fontSize: 14, height: 1.6, color: WW.body)),
              ),
              WWToggle(on: allow, onTap: () => setState(() => allow = !allow)),
            ]),
          const Divider(height: 20, color: WW.line),
          const Row(children: [
            Icon(Icons.lock_outline_rounded, size: 14, color: WW.sub),
            SizedBox(width: 8),
            Expanded(child: Text('الأجهزة الحرجة مثل الثلاجة والأجهزة الطبية: لا يمكن إطفاؤها.', style: TextStyle(fontSize: 12.5, color: WW.sub))),
          ]),
        ]),
      ),
    ];
  }

  @override
  Widget build(BuildContext context) => WizardScaffold(
        title: 'مقبس ذكي (Wi-Fi)',
        step: step,
        steps: 3,
        onClose: widget.onClose,
        onBack: () => setState(() => step--),
        nextLabel: step == 2 ? 'أضف الجهاز' : 'التالي',
        onNext: canNext
            ? () {
                if (step == 2) {
                  _finish();
                  return;
                }
                setState(() => step++);
                if (step == 2) _check();
              }
            : null,
        children: (step == 0 ? _step0 : step == 1 ? _step1 : _step2)(),
      );
}

class _PlugCard extends StatelessWidget {
  const _PlugCard({required this.f, required this.selected, required this.onTap});
  final dynamic f;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final meters = f['meters'];
    final needs = (f['needs'] as List?) ?? [];
    final cap = meters == false ? 'تشغيل وإطفاء فقط' : meters == true ? 'يقيس الواط ✓' : 'نعرف إن كان يقيس بعد الفحص';
    return RadioRow(
      on: selected,
      onTap: onTap,
      title: '${f['model']}',
      titleLtr: true,
      body: Text.rich(
        TextSpan(children: [
          TextSpan(text: '${f['brand_name']} · ${f['host']}'),
          const TextSpan(text: ' · '),
          TextSpan(text: cap, style: TextStyle(color: meters == true ? WW.ink : WW.sub, fontWeight: FontWeight.w600)),
          if (needs.isNotEmpty) const TextSpan(text: ' · يحتاج Local Key'),
        ]),
        style: const TextStyle(fontSize: 12.5, color: WW.sub),
      ),
    );
  }
}

/// One line under a device that sits on a smart plug: brand, live watts, remove.
class PlugLine extends StatelessWidget {
  const PlugLine({super.key, required this.d, required this.onRemove, this.dark = false});
  final dynamic d;
  final VoidCallback onRemove;
  final bool dark; // the device card is dark (device running)

  @override
  Widget build(BuildContext context) {
    final p = d['plug'] as Map<String, dynamic>?;
    if (p == null) return const SizedBox.shrink();
    final online = p['online'] == true;
    final label = p['simulated'] == true && p['model'] != null ? p['model'] : p['brand_name'];
    final live = !online
        ? 'المقبس غير متصل'
        : p['meters'] == true && p['power_w'] != null
            ? '${WW.fmt(p['power_w'] as num)} W من المقبس'
            : 'متصل';
    final sub = dark ? WW.darkSub : WW.sub;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.only(top: 4),
      decoration: BoxDecoration(border: Border(top: BorderSide(color: dark ? WW.darkLine : WW.line))),
      child: Row(children: [
        Icon(Icons.power_outlined, size: 14, color: online ? sub : (dark ? WW.redSoft : WW.red)),
        const SizedBox(width: 6),
        Expanded(child: Text('$label · $live', style: TextStyle(fontSize: 12.5, color: online ? sub : (dark ? WW.redSoft : WW.red)))),
        TextButton(
          onPressed: onRemove,
          style: TextButton.styleFrom(minimumSize: const Size(0, 36), foregroundColor: dark ? WW.redSoft : WW.red),
          child: const Text('إزالة', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        ),
      ]),
    );
  }
}
