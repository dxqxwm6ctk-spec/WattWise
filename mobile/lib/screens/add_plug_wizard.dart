// "Add a WiFi smart plug" wizard (same steps as the web page js/plugs.js).
//
// 1. pick the plug: the server scans the local Wi-Fi, or the user types brand + IP
// 2. what is plugged into it: type, room, name
// 3. connection + safety check (high-power warning, the heater should use a contactor)
// After that the agent controls it like the relay, always with the same approval step.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import 'devices_screen.dart' show deviceTypes;

final plugKinds = [(k: 'fan', label: 'مروحة', locked: false), ...deviceTypes];

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

  static const titles = ['اختر المقبس الذكي', 'ما الجهاز الموصول به؟', 'فحص الاتصال والأمان'];

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
    final name = nameCtrl.text.trim().isEmpty ? '${t.label.split(' / ').first} $roomName' : nameCtrl.text.trim();
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

  Widget _chip(String label, bool selected, VoidCallback onTap) => Material(
        color: selected ? WW.ink : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14), side: BorderSide(color: selected ? WW.ink : WW.line, width: 1.5)),
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: onTap,
          child: Container(
            constraints: const BoxConstraints(minHeight: 46),
            padding: const EdgeInsets.all(8),
            alignment: Alignment.center,
            child: Text(label, textAlign: TextAlign.center, style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: selected ? WW.paper : WW.ink)),
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

  InputDecoration _field(String hint) => InputDecoration(
        hintText: hint,
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: WW.line, width: 1.5)),
      );

  Widget _busyBox(String text) => Container(
        height: 56,
        decoration: BoxDecoration(color: WW.greenBg, borderRadius: BorderRadius.circular(18)),
        alignment: Alignment.center,
        child: Text(text, style: const TextStyle(fontSize: 15, color: WW.greenText, fontWeight: FontWeight.w600)),
      );

  Widget _step0() {
    final b = brandInfo;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('صِل المقبس الذكي بالكهرباء وصِل الجهاز به. يجب أن يكون المقبس قد أُعدّ أول مرة من تطبيق الشركة على شبكة الـ Wi-Fi نفسها.',
          style: TextStyle(fontSize: 13, height: 1.6, color: WW.sub)),
      const SizedBox(height: 10),
      if (scanning) _busyBox('جارٍ البحث في شبكة الـ Wi-Fi…'),
      if (!scanning && found.isEmpty)
        const WWBox(child: Text('لم نجد مقابس على هذه الشبكة. تأكّد أن المقبس والهاتف على شبكة الـ Wi-Fi نفسها، أو أضفه يدويًا.', style: TextStyle(fontSize: 13.5, color: WW.sub))),
      if (!scanning)
        for (final f in found) ...[
          _PlugCard(f: f, selected: pick != null && pick!['host'] == f['host'], onTap: () => setState(() {
                pick = f as Map<String, dynamic>;
                manual = false;
                final a = (f['options'] as Map?)?['max_a'];
                if (a is num) maxA = a.toInt();
              })),
          const SizedBox(height: 8),
        ],
      const SizedBox(height: 8),
      Row(children: [
        Expanded(child: OutlinedButton(onPressed: scanning ? null : _scan, child: const Text('ابحث مجددًا'))),
        const SizedBox(width: 8),
        Expanded(
            child: OutlinedButton(
                onPressed: () => setState(() {
                      manual = !manual;
                      pick = null;
                    }),
                child: Text(manual ? 'إخفاء الإدخال اليدوي' : 'إضافة يدويًا'))),
      ]),
      if (manual) ...[
        const SizedBox(height: 10),
        WWBox(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('ما ماركة المقبس؟', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            _grid([
              for (final x in brands.where((x) => x['key'] != 'simulated'))
                _chip('${x['name']}', brand == x['key'], () => setState(() => brand = x['key'] as String)),
            ]),
            if (b != null) ...[
              const SizedBox(height: 8),
              Text('${b['how']}', style: const TextStyle(fontSize: 12.5, height: 1.6, color: WW.sub)),
              const SizedBox(height: 8),
              TextField(controller: hostCtrl, textDirection: TextDirection.ltr, onChanged: (_) => setState(() {}), decoration: _field('IP مثل 192.168.1.50')),
              for (final f in b['fields'] as List) ...[
                const SizedBox(height: 8),
                TextField(
                  controller: _opt(f['key'] as String),
                  textDirection: TextDirection.ltr,
                  obscureText: f['secret'] == true,
                  onChanged: (_) => setState(() {}),
                  decoration: _field('${f['label']}${f['optional'] == true ? ' (اختياري)' : ''}'),
                ),
              ],
            ],
          ]),
        ),
      ],
      const SizedBox(height: 10),
      Row(children: [
        const Expanded(child: Text('حد المقبس (مكتوب عليه)', style: TextStyle(fontSize: 13, color: WW.sub))),
        DropdownButton<int>(
          value: maxA,
          items: const [DropdownMenuItem(value: 10, child: Text('10A')), DropdownMenuItem(value: 13, child: Text('13A')), DropdownMenuItem(value: 16, child: Text('16A'))],
          onChanged: (v) => setState(() => maxA = v ?? 10),
        ),
      ]),
    ]);
  }

  Widget _step1() => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        _grid([for (final x in plugKinds) _chip(x.label, type == x.k, () => setState(() => type = x.k))]),
        const SizedBox(height: 12),
        const Text('في أي غرفة؟', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        _grid([for (final r in widget.st['rooms'] as List) _chip('${r['name']}', room == r['id'], () => setState(() => room = r['id'] as String))]),
        const SizedBox(height: 12),
        TextField(controller: nameCtrl, decoration: _field('الاسم، مثلًا: سخّان الحمّام')),
      ]);

  Widget _step2() {
    if (checking) return _busyBox('جارٍ الاتصال بالمقبس…');
    final c = check;
    if (c == null) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        WWBox(color: const Color(0xFFFBE3DD), child: Text(error.isEmpty ? 'تعذّر الوصول إلى المقبس.' : error, style: const TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF7A2A1C)))),
        const SizedBox(height: 8),
        OutlinedButton(onPressed: _check, child: const Text('حاول مجددًا')),
      ]);
    }
    final s = c['safety'] as Map<String, dynamic>;
    final level = s['level'];
    final locked = plugKinds.firstWhere((x) => x.k == type).locked;
    final textColor = level == 'block' ? const Color(0xFF7A2A1C) : const Color(0xFF6B4A00);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      WWBox(
        color: WW.greenBg,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('تم الاتصال بالمقبس ✓ ${c['on'] == true ? 'يعمل' : 'مطفأ'}', style: const TextStyle(fontSize: 13, color: WW.greenText)),
          if (c['meters'] == true) ...[
            Text('${WW.fmt(c['power_w'] as num?)} W', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 24)),
            Text(c['measured'] == true ? 'هذه بصمة الجهاز من المقبس نفسه.' : 'سنقيس بصمته عند تشغيله. التقدير الحالي ≈ ${c['est_w']} واط.',
                style: const TextStyle(fontSize: 12, color: WW.greenText)),
          ] else
            Text('هذا المقبس لا يقيس الواط. نتحكّم به ونقيس بصمته على العدّاد الرئيسي (≈ ${c['est_w']} واط حاليًا).',
                style: const TextStyle(fontSize: 12.5, height: 1.6, color: WW.greenText)),
          Text('حد المقبس: ${WW.fmt(c['max_w'] as num?)} واط', style: const TextStyle(fontSize: 12, color: WW.greenText)),
        ]),
      ),
      if (level != 'ok') ...[
        const SizedBox(height: 10),
        WWBox(
          color: level == 'block' ? const Color(0xFFFBE3DD) : WW.pendingBg,
          border: level == 'block' ? WW.red : WW.pendingBorder,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(level == 'block' ? 'ممنوع على هذا المقبس' : '⚠️ تحذير أمان', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: textColor)),
            const SizedBox(height: 6),
            Text('${s['message']}', style: TextStyle(fontSize: 13.5, height: 1.7, color: textColor)),
            if (s['needs_confirm'] == true)
              CheckboxListTile(
                value: confirmed,
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: (v) => setState(() => confirmed = v ?? false),
                title: Text('فهمت التحذير وأريد المتابعة', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: textColor)),
              ),
          ]),
        ),
      ],
      const SizedBox(height: 10),
      if (locked)
        const WWBox(
          color: Color(0xFFFBE3DD),
          child: Text('جهاز حرج (T2): سنراقب استهلاكه من المقبس فقط، ولا يمكن لأحد إطفاؤه. محمي برمجيًا.',
              style: TextStyle(fontSize: 13.5, height: 1.7, color: Color(0xFF7A2A1C))),
        )
      else
        WWBox(
          child: Row(children: [
            const Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('يقترح الوكيل إطفاءه عند وجود هدر', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                SizedBox(height: 4),
                Text('يسألك دائمًا قبل أي إجراء، ولا يفعل شيئًا إن لم تردّ.', style: TextStyle(fontSize: 12.5, height: 1.6, color: WW.sub)),
              ]),
            ),
            WWToggle(on: allow, onTap: () => setState(() => allow = !allow)),
          ]),
        ),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        const Expanded(child: Text('مقبس ذكي (Wi-Fi)', style: TextStyle(fontSize: 12, color: WW.sub))),
        Text('${step + 1} / 3', style: WW.mono.copyWith(fontSize: 12, color: WW.sub)),
      ]),
      const SizedBox(height: 8),
      ClipRRect(
        borderRadius: BorderRadius.circular(2),
        child: LinearProgressIndicator(value: (step + 1) / 3, minHeight: 4, backgroundColor: WW.line, color: WW.ink),
      ),
      const SizedBox(height: 14),
      Text(titles[step], style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
      const SizedBox(height: 14),
      [_step0, _step1, _step2][step](),
      const SizedBox(height: 14),
      Row(children: [
        Expanded(
          flex: 10,
          child: SizedBox(
            height: 52,
            child: OutlinedButton(
              onPressed: () => step == 0 ? widget.onClose() : setState(() => step--),
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
              onPressed: canNext
                  ? () {
                      if (step == 2) {
                        _finish();
                        return;
                      }
                      setState(() => step++);
                      if (step == 2) _check();
                    }
                  : null,
              style: FilledButton.styleFrom(
                backgroundColor: WW.ink,
                disabledBackgroundColor: const Color(0xFFD8D5CA),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              ),
              child: Text(step == 2 ? 'إضافة الجهاز' : 'التالي', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ]),
    ]);
  }
}

class _PlugCard extends StatelessWidget {
  const _PlugCard({required this.f, required this.selected, required this.onTap});
  final dynamic f;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fg = selected ? WW.paper : WW.ink;
    final meters = f['meters'];
    final needs = (f['needs'] as List?) ?? [];
    return Material(
      color: selected ? WW.ink : Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18), side: BorderSide(color: selected ? WW.ink : WW.line, width: 1.5)),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${f['model']}', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: fg)),
            const SizedBox(height: 2),
            Text('${f['brand_name']} · ${f['host']}', style: TextStyle(fontSize: 12, color: fg.withValues(alpha: 0.75))),
            Text(
              '${meters == false ? 'تشغيل وإطفاء فقط (لا يقيس الواط)' : meters == true ? 'يقيس الواط ✓' : 'نعرف إن كان يقيس بعد الفحص'}${needs.isNotEmpty ? ' · يحتاج Local Key' : ''}',
              style: TextStyle(fontSize: 12, color: fg.withValues(alpha: 0.75)),
            ),
          ]),
        ),
      ),
    );
  }
}

/// One line under a device that sits on a smart plug: brand, live watts, remove.
class PlugLine extends StatelessWidget {
  const PlugLine({super.key, required this.d, required this.onRemove});
  final dynamic d;
  final VoidCallback onRemove;

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
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(children: [
        Expanded(child: Text('🔌 $label · $live', style: TextStyle(fontSize: 12, color: online ? WW.greenText : WW.red))),
        TextButton(onPressed: onRemove, child: const Text('إزالة', style: TextStyle(fontSize: 12, color: WW.sub))),
      ]),
    );
  }
}
