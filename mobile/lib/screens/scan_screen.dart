// Scan the QR code shown on the dashboard. It contains the server address,
// for example http://192.168.1.10:8000. Returns that address to the caller.

import 'package:material_ui/material_ui.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool done = false;

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
        appBar: AppBar(title: const Text('امسح الـ QR من لوحة التحكم')),
        body: MobileScanner(onDetect: _onDetect),
      );
}
