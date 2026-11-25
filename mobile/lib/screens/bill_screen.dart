// "الفاتورة" tab: measured savings, goal and plan, "why is my bill like this?", bill photo,
// weekly report, tariff, where the money goes, and the short-term forecast.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/assistant_widgets.dart';
import '../widgets/bill_photo_card.dart';

class BillScreen extends StatelessWidget {
  const BillScreen({super.key, required this.st, required this.api, required this.run});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;

  // One colour per row of the cost breakdown, from the design.
  static const _barColors = [Color(0xFF7CC4FF), Color(0xFFFFB35C), Color(0xFFFF9C8A), WW.accent, WW.muted];

  @override
  Widget build(BuildContext context) {
    final b = st['bill'] as Map<String, dynamic>;
    final s = st['savings'] as Map<String, dynamic>;
    final breakdown = st['breakdown'] as List<dynamic>;
    final f = st['forecast'] as Map<String, dynamic>?;
    final totalJd = breakdown.fold<double>(0, (a, x) => a + (x['jod'] as num).toDouble());
    const h2 = TextStyle(fontSize: 17, fontWeight: FontWeight.w700);
    final types = b['types'] as List;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      // Measured savings (M&V): only what the meter really measured.
      WWBox(
        dark: true,
        radius: 24,
        padding: 20,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Row(children: [
            Expanded(child: Text('التوفير المقاس', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: WW.darkSub))),
            Pill('مقاس', bg: WW.greenBright, fg: WW.ink),
          ]),
          const SizedBox(height: 8),
          Text.rich(
            TextSpan(children: [
              TextSpan(text: WW.fmt(s['jod'] as num?, 3)),
              const TextSpan(text: ' JD', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: Colors.white)),
            ]),
            textDirection: TextDirection.ltr,
            style: WW.mono.copyWith(fontSize: 48, fontWeight: FontWeight.w700, letterSpacing: -1, height: 1.1, color: WW.greenBright),
          ),
          const SizedBox(height: 8),
          Text.rich(TextSpan(children: [
            TextSpan(text: '${WW.fmt(s['kwh'] as num?, 2)} kWh', style: WW.mono),
            const TextSpan(text: ' · '),
            TextSpan(text: '${s['co2_kg'] == null ? '—' : WW.fmt(s['co2_kg'] as num, 2)} kg CO₂', style: WW.mono),
            const TextSpan(text: ' أقل'),
          ]), style: const TextStyle(fontSize: 14, color: WW.accentLight)),
        ]),
      ),
      const SizedBox(height: 14),
      GoalCard(st: st, api: api, run: run),
      const SizedBox(height: 14),
      WhyCard(api: api),
      const SizedBox(height: 14),
      BillPhotoCard(api: api),
      const SizedBox(height: 14),
      ReportCard(api: api),
      const SizedBox(height: 14),
      WWBox(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('نوع الاشتراك', style: h2),
          const SizedBox(height: 12),
          Segmented(
            labels: [for (final o in types) '${o['label']}'],
            selected: types.indexWhere((o) => o['key'] == b['type']).clamp(0, types.length - 1),
            onTap: (i) => run(() => api.setTariff(types[i]['key'])),
          ),
          const SizedBox(height: 12),
          Text('${b['who']}', style: const TextStyle(fontSize: 13, height: 1.6, color: WW.sub)),
          const SizedBox(height: 10),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            child: Row(children: [
              Expanded(child: Text('الاستهلاك الشهري', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: WW.sub))),
              Text('السعر', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: WW.sub)),
            ]),
          ),
          for (final t in b['segments'] as List)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
              color: t['active'] == true ? WW.ink : Colors.transparent,
              child: Row(children: [
                Expanded(
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: Text(
                      t['to_kwh'] == null
                          ? '> ${(t['from_kwh'] as num).toInt()} kWh'
                          : '${(t['from_kwh'] as num).toInt() + 1} – ${(t['to_kwh'] as num).toInt()} kWh',
                      textDirection: TextDirection.ltr,
                      style: WW.mono.copyWith(fontSize: 14, fontWeight: FontWeight.w600, color: t['active'] == true ? WW.accent : WW.ink),
                    ),
                  ),
                ),
                Text.rich(TextSpan(children: [
                  TextSpan(text: '${t['fils']}', style: WW.mono),
                  const TextSpan(text: ' فلس/kWh'),
                ]), style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: t['active'] == true ? WW.accent : WW.ink)),
              ]),
            ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(color: WW.warnBg, borderRadius: BorderRadius.circular(14), border: Border.all(color: WW.warnBorder)),
            child: Text('${b['message']}', style: const TextStyle(fontSize: 13.5, height: 1.6, color: WW.pendingText)),
          ),
        ]),
      ),
      const SizedBox(height: 14),
      WWBox(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('تفصيل التكلفة', style: h2),
          const SizedBox(height: 12),
          if (breakdown.isEmpty) const Text('لا توجد بيانات كافية بعد.', style: TextStyle(fontSize: 13, color: WW.sub)),
          for (final (i, x) in breakdown.indexed) ...[
            Builder(builder: (_) {
              final share = totalJd <= 0 ? 0.0 : (x['jod'] as num) / totalJd;
              return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  Expanded(child: Text('${x['name']}', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                  Text('${WW.fmt(x['jod'] as num, 2)} JD', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 14, fontWeight: FontWeight.w700)),
                  Text(' · ${(share * 100).round()}%', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 14, color: WW.sub)),
                ]),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(value: share, minHeight: 8, backgroundColor: WW.neutralBg, color: _barColors[i % _barColors.length]),
                ),
              ]);
            }),
            const SizedBox(height: 12),
          ],
        ]),
      ),
      if (f != null) ...[
        const SizedBox(height: 14),
        WWBox(
          dark: true,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('المتوقع للساعات الـ${(f['steps'] as List).length} القادمة', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: WW.darkSub)),
            const SizedBox(height: 8),
            Text.rich(
              TextSpan(children: [
                TextSpan(text: '${WW.fmt(f['jod'] as num?, 2)} JD', style: const TextStyle(color: WW.accent)),
                const TextSpan(text: ' · '),
                TextSpan(text: '${WW.fmt(f['kwh'] as num?, 1)} kWh', style: const TextStyle(color: WW.accentLight)),
              ]),
              textDirection: TextDirection.ltr,
              style: WW.mono.copyWith(fontSize: 26, fontWeight: FontWeight.w700, color: Colors.white),
            ),
            const SizedBox(height: 8),
            Text(
                (f['accuracy']['hours'] as num) > 0
                    ? 'خطأ التوقع ≈ ${WW.fmt(f['accuracy']['mean_err_pct'] as num?, 0)}% (مقاس على العدّاد)'
                    : 'جارٍ قياس دقة التوقع',
                style: const TextStyle(fontSize: 13, color: WW.darkBody)),
          ]),
        ),
      ],
    ]);
  }
}
