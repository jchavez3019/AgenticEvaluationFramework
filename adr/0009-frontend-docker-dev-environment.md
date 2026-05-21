---
status: proposed
date: 2026-05-18
decision-makers: jorgejc2
---

# Frontend Docker Dev Environment and Backend Access Pattern

## Context and Problem Statement

The Angular dashboard is the only component of this framework that ships inside a Docker container in v1. The high-level architecture document (§9.5) records two binding constraints:

1. The container runs **`ng serve` in dev mode only** — no production build artifact is shipped.
2. The backend (`uv` + FastAPI), the CLI, the database (SQLite, embedded), and the Celery + Redis broker (when used) all run **outside** the container.

The first constraint exists to neutralize Node.js / Angular CLI / TypeScript version drift across contributor machines. The second exists because SQLite is an embedded engine (per ADR-0006), the backend is `uv`-managed (per ADR-0002), and there is therefore nothing left to containerize. Specifically, this means **no Docker Compose** in v1 — there is only one container, run with `docker run`.

Without an ADR pinning the dev container's shape, a few predictable problems materialize:

- The container is built with `node:lts` and the LTS version drifts under everyone's feet, defeating the point.
- File-system ownership mismatches (root inside container, `1000:1000` outside) make `node_modules` and Angular's cache unwriteable on Linux hosts.
- The container's `ng serve` cannot reach the backend running on the host because of misconfigured `--host`/`--proxy-config`.
- Hot module replacement breaks because the host's filesystem is bind-mounted but the inotify watch limit is too low and the container falls back to slow polling.
- The Knowledge Base manifest generation and OpenAPI codegen scripts (per ADR-0008) work outside the container but not inside, or vice versa, producing committed-but-stale artifacts.

This ADR pins the dev container, the bind-mount strategy, the backend access pattern, the proxy configuration, and the developer ergonomics around it.

## Decision

Ship a single-purpose **Angular dev-mode Docker container** for the frontend, accessed via `docker run` (no Compose), with the backend, CLI, and SQLite persistence running on the host.

### 1. The container

- **Base image:** `node:22-bookworm-slim` (the active Node.js LTS at the time of this ADR; the `Dockerfile` pins the exact major version so a `docker pull` in six months does not silently jump to Node 24).
- **Working dir:** `/workspace/frontend`.
- **Installed:**
  - The `node` user from the base image (UID 1000 by default, which matches the typical Linux dev host).
  - `git` (for `npm install` packages that pull from git refs).
  - `chromium` (for Playwright e2e tests; optional via a build arg `INSTALL_E2E=1`).
- **Not installed:** Python, `uv`, the backend, SQLite tooling. None of those belong in this image.
- **Entrypoint:** `npm run start` (which delegates to `ng serve --host 0.0.0.0 --port 4200 --poll 2000 --proxy-config proxy.conf.json`).
- **Healthcheck:** an HTTP probe against `http://localhost:4200` inside the container.

The Dockerfile is intentionally short. The image is a _frozen toolchain_, not an application bundle: the application's source code lives on the host and is bind-mounted into `/workspace/frontend` at runtime.

### 2. Bind mounts and `node_modules` strategy

```
host:./frontend        →  /workspace/frontend   (read-write, source)
host:<named volume>    →  /workspace/frontend/node_modules  (read-write, container-owned)
```

- The source tree is bind-mounted so edits in the host editor reach `ng serve` immediately.
- `node_modules` lives in a **named Docker volume**, not the bind-mounted host directory, for two reasons:
  1. Cross-platform binary differences: a Linux container reading a `node_modules` populated on macOS or Windows breaks for native modules. Keeping `node_modules` inside a container-managed volume avoids this entirely.
  2. Performance: `node_modules` has tens of thousands of small files. A named volume is dramatically faster than a bind mount on macOS (Docker Desktop's bind-mount throughput remains a known pain point).
- The volume is named `aef-frontend-node-modules`. A `make frontend-clean` target removes it when a fresh install is needed.
- The user inside the container is `node` (UID 1000). Linux hosts where the developer's UID is also 1000 (the default for many distributions) get unmangled file ownership for free. Hosts where it is not get a one-line override via `--user $(id -u):$(id -g)` documented in the README.

### 3. Backend access pattern

The Angular dev server proxies API and WebSocket traffic to the backend running on the host. Three rules:

1. The container runs with `--add-host=host.docker.internal:host-gateway` on Linux (Docker Desktop already wires this on macOS/Windows). `host.docker.internal:8000` therefore resolves to the host's backend from inside the container.
2. The Angular CLI's proxy config (`frontend/proxy.conf.json`) routes `/api` and `/ws` to `http://host.docker.internal:8000` and `ws://host.docker.internal:8000` respectively. Components and the generated API client never use absolute URLs — they call `/api/...` and let the proxy do the work.
3. The `environment.ts` file's `apiBaseUrl` is therefore the empty string in dev (proxy handles routing). A future production build (out of scope here) would set it to the real backend URL.

This means: a developer runs the backend on the host (`uv run aef-api` or `uvicorn aef.api.app:app --reload`), runs the dev container, and the dashboard at `http://localhost:4200` works against the running backend without any further configuration.

**The proxy is the only documented client path in v1.** The FastAPI server intentionally does **not** enable CORS (per [ADR-0002](0002-backend-technology-stack.md)), so a browser hitting `http://localhost:8000` directly from a different origin is blocked. This keeps the v1 surface tight; a future cross-origin deployment opens a follow-up ADR.

### 4. SQLite, persistence, and `outputs/`

- The dashboard never reads SQLite directly (per ADR-0006). All persistence access is through the backend API, which lives on the host.
- The `outputs/` tree (per ADR-0007) lives on the host, written by the backend / CLI. The frontend container does not touch it.
- The frontend container does not need any backend filesystem access. Its only filesystem needs are its own source tree and `node_modules`.

### 5. Why no Docker Compose, no Compose-managed backend, no Compose-managed Redis

- **Compose is not justified by a single container.** Compose's value is wiring multiple services. With one container, `docker run` is simpler.
- **The backend is `uv`-managed deliberately.** The `uv.lock` already pins every Python dependency exactly. Adding a Docker layer on top would add overhead without adding reproducibility.
- **SQLite is embedded.** There is no SQLite _service_ to spin up.
- **Redis is only required when the user opts into the distributed engine.** When that day comes, the Redis container is added behind a separate ADR or Compose file (see `revisit triggers` below). It is intentionally _not_ part of the v1 frontend dev experience because most evaluation runs land on the local engine.
- **Network namespace simplicity.** With one container and the backend on the host, "backend at `host.docker.internal:8000`" is a single, durable rule. Compose's separate networks would force the backend into a container too, undoing rule §3.

If a contributor wants to run the backend in a container for any reason (CI, reproducibility experiments), nothing stops them — but that is a personal-environment decision, not a framework default.

### 6. Developer ergonomics

- A `make frontend` target in the repo root brings the container up:

  ```bash
  docker run --rm -it \
    --name aef-frontend \
    --add-host=host.docker.internal:host-gateway \
    -p 4200:4200 \
    -v "$(pwd)/frontend:/workspace/frontend" \
    -v aef-frontend-node-modules:/workspace/frontend/node_modules \
    aef/frontend:dev
  ```

  The `Makefile` (or a small wrapper script) hides this command from day-to-day use, but the flags are intentional:

  | Flag                                                            | Meaning in this command                                                                                                                                                            |
  | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | `--rm`                                                          | Delete the container filesystem when it exits. The source code and `node_modules` volume remain; only the disposable container wrapper is removed.                                 |
  | `-it`                                                           | Allocate an interactive terminal so `ng serve` logs stream cleanly and `Ctrl+C` stops the dev server. `-i` keeps stdin open; `-t` allocates a pseudo-TTY.                          |
  | `--name aef-frontend`                                           | Gives the running container a stable name so `make frontend-shell`, `docker logs aef-frontend`, and cleanup commands can target it.                                                |
  | `--add-host=host.docker.internal:host-gateway`                  | On Linux, maps the hostname `host.docker.internal` to the host machine. This lets the Angular dev server proxy `/api` and `/ws` to the backend running on the host at port `8000`. |
  | `-p 4200:4200`                                                  | Publishes container port `4200` to host port `4200`, so the dashboard is reachable at `http://localhost:4200`.                                                                     |
  | `-v "$(pwd)/frontend:/workspace/frontend"`                      | Bind-mounts the host's `frontend/` source tree into the container. Edits in Cursor are immediately visible to `ng serve`.                                                          |
  | `-v aef-frontend-node-modules:/workspace/frontend/node_modules` | Mounts a named Docker volume for dependencies. This avoids bind-mounting host `node_modules`, which is slower and can contain platform-specific binaries.                          |
  | `aef/frontend:dev`                                              | Runs the locally built dev image, whose entrypoint starts `npm run start`.                                                                                                         |

- A first-run convenience target `make frontend-install` runs `npm install` inside the container so `node_modules` is populated in the named volume before the first `ng serve`.
- A `make frontend-codegen` target runs `npm run codegen` (per ADR-0008) inside the container against the host's running backend at `http://host.docker.internal:8000/openapi.json`.
- A `make frontend-clean` target removes the `aef-frontend-node-modules` volume so the next start does a clean install.
- A `make frontend-shell` target opens a bash shell inside the running container for ad-hoc debugging.
- All four targets work identically on Linux and macOS hosts. Windows is supported via WSL2 (the assumed dev environment for Windows users); native Windows Docker is not in scope.

### 7. CI integration

- CI builds the dev image with the same Dockerfile so the CI environment matches local. The container's `npm run check` (lint + format + tsc + tests) runs as a single CI step.
- CI does NOT run `ng build`. There is no production artifact to validate.
- The Playwright e2e suite is gated behind `INSTALL_E2E=1` at image build time and behind the `e2e` test marker per ADR-0011. The e2e job builds the container with `INSTALL_E2E=1`, runs the backend in `mock` mode on the CI runner, and points the proxy at `http://host.docker.internal:8000`.

### Non-goals

- We are NOT producing or shipping a production build artifact in v1.
- We are NOT introducing Docker Compose in v1.
- We are NOT containerizing the backend, the CLI, SQLite, or Redis in v1.
- We are NOT supporting a "remote dashboard" deployment in v1. The dev container is for individual contributors against their own host's backend.
- We are NOT shipping a multi-stage `Dockerfile` with a production target (it would imply a `prod` build the rest of the framework does not consume).
- We are NOT publishing the dev image to a public registry. Contributors `docker build` it locally.

## Consequences

- Good, because Node.js / Angular CLI / TypeScript version drift across machines is _eliminated_ — the Dockerfile is the single source of truth.
- Good, because `node_modules` in a named volume sidesteps the macOS bind-mount performance trap and the cross-platform native-module problem in one move.
- Good, because the `host.docker.internal` rule makes "where is the backend?" a single, never-changing question.
- Good, because keeping the backend on the host preserves the `uv` workflow and lets contributors use whatever Python REPL / debugger / IDE setup they already have.
- Good, because no Compose means a one-command bring-up. Compose's value is multi-service orchestration; the framework's v1 deployment is single-service.
- Bad, because `--add-host=host.docker.internal:host-gateway` is required on Linux. We document it in the README and in the `make` target so developers do not type it.
- Bad, because the e2e suite needing Chromium adds image-build time when `INSTALL_E2E=1`. Mitigation: gate it behind a build arg and skip in normal dev.
- Bad, because Windows (without WSL2) is unsupported. Mitigation: WSL2 is the documented Windows path; the WSL2 environment behaves like Linux for this purpose.
- Neutral, because contributors who want to containerize the backend can do so themselves; the framework simply does not require it.

## Implementation Plan

- **Affected paths**:
  - `frontend/Dockerfile` — the dev image.
  - `frontend/.dockerignore` — at minimum `node_modules`, `dist`, `.angular`, coverage outputs.
  - `frontend/proxy.conf.json` — proxy rules for `/api` (HTTP) and `/ws` (WebSocket) → `host.docker.internal:8000`.
  - `frontend/package.json` — `start` script invokes `ng serve --host 0.0.0.0 --port 4200 --poll 2000 --proxy-config proxy.conf.json`.
  - `Makefile` (repo root) — targets `frontend`, `frontend-install`, `frontend-codegen`, `frontend-clean`, `frontend-shell`.
  - `frontend/src/environments/environment.ts` — `apiBaseUrl: ''` in dev.
  - `frontend/README.md` — quickstart that documents `make frontend-install && make frontend`.
  - `.github/workflows/frontend-ci.yaml` (or equivalent) — builds the image, runs `npm run check`, runs Playwright e2e in the gated job.
- **Dependencies**: nothing beyond what ADR-0008 already pins.
- **Patterns to follow**:
  - The Dockerfile pins the exact Node.js major version. Bumping it is a tracked change.
  - All `make frontend-*` targets are idempotent.
  - The proxy config is the only place where backend URLs appear in dev.
  - All e2e runs use `mock` model and dataset adapters (per ADR-0011) to avoid GPU / network coupling.
- **Patterns to avoid**:
  - Do NOT add Docker Compose in v1.
  - Do NOT add a backend container in v1.
  - Do NOT bind-mount `node_modules` from the host into the container.
  - Do NOT hardcode `host.docker.internal:8000` inside source code; it lives in the proxy config only.
  - Do NOT build a `prod` target in the Dockerfile in v1.
- **Configuration**:
  - `AEF_API_URL` — optional override consumed by `proxy.conf.json` for non-default backend addresses (e.g., remote dev). Default `http://host.docker.internal:8000`.
  - `INSTALL_E2E` — Docker build arg controlling whether Chromium and Playwright are installed.
- **Migration steps**: greenfield.

### Verification

- [ ] `make frontend-install && make frontend` brings up the dashboard at `http://localhost:4200` with a backend running at `http://localhost:8000` on the host.
- [ ] The Dockerfile pins an exact Node.js major version (e.g., `node:22-bookworm-slim`), not `node:lts`.
- [ ] The container runs as the `node` user (or a documented `--user $(id -u):$(id -g)` override) — never as root.
- [ ] `frontend/proxy.conf.json` routes `/api` and `/ws` to `host.docker.internal:8000` over HTTP and WebSocket respectively.
- [ ] No file under `frontend/src/` references `host.docker.internal` directly.
- [ ] `node_modules` lives in a named Docker volume (`aef-frontend-node-modules`), not in the bind-mounted host directory.
- [ ] The `Dockerfile` does NOT install Python, `uv`, or any backend dependencies.
- [ ] No `docker-compose.yaml` exists at the repo root.
- [ ] CI builds the image and runs `npm run check` inside it; the job fails when lint, prettier, tsc, or unit tests fail.
- [ ] Playwright e2e suite, gated by `INSTALL_E2E=1` and the `e2e` marker (per ADR-0011), runs against the backend in mock mode and exercises a full evaluation run.
- [ ] `make frontend-clean` removes `aef-frontend-node-modules`; the next `make frontend-install` repopulates it.

## Alternatives Considered

- **Docker Compose with backend + Redis + frontend**: rejected for v1. Compose's value is multi-service wiring; we have one service. SQLite is embedded, the backend is `uv`-managed, and Redis is only needed by the optional distributed engine. Compose would add concepts (networks, volumes per service, service-discovery names) without simplifying anything.
- **Containerize the backend too**: rejected for v1. `uv` already gives reproducible Python environments. Adding a backend container would force every developer through Docker for the most-iterated component, slowing the inner loop without improving reproducibility.
- **Bind-mount `node_modules` from the host**: rejected. Cross-platform binary differences and macOS bind-mount throughput both make this unworkable.
- **`node:lts` base image (auto-tracking the latest LTS)**: rejected. Defeats the entire point of the dev container — to freeze the toolchain.
- **Devcontainer (`.devcontainer/devcontainer.json`) instead of a `Dockerfile` + `docker run`**: considered. Devcontainers integrate well with VS Code / Cursor, but they couple the dev environment to a specific editor ecosystem. Shipping a plain Dockerfile + Makefile keeps editor-agnostic compatibility and lets devcontainer-using developers add a `.devcontainer/devcontainer.json` that points at the same Dockerfile if they want.
- **Vite-based dev server alongside Angular's `ng serve`**: out of scope. The Angular CLI in the chosen LTS already uses esbuild + Vite under the hood; we use the CLI directly to avoid forking the toolchain.
- **Network mode `host` instead of port mapping**: rejected. `--network=host` is Linux-only (no parity on macOS / Windows Docker Desktop), so the documented setup would diverge by platform. `-p 4200:4200` plus `host.docker.internal` works identically on every supported host.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §9.5.
- External references:
  - [Docker `run` reference](https://docs.docker.com/reference/cli/docker/container/run/) — semantics for `--rm`, `-it`, `--add-host`, `-p`, and `-v`.
  - [Docker bind mounts documentation](https://docs.docker.com/engine/storage/bind-mounts/) — host-source bind mount behavior.
  - [Docker volumes documentation](https://docs.docker.com/engine/storage/volumes/) — named volume behavior used for `node_modules`.
  - [Docker host networking / `host-gateway` documentation](https://docs.docker.com/network/) — background for host access from Linux containers.
  - [Angular CLI `serve` documentation](https://angular.dev/tools/cli/serve) — `ng serve` flags used by the frontend `start` script.
- Related ADRs:
  - [`0002-backend-technology-stack.md`](0002-backend-technology-stack.md) — the backend runs on the host via `uv`; this ADR's "no backend container" rule consumes that decision.
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — SQLite is embedded; nothing to spin up alongside the frontend.
  - [`0007-cli-configuration-with-hydra-and-hydra-zen.md`](0007-cli-configuration-with-hydra-and-hydra-zen.md) — `outputs/` lives on the host; the frontend container does not touch it.
  - [`0008-frontend-stack-angular-strict-typescript-plotly-mermaid.md`](0008-frontend-stack-angular-strict-typescript-plotly-mermaid.md) — what the dev container actually runs.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — `npm run check` is the CI entry point inside the container.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — e2e tests run against mock adapters; the container does not need GPU access.
- Revisit triggers:
  - The distributed engine (per ADR-0005) becomes the default for at least one supported workflow — open an ADR introducing a Compose file that wires the backend, Redis, and the frontend, while preserving the host-only path for solo development.
  - A production deployment of the dashboard is needed — open an ADR for a multi-stage `Dockerfile` with a real build target and a static-asset deployment pattern.
  - Native Windows (without WSL2) becomes a supported platform — revisit the `host.docker.internal` story and any path conventions.
