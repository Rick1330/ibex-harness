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

**Mémoire et contexte auto-hébergés pour les agents IA multi-locataires.**

IBEX est une couche de mémoire et de contexte qui s'exécute sur votre propre infrastructure. Pointez votre agent vers
un point de terminaison compatible OpenAI ou ajoutez le serveur MCP : IBEX résout l'identité du locataire et de
l'agent, injecte un contexte borné, stocke des mémoires gouvernées et tente, au mieux, d'enregistrer une preuve après
la réponse pour les sessions gouvernées lorsque le plan de preuve PostgreSQL est configuré.

## Pourquoi IBEX

- **Identité à chaque appel.** L'`org_id` n'est jamais accepté depuis une URL ou le navigateur. AuthService fait
  autorité et chaque chemin de données filtre explicitement le locataire.
- **Contexte borné, pas un déversement de prompt.** L'assemblage récupère, classe et emballe mémoires et directives
  dans un budget de tokens et une échéance, puis se dégrade en contexte de directives plutôt que de bloquer le proxy.
- **Preuve après la réponse, au mieux.** Lorsque le plan PostgreSQL, une session durable et une clôture faisant autorité
  sont disponibles, les chemins gouvernés de chat et de session tentent d'écrire une ligne d'outbox après la réponse.
  La preuve peut être retenue si la session ou la clôture manque, ou perdue en cas d'échec de persistance, de file
  bornée saturée ou d'arrêt avant vidage. Le relais est désactivé par défaut ; aucun acquittement durable avant réponse
  n'est revendiqué.

## Démarrage rapide

Prérequis : Docker Compose v2 ou Podman Compose, GNU Make et les versions de
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

Démarrez AuthService et le proxy dans deux terminaux avec les commandes de
[`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services), puis lancez :

```bash
make dev-smoke
```

Console :

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

Ouvrez `http://127.0.0.1:3000`. La console est en lecture seule et échoue fermée sans session opérateur et
`IBEX_OPERATOR_API_ORIGIN`.

## Services

| Service | Runtime | État |
| --- | --- | --- |
| Proxy | Go | Implémenté en local ; preuve de SLO hébergé en attente |
| AuthService | Go | Implémenté en local ; gestion des clés de production en attente |
| Mémoire | Python / FastAPI | Implémenté en local |
| Assemblage de contexte | Python / gRPC | Provisoire |
| Embedder | Python | Implémenté ou expérimental selon le profil |
| API de gestion | Python / FastAPI | Montée et testée ; surfaces opérateur provisoires |
| Workers | Python / Celery | Mixte |
| Console | Nuxt 4 + Nitro | Provisoire ; 8 des 10 surfaces principales ont une lecture en direct |

L'inventaire complet se trouve dans [`services/README.md`](services/README.md).

## Documentation

- [Architecture](engineering/ARCHITECTURE.md)
- [Guide de développement](engineering/DEVELOPMENT_GUIDE.md)
- [Variables d'environnement](engineering/ENVIRONMENT_VARIABLES.md)
- [Sécurité](engineering/SECURITY.md)
- [État et preuves](https://ibexharness.com/docs/architecture/status-and-evidence)
- [Contribuer](CONTRIBUTING.md)

IBEX distingue **implémenté**, **monté mais provisoire**, **spécifié non implémenté** et **différé**. Les routes
locales, schémas, fixtures et documents de conception ne constituent pas une preuve de déploiement.

## Sécurité et multi-locataires

- Isolation en profondeur : RLS PostgreSQL et filtrage explicite de `org_id`.
- Les lectures entre locataires renvoient `404`, pas `403`.
- Les secrets n'atteignent jamais les logs, traces, configurations navigateur ou fixtures.
- Le contenu mémoire est une entrée non fiable : mis en quarantaine et jamais traité comme des instructions.
- Signalez les vulnérabilités via le processus privé de [`engineering/SECURITY.md`](engineering/SECURITY.md).

## Licence

[MIT](LICENSE)

---

[README canonique en anglais](README.md)
