// Talks to the WattWise backend. The same API the web dashboard uses.
//
// The phone and the laptop running the backend must be on the same Wi-Fi.
// No internet is needed.

import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.message);
  final String message; // Arabic text from the backend, safe to show
  @override
  String toString() => message;
}

class WattWiseApi {
  WattWiseApi({required this.baseUrl, this.site = 'home'});

  final String baseUrl; // for example http://192.168.1.10:8000
  final String site;

  Uri _uri(String path) => Uri.parse('$baseUrl/api/sites/$site$path');

  Future<Map<String, dynamic>> getState() async {
    final res = await http.get(_uri('/state')).timeout(const Duration(seconds: 4));
    return _decode(res);
  }

  Future<Map<String, dynamic>> post(String path, [Map<String, dynamic>? body]) async {
    final res = await http
        .post(_uri(path), headers: {'Content-Type': 'application/json'}, body: jsonEncode(body ?? {}))
        .timeout(const Duration(seconds: 4));
    return _decode(res);
  }

  Future<void> delete(String path) async {
    await http.delete(_uri(path)).timeout(const Duration(seconds: 4));
  }

  // --- actions (each one goes through the Policy Guard on the server) ---
  Future<void> approve(int id) => post('/approvals/$id/approve');
  Future<void> reject(int id) => post('/approvals/$id/reject');
  Future<void> emergencyStop() => post('/estop');
  Future<void> reset() => post('/reset');
  Future<void> setTariff(String type) => post('/tariff', {'type': type});
  Future<void> toggle(String id, bool on, {bool confirmed = false}) =>
      post('/devices/$id/toggle', {'on': on, 'confirmed': confirmed});
  Future<void> setpoint(String id, num value) => post('/devices/$id/setpoint', {'value': value});
  Future<void> startLearning(String kind) => post('/learn', {'kind': kind});
  Future<void> cancelLearning() => delete('/learn');
  Future<void> addDevice({required String kind, required String room, required String name, required bool allow}) =>
      post('/devices', {'kind': kind, 'room': room, 'name': name, 'allow': allow});

  Map<String, dynamic> _decode(http.Response res) {
    final body = utf8.decode(res.bodyBytes);
    final data = body.isEmpty ? <String, dynamic>{} : jsonDecode(body);
    if (res.statusCode >= 400) {
      final detail = data is Map ? data['detail'] : null;
      throw ApiException(detail is String ? detail : 'خطأ من السيرفر (${res.statusCode})');
    }
    return data is Map<String, dynamic> ? data : <String, dynamic>{};
  }
}
