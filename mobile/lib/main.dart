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
        colorScheme: ColorScheme.fromSeed(seedColor: WW.lime, surface: WW.paper),
        scaffoldBackgroundColor: WW.paper,
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
  // Optional server baked in at build time, for example the online Railway copy:
  //   flutter build ios --dart-define=WATTWISE_SERVER=https://example.up.railway.app
  // Empty by default, so normal builds still look for the laptop on the Wi-Fi.
  static const _builtInServer = String.fromEnvironment('WATTWISE_SERVER');

  WattWiseApi? api;
  Map<String, dynamic>? st;
  String? connectionError;
  int tab = 0;
  Timer? timer;

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
    if (url == null && _builtInServer.isNotEmpty) url = _builtInServer;
    // Use the saved address if the server answers there; otherwise look for it on the network.
    if (url != null && (kIsWeb || await isWattWise(url))) {
      _connect(url);
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
    if (url == null || !mounted) return;
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
    final ctrl = TextEditingController(text: prefs.getString(_urlKey) ?? '');
    final choice = await showDialog<String>(
      context: context,
      barrierDismissible: api != null,
      builder: (c) => AlertDialog(
        title: Text(notFound ? 'ما لقينا اللابتوب' : 'وين السيرفر؟'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('تأكد إنه WattWise شغّال على اللابتوب، وإنه الهاتف واللابتوب على نفس الـ Wi-Fi.'),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: () => Navigator.pop(c, _choiceScan),
            style: FilledButton.styleFrom(backgroundColor: WW.ink),
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('امسح الـ QR من لوحة التحكم'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () => Navigator.pop(c, _choiceSearch),
            icon: const Icon(Icons.wifi_find),
            label: const Text('دوّر مرة تانية'),
          ),
          const SizedBox(height: 14),
          const Text('أو اكتب العنوان بإيدك:', style: TextStyle(fontSize: 13, color: WW.sub)),
          TextField(
            controller: ctrl,
            textDirection: TextDirection.ltr,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(hintText: 'http://192.168.1.10:8000'),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, ctrl.text.trim()), child: const Text('اتصل')),
        ],
      ),
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
    if (a == null) return;
    try {
      final s = await a.getState();
      if (mounted) setState(() { st = s; connectionError = null; failedTries = 0; });
      await Notifier.instance.handleState(s);
      _onNotificationOpened();
    } catch (e) {
      if (mounted) setState(() => connectionError = 'ما قدرنا نوصل للسيرفر (${a.baseUrl}).');
      // Still on the splash and the server keeps failing: ask once, quietly retrying meanwhile.
      failedTries++;
      if (st == null && failedTries >= 8 && !askedAfterFailures) {
        askedAfterFailures = true;
        _askServer();
      }
    }
  }

  /// A notification was tapped: go to the home tab. If "طفّيه؟" was pressed,
  /// ask the backend for an approval request (the human still has to approve it).
  void _onNotificationOpened() {
    final a = api;
    if (a == null || st == null || !mounted) return;
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
      _snack('ما قدرنا نوصل للسيرفر.');
    }
    await _refresh();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: const Color(0xFF7A2A1C)));
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
    final body = ListView(padding: const EdgeInsets.fromLTRB(20, 14, 20, 16), children: [
      _Header(siteName: '${s['site_name']}'),
      if (connectionError != null) ...[
        const SizedBox(height: 10),
        WWBox(color: const Color(0xFFFBE3DD), padding: 12, child: Text(connectionError!, style: const TextStyle(color: Color(0xFF7A2A1C)))),
      ],
      const SizedBox(height: 14),
      screens[tab],
    ]);
    return Scaffold(
      key: const ValueKey('app'),
      body: SafeArea(bottom: false, child: body),
      bottomNavigationBar: _TabBar(index: tab, onTap: (i) => setState(() => tab = i)),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.siteName});
  final String siteName;

  @override
  Widget build(BuildContext context) => Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(siteName, style: const TextStyle(fontSize: 13, color: WW.sub)),
            const SizedBox(height: 2),
            const Text('أهلين 👋', style: TextStyle(fontSize: 21, fontWeight: FontWeight.w700)),
          ]),
        ),
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(color: WW.ink, borderRadius: BorderRadius.circular(12)),
          alignment: Alignment.center,
          // Same mark as the app icon.
          child: CustomPaint(size: const Size(38, 38), painter: WattWiseMarkPainter()),
        ),
      ]);
}

class _TabBar extends StatelessWidget {
  const _TabBar({required this.index, required this.onTap});
  final int index;
  final ValueChanged<int> onTap;

  static const labels = ['البيت', 'الأجهزة', 'الجدولة', 'الفاتورة', 'الأمان'];

  @override
  Widget build(BuildContext context) => Container(
        decoration: const BoxDecoration(color: WW.paper, border: Border(top: BorderSide(color: WW.line))),
        padding: EdgeInsets.fromLTRB(14, 8, 14, 8 + MediaQuery.of(context).padding.bottom),
        child: Row(children: [
          for (var i = 0; i < labels.length; i++)
            Expanded(
              child: InkWell(
                onTap: () => onTap(i),
                child: SizedBox(
                  height: 48,
                  child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Container(width: 18, height: 3, decoration: BoxDecoration(color: i == index ? WW.ink : Colors.transparent, borderRadius: BorderRadius.circular(2))),
                    const SizedBox(height: 5),
                    Text(labels[i], style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: i == index ? WW.ink : const Color(0xFF9A988E))),
                  ]),
                ),
              ),
            ),
        ]),
      );
}
