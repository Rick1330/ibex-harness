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

**ለብዙ ተከራይ የ AI ወኪሎች በራስ የሚስተናገድ ትውስታ እና አውድ።**

IBEX በራስዎ መሠረተ ልማት ላይ የሚሠራ የትውስታ እና አውድ ንብርብር ነው። ወኪልዎን ከ OpenAI ጋር ተኳሃኝ ወደሆነ የመጨረሻ ነጥብ
ያገናኙ ወይም የ MCP አገልጋዩን ይጨምሩ፦ IBEX የተከራይና የወኪል ማንነትን ይፈታል፣ የተገደበ አውድ ያስገባል፣ የተቆጣጠሩ ትውስታዎችን
ያከማቻል፣ እና ለእያንዳንዱ ጥያቄ ማስረጃ ያያይዛል።

## ለምን IBEX

- **በእያንዳንዱ ጥሪ ማንነት።** `org_id` ከURL ወይም ከአሳሽ ፈጽሞ አይቀበልም። AuthService ስልጣኑ ነው፣ እና እያንዳንዱ የውሂብ መንገድ
  ተከራዩን በግልጽ ያጣራል።
- **የተገደበ አውድ፣ የፕሮምፕ ክምር አይደለም።** የአውድ ማሰባሰቢያው ትውስታዎችንና መመሪያዎችን በቶከን በጀትና በጊዜ ገደብ
  ውስጥ ያመጣል፣ ያስተካክላል፣ እና ያሸጋግራል፤ ሲወድቅ ፕሮክሲውን ከማገድ ይልቅ ወደ መመሪያ-ብቻ አውድ ይወርዳል።
- **ከጥያቄው ጋር የተያዘ ማስረጃ።** ትሬሶች፣ የስደብ ሁኔታ፣ የመያዣ ሁነታ እና የህትመት ሁኔታ ከሂደቱ ጋር ይጓዛሉ።

## ፈጣን መጀመሪያ

ቅድመ ሁኔታዎች፦ Docker Compose v2 ወይም Podman Compose፣ GNU Make፣ እና በ
[`infra/tool-versions.conf`](infra/tool-versions.conf) የተገለጹት ስሪቶች።

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness
make setup
make check-tools
make compose-dev-up
make db-migrate
make db-seed
```

AuthService እና ፕሮክሲውን በሁለት ተርሚናሎች በ
[`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services) ውስጥ በተገለጹት ትዕዛዞች ያስጀምሩ፣ ከዚያ
ያሂዱ፦

```bash
make dev-smoke
```

ኮንሶል፦

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

`http://127.0.0.1:3000` ይክፈቱ። ኮንሶሉ አንባቢ-ብቻ ነው፤ የኦፕሬተር ክፍለ-ጊዜ እና `IBEX_OPERATOR_API_ORIGIN` ከሌለ በደህንነት
ይወድቃል።

## አገልግሎቶች

| አገልግሎት | ማስኬጃ | ሁኔታ |
| --- | --- | --- |
| ፕሮክሲ | Go | በአካባቢ ተተግብሯል፤ የተስተናገደ SLO ማስረጃ ይቀራል |
| AuthService | Go | በአካባቢ ተተግብሯል፤ የምርት ቁልፍ አስተዳደር ይቀራል |
| ትውስታ | Python / FastAPI | በአካባቢ ተተግብሯል |
| የአውድ ማሰባሰቢያ | Python / gRPC | ጊዜያዊ |
| Embedder | Python | እንደ መገለጫው ተተግብሯል ወይም ሙከራዊ |
| የአስተዳደር API | Python / FastAPI | ተጭኗል እና ተፈትኗል፤ የኦፕሬተር ገጽታዎች ጊዜያዊ |
| Workers | Python / Celery | የተቀላቀለ |
| ኮንሶል | Nuxt 4 + Nitro | ጊዜያዊ፤ ከ10 ዋና ገጽታዎች 3ቱ ቀጥታ የንባብ መንገድ አላቸው |

ሙሉ ዝርዝሩ በ [`services/README.md`](services/README.md) ውስጥ ነው።

## ሰነዶች

- [አርክቴክቸር](engineering/ARCHITECTURE.md)
- [የልማት መመሪያ](engineering/DEVELOPMENT_GUIDE.md)
- [የአካባቢ ተለዋዋጮች](engineering/ENVIRONMENT_VARIABLES.md)
- [ደህንነት](engineering/SECURITY.md)
- [ሁኔታ እና ማስረጃ](https://ibexharness.com/docs/architecture/status-and-evidence)
- [አስተዋጽኦ](CONTRIBUTING.md)

IBEX **ተተግብሯል**፣ **ተጭኗል ግን ጊዜያዊ**፣ **ተገልጿል ግን አልተተገበረም** እና **ተላልፏል** የሚሉትን ይለያል። የአካባቢ
መንገዶች፣ ሼማዎች፣ የሙከራ ውሂብ እና የንድፍ ሰነዶች የማሰማራት ማስረጃ አይደሉም።

## ደህንነት እና የተከራይ መለያየት

- ጥልቅ መከላከያ፦ PostgreSQL RLS እና ግልጽ `org_id` ማጣራት።
- ከተከራይ ወደ ተከራይ ንባቦች `404` ይመልሳሉ፣ `403` አይደለም።
- ምስጢሮች ወደ ሎግ፣ ትሬስ፣ የአሳሽ ውቅር ወይም የሙከራ ውሂብ ፈጽሞ አይደርሱም።
- የትውስታ ይዘት የማይታመን ግብዓት ነው፦ ይነጠላል እና እንደ መመሪያ ፈጽሞ አይታይም።
- ተጋላጭነቶችን በ [`engineering/SECURITY.md`](engineering/SECURITY.md) የግል ሂደት ያሳውቁ።

## ፈቃድ

[MIT](LICENSE)

---

[መሠረታዊው የእንግሊዝኛ README](README.md)
