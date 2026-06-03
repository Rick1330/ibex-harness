# IBEX Harness - Toolchain

## 1) Purpose

This document defines the local tools required to work on IBEX Harness. The goal is a predictable setup where local commands match CI as closely as possible.

Run the repository command surface from the root `Makefile` where possible:

```bash
make help
```

---

## 2) Required tools

| Tool | Minimum | Why it is required |
| --- | --- | --- |
| Git | 2.40+ | Source control and PR workflow |
| Docker Engine + Docker Compose | Docker 24+, Compose v2 | Local Postgres, Redis, ClickHouse, and MinIO |
| Go | 1.25.11+ | Go services (`auth`, `proxy`, future CLI); must match `go.mod` |
| GNU Make | any POSIX `make` implementation | Canonical command surface (`Makefile`) used by developers and CI; on Windows prefer running via Git Bash or install a compatible `make` implementation |
| Node.js | 18+ | `markdownlint-cli2` and future dashboard |
| Python | 3.11+ | Future Python services and optional tooling |
| Buf CLI | 1.47+ | Protobuf linting and breaking-change checks |
| Bash | Git Bash, macOS bash, or Linux shell | Root `Makefile` targets and repo guards |

## 3) Optional tools

| Tool | Why it helps |
| --- | --- |
| Gitleaks | Run secret scans before pushing; CI always runs it |
| pre-commit | Run fast local checks before every commit |
| act | Dry-run GitHub Actions locally where Docker support is available |

---

## 4) Installation

### 4.1 Windows

Use PowerShell. Install Git Bash because Make targets run POSIX shell scripts. If `make` is not available, install Git for Windows (includes Git Bash) or install `make` via Chocolatey/winget. Prefer running `make` inside Git Bash to match CI behavior.

```powershell
winget install --id Git.Git -e
winget install --id Docker.DockerDesktop -e
winget install --id GoLang.Go -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Python.Python.3.11 -e
winget install --id Bufbuild.Buf -e
winget install --id Gitleaks.Gitleaks -e
```

If `winget` does not provide a package in your environment, Chocolatey equivalents are:

```powershell
choco install git docker-desktop golang nodejs-lts python311 buf gitleaks -y
```

After installing Docker Desktop, start it once from the Windows UI and confirm Docker Compose v2 is available.

### 4.2 macOS

```bash
brew install git go node python@3.11 bufbuild/buf/buf gitleaks pre-commit act
brew install --cask docker
```

Start Docker Desktop before running compose commands.

### 4.3 Linux

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y git make curl ca-certificates gnupg python3.11 python3-pip nodejs npm golang-go
```

Install Docker Engine and the Compose plugin using Docker's official packages for your distribution:

```bash
docker version
docker compose version
```

Install Buf:

```bash
curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.47.2/buf-Linux-x86_64" -o /tmp/buf
sudo install -m 0755 /tmp/buf /usr/local/bin/buf
```

Install Gitleaks:

```bash
curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.24.3/gitleaks_8.24.3_linux_x64.tar.gz \
  | sudo tar -xz -C /usr/local/bin gitleaks
```

Fedora/RHEL:

```bash
sudo dnf install -y git make curl python3.11 nodejs npm golang
```

Install Docker, Buf, and Gitleaks with the official upstream packages or release binaries for your architecture.

---

## 5) Sanity check

Run these commands from any shell. Version numbers may be newer than the minimums listed above.

```bash
git --version
docker version
docker compose version
go version
node --version
npm --version
python --version
buf --version
```

Expected:

- `git --version` prints Git `2.40` or newer.
- `docker version` reports a reachable Docker server.
- `docker compose version` prints Compose `v2...`.
- `go version` prints `go1.22` or newer.
- `node --version` prints `v18...` or newer.
- `python --version` prints `3.11...` or newer.
- `buf --version` prints `1.47...` or newer.

Optional:

```bash
gitleaks version
pre-commit --version
act --version
```

---

## 6) Repository checks

From the repository root:

```bash
make help
make repo-guards
make lint-docs
make proto-lint
make compose-dev-ps
```

Run a local secret scan when Gitleaks is installed:

```bash
make security-scan
```

Start local dependencies:

```bash
make compose-dev-up
make compose-dev-down
```

Apply Postgres schema (after compose is healthy):

```bash
make db-migrate
make db-version
```

Integration tests for migrations (requires [test compose](../../infra/compose/test/docker-compose.yml) on port 5433):

```bash
make compose-test-up
go test -tags=integration ./infra/migrations/postgres/...
```

---

## 7) Troubleshooting

If `make` is missing on Windows, install GNU Make (for example `winget install GnuWin32.Make` or Chocolatey `make`) and run `make` from Git Bash. Git for Windows does not include GNU Make by itself.

If Docker commands fail with connection errors, start Docker Desktop or the Docker daemon and retry `docker version`.

If `buf breaking` fails with network or authentication errors, verify GitHub access to `https://github.com/Rick1330/ibex-harness.git` and retry from `packages/proto`.
