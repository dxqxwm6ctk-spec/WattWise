// The splash screen shown while the app finds the server.
//
// It shows only the WattWise mark and name, with a soft "charging" glow on the bolt.
// No status text on purpose: the connection happens silently behind it, and the app
// opens by itself the moment the server answers.
//
// The mark is drawn in code (not an image) with the same shape and size as the native
// splash (assets/branding/splash.svg, made by tool/make_icons.py), so the switch from
// the native splash to this one is invisible.

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import 'theme.dart';

class SplashView extends StatefulWidget {
  const SplashView({super.key});

  @override
  State<SplashView> createState() => _SplashViewState();
}

class _SplashViewState extends State<SplashView> with TickerProviderStateMixin {
  // Fades the name in once, right after the native splash.
  late final AnimationController intro = AnimationController(vsync: this, duration: const Duration(milliseconds: 650))..forward();
  // The bolt's glow, breathing slowly while we wait.
  late final AnimationController glow = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))
    ..repeat(reverse: true);

  @override
  void dispose() {
    intro.dispose();
    glow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final name = CurvedAnimation(parent: intro, curve: Curves.easeOutCubic);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: ColoredBox(
        color: WW.ink,
        child: Center(
          // Same 288 x 288 box as the native splash image.
          child: SizedBox(
            width: 288,
            height: 288,
            child: Stack(clipBehavior: Clip.none, children: [
              // A rounded square ring that breathes out and fades, behind the mark.
              Positioned(
                left: 54,
                top: 54,
                width: 180,
                height: 180,
                child: AnimatedBuilder(
                  animation: glow,
                  builder: (_, _) {
                    final v = Curves.easeInOut.transform(glow.value);
                    return Transform.scale(
                      scale: 1 + 0.18 * v,
                      child: Opacity(
                        opacity: 0.55 * (1 - v),
                        child: DecoratedBox(
                          decoration: BoxDecoration(borderRadius: BorderRadius.circular(54), border: Border.all(color: WW.accent, width: 2.5)),
                        ),
                      ),
                    );
                  },
                ),
              ),
              Positioned.fill(
                child: AnimatedBuilder(
                  animation: glow,
                  builder: (_, _) => CustomPaint(painter: WattWiseMarkPainter(glow: Curves.easeInOut.transform(glow.value))),
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                top: 226,
                child: FadeTransition(
                  opacity: name,
                  child: SlideTransition(
                    position: Tween(begin: const Offset(0, 0.4), end: Offset.zero).animate(name),
                    child: const _Wordmark(),
                  ),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

class _Wordmark extends StatelessWidget {
  const _Wordmark();

  @override
  Widget build(BuildContext context) => const Directionality(
        textDirection: TextDirection.ltr,
        child: Text.rich(
          TextSpan(children: [
            TextSpan(text: 'Watt', style: TextStyle(color: Colors.white)),
            TextSpan(text: 'Wise', style: TextStyle(color: WW.accent)),
          ]),
          textAlign: TextAlign.center,
          style: TextStyle(fontFamily: WW.font, fontSize: 32, fontWeight: FontWeight.w700, letterSpacing: -0.4, decoration: TextDecoration.none),
        ),
      );
}

/// Draws the WattWise mark: a lavender house outline with a lightning bolt inside.
///
/// Coordinates come from the 1024 x 1024 drawing in tool/make_icons.py (splash version:
/// scaled 0.9 around the centre). [glow] from 0 to 1 sets how bright the bolt's halo is.
class WattWiseMarkPainter extends CustomPainter {
  WattWiseMarkPainter({this.glow = 0});
  final double glow;

  static final Path _house = Path()
    ..moveTo(290, 470)
    ..lineTo(512, 280)
    ..lineTo(734, 470)
    ..lineTo(734, 756)
    ..quadraticBezierTo(734, 790, 700, 790)
    ..lineTo(324, 790)
    ..quadraticBezierTo(290, 790, 290, 756)
    ..close();

  static final Path _bolt = Path()
    ..moveTo(556, 382)
    ..lineTo(440, 580)
    ..lineTo(506, 580)
    ..lineTo(474, 712)
    ..lineTo(590, 506)
    ..lineTo(522, 506)
    ..close();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 1024);
    canvas.translate(512, 512);
    canvas.scale(0.9);
    canvas.translate(-512, -512 - 23);

    final stroke = Paint()
      ..color = WW.accent
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round;

    // Halo behind the bolt ("charging").
    if (glow > 0) {
      canvas.drawPath(
        _bolt,
        Paint()
          ..color = WW.accent.withValues(alpha: 0.15 + 0.45 * glow)
          ..maskFilter = MaskFilter.blur(BlurStyle.normal, 18 + 22 * glow),
      );
    }
    canvas.drawPath(_house, stroke..strokeWidth = 52);
    canvas.drawPath(_bolt, Paint()..color = WW.accent);
    canvas.drawPath(_bolt, stroke..strokeWidth = 18);
    canvas.restore();
  }

  @override
  bool shouldRepaint(WattWiseMarkPainter old) => old.glow != glow;
}
