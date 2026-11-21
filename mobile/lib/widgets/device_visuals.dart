// Animated device icons and live numbers for the phone app.
//
// The idea: you see at a glance what is running.
//   fan / AC   -> blades spin, cold air flows
//   lamp       -> the bulb glows and shines
//   heater     -> heat waves rise
//   TV / PC    -> the screen lights up
//   washer     -> the drum turns
//   router     -> Wi-Fi waves pulse
//   protected  -> a calm shield pulse (fridge, fire alarm: always on, T2)
//
// Everything is drawn in code (CustomPainter), so no image files are needed.
// When a device turns on or off the animation speeds up or slows down
// smoothly instead of jumping. When it is off and still, the ticker stops,
// so it costs no battery.

import 'dart:math' as math;

import 'package:flutter/scheduler.dart';
import 'package:material_ui/material_ui.dart';

import '../theme.dart';

/// Accent colour for each kind of device when it is on.
Color deviceAccent(String kind) => switch (kind) {
      'fan' || 'ac' => const Color(0xFF7FD6FF),
      'light' || 'emergency_light' => const Color(0xFFFFD45C),
      'heater' => const Color(0xFFFF7A3D),
      'tv' => const Color(0xFF9B8CFF),
      'washer' => const Color(0xFF6FE3D0),
      'fridge' || 'fire_alarm' || 'medical' => const Color(0xFFFF8A70),
      _ => WW.lime,
    };

/// Short Arabic label that matches the animation (shown under the name).
String runningWord(String kind) => switch (kind) {
      'fan' => 'تدور',
      'ac' => 'يبرّد',
      'light' || 'emergency_light' => 'مضاءة',
      'heater' => 'يسخّن',
      'washer' => 'تغسل',
      _ => 'يعمل',
    };

/// The animated picture of one device.
class DeviceIcon extends StatefulWidget {
  const DeviceIcon({super.key, required this.kind, required this.on, this.size = 56, this.locked = false, this.dark = false});
  final String kind;
  final bool on;
  final bool locked; // T2: protected, always on
  final double size;
  final bool dark; // drawn on a dark card

  @override
  State<DeviceIcon> createState() => _DeviceIconState();
}

class _DeviceIconState extends State<DeviceIcon> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  Duration _last = Duration.zero;
  double _t = 0; // seconds since start (for waves and pulses)
  double _angle = 0; // integrated rotation (fan, washer)
  late double _level; // 0 = fully off, 1 = fully on (eases between)

  bool get _target => widget.on || widget.locked;

  @override
  void initState() {
    super.initState();
    _level = _target ? 1 : 0;
    _ticker = createTicker(_tick);
    if (_target) _ticker.start();
  }

  @override
  void didUpdateWidget(DeviceIcon old) {
    super.didUpdateWidget(old);
    if (_target && !_ticker.isActive) {
      _last = Duration.zero;
      _ticker.start();
    }
  }

  void _tick(Duration elapsed) {
    final dt = _last == Duration.zero ? 0.016 : (elapsed - _last).inMicroseconds / 1e6;
    _last = elapsed;
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    final goal = _target ? 1.0 : 0.0;
    // Ease towards the goal: about 0.8 s to spin up, a bit longer to slow down.
    final rate = goal > _level ? 1.4 : 0.9;
    _level += (goal - _level) * math.min(1, dt * rate * 2.2);
    if ((goal - _level).abs() < 0.004) _level = goal;
    if (!reduce) {
      _t += dt;
      _angle += dt * _level * (widget.kind == 'washer' ? 4.0 : 9.0);
    }
    setState(() {});
    if (!_target && _level == 0) _ticker.stop(); // fully off: stop drawing
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: CustomPaint(
        size: Size.square(widget.size),
        painter: _DevicePainter(
          kind: widget.kind,
          level: _level,
          t: _t,
          angle: _angle,
          locked: widget.locked,
          dark: widget.dark,
        ),
      ),
    );
  }
}

class _DevicePainter extends CustomPainter {
  _DevicePainter({required this.kind, required this.level, required this.t, required this.angle, required this.locked, required this.dark});
  final String kind;
  final double level, t, angle;
  final bool locked, dark;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width;
    final c = Offset(s / 2, s / 2);
    final accent = deviceAccent(kind);
    final offFg = dark ? const Color(0xFF6E6C63) : const Color(0xFF9A988E);
    final offBg = dark ? const Color(0xFF2A2C25) : const Color(0xFFEDEBE3);
    final onBg = Color.lerp(const Color(0xFF23251F), accent, 0.16)!;
    final fg = Color.lerp(offFg, accent, level)!;

    // Glow behind the disc when on.
    if (level > 0.01) {
      final pulse = 0.85 + 0.15 * math.sin(t * 2.4);
      canvas.drawCircle(c, s * 0.46,
          Paint()..color = accent.withValues(alpha: 0.38 * level * pulse)..maskFilter = MaskFilter.blur(BlurStyle.normal, s * 0.22));
    }
    canvas.drawCircle(c, s / 2, Paint()..color = Color.lerp(offBg, onBg, level)!);

    canvas.save();
    canvas.clipPath(Path()..addOval(Rect.fromCircle(center: c, radius: s / 2)));
    switch (kind) {
      case 'fan':
        _fan(canvas, s, c, fg);
      case 'ac':
        _ac(canvas, s, c, fg, accent);
      case 'light' || 'emergency_light':
        _bulb(canvas, s, c, fg, accent);
      case 'heater':
        _heater(canvas, s, c, fg, accent);
      case 'tv' || 'pc':
        _screen(canvas, s, c, fg, accent);
      case 'washer':
        _washer(canvas, s, c, fg);
      case 'router':
        _router(canvas, s, c, fg);
      case 'fridge' || 'fire_alarm' || 'medical':
        _shield(canvas, s, c, fg, accent);
      default:
        _plug(canvas, s, c, fg, accent);
    }
    canvas.restore();
  }

  Paint _stroke(Color col, double w) => Paint()
    ..color = col
    ..style = PaintingStyle.stroke
    ..strokeWidth = w
    ..strokeCap = StrokeCap.round
    ..strokeJoin = StrokeJoin.round;

  // Three blades that spin. The motion blur ring shows speed.
  void _fan(Canvas canvas, double s, Offset c, Color fg) {
    final r = s * 0.32;
    if (level > 0.2) {
      canvas.drawCircle(c, r * 0.95, Paint()..color = fg.withValues(alpha: 0.12 * level));
    }
    canvas.save();
    canvas.translate(c.dx, c.dy);
    canvas.rotate(angle);
    for (var i = 0; i < 3; i++) {
      canvas.save();
      canvas.rotate(i * 2 * math.pi / 3);
      final blade = Path()
        ..moveTo(0, 0)
        ..cubicTo(r * 0.25, -r * 0.35, r * 0.95, -r * 0.45, r, -r * 0.05)
        ..cubicTo(r * 0.9, r * 0.25, r * 0.35, r * 0.2, 0, 0)
        ..close();
      canvas.drawPath(blade, Paint()..color = fg);
      canvas.restore();
    }
    canvas.restore();
    canvas.drawCircle(c, s * 0.07, Paint()..color = dark || level > 0.5 ? const Color(0xFF1A1B16) : Colors.white);
    canvas.drawCircle(c, s * 0.07, _stroke(fg, s * 0.03));
  }

  // Wall unit with cold air lines flowing down.
  void _ac(Canvas canvas, double s, Offset c, Color fg, Color accent) {
    final body = RRect.fromRectAndRadius(Rect.fromCenter(center: c.translate(0, -s * 0.12), width: s * 0.6, height: s * 0.22), Radius.circular(s * 0.06));
    canvas.drawRRect(body, _stroke(fg, s * 0.045));
    canvas.drawLine(c.translate(-s * 0.2, -s * 0.06), c.translate(s * 0.2, -s * 0.06), _stroke(fg, s * 0.03));
    canvas.drawCircle(c.translate(s * 0.2, -s * 0.16), s * 0.018, Paint()..color = level > 0.5 ? WW.lime : fg);
    if (level < 0.02) return;
    for (var i = 0; i < 3; i++) {
      final x = c.dx + (i - 1) * s * 0.16;
      final phase = (t * 0.9 + i * 0.33) % 1.0;
      final y0 = c.dy + s * 0.04 + phase * s * 0.18;
      final alpha = (1 - phase) * level;
      final p = Path()..moveTo(x, y0);
      for (var k = 1; k <= 6; k++) {
        final y = y0 + k * s * 0.025;
        p.lineTo(x + math.sin(k * 1.2 + t * 4 + i) * s * 0.025, y);
      }
      canvas.drawPath(p, _stroke(accent.withValues(alpha: alpha), s * 0.035));
    }
  }

  // Bulb that fills with warm light and sends out rays.
  void _bulb(Canvas canvas, double s, Offset c, Color fg, Color accent) {
    final bc = c.translate(0, -s * 0.05);
    final r = s * 0.17;
    if (level > 0.01) {
      canvas.drawCircle(bc, r * 1.9, Paint()..color = accent.withValues(alpha: 0.30 * level)..maskFilter = MaskFilter.blur(BlurStyle.normal, s * 0.12));
      final grow = 0.75 + 0.25 * math.sin(t * 3);
      for (var i = 0; i < 8; i++) {
        final a = i * math.pi / 4 + t * 0.4;
        final p1 = bc + Offset(math.cos(a), math.sin(a)) * (r * 1.45);
        final p2 = bc + Offset(math.cos(a), math.sin(a)) * (r * (1.45 + 0.55 * grow * level));
        canvas.drawLine(p1, p2, _stroke(accent.withValues(alpha: 0.9 * level), s * 0.03));
      }
    }
    canvas.drawCircle(bc, r, Paint()..color = Color.lerp(Colors.transparent, accent, level)!);
    canvas.drawCircle(bc, r, _stroke(fg, s * 0.04));
    final base = Rect.fromCenter(center: bc.translate(0, r * 1.45), width: r * 0.95, height: r * 0.7);
    canvas.drawRRect(RRect.fromRectAndRadius(base, Radius.circular(s * 0.02)), _stroke(fg, s * 0.04));
  }

  // Radiator bars that turn red-hot, with heat waves rising.
  void _heater(Canvas canvas, double s, Offset c, Color fg, Color accent) {
    final hot = Color.lerp(fg, const Color(0xFFFF4F2A), level * (0.8 + 0.2 * math.sin(t * 5)))!;
    for (var i = 0; i < 4; i++) {
      final x = c.dx + (i - 1.5) * s * 0.11;
      final r = RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(x, c.dy + s * 0.14), width: s * 0.07, height: s * 0.22), Radius.circular(s * 0.035));
      canvas.drawRRect(r, Paint()..color = hot);
    }
    canvas.drawLine(c.translate(-s * 0.22, s * 0.27), c.translate(s * 0.22, s * 0.27), _stroke(fg, s * 0.03));
    if (level < 0.02) return;
    for (var i = 0; i < 3; i++) {
      final x = c.dx + (i - 1) * s * 0.14;
      final phase = (t * 0.7 + i * 0.3) % 1.0;
      final yBottom = c.dy - s * 0.0 - phase * s * 0.12;
      final p = Path()..moveTo(x, yBottom);
      for (var k = 1; k <= 8; k++) {
        p.lineTo(x + math.sin(k * 0.9 - t * 5 + i) * s * 0.03, yBottom - k * s * 0.025);
      }
      final alpha = math.sin(phase * math.pi) * level;
      canvas.drawPath(p, _stroke(accent.withValues(alpha: alpha), s * 0.035));
    }
  }

  // Screen that lights up with moving colours (TV) or typing lines (PC).
  void _screen(Canvas canvas, double s, Offset c, Color fg, Color accent) {
    final rect = Rect.fromCenter(center: c.translate(0, -s * 0.04), width: s * 0.56, height: s * 0.36);
    final rr = RRect.fromRectAndRadius(rect, Radius.circular(s * 0.04));
    if (level > 0.01) {
      final shader = LinearGradient(
        begin: Alignment(math.cos(t), math.sin(t)),
        end: Alignment(-math.cos(t), -math.sin(t)),
        colors: [accent.withValues(alpha: level), WW.lime.withValues(alpha: 0.6 * level)],
      ).createShader(rect);
      canvas.drawRRect(rr, Paint()..shader = shader);
      if (kind == 'pc') {
        final lines = ((t * 2) % 4).floor() + 1;
        for (var i = 0; i < lines; i++) {
          final w = rect.width * (0.3 + 0.12 * ((i * 7) % 4));
          canvas.drawLine(Offset(rect.left + s * 0.06, rect.top + s * 0.07 + i * s * 0.065),
              Offset(rect.left + s * 0.06 + w, rect.top + s * 0.07 + i * s * 0.065), _stroke(const Color(0xFF1A1B16).withValues(alpha: 0.7 * level), s * 0.03));
        }
      }
    }
    canvas.drawRRect(rr, _stroke(fg, s * 0.04));
    canvas.drawLine(c.translate(-s * 0.1, s * 0.22), c.translate(s * 0.1, s * 0.22), _stroke(fg, s * 0.04));
  }

  // Washing machine with a turning drum.
  void _washer(Canvas canvas, double s, Offset c, Color fg) {
    final body = RRect.fromRectAndRadius(Rect.fromCenter(center: c, width: s * 0.5, height: s * 0.56), Radius.circular(s * 0.06));
    canvas.drawRRect(body, _stroke(fg, s * 0.04));
    final dc = c.translate(0, s * 0.05);
    canvas.drawCircle(dc, s * 0.15, _stroke(fg, s * 0.035));
    canvas.save();
    canvas.translate(dc.dx, dc.dy);
    canvas.rotate(angle);
    for (var i = 0; i < 3; i++) {
      canvas.drawArc(Rect.fromCircle(center: Offset.zero, radius: s * 0.08), i * 2 * math.pi / 3, 1.2, false, _stroke(fg.withValues(alpha: 0.4 + 0.6 * level), s * 0.03));
    }
    canvas.restore();
    canvas.drawCircle(c.translate(-s * 0.15, -s * 0.2), s * 0.02, Paint()..color = fg);
  }

  // Router with Wi-Fi arcs pulsing one after another.
  void _router(Canvas canvas, double s, Offset c, Color fg) {
    final box = RRect.fromRectAndRadius(Rect.fromCenter(center: c.translate(0, s * 0.17), width: s * 0.5, height: s * 0.14), Radius.circular(s * 0.04));
    canvas.drawRRect(box, _stroke(fg, s * 0.04));
    final o = c.translate(0, s * 0.05);
    for (var i = 0; i < 3; i++) {
      final on = ((t * 2.5).floor() % 4) > i;
      final alpha = level < 0.02 ? 0.6 : (on ? 1.0 : 0.25);
      canvas.drawArc(Rect.fromCircle(center: o, radius: s * (0.09 + i * 0.08)), math.pi * 1.25, math.pi * 0.5, false,
          _stroke(fg.withValues(alpha: alpha), s * 0.04));
    }
  }

  // Protected device: shield with a slow expanding ring.
  void _shield(Canvas canvas, double s, Offset c, Color fg, Color accent) {
    final phase = (t * 0.6) % 1.0;
    canvas.drawCircle(c, s * (0.18 + phase * 0.3), _stroke(accent.withValues(alpha: (1 - phase) * 0.6 * level), s * 0.03));
    final p = Path()
      ..moveTo(c.dx, c.dy - s * 0.22)
      ..lineTo(c.dx + s * 0.17, c.dy - s * 0.14)
      ..quadraticBezierTo(c.dx + s * 0.17, c.dy + s * 0.12, c.dx, c.dy + s * 0.22)
      ..quadraticBezierTo(c.dx - s * 0.17, c.dy + s * 0.12, c.dx - s * 0.17, c.dy - s * 0.14)
      ..close();
    canvas.drawPath(p, _stroke(fg, s * 0.04));
    canvas.drawPath(Path()..moveTo(c.dx - s * 0.07, c.dy)..lineTo(c.dx - s * 0.01, c.dy + s * 0.06)..lineTo(c.dx + s * 0.08, c.dy - s * 0.05),
        _stroke(fg, s * 0.04));
  }

  // Anything else: a plug with a lightning bolt that flickers.
  void _plug(Canvas canvas, double s, Offset c, Color fg, Color accent) {
    final bolt = Path()
      ..moveTo(c.dx + s * 0.04, c.dy - s * 0.24)
      ..lineTo(c.dx - s * 0.12, c.dy + s * 0.03)
      ..lineTo(c.dx - s * 0.01, c.dy + s * 0.03)
      ..lineTo(c.dx - s * 0.05, c.dy + s * 0.24)
      ..lineTo(c.dx + s * 0.12, c.dy - s * 0.04)
      ..lineTo(c.dx + s * 0.01, c.dy - s * 0.04)
      ..close();
    final flicker = level * (0.75 + 0.25 * math.sin(t * 7));
    canvas.drawPath(bolt, Paint()..color = Color.lerp(Colors.transparent, accent, flicker)!);
    canvas.drawPath(bolt, _stroke(fg, s * 0.035));
  }

  @override
  bool shouldRepaint(_DevicePainter o) =>
      o.level != level || o.t != t || o.angle != angle || o.kind != kind || o.locked != locked || o.dark != dark;
}

/// A number that counts smoothly to its new value (for live watts).
class AnimatedWatts extends StatelessWidget {
  const AnimatedWatts({super.key, required this.watts, this.style, this.unitStyle});
  final num watts;
  final TextStyle? style;
  final TextStyle? unitStyle;

  @override
  Widget build(BuildContext context) {
    final kw = watts >= 1000;
    return TweenAnimationBuilder<double>(
      tween: Tween(end: watts.toDouble()),
      duration: const Duration(milliseconds: 900),
      curve: Curves.easeOutCubic,
      builder: (context, v, _) => Text.rich(
        TextSpan(children: [
          TextSpan(text: kw ? (v / 1000).toStringAsFixed(2) : v.round().toString(), style: style),
          TextSpan(text: kw ? ' kW' : ' W', style: unitStyle ?? style?.copyWith(fontSize: (style?.fontSize ?? 14) * 0.55)),
        ]),
        textDirection: TextDirection.ltr,
        style: WW.mono,
      ),
    );
  }
}

/// Small dot with a ring that keeps pulsing: "this is live".
class LiveDot extends StatefulWidget {
  const LiveDot({super.key, this.color = WW.lime, this.size = 8});
  final Color color;
  final double size;

  @override
  State<LiveDot> createState() => _LiveDotState();
}

class _LiveDotState extends State<LiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.size;
    return SizedBox(
      width: s * 2.4,
      height: s * 2.4,
      child: AnimatedBuilder(
        animation: _c,
        builder: (context, _) => Stack(alignment: Alignment.center, children: [
          Container(
            width: s * (1 + 1.4 * _c.value),
            height: s * (1 + 1.4 * _c.value),
            decoration: BoxDecoration(shape: BoxShape.circle, color: widget.color.withValues(alpha: 0.45 * (1 - _c.value))),
          ),
          Container(width: s, height: s, decoration: BoxDecoration(shape: BoxShape.circle, color: widget.color)),
        ]),
      ),
    );
  }
}

/// Grows and fades in the first time it is built (a chip that just appeared).
class PopIn extends StatelessWidget {
  const PopIn({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 450),
        curve: Curves.easeOutBack,
        builder: (context, v, child) => Opacity(opacity: v.clamp(0.0, 1.0), child: Transform.scale(scale: 0.6 + 0.4 * v, child: child)),
        child: child,
      );
}

/// Dark card: "running now" with the total watts and a strip of running devices.
/// Used on the home tab and at the top of the devices tab.
class RunningNowCard extends StatelessWidget {
  const RunningNowCard({super.key, required this.devices, this.pendingDeviceId});
  final List<dynamic> devices;
  final String? pendingDeviceId;

  @override
  Widget build(BuildContext context) {
    final running = devices.where((d) => d['is_on'] == true).toList();
    // Biggest loads first: the ones that matter for the bill.
    running.sort((a, b) => (b['est_w'] as num).compareTo(a['est_w'] as num));
    final total = running.fold<num>(0, (sum, d) => sum + (d['est_w'] as num));

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        gradient: const LinearGradient(begin: Alignment.topRight, end: Alignment.bottomLeft, colors: [WW.darkCard1, WW.darkCard2]),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          const LiveDot(),
          const SizedBox(width: 4),
          const Text('يعمل الآن', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: WW.paper)),
          const SizedBox(width: 8),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            transitionBuilder: (child, a) => ScaleTransition(scale: a, child: child),
            child: Container(
              key: ValueKey(running.length),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(color: const Color(0xFF33352D), borderRadius: BorderRadius.circular(10)),
              child: Text('${running.length} من ${devices.length}', style: const TextStyle(fontSize: 11.5, color: Color(0xFFC9C7BC))),
            ),
          ),
          const Spacer(),
          AnimatedWatts(
            watts: total,
            style: WW.mono.copyWith(fontSize: 20, fontWeight: FontWeight.w600, color: WW.lime),
            unitStyle: WW.mono.copyWith(fontSize: 11, color: const Color(0xFFA9A79D)),
          ),
        ]),
        const SizedBox(height: 10),
        AnimatedSize(
          duration: const Duration(milliseconds: 350),
          curve: Curves.easeOutCubic,
          child: running.isEmpty
              ? const Padding(
                  padding: EdgeInsets.symmetric(vertical: 10),
                  child: Text('كل الأجهزة مطفأة 🌙', style: TextStyle(fontSize: 13, color: Color(0xFFA9A79D))),
                )
              : SizedBox(
                  height: 92,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: running.length,
                    separatorBuilder: (_, _) => const SizedBox(width: 8),
                    itemBuilder: (context, i) {
                      final d = running[i];
                      return PopIn(
                        key: ValueKey(d['id']),
                        child: _RunningChip(d: d, pending: d['id'] == pendingDeviceId),
                      );
                    },
                  ),
                ),
        ),
      ]),
    );
  }
}

class _RunningChip extends StatelessWidget {
  const _RunningChip({required this.d, required this.pending});
  final dynamic d;
  final bool pending;

  @override
  Widget build(BuildContext context) {
    final kind = '${d['kind']}';
    return Container(
      width: 84,
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      decoration: BoxDecoration(
        color: const Color(0xFF23251F),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: pending ? WW.amber : const Color(0xFF33352D), width: pending ? 1.5 : 1),
      ),
      child: Column(children: [
        DeviceIcon(kind: kind, on: true, size: 38, locked: d['tier'] == 'T2', dark: true),
        const SizedBox(height: 4),
        Text('${d['name']}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11, color: WW.paper)),
        AnimatedWatts(
          watts: d['est_w'] as num,
          style: WW.mono.copyWith(fontSize: 11, color: deviceAccent(kind)),
          unitStyle: WW.mono.copyWith(fontSize: 9, color: const Color(0xFF8E8C82)),
        ),
      ]),
    );
  }
}
