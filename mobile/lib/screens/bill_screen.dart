// "الفاتورة" tab: tariff type, tiers, where the money goes, measured savings, tips.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/assistant_widgets.dart';
import '../widgets/bill_photo_card.dart';

const tips = [
  'السخّان: شغّله قبل الاستحمام بساعة بدل تركه يعمل طوال اليوم.',
  'أغلق الشبابيك أثناء تشغيل المكيّف، وسننبّهك تلقائيًا إن لاحظنا غير ذلك.',
  'ضبط المكيّف على ٢٤° بدل ٢٢° مريح ويقلّل الاستهلاك.',
];

class BillScreen extends StatelessWidget {
  const BillScreen({super.key, required this.st, required this.api, required this.run});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;

  @override
  Widget build(BuildContext context) {
    final b = st['bill'] as Map<String, dynamic>;
    final s = st['savings'] as Map<String, dynamic>;
    final breakdown = st['breakdown'] as List<dynamic>;
    final f = st['forecast'] as Map<String, dynamic>?;
    const sub = TextStyle(fontSize: 13, color: WW.sub);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      GoalCard(st: st, api: api, run: run),
      const SizedBox(height: 12),
      WhyCard(api: api),
      const SizedBox(height: 12),
      BillPhotoCard(api: api),
      const SizedBox(height: 12),
      ReportCard(api: api),
      const SizedBox(height: 12),
      WWBox(
        radius: 22,
        padding: 18,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('نوع اشتراكك (مذكور في فاتورتك)', style: sub),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(color: WW.paper, borderRadius: BorderRadius.circular(16)),
            child: Row(children: [
              for (final o in b['types'] as List)
                Expanded(
                  child: GestureDetector(
                    onTap: () => run(() => api.setTariff(o['key'])),
                    child: Container(
                      height: 44,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: b['type'] == o['key'] ? Colors.white : Colors.transparent,
                        borderRadius: BorderRadius.circular(12),
                        boxShadow: b['type'] == o['key'] ? const [BoxShadow(color: Color(0x1F000000), blurRadius: 4, offset: Offset(0, 1))] : null,
                      ),
                      child: Text('${o['label']}',
                          style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700, color: b['type'] == o['key'] ? WW.ink : WW.sub)),
                    ),
                  ),
                ),
            ]),
          ),
          const SizedBox(height: 12),
          Text('${b['who']}', style: const TextStyle(fontSize: 12.5, height: 1.6, color: WW.sub)),
          const SizedBox(height: 12),
          for (final t in b['segments'] as List) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(color: t['active'] == true ? WW.ink : WW.paper, borderRadius: BorderRadius.circular(12)),
              child: Row(children: [
                Expanded(
                  child: Text(
                    t['to_kwh'] == null ? 'أكثر من ${(t['from_kwh'] as num).toInt()} ك.و.س' : '${(t['from_kwh'] as num).toInt() + 1}–${(t['to_kwh'] as num).toInt()} ك.و.س',
                    style: TextStyle(fontSize: 13, color: t['active'] == true ? WW.paper : WW.ink),
                  ),
                ),
                Text('${t['fils']} فلس', style: WW.mono.copyWith(fontSize: 13, fontWeight: FontWeight.w600, color: t['active'] == true ? WW.paper : WW.ink)),
              ]),
            ),
            const SizedBox(height: 6),
          ],
          const SizedBox(height: 6),
          Text('${b['message']}', style: const TextStyle(fontSize: 13, height: 1.6)),
        ]),
      ),
      const SizedBox(height: 12),
      WWBox(
        radius: 22,
        padding: 18,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('توزيع التكلفة (حسب بصمة كل جهاز)', style: sub),
          const SizedBox(height: 14),
          if (breakdown.isEmpty) const Text('لا توجد بيانات كافية بعد.', style: sub),
          for (final x in breakdown) ...[
            Row(children: [
              Expanded(child: Text('${x['name']}', style: const TextStyle(fontSize: 14))),
              Text('${WW.fmt(x['jod'], 2)} JD', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 14)),
            ]),
            const SizedBox(height: 6),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(value: (x['pct'] as num) / 100, minHeight: 6, backgroundColor: const Color(0xFFECE9DF), color: WW.ink),
            ),
            const SizedBox(height: 14),
          ],
        ]),
      ),
      const SizedBox(height: 12),
      WWBox(
        color: WW.greenBg,
        radius: 22,
        padding: 18,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('التوفير (مُقاس فعليًا)', style: TextStyle(fontSize: 13, color: WW.greenText)),
          const SizedBox(height: 6),
          Text('${WW.fmt(s['jod'], 3)} JD', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 30, fontWeight: FontWeight.w500)),
          const SizedBox(height: 6),
          Text('${WW.fmt(s['kwh'], 2)} ك.و.س · ${s['co2_kg'] == null ? '—' : WW.fmt(s['co2_kg'], 2)} كغ CO₂ أقل',
              style: const TextStyle(fontSize: 12.5, color: WW.greenText)),
        ]),
      ),
      if (f != null) ...[
        const SizedBox(height: 12),
        WWBox(
          radius: 22,
          padding: 18,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('المتوقّع للساعات الـ${(f['steps'] as List).length} القادمة', style: sub),
            const SizedBox(height: 6),
            Text('${WW.fmt(f['jod'], 2)} JD · ${WW.fmt(f['kwh'], 1)} kWh',
                textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 22, fontWeight: FontWeight.w500)),
            const SizedBox(height: 6),
            Text(
                (f['accuracy']['hours'] as num) > 0
                    ? 'خطأ التوقّع ≈ ${WW.fmt(f['accuracy']['mean_err_pct'], 0)}% (مقاس بالعدّاد)'
                    : 'جارٍ قياس دقة التوقّع',
                style: const TextStyle(fontSize: 12.5, color: WW.sub)),
          ]),
        ),
      ],
      const SizedBox(height: 16),
      const Text('نصائح (لا ننفّذها تلقائيًا)', style: sub),
      for (final t in tips) ...[
        const SizedBox(height: 8),
        WWBox(child: Text(t, style: const TextStyle(fontSize: 14, height: 1.65))),
      ],
    ]);
  }
}
