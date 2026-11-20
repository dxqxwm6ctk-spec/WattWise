// Discovery on the web build: browsers cannot use UDP. The web build is served by
// the backend itself, so main.dart already uses the page's own address.

List<String> fixedCandidates() => const [];

Future<String?> listenForAnnouncement(Duration timeout) async => null;
