// Colours from the WattWise design (owner's phone app, light theme).

import 'package:material_ui/material_ui.dart';

class WW {
  static const ink = Color(0xFF1A1B16);
  static const paper = Color(0xFFF3F1EA);
  static const sub = Color(0xFF77756C);
  static const line = Color(0xFFE2DFD4);
  static const lime = Color(0xFFB8F04A);
  static const amber = Color(0xFFF2B544);
  static const red = Color(0xFFD9432E);
  static const darkCard1 = Color(0xFF2A2E22);
  static const darkCard2 = Color(0xFF15160F);
  static const pendingBg = Color(0xFFFFF4D9);
  static const pendingBorder = Color(0xFFE8B23A);
  static const pendingText = Color(0xFF8A5A00);
  static const greenBg = Color(0xFFE6F5C8);
  static const greenText = Color(0xFF4A6418);

  static const mono = TextStyle(fontFamily: 'monospace', fontFeatures: [FontFeature.tabularFigures()]);

  static String fmt(num? v, [int digits = 0]) => v == null ? '—' : v.toStringAsFixed(digits);
}

/// White rounded box used all over the app.
class WWBox extends StatelessWidget {
  const WWBox({super.key, required this.child, this.color = Colors.white, this.padding = 16, this.radius = 18, this.border});
  final Widget child;
  final Color color;
  final double padding;
  final double radius;
  final Color? border;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: EdgeInsets.all(padding),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(radius),
          border: border == null ? null : Border.all(color: border!, width: 1.5),
        ),
        child: child,
      );
}

/// On/off switch styled like the design (knob on the left when on, as in RTL).
class WWToggle extends StatelessWidget {
  const WWToggle({super.key, required this.on, required this.onTap, this.locked = false});
  final bool on;
  final bool locked;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final track = locked ? const Color(0xFFF0C2B8) : on ? WW.ink : const Color(0xFFD8D5CA);
    final knob = locked ? WW.red : on ? WW.lime : Colors.white;
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 52,
        height: 32,
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(color: track, borderRadius: BorderRadius.circular(16)),
        alignment: on ? AlignmentDirectional.centerEnd : AlignmentDirectional.centerStart,
        child: Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            color: knob,
            shape: BoxShape.circle,
            boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 3, offset: Offset(0, 1))],
          ),
        ),
      ),
    );
  }
}
