// Discovery on Android / iOS / desktop (uses UDP sockets from dart:io).

import 'dart:async';
import 'dart:convert';
import 'dart:io';

const discoveryPort = 47800; // must match DISCOVERY_PORT in backend/discovery.py

/// Addresses worth trying without any announcement.
List<String> fixedCandidates() =>
    Platform.isAndroid ? ['http://10.0.2.2:8000'] : ['http://127.0.0.1:8000'];

/// Waits for the backend's UDP announcement. Returns the server address, or null.
Future<String?> listenForAnnouncement(Duration timeout) async {
  final RawDatagramSocket sock;
  try {
    sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, discoveryPort, reuseAddress: true);
  } catch (_) {
    return null; // port busy or not allowed: the other methods still work
  }
  final result = Completer<String?>();
  final timer = Timer(timeout, () {
    if (!result.isCompleted) result.complete(null);
  });
  sock.listen((event) {
    if (event != RawSocketEvent.read || result.isCompleted) return;
    final packet = sock.receive();
    if (packet == null) return;
    try {
      final msg = jsonDecode(utf8.decode(packet.data));
      if (msg is Map && msg['app'] == 'wattwise') {
        final port = msg['port'] is int ? msg['port'] : 8000;
        result.complete('http://${packet.address.address}:$port');
      }
    } catch (_) {
      // not our message, ignore it
    }
  });
  final url = await result.future;
  timer.cancel();
  sock.close();
  return url;
}
