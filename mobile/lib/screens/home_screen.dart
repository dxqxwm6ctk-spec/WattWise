// "البيت" tab: the approval card (or the agent status), key numbers and open alerts.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';

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
      pending != null
          ? _ApprovalCard(p: pending, onApprove: () => run(() => onApprove(pending['id'])), onReject: () => run(() => onReject(pending['id'])))
          : _StatusCard(st: st),
      const SizedBox(height: 12),
      _SummaryCard(st: st),
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
    final over = goalJd != null && proj > goalJd;
    final kw = maxW > 1000 ? '${WW.fmt(w / 1000, 2)} kW' : '${WW.fmt(w)} W';

    Widget line(String label, String value, {Color? color}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(children: [
            Expanded(child: Text(label, style: const TextStyle(fontSize: 14, color: WW.sub))),
            Text(value, textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 17, fontWeight: FontWeight.w600, color: color ?? WW.ink)),
          ]),
        );

    return WWBox(
      radius: 20,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        line('الاستهلاك الآن', kw),
        line('الفاتورة حتى الآن', '${WW.fmt(bill['bill_now'], 2)} JD'),
        line('المتوقّع آخر الشهر', goalJd != null ? '${WW.fmt(proj, 1)} / ${WW.fmt(goalJd)} JD' : '${WW.fmt(proj, 1)} JD',
            color: over ? WW.pendingText : null),
      ]),
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
          const Expanded(child: Text('نحتاج موافقتك', style: TextStyle(fontSize: 13, color: WW.pendingText, fontWeight: FontWeight.w600))),
          Text('${left.toInt()}s', style: WW.mono.copyWith(fontSize: 13, color: WW.pendingText)),
        ]),
        const SizedBox(height: 10),
        Text('${p['title']}', style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700, height: 1.35)),
        const SizedBox(height: 8),
        Text('${p['reason']}', style: const TextStyle(fontSize: 14, height: 1.7, color: Color(0xFF4A4536))),
        if ((p['details'] as Map?)?['alternative'] != null) ...[
          const SizedBox(height: 6),
          Text('البديل: ${p['details']['alternative']}', style: const TextStyle(fontSize: 13, height: 1.6, color: Color(0xFF6B4A00))),
        ],
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(color: const Color(0xFFFBE7B5), borderRadius: BorderRadius.circular(12)),
          child: Row(children: [
            const Expanded(child: Text('التوفير التقريبي', style: TextStyle(fontSize: 13, color: Color(0xFF6B4A00)))),
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
                child: const Text('لا، اتركه', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
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
                child: const Text('نعم، أطفئه', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        const Text('إن لم تردّ، لن نفعل شيئًا', textAlign: TextAlign.center, style: TextStyle(fontSize: 11.5, color: Color(0xFF8A7A55))),
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
      (c, title, body) = (red, 'لا توجد قراءات', 'عادت الأجهزة إلى وضعها الطبيعي.');
    } else if (agent['estop'] == true) {
      (c, title, body) = (red, 'WattWise متوقف', 'عادت الأجهزة إلى وضعها الطبيعي.');
    } else if (agent['safe_mode'] == true) {
      (c, title, body) = (red, 'لا يوجد اتصال', 'لن ننفّذ شيئًا حتى يعود الاتصال.');
    } else if (st['goal'] == null) {
      (c, title, body) = (amber, 'بانتظار هدف', 'أعطِ الوكيل هدفًا من لوحة التحكم ليبدأ.');
    } else {
      (c, title, body) = switch (agent['phase']) {
        'analyzing' => (amber, 'جارٍ التحليل', 'جهاز يعمل في غرفة فارغة.'),
        'executing' => (green, 'جارٍ الإطفاء', 'وصلت موافقتك.'),
        'verified' => (green, 'تم ✓', 'أُطفئ $dev وأكّد العدّاد ذلك.'),
        'rejected' => (red, 'حسنًا، لم نغيّر شيئًا', 'بقي $dev كما هو.'),
        'expired' => (red, 'لم يصل رد', 'لذا لم نفعل شيئًا. عدم الرد لا يعني الموافقة.'),
        _ => (green, 'كل شيء على ما يرام', 'لا يوجد هدر الآن.'),
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
        ? 'جهاز غير معروف يستهلك ≈ $w واط. تحقّق إن كان هناك جهاز يعمل دون حاجة.'
        : 'الاستهلاك أقل من المتوقع بنحو ${-w} واط. ربما يوجد جهاز مفصول أو معطّل.';
    return WWBox(
      color: WW.pendingBg,
      border: WW.pendingBorder,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('استهلاك غير معتاد', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: WW.pendingText)),
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
/// "أطفئه؟" only sends an approval request; nothing is switched before "نعم، أطفئه".
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
                  child: const Text('أطفئه؟', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
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
                child: const Text('تجاهل', style: TextStyle(fontSize: 14)),
              ),
            ),
          ),
        ]),
      ]),
    );
  }
}
