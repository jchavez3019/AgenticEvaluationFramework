---
status: proposed
date: 2026-05-18
decision-makers: jorgejc2
---

# CLI Configuration with Hydra and hydra-zen

## Context and Problem Statement

The CLI is the framework's headless entry point: a Python script that imports the backend as a library and runs an evaluation end-to-end without any HTTP layer (high-level architecture §4). It needs:

- A way to compose a run configuration out of orthogonal pieces (model, dataset, metric set, engine, sampling parameters, output) that can be mixed and matched without copy-pasting whole YAML files.
- Ergonomic CLI overrides so users can change a single parameter without editing a file (`aef-eval sampling.temperature=0.0 model=smollm`).
- A managed output directory per run so artifacts (logs, `result.json`, plots, CSVs, the resolved config) live next to each other (§4 already specifies the layout).
- Strict typing all the way through: the resolved config must be a Pydantic object the backend already understands, not a `DictConfig` blob the rest of the code has to inspect.
- A clean way to expose the runtime-configurable sampling parameters introduced in ADR-0003 (`temperature`, `top_k`, `top_p`, `repetition_penalty`, `max_output_tokens`, plus optional `seed`).

Without a single, opinionated configuration mechanism, the CLI will accumulate ad-hoc `argparse` / `click` / YAML loaders that don't compose, and the strict-typing rule will erode at the CLI ↔ backend seam — which is exactly where ergonomics most tempt people to stuff dictionaries through.

The high-level architecture document already commits to **Hydra** as the configuration mechanism (§4) and to trying **hydra-zen** for Pydantic interop (§11.2). This ADR locks both in, defines the directory layout, the config-group catalog, and the typed handoff to the backend.

## Decision

Adopt **Hydra 1.3+** as the only CLI configuration mechanism, paired with **hydra-zen 0.13+** for typed dataclass-based config building and Pydantic conversion. YAML configuration files live under a top-level `configs/` directory.

### 1. Directory layout

```
configs/
  config.yaml                     # the default top-level composition
  model/
    smollm.yaml                   # default; small HF model for low-VRAM dev
    huggingface_default.yaml
    ollama_default.yaml
    openai_default.yaml
    langgraph_default.yaml
    mock.yaml                     # uses MockChatModel
  dataset/
    csv.yaml
    huggingface.yaml
    mock.yaml
  metrics/
    default.yaml                  # the v1 default metric suite
    lexical_only.yaml
    embedding_only.yaml
    judge_only.yaml
    custom.yaml                   # placeholder; user-extended
  engine/
    local.yaml                    # default; LocalEngine
    distributed.yaml              # DistributedEngine, used once Redis is reachable
  sampling/
    default.yaml                  # all None — defer to model defaults
    greedy.yaml                   # temperature=0
    balanced.yaml                 # temperature=0.7, top_p=0.9
    creative.yaml                 # temperature=1.0, top_p=0.95, repetition_penalty=1.1
  output/
    default.yaml                  # `outputs/${now:%Y-%m-%d}/${now:%H-%M-%S}/`
```

`config.yaml` is the master composition, defaulting to:

```yaml
defaults:
  - model: smollm
  - dataset: mock
  - metrics: default
  - engine: local
  - sampling: default
  - output: default
  - _self_

run_id: ??? # null sentinel; CLI generates a UUIDv7 if not supplied
seed: 0
hydra:
  run:
    dir: ${output.dir}
  job:
    chdir: false
```

The `???` sentinel forces Hydra to fail fast if `run_id` is not provided either by override or by the CLI's startup hook.

### 2. Typed configs via hydra-zen

Each config group is backed by a Python dataclass produced by hydra-zen's `builds(...)`, which generates a structured config that Hydra validates against. The dataclass fields are 1-to-1 with the corresponding Pydantic model in `aef.contracts`.

**Quick glossary** (these terms appear throughout the ADR and are easy to gloss over the first time):

- **`builds(Target, ..., populate_full_signature=True, zen_partial=False)`** — hydra-zen helper that produces a structured _config dataclass_ whose field names match `Target`'s constructor signature. `populate_full_signature=True` tells hydra-zen to walk `Target.__init__` (or for Pydantic models, the `BaseModel`'s field set) and expose every parameter as an overridable Hydra field. `zen_partial=False` tells hydra-zen that, when Hydra calls `instantiate(config)`, it should _construct the actual `Target` object_ immediately and return it. With `zen_partial=True`, `instantiate` would instead return a partially-applied callable that you invoke later — useful for "delay construction until I provide the rest of the args" patterns; not what we want here, where the goal is "give me a fully-constructed `EvaluationRunRequest` and friends, ready to hand to the engine."
- **`store(Conf, group="model", name="smollm")`** — registers `Conf` in hydra-zen's named config registry under the group `"model"` and the name `"smollm"`. This is the bridge between Python and the CLI: after this call, `aef-eval model=smollm` resolves to `Conf` at runtime. `store` is therefore where most defaults get written down: the config dataclass produced by `builds(...)` already carries its field defaults (because `populate_full_signature=True` introspected them), and `store` makes that named bundle available as a CLI override token. The ADR assumes you `import aef.cli.config` once at CLI startup — the side effect of that import is that every shipped config group is in the store.

Skeleton (illustrative):

```python
from hydra_zen import builds, store

from aef.contracts.adapter_spec import (
    HuggingFaceModelSpec,
    CSVDatasetSpec,
    MockChatModelSpec,
)
from aef.contracts.run import GenerationConfig, EngineConfig, OutputConfig
from aef.contracts.run import EvaluationRunRequest


SmolLMConf = builds(
    HuggingFaceModelSpec,
    model_id="HuggingFaceTB/SmolLM2-135M-Instruct",
    revision="<pinned-sha>",
    populate_full_signature=True,
    zen_partial=False,
)
store(SmolLMConf, group="model", name="smollm")


GreedySamplingConf = builds(
    GenerationConfig,
    temperature=0.0,
    top_k=None,
    top_p=None,
    repetition_penalty=None,
    max_output_tokens=512,
    seed=0,
    populate_full_signature=True,
)
store(GreedySamplingConf, group="sampling", name="greedy")


EvalRunConf = builds(
    EvaluationRunRequest,
    model="${model}",
    dataset="${dataset}",
    metrics="${metrics}",
    engine="${engine}",
    generation_config="${sampling}",
    output="${output}",
    populate_full_signature=True,
)
store(EvalRunConf, name="config")
```

The `aef.cli.config` module owns this registration. At CLI startup it registers every shipped config group with hydra-zen's store, then hands off to Hydra:

```python
@hydra.main(config_path="../../configs", config_name="config", version_base="1.3")
def main(cfg: DictConfig) -> None:
    request: EvaluationRunRequest = instantiate(cfg)  # produces a Pydantic object
    asyncio.run(_run(request))
```

`instantiate(cfg)` returns the actual Pydantic objects, not a `DictConfig`. From that point on, every line of code treats the config as fully-typed.

### 3. Sampling parameters on the CLI

Sampling is a first-class config group precisely so it is overridable per-invocation. Examples:

```bash
# Pick a preset
aef-eval sampling=balanced

# Override individual fields on top of the default
aef-eval sampling.temperature=0.0 sampling.top_p=0.9

# Combine: balanced preset plus a single override
aef-eval sampling=balanced sampling.max_output_tokens=128

# Pair with a specific model
aef-eval model=ollama_default sampling=creative

# Multirun over a sweep of temperatures
aef-eval --multirun sampling.temperature=0.0,0.3,0.7,1.0
```

The CLI does **not** silently drop unsupported parameters. After `instantiate(cfg)`, the CLI calls `validate_against_capabilities(request)` (defined in `aef.adapters.capabilities`) which checks each non-`None` `GenerationConfig` field against the resolved adapter's `capabilities.supported_sampling_parameters` and raises `UnsupportedSamplingParameterError` with a clear message naming the offending field and the adapter. This guarantees that a user who types `sampling.top_k=40 model=openai_default` learns immediately that OpenAI's chat-completions adapter does not honor `top_k`, rather than discovering the parameter was ignored after a long run.

### 4. Run identifier and output directory

- `run_id` is required. If absent, the CLI generates a UUIDv7 in a `pre_run` hook (so the value is set before Hydra resolves `output.dir`).
- Run artifacts are partitioned by entry point so CLI-launched and dashboard-launched runs cannot collide on the same second:

  | Entry point            | Artifact tree                                                                                                                   |
  | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
  | CLI (`aef-eval`)       | `outputs/cli/${now:%Y-%m-%d}/${now:%H-%M-%S}-${run_id}/`                                                                        |
  | API server / dashboard | `outputs/frontend/${now:%Y-%m-%d}/${now:%H-%M-%S}-${run_id}/`                                                                   |
  | Library callers        | `outputs/lib/${now:%Y-%m-%d}/${now:%H-%M-%S}-${run_id}/` (configurable; the library can also disable artifact writing entirely) |

  In the table above, "frontend" labels the user-facing source even though the actual writer is the backend API process (the Angular frontend never touches the filesystem). The label is chosen for human-readability over technical purity.

- Hydra's `hydra.run.dir` is set to the CLI tree (above) so its `.hydra/` subfolder, with the resolved YAML, lands alongside `result.json` and the CLI's other artifacts.
- The API server uses the same `EvaluationRunResult` serialization but writes to its `outputs/frontend/...` tree directly (without Hydra's wrapper, since API-launched runs do not have a YAML composition). It still produces `result.json`, `metrics_summary.csv`, and `plots/` so a dashboard run is exportable in the same format as a CLI run.
- The API process additionally maintains a single rotating server log file (`outputs/frontend/server.log` or, if Hydra is involved on the API process, the server log location is configurable via `AEF_API_LOG_PATH`). This is separate from per-run logs; it captures uvicorn startup, request access logs, and background-task output. ADR-0012 owns the exact handler / formatter setup; this ADR only commits to the per-run path scheme.

### 5. Multirun

Hydra's `--multirun` mode is supported for sweeps over models, datasets, sampling presets, and individual parameters. Each sweep cell becomes a separate run with its own `run_id` and its own SQLite row.

Examples:

```bash
# Run the same config across three models
aef-eval --multirun model=smollm,ollama_default,openai_default

# Sweep temperatures
aef-eval --multirun sampling.temperature=0.0,0.3,0.7,1.0

# Cross product
aef-eval --multirun model=smollm,ollama_default sampling=greedy,balanced
```

Hydra's `BasicLauncher` is the v1 default. The `JoblibLauncher` and `RayLauncher` plugins are **not** part of the CLI's dependency surface; if a user wants parallel multirun, they install the plugin themselves. The `DistributedEngine` (ADR-0005) handles intra-run parallelism; Hydra multirun is for _between-run_ sweeps.

### 6. Config validation

- `aef.cli.config` includes a `validate_config(cfg: EvaluationRunRequest) -> None` step that runs after `instantiate` and before any expensive work. It checks:
  - The adapter exists in the registry (would otherwise fail later inside the engine).
  - `GenerationConfig` is honored by the adapter (per §3 above).
  - Metric specs are all in the metric registry (deferred to ADR-0004's contract).
  - `output.dir` is writable.
  - If `engine=distributed`, Redis is reachable. Otherwise refuse to start so the user does not wait for a connection timeout deep into the run.

### 7. Library / CLI symmetry

- `aef.cli.run(request: EvaluationRunRequest) -> EvaluationRunResult` is the function the Hydra entry point ultimately calls. It is also a public library function, so a Python user who already has an `EvaluationRunRequest` (constructed by hand or by another tool) can run it without going through Hydra.
- Hydra is therefore an _optional_ surface, not a required one. The contract is the Pydantic model.

### Non-goals

- We are NOT supporting `argparse`, `click`, `typer`, or any other CLI layer alongside Hydra. The CLI is single-surfaced.
- We are NOT supporting `.env`-style flat configuration as the **primary** mechanism for evaluation-run configuration. `.env` is fine — and expected — for _runtime / environment / secret_ values (database URL, log level, OTel toggle, third-party API keys); a single `.env` is loaded once by `aef.config.settings.Settings` (a `pydantic-settings` model) at process startup and read by both the CLI and the API server, so there is no key duplication between entry points. What `.env` is **not** for is the per-run configuration of model / dataset / metrics / sampling / engine — those belong in Hydra because they need composition, named presets, sweeps, per-run overrides, and a saved resolved snapshot. Treating run config as `.env`-style globals would lose all of those and would make reproducibility per run effectively impossible. The frontend/dashboard never receives `.env` contents directly: the API process reads them in-memory and exposes only what is safe through its REST/WS API.
- We are NOT supporting direct `OmegaConf` -> `dict` -> backend handoff. Every CLI invocation produces typed Pydantic objects via `instantiate`. The strict-typing rule is binding here.
- We are NOT making Hydra mandatory for the API server. The server takes `EvaluationRunRequest` over JSON; it does not consume YAML. The CLI is the only Hydra consumer.
- We are NOT shipping the `hydra-joblib-launcher` or `hydra-ray-launcher` plugins by default. Users who want them install them themselves.

## Consequences

- Good, because composition makes "swap one adapter, keep everything else" a one-token change. Sweeps over models, datasets, and sampling parameters are first-class.
- Good, because hydra-zen turns Hydra's `DictConfig` outputs into the same Pydantic models the rest of the codebase already uses — strict typing all the way through.
- Good, because the sampling group surfaces every user-configurable knob in a uniform way (`sampling=balanced`, `sampling.temperature=0.7`). The "free reign to update these parameters when performing a run" requirement is satisfied directly.
- Good, because Hydra owns the per-run output directory layout, including `.hydra/`, so CLI artifacts and Hydra artifacts cannot drift.
- Bad, because Hydra has a learning curve. New contributors will encounter `defaults` lists, override syntax, and multirun semantics for the first time. We mitigate by shipping a `docs/cli.md` cheat sheet with the most common invocations.
- Bad, because hydra-zen is a smaller library than Hydra itself and adds one more dependency that has to keep up with Pydantic v2. We accept this — the alternative is a hand-written OmegaConf-to-Pydantic shim that we would also have to maintain.
- Bad, because Hydra changes the working directory by default. We disable that (`hydra.job.chdir: false`) so the CLI plays nicely with relative paths.
- Neutral, because Hydra's multirun mechanism intentionally stops at sweep granularity. Intra-run parallelism is the engine's job (ADR-0005); cross-run sweeps are Hydra's. The two do not overlap.

## Implementation Plan

- **Affected paths**:
  - `configs/` — directory layout exactly as in §1.
  - `cli/` (workspace member) — flat package beside `cli/pyproject.toml`; exposes `aef-eval`, `aef-plot`, `aef-report`.
  - `cli/__init__.py` — `main`, `run`, `validate_config`, hydra-zen registration entry.
  - `cli/config.py` — hydra-zen builds and store calls for every config group.
  - `cli/visualize.py` — `aef-plot` and `aef-report` post-processors that read `outputs/<...>/result.json`.
  - `backend/contracts/run.py` — `EvaluationRunRequest`, `EngineConfig`, `OutputConfig` (so Hydra has typed targets).
  - `backend/adapters/capabilities.py` — `validate_against_capabilities(request)` helper.
  - `docs/cli.md` (new, optional but recommended) — quickstart and override syntax cheat sheet.
- **Dependencies**:
  - `hydra-core>=1.3,<2`.
  - `hydra-zen>=0.13,<0.14`.
  - `omegaconf>=2.3` (transitively pulled by Hydra; pin only if a known issue forces it).
  - No `argparse`, `click`, `typer`. No `joblib-launcher` or `ray-launcher` plugins in the default install.
- **Patterns to follow**:
  - Every config group has a `default` named entry. The top-level `defaults:` list always picks named entries; never inline structured configs.
  - Every YAML in `configs/<group>/<name>.yaml` either references a hydra-zen-built dataclass via `_target_` or composes other named entries. There is no free-form YAML at the leaves.
  - When adding a new adapter (per ADR-0003), the same PR adds a `configs/model/<name>.yaml` (or `configs/dataset/<name>.yaml`) so the CLI exposes it.
  - Sampling presets in `configs/sampling/` set explicit values for the parameters they care about and leave others as `null` (deferring to model defaults). Presets are short and readable.
  - `run_id` is generated once, in a `pre_run` hook, and passed unchanged through every downstream component.
- **Patterns to avoid**:
  - Do NOT pass raw `DictConfig` objects past the CLI boundary. Always `instantiate` first.
  - Do NOT hand-write argparse alongside Hydra to capture extra flags. Add another config group instead.
  - Do NOT special-case adapter-specific extra knobs by stuffing them into `OmegaConf` dicts. Extend `GenerationConfig` (per ADR-0003) or add a typed adapter-specific spec field.
  - Do NOT default any sampling parameter to a non-`None` value at the framework level. Per ADR-0003, `None` means "use the adapter's default"; the only place defaults are set is inside the user's chosen `sampling` preset, which is explicit.
  - Do NOT change Hydra's working directory (`hydra.job.chdir`); keep it disabled.
- **Configuration**:
  - Top-level Hydra version base: `1.3`.
  - `hydra.run.dir = ${output.dir}`.
  - `hydra.sweep.dir = outputs/multirun/${now:%Y-%m-%d}/${now:%H-%M-%S}/`, `hydra.sweep.subdir = ${run_id}`.
  - `hydra.job.chdir: false`.
- **Migration steps**: greenfield.

### Verification

- [ ] `aef-eval --help` prints the Hydra usage with `model=`, `dataset=`, `metrics=`, `engine=`, `sampling=`, `output=` listed as overridable groups.
- [ ] `aef-eval` (no overrides) runs the default composition (`model=smollm`, `dataset=mock`, `metrics=default`, `engine=local`, `sampling=default`) end-to-end on a clean tree with no GPU.
- [ ] `aef-eval sampling=balanced` produces a `result.json` whose `run_request.generation_config.temperature` and `top_p` reflect the preset.
- [ ] `aef-eval sampling.temperature=0.0 sampling.top_p=0.9` overrides individual fields without touching the rest of the preset.
- [ ] `aef-eval model=openai_default sampling.top_k=40` exits with `UnsupportedSamplingParameterError` _before_ any model call (because OpenAI's chat-completions adapter does not honor `top_k`).
- [ ] `aef-eval --multirun sampling.temperature=0.0,0.5,1.0` produces three runs with three distinct `run_id`s and three SQLite rows.
- [ ] Every shipped YAML under `configs/` either composes other named entries via `defaults:` or references a hydra-zen-built `_target_`. No free-form YAML leaves.
- [ ] After `instantiate(cfg)`, every value reaching `cli.run` is a Pydantic object (verifiable by a unit test that asserts `isinstance(request, EvaluationRunRequest)` and that all fields are typed sub-models, not `DictConfig`).
- [ ] `pyproject.toml` does NOT list `argparse`, `click`, or `typer` as dependencies.
- [ ] `pyproject.toml` declares `[project.scripts]` entries for `aef-eval`, `aef-plot`, `aef-report`.
- [ ] `outputs/<date>/<time>-<run_id>/.hydra/config.yaml` is produced and matches the resolved configuration of the run.

## Alternatives Considered

- **Argparse + custom YAML loader**: rejected. We would re-invent Hydra's composition / override / sweep features badly. The custom loader becomes the bottleneck for every new feature.
- **`click` or `typer`**: same as above. They are great for traditional CLIs that pass flags into a single function. They do not natively support compositional YAML configs or multirun sweeps.
- **Pydantic Settings only (no Hydra)**: considered. Pydantic Settings is excellent for app-level configuration (env vars, single config file). It is not a runner: no multirun, no per-run output directory, no group composition. It pairs well with Hydra for the runtime-environment slice (database URL, log level), and we use it for that, but it is not a substitute for Hydra at the CLI.
- **Hand-rolled OmegaConf → Pydantic shim (no hydra-zen)**: considered. Workable but adds maintenance load every time Pydantic or OmegaConf changes a behavior. hydra-zen already does this conversion idiomatically and supports Pydantic v2 models out of the box.
- **`fire` or `invoke`**: rejected. Same class as click/typer — no composition, no sweep semantics.
- **Hydra without hydra-zen** (use raw structured configs in `dataclass` form): considered. Workable but verbose; we would write a `@dataclass` for every Pydantic model in the contract layer to satisfy Hydra's structured-config requirements. hydra-zen's `builds(...)` collapses that step.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §4, §11.2.
- External references:
  - [Hydra documentation](https://hydra.cc/docs/intro/) — config composition, overrides, output directories, and multirun.
  - [hydra-zen documentation](https://mit-ll-responsible-ai.github.io/hydra-zen/) — `builds`, `store`, and typed Hydra config generation.
  - [OmegaConf documentation](https://omegaconf.readthedocs.io/) — underlying structured configuration container used by Hydra.
  - [pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — `.env` / `AEF_*` runtime settings model.
- Related ADRs:
  - [`0002-backend-technology-stack.md`](0002-backend-technology-stack.md) — Pydantic v2 and the typed contracts hydra-zen converts into.
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — `GenerationConfig`, the supported-sampling-parameter capability, and the `UnsupportedSamplingParameterError` semantics referenced here.
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — every CLI run is persisted to SQLite as well as written to `outputs/`.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — pyright strict on `aef.cli.*` is the gate that catches `DictConfig` leaks.
  - [`0005-execution-engine-local-and-distributed.md`](0005-execution-engine-local-and-distributed.md) — the `engine=distributed` group only becomes meaningful once the `DistributedEngine` ADR lands.
  - [`0008-frontend-stack-angular-strict-typescript-plotly-mermaid.md`](0008-frontend-stack-angular-strict-typescript-plotly-mermaid.md) — frontend mirrors the same sampling-parameter UI driven by adapter capabilities.
- Revisit triggers:
  - hydra-zen falls behind Pydantic v2 / Hydra version updates — re-evaluate the OmegaConf-to-Pydantic shim alternative.
  - A second CLI surface emerges (e.g., a separate "report-only" tool with very different ergonomics) — split into multiple entry points rather than abandoning Hydra.
  - Multirun coordination needs to interact with the `DistributedEngine` directly — replace Hydra's launcher with engine-side sweep dispatch and update this ADR.
