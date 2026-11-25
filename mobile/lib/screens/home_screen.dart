// "البيت" tab: the approval card (or the agent's state), the money summary and open alerts.

import 'dart:math' as math;

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
    final alerts = _openAlerts(st);
    final anomaly = st['anomaly'] as Map<String, dynamic>?;
    final showAnomaly = anomaly?['open'] == true && !alerts.any((a) => a['kind'] == 'unknown_device' || a['kind'] == 'anomaly');
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      pending != null
          ? _ApprovalCard(p: pending, onApprove: () => run(() => onApprove(pending['id'])), onReject: () => run(() => onReject(pending['id'])))
          : _StatusCard(st: st),
      const SizedBox(height: 14),
      _SummaryCard(st: st),
      if (alerts.isNotEmpty) ...[
        const SizedBox(height: 14),
        SectionTitle('تنبيهات', count: alerts.length),
        for (final a in alerts) ...[
          const SizedBox(height: 10),
          _AlertCard(a: a, onAct: () => run(() => api.alertAct(a['id'] as int)), onDismiss: () => run(() => api.alertDismiss(a['id'] as int))),
        ],
      ],
      if (showAnomaly) ...[
        const SizedBox(height: 14),
        _AnomalyCard(a: anomaly!),
      ],
    ]);
  }
}

/// Dark card: the bill so far, the power right now, and the month's projection against the goal.
class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.st});
  final Map<String, dynamic> st;

  @override
  Widget build(BuildContext context) {
    final w = ((st['meter']['power_w'] ?? 0) as num).toDouble();
    final bill = st['bill'] as Map<String, dynamic>;
    final goal = st['goal'] as Map<String, dynamic>?;
    final goalJd = goal?['bill_target_jd'] as num?;
    final proj = (bill['bill_projected'] as num).toDouble();
    final over = goalJd != null && proj > goalJd;
    final frac = goalJd == null || goalJd <= 0 ? null : (proj / goalJd).clamp(0.0, 1.0);

    return WWBox(
      dark: true,
      radius: 24,
      padding: 18,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('فاتورة هذا الشهر حتى الآن', style: TextStyle(fontSize: 13, color: WW.darkSub)),
              const SizedBox(height: 2),
              Text.rich(
                TextSpan(children: [
                  TextSpan(text: WW.fmt(bill['bill_now'] as num?, 2)),
                  const TextSpan(text: ' JD', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: WW.darkSub)),
                ]),
                textDirection: TextDirection.ltr,
                style: WW.mono.copyWith(fontSize: 36, fontWeight: FontWeight.w700, letterSpacing: -0.5, height: 1.15, color: Colors.white),
              ),
            ]),
          ),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            const Row(mainAxisSize: MainAxisSize.min, children: [
              PulseDot(color: WW.accentLight),
              SizedBox(width: 6),
              Text('الاستهلاك الآن', style: TextStyle(fontSize: 13, color: WW.darkSub)),
            ]),
            const SizedBox(height: 2),
            Text(WW.watts(w), textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 22, fontWeight: FontWeight.w700, color: WW.accentLight)),
          ]),
        ]),
        const SizedBox(height: 14),
        if (frac != null) ...[
          _Bar(frac: frac, color: over ? WW.redSoft : WW.accent, track: WW.darkLine, height: 8),
          const SizedBox(height: 8),
        ],
        Row(children: [
          Expanded(child: Text(goalJd != null ? 'المتوقع لنهاية الشهر مقابل الهدف' : 'المتوقع لنهاية الشهر', style: const TextStyle(fontSize: 13, color: WW.darkSub))),
          Text.rich(
            TextSpan(children: [
              TextSpan(text: WW.fmt(proj, 1)),
              TextSpan(text: goalJd != null ? ' / ${WW.fmt(goalJd)} JD' : ' JD', style: const TextStyle(color: WW.darkSub, fontWeight: FontWeight.w500)),
            ]),
            textDirection: TextDirection.ltr,
            style: WW.mono.copyWith(fontSize: 13, fontWeight: FontWeight.w700, color: WW.accentLight),
          ),
        ]),
        if (goalJd != null) ...[
          const SizedBox(height: 8),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: over ? const Pill('أعلى من الهدف', bg: WW.redSoft, fg: WW.ink) : const Pill('ضمن الهدف', bg: WW.greenBright, fg: WW.ink),
          ),
        ],
      ]),
    );
  }
}

class _Bar extends StatelessWidget {
  const _Bar({required this.frac, required this.color, required this.track, this.height = 4});
  final double frac;
  final Color color, track;
  final double height;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(height / 2),
        child: SizedBox(
          height: height,
          child: Stack(children: [
            Positioned.fill(child: ColoredBox(color: track)),
            FractionallySizedBox(
              alignment: AlignmentDirectional.centerStart,
              widthFactor: frac.clamp(0.0, 1.0),
              child: Container(decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(height / 2))),
            ),
          ]),
        ),
      );
}

/// The approval request: dark card, countdown ring, reason, alternative, saving, two big buttons.
class _ApprovalCard extends StatelessWidget {
  const _ApprovalCard({required this.p, required this.onApprove, required this.onReject});
  final Map<String, dynamic> p;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    final left = (p['expires_in_s'] as num).toDouble();
    final total = math.max(1.0, (p['timeout_s'] as num).toDouble());
    final frac = (left / total).clamp(0.0, 1.0);
    final details = (p['details'] as Map?) ?? const {};
    final turnOn = p['turn_on'] == true;
    final mmss = '${left ~/ 60}:${(left.toInt() % 60).toString().padLeft(2, '0')}';
    const body = TextStyle(fontSize: 15, height: 1.6, color: WW.darkBody);

    return Container(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
      decoration: BoxDecoration(
        color: WW.ink,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: WW.accent.withValues(alpha: 0.30)),
      ),
      child: DefaultTextStyle.merge(
        style: const TextStyle(color: Colors.white),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(color: WW.darkChip, borderRadius: BorderRadius.circular(999)),
              child: const Row(mainAxisSize: MainAxisSize.min, children: [
                PulseDot(color: WW.accent),
                SizedBox(width: 8),
                Text('نحتاج موافقتك', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: WW.accentText)),
              ]),
            ),
            const Spacer(),
            Semantics(
              label: '${left.toInt()} ثانية متبقية',
              child: SizedBox(
                width: 52,
                height: 52,
                child: Stack(alignment: Alignment.center, children: [
                  CustomPaint(size: const Size(52, 52), painter: _RingPainter(frac)),
                  Text('${left.toInt()}s', textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 14, fontWeight: FontWeight.w700, color: Colors.white)),
                ]),
              ),
            ),
          ]),
          const SizedBox(height: 14),
          Text('${p['title']}', style: const TextStyle(fontSize: 23, height: 1.35, fontWeight: FontWeight.w700, color: Colors.white)),
          const SizedBox(height: 14),
          Text('${p['reason']}', style: body),
          if (details['alternative'] != null) ...[
            const SizedBox(height: 14),
            Text.rich(TextSpan(children: [
              const TextSpan(text: 'البديل: ', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
              TextSpan(text: '${details['alternative']}'),
            ]), style: body.copyWith(fontSize: 14)),
          ],
          if (details['saving_jod_per_hour'] != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(color: WW.darkField, borderRadius: BorderRadius.circular(14)),
              child: Row(children: [
                const Expanded(child: Text('التوفير التقريبي', style: TextStyle(fontSize: 13, color: WW.darkBody))),
                Text.rich(
                  TextSpan(children: [
                    TextSpan(text: '${WW.fmt(details['saving_jod_per_hour'] as num?, 3)} JD'),
                    const TextSpan(text: ' / hr', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: WW.darkBody)),
                  ]),
                  textDirection: TextDirection.ltr,
                  style: WW.mono.copyWith(fontSize: 20, fontWeight: FontWeight.w700, color: WW.accentText),
                ),
              ]),
            ),
          ],
          const SizedBox(height: 14),
          Row(children: [
            const Expanded(child: Text('ينتهي الطلب بعد', style: TextStyle(fontSize: 12.5, color: WW.darkBody))),
            Text(mmss, textDirection: TextDirection.ltr, style: WW.mono.copyWith(fontSize: 12.5, fontWeight: FontWeight.w600, color: Colors.white)),
          ]),
          const SizedBox(height: 6),
          _Bar(frac: frac, color: WW.accent, track: WW.darkLine),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(child: WWButton(turnOn ? 'لا، اتركه مطفأ' : 'لا، اتركه', onReject, kind: BtnKind.darkGhost, height: 56, fontSize: 16)),
            const SizedBox(width: 10),
            Expanded(child: WWButton(turnOn ? 'نعم، شغّله' : 'نعم، أطفئه', onApprove, kind: BtnKind.accent, height: 56, fontSize: 16)),
          ]),
          const SizedBox(height: 14),
          const Row(children: [
            Icon(Icons.shield_outlined, size: 16, color: WW.darkBody),
            SizedBox(width: 8),
            Text('إن لم تردّ، لن نفعل شيئًا.', style: TextStyle(fontSize: 13, color: WW.darkBody)),
          ]),
        ]),
      ),
    );
  }
}

/// Countdown ring around the seconds left.
class _RingPainter extends CustomPainter {
  _RingPainter(this.frac);
  final double frac;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromCircle(center: size.center(Offset.zero), radius: 22);
    final p = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(rect, 0, 2 * math.pi, false, p..color = WW.darkLine);
    canvas.drawArc(rect, -math.pi / 2, 2 * math.pi * frac, false, p..color = WW.accent);
  }

  @override
  bool shouldRepaint(_RingPainter old) => old.frac != frac;
}

/// What the agent is doing when nothing waits for approval: one short title and one line.
class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.st});
  final Map<String, dynamic> st;

  static const _green = (WW.greenBg, WW.green);
  static const _blue = (WW.blueBg, WW.blueFg);
  static const _grey = (WW.neutralBg, WW.body);
  static const _amber = (WW.pendingBg, WW.pendingFg);
  static const _red = (WW.redBg, WW.red);

  @override
  Widget build(BuildContext context) {
    final agent = st['agent'] as Map<String, dynamic>;
    final last = st['last_approval'] as Map<String, dynamic>?;
    final dev = (last?['device_name'] as String?) ?? 'الجهاز';

    late final (Color, Color) c;
    late final IconData icon;
    late final String title, body;
    if (st['online'] != true) {
      (c, icon, title, body) = (_grey, Icons.speed_outlined, 'لا توجد قراءات', 'لم يصل شيء من العدّاد. عادت الأجهزة إلى وضعها الطبيعي.');
    } else if (agent['estop'] == true) {
      (c, icon, title, body) = (_red, Icons.stop_rounded, 'WattWise متوقف', 'أوقفته من صفحة الأمان. لن نقترح أي إجراء.');
    } else if (agent['safe_mode'] == true) {
      (c, icon, title, body) = (_amber, Icons.gpp_maybe_outlined, 'لا يوجد اتصال', 'وضع الأمان: أُعيدت الأجهزة إلى حالتها الطبيعية.');
    } else if (st['goal'] == null) {
      (c, icon, title, body) = (_grey, Icons.flag_outlined, 'بانتظار هدف', 'اكتب هدفك في صفحة الفاتورة لنبدأ التخطيط.');
    } else {
      (c, icon, title, body) = switch (agent['phase']) {
        'analyzing' => (_blue, Icons.search_rounded, 'جارٍ التحليل', 'جهاز يعمل في غرفة فارغة، نتأكد قبل أن نسألك.'),
        'executing' => (_amber, Icons.bolt_rounded, 'جارٍ الإطفاء', 'وصلت موافقتك، نطفئ الجهاز الآن.'),
        'verified' => (_green, Icons.check_rounded, 'تم ✓', 'أُطفئ $dev وأكّد العدّاد ذلك.'),
        'rejected' => (_grey, Icons.undo_rounded, 'حسنًا، لم نغيّر شيئًا', 'رفضت الطلب، فبقي $dev كما هو.'),
        'expired' => (_grey, Icons.schedule_rounded, 'لم يصل رد', 'انتهى وقت الطلب، لذلك لم نفعل شيئًا.'),
        _ => (_green, Icons.check_rounded, 'كل شيء على ما يرام', 'لا يوجد هدر في الكهرباء الآن.'),
      };
    }
    return WWBox(
      radius: 24,
      padding: 18,
      child: Row(children: [
        IconTile(icon: icon, bg: c.$1, fg: c.$2),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text(body, style: const TextStyle(fontSize: 14, height: 1.6, color: WW.body)),
          ]),
        ),
      ]),
    );
  }
}

/// AI layer 1: the meter reads something the known devices do not explain. Information only.
class _AnomalyCard extends StatelessWidget {
  const _AnomalyCard({required this.a});
  final Map<String, dynamic> a;

  @override
  Widget build(BuildContext context) {
    final w = (a['residual_w'] as num? ?? 0).toInt();
    final msg = a['kind'] == 'extra'
        ? 'جهاز غير معروف يستهلك ≈ $w W.'
        : 'الاستهلاك أقل من المتوقع بـ ≈ ${-w} W، ربما جهاز مفصول أو معطّل.';
    return DashedBox(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Pill('AI'),
          SizedBox(width: 8),
          Text('استهلاك غير معتاد', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ]),
        const SizedBox(height: 8),
        Text(msg, style: const TextStyle(fontSize: 14, height: 1.6, color: WW.body)),
        const SizedBox(height: 8),
        const Text('للعلم فقط، لن نفعل شيئًا.', style: TextStyle(fontSize: 12, color: WW.sub)),
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
    final (bg, border, fg) = danger ? (WW.redBg, WW.redBorder, WW.red) : (WW.warnBg, WW.warnBorder, WW.warnFg);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20), border: Border.all(color: border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          IconTile(icon: Icons.warning_amber_rounded, bg: Colors.white, fg: fg, size: 36, iconSize: 20, radius: 12),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(danger ? 'خطر' : 'تحذير', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: fg)),
              const SizedBox(height: 3),
              Text('${a['title']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 3),
              Text('${a['body']}', style: const TextStyle(fontSize: 14, height: 1.6, color: WW.body)),
            ]),
          ),
        ]),
        const SizedBox(height: 10),
        Row(mainAxisAlignment: MainAxisAlignment.end, children: [
          TextButton(
            onPressed: onDismiss,
            style: TextButton.styleFrom(foregroundColor: WW.body, minimumSize: const Size(0, 44)),
            child: const Text('تجاهل', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ),
          if (a['can_act'] == true) ...[
            const SizedBox(width: 8),
            WWButton('أطفئه؟', onAct, height: 44, radius: 14, fontSize: 14),
          ],
        ]),
      ]),
    );
  }
}
