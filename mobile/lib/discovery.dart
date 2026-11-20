// Finds the WattWise server on the local network, so nobody has to type an address.
//
// 1. The backend broadcasts {"app": "wattwise", "port": 8000} every 2 seconds on
//    UDP port 47800. We listen; the sender's address is the laptop.
// 2. On the Android emulator, the laptop is always at 10.0.2.2, so we also try that.
// 3. If both fail, the user can scan the QR code shown on the dashboard.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'discovery_stub.dart' if (dart.library.io) 'discovery_io.dart' as platform;

/// True if [url] answers like a WattWise backend.
Future<bool> isWattWise(String url) async {
  try {
    final res = await http.get(Uri.parse('$url/api/health')).timeout(const Duration(seconds: 2));
    final data = jsonDecode(res.body);
    return res.statusCode == 200 && data is Map && data['ok'] == true;
  } catch (_) {
    return false;
  }
}

/// Looks for the server for up to [timeout]. Returns its address, or null.
Future<String?> findServer({Duration timeout = const Duration(seconds: 6)}) async {
  final found = Completer<String?>();
  void offer(String? url) {
    if (url != null && !found.isCompleted) found.complete(url);
  }

  // Fixed guesses (the emulator address), checked right away.
  for (final url in platform.fixedCandidates()) {
    isWattWise(url).then((ok) => offer(ok ? url : null));
  }
  // The UDP announcement from the laptop. Check it really answers before using it.
  platform.listenForAnnouncement(timeout).then((url) async {
    if (url != null && await isWattWise(url)) offer(url);
  });

  return found.future.timeout(timeout, onTimeout: () => null);
}
