// Full-screen frame shared by the two "add a device" wizards:
// a white header (close, title, "الخطوة 2 من 3", step bars), the step, and a footer
// with back/cancel and next. Plus the tiles both wizards use.

import 'package:material_ui/material_ui.dart';

import '../api.dart';
import '../theme.dart';

/// Opens a wizard on its own page. It keeps getting the live state every second.
Future<void> openWizard(BuildContext context, Map<String, dynamic> st, Widget Function(Map<String, dynamic> st) build) =>
    Navigator.of(context).push(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => ValueListenableBuilder<Map<String, dynamic>?>(
        valueListenable: liveState,
        builder: (_, s, _) => build(s ?? st),
      ),
    ));

/// Icon for each device kind (wizard tiles, schedule detail).
IconData kindIcon(String kind) => switch (kind) {
      'ac' => Icons.ac_unit_rounded,
      'light' || 'emergency_light' => Icons.lightbulb_outline_rounded,
      'heater' => Icons.hot_tub_outlined,
      'tv' => Icons.tv_rounded,
      'washer' => Icons.local_laundry_service_outlined,
      'pc' => Icons.computer_rounded,
      'router' => Icons.router_outlined,
      'fan' => Icons.toys_outlined,
      'fridge' => Icons.kitchen_outlined,
      'medical' => Icons.medical_services_outlined,
      'fire_alarm' => Icons.local_fire_department_outlined,
      _ => Icons.more_horiz_rounded,
    };

class WizardScaffold extends StatelessWidget {
  const WizardScaffold({
    super.key,
    required this.title,
    required this.step,
    required this.steps,
    required this.onClose,
    required this.onBack,
    required this.onNext,
    required this.nextLabel,
    required this.children,
  });
  final String title;
  final int step; // 0-based
  final int steps;
  final VoidCallback onClose;
  final VoidCallback onBack;
  final VoidCallback? onNext; // null = disabled
  final String nextLabel;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WW.paper,
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          Container(
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Row(children: [
                IconButton(onPressed: onClose, tooltip: 'إلغاء', icon: const Icon(Icons.close_rounded, size: 22, color: WW.ink)),
                const SizedBox(width: 4),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  Text('الخطوة ${step + 1} من $steps', style: const TextStyle(fontSize: 13, color: WW.sub)),
                ]),
              ]),
              const SizedBox(height: 10),
              Row(children: [
                for (var i = 0; i < steps; i++) ...[
                  if (i > 0) const SizedBox(width: 6),
                  Expanded(
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 250),
                      height: 5,
                      decoration: BoxDecoration(color: i <= step ? WW.accentDeep : WW.line, borderRadius: BorderRadius.circular(3)),
                    ),
                  ),
                ],
              ]),
            ]),
          ),
          const Divider(height: 1, color: WW.line),
          Expanded(
            child: ListView(padding: const EdgeInsets.fromLTRB(16, 18, 16, 18), children: children),
          ),
          Container(
            decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: WW.line))),
            padding: EdgeInsets.fromLTRB(16, 12, 16, 12 + MediaQuery.of(context).padding.bottom),
            child: Row(children: [
              Expanded(child: WWButton(step == 0 ? 'إلغاء' : 'رجوع', step == 0 ? onClose : onBack, kind: BtnKind.ghost, height: 54, fontSize: 16)),
              const SizedBox(width: 10),
              Expanded(child: WWButton(nextLabel, onNext, height: 54, fontSize: 16)),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// Step heading and an optional line under it.
List<Widget> stepHead(String title, [String? body]) => [
      Text(title, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w700)),
      if (body != null) ...[
        const SizedBox(height: 10),
        Text(body, style: const TextStyle(fontSize: 14.5, height: 1.65, color: WW.body)),
      ],
      const SizedBox(height: 14),
    ];

/// 3-column grid of device kinds with an icon. Protected kinds carry a small lock.
class KindGrid extends StatelessWidget {
  const KindGrid({super.key, required this.kinds, required this.selected, required this.onPick});
  final List<({String k, String label, bool locked})> kinds;
  final String? selected;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) => GridView.count(
        crossAxisCount: 3,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 8,
        crossAxisSpacing: 8,
        childAspectRatio: 1.18,
        children: [
          for (final x in kinds)
            Material(
              color: selected == x.k ? WW.accentSel2 : x.locked ? const Color(0xFFEEF2F6) : Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(color: selected == x.k ? WW.accent : WW.line, width: selected == x.k ? 2 : 1),
              ),
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: () => onPick(x.k),
                child: Stack(children: [
                  Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Icon(kindIcon(x.k), size: 26, color: WW.ink),
                      const SizedBox(height: 6),
                      Text(x.label.split(' / ').first, textAlign: TextAlign.center, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    ]),
                  ),
                  if (x.locked) const PositionedDirectional(top: 8, end: 8, child: Icon(Icons.lock_outline_rounded, size: 14, color: WW.blueFg)),
                ]),
              ),
            ),
        ],
      );
}

/// Rooms as pills that wrap (smart plug wizard).
class RoomPills extends StatelessWidget {
  const RoomPills({super.key, required this.rooms, required this.selected, required this.onPick});
  final List<dynamic> rooms;
  final String? selected;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) => Wrap(spacing: 8, runSpacing: 8, children: [
        for (final r in rooms)
          GestureDetector(
            onTap: () => onPick('${r['id']}'),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              constraints: const BoxConstraints(minHeight: 40),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: selected == r['id'] ? WW.ink : Colors.white,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: selected == r['id'] ? WW.accent : WW.field, width: selected == r['id'] ? 1.5 : 1),
              ),
              child: Text('${r['name']}',
                  style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: selected == r['id'] ? Colors.white : WW.ink)),
            ),
          ),
      ]);
}

/// White option row with a radio dot (plug list, rooms, permissions).
class RadioRow extends StatelessWidget {
  const RadioRow({super.key, required this.on, required this.onTap, required this.title, this.body, this.titleLtr = false, this.dotFirst = true});
  final bool on;
  final VoidCallback onTap;
  final String title;
  final Widget? body;
  final bool titleLtr;
  final bool dotFirst;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: on ? WW.accent : WW.line, width: on ? 2 : 1)),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 60),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Row(crossAxisAlignment: body == null ? CrossAxisAlignment.center : CrossAxisAlignment.start, children: [
                if (dotFirst) ...[Padding(padding: EdgeInsets.only(top: body == null ? 0 : 2), child: RadioDot(on: on)), const SizedBox(width: 12)],
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(title,
                        textDirection: titleLtr ? TextDirection.ltr : null,
                        style: TextStyle(fontSize: body == null ? 16 : 15, fontWeight: body == null ? FontWeight.w600 : FontWeight.w700)),
                    if (body != null) ...[const SizedBox(height: 3), body!],
                  ]),
                ),
                if (!dotFirst) ...[const SizedBox(width: 12), RadioDot(on: on)],
              ]),
            ),
          ),
        ),
      );
}
