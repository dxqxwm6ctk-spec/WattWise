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
      'الوكيل ما بيطفي ولا جهاز بدون موافقتك. إنتِ بتقدري تتحكمي بأي جهاز يدويًا.',
      'ما رح نخلّي حرارة أي غرفة مشغولة تطلع برّا ${WW.fmt(c['min_c'])}–${WW.fmt(c['max_c'])}°.',
      'إذا انقطع النت أو الراوتر أو صار عطل، كل إشي بيضل طبيعي وما في إجراء تلقائي.',
      'بنعرف إذا الغرفة فيها حدا أو لا بس، بلا كاميرات.',
    ];
    const sub = TextStyle(fontSize: 13, color: WW.sub);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('إشي ما بنلمسه أبدًا', style: sub),
      const SizedBox(height: 10),
      const WWBox(
        child: Text('الثلاجة، إنذار الحريق، والأجهزة الطبية وإنارة الطوارئ: ممنوعة بالكود، حتى لو وافقتي.', style: TextStyle(fontSize: 14, height: 1.7)),
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
          child: Text(stopped ? 'رجّع شغّل WattWise' : 'وقّف WattWise هلأ', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ),
      ),
      const SizedBox(height: 10),
      TextButton(onPressed: onChangeServer, child: Text('عنوان السيرفر: ${api.baseUrl}', style: sub)),
    ]);
  }
}
