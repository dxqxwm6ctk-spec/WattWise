// "حلّل فاتورتك من صورة": take a photo of the electricity bill (camera or gallery)
// and send it to the WattWise server. The server asks Claude to read the numbers
// and the code checks them against the tariff and the meter.
//
// With no API key on the server (or no internet), the card shows a small form
// instead: type kWh, days and the amount by hand. The photo is never saved.

import 'dart:convert';

import 'package:image_picker/image_picker.dart';
import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';
import 'assistant_widgets.dart';

class BillPhotoCard extends StatefulWidget {
  const BillPhotoCard({super.key, required this.api});
  final WattWiseApi api;
  @override
  State<BillPhotoCard> createState() => _BillPhotoCardState();
}

class _BillPhotoCardState extends State<BillPhotoCard> {
  final kwh = TextEditingController();
  final days = TextEditingController();
  final amount = TextEditingController();
  Map<String, dynamic>? status; // {photo: bool, reason_ar: String}
  Map<String, dynamic>? res;
  bool busy = false;
  bool manual = false;
  String msg = '';

  @override
  void initState() {
    super.initState();
    widget.api.billStatus().then((s) {
      if (mounted) setState(() => status = s);
    }).catchError((_) {});
  }

  @override
  void dispose() {
    kwh.dispose();
    days.dispose();
    amount.dispose();
    super.dispose();
  }

  bool get photoOk => status == null || status!['photo'] == true;

  Future<void> send(Future<Map<String, dynamic>> Function() call) async {
    setState(() { busy = true; msg = ''; });
    try {
      final r = await call();
      if (r['needs_manual'] == true) {
        manual = true;
        msg = '${r['message']}';
      } else {
        res = r;
      }
    } catch (e) {
      msg = '$e';
    }
    if (mounted) setState(() => busy = false);
  }

  Future<void> pick(ImageSource source) async {
    // The phone shrinks the photo (max 1600 px, JPEG) so it uploads fast on a hotspot.
    final XFile? file = await ImagePicker().pickImage(source: source, maxWidth: 1600, maxHeight: 1600, imageQuality: 85);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    await send(() => widget.api.billPhoto(base64Encode(bytes)));
  }

  Future<void> sendManual() async {
    final k = double.tryParse(kwh.text.trim());
    if (k == null || k <= 0) {
      setState(() => msg = 'اكتب الكيلوواط ساعة (ك.و.س) من الفاتورة.');
      return;
    }
    await send(() => widget.api.billManual(k, double.tryParse(days.text.trim()), double.tryParse(amount.text.trim())));
  }

  Widget chip(String text) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(color: WW.paper, borderRadius: BorderRadius.circular(999)),
        child: Text(text, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
      );

  @override
  Widget build(BuildContext context) {
    final r = res;
    final bill = r?['bill'] as Map<String, dynamic>?;
    final showForm = manual || !photoOk;
    return WWBox(
      radius: 22,
      padding: 18,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('حلّل فاتورتك من صورة', style: TextStyle(fontSize: 13, color: WW.sub)),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: lineButton(busy ? 'عم نقرأ…' : '📷 صوّر الفاتورة',
              busy || !photoOk ? null : () => pick(ImageSource.camera), border: WW.ink)),
          const SizedBox(width: 8),
          Expanded(child: lineButton('من المعرض', busy || !photoOk ? null : () => pick(ImageSource.gallery), border: WW.ink)),
        ]),
        const SizedBox(height: 6),
        if (!photoOk)
          Text('${status!['reason_ar']}', style: const TextStyle(fontSize: 12.5, height: 1.55, color: WW.pendingText))
        else
          TextButton(
            onPressed: () => setState(() => manual = !manual),
            child: const Text('أو اكتب الأرقام بإيدك', style: TextStyle(color: Color(0xFF5E5C55), decoration: TextDecoration.underline)),
          ),
        if (msg.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(msg, style: const TextStyle(fontSize: 12.5, height: 1.55, color: WW.pendingText)),
        ],
        if (showForm) ...[
          const SizedBox(height: 8),
          TextField(controller: kwh, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: wwField('الاستهلاك (ك.و.س)')),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: TextField(controller: days, keyboardType: TextInputType.number, decoration: wwField('عدد الأيام'))),
            const SizedBox(width: 8),
            Expanded(child: TextField(controller: amount, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: wwField('المبلغ (دينار)'))),
          ]),
          const SizedBox(height: 8),
          darkButton(busy ? 'عم نحلّل…' : 'حلّل الأرقام', busy ? null : sendManual),
        ],
        if (r != null && bill != null) ...[
          const SizedBox(height: 10),
          Wrap(spacing: 6, runSpacing: 6, children: [
            if (bill['kwh'] != null) chip('${(bill['kwh'] as num).round()} ك.و.س'),
            if (bill['days'] != null) chip('${bill['days']} يوم'),
            if (bill['amount_jod'] != null) chip('${(bill['amount_jod'] as num).toStringAsFixed(2)} دينار'),
          ]),
          for (final x in r['explanation'] as List) ...[
            const SizedBox(height: 6),
            Text('$x', style: const TextStyle(fontSize: 14, height: 1.65)),
          ],
          for (final x in r['checks'] as List) ...[
            const SizedBox(height: 8),
            greyBox([Text('$x', style: const TextStyle(fontSize: 12.5, height: 1.55, color: Color(0xFF5E5C55)))]),
          ],
          for (final x in r['ideas'] as List) ...[
            const SizedBox(height: 6),
            Text('• $x', style: const TextStyle(fontSize: 13.5, height: 1.6, color: WW.greenText)),
          ],
          const SizedBox(height: 6),
          Text('${r['note']}', style: const TextStyle(fontSize: 11.5, color: WW.sub)),
        ],
        const SizedBox(height: 8),
        const Text('الصورة بتنقرأ مرة وحدة وما بتنحفظ. بنحتفظ بس بالأرقام.', style: TextStyle(fontSize: 11, color: WW.sub)),
      ]),
    );
  }
}
