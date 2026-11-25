// Colours, type and small shared pieces from the WattWise app design
// ("WattWise — App Design" canvas): near-black ink, a soft grey page,
// white cards, and one lavender accent. Font: IBM Plex Sans Arabic (bundled).

import 'package:material_ui/material_ui.dart';

class WW {
  static const font = 'IBMPlexSansArabic';

  // Ink and page.
  static const ink = Color(0xFF0B0B0F);
  static const paper = Color(0xFFF5F5F7); // page background
  static const body = Color(0xFF43434B); // body text on white
  static const sub = Color(0xFF64646E); // secondary text
  static const line = Color(0xFFE6E6EC); // card borders, separators
  static const field = Color(0xFFD4D4DC); // input and outline-button borders
  static const soft = Color(0xFFFAFAFB); // inner boxes on a white card
  static const segBg = Color(0xFFEAEAEF); // segmented control track
  static const neutralBg = Color(0xFFEFEFF3);
  static const muted = Color(0xFFA3A3AD);

  // The lavender accent.
  static const accent = Color(0xFFA9A4F7);
  static const accentLight = Color(0xFFB9B4FF); // numbers on dark cards
  static const accentText = Color(0xFFC9C5FF); // small text on dark cards
  static const accentDeep = Color(0xFF7A73EA); // dots, step bars, rule numbers
  static const accentInk = Color(0xFF4C45C7); // "AI" chip text
  static const accentBg = Color(0xFFEEEDFE); // light chips
  static const accentSel = Color(0xFFE4E2FD); // selected tab / segment
  static const accentSel2 = Color(0xFFF1F0FE); // selected grid tile

  // Dark cards.
  static const dark = Color(0xFF111116);
  static const dark2 = Color(0xFF1E1E26);
  static const darkField = Color(0xFF1B1B22);
  static const darkLine = Color(0xFF2A2A33);
  static const darkBorder = Color(0xFF4A4A55);
  static const darkSub = Color(0xFFB4B4BE);
  static const darkBody = Color(0xFFC8C8D2);
  static const darkChip = Color(0xFF26223F);

  // States.
  static const green = Color(0xFF15803D);
  static const greenBg = Color(0xFFE7F8EE);
  static const greenBright = Color(0xFF4ADE80);
  static const warnBg = Color(0xFFFFF6E5);
  static const warnBorder = Color(0xFFF1D9A6);
  static const warnFg = Color(0xFF8A5300);
  static const pendingBg = Color(0xFFFFF3DB);
  static const pendingFg = Color(0xFF7A4A00);
  static const pendingText = Color(0xFF5E3A00);
  static const red = Color(0xFFB42318);
  static const redBg = Color(0xFFFDECEA);
  static const redBorder = Color(0xFFF3C3BD);
  static const redSoft = Color(0xFFFF9C8A);
  static const blueBg = Color(0xFFE6EEF6);
  static const blueFg = Color(0xFF1F4E79);

  // Numbers line up (same width digits). Same font as the text, as in the design.
  static const mono = TextStyle(fontFeatures: [FontFeature.tabularFigures()]);

  static String fmt(num? v, [int digits = 0]) => v == null ? '—' : v.toStringAsFixed(digits);

  /// 350 W, or 1.24 kW from 1000 W up.
  static String watts(num w) => w >= 1000 ? '${(w / 1000).toStringAsFixed(2)} kW' : '${w.round()} W';
}

/// Rounded card. White with a thin border by default; [dark] gives the near-black card
/// with a faint lavender edge used for the money and agent cards.
class WWBox extends StatelessWidget {
  const WWBox({super.key, required this.child, this.color, this.padding = 16, this.radius = 22, this.border, this.borderWidth = 1, this.dark = false});
  final Widget child;
  final Color? color;
  final double padding;
  final double radius;
  final Color? border;
  final double borderWidth;
  final bool dark;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: EdgeInsets.all(padding),
        decoration: BoxDecoration(
          color: color ?? (dark ? WW.dark : Colors.white),
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(color: border ?? (dark ? WW.accent.withValues(alpha: 0.30) : WW.line), width: borderWidth),
        ),
        child: dark ? DefaultTextStyle.merge(style: const TextStyle(color: Colors.white), child: child) : child,
      );
}

/// Square with rounded corners holding an icon (state cards, alerts, devices).
class IconTile extends StatelessWidget {
  const IconTile({super.key, required this.icon, required this.bg, required this.fg, this.size = 48, this.iconSize = 24, this.radius});
  final IconData icon;
  final Color bg, fg;
  final double size, iconSize;
  final double? radius;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(radius ?? size / 3)),
        alignment: Alignment.center,
        child: Icon(icon, size: iconSize, color: fg),
      );
}

/// Small rounded label, for example "AI", "ضمن الهدف", "مقاس".
class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.bg = WW.accentBg, this.fg = WW.accentInk, this.size = 12, this.icon});
  final String text;
  final Color bg, fg;
  final double size;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[Icon(icon, size: size + 1, color: fg), const SizedBox(width: 4)],
          Text(text, style: TextStyle(fontSize: size, fontWeight: FontWeight.w700, color: fg, height: 1.4)),
        ]),
      );
}

enum BtnKind { primary, outline, ghost, danger, accent, darkGhost }

/// The buttons of the design: black filled, black outline, grey outline, red, lavender,
/// and a grey outline for dark cards.
class WWButton extends StatelessWidget {
  const WWButton(this.label, this.onTap, {super.key, this.kind = BtnKind.primary, this.height = 52, this.icon, this.fontSize = 15, this.radius = 16});
  final String label;
  final VoidCallback? onTap;
  final BtnKind kind;
  final double height;
  final IconData? icon;
  final double fontSize;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final disabled = onTap == null;
    final (Color bg, Color fg, Color? side) = switch (kind) {
      BtnKind.primary => (disabled ? WW.muted : WW.ink, Colors.white, null),
      BtnKind.outline => (Colors.white, WW.ink, WW.ink),
      BtnKind.ghost => (Colors.white, WW.ink, WW.field),
      BtnKind.danger => (WW.red, Colors.white, null),
      BtnKind.accent => (WW.accent, WW.ink, null),
      BtnKind.darkGhost => (Colors.transparent, Colors.white, WW.darkBorder),
    };
    final w = kind == BtnKind.ghost || kind == BtnKind.darkGhost ? FontWeight.w600 : FontWeight.w700;
    return SizedBox(
      height: height,
      child: Material(
        color: bg,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
          side: side == null ? BorderSide.none : BorderSide(color: disabled ? WW.line : side, width: 1.5),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                if (icon != null) ...[Icon(icon, size: 20, color: disabled ? WW.muted : fg), const SizedBox(width: 8)],
                Flexible(
                  child: Text(label,
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      style: TextStyle(fontSize: fontSize, fontWeight: w, color: disabled && kind != BtnKind.primary ? WW.muted : fg)),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

/// Underlined text button ("عرض الطلب من جديد", "حلّل مرة أخرى").
class LinkButton extends StatelessWidget {
  const LinkButton(this.label, this.onTap, {super.key, this.color = WW.ink});
  final String label;
  final VoidCallback? onTap;
  final Color color;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              widthFactor: 1,
              child: Text(label,
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: color, decoration: TextDecoration.underline, decorationColor: color)),
            ),
          ),
        ),
      );
}

/// Grey track with lavender selected segment ("الكل / العاملة فقط", tariff type).
class Segmented extends StatelessWidget {
  const Segmented({super.key, required this.labels, required this.selected, required this.onTap, this.expand = true});
  final List<String> labels;
  final int selected;
  final ValueChanged<int> onTap;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    Widget seg(int i) {
      final on = i == selected;
      final child = GestureDetector(
        onTap: () => onTap(i),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          constraints: const BoxConstraints(minHeight: 40),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          alignment: Alignment.center,
          decoration: BoxDecoration(color: on ? WW.accentSel : Colors.transparent, borderRadius: BorderRadius.circular(11)),
          child: Text(labels[i],
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13.5, fontWeight: on ? FontWeight.w700 : FontWeight.w600, color: on ? WW.ink : WW.body)),
        ),
      );
      return expand ? Expanded(child: child) : child;
    }

    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: WW.segBg, borderRadius: BorderRadius.circular(14)),
      child: Row(mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min, children: [for (var i = 0; i < labels.length; i++) seg(i)]),
    );
  }
}

/// On/off switch from the design. Lavender knob on a deep lavender track when on;
/// grey with a lock for protected devices (they cannot be switched).
class WWToggle extends StatelessWidget {
  const WWToggle({super.key, required this.on, required this.onTap, this.locked = false, this.onDark = false});
  final bool on;
  final bool locked;
  final bool onDark; // sits on a dark card
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final track = locked ? const Color(0xFF4A4F57) : on ? (onDark ? const Color(0xFF3B3870) : WW.ink) : const Color(0xFFD9D9E0);
    final knob = locked ? const Color(0xFFC9CDD3) : on ? (onDark ? WW.accentLight : Colors.white) : Colors.white;
    return Semantics(
      toggled: on,
      button: true,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: SizedBox(
          width: 56,
          height: 44,
          child: Center(
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              curve: Curves.easeOutCubic,
              width: 52,
              height: 30,
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(color: track, borderRadius: BorderRadius.circular(15)),
              alignment: on ? AlignmentDirectional.centerEnd : AlignmentDirectional.centerStart,
              child: Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(color: knob, shape: BoxShape.circle),
                child: locked ? const Icon(Icons.lock_outline, size: 13, color: WW.body) : null,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Radio dot used in the wizards (plug list, rooms, permissions).
class RadioDot extends StatelessWidget {
  const RadioDot({super.key, required this.on});
  final bool on;

  @override
  Widget build(BuildContext context) => Container(
        width: 22,
        height: 22,
        decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: on ? WW.accentDeep : WW.muted, width: 2)),
        alignment: Alignment.center,
        child: Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: on ? WW.accentDeep : Colors.transparent)),
      );
}

/// Text field look: white, grey border, lavender ring when focused.
InputDecoration wwField(String hint, {bool dark = false}) => InputDecoration(
      hintText: hint,
      hintStyle: TextStyle(color: dark ? WW.darkSub : WW.muted, fontSize: 15),
      filled: true,
      fillColor: dark ? WW.darkField : Colors.white,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: dark ? WW.darkBorder : WW.field, width: 1.5)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: WW.accent, width: 2)),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: const BorderSide(color: WW.field, width: 1.5)),
    );

/// Small grey header text over a group ("تنبيهات · 3").
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.count});
  final String text;
  final int? count;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 6, 4, 0),
        child: Text.rich(TextSpan(children: [
          TextSpan(text: text),
          if (count != null) TextSpan(text: ' · $count', style: const TextStyle(color: WW.sub, fontWeight: FontWeight.w500)),
        ]), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
      );
}

/// Bottom sheet confirm, as in the design: handle, red icon, title, text, cancel + red action.
Future<bool> confirmSheet(BuildContext context,
    {required String title, required String body, required String ok, IconData icon = Icons.warning_amber_rounded, String cancel = 'إلغاء'}) async {
  final r = await showModalBottomSheet<bool>(
    context: context,
    backgroundColor: Colors.white,
    barrierColor: const Color(0x8C0E1A15),
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    builder: (c) => SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Center(child: Container(width: 40, height: 5, decoration: BoxDecoration(color: const Color(0xFFDCDCE3), borderRadius: BorderRadius.circular(3)))),
          const SizedBox(height: 14),
          IconTile(icon: icon, bg: WW.redBg, fg: WW.red, size: 52, iconSize: 26),
          const SizedBox(height: 14),
          Text(title, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          Text(body, style: const TextStyle(fontSize: 15, height: 1.65, color: WW.body)),
          const SizedBox(height: 20),
          Row(children: [
            Expanded(child: WWButton(cancel, () => Navigator.pop(c, false), kind: BtnKind.ghost, height: 54, fontSize: 16)),
            const SizedBox(width: 10),
            Expanded(child: WWButton(ok, () => Navigator.pop(c, true), kind: BtnKind.danger, height: 54, fontSize: 16)),
          ]),
        ]),
      ),
    ),
  );
  return r == true;
}

/// Dark message at the bottom (server refusals, "copied", errors).
void wwSnack(BuildContext context, String msg, {IconData icon = Icons.info_outline}) {
  final m = ScaffoldMessenger.maybeOf(context);
  if (m == null) return;
  m.hideCurrentSnackBar();
  m.showSnackBar(SnackBar(
    behavior: SnackBarBehavior.floating,
    backgroundColor: WW.ink,
    margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    content: Row(children: [
      Icon(icon, size: 18, color: WW.accentText),
      const SizedBox(width: 10),
      Expanded(child: Text(msg, style: const TextStyle(fontFamily: WW.font, fontSize: 14, height: 1.5, color: Colors.white))),
    ]),
  ));
}

/// Card with a dashed lavender border (the AI "unusual consumption" note).
class DashedBox extends StatelessWidget {
  const DashedBox({super.key, required this.child, this.color = WW.accent, this.radius = 20, this.padding = 16, this.fill = Colors.white});
  final Widget child;
  final Color color, fill;
  final double radius, padding;

  @override
  Widget build(BuildContext context) => CustomPaint(
        painter: _DashPainter(color, radius, fill),
        child: Padding(padding: EdgeInsets.all(padding), child: child),
      );
}

class _DashPainter extends CustomPainter {
  _DashPainter(this.color, this.radius, this.fill);
  final Color color, fill;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final rr = RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(radius));
    canvas.drawRRect(rr, Paint()..color = fill);
    final path = Path()..addRRect(rr.deflate(0.5));
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    for (final m in path.computeMetrics()) {
      for (double d = 0; d < m.length; d += 7) {
        canvas.drawPath(m.extractPath(d, d + 4), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashPainter o) => o.color != color || o.radius != radius || o.fill != fill;
}

/// Fades in and out forever (the "live" dot next to "الاستهلاك الآن").
class PulseDot extends StatefulWidget {
  const PulseDot({super.key, this.color = WW.accent, this.size = 8});
  final Color color;
  final double size;

  @override
  State<PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<PulseDot> with SingleTickerProviderStateMixin {
  late final AnimationController c = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..repeat(reverse: true);

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween(begin: 1.0, end: 0.3).animate(c),
        child: Container(width: widget.size, height: widget.size, decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle)),
      );
}
