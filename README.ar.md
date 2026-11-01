<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.pt-BR.md">Português (Brasil)</a> ·
  <a href="README.zh-CN.md">中文</a> ·
  <a href="README.ar.md">العربية</a> ·
  <a href="README.am.md">አማርኛ</a>
</p>

# IBEX Harness

**ذاكرة وسياق مستضافان ذاتيًا لوكلاء الذكاء الاصطناعي متعددي المستأجرين.**

IBEX طبقة ذاكرة وسياق تعمل على بنيتك التحتية. وجّه وكيلك إلى نقطة نهاية متوافقة مع OpenAI أو أضف خادم MCP: يحل IBEX
هوية المستأجر والوكيل، ويحقن سياقًا محدودًا، ويخزّن ذاكرات محكومة، ويرفق دليلًا بكل طلب.

## لماذا IBEX

- **الهوية في كل استدعاء.** لا يُقبل `org_id` أبدًا من عنوان URL أو المتصفح. AuthService هو المرجع، وكل مسار بيانات
  يصفّي المستأجر صراحةً.
- **سياق محدود، لا تكديس مطالبات.** تسترجع طبقة تجميع السياق الذاكرات والتوجيهات وترتبها وتعبّئها ضمن ميزانية رموز
  وموعد نهائي، وتتراجع إلى سياق التوجيهات فقط بدلًا من تعطيل الوسيط.
- **دليل مرفق بالطلب.** تنتقل التتبعات وحالة التنقيح ووضع الالتقاط وحالة النشر مع التشغيل.

## البدء السريع

المتطلبات: Docker Compose v2 أو Podman Compose وGNU Make والإصدارات في
[`infra/tool-versions.conf`](infra/tool-versions.conf).

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness
make setup
make check-tools
make compose-dev-up
make db-migrate
make db-seed
```

شغّل AuthService والوسيط في طرفيتين بالأوامر الواردة في
[`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services)، ثم نفّذ:

```bash
make dev-smoke
```

لوحة التحكم:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

افتح `http://127.0.0.1:3000`. لوحة التحكم للقراءة فقط وتفشل بأمان دون جلسة مشغّل و`IBEX_OPERATOR_API_ORIGIN`.

## الخدمات

| الخدمة | وقت التشغيل | الحالة |
| --- | --- | --- |
| الوسيط | Go | منفّذ محليًا؛ دليل SLO المستضاف معلّق |
| AuthService | Go | منفّذ محليًا؛ إدارة مفاتيح الإنتاج معلّقة |
| الذاكرة | Python / FastAPI | منفّذة محليًا |
| تجميع السياق | Python / gRPC | مؤقت |
| Embedder | Python | منفّذ أو تجريبي حسب الملف التعريفي |
| واجهة الإدارة | Python / FastAPI | مثبّتة ومختبرة؛ واجهات المشغّل مؤقتة |
| Workers | Python / Celery | مختلط |
| لوحة التحكم | Nuxt 4 + Nitro | مؤقتة؛ 3 من 10 واجهات أساسية بمسار قراءة حي |

القائمة الكاملة في [`services/README.md`](services/README.md).

## الوثائق

- [البنية](engineering/ARCHITECTURE.md)
- [دليل التطوير](engineering/DEVELOPMENT_GUIDE.md)
- [متغيرات البيئة](engineering/ENVIRONMENT_VARIABLES.md)
- [الأمان](engineering/SECURITY.md)
- [الحالة والأدلة](https://ibexharness.com/docs/architecture/status-and-evidence)
- [المساهمة](CONTRIBUTING.md)

يميّز IBEX بين **منفّذ** و**مثبّت لكن مؤقت** و**محدّد غير منفّذ** و**مؤجّل**. المسارات المحلية والمخططات وبيانات
الاختبار ومستندات التصميم ليست دليل نشر.

## الأمان وعزل المستأجرين

- عزل متعدد الطبقات: RLS في PostgreSQL مع تصفية `org_id` صريحة.
- القراءات عبر المستأجرين تعيد `404` وليس `403`.
- لا تصل الأسرار أبدًا إلى السجلات أو التتبعات أو إعدادات المتصفح أو بيانات الاختبار.
- محتوى الذاكرة مدخل غير موثوق: يُحجر عليه ولا يُعامل كتعليمات.
- أبلغ عن الثغرات عبر العملية الخاصة في [`engineering/SECURITY.md`](engineering/SECURITY.md).

## الترخيص

[MIT](LICENSE)

---

[README الإنجليزي المرجعي](README.md)
