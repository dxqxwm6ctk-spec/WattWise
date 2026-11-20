// "البيت" tab: live load, monthly meter, bill so far, and the approval card.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import '../widgets/assistant_widgets.dart';
import '../widgets/meter_widgets.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.st, required this.api, required this.run, required this.onApprove, required this.onReject});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  final Future<void> Function(int id) onApprove;
  final Future<void> Function(int id) onReject;

  @override
  Widget build(BuildContext context) {
    final pending = st['pending'] as Map<String, dynamic>?;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      CommandCard(api: api),
      const SizedBox(height: 12),
      _SummaryCard(st: st),
      const SizedBox(height: 12),
      pending != null
          ? _ApprovalCard(p: pending, onApprove: () => run(() => onApprove(pending['id'])), onReject: () => run(() => onReject(pending['id'])))
          : _StatusCard(st: st),
      for (final a in _openAlerts(st)) ...[
        const SizedBox(height: 12),
        _AlertCard(a: a, onAct: () => run(() => api.alertAct(a['id'] as int)), onDismiss: () => run(() => api.alertDismiss(a['id'] as int))),
      ],
      if ((st['anomaly'] as Map<String, dynamic>?)?['open'] == true && !_openAlerts(st).any((a) => a['kind'] == 'unknown_device' || a['kind'] == 'anomaly')) ...[
        const SizedBox(height: 12),
        _AnomalyCard(a: st['anomaly'] as Map<String, dynamic>),
      ],
    ]);
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.st});
  final Map<String, dynamic> st;

  @override
  Widget build(BuildContext context) {
    final maxW = ((st['labels'] as Map<String, dynamic>?)?['max_w'] as num? ?? 4000).toDouble();
    final w = ((st['meter']['power_w'] ?? 0) as num).toDouble();
    final bill = st['bill'] as Map<String, dynamic>;
    final goal = st['goal'] as Map<String, dynamic>?;
    final goalJd = goal?['bill_target_jd'] as num?;
    final proj = (bill['bill_projected'] as num).toDouble();
    final projColor = goalJd != null && proj > goalJd ? WW.amber : WW.lime;
    final kw = maxW > 1000 ? WW.fmt(w / 1000, 2) : WW.fmt(w);
    const light = TextStyle(color: Color(0xFFA9A79D));

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const RadialGradient(center: Alignment.topCenter, radius: 1.3, colors: [WW.darkCard1, WW.darkCard2]),
        boxShadow: const [BoxShadow(color: Color(0x99141408), blurRadius: 26, offset: Offset(0, 14), spreadRadius: -18)],
      ),
      child: DefaultTextStyle(
        style: const TextStyle(color: WW.paper),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Directionality(
            textDirection: TextDirection.ltr,
            child: Row(children: [
              Stack(clipBehavior: Clip.none, children: [
                LoadGauge(watts: w, maxWatts: maxW),
                const Positioned(left: 6, top: 86, child: Text('0', style: TextStyle(fontSize: 9, color: Color(0xFF8E8C82)))),
                Positioned(right: 2, top: 86, child: Text(maxW > 1000 ? '${maxW ~/ 1000}kW' : '${maxW.toInt()}W', style: const TextStyle(fontSize: 9, color: Color(0xFF8E8C82)))),
              ]),
              const SizedBox(width: 10),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  const Text('الحمل الآن', style: TextStyle(fontSize: 11, color: Color(0xFFA9A79D))),
                  const SizedBox(height: 6),
                  Row(mainAxisAlignment: MainAxisAlignment.end, crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
                    Text(kw, style: WW.mono.copyWith(fontSize: 28, fontWeight: FontWeight.w600, color: WW.paper)),
                    const SizedBox(width: 4),
                    Text(maxW > 1000 ? 'kW' : 'W', style: WW.mono.copyWith(fontSize: 11, color: const Color(0xFFA9A79D))),
                  ]),
                  const SizedBox(height: 6),
                  Odometer(kwh: ((bill['kwh_now'] ?? 0) as num).toDouble()),
                  const SizedBox(height: 6),
                  const Text('ك.و.س هالشهر', style: TextStyle(fontSize: 10, color: Color(0xFF8E8C82))),
                ]),
              ),
            ]),
          ),
          const SizedBox(height: 10),
          RoomBars(rooms: st['rooms'] as List<dynamic>, maxWatts: maxW * 0.6),
          const SizedBox(height: 8),
          const Divider(color: Color(0xFF2A2C25), height: 1),
          const SizedBox(height: 8),
          Row(children: [
            const Expanded(child: Text('الفاتورة لحد الآن', style: TextStyle(fontSize: 12, color: Color(0xFFA9A79D)))),
            Text('${WW.fmt(bill['bill_now'], 2)} JD', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 18, fontWeight: FontWeight.w600, color: WW.paper)),
          ]),
          if (goalJd != null) ...[
            const SizedBox(height: 6),
            ClipRRect(
              borderRadius: BorderRadius.circular(2),
              child: LinearProgressIndicator(value: (proj / goalJd).clamp(0, 1).toDouble(), minHeight: 4, backgroundColor: const Color(0xFF33352D), color: projColor),
            ),
            const SizedBox(height: 6),
            Row(children: [
              const Expanded(child: Text('متوقّع آخر الشهر', style: TextStyle(fontSize: 11, color: Color(0xFF8E8C82)))),
              Text.rich(
                TextSpan(children: [
                  TextSpan(text: WW.fmt(proj, 1), style: TextStyle(color: projColor)),
                  TextSpan(text: ' / ${WW.fmt(goalJd)} JD'),
                ]),
                textDirection: TextDirection.ltr,
                style: WW.mono.copyWith(fontSize: 11, color: const Color(0xFF8E8C82)),
              ),
            ]),
          ],
          const SizedBox(height: 6),
          Text('${bill['message']}', style: light.copyWith(fontSize: 12, height: 1.55, color: const Color(0xFFC8E68A))),
        ]),
      ),
    );
  }
}

class _ApprovalCard extends StatelessWidget {
  const _ApprovalCard({required this.p, required this.onApprove, required this.onReject});
  final Map<String, dynamic> p;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final left = (p['expires_in_s'] as num).toDouble();
    final total = (p['timeout_s'] as num).toDouble();
    return WWBox(
      color: WW.pendingBg,
      border: WW.pendingBorder,
      radius: 24,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Container(width: 8, height: 8, decoration: const BoxDecoration(color: Color(0xFFE8A21A), shape: BoxShape.circle)),
          const SizedBox(width: 8),
          const Expanded(child: Text('بدنا رأيك', style: TextStyle(fontSize: 13, color: WW.pendingText, fontWeight: FontWeight.w600))),
          Text('${left.toInt()}s', style: WW.mono.copyWith(fontSize: 13, color: WW.pendingText)),
        ]),
        const SizedBox(height: 10),
        Text('${p['title']}', style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700, height: 1.35)),
        const SizedBox(height: 8),
        Text('${p['reason']}', style: const TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF4A4536))),
        if ((p['details'] as Map?)?['alternative'] != null) ...[
          const SizedBox(height: 6),
          Text('إذا لا: ${p['details']['alternative']}', style: const TextStyle(fontSize: 13, height: 1.6, color: Color(0xFF6B4A00))),
        ],
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(color: const Color(0xFFFBE7B5), borderRadius: BorderRadius.circular(12)),
          child: Row(children: [
            const Expanded(child: Text('بيوفّر تقريبًا', style: TextStyle(fontSize: 13, color: Color(0xFF6B4A00)))),
            Text('${WW.fmt(p['details']['saving_jod_per_hour'], 3)} JD / hr',
                textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 15, fontWeight: FontWeight.w600)),
          ]),
        ),
        const SizedBox(height: 10),
        ClipRRect(
          borderRadius: BorderRadius.circular(2),
          child: LinearProgressIndicator(value: (left / total).clamp(0, 1), minHeight: 4, backgroundColor: const Color(0xFFF1D58E), color: const Color(0xFFE8A21A)),
        ),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            flex: 10,
            child: SizedBox(
              height: 54,
              child: OutlinedButton(
                onPressed: onReject,
                style: OutlinedButton.styleFrom(
                  foregroundColor: WW.ink,
                  side: const BorderSide(color: Color(0xFFD9C38A), width: 1.5),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
                ),
                child: const Text('لا، خلّيه', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 14,
            child: SizedBox(
              height: 54,
              child: FilledButton(
                onPressed: onApprove,
                style: FilledButton.styleFrom(backgroundColor: WW.ink, foregroundColor: WW.paper, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
                child: const Text('إيه، طفّيه', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        const Text('إذا ما رديتي، ما رح نعمل إشي', textAlign: TextAlign.center, style: TextStyle(fontSize: 11.5, color: Color(0xFF8A7A55))),
      ]),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.st});
  final Map<String, dynamic> st;

  @override
  Widget build(BuildContext context) {
    final agent = st['agent'] as Map<String, dynamic>;
    final last = st['last_approval'] as Map<String, dynamic>?;
    final dev = (last?['device_name'] as String?) ?? 'الجهاز';
    const red = (Color(0xFFA23A26), Color(0xFFF0C2B8));
    const amber = (Color(0xFF8A5A00), Color(0xFFE8B23A));
    const green = (Color(0xFF4A6418), Color(0xFFD6E8B0));

    late final (Color, Color) c;
    late final String title, body;
    if (st['online'] != true) {
      (c, title, body) = (red, 'ما في قراءات', 'انقطعت القراءات، فكل إشي رجع طبيعي وما في إجراء تلقائي.');
    } else if (agent['estop'] == true) {
      (c, title, body) = (red, 'WattWise موقوف', 'كل الأجهزة رجعت طبيعي. ما رح نقترح إشي لحد ما تشغّليه.');
    } else if (agent['safe_mode'] == true) {
      (c, title, body) = (red, 'ما في اتصال', 'الراوتر مطفي، فما بنطلب موافقة وما بننفّذ إشي.');
    } else if (st['goal'] == null) {
      (c, title, body) = (amber, 'بانتظار هدف', 'أعطِ الوكيل هدف من لوحة التحكم عشان يبلّش.');
    } else {
      (c, title, body) = switch (agent['phase']) {
        'analyzing' => (amber, 'عم نفكّر', 'لاحظنا جهاز شغّال بغرفة فاضية. ثواني ونرجعلك.'),
        'executing' => (green, 'عم نطفيه', 'وصلتنا موافقتك.'),
        'verified' => (green, 'تم ✓', 'طفينا $dev والعدّاد أكّد. التوفير بيبيّن تحت بالفاتورة.'),
        'rejected' => (red, 'تمام، ما لمسنا إشي', '$dev بقي متل ما بدك.'),
        'expired' => (red, 'ما وصلنا رد', 'فما عملنا إشي. السكوت عنا مش موافقة.'),
        _ => (green, 'كل إشي تمام', 'البيت ماشي طبيعي وما في هدر هلأ.'),
      };
    }
    return WWBox(
      border: c.$2,
      radius: 20,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: c.$1)),
        const SizedBox(height: 4),
        Text(body, style: const TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF4A4840))),
      ]),
    );
  }
}


/// AI layer 1: the meter reads something the known devices do not explain. Alert only.
class _AnomalyCard extends StatelessWidget {
  const _AnomalyCard({required this.a});
  final Map<String, dynamic> a;

  @override
  Widget build(BuildContext context) {
    final w = (a['residual_w'] as num? ?? 0).toInt();
    final msg = a['kind'] == 'extra'
        ? 'في جهاز عم يسحب ≈ $w واط وما بنعرفه. شيكي إذا في إشي شغّال ومش لازم.'
        : 'الاستهلاك أقل من المتوقع بـ≈ ${-w} واط. ممكن جهاز فاصل أو معطّل.';
    return WWBox(
      color: WW.pendingBg,
      border: WW.pendingBorder,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('استهلاك غريب', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: WW.pendingText)),
        const SizedBox(height: 4),
        Text(msg, style: const TextStyle(fontSize: 14, height: 1.7)),
      ]),
    );
  }
}


/// Warnings that are still true and that the user did not answer yet.
List<Map<String, dynamic>> _openAlerts(Map<String, dynamic> st) =>
    ((st['alerts'] as Map<String, dynamic>?)?['items'] as List<dynamic>? ?? [])
        .cast<Map<String, dynamic>>()
        .where((a) => a['active'] == true && a['user_state'] == null)
        .toList();

/// One warning from the agent (the same one the phone showed as a notification).
/// "طفّيه؟" only sends an approval request; nothing is switched before "إيه، طفّيه".
class _AlertCard extends StatelessWidget {
  const _AlertCard({required this.a, required this.onAct, required this.onDismiss});
  final Map<String, dynamic> a;
  final VoidCallback onAct;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final danger = a['level'] == 'danger';
    final bg = danger ? const Color(0xFFFBE3DD) : WW.pendingBg;
    final border = danger ? WW.red : WW.pendingBorder;
    final text = danger ? const Color(0xFF7A2A1C) : WW.pendingText;
    return WWBox(
      color: bg,
      border: border,
      radius: 20,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('${a['title']}', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: text)),
        const SizedBox(height: 4),
        Text('${a['body']}', style: const TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF4A4840))),
        const SizedBox(height: 10),
        Row(children: [
          if (a['can_act'] == true) ...[
            Expanded(
              flex: 14,
              child: SizedBox(
                height: 44,
                child: FilledButton(
                  onPressed: onAct,
                  style: FilledButton.styleFrom(backgroundColor: WW.ink, foregroundColor: WW.paper, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                  child: const Text('طفّيه؟', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                ),
              ),
            ),
            const SizedBox(width: 8),
          ],
          Expanded(
            flex: 10,
            child: SizedBox(
              height: 44,
              child: OutlinedButton(
                onPressed: onDismiss,
                style: OutlinedButton.styleFrom(foregroundColor: WW.ink, side: BorderSide(color: border, width: 1.5), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                child: const Text('تمام', style: TextStyle(fontSize: 14)),
              ),
            ),
          ),
        ]),
      ]),
    );
  }
}
