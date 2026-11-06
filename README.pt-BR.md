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

**Memória e contexto auto-hospedados para agentes de IA multilocatários.**

IBEX é uma camada de memória e contexto executada na sua própria infraestrutura. Aponte seu agente para um endpoint
compatível com OpenAI ou adicione o servidor MCP: o IBEX resolve a identidade do locatário e do agente, injeta contexto
limitado, armazena memórias governadas e tenta, como melhor esforço, registrar evidências após a resposta para sessões
governadas quando o plano de evidências PostgreSQL está configurado.

## Por que IBEX

- **Identidade em cada chamada.** O `org_id` nunca é aceito de uma URL ou do navegador. O AuthService é a autoridade e
  cada caminho de dados filtra o locatário explicitamente.
- **Contexto limitado, não um despejo de prompt.** A montagem de contexto recupera, ordena e empacota memórias e
  diretivas dentro de um orçamento de tokens e de um prazo, degradando para contexto somente de diretivas em vez de
  bloquear o proxy.
- **Evidência após a resposta, como melhor esforço.** Com o plano PostgreSQL configurado e a versão de fence de
  evidência autoritativa da sessão disponível, as requisições governadas de conclusão de chat tentam gravar uma linha no
  outbox após a resposta; não é necessário encerrar a sessão antes. A evidência pode ser retida quando falta a sessão ou
  a fence, ou perdida por falha de persistência, saturação da fila limitada ou desligamento antes do esvaziamento. O
  relay fica desativado por padrão; não há alegação de acknowledgement durável antes da resposta.

## Início rápido

Pré-requisitos: Docker Compose v2 ou Podman Compose, GNU Make e as versões de
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

Inicie o AuthService e o proxy em dois terminais com os comandos de
[`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services) e execute:

```bash
make dev-smoke
```

Console:

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

Abra `http://127.0.0.1:3000`. O console é somente leitura e falha fechado sem uma sessão de operador e
`IBEX_OPERATOR_API_ORIGIN`.

## Serviços

| Serviço | Runtime | Estado |
| --- | --- | --- |
| Proxy | Go | Implementado localmente; evidência de SLO hospedado pendente |
| AuthService | Go | Implementado localmente; gestão de chaves de produção pendente |
| Memória | Python / FastAPI | Implementado localmente |
| Montagem de contexto | Python / gRPC | Provisório |
| Embedder | Python | Implementado ou experimental conforme o perfil |
| API de gestão | Python / FastAPI | Montada e testada; superfícies de operador provisórias |
| Workers | Python / Celery | Misto |
| Console | Nuxt 4 + Nitro | Provisório; 8 de 10 superfícies principais com leitura ao vivo |

O inventário completo está em [`services/README.md`](services/README.md).

## Documentação

- [Arquitetura](engineering/ARCHITECTURE.md)
- [Guia de desenvolvimento](engineering/DEVELOPMENT_GUIDE.md)
- [Variáveis de ambiente](engineering/ENVIRONMENT_VARIABLES.md)
- [Segurança](engineering/SECURITY.md)
- [Status e evidências](https://ibexharness.com/docs/architecture/status-and-evidence)
- [Contribuir](CONTRIBUTING.md)

O IBEX distingue **implementado**, **montado, mas provisório**, **especificado sem implementação** e **adiado**. Rotas
locais, esquemas, fixtures e documentos de projeto não são evidência de implantação.

## Segurança e multilocação

- Isolamento em profundidade: RLS do PostgreSQL mais filtragem explícita de `org_id`.
- Leituras entre locatários retornam `404`, não `403`.
- Segredos nunca chegam a logs, traces, configuração do navegador ou fixtures.
- O conteúdo de memória é entrada não confiável: isolado e nunca tratado como instruções.
- Relate vulnerabilidades pelo processo privado em [`engineering/SECURITY.md`](engineering/SECURITY.md).

## Licença

[MIT](LICENSE)

---

[README canônico em inglês](README.md)
