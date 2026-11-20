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

  @override
  Widget build(BuildContext context) {
    final c = st['comfort'] as Map<String, dynamic>;
    final stopped = st['agent']['estop'] == true;
    final rules = [
      'لا يُطفئ الوكيل أي جهاز دون موافقتك، ويمكنك التحكم بأي جهاز يدويًا.',
      'تبقى حرارة أي غرفة مشغولة ضمن ${WW.fmt(c['min_c'])}–${WW.fmt(c['max_c'])}°.',
      'إذا انقطع الإنترنت أو الراوتر أو حدث عطل، يبقى كل شيء على وضعه الطبيعي دون أي إجراء تلقائي.',
      'نعرف فقط إن كانت الغرفة مشغولة أم فارغة، بلا كاميرات.',
    ];
    const sub = TextStyle(fontSize: 13, color: WW.sub);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('أجهزة لا نلمسها أبدًا', style: sub),
      const SizedBox(height: 10),
      const WWBox(
        child: Text('الثلاجة وإنذار الحريق والأجهزة الطبية وإنارة الطوارئ: ممنوعة برمجيًا، حتى لو وافقت.', style: TextStyle(fontSize: 14, height: 1.7)),
      ),
      const SizedBox(height: 14),
      const Text('قواعد البيت', style: sub),
      for (var i = 0; i < rules.length; i++) ...[
        const SizedBox(height: 10),
        WWBox(
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('0${i + 1}', style: WW.mono.copyWith(fontSize: 11, color: const Color(0xFF5E7A1C))),
            const SizedBox(width: 12),
            Expanded(child: Text(rules[i], style: const TextStyle(fontSize: 14, height: 1.6))),
          ]),
        ),
      ],
      const SizedBox(height: 14),
      SizedBox(
        height: 58,
        child: FilledButton(
          onPressed: () => run(stopped ? api.reset : api.emergencyStop),
          style: FilledButton.styleFrom(
            backgroundColor: stopped ? WW.ink : WW.red,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          ),
          child: Text(stopped ? 'أعد تشغيل WattWise' : 'أوقف WattWise الآن', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ),
      ),
      const SizedBox(height: 10),
      TextButton(onPressed: onChangeServer, child: Text('عنوان الخادم: ${api.baseUrl}', style: sub)),
    ]);
  }
}
