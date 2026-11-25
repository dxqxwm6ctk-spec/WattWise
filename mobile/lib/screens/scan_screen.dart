// Scan the QR code shown on the dashboard. It contains the server address,
// for example http://192.168.1.10:8000. Returns that address to the caller.
// "اكتب العنوان بدلًا من ذلك" closes the scanner with no address, so the
// "where is the server?" sheet opens again with its address field.

import 'package:material_ui/material_ui.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../theme.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> with SingleTickerProviderStateMixin {
  bool done = false;
  late final AnimationController line = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);

  @override
  void dispose() {
    line.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (done) return;
    for (final code in capture.barcodes) {
      final value = code.rawValue?.trim();
      if (value != null && value.startsWith('http')) {
        done = true;
        Navigator.pop(context, value);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF08080B),
        body: SafeArea(
          child: Column(children: [
            Container(
              height: 64,
              color: WW.ink,
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(children: [
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  tooltip: 'رجوع',
                  icon: const Icon(Icons.arrow_back_rounded, size: 20, color: Colors.white),
                ),
                const Text('امسح رمز QR من لوحة التحكم', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: Colors.white)),
              ]),
            ),
            Expanded(
              child: Stack(fit: StackFit.expand, children: [
                MobileScanner(onDetect: _onDetect),
                // Dark veil with a clear square, lavender corners and a moving scan line.
                CustomPaint(painter: _VeilPainter()),
                Center(
                  child: SizedBox(
                    width: 250,
                    height: 250,
                    child: AnimatedBuilder(
                      animation: line,
                      builder: (_, _) => Stack(children: [
                        Positioned(
                          left: 14,
                          right: 14,
                          top: 20 + 200 * Curves.easeInOut.transform(line.value),
                          child: Container(
                            height: 2,
                            decoration: const BoxDecoration(color: WW.accent, boxShadow: [BoxShadow(color: WW.accent, blurRadius: 12)]),
                          ),
                        ),
                      ]),
                    ),
                  ),
                ),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
              child: Column(children: [
                const Text('افتح لوحة التحكم على الحاسوب ووجّه الكاميرا نحو الرمز.',
                    textAlign: TextAlign.center, style: TextStyle(fontSize: 15, height: 1.6, color: Color(0xFFD6DED9))),
                const SizedBox(height: 14),
                OutlinedButton(
                  onPressed: () => Navigator.pop(context),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    minimumSize: const Size(0, 48),
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    side: const BorderSide(color: WW.darkBorder),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
                  ),
                  child: const Text('اكتب العنوان بدلًا من ذلك', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                ),
              ]),
            ),
          ]),
        ),
      );
}

class _VeilPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final hole = RRect.fromRectAndRadius(Rect.fromCenter(center: size.center(Offset.zero), width: 250, height: 250), const Radius.circular(28));
    canvas.drawPath(
      Path.combine(PathOperation.difference, Path()..addRect(Offset.zero & size), Path()..addRRect(hole)),
      Paint()..color = const Color(0x9E080E0B),
    );
    // Corner brackets.
    final p = Paint()
      ..color = WW.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    final r = hole.outerRect;
    const l = 42.0, rad = 28.0;
    for (final (dx, dy) in [(1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)]) {
      final cx = dx > 0 ? r.left : r.right;
      final cy = dy > 0 ? r.top : r.bottom;
      final path = Path()
        ..moveTo(cx, cy + dy * l)
        ..lineTo(cx, cy + dy * rad)
        ..arcToPoint(Offset(cx + dx * rad, cy), radius: const Radius.circular(rad), clockwise: dx * dy > 0)
        ..lineTo(cx + dx * l, cy);
      canvas.drawPath(path, p);
    }
  }

  @override
  bool shouldRepaint(_VeilPainter old) => false;
}
