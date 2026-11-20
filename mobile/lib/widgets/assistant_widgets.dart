// Talking to WattWise in plain Arabic: the command card (home tab), and the goal,
// "why is my bill like this?" and weekly report cards (bill tab).
//
// The server understands the words and the Policy Guard checks every action.
// Nothing runs until the owner presses "إيه، نفّذ".

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';

InputDecoration wwField(String hint) => InputDecoration(
      hintText: hint,
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: const BorderSide(color: WW.line, width: 1.5)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: const BorderSide(color: WW.ink, width: 1.5)),
    );

Widget darkButton(String label, VoidCallback? onTap, {double height = 50}) => SizedBox(
      height: height,
      child: FilledButton(
        style: FilledButton.styleFrom(backgroundColor: WW.ink, foregroundColor: WW.paper, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
        onPressed: onTap,
        child: Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
      ),
    );

Widget lineButton(String label, VoidCallback? onTap, {double height = 50, Color border = const Color(0xFFD8D5CA)}) => SizedBox(
      height: height,
      child: OutlinedButton(
        style: OutlinedButton.styleFrom(foregroundColor: WW.ink, side: BorderSide(color: border, width: 1.5), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
        onPressed: onTap,
        child: Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
      ),
    );

Widget greyBox(List<Widget> children) => Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(color: WW.paper, borderRadius: BorderRadius.circular(12)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );

void showError(BuildContext context, Object e) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e', textDirection: TextDirection.rtl)));

// ---------- command card (home tab) ----------

class CommandCard extends StatefulWidget {
  const CommandCard({super.key, required this.api});
  final WattWiseApi api;
  @override
  State<CommandCard> createState() => _CommandCardState();
}

class _CommandCardState extends State<CommandCard> {
  final text = TextEditingController();
  Map<String, dynamic>? res;
  bool busy = false;
  String msg = '';

  Future<void> parse() async {
    if (text.text.trim().isEmpty || busy) return;
    setState(() { busy = true; msg = ''; });
    try {
      res = await widget.api.parseCommand(text.text);
    } catch (e) {
      if (mounted) showError(context, e);
    }
    if (mounted) setState(() => busy = false);
  }

  Future<void> runIt() async {
    try {
      final r = await widget.api.runCommand(text.text);
      final done = (r['done'] as List).cast<String>();
      setState(() { res = null; text.clear(); msg = done.isEmpty ? 'ما تنفّذ إشي.' : 'تم: ${done.join('، ')}'; });
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final r = res;
    final items = (r?['items'] as List?) ?? const [];
    return WWBox(
      radius: 22,
      padding: 14,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(child: TextField(controller: text, decoration: wwField('قول: طفّي مكيّف النوم'), onSubmitted: (_) => parse())),
          const SizedBox(width: 8),
          darkButton(busy ? '…' : 'نفّذ', parse, height: 50),
        ]),
        if (r != null) ...[
          const SizedBox(height: 10),
          Text('${r['clarify'] ?? r['reply']}', style: const TextStyle(fontSize: 14, height: 1.6)),
          for (final i in items) ...[
            const SizedBox(height: 8),
            greyBox([
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(i['ok'] == true ? '✓ ' : '✕ ',
                    style: TextStyle(fontWeight: FontWeight.w700, color: i['ok'] == true ? WW.greenText : const Color(0xFFA23A26))),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${i['label']}', style: const TextStyle(fontSize: 14)),
                    if ('${i['why']}'.isNotEmpty) Text('${i['why']}', style: const TextStyle(fontSize: 12, color: WW.sub)),
                  ]),
                ),
              ]),
            ]),
          ],
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: lineButton('لا', () => setState(() => res = null), height: 48)),
            if (items.any((i) => i['ok'] == true)) ...[
              const SizedBox(width: 8),
              Expanded(flex: 14, child: darkButton('إيه، نفّذ', runIt, height: 48)),
            ],
          ]),
        ],
        if (msg.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(msg, style: const TextStyle(fontSize: 13.5, color: WW.greenText, fontWeight: FontWeight.w600)),
        ],
      ]),
    );
  }
}

// ---------- goal, why and report (bill tab) ----------

class GoalCard extends StatefulWidget {
  const GoalCard({super.key, required this.st, required this.api, required this.run});
  final Map<String, dynamic> st;
  final WattWiseApi api;
  final Future<void> Function(Future<void> Function()) run;
  @override
  State<GoalCard> createState() => _GoalCardState();
}

class _GoalCardState extends State<GoalCard> {
  final text = TextEditingController(text: 'خلّي فاتورة هالشهر تحت 30 دينار بدون ما تزعّج حدا بالبيت');

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final goal = widget.st['goal'] as Map<String, dynamic>?;
    final plan = widget.st['plan'] as Map<String, dynamic>?;
    final steps = (plan?['steps'] as List?) ?? const [];
    final tags = (plan?['tags'] as List?) ?? const [];
    return WWBox(
      radius: 22,
      padding: 18,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('هدفك بكلامك', style: TextStyle(fontSize: 13, color: WW.sub)),
        if (goal != null) ...[
          const SizedBox(height: 8),
          Text('«${goal['text']}»', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, height: 1.5)),
        ],
        const SizedBox(height: 10),
        TextField(controller: text, decoration: wwField('مثلاً: بدي الفاتورة تحت ٢٥ دينار')),
        const SizedBox(height: 10),
        darkButton(goal == null ? 'حوّله لخطة' : 'غيّر الهدف', () => widget.run(() => widget.api.setGoal(text.text))),
        if (goal != null && steps.isNotEmpty) ...[
          const SizedBox(height: 10),
          if ('${plan?['summary'] ?? ''}'.isNotEmpty) Text('${plan!['summary']}', style: const TextStyle(fontSize: 14, height: 1.65)),
          for (var i = 0; i < steps.length; i++) ...[
            const SizedBox(height: 8),
            greyBox([
              Text(i < tags.length && tags[i] == 'T1' ? 'T1 · بموافقتك' : 'T0 · تلقائي',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: i < tags.length && tags[i] == 'T1' ? WW.pendingText : WW.greenText)),
              Text('${steps[i]}', style: const TextStyle(fontSize: 13.5, height: 1.55)),
            ]),
          ],
        ],
      ]),
    );
  }
}

class WhyCard extends StatefulWidget {
  const WhyCard({super.key, required this.api});
  final WattWiseApi api;
  @override
  State<WhyCard> createState() => _WhyCardState();
}

class _WhyCardState extends State<WhyCard> {
  Map<String, dynamic>? res;
  bool busy = false;

  Future<void> ask() async {
    setState(() => busy = true);
    try {
      res = await widget.api.why();
    } catch (e) {
      if (mounted) showError(context, e);
    }
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final w = res;
    return WWBox(
      radius: 22,
      padding: 18,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        lineButton(busy ? 'عم نحلّل…' : w == null ? 'ليش الفاتورة هيك؟' : 'حلّل من جديد', ask, border: WW.ink),
        if (w != null) ...[
          const SizedBox(height: 10),
          Text('${w['headline']}', style: const TextStyle(fontSize: 14, height: 1.65)),
          for (final c in w['causes'] as List) ...[
            const SizedBox(height: 8),
            greyBox([
              Text('${c['what']}', style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
              Text('${c['evidence']}', style: const TextStyle(fontSize: 12.5, height: 1.55, color: Color(0xFF5E5C55))),
            ]),
          ],
          const SizedBox(height: 8),
          Text('${w['action']}', style: const TextStyle(fontSize: 13.5, height: 1.6, color: WW.greenText)),
          Text('${w['note']}', style: const TextStyle(fontSize: 11.5, color: WW.sub)),
        ],
      ]),
    );
  }
}

class ReportCard extends StatefulWidget {
  const ReportCard({super.key, required this.api});
  final WattWiseApi api;
  @override
  State<ReportCard> createState() => _ReportCardState();
}

class _ReportCardState extends State<ReportCard> {
  String text = '';
  bool busy = false;
  String saved = '';

  Future<void> make() async {
    setState(() { busy = true; saved = ''; });
    try {
      text = await widget.api.weeklyReport();
    } catch (e) {
      if (mounted) showError(context, e);
    }
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return WWBox(
      radius: 22,
      padding: 18,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        lineButton(busy ? 'عم نجهّز…' : text.isEmpty ? 'جهّز التقرير الأسبوعي' : 'جهّز تقرير جديد', make, border: WW.ink),
        if (text.isNotEmpty) ...[
          const SizedBox(height: 10),
          Container(
            constraints: const BoxConstraints(maxHeight: 220),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: WW.paper, borderRadius: BorderRadius.circular(12)),
            child: SingleChildScrollView(child: SelectableText(text, style: const TextStyle(fontSize: 12.5, height: 1.75))),
          ),
          const SizedBox(height: 10),
          // The file download lives on the dashboard; on the phone we copy the text to share it.
          darkButton('انسخ التقرير', () async {
            await Clipboard.setData(ClipboardData(text: text));
            setState(() => saved = 'انسخ ✓ بتقدر تلصقه برسالة أو ملف.');
          }, height: 46),
          if (saved.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Text(saved, style: const TextStyle(fontSize: 12, color: WW.sub))),
        ],
      ]),
    );
  }
}
