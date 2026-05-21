# Architecture Decision Records

This directory holds the Architecture Decision Records (ADRs) for the Agentic Evaluation Framework. Every cross-cutting design choice that future contributors or coding agents need to respect lives here.

If you are an agent working in this repository, **read the relevant ADRs before changing anything in the area they govern.** ADRs are not optional documentation; they are executable specifications.

## Conventions

- **Filename:** `NNNN-slug.md`, where `NNNN` is a zero-padded ordinal that matches the `ADR-NNNN` references used elsewhere in the repo (notably `high_level_architecture.md`).
- **Status lifecycle:** `proposed` → `accepted` → optionally `deprecated` or `superseded by ...`. Status and date live in YAML front matter at the top of each ADR.
- **Mutability:** prefer appending dated notes in `## More Information` over rewriting accepted ADRs. If a decision changes materially, write a new ADR that explicitly supersedes the old one.
- **Templates:** simple template for one-clear-winner decisions; MADR (options-heavy) template for decisions with multiple realistic alternatives that warrant structured comparison.

## How to Read This Index

The table below is the canonical list of ADRs in this project. Status reflects the current lifecycle state. The high-level architecture document (`../high_level_architecture.md`) cross-references these by number.

| #    | Title                                                                                                                   | Status   | Scope                      |
| ---- | ----------------------------------------------------------------------------------------------------------------------- | -------- | -------------------------- |
| 0001 | [Adopt Architecture Decision Records](0001-adopt-architecture-decision-records.md)                                      | proposed | Process / governance       |
| 0002 | [Backend Technology Stack](0002-backend-technology-stack.md)                                                            | proposed | Backend foundation         |
| 0003 | [Adapter Architecture for Models and Datasets](0003-adapter-architecture-for-models-and-datasets.md)                    | proposed | Backend extensibility      |
| 0004 | [Default Metric Suite and Metric-Plugin Contract](0004-default-metric-suite-and-plugin-contract.md)                     | proposed | Backend metrics            |
| 0005 | [Execution Engine — Local and Distributed](0005-execution-engine-local-and-distributed.md)                              | proposed | Backend scalability        |
| 0006 | [Persistence — SQLite Default, Postgres Swap-In](0006-persistence-sqlite-default-postgres-swap-in.md)                   | proposed | Backend storage            |
| 0007 | [CLI Configuration with Hydra and hydra-zen](0007-cli-configuration-with-hydra-and-hydra-zen.md)                        | proposed | CLI                        |
| 0008 | [Frontend Stack — Angular, Strict TS, Plotly, Mermaid](0008-frontend-stack-angular-strict-typescript-plotly-mermaid.md) | proposed | Frontend                   |
| 0009 | [Frontend Docker Dev Environment](0009-frontend-docker-dev-environment.md)                                              | proposed | Frontend / dev environment |
| 0010 | [Code-Quality Standards](0010-code-quality-standards.md)                                                                | proposed | Cross-cutting              |
| 0011 | [Testing Strategy and Mock Adapters](0011-testing-strategy-and-mock-adapters.md)                                        | proposed | Cross-cutting              |
| 0012 | [Logging and Telemetry Contract](0012-logging-and-telemetry-contract.md)                                                | proposed | Cross-cutting              |
| 0013 | [Default Local Model — SmolLM](0013-default-local-model-smollm.md)                                                      | proposed | Backend / dev environment  |
| 0014 | [LLM-as-Judge Contract and Bias-Mitigation Defaults](0014-llm-as-judge-contract-and-bias-mitigation.md)                 | proposed | Backend metrics            |

## Code ↔ ADR Linking

Once implementation begins, files governed by an ADR should carry a short reference comment near the entry point, for example:

```python
# ADR: Adapter architecture
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
```

This makes it easy for both humans and agents to discover the reasoning behind a pattern when reading the code.
