"""METEOR via NLTK (lazy-imported, downloads the wordnet corpus on first use)."""

from __future__ import annotations

from typing import Any

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.registry import register_metric


class MeteorMetric(BaseMetric):
    """METEOR score (NLTK)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Hold the NLTK module reference (lazy)."""
        super().__init__(*args, **kwargs)
        self._meteor: Any = None

    def _ensure_dependencies(self) -> Any:
        if self._meteor is None:
            from nltk.translate.meteor_score import (  # type: ignore[import-untyped]
                meteor_score,
            )

            self._meteor = meteor_score
        return self._meteor

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        references = inputs.references or ([inputs.reference] if inputs.reference else None)
        if not references:
            raise ValueError("meteor requires `reference` or `references`")
        meteor_score = self._ensure_dependencies()
        ref_tokens = [r.split() for r in references]
        cand_tokens = inputs.candidate.split()
        score = float(meteor_score(ref_tokens, cand_tokens))
        return score, []


try:
    register_metric("meteor", metric_factory(MeteorMetric))
except ValueError:
    pass
