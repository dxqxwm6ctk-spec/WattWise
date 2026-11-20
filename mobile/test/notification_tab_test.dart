// Regression test: the app refreshes its state every second and, after each refresh,
// asks the Notifier whether a notification was tapped. That answer must be "yes" only
// once per real tap. If it stayed "yes", every refresh would throw the user back to
// the home tab (the bug where the bottom tabs kept jumping back to البيت).

import 'package:flutter_test/flutter_test.dart';
import 'package:wattwise_app/notifications.dart';

void main() {
  final n = Notifier.instance;

  setUp(() {
    n.onOpened = null;
    n.pendingTurnOff = null;
    n.takeOpened(); // start clean
  });

  test('no tap means ordinary refreshes never ask to switch tabs', () {
    for (var i = 0; i < 10; i++) {
      expect(n.takeOpened(), isFalse);
    }
  });

  test('one tap switches to the home tab exactly once', () {
    var calls = 0;
    n.onOpened = () => calls++;
    n.markOpened();
    expect(calls, 1);
    expect(n.takeOpened(), isTrue);
    expect(n.takeOpened(), isFalse);
    expect(n.takeOpened(), isFalse);
  });

  test('the "turn it off?" button keeps the alert id for the app', () {
    n.markOpened(turnOffAlert: 42);
    expect(n.pendingTurnOff, 42);
    expect(n.takeOpened(), isTrue);
  });
}
