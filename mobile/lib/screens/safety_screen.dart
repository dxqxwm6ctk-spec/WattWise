// "الأمان" tab: what WattWise never touches, the house rules, and the emergency stop.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';

class SafetyScreen extends StatelessWidget {
  const SafetyScreen({super.key, required this.st, required this.api, required this.run, required this.onChangeServer});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  final VoidCallback onChangeServer;

  static const _never = [
    ('الثلاجة', Icons.kitchen_outlined, Color(0xFFFF9C8A)),
    ('إنذار الحريق', Icons.local_fire_department_outlined, Color(0xFFFFB35C)),
    ('الأجهزة الطبية', Icons.medical_services_outlined, Color(0xFF7CC4FF)),
    ('إضاءة الطوارئ', Icons.lightbulb_outline_rounded, Color(0xFFF7C948)),
  ];

  @override
  Widget build(BuildContext context) {
    final c = st['comfort'] as Map<String, dynamic>;
    final stopped = st['agent']['estop'] == true;
    final rules = [
      'لا نشغّل أو نطفئ أي جهاز دون موافقتك.',
      'حرارة الغرف المشغولة تبقى بين ${WW.fmt(c['min_c'] as num?)}° و${WW.fmt(c['max_c'] as num?)}°.',
      'عند أي عطل أو انقطاع تبقى الأجهزة على حالتها الطبيعية.',
      'لا كاميرات. نعرف فقط إن كانت الغرفة مشغولة أو فارغة.',
    ];
    // Live temperature of the occupied rooms, under the comfort rule.
    final temps = (st['rooms'] as List).where((r) => r['occupied'] == true && r['temp_c'] != null).toList();

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (stopped) ...[
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(color: WW.red, borderRadius: BorderRadius.circular(24)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              IconTile(icon: Icons.stop_rounded, bg: Colors.white.withValues(alpha: 0.18), fg: Colors.white, size: 44, iconSize: 24, radius: 14),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('WattWise متوقف', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white)),
                  Text('لن نقترح أو نفعل أي شيء حتى تعيد تشغيله.', style: TextStyle(fontSize: 14, color: Color(0xFFFFE1DC))),
                ]),
              ),
            ]),
            const SizedBox(height: 12),
            SizedBox(
              height: 56,
              child: FilledButton(
                onPressed: () => run(api.reset),
                style: FilledButton.styleFrom(backgroundColor: Colors.white, foregroundColor: WW.ink, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
                child: const Text('أعد تشغيل WattWise', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              ),
            ),
          ]),
        ),
        const SizedBox(height: 14),
      ],
      WWBox(
        dark: true,
        radius: 24,
        padding: 18,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('أجهزة لا نلمسها أبدًا', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 12),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            childAspectRatio: 2.4,
            children: [
              for (final (label, icon, color) in _never)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: WW.dark2, borderRadius: BorderRadius.circular(16)),
                  child: Row(children: [
                    IconTile(icon: icon, bg: WW.dark, fg: color, size: 36, iconSize: 20, radius: 12),
                    const SizedBox(width: 10),
                    Expanded(child: Text(label, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, height: 1.4, color: Colors.white))),
                  ]),
                ),
            ],
          ),
        ]),
      ),
      const SizedBox(height: 14),
      WWBox(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('قواعد البيت', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          for (var i = 0; i < rules.length; i++)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(border: i == 0 ? null : const Border(top: BorderSide(color: WW.line))),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(
                  width: 30,
                  child: Text('0${i + 1}', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 22, fontWeight: FontWeight.w700, color: WW.accentDeep, height: 1.2)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(rules[i], style: const TextStyle(fontSize: 14.5, height: 1.6)),
                    if (i == 1 && temps.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(spacing: 6, runSpacing: 6, children: [
                        for (final r in temps)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                            decoration: BoxDecoration(color: WW.accentBg, borderRadius: BorderRadius.circular(999)),
                            child: Text.rich(TextSpan(children: [
                              TextSpan(text: '${r['name']} '),
                              TextSpan(text: '${WW.fmt(r['temp_c'] as num, 1)}°', style: WW.mono),
                            ]), style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                          ),
                      ]),
                    ],
                  ]),
                ),
              ]),
            ),
        ]),
      ),
      if (!stopped) ...[
        const SizedBox(height: 14),
        Container(
          height: 64,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            boxShadow: [BoxShadow(color: WW.red.withValues(alpha: 0.25), blurRadius: 18, offset: const Offset(0, 6))],
          ),
          child: FilledButton.icon(
            onPressed: () => run(api.emergencyStop),
            style: FilledButton.styleFrom(backgroundColor: WW.red, foregroundColor: Colors.white, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20))),
            icon: const Icon(Icons.stop_rounded, size: 24),
            label: const Text('أوقف WattWise الآن', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          ),
        ),
        const SizedBox(height: 8),
        const Text('يتوقف كل شيء فورًا وتعود الأجهزة إلى وضعها الطبيعي.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12.5, color: WW.sub)),
      ],
      const SizedBox(height: 8),
      Center(
        child: TextButton(
          onPressed: onChangeServer,
          style: TextButton.styleFrom(foregroundColor: WW.sub, minimumSize: const Size(0, 44)),
          child: Text.rich(TextSpan(children: [
            const TextSpan(text: 'عنوان الخادم: '),
            TextSpan(text: api.baseUrl, style: const TextStyle(decoration: TextDecoration.underline)),
          ]), style: const TextStyle(fontSize: 12.5)),
        ),
      ),
    ]);
  }
}
