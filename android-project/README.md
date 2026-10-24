# 📱 Liquidity Dissection — Native Android Studio Project
### تطبيق أندرويد أصلي 100% (Kotlin + Jetpack Compose + Room SQLite)
يعمل بشكل مستقل بالكامل (Zero Node.js Backend) ويتم بناؤه وتشغيله مباشرة عبر **Android Studio**.

---

## 🏗️ البنية المعمارية للمشروع:
* **لغة البرمجة:** Kotlin 1.9+
* **واجهة المستخدم:** Jetpack Compose & Material 3 (تصميم فاخر داكن Obsidian `#121212` وذهب 3D `#C5A059`)
* **قاعدة بيانات داخلية على الهاتف:** Room Database (SQLite) لحفظ إعدادات الحساب ونسبة المخاطرة 1% وسجل الصفقات (Journal)
* **جلب الشارت المباشر:** اتصال مباشر عبر OkHttp بـ Binance WebSocket و Yahoo Finance للذهب والعملات
* **جلب الأخبار اللحظية:** معالجة تلقائية لخلاصات RSS مع بروتوكول حظر التداول المؤسساتي (`⛔ NEWS LOCKOUT`)

---

## 🚀 كيفية فتح المشروع وبناء الـ APK في Android Studio:

### 1. فتح المشروع في Android Studio:
1. شغل برنامج **Android Studio** على حاسوبك.
2. من القائمة الرئيسية اضغط على **Open** (أو `File` -> `Open...`).
3. توجه إلى مجلد المشروع واختر مجلد: **`android-project`** ثم اضغط **OK**.
4. انتظر بضع ثوانٍ حتى تنتهي عملية **Gradle Sync**.

### 2. تشغيل التطبيق على الهاتف أو المحاكي (Run):
* صل هاتفك الأندرويد بالحاسوب عبر كابل USB مع تفعيل **USB Debugging** (أو شغل محاكي Emulator).
* اضغط على زر التشغيل الأخضر **Run ▶️** (أو اختصار `Shift + F10`).
* سيتم تثبيت التطبيق وفتحه فوراً على شاشة هاتفك!

### 3. استخراج ملف APK جاهز للتثبيت (Build APK):
* من القائمة العلوية في Android Studio، اضغط على:
  **`Build`** -> **`Build Bundle(s) / APK(s)`** -> **`Build APK(s)`**
* سيقوم أندرويد ستوديو بتوليد ملف `app-debug.apk` في مسار:
  `android-project/app/build/outputs/apk/debug/app-debug.apk`
  يمكنك إرساله وتثبيته على أي هاتف مباشرة!
