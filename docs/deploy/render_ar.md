# نسخة أونلاين على Render (بدل Railway)

> مهم: العرض قدام الحكام **ما بحتاج إنترنت ولا Render**. العرض الأساسي بضل على اللابتوب:
> `python scripts/run_demo.py`. النسخة الأونلاين بس عشان تفرجي حدا المشروع من أي مكان.

## شو اللي بصير على Render؟

- Render بقرأ الملف `render.yaml` من المستودع (اسمه Blueprint).
- بنزّل المكتبات (`pip install -r requirements.txt`) وبشغّل `python scripts/cloud_start.py`.
- هذا السكربت بشغّل السيرفر والمحاكي (البيت + المبنى ١٠ غرف)، فاللوحة فيها بيانات **مصطنعة** حيّة.
- كل ما ينعمل push على `main`، Render بعيد النشر لحاله. **ما في داعي للابتوب يضل شغّال.**

## الخطوات (مرة وحدة بس، من المتصفح، بدون CLI)

1. افتح https://dashboard.render.com وادخل بـ **GitHub**.
2. افتح https://dashboard.render.com/blueprint/new
3. إذا طلب صلاحية GitHub، اسمحله يشوف المستودع `WattWise`.
4. اختار `WattWise`، واكتب أي اسم للـ Blueprint (مثلاً `wattwise`)، واضغط **Deploy Blueprint** (أو **Apply**).
5. استنى ٣ لـ ٥ دقايق. افتح الخدمة `wattwise`، فوق رح تلاقي رابط مثل
   `https://wattwise-xxxx.onrender.com`.
6. افتح الرابط وزيد عليه `/index.html`. لازم تشوف اللوحة والأرقام بتتحرك.

## الخطة المجانية: شو لازم تعرف

- **بنام:** إذا ما حدا فتح الموقع ١٥ دقيقة، بنام. أول زيارة بعدها بتوخذ تقريباً دقيقة لحتى يصحى.
  قبل ما تفرجي حدا، افتح الرابط قبلها بدقيقتين.
- **البيانات بتنمسح** كل ما يصحى أو ينعاد النشر، لأنه الخطة المجانية ما فيها disk.
  هذا مش مشكلة لأنه كل البيانات مصطنعة والمحاكي بعبّيها خلال ثواني.

## Render CLI (اختياري)

مش لازم للنشر. بس إذا بدك تشوف الـ logs من PowerShell:

1. نزّل آخر نسخة Windows من https://github.com/render-oss/cli/releases
   (الملف اللي اسمه فيه `windows_amd64.zip`)، وفك الضغط، وحط `cli_...exe` باسم `render.exe`
   بمجلد مثل `D:\developer\tools`.
2. بـ PowerShell: `D:\developer\tools\render.exe login`
   بطبعلك رابط فيه كود وبفتح المتصفح. اضغط **Authorize** بصفحة Render.
3. بعدها: `render.exe services` و`render.exe logs`.

## إذا صار مشكلة

- **Build failed:** افتح الخدمة ← **Events** ← آخر deploy ← **Logs**، وابعتلي آخر ٢٠ سطر.
- **الموقع ما بفتح:** بالـ Logs لازم تشوف `WattWise backend is running on port ...` و`Simulators running`.

## ملاحظة أمان

الرابط عام: أي حدا معه الرابط بقدر يكبس موافقة/رفض على **المحاكاة** بس. لا توصل الـ ESP32 والريلاي الحقيقي على النسخة الأونلاين.
