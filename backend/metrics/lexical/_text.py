"""Shared text-normalization helpers used by the lexical metrics."""

from __future__ import annotations

import re
import string
import unicodedata

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalize(text: str, *, lowercase: bool = True, strip_punct: bool = True) -> str:
    """
    Apply the canonical text normalization for lexical scoring.

    Steps: NFKC unicode normalization, optional lowercasing, optional punctuation stripping,
    whitespace collapsing.

    :param text: Text to normalize or tokenize.
    :param lowercase: Whether to lowercase during normalization.
    :param strip_punct: Whether to strip punctuation during normalization.

    :return: Result string.
    """
    norm = unicodedata.normalize("NFKC", text)
    if lowercase:
        norm = norm.lower()
    if strip_punct:
        norm = norm.translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", norm).strip()


def whitespace_tokenize(text: str) -> list[str]:
    """
    Whitespace tokenizer; the lexical metrics are pre-normalized.

    :param text: Text to normalize or tokenize.

    :return: Result string.
    """
    return [tok for tok in text.split() if tok]
