# 📱 Liquidity Dissection — 100% Native Mobile App (Expo / React Native)

تطبيق هاتف أصلي 100% (iOS & Android) لمنصة **Liquidity Dissection - Private Desk**.
يعمل بشكل مستقل بالكامل (**Serverless / 100% Client-Side**) وبدون الحاجة إلى أي سيرفر Node.js أو بروكسي خارجي.

---

## 🌟 المميزات التقنية للهاتف:
1. **بدون سيرفر نهائياً (Zero Backend Dependency):**
   - خوارزميات الـ 10 ركائز المؤسساتية (SMC Order Blocks, BOS, CHOCH, FVG, Liquidity Sweeps, 4H HTF Framework, 5M Confirmation Trigger) تُحسب بالكامل داخل معالج الهاتف بلغة TypeScript.
2. **قاعدة بيانات محلية على الهاتف (expo-sqlite):**
   - حفظ بيانات المستخدم، إعدادات الحساب ونسبة المخاطرة 1%.
   - مذكرة صفقات متكاملة (Trading Journal) مع حساب الـ PnL ونسبة الصفقات الرابحة.
3. **شارت مباشر بدون وسيط (Direct Market Charts):**
   - اتصال مباشر عبر WebSocket ببينانس للعملات الرقمية (`wss://stream.binance.com:9443/ws/btcusdt@kline_15m`).
   - جلب مباشر لشموع الذهب (XAU/USD) والنفط والعملات من Yahoo Finance.
4. **أخبار حية مع بروتوكول حظر التداول (`⛔ NEWS LOCKOUT`):**
   - جلب وتفكيك الـ RSS اللحظي من Bloomberg, Yahoo Finance, Investing.com, CNBC.
   - تفعيل آلي لبروتوكول حظر التداول وقت الأخبار الفائقة التأثير (CPI, NFP, Fed).
5. **تصميم فاخر مخصص للهاتف (Luxury Mobile UX):**
   - أسود أوبسيديان (`#121212`, `#1A1A1A`) مع لمسات الذهب المصقول 3D (`#C5A059`).
   - شعار **LD** السداسي المجسم بتقنية `react-native-svg`.
   - شريط تنقل سفلي أصلي (Bottom Navigation) مع اهتزازات لمسية تفاعلية (`expo-haptics`).

---

## 🚀 كيفية تشغيل التطبيق على الهاتف:

### الخطوة 1: تثبيت الحزم داخل مجلد `mobile`
```bash
cd mobile
npm install
```

### الخطوة 2: تشغيل التطبيق في وضع التطوير (Expo)
```bash
npx expo start
```
* سيظهر لك رمز **QR Code** في الطرفية (Terminal).
* افتح تطبيق **Expo Go** على هاتفك (آيفون أو أندرويد) وامسح الكود بالكاميرا لتجربة التطبيق مباشرة على هاتفك!

---

## 📦 استخراج ملف الـ APK للأندرويد (Production Build):
لبناء ملف تثبيت أندرويد مستقل **APK** يمكن تثبيته على أي هاتف:
```bash
# تثبيت أداة EAS عالمياً
npm install -g eas-cli

# تسجيل الدخول لحساب Expo المجاني
eas login

# تهيئة المشروع
eas build:configure

# بناء الـ APK مباشرة سحابياً
eas build -p android --profile preview
```
ستحصل في نهاية الأمر على رابط تحميل مباشر لملف `app-release.apk` لتثبيته فوراً على جهازك.
