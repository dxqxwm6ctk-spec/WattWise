// Local notifications for the agent's warnings (high use, next tariff tier, danger...).
//
// How it works: the app already asks the backend for the state every second.
// When the state has a warning with a NEW id, we show a notification on the phone.
// No Apple / Google push servers are used, so it works offline on the local Wi-Fi
// and with the free-Apple-ID iOS build. The limit: the app must be open or recently
// in the background (iOS pauses apps quickly), because nothing can wake it up.
//
// The "طفّيه؟" button does NOT switch anything. It asks the backend to create a
// normal approval request, and the human still has to press Approve in the app.

import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

class Notifier {
  Notifier._();
  static final Notifier instance = Notifier._();

  static const _channelId = 'ww_alerts';
  static const _channelName = 'تنبيهات WattWise';
  static const _iosCategory = 'ww_alert_off';
  static const actionTurnOff = 'turn_off';
  static const _lastKey = 'last_alert_id';

  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;
  int? _lastAlertId;
  int? _lastApprovalId;
  bool _firstState = true;

  /// The user pressed "طفّيه؟" on a notification: the alert id, handled by the app.
  int? pendingTurnOff;

  /// Called when a notification needs the app's attention (tap or action button).
  void Function()? onOpened;

  Future<void> init() async {
    if (kIsWeb || _ready) return; // the web page has its own browser notifications
    final darwin = DarwinInitializationSettings(
      notificationCategories: [
        DarwinNotificationCategory(_iosCategory, actions: [
          DarwinNotificationAction.plain(actionTurnOff, 'طفّيه؟',
              options: {DarwinNotificationActionOption.foreground}),
        ]),
      ],
    );
    try {
      await _plugin.initialize(
        settings: InitializationSettings(
          android: const AndroidInitializationSettings('@mipmap/ic_launcher'),
          iOS: darwin,
        ),
        onDidReceiveNotificationResponse: _onResponse,
      );
      // Android 13+ asks the user once. iOS asks during initialize().
      await _plugin
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
      // The app was closed and the user opened it from a notification.
      final launch = await _plugin.getNotificationAppLaunchDetails();
      final resp = launch?.notificationResponse;
      if (launch?.didNotificationLaunchApp == true && resp != null) _onResponse(resp);
      final prefs = await SharedPreferences.getInstance();
      _lastAlertId = prefs.getInt(_lastKey);
      _ready = true;
    } catch (_) {
      // Notifications are a nice extra. The app works the same without them.
    }
  }

  void _onResponse(NotificationResponse r) {
    final data = r.payload == null ? null : jsonDecode(r.payload!) as Map<String, dynamic>;
    if (r.actionId == actionTurnOff && data?['alert'] is int) pendingTurnOff = data!['alert'] as int;
    onOpened?.call();
  }

  /// Called after every state refresh. Shows a notification for each new warning
  /// and for a new approval request.
  Future<void> handleState(Map<String, dynamic> st) async {
    if (!_ready) return;
    final alerts = st['alerts'] as Map<String, dynamic>?;
    final lastId = (alerts?['last_id'] as num?)?.toInt() ?? 0;
    final items = (alerts?['items'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();

    // First time ever, or the server's database was reset: start from now.
    if (_lastAlertId == null || lastId < _lastAlertId!) _lastAlertId = _firstState ? lastId : 0;
    final fresh = items
        .where((a) => (a['id'] as num).toInt() > _lastAlertId! && a['active'] == true && a['user_state'] == null)
        .toList()
        .reversed;
    for (final a in fresh) {
      await _showAlert(a);
    }
    if (lastId != _lastAlertId) {
      _lastAlertId = lastId;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt(_lastKey, lastId);
    }

    // A new approval request (the card is in the app, the notification brings you there).
    final pending = st['pending'] as Map<String, dynamic>?;
    final pid = (pending?['id'] as num?)?.toInt();
    if (pid != null && pid != _lastApprovalId && !_firstState) {
      await _plugin.show(
        id: 900000 + pid,
        title: 'بدنا رأيك: ${pending!['title']}',
        body: '${pending['reason']}\nإذا ما رديت، ما رح نعمل إشي.',
        notificationDetails: _details(body: '${pending['reason']}', withAction: false, danger: false),
        payload: jsonEncode({'approval': pid}),
      );
    }
    _lastApprovalId = pid;
    _firstState = false;
  }

  Future<void> _showAlert(Map<String, dynamic> a) async {
    final id = (a['id'] as num).toInt();
    await _plugin.show(
      id: id,
      title: '${a['title']}',
      body: '${a['body']}',
      notificationDetails: _details(body: '${a['body']}', withAction: a['can_act'] == true, danger: a['level'] == 'danger'),
      payload: jsonEncode({'alert': id}),
    );
  }

  NotificationDetails _details({required String body, required bool withAction, required bool danger}) => NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: 'استهلاك عالي، الشريحة الأغلى، خطر، وطلبات الموافقة',
          importance: Importance.high,
          priority: danger ? Priority.max : Priority.high,
          styleInformation: BigTextStyleInformation(body), // long Arabic text is not cut
          actions: withAction
              ? const [AndroidNotificationAction(actionTurnOff, 'طفّيه؟', showsUserInterface: true)]
              : null,
        ),
        iOS: DarwinNotificationDetails(
          categoryIdentifier: withAction ? _iosCategory : null,
        ),
      );
}
