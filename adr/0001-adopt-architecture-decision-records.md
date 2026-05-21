---
status: proposed
date: 2026-05-17
decision-makers: jorgejc2
---

# Adopt Architecture Decision Records

## Context and Problem Statement

The Agentic Evaluation Framework is being designed as a multi-layer system (Python backend, Python CLI, Angular frontend) with several non-trivial architectural choices: an adapter pattern for models and datasets, a hybrid local/distributed execution engine, a persistent SQLite-backed run store, strict typing rules, and a metric plugin system. Many of these choices have realistic alternatives and meaningful long-term consequences.

We expect this framework to be extended over time both by humans and by coding agents. Without a durable record of _why_ a particular pattern was chosen, future contributors will:

- Re-litigate decisions that have already been considered.
- Introduce dependencies, patterns, or workflows that contradict prior choices without realizing it.
- Lose institutional context as the project grows beyond what fits in any single contributor's head.

We need a lightweight, reviewable, version-controlled mechanism for capturing these decisions and the reasoning behind them.

## Decision

Adopt **Architecture Decision Records (ADRs)** as the canonical mechanism for recording cross-cutting design decisions in this repository.

Specifically:

- All ADRs live in the top-level `adr/` directory at the repository root.
- ADR filenames follow the pattern `NNNN-slug.md`, where `NNNN` is a zero-padded ordinal that matches the `ADR-NNNN` references used in `high_level_architecture.md` and elsewhere.
- Each ADR carries YAML front matter with at minimum: `status`, `date`, `decision-makers`. Optional fields: `consulted`, `informed`, `supersedes`, `superseded-by`.
- Status lifecycle: `proposed` → `accepted` → optionally `deprecated` or `superseded by ...`.
- Two templates are permitted: a **simple** template for decisions with one clear winner and minimal tradeoffs, and a **MADR-style** template for decisions with multiple genuine alternatives that warrant structured comparison.
- Every ADR must include an **Implementation Plan** section naming the affected paths, dependencies (with version constraints where applicable), patterns to follow, patterns to avoid, and migration steps where relevant.
- Every ADR must include a **Verification** section as a list of checkboxes that an agent can validate after implementation.
- The directory contains a `README.md` index listing every ADR with its number, title, status, and scope.
- When code is written that implements or is governed by an ADR, the entry-point file should carry a short comment of the form `# ADR: <title>` followed by `# See: adr/<file>.md`.
- ADRs that are superseded link to their replacement, and the replacement links back. Accepted ADRs are not rewritten in place; clarifications are appended to a `## More Information` section with a date stamp.

Non-goals:

- We are NOT adopting RFCs, design docs, or any other heavier document format in addition to ADRs.
- We are NOT requiring an ADR for routine implementation choices (bug fixes, refactors within an established pattern, style preferences already covered by linters).
- We are NOT building custom ADR tooling. We rely on plain Markdown plus the `adr-skill` resources already available in the developer environment.

## Consequences

- Good, because every architectural choice has a single, discoverable, reviewable home.
- Good, because new contributors and coding agents can trace any pattern in the codebase back to its rationale through the `# ADR:` code comments.
- Good, because the ADR file itself is structured well enough to act as an executable specification for an agent implementing the decision.
- Good, because the `proposed` status lets us socialize and revise a decision without merging code that depends on it.
- Bad, because writing an ADR adds friction up front for non-trivial decisions. We accept this as a deliberate cost — the decisions worth capturing are exactly the ones worth slowing down to think about.
- Bad, because the ADR set must be kept in sync with the code. If a decision is changed without writing a superseding ADR, the codebase will silently drift from its documented architecture. This is mitigated by enforcing ADR review during PRs that touch governed areas.
- Neutral, because ADRs duplicate some information that also lives in `high_level_architecture.md`. The architecture doc is the **map**; ADRs are the **detailed rationale and implementation contracts**. Each serves a different reader.

## Implementation Plan

- **Affected paths**:
  - `adr/` — new directory at the repository root (already created).
  - `adr/README.md` — index of all ADRs, kept current as new ones are added.
  - `adr/0001-adopt-architecture-decision-records.md` — this ADR.
  - `high_level_architecture.md` — already references ADRs by number; no edit needed for this ADR.
- **Dependencies**: none. ADRs are plain Markdown.
- **Patterns to follow**:
  - For new ADRs, copy the structure of this file (simple template) or use the MADR layout for options-heavy decisions.
  - Place YAML front matter at the very top of the file.
  - Use present-tense imperative verb phrases for titles ("Adopt X", "Use Y for Z", "Replace A with B").
  - Keep ADRs self-contained: define acronyms, name systems explicitly, and link to related ADRs rather than relying on tribal knowledge.
- **Patterns to avoid**:
  - Do NOT edit an `accepted` ADR's Decision or Consequences in place. Append dated notes to `## More Information`, or write a superseding ADR.
  - Do NOT use vague verification criteria such as "it works" or "performance is good". Each criterion must be testable.
  - Do NOT introduce a second ADR directory (e.g., `docs/adr/`) once `adr/` is in use.
- **Configuration**: none.
- **Migration steps**: none — this is the first ADR.

### Verification

- [ ] `adr/` directory exists at the repository root.
- [ ] `adr/README.md` exists and lists every ADR with number, title, status, and scope.
- [ ] `adr/0001-adopt-architecture-decision-records.md` exists with this content and YAML front matter.
- [ ] All subsequent ADRs follow the `NNNN-slug.md` filename pattern.
- [ ] All subsequent ADRs include `status`, `date`, and `decision-makers` in YAML front matter.
- [ ] All subsequent ADRs include an `Implementation Plan` and a `Verification` section.
- [ ] Once code begins to land, files implementing an ADR carry `# ADR:` reference comments at their entry points.

## Alternatives Considered

- **No formal decision record** — rely on commit messages, PR descriptions, and tribal knowledge. Rejected because that information is not discoverable from inside the codebase and decays as contributors rotate.
- **Free-form design documents in a `docs/` folder** — rejected because design docs are typically narrative and time-bound, while ADRs are structured and durable. ADRs make status, scope, and replacement explicit; ad-hoc design docs do not.
- **External tools (Confluence, Notion, etc.)** — rejected because external tools decouple decisions from the code that implements them. ADRs in the repo travel with the source, are version-controlled, and are visible to coding agents operating on the working tree.

## More Information

- High-level architecture overview: [`../high_level_architecture.md`](../high_level_architecture.md).
- External references:
  - [MADR project](https://adr.github.io/madr/) — one of the structured ADR template variants used when a decision has multiple meaningful options.
  - [Documenting Architecture Decisions by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) — original short-form ADR pattern.
  - [Architecture Decision Records overview](https://adr.github.io/) — broader ADR ecosystem and tooling references.
- The ADR conventions in this repo are aligned with the `adr-skill` resources available in the developer environment, with one local deviation: filenames use `NNNN-slug.md` instead of `YYYY-MM-DD-slug.md` to match the `ADR-NNNN` references already established in `high_level_architecture.md`.
- Revisit trigger: if the team grows or the ADR set exceeds ~30 entries, reconsider categorizing ADRs into subdirectories (`adr/backend/`, `adr/frontend/`, `adr/infra/`).
