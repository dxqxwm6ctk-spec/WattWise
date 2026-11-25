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
      setState(() => msg = 'أدخل الاستهلاك بالكيلوواط ساعة (ك.و.س) من الفاتورة.');
      return;
    }
    await send(() => widget.api.billManual(k, double.tryParse(days.text.trim()), double.tryParse(amount.text.trim())));
  }

  Widget tile(String label, IconData icon, VoidCallback? onTap, {bool dark = false}) => Expanded(
        child: SizedBox(
          height: 84,
          child: Material(
            color: dark ? WW.ink : Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: dark ? BorderSide.none : const BorderSide(color: WW.field, width: 1.5)),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onTap,
              child: Opacity(
                opacity: onTap == null ? 0.5 : 1,
                child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Icon(icon, size: 24, color: dark ? WW.accent : WW.ink),
                  const SizedBox(height: 6),
                  Text(label, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: dark ? Colors.white : WW.ink)),
                ]),
              ),
            ),
          ),
        ),
      );

  Widget field(String label, TextEditingController c, {bool ltrLabel = false}) => Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, textDirection: ltrLabel ? TextDirection.ltr : null, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: WW.sub)),
          const SizedBox(height: 4),
          TextField(
            controller: c,
            textDirection: TextDirection.ltr,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: wwField(''),
          ),
        ]),
      );

  Widget number(String v, String unit) => Expanded(
        child: Column(children: [
          Text(v, style: WW.mono.copyWith(fontSize: 18, fontWeight: FontWeight.w700)),
          Text(unit, style: const TextStyle(fontSize: 11, color: WW.sub, fontWeight: FontWeight.w500)),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    final r = res;
    final bill = r?['bill'] as Map<String, dynamic>?;
    final showForm = manual || !photoOk;
    final canPhoto = !busy && photoOk;
    return WWBox(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('حلّل فاتورتك من صورة', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Row(children: [
          tile(busy ? 'جارٍ القراءة…' : 'صوّر الفاتورة', Icons.photo_camera_outlined, canPhoto ? () => pick(ImageSource.camera) : null, dark: true),
          const SizedBox(width: 8),
          tile('من المعرض', Icons.image_outlined, canPhoto ? () => pick(ImageSource.gallery) : null),
        ]),
        const SizedBox(height: 6),
        if (!photoOk)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text('${status!['reason_ar']}', style: const TextStyle(fontSize: 12.5, height: 1.55, color: WW.pendingFg)),
          )
        else
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton(
              onPressed: () => setState(() => manual = !manual),
              style: TextButton.styleFrom(foregroundColor: WW.ink, padding: const EdgeInsets.symmetric(horizontal: 2), minimumSize: const Size(0, 40)),
              child: const Text('أو أدخل الأرقام يدويًا', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, decoration: TextDecoration.underline)),
            ),
          ),
        if (msg.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(msg, style: const TextStyle(fontSize: 12.5, height: 1.55, color: WW.pendingFg)),
        ],
        if (showForm) ...[
          const SizedBox(height: 8),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            field('kWh', kwh, ltrLabel: true),
            const SizedBox(width: 8),
            field('أيام', days),
            const SizedBox(width: 8),
            field('المبلغ JD', amount),
          ]),
          const SizedBox(height: 12),
          WWButton(busy ? 'جارٍ التحليل…' : 'حلّل الأرقام', busy ? null : sendManual, kind: BtnKind.outline, height: 48, radius: 14),
        ],
        if (r != null && bill != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            decoration: BoxDecoration(color: WW.soft, borderRadius: BorderRadius.circular(16)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Directionality(
                textDirection: TextDirection.ltr,
                child: Row(children: [
                  if (bill['kwh'] != null) number('${(bill['kwh'] as num).round()}', 'kWh'),
                  if (bill['days'] != null) number('${bill['days']}', 'days'),
                  if (bill['amount_jod'] != null) number((bill['amount_jod'] as num).toStringAsFixed(2), 'JD'),
                ]),
              ),
              const SizedBox(height: 8),
              for (final x in [...r['explanation'] as List, ...r['checks'] as List]) ...[
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('•  ', style: TextStyle(fontSize: 13.5, height: 1.7, color: WW.body)),
                  Expanded(child: Text('$x', style: const TextStyle(fontSize: 13.5, height: 1.7, color: WW.body))),
                ]),
              ],
              for (final x in r['ideas'] as List) ...[
                const SizedBox(height: 6),
                Text('• $x', style: const TextStyle(fontSize: 13.5, height: 1.6, color: WW.green)),
              ],
              const SizedBox(height: 6),
              Text('${r['note']}', style: const TextStyle(fontSize: 11.5, color: WW.sub)),
            ]),
          ),
        ],
        const SizedBox(height: 12),
        const Row(children: [
          Icon(Icons.lock_outline_rounded, size: 14, color: WW.sub),
          SizedBox(width: 6),
          Expanded(child: Text('تُقرأ الصورة مرة واحدة ولا تُحفظ أبدًا، ونحتفظ بالأرقام فقط.', style: TextStyle(fontSize: 12, color: WW.sub))),
        ]),
      ]),
    );
  }
}
