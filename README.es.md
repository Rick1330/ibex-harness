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

**Memoria y contexto autoalojados para agentes de IA multiinquilino.**

IBEX es una capa de memoria y contexto que se ejecuta en tu propia infraestructura. Apunta tu agente a un endpoint
compatible con OpenAI o añade el servidor MCP: IBEX resuelve la identidad del inquilino y del agente, inyecta contexto
acotado, almacena memorias gobernadas e intenta registrar, como mejor esfuerzo, evidencia posterior a la respuesta de
las sesiones gobernadas cuando el plano de evidencia PostgreSQL está configurado.

## Por qué IBEX

- **Identidad en cada llamada.** El `org_id` nunca se acepta desde una URL o el navegador. AuthService es la autoridad y
  cada ruta de datos filtra el inquilino de forma explícita.
- **Contexto acotado, no un volcado de prompt.** La ensambladura recupera, ordena y empaqueta memorias y directivas
  dentro de un presupuesto de tokens y un plazo, y degrada a contexto de solo directivas en lugar de bloquear el proxy.
- **Evidencia posterior a la respuesta, como mejor esfuerzo.** Con el plano PostgreSQL configurado y la versión de fence
  de evidencia autoritativa de la sesión disponible, las solicitudes gobernadas de finalización de chat intentan
  escribir una fila en el outbox tras la respuesta; no hace falta cerrar la sesión antes. La evidencia puede retenerse
  si falta la sesión o su fence, o perderse por un fallo de persistencia, una cola limitada saturada o un apagado antes
  del drenaje. El relay está desactivado por defecto; no se afirma un acknowledgement durable antes de la respuesta.

## Inicio rápido

Requisitos: Docker Compose v2 o Podman Compose, GNU Make y las versiones de
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

Inicia AuthService y el proxy en dos terminales con los comandos de
[`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services), y después ejecuta:

```bash
make dev-smoke
```

Consola:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

Abre `http://127.0.0.1:3000`. La consola es de solo lectura y falla cerrada sin una sesión de operador y
`IBEX_OPERATOR_API_ORIGIN`.

## Servicios

| Servicio | Runtime | Estado |
| --- | --- | --- |
| Proxy | Go | Implementado en local; evidencia de SLO alojado pendiente |
| AuthService | Go | Implementado en local; gestión de claves de producción pendiente |
| Memoria | Python / FastAPI | Implementado en local |
| Ensambladura de contexto | Python / gRPC | Provisional |
| Embedder | Python | Implementado o experimental según el perfil |
| API de gestión | Python / FastAPI | Montada y probada; superficies de operador provisionales |
| Workers | Python / Celery | Mixto |
| Consola | Nuxt 4 + Nitro | Provisional; 8 de 10 superficies principales con lectura en vivo |

El inventario completo está en [`services/README.md`](services/README.md).

## Documentación

- [Arquitectura](engineering/ARCHITECTURE.md)
- [Guía de desarrollo](engineering/DEVELOPMENT_GUIDE.md)
- [Variables de entorno](engineering/ENVIRONMENT_VARIABLES.md)
- [Seguridad](engineering/SECURITY.md)
- [Estado y evidencia](https://ibexharness.com/docs/architecture/status-and-evidence)
- [Contribuir](CONTRIBUTING.md)

IBEX distingue entre **implementado**, **montado pero provisional**, **especificado sin implementar** y **diferido**.
Las rutas locales, esquemas, fixtures y documentos de diseño no son evidencia de despliegue.

## Seguridad y multinquilino

- Aislamiento por inquilino en profundidad: RLS de PostgreSQL más filtrado explícito de `org_id`.
- Las lecturas entre inquilinos devuelven `404`, no `403`.
- Los secretos nunca llegan a logs, trazas, configuración del navegador ni fixtures.
- El contenido de memoria es entrada no confiable: se pone en cuarentena y nunca se trata como instrucciones.
- Reporta vulnerabilidades mediante el proceso privado de [`engineering/SECURITY.md`](engineering/SECURITY.md).

## Licencia

[MIT](LICENSE)

---

[README canónico en inglés](README.md)
