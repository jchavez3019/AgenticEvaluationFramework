"""Metric framework — Protocol, registry, and v1 default suite.

Importing :mod:`backend.metrics` registers every shipped metric:

- 8 lexical metrics (`bleu`, `rouge`, `ngram_overlap`, `chrf`, `meteor`,
  `exact_match`, `token_f1`, `fuzzy_match`)
- 4 operational metrics (`latency`, `token_counts`, `cost`,
  `output_validity`)

Embedding, learned, and RAG metrics ship as deferred placeholders; their
modules contain :class:`NotImplementedError` markers so contributors who
look for them get a clear pointer to the milestone where they land.

# ADR: Default Metric Suite and Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

from backend.metrics.base import (
    Metric,
    MetricInputs,
    MetricSpec,
    metric_factory,
)

# Eagerly register every shipped metric. The registration helpers run at
# module import; importing the modules below is the side-effect.
from backend.metrics.lexical import (
    bleu as _bleu,
)
from backend.metrics.lexical import (
    chrf as _chrf,
)
from backend.metrics.lexical import (
    exact_match as _exact_match,
)
from backend.metrics.lexical import (
    fuzzy_match as _fuzzy_match,
)
from backend.metrics.lexical import (
    meteor as _meteor,
)
from backend.metrics.lexical import (
    ngram as _ngram,
)
from backend.metrics.lexical import (
    rouge as _rouge,
)
from backend.metrics.lexical import (
    token_f1 as _token_f1,
)
from backend.metrics.operational import (
    cost as _cost,
)
from backend.metrics.operational import (
    latency as _latency,
)
from backend.metrics.operational import (
    output_validity as _output_validity,
)
from backend.metrics.operational import (
    token_counts as _token_counts,
)
from backend.metrics.registry import (
    build_metric,
    list_metrics,
    register_metric,
    unregister_metric,
)

_REGISTERED_VIA_IMPORT = (
    _bleu,
    _chrf,
    _exact_match,
    _fuzzy_match,
    _meteor,
    _ngram,
    _rouge,
    _token_f1,
    _latency,
    _token_counts,
    _cost,
    _output_validity,
)

__all__ = [
    "Metric",
    "MetricInputs",
    "MetricSpec",
    "build_metric",
    "list_metrics",
    "metric_factory",
    "register_metric",
    "unregister_metric",
]
