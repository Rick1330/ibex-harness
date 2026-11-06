<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.pt-BR.md">Português (Brasil)</a> ·
  <a href="README.zh-CN.md">中文</a> ·
  <a href="README.ar.md">العربية</a>
</p>

# IBEX Harness

**Selbst gehosteter Speicher und Kontext für mandantenfähige KI-Agenten.**

IBEX ist eine Speicher- und Kontextschicht, die auf Ihrer eigenen Infrastruktur läuft. Richten Sie Ihren Agenten auf
einen OpenAI-kompatiblen Endpunkt oder fügen Sie den MCP-Server hinzu: IBEX löst Mandanten- und Agentenidentität auf,
injiziert begrenzten Kontext, speichert governierte Erinnerungen und versucht für governierte Sitzungen nach der
Antwort nach bestem Bemühen Evidenz zu schreiben, wenn die PostgreSQL-Evidenzebene konfiguriert ist.

## Warum IBEX

- **Identität bei jedem Aufruf.** Die `org_id` wird nie aus einer URL oder dem Browser übernommen. AuthService ist die
  Autorität, und jeder Datenpfad filtert den Mandanten explizit.
- **Begrenzter Kontext statt Prompt-Dumping.** Die Kontextmontage ruft Erinnerungen und Direktiven ab, ordnet sie und
  packt sie innerhalb eines Token-Budgets und einer Frist; bei Fehlern fällt sie auf Direktiven-Kontext zurück, statt
  den Proxy zu blockieren.
- **Evidenz nach der Antwort, nach bestem Bemühen.** Wenn die PostgreSQL-Evidenzebene sowie eine dauerhafte Sitzung und
  ein maßgeblicher Fence vorhanden sind, versuchen governierte Chat- und Sitzungspfade nach der Antwort eine Outbox-Zeile
  zu schreiben. Bei fehlender Sitzung oder fehlendem Fence wird Evidenz zurückgehalten; bei Persistenzfehlern, voller
  begrenzter Warteschlange oder Herunterfahren vor dem Leeren kann sie verloren gehen. Das Relay ist standardmäßig
  deaktiviert; eine synchrone dauerhafte Bestätigung vor der Antwort wird nicht behauptet.

## Schnellstart

Voraussetzungen: Docker Compose v2 oder Podman Compose, GNU Make und die Versionen aus
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

Starten Sie AuthService und den Proxy in zwei Terminals mit den Befehlen aus
[`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services), und führen Sie dann aus:

```bash
make dev-smoke
```

Konsole:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

Öffnen Sie `http://127.0.0.1:3000`. Die Konsole ist schreibgeschützt und schlägt ohne Operator-Sitzung und
`IBEX_OPERATOR_API_ORIGIN` geschlossen fehl.

## Dienste

| Dienst | Runtime | Status |
| --- | --- | --- |
| Proxy | Go | Lokal implementiert; Hosted-SLO-Evidenz offen |
| AuthService | Go | Lokal implementiert; Produktions-Schlüsselverwaltung offen |
| Speicher | Python / FastAPI | Lokal implementiert |
| Kontextmontage | Python / gRPC | Vorläufig |
| Embedder | Python | Je nach Profil implementiert oder experimentell |
| Management-API | Python / FastAPI | Eingebunden und getestet; Operator-Oberflächen vorläufig |
| Worker | Python / Celery | Gemischt |
| Konsole | Nuxt 4 + Nitro | Vorläufig; 8 von 10 Kernoberflächen mit Live-Lesepfad |

Die vollständige Übersicht steht in [`services/README.md`](services/README.md).

## Dokumentation

- [Architektur](engineering/ARCHITECTURE.md)
- [Entwicklungsleitfaden](engineering/DEVELOPMENT_GUIDE.md)
- [Umgebungsvariablen](engineering/ENVIRONMENT_VARIABLES.md)
- [Sicherheit](engineering/SECURITY.md)
- [Status und Evidenz](https://ibexharness.com/docs/architecture/status-and-evidence)
- [Mitwirken](CONTRIBUTING.md)

IBEX unterscheidet **implementiert**, **eingebunden, aber vorläufig**, **spezifiziert, nicht implementiert** und
**zurückgestellt**. Lokale Routen, Schemata, Fixtures und Entwurfsdokumente sind keine Deployment-Evidenz.

## Sicherheit und Mandantentrennung

- Mandantentrennung in der Tiefe: PostgreSQL-RLS plus explizite `org_id`-Filterung.
- Mandantenübergreifende Lesezugriffe liefern `404`, nicht `403`.
- Geheimnisse gelangen nie in Logs, Traces, Browserkonfiguration oder Fixtures.
- Speicherinhalte sind nicht vertrauenswürdige Eingaben: isoliert und nie als Anweisungen behandelt.
- Melden Sie Schwachstellen über den privaten Prozess in [`engineering/SECURITY.md`](engineering/SECURITY.md).

## Lizenz

[MIT](LICENSE)

---

[Kanonische englische README](README.md)
