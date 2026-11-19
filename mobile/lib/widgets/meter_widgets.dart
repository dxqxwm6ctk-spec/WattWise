// Gauge, odometer and room bars for the dark summary card on the home screen.

import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';

import '../theme.dart';

Color gaugeColor(double frac) => frac > 0.75 ? const Color(0xFFE8553F) : frac > 0.5 ? WW.amber : WW.lime;

/// Half-circle gauge with ticks and a needle. Animates when the value changes.
class LoadGauge extends StatelessWidget {
  const LoadGauge({super.key, required this.watts, required this.maxWatts});
  final double watts;
  final double maxWatts;

  @override
  Widget build(BuildContext context) {
    final frac = (watts / maxWatts).clamp(0.0, 1.0);
    return TweenAnimationBuilder<double>(
      tween: Tween(end: frac),
      duration: const Duration(milliseconds: 1100),
      curve: Curves.easeOutBack,
      builder: (context, f, _) => CustomPaint(size: const Size(150, 96), painter: _GaugePainter(f.clamp(0.0, 1.0))),
    );
  }
}

class _GaugePainter extends CustomPainter {
  _GaugePainter(this.frac);
  final double frac;

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, 80);
    const r = 62.0;
    final color = gaugeColor(frac);
    final rect = Rect.fromCircle(center: c, radius: r);

    // glow
    canvas.drawCircle(c.translate(0, -10), 40,
        Paint()..color = color.withValues(alpha: 0.28)..maskFilter = const MaskFilter.blur(BlurStyle.normal, 30));
    // track + value arc
    final arc = Paint()..style = PaintingStyle.stroke..strokeWidth = 9..strokeCap = StrokeCap.round;
    canvas.drawArc(rect, math.pi, math.pi, false, arc..color = const Color(0xFF33352D));
    canvas.drawArc(rect, math.pi, math.pi * frac, false, arc..color = color);
    // ticks
    for (var i = 0; i <= 20; i++) {
      final major = i % 5 == 0;
      final lit = i / 20 <= frac;
      final a = math.pi + math.pi * i / 20;
      final len = major ? 7.0 : 4.0;
      final p1 = c + Offset(math.cos(a), math.sin(a)) * 54;
      final p2 = c + Offset(math.cos(a), math.sin(a)) * (54 - len);
      canvas.drawLine(p1, p2, Paint()
        ..strokeWidth = major ? 2 : 1
        ..color = lit ? (major ? WW.paper : const Color(0xFFA9A79D)) : (major ? const Color(0xFF5E5C55) : const Color(0xFF33352D)));
    }
    // needle
    final a = math.pi + math.pi * frac;
    canvas.drawLine(c, c + Offset(math.cos(a), math.sin(a)) * 50,
        Paint()..strokeWidth = 3..strokeCap = StrokeCap.round..color = WW.paper);
    canvas.drawCircle(c, 7, Paint()..color = WW.darkCard2);
    canvas.drawCircle(c, 7, Paint()..style = PaintingStyle.stroke..strokeWidth = 2.5..color = WW.paper);
  }

  @override
  bool shouldRepaint(_GaugePainter old) => old.frac != frac;
}

/// Rolling digits like a real electricity meter (last digit = tenths of a kWh).
class Odometer extends StatelessWidget {
  const Odometer({super.key, required this.kwh});
  final double kwh;

  @override
  Widget build(BuildContext context) {
    final s = kwh.toStringAsFixed(1).replaceAll('.', '').padLeft(6, '0');
    final digits = s.substring(s.length - 6).split('').map(int.parse).toList();
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: const Color(0xFF0A0B08),
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: const Color(0xFF2A2C25)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          for (var i = 0; i < 6; i++)
            Padding(padding: const EdgeInsets.symmetric(horizontal: 1), child: _Digit(value: digits[i], last: i == 5)),
        ]),
      ),
    );
  }
}

class _Digit extends StatelessWidget {
  const _Digit({required this.value, required this.last});
  final int value;
  final bool last;

  @override
  Widget build(BuildContext context) {
    const h = 22.0;
    return Container(
      width: 15,
      height: h,
      decoration: BoxDecoration(color: last ? const Color(0xFF3A1712) : const Color(0xFF16170F), borderRadius: BorderRadius.circular(3)),
      clipBehavior: Clip.hardEdge,
      child: TweenAnimationBuilder<double>(
        tween: Tween(end: value.toDouble()),
        duration: const Duration(milliseconds: 900),
        curve: Curves.easeInOut,
        builder: (context, v, _) => OverflowBox(
          alignment: Alignment.topCenter,
          maxHeight: h * 10,
          child: Transform.translate(
            offset: Offset(0, -v * h),
            child: Column(children: [
              for (var n = 0; n < 10; n++)
                SizedBox(
                  height: h,
                  child: Center(
                    child: Text('$n',
                        style: WW.mono.copyWith(fontSize: 13, fontWeight: FontWeight.w600, color: last ? const Color(0xFFFF8A70) : const Color(0xFFECEBE4))),
                  ),
                ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Small bar per room: "who is drawing power now". Amber = waste detected.
class RoomBars extends StatelessWidget {
  const RoomBars({super.key, required this.rooms, required this.maxWatts});
  final List<dynamic> rooms;
  final double maxWatts;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Container(
        height: 40,
        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF33352D)))),
        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          for (final r in rooms)
            Expanded(
              child: Center(
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 1100),
                    curve: Curves.easeOutBack,
                    width: 26,
                    height: math.max(2, math.min(40, (r['power_w'] as num) / maxWatts * 40)).toDouble(),
                    decoration: BoxDecoration(
                      borderRadius: const BorderRadius.vertical(top: Radius.circular(4), bottom: Radius.circular(1)),
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: r['waste'] == true
                            ? const [Color(0xFF5A4518), WW.amber]
                            : (r['power_w'] as num) > 0
                                ? const [Color(0xFF2E3A1C), WW.lime]
                                : const [Color(0xFF23251F), Color(0xFF3A3C33)],
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ]),
      ),
      const SizedBox(height: 3),
      Row(children: [
        for (final r in rooms)
          Expanded(
            child: Text('${r['name']}',
                textAlign: TextAlign.center, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 9, color: Color(0xFFA9A79D))),
          ),
      ]),
    ]);
  }
}
