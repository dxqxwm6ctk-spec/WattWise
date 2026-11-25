// WattWise owner app (Flutter).
//
// Simple words, dinars instead of watts, one decision per tap.
// It polls the backend every second and shows 4 tabs: home, devices, bill, safety.

import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'discovery.dart';
import 'notifications.dart';
import 'screens/bill_screen.dart';
import 'screens/devices_screen.dart';
import 'screens/home_screen.dart';
import 'screens/safety_screen.dart';
import 'screens/schedule_screen.dart';
import 'screens/scan_screen.dart';
import 'splash.dart';
import 'theme.dart';

void main() => runApp(const WattWiseApp());

class WattWiseApp extends StatelessWidget {
  const WattWiseApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'WattWise',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: WW.accent, primary: WW.ink, surface: WW.paper),
        scaffoldBackgroundColor: WW.paper,
        fontFamily: WW.font,
        textTheme: const TextTheme().apply(bodyColor: WW.ink, displayColor: WW.ink),
        timePickerTheme: const TimePickerThemeData(backgroundColor: Colors.white),
        useMaterial3: true,
      ),
      // The whole app is Arabic, right-to-left.
      builder: (context, child) => Directionality(textDirection: TextDirection.rtl, child: child!),
      home: const RootPage(),
    );
  }
}

class RootPage extends StatefulWidget {
  const RootPage({super.key});

  @override
  State<RootPage> createState() => _RootPageState();
}

class _RootPageState extends State<RootPage> {
  static const _urlKey = 'server_url';
  // What the "where is the server?" dialog can return besides a typed address.
  static const _choiceSearch = '#search';
  static const _choiceScan = '#scan';
  // The online server on Render. It runs in the cloud, so the app works from
  // anywhere without the laptop. On the free plan it sleeps after about 15 minutes
  // without visitors; the first open then waits up to a minute while it wakes up.
  // Another address can be baked in at build time:
  //   flutter build ios --dart-define=WATTWISE_SERVER=https://example.onrender.com
  static const _cloudServer = String.fromEnvironment('WATTWISE_SERVER',
      defaultValue: 'https://wattwise-vysn.onrender.com');

  WattWiseApi? api;
  Map<String, dynamic>? st;
  String? connectionError;
  int tab = 0;
  Timer? timer;
  // True while a state request is on its way, so slow answers never pile up.
  bool refreshing = false;

  // The splash stays at least this long, so it never just flickers.
  bool splashMinDone = false;
  // Failed tries before the first screen; after a few, we ask where the server is.
  int failedTries = 0;
  bool askedAfterFailures = false;

  @override
  void initState() {
    super.initState();
    Future.delayed(const Duration(milliseconds: 700), () {
      if (mounted) setState(() => splashMinDone = true);
    });
    Notifier.instance.onOpened = _onNotificationOpened;
    Notifier.instance.init();
    _loadServer();
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<void> _loadServer() async {
    final prefs = await SharedPreferences.getInstance();
    var url = prefs.getString(_urlKey);
    // When the web build is served by our own backend, use the same address.
    if (url == null && kIsWeb && Uri.base.scheme.startsWith('http')) url = Uri.base.origin;
    // Use the saved address if the server answers there (for example the laptop during the
    // offline demo). Otherwise use the online server. Only if that fails too (no internet),
    // look for the laptop on the Wi-Fi.
    if (url != null && (kIsWeb || await isWattWise(url))) {
      _connect(url);
      return;
    }
    // The online server may be asleep (free plan), so wait for it to wake up.
    if (url != _cloudServer && await waitForWattWise(_cloudServer)) {
      _connect(_cloudServer);
      return;
    }
    await _searchAndConnect();
  }

  /// Looks for the laptop on the Wi-Fi (silently, behind the splash). If it is not found, asks the user.
  Future<void> _searchAndConnect() async {
    if (!mounted) return;
    final url = await findServer();
    if (!mounted) return;
    if (url == null) {
      _askServer(notFound: true);
      return;
    }
    await _save(url);
    _connect(url);
  }

  Future<void> _save(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_urlKey, url);
  }

  Future<void> _scanQr() async {
    final url = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScanScreen()));
    if (!mounted) return;
    // No code scanned ("type the address instead", or back): show the address sheet again.
    if (url == null) return _askServer(notFound: api == null);
    await _save(url);
    _connect(url);
  }

  void _connect(String url) {
    final site = kIsWeb ? (Uri.base.queryParameters['site'] ?? 'home') : 'home';
    setState(() {
      api = WattWiseApi(baseUrl: url.replaceAll(RegExp(r'/+$'), ''), site: site);
      st = null;
    });
    timer?.cancel();
    _refresh();
    timer = Timer.periodic(const Duration(seconds: 1), (_) => _refresh());
  }

  Future<void> _askServer({bool notFound = false}) async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    final choice = await showModalBottomSheet<String>(
      context: context,
      isDismissible: api != null,
      enableDrag: api != null,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      barrierColor: api == null ? Colors.transparent : const Color(0x8C0E1A15),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
      builder: (c) => ServerSheet(notFound: notFound, initial: prefs.getString(_urlKey) ?? '', cloud: _cloudServer, scan: _choiceScan, search: _choiceSearch),
    );
    if (choice == null || choice.isEmpty) {
      // Still on the splash with no server: ask again, otherwise there is nothing to tap.
      if (st == null && api == null) return _askServer(notFound: notFound);
      return;
    }
    if (choice == _choiceSearch) return _searchAndConnect();
    if (choice == _choiceScan) return _scanQr();
    await _save(choice);
    _connect(choice);
  }

  Future<void> _refresh() async {
    final a = api;
    if (a == null || refreshing) return;
    refreshing = true;
    try {
      final s = await a.getState();
      if (mounted) setState(() { st = s; connectionError = null; failedTries = 0; });
      liveState.value = s;
      await Notifier.instance.handleState(s);
      _onNotificationOpened();
    } catch (e) {
      if (mounted) setState(() => connectionError = 'تعذّر الوصول إلى الخادم (${a.baseUrl}).');
      // Still on the splash and the server keeps failing: ask once, quietly retrying meanwhile.
      failedTries++;
      if (st == null && failedTries >= 8 && !askedAfterFailures) {
        askedAfterFailures = true;
        _askServer();
      }
    } finally {
      refreshing = false;
    }
  }

  /// A notification was tapped: go to the home tab. If "أطفئه؟" was pressed,
  /// ask the backend for an approval request (the human still has to approve it).
  /// It is also called after every refresh, to catch a tap that came before the first
  /// state. It only moves to the home tab when there really was a tap; before this
  /// check, every refresh (once a second) threw the user back to the home tab.
  void _onNotificationOpened() {
    final a = api;
    if (a == null || st == null || !mounted) return;
    if (!Notifier.instance.takeOpened()) return;
    final alertId = Notifier.instance.pendingTurnOff;
    Notifier.instance.pendingTurnOff = null;
    setState(() => tab = 0);
    if (alertId != null) run(() => a.alertAct(alertId));
  }

  /// Runs an action, shows the server's Arabic message if it is refused, then refreshes.
  Future<void> run(Future<void> Function() action) async {
    try {
      await action();
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (_) {
      _snack('تعذّر الوصول إلى الخادم.');
    }
    await _refresh();
  }

  void _snack(String msg) {
    if (!mounted) return;
    wwSnack(context, msg, icon: Icons.lock_outline);
  }

  @override
  Widget build(BuildContext context) {
    final s = st, a = api;
    // Until the first state arrives, only the splash shows. The search and connection run
    // silently behind it, and the app fades in as soon as the server answers.
    final Widget page = (s == null || a == null || !splashMinDone)
        ? const SplashView(key: ValueKey('splash'))
        : _app(s, a);
    return AnimatedSwitcher(duration: const Duration(milliseconds: 450), child: page);
  }

  Widget _app(Map<String, dynamic> s, WattWiseApi a) {
    final screens = [
      HomeScreen(st: s, api: a, run: run, onApprove: a.approve, onReject: a.reject),
      DevicesScreen(st: s, api: a, run: run),
      ScheduleScreen(st: s, api: a, run: run),
      BillScreen(st: s, api: a, run: run),
      SafetyScreen(st: s, api: a, run: run, onChangeServer: _askServer),
    ];
    final body = ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 20), children: [
      if (connectionError != null) ...[
        _ConnectionBanner(onRetry: _refresh),
        const SizedBox(height: 14),
      ],
      screens[tab],
    ]);
    return Scaffold(
      key: const ValueKey('app'),
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          _Header(siteName: '${s['site_name']}', lab: a.site == 'lab'),
          Expanded(child: body),
        ]),
      ),
      bottomNavigationBar: _TabBar(index: tab, lab: a.site == 'lab', onTap: (i) => setState(() => tab = i)),
    );
  }
}

/// Logo, the site's name and "WattWise". A small badge in lab mode.
class _Header extends StatelessWidget {
  const _Header({required this.siteName, required this.lab});
  final String siteName;
  final bool lab;

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 64,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Row(children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(color: WW.ink, borderRadius: BorderRadius.circular(10.5)),
              // Same mark as the app icon.
              child: CustomPaint(painter: WattWiseMarkPainter()),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(siteName, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: WW.body, height: 1.25)),
                const Text('WattWise', textDirection: TextDirection.ltr, style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700, height: 1.25, letterSpacing: -0.2)),
              ]),
            ),
            if (lab) const Pill('وضع المختبر', icon: Icons.science_outlined),
          ]),
        ),
      );
}

/// Red strip under the header when the server does not answer.
class _ConnectionBanner extends StatelessWidget {
  const _ConnectionBanner({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
        decoration: BoxDecoration(color: WW.red, borderRadius: BorderRadius.circular(14)),
        child: Row(children: [
          const Icon(Icons.wifi_off_rounded, size: 18, color: Colors.white),
          const SizedBox(width: 10),
          const Expanded(child: Text('تعذّر الوصول إلى الخادم', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Colors.white))),
          OutlinedButton(
            onPressed: onRetry,
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white,
              minimumSize: const Size(0, 36),
              side: const BorderSide(color: Colors.white),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            child: const Text('أعد المحاولة', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
          ),
        ]),
      );
}

class _TabBar extends StatelessWidget {
  const _TabBar({required this.index, required this.lab, required this.onTap});
  final int index;
  final bool lab;
  final ValueChanged<int> onTap;

  static const icons = [Icons.home_outlined, Icons.power_outlined, Icons.schedule_rounded, Icons.receipt_long_outlined, Icons.verified_user_outlined];

  @override
  Widget build(BuildContext context) {
    final labels = [lab ? 'الرئيسية' : 'البيت', 'الأجهزة', 'الجدولة', 'الفاتورة', 'الأمان'];
    return Container(
      decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: WW.line))),
      padding: EdgeInsets.fromLTRB(4, 8, 4, 8 + MediaQuery.of(context).padding.bottom),
      child: Row(children: [
        for (var i = 0; i < labels.length; i++)
          Expanded(
            child: Semantics(
              selected: i == index,
              button: true,
              child: InkWell(
                onTap: () => onTap(i),
                borderRadius: BorderRadius.circular(16),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width: 58,
                    height: 30,
                    decoration: BoxDecoration(color: i == index ? WW.accentSel : Colors.transparent, borderRadius: BorderRadius.circular(15)),
                    child: Icon(icons[i], size: 22, color: i == index ? WW.ink : WW.sub),
                  ),
                  const SizedBox(height: 3),
                  Text(labels[i],
                      style: TextStyle(fontSize: 12, fontWeight: i == index ? FontWeight.w700 : FontWeight.w500, color: i == index ? WW.ink : WW.sub)),
                ]),
              ),
            ),
          ),
      ]),
    );
  }
}

/// "Can't reach the server": online server, scan the QR, search the Wi-Fi again, or type the address.
class ServerSheet extends StatefulWidget {
  const ServerSheet({super.key, required this.notFound, required this.initial, required this.cloud, required this.scan, required this.search});
  final bool notFound;
  final String initial, cloud, scan, search;

  @override
  State<ServerSheet> createState() => _ServerSheetState();
}

class _ServerSheetState extends State<ServerSheet> {
  late final ctrl = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget option(String label, IconData icon, String value, {bool dark = false}) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Material(
            color: dark ? WW.ink : Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: dark ? BorderSide.none : const BorderSide(color: WW.line)),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => Navigator.pop(context, value),
              child: SizedBox(
                height: 56,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Row(children: [
                    Icon(icon, size: 20, color: dark ? Colors.white : WW.ink),
                    const SizedBox(width: 12),
                    Expanded(
                        child: Text(label,
                            style: TextStyle(fontSize: 16, fontWeight: dark ? FontWeight.w700 : FontWeight.w600, color: dark ? Colors.white : WW.ink))),
                  ]),
                ),
              ),
            ),
          ),
        );
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 22),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Center(child: Container(width: 40, height: 5, decoration: BoxDecoration(color: const Color(0xFFDCDCE3), borderRadius: BorderRadius.circular(3)))),
            const SizedBox(height: 14),
            Row(children: [
              IconTile(
                  icon: widget.notFound ? Icons.wifi_off_rounded : Icons.dns_outlined,
                  bg: widget.notFound ? WW.redBg : WW.accentBg,
                  fg: widget.notFound ? WW.red : WW.ink,
                  size: 44,
                  iconSize: 22,
                  radius: 14),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(widget.notFound ? 'تعذّر الوصول إلى الخادم' : 'أين الخادم؟', style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w700)),
                  const Text('اختر طريقة للاتصال:', style: TextStyle(fontSize: 14, color: WW.sub)),
                ]),
              ),
            ]),
            const SizedBox(height: 14),
            option('استخدم الخادم على الإنترنت', Icons.cloud_outlined, widget.cloud, dark: true),
            option('امسح رمز QR من لوحة التحكم', Icons.qr_code_2_rounded, widget.scan),
            option('ابحث مجددًا في شبكة Wi-Fi', Icons.wifi_rounded, widget.search),
            const SizedBox(height: 6),
            const Row(children: [
              Expanded(child: Divider(color: WW.line)),
              Padding(padding: EdgeInsets.symmetric(horizontal: 10), child: Text('أو', style: TextStyle(fontSize: 13, color: WW.sub))),
              Expanded(child: Divider(color: WW.line)),
            ]),
            const SizedBox(height: 6),
            const Text('اكتب عنوان الخادم', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: ctrl,
                  textDirection: TextDirection.ltr,
                  keyboardType: TextInputType.url,
                  decoration: wwField('http://192.168.1.10:8000'),
                  onSubmitted: (v) => Navigator.pop(context, v.trim()),
                ),
              ),
              const SizedBox(width: 8),
              WWButton('اتصل', () => Navigator.pop(context, ctrl.text.trim()), height: 52, radius: 14),
            ]),
            const SizedBox(height: 6),
            const Text('تجده على شاشة الحاسوب الذي يشغّل WattWise.', style: TextStyle(fontSize: 12.5, color: WW.sub)),
          ]),
        ),
      ),
    );
  }
}
