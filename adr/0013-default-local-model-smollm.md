---
status: proposed
date: 2026-05-18
decision-makers: jorgejc2
---

# Default Local Model — SmolLM

## Context and Problem Statement

The framework needs a designated _default local model_ that:

- Runs end-to-end on a low-VRAM development GPU (≤ 8 GB) without quantization tricks or aggressive offloading.
- Loads quickly enough that a smoke test (`pytest -m gpu` from ADR-0011) finishes in a few minutes, not tens of minutes.
- Exercises the full code path — chat templating, sampling parameters, tokenization, streaming if requested — so the smoke test catches real integration bugs.
- Is permissively licensed and freely downloadable from Hugging Face Hub so any contributor can pull it without account gating.
- Is small enough that a developer can iterate on the framework (not the model) without paying for cloud access, and small enough that micro-batching is realistic on a laptop GPU.

The high-level architecture document (§9.4) already names **SmolLM** as the chosen default, but does not pin a specific revision or articulate the reasoning. Without an explicit choice, contributors will disagree about which size, which checkpoint, and which tokenizer settings to use; smoke tests will drift; and the documentation will fall behind the code.

This ADR pins the default and documents what the framework guarantees (and does not guarantee) about it.

## Decision

Pin the default local model to **`HuggingFaceTB/SmolLM2-135M-Instruct`** (Hugging Face Hub repo) at a fixed revision, served via the `huggingface` `ModelAdapter` from ADR-0003.

### 1. Exact pin

- **Repo:** `HuggingFaceTB/SmolLM2-135M-Instruct`.
- **Revision:** the `main` branch SHA at the time the ADR ships, recorded in `configs/model/smollm.yaml` and in the corresponding hydra-zen-built dataclass. Pinning a SHA — not just `revision: main` — is required so that re-running an old configuration does not silently pull a newer checkpoint.
- **Tokenizer:** the repo's bundled tokenizer; no overrides.
- **Chat template:** the model's bundled template; the adapter passes structured `messages` through `tokenizer.apply_chat_template(...)`.
- **dtype:** `bfloat16` on CUDA, `float32` on CPU. The adapter detects automatically.
- **Default `GenerationConfig` for the smoke test:** `temperature=0.7`, `top_p=0.9`, `max_output_tokens=128`, `seed=0`. These live in `configs/sampling/balanced.yaml` (per ADR-0007) and are not specific to SmolLM; the smoke test composition simply picks `model=smollm sampling=balanced`.

### 2. Why SmolLM (and not a different small model)

| Candidate                            | Size  | License         | Practical fit                                                                                                                                                               |
| ------------------------------------ | ----- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`SmolLM2-135M-Instruct`** (chosen) | 135 M | Apache 2.0      | Extremely light; realistic for smoke tests, laptop micro-batching, CPU fallback, and repeated local development. Quality is intentionally not the selection criterion.      |
| `SmolLM2-360M-Instruct`              | 360 M | Apache 2.0      | Still light and may be useful as an optional stronger smoke model, but the default should minimize VRAM and download footprint.                                             |
| `SmolLM2-1.7B-Instruct`              | 1.7 B | Apache 2.0      | Better output quality but too large for the default goal; it makes laptop micro-batching and repeated local smoke runs less accessible.                                     |
| `Qwen2.5-1.5B-Instruct`              | 1.5 B | Apache 2.0      | Strong quality. Heavier license review depending on use case. Bundled template differs across versions.                                                                     |
| `Llama-3.2-1B-Instruct`              | 1.0 B | Llama Community | Strong quality. License terms preclude unconditional redistribution; users must accept Meta's terms on Hugging Face Hub. Acceptable but adds friction for new contributors. |
| `Phi-3.5-mini-instruct`              | 3.8 B | MIT             | Heavier on a low-VRAM GPU; harder to fit alongside an embedding model and a judge model in the same memory.                                                                 |
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | 1.1 B | Apache 2.0      | Lighter, but instruction following lags meaningfully behind SmolLM2.                                                                                                        |

SmolLM2-135M-Instruct wins because the default model's job is not to provide high-quality generations; it is to exercise the framework's adapter, tokenization, sampling, batching, persistence, metrics, and telemetry paths as cheaply as possible. The 135M _Instruct_ variant still exercises the chat-shaped code path, but keeps VRAM and download costs low enough that contributors can run tests repeatedly on laptops.

### 3. Optional stronger local smoke model: `SmolLM2-360M-Instruct`

The default smoke-test path uses the 135M model. Contributors who want slightly more coherent sample outputs while still staying far below 1B parameters can opt into a tiered alternative:

- `configs/model/smollm_360m.yaml` registers `HuggingFaceTB/SmolLM2-360M-Instruct` for the same `huggingface` adapter.
- Use it via `aef-eval model=smollm_360m`. Tests under `tests/smoke/smollm/` may opt in via a `@pytest.mark.parametrize("model", ["smollm", "smollm_360m"], ...)` strategy when the extra runtime is acceptable.
- This is _not_ the default. The default remains the 135M model so smoke tests stay as lightweight and accessible as possible.

### 4. What the framework guarantees about SmolLM

- The HF adapter (per ADR-0003) advertises the following capabilities for SmolLM2-135M-Instruct:
  - `supports_streaming=True`
  - `supports_tool_use=False`
  - `max_context_tokens=8192` (matches the model's training context)
  - `requires_gpu=False` (the adapter may use CUDA automatically when available, but the model is small enough that CPU smoke tests are viable)
  - `is_remote=False`
  - `cost_reporting="none"` (local model, no per-token cost)
  - `supported_sampling_parameters=frozenset({"temperature", "top_k", "top_p", "repetition_penalty", "max_output_tokens", "seed"})` — all six.
  - `family="local-hf"`.
- The smoke test (`tests/smoke/smollm/test_end_to_end.py`; GPU-only assertions are separately gated `@pytest.mark.gpu` per ADR-0011) asserts:
  - Model loads in under 30 s on a 8 GB consumer GPU or a modern CPU laptop after the weights are cached.
  - A 5-row evaluation with `MockDatasetAdapter` and the v1 default metric suite (lexical + embedding subset; no learned/judge) completes in under 2 minutes on GPU and under 5 minutes on CPU.
  - `EvaluationRunResult.run_request.model_spec.revision` records the pinned SHA.
  - Re-running with the same `seed` produces identical generations (within HF's documented determinism guarantees).
- The smoke test does NOT assert specific metric values — model quality drifts across HF revisions even within a single instruct release, and we do not want every checkpoint update to break CI on metric thresholds. We assert _structure_, _latency bounds_, and _determinism_; metric _quality_ is a manual review concern.

### 5. Update / refresh policy

- The pin is reviewed once per quarter or when the upstream repo cuts a meaningful new revision.
- Updating the pin requires a follow-up entry in this ADR's `## More Information` section with the date, the new SHA, and a one-line note on why (e.g., "upstream fixed tokenizer regression").
- A _major_ update — switching to a different model entirely — supersedes this ADR.

### Non-goals

- We are NOT promising specific scoring outcomes. Smoke tests assert structure and timing only.
- We are NOT supporting quantized variants (4-bit, 8-bit) as the default. Users who want them install the `bitsandbytes` extra and select a quantized config; that path is out of scope here.
- We are NOT requiring GPU hardware for the default SmolLM smoke path. GPU-specific assertions remain behind `@pytest.mark.gpu`; the basic 135M smoke path may run on CPU when CI resources permit.
- We are NOT claiming SmolLM is the right judge model. Judges (per ADR-0014) are a separate selection.
- We are NOT supporting Llama 3.x as the default (license friction outweighs quality benefit at this size).

## Consequences

- Good, because every contributor and agent has the same default local model. A "works on my machine" report against `model=smollm` is precise.
- Good, because the SHA pin makes the smoke test reproducible across upstream changes. Updating the pin is a tracked, dated change.
- Good, because Apache-2.0 license has zero account-gating friction, so any new contributor (human or agent) can fetch the model on first run.
- Good, because the smoke test asserting on structure, latency, and determinism — but not on metric values — keeps CI stable across upstream model revisions.
- Bad, because 135M parameters is too small to produce consistently useful benchmark-quality answers. We accept that — the smoke test is for plumbing, batching, and artifact contracts, not model quality.
- Bad, because a future Hugging Face Hub outage breaks the smoke test. Mitigation: `HF_HUB_OFFLINE=1` plus a cached weights directory works once the model is present locally; the docs call this out.
- Neutral, because a slightly stronger alternative (`smollm_360m`) exists for local runs where output coherence matters more than minimum resource use; users opt in.

## Implementation Plan

- **Affected paths**:
  - `configs/model/smollm.yaml` — hydra-zen-built `HuggingFaceModelSpec` with the pinned SHA, `dtype: bfloat16`, the capability set above.
  - `configs/model/smollm_360m.yaml` — optional stronger local smoke config pinned to `SmolLM2-360M-Instruct`.
  - `backend/src/aef/adapters/models/huggingface.py` — already exists from ADR-0003; verify the SmolLM-specific defaults (chat template handling, dtype, attention impl) are correct.
  - `backend/tests/smoke/smollm/test_end_to_end.py` — the lightweight smoke test described in §4, with GPU-only batching assertions gated `@pytest.mark.gpu`.
  - `backend/tests/smoke/smollm/conftest.py` — fixture that ensures the model is cached locally and skips with a clear message if download fails (e.g., offline CI without prefetched cache).
  - `docs/dev_setup.md` (optional) — a one-page note for new contributors: "your first `aef-eval` run will download SmolLM weights into the Hugging Face cache."
- **Dependencies (already declared in ADR-0002 + ADR-0003)**:
  - `transformers>=4.45`, `torch>=2.4`, `accelerate>=0.34` in the `models-hf` optional group.
  - No new dependencies introduced by this ADR.
- **Patterns to follow**:
  - The pinned revision SHA appears in `configs/model/smollm.yaml`, not just on `main`. The hydra-zen builder reads it from the YAML and it lands on `EvaluationRunResult.run_request.model_spec.revision` for every run.
  - The smoke test runs against `model=smollm dataset=mock metrics=default` (a small subset that excludes learned/judge to avoid pulling additional models).
  - The CI workflow that runs SmolLM smoke jobs caches the HF Hub directory between runs (e.g., GitHub Actions cache keyed on `huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/<sha>`).
- **Patterns to avoid**:
  - Do NOT add metric-value assertions to the smoke test. Structure and timing only.
  - Do NOT make GPU availability a requirement for the default 135M smoke test. GPU-specific batching assertions can live behind `@pytest.mark.gpu`.
  - Do NOT pin to `main` without a SHA. `main` updates silently break reproducibility.
  - Do NOT bundle the model weights in the repo. They live in the HF cache.
- **Configuration**:
  - `AEF_HF_CACHE_DIR` env var — overrides the default HF cache location for CI environments that want a stable cache path.
  - `HF_HUB_OFFLINE=1` honored for fully offline runs once the model is cached locally.
- **Migration steps**: greenfield.

### Verification

- [ ] `configs/model/smollm.yaml` references `HuggingFaceTB/SmolLM2-135M-Instruct` with an explicit revision SHA (not `main`).
- [ ] `configs/model/smollm_360m.yaml` references `HuggingFaceTB/SmolLM2-360M-Instruct` with an explicit revision SHA.
- [ ] `aef-eval model=smollm dataset=mock metrics=default sampling=greedy` runs end-to-end on a CPU laptop and on a CUDA-equipped workstation with ≤ 8 GB VRAM.
- [ ] `tests/smoke/smollm/test_end_to_end.py` passes in the lightweight smoke job; GPU-only batching assertions are excluded by the default `pytest -m "not gpu and not network and not broker and not docker"` job (per ADR-0011).
- [ ] The smoke test asserts on structure (`isinstance(result, EvaluationRunResult)`), on `result.run_request.model_spec.revision == <pinned SHA>`, and on `result.telemetry.total_duration_ms < 300_000` (5 minutes CPU upper bound).
- [ ] The smoke test does NOT assert on metric _values_ — only on shapes and bounds.
- [ ] The HF adapter advertises the capability set above for the SmolLM specs (verifiable via a unit test).
- [ ] Re-running the smoke test with `seed=0` produces a generation byte-identical to a previous run on the same hardware (within HF's determinism caveats; assertion is conditional on a `__pytest_skip_if_nondeterministic_hardware__` fixture that detects known-noisy GPU hardware).

## Alternatives Considered

- **No default local model — let users pick**: rejected. CI would have nothing concrete to test, and contributor onboarding instructions would be a flowchart instead of a one-liner.
- **TinyLlama-1.1B as default**: rejected. Smaller and faster, but instruction-following quality is meaningfully worse, which makes "does this run produce sensible output" a less useful smoke check.
- **Llama-3.2-1B-Instruct**: rejected for v1. Strong quality, but the license requires per-user acceptance on Hugging Face Hub — friction we do not want for default smoke tests, especially for agents that fetch weights non-interactively.
- **Qwen2.5-1.5B-Instruct**: considered. Strong quality. Bundled chat template differs across versions and license review is more involved depending on use case. Acceptable as a _configurable_ choice, not the default.
- **Phi-3.5-mini-instruct**: rejected. 3.8 B parameters strain a low-VRAM GPU when an embedding model and judge model also need to fit alongside.
- **Pin to `main` instead of a SHA**: rejected. Loses reproducibility across upstream pushes.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §9.4.
- External references:
  - [SmolLM2 model collection](https://huggingface.co/collections/HuggingFaceTB/smollm2) — upstream model family and available parameter sizes (135M, 360M, 1.7B).
  - [SmolLM2 paper (arXiv:2502.02737)](https://arxiv.org/abs/2502.02737) — "SmolLM2: When Smol Goes Big — Data-Centric Training of a Small Language Model" (Allal et al., 2025); training data and evaluation methodology.
  - [`HuggingFaceTB/SmolLM2-135M-Instruct` model card](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct) — the default local smoke-test model selected by this ADR.
  - [Transformers chat templating documentation](https://huggingface.co/docs/transformers/chat_templating) — how the HF adapter applies the model's bundled chat template.
  - [Hugging Face Hub cache documentation](https://huggingface.co/docs/huggingface_hub/guides/manage-cache) — cache behavior referenced by `AEF_HF_CACHE_DIR` / `HF_HUB_OFFLINE`.
- Related ADRs:
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — the HF adapter, capabilities, and `GenerationConfig` plumbing this ADR consumes.
  - [`0007-cli-configuration-with-hydra-and-hydra-zen.md`](0007-cli-configuration-with-hydra-and-hydra-zen.md) — `model=smollm` is the default; the SHA pin lives in the corresponding `configs/model/smollm.yaml`.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — the smoke test passes under pyright strict and Ruff.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — the `@pytest.mark.gpu` marker and the smoke-suite layout this ADR uses.
- Revisit triggers:
  - Upstream releases SmolLM3 with significantly improved quality at the same VRAM footprint — bump the pin in this ADR's `## More Information` and update `configs/model/smollm.yaml`.
  - HuggingFaceTB changes the license terms — open a follow-up ADR comparing alternatives (likely Qwen).
  - The smoke test repeatedly hits HF Hub timeouts in CI — cache weights as a CI artifact rather than re-downloading.
