# WattWise owner app (Flutter)

تطبيق صاحب البيت: بطاقة «بدنا رأيك» للموافقة أو الرفض، الأجهزة، الفاتورة، والأمان.
بيحكي مع نفس الـ backend اللي بتحكي معه لوحة التحكم، على نفس الـ Wi-Fi (ما بدّه إنترنت).

## التشغيل
1. شغّل الـ backend على اللابتوب: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
   (مهم `--host 0.0.0.0` عشان الهاتف يقدر يوصله).
2. اعرف عنوان اللابتوب على الشبكة (Windows: `ipconfig` ← IPv4 Address، مثلاً `192.168.1.10`).
3. وصّل الهاتف بالكمبيوتر وشغّل:
   ```bash
   cd mobile
   flutter pub get
   flutter run
   ```
4. التطبيق بيلاقي اللابتوب **لحاله**: الـ backend بيعلن عن حاله على الـ Wi-Fi كل ثانيتين
   (UDP، بورت 47800)، وعلى محاكي Android التطبيق بيجرّب `10.0.2.2` تلقائياً.
   إذا ما لقاه، بيطلعلك زر «امسح الـ QR من لوحة التحكم» (الـ QR موجود بلوحة التحكم على اللابتوب)،
   أو بتقدر تكتب العنوان بإيدك. بتقدر تغيّره بعدين من تبويب «الأمان».

إذا ما اتصل: تأكد إنه الهاتف واللابتوب على نفس الـ Wi-Fi، وإنه الـ Firewall على اللابتوب سامح للبورت 8000.

## Structure
- `lib/api.dart`: HTTP client for the backend API
- `lib/main.dart`: app shell, server address, 1-second polling, tab bar
- `lib/screens/`: home (approval card), devices (+ add-device wizard), bill, safety
- `lib/widgets/meter_widgets.dart`: gauge, odometer, room bars
- `lib/theme.dart`: colours from the design

All safety rules are enforced on the server (Policy Guard). The app only sends requests;
if something is refused, it shows the server's Arabic reason.

Android allows plain HTTP to the local server (`usesCleartextTraffic`), iOS allows local networking.
