---
status: proposed
date: 2026-05-18
decision-makers: jorgejc2
---

# Frontend Stack — Angular, Strict TypeScript, Plotly, Mermaid

## Context and Problem Statement

The dashboard is the framework's most user-visible surface. The high-level architecture document (§5) commits to:

- Angular as the framework, in **dev mode only** inside a Docker container (no production build artifact).
- TypeScript with strict typing.
- Four navigation cards: **Evaluation Runner**, **Metadata Viewer**, **Run History**, **Knowledge Base / Blog**.
- `mermaid.js` for rendering LLM and agentic-graph topologies in the Metadata Viewer.
- A chart library for evaluation analytics — `Plotly.js` is the chosen default, with `ngx-charts` and `ECharts` as fallback options.
- Strict separation: the frontend never reads SQLite directly; everything goes through the backend HTTP/WS API (per ADR-0006).

What is _not_ yet fixed: the specific Angular setup (standalone components vs NgModules, Signals vs RxJS as the default state primitive), the styling library, the routing layout, the API client codegen, the WebSocket subscription model, and the Run History card's comparison shape. Without an ADR pinning these, the frontend will fragment by component and lose the strict-typing guarantees that are otherwise binding across the project.

This ADR locks the frontend stack and structure for v1.

## Decision Drivers

- **Strict typing parity with the backend.** The same "no `any`, no untyped extras" rule applies. Pydantic shapes round-trip into TypeScript types via codegen.
- **Live progress for long-running evals.** WebSocket subscriptions surface per-sample progress in the Evaluation Runner card.
- **Run comparison ergonomics.** The Run History card has to support side-by-side diff of two runs and free-text + faceted filtering, both of which need a real chart library and a real grid component.
- **Knowledge Base authoring.** Articles live in Markdown alongside the rest of the repo so they ship with the framework, not on a separate CMS.
- **Frontend tooling discipline.** ESLint + Prettier (per ADR-0010) and the strict TS flags are non-negotiable.

## Decision

Adopt the following stack.

### 1. Framework, language, and build

- **Angular** at the latest LTS supported by the Angular CLI's `ng new` (Angular 18+ as of this ADR; the Docker base image pins the exact major version — see ADR-0009 for the dev container).
- **TypeScript strict mode**: `"strict": true`, `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`, `"noImplicitOverride": true`, `"noFallthroughCasesInSwitch": true` (per ADR-0010 §1).
- **Standalone components only.** No NgModules. New components, directives, and pipes are `standalone: true`.
- **Signals as the default state primitive**, with RxJS reserved for inherently streaming concerns (HTTP, WebSocket, deferred work). Ad-hoc `BehaviorSubject` in components is replaced by `signal()` + `computed()`.
- **Production build is not produced.** `ng serve` is the only run mode (per ADR-0009). `ng build` exists but is not part of CI.

**What "standalone" means.** In modern Angular, a component can declare its own template dependencies directly in its `imports` array instead of being declared inside an `NgModule`. That makes the component self-contained: reading the component tells you which directives, pipes, and child components it uses. This is not primarily a security decision, and NgModules are not inherently unsafe. The trade-off is architectural: NgModules are useful for older Angular applications and some library-packaging patterns, but they add an indirection layer that is unnecessary for a greenfield dashboard. Standalone components reduce boilerplate, make lazy loading simpler (`loadComponent` instead of module wrappers), and align with Angular's current documentation and CLI defaults.

**Signals vs RxJS.** Signals are Angular's synchronous reactive state primitive: `signal()` stores local state, `computed()` derives state, and Angular knows exactly which templates depend on which values. They are a good fit for UI state such as selected run IDs, active filters, and derived chart configs. RxJS is a stream library for asynchronous event sequences: HTTP responses, WebSocket messages, timers, retries, cancellation, and operators such as `switchMap` / `debounceTime`. The framework uses both: RxJS at the boundary where data arrives over time, and Signals inside components once that data becomes UI state. This avoids turning simple component state into observable plumbing while still using RxJS where it is strongest.

### 2. Styling

- **Tailwind CSS 3+** for utility-first styling.
- **Angular Material** for high-value primitives that are tedious to rebuild: data tables, dialogs, autocomplete, snack bars, side nav. The two coexist: Material handles the structural primitives, Tailwind handles layout, spacing, and theming refinements. Mixing them is a deliberate and well-trodden pattern.
- **Theme:** a single shared theme file applies to all four cards. Light mode is the default; a dark-mode toggle is in scope for v1 (Angular Material's theming + Tailwind `dark:` modifiers cover both layers).

### 3. Routing and shell

- The shell renders the four navigation cards on the home route (`/`). The Run History card is the new addition introduced during planning, so the shell is deliberately built for **four cards, not three**.
- Each card has its own feature route:
  - `/runner` — Evaluation Runner.
  - `/models` — Metadata Viewer (renamed from "models" if it expands; the path is stable).
  - `/runs` — Run History.
  - `/blog` — Knowledge Base.
- Routes are lazy-loaded via `loadComponent: ...` (the standalone-component equivalent of `loadChildren`). Cold load of the shell pulls only the home view; visiting a card loads its bundle on demand.

### 4. State and data flow

- **HTTP client:** Angular's `HttpClient`, configured with `provideHttpClient(withFetch())`.
- **WebSocket client:** `rxjs/webSocket` for low-level subscription, wrapped in a typed `RunProgressService` that exposes a `signal<RunProgress>`-friendly API.
- **API client codegen:** the backend's FastAPI app exposes an OpenAPI 3.1 document at `/openapi.json` (per ADR-0002). The frontend generates a typed client from it via `openapi-typescript-codegen` (or the `hey-api/openapi-ts` successor) at build time. Generated code lives under `frontend/src/app/api/generated/` and is regenerated by an `npm run codegen` script. **Do not hand-edit generated files.**
- **WebSocket message types** are _not_ emitted by FastAPI's OpenAPI; they are captured by a hand-maintained schema in `frontend/src/app/api/ws-schemas.ts` whose Pydantic-side counterpart lives in `aef.api.ws_schemas`. Both sides import from the same Pydantic model definitions, and a generated test (`tests/integration/api/test_ws_schema_parity.py`) asserts they stay in sync.

### 5. Charting

- **Default chart library:** **Plotly.js** (the open-source `plotly.js-dist-min` build) wrapped behind a thin `<aef-chart>` component.
- The wrapper component is the only place that imports Plotly. All cards consume it. Switching to `ECharts` (or `ngx-charts`) at a later date is therefore a one-component change. ECharts and ngx-charts remain documented fallbacks in the high-level architecture (§11.1) but are not implemented in v1.
- Chart specs are typed: `ChartConfig` is a Pydantic-shaped TypeScript interface that the wrapper translates into Plotly's options. The cards never construct Plotly options directly.

### 6. Diagrams

- **Mermaid 11+** via `mermaid` npm package, mounted inside an `<aef-mermaid>` component that:
  - Renders SVG on the client.
  - Sanitizes input (no inline HTML in node labels).
  - Emits a typed click event so node clicks can drive navigation.
- Used by the Metadata Viewer to render LangGraph topologies (per high-level architecture §5.3) and by the Knowledge Base for didactic flow diagrams.

### 7. Knowledge Base ("Blog")

- Articles are **Markdown files in the repo** under `frontend/src/app/blog/articles/<slug>.md`.
- Rendering pipeline: `marked` for Markdown → `DOMPurify` for sanitization → `highlight.js` for code fences → optional `<aef-mermaid>` for ` ```mermaid ` fences.
- **No CMS.** Authors edit Markdown and open a PR. The `frontend/src/app/blog/articles.manifest.ts` is generated by an `npm run blog:index` script that scans the directory and writes a typed list of `{ slug, title, summary, tags, published_at }` entries (parsed from frontmatter). The Blog card renders from the manifest.
- **Math:** `katex` for inline / display math when an article uses it. Off by default.

### 8. The four cards (binding shape)

#### Evaluation Runner (`/runner`)

- Form-driven config builder backed by the OpenAPI types: pick a model adapter, a dataset adapter, a metric set, an engine config, and a `GenerationConfig`.
- The sampling-parameter inputs are dynamically rendered from the resolved adapter's `capabilities.supported_sampling_parameters` (per ADR-0003). A user picking the OpenAI adapter sees `temperature`, `top_p`, `max_output_tokens`, `seed` only; switching to the HF SmolLM adapter unlocks `top_k` and `repetition_penalty`. Disabled fields are visibly so, with a tooltip explaining why.
- Submit triggers `POST /runs`. The response carries the new `run_id`; the card immediately switches to a "live" view that subscribes to `WS /runs/{run_id}/progress` and renders progress, per-sample status, and a tail of the run log.
- On completion the card renders the `EvaluationRunResult` summary plus charts (latency distribution, metric-score histogram).

#### Metadata Viewer (`/models`)

- Lists registered model adapters and dataset adapters from `GET /adapters`.
- Detail panel shows the adapter's `ModelAdapterSpec` (capabilities, `supported_sampling_parameters`, model family).
- For LangGraph adapters, renders the graph topology via `<aef-mermaid>` (the adapter exposes a `GET /adapters/{id}/topology` endpoint returning a Mermaid-flavored graph string; per high-level architecture §11.4).
- Lists dataset adapters with a small preview pane (first N rows) sourced from `GET /datasets/{id}/preview?limit=10`.

#### Run History (`/runs`)

- Paginated, sortable, filterable table backed by `GET /runs?...` (the `RunQuery` shape from ADR-0006).
- Filter facets: status, engine kind, date range, model family, dataset id, metric presence.
- Row click opens a detail view with the full `EvaluationRunResult` and exports (`Download result.json`, `Download CSV`).
- **Compare mode:** select two rows → side-by-side diff view that aligns metric results and highlights significant deltas. Stats: per-metric mean diff, p-value (Wilcoxon for paired samples), per-sample winner counts. The compare view is the headline differentiator of this card vs the CLI.

#### Knowledge Base ("Blog") (`/blog`)

- Index page lists articles from the generated manifest, with tag filtering.
- Article view renders Markdown → SVG mermaid + KaTeX as needed, with a sticky table-of-contents column.
- One article per shipped metric family (lexical, embedding, learned/judge, RAG, operational) plus framework-overview and methodology articles. The exact list of seed articles is not binding here; the contract is that they live in `frontend/src/app/blog/articles/` and follow the manifest schema.

### 9. Linting, formatting, and tests

- ESLint (`@angular-eslint`, `@typescript-eslint`) + Prettier per ADR-0010.
- TSDoc on every exported symbol (per ADR-0010 §3).
- Tests:
  - **Unit:** Vitest (or `karma + jasmine` if the Angular CLI default in the chosen LTS is still Karma; we prefer Vitest where the Angular CLI supports it).
  - **Component / integration:** Angular's testing utilities (`TestBed`) for component contracts.
  - **End-to-end:** Playwright. A small e2e suite under `frontend/e2e/` runs against a backend started in mock mode (per ADR-0011's mock adapters).
- `npm run check` (per ADR-0010) runs `ng lint`, `prettier --check`, `tsc --noEmit`, and the unit suite.

### Non-goals

- We are NOT shipping a server-side-rendered (SSR) variant in v1.
- We are NOT building a mobile-optimized layout in v1. The dashboard is desktop-first.
- We are NOT bundling a custom design system. Material + Tailwind cover the surface.
- We are NOT supporting i18n in v1. English only; the architecture does not foreclose i18n later (Angular i18n + a translations directory).
- We are NOT shipping multiple chart libraries. Plotly is the only library imported in v1; the wrapper makes a swap cheap if needed.
- We are NOT exposing direct database access from the frontend. All data flows through the backend API.
- We are NOT including an authentication layer in v1. The dashboard is a single-user / trusted-LAN tool; auth is a future ADR.

## Consequences

- Good, because standalone components + signals make the frontend simpler than the legacy NgModule + RxJS-everywhere pattern. New contributors pick it up faster.
- Good, because typed API client codegen means the strict-typing rule extends to the backend ↔ frontend boundary. A backend schema change that the frontend hasn't consumed produces a TypeScript error, not a runtime exception.
- Good, because adapter-driven sampling-parameter UI makes the `supported_sampling_parameters` capability from ADR-0003 directly visible to the user, satisfying the "free reign to update these parameters when performing a run" requirement.
- Good, because Markdown-as-Blog keeps documentation versioned with code. No CMS to babysit.
- Good, because the Plotly wrapper is the only Plotly importer, so swapping in ECharts later is a 1-component change, not a sweep.
- Bad, because TypeScript codegen has to be re-run when the OpenAPI document changes. Mitigation: `npm run codegen` is part of `npm run check` so a missed regeneration fails CI.
- Bad, because mixing Tailwind with Angular Material occasionally produces specificity wars. We accept this; the alternative (Material only or Tailwind only) is each weaker on its own axis.
- Bad, because Plotly.js is a heavyweight dependency (~3 MB minified). For dev-mode `ng serve` this is fine; if we ever introduce a production build, this is a candidate for code-splitting.
- Neutral, because rejecting NgModules removes one Angular concept from the codebase but every contributor learning Angular today will be learning standalone components anyway.

## Implementation Plan

- **Affected paths**:
  - `frontend/` — Angular workspace produced by `ng new aef-dashboard --standalone --routing --style=scss`.
  - `frontend/src/app/app.config.ts` — `provideHttpClient(withFetch())`, Angular Router, animations, Material theme.
  - `frontend/src/app/shell/` — home-shell component rendering four cards.
  - `frontend/src/app/cards/runner/` — Evaluation Runner.
  - `frontend/src/app/cards/metadata/` — Metadata Viewer.
  - `frontend/src/app/cards/runs/` — Run History (with compare mode).
  - `frontend/src/app/cards/blog/` — Knowledge Base.
  - `frontend/src/app/api/generated/` — OpenAPI-derived types and clients (regenerated, not hand-edited).
  - `frontend/src/app/api/ws-schemas.ts` — hand-maintained WebSocket message types in lockstep with `aef.api.ws_schemas`.
  - `frontend/src/app/components/aef-chart/` — Plotly wrapper.
  - `frontend/src/app/components/aef-mermaid/` — Mermaid wrapper.
  - `frontend/src/app/blog/articles/` — Markdown articles.
  - `frontend/src/app/blog/articles.manifest.ts` — generated by `npm run blog:index`.
  - `frontend/eslint.config.mjs`, `frontend/.prettierrc.json`, `frontend/tsconfig.json` — already covered by ADR-0010.
  - `frontend/package.json` — scripts: `start`, `build` (not used in CI), `codegen`, `blog:index`, `lint`, `format`, `check`, `e2e`.
  - `frontend/e2e/` — Playwright smoke tests.
- **Dependencies** (initial pin set; exact patch versions resolved by `npm install`):
  - `@angular/{core,common,router,forms,animations,material,cdk}` — latest LTS major.
  - `tailwindcss`, `postcss`, `autoprefixer`.
  - `rxjs`.
  - `plotly.js-dist-min`.
  - `mermaid`.
  - `marked`, `dompurify`, `highlight.js`, `katex`.
  - `@types/...` for any of the above lacking inline types.
  - `openapi-typescript-codegen` (or `@hey-api/openapi-ts`).
  - Dev: `@angular-eslint/eslint-plugin`, `@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`, `eslint-config-prettier`, `prettier`, `playwright`.
- **Patterns to follow**:
  - Every component is `standalone: true` and declares its imports inline.
  - Every API call goes through a service that wraps the generated client. Components do not call `HttpClient` directly.
  - Every WebSocket subscription goes through `RunProgressService`. Components consume a `Signal<RunProgress>`.
  - Every chart goes through `<aef-chart [config]>`. Components do not import Plotly.
  - Every diagram goes through `<aef-mermaid [source]>`. Components do not import `mermaid`.
  - Every form uses Reactive Forms with a typed `FormGroup<...>` matching the Pydantic-derived TypeScript type.
- **Patterns to avoid**:
  - Do NOT use NgModules in new code.
  - Do NOT import Plotly or Mermaid outside their wrapper components.
  - Do NOT hand-edit `frontend/src/app/api/generated/`.
  - Do NOT introduce a second chart library or a second Markdown library in v1.
  - Do NOT use `any`. Pyright strict and `@typescript-eslint/no-explicit-any` are both binding.
  - Do NOT use template-driven forms. Reactive Forms only.
- **Configuration**:
  - In dev mode, the frontend uses relative URLs (`/api`, `/ws`) and the Angular CLI's proxy (ADR-0009 §3) routes them to the host backend via `host.docker.internal:8000`. `frontend/src/environments/environment.ts` therefore sets `apiBaseUrl: ''` for dev; a future production environment file would set it to the deployed backend URL. No secrets live in the frontend.
  - Tailwind config under `frontend/tailwind.config.cjs`, scoped to `frontend/src/**/*.{html,ts}`.
  - Mermaid initialized with `securityLevel: 'strict'`.
- **Migration steps**: greenfield.

### Verification

- [ ] `npm run start` (which delegates to `ng serve`) brings up the dashboard at `http://localhost:4200/` against a running backend.
- [ ] The shell renders exactly four navigation cards: Evaluation Runner, Metadata Viewer, Run History, Knowledge Base.
- [ ] No NgModule is declared in `frontend/src/app/`.
- [ ] No file outside `frontend/src/app/components/aef-chart/` imports `plotly.js-dist-min`.
- [ ] No file outside `frontend/src/app/components/aef-mermaid/` imports `mermaid`.
- [ ] Switching the model adapter in the Evaluation Runner re-renders the sampling-parameter inputs to match `capabilities.supported_sampling_parameters`. Unsupported fields are visibly disabled with a tooltip.
- [ ] `npm run codegen` regenerates `frontend/src/app/api/generated/` from the backend's `/openapi.json` and CI fails when the regeneration produces a diff that was not committed.
- [ ] WebSocket message schemas in `frontend/src/app/api/ws-schemas.ts` match `aef.api.ws_schemas` (asserted by `tests/integration/api/test_ws_schema_parity.py`).
- [ ] Playwright e2e suite under `frontend/e2e/` brings up a backend in mock mode and exercises a full run end-to-end including the Run History compare mode.
- [ ] `npm run check` exits 0 on a clean tree (delegates to lint, prettier, tsc --noEmit, unit tests).
- [ ] Knowledge Base manifest is generated by `npm run blog:index` and CI fails when an `articles/*.md` is added without re-running the script.
- [ ] No file under `frontend/src/` uses `any` (verifiable via ESLint).

## Alternatives Considered

- **React or Vue instead of Angular**: rejected. Angular was named in the high-level architecture and chosen for its strict typing defaults, batteries-included Material library, and coherent reactive primitives (Signals + RxJS). Re-litigating would invalidate the rest of the architecture.
- **NgModules + heavy RxJS**: rejected. Standalone components + Signals are the explicit modern Angular direction; new code in 2026 has no reason to use the older pattern.
- **ECharts as default chart library**: considered. Excellent performance for very large datasets, richer Sankey/heatmap built-ins. Plotly was named as the v1 commitment in the architecture doc; the wrapper component preserves the option to swap. We can revisit when run-history dataset sizes start hurting Plotly.
- **ngx-charts as default chart library**: rejected. Angular-native is appealing but ngx-charts' interactivity story lags behind Plotly and ECharts; the Run History compare view's UX would suffer.
- **A separate CMS for the Knowledge Base** (Strapi, Contentful, Notion-as-CMS): rejected. The articles are part of the framework's pedagogy and need to ship and be versioned alongside the code.
- **Server-side rendering (SSR) via Angular Universal**: rejected. The dashboard is a tool for evaluating LLMs in a trusted environment, not a public site. The bundle size and time-to-interactive arguments for SSR do not apply.
- **Hand-written API client**: rejected. The OpenAPI document is already produced by FastAPI; hand-maintaining a parallel TypeScript client invites drift.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §5 (entire), §11.1 (chart-library rationale).
- External references:
  - [Angular standalone components documentation](https://angular.dev/guide/components/importing) — component-level imports and standalone component patterns.
  - [Angular Signals guide](https://angular.dev/guide/signals) — `signal`, `computed`, and template dependency tracking.
  - [RxJS documentation](https://rxjs.dev/guide/overview) — stream primitives and operators used for HTTP / WebSocket boundaries.
  - [Angular `HttpClient` documentation](https://angular.dev/guide/http) — typed HTTP client used by API services.
  - [Plotly JavaScript documentation](https://plotly.com/javascript/) — charting library wrapped by `<aef-chart>`.
  - [Mermaid documentation](https://mermaid.js.org/) — diagram renderer wrapped by `<aef-mermaid>`.
  - [Angular Material documentation](https://material.angular.dev/) — UI primitives used by the dashboard.
  - [Tailwind CSS documentation](https://tailwindcss.com/docs) — utility styling layer.
- Related ADRs:
  - [`0002-backend-technology-stack.md`](0002-backend-technology-stack.md) — FastAPI's OpenAPI is the source of truth for the typed API client.
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — `capabilities.supported_sampling_parameters` drives the Evaluation Runner UI.
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — Run History queries flow through the API, never directly to SQLite.
  - [`0007-cli-configuration-with-hydra-and-hydra-zen.md`](0007-cli-configuration-with-hydra-and-hydra-zen.md) — sampling presets surfaced in the runner mirror the YAML presets.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — strict TS flags, ESLint, Prettier, TSDoc.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — the e2e suite consumes mock adapters for deterministic runs.
  - [`0012-logging-and-telemetry-contract.md`](0012-logging-and-telemetry-contract.md) — `RunProgressService` consumes the typed Pydantic events from the WebSocket layer.
  - [`0009-frontend-docker-dev-environment.md`](0009-frontend-docker-dev-environment.md) — Frontend Docker dev environment + backend access pattern (proxy, host-only access, named-volume `node_modules`).
- Revisit triggers:
  - A second product surface (e.g., a public read-only embed) appears — revisit SSR.
  - Plotly's bundle size becomes a measurable problem — switch the wrapper to ECharts via the documented swap path.
  - An i18n requirement appears — open an i18n ADR; the directory layout already permits Angular i18n drop-in.
  - The Knowledge Base outgrows Markdown-in-repo — adopt a CMS in a follow-up ADR; the article-manifest contract makes this a one-source change, not a rewrite.
