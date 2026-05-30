"""
ingestion/sparse.py

Generates TF-based sparse vectors from text for Qdrant hybrid search.

These sparse vectors power the keyword/BM25-style leg of hybrid retrieval.
When combined with dense semantic vectors via Qdrant's RRF fusion, the
system handles both semantic similarity AND exact keyword matching — the
two complement each other well for technical documentation queries.

Why TF instead of full BM25:
  BM25 requires IDF weights, which need the full corpus at index time.
  Since we index incrementally (resumable), computing IDF per-batch would
  be inconsistent. TF alone is still highly effective for exact-term
  retrieval and requires zero corpus-level statistics.

Term → index mapping:
  Uses CRC32 for deterministic, stable hashing (no PYTHONHASHSEED issues).
  Collision probability for typical doc vocabulary sizes is negligible.
"""

import re
import binascii
from collections import Counter

# ---------------------------------------------------------------------------
# Stopwords (excluded from sparse vectors — too frequent to be discriminative)
# ---------------------------------------------------------------------------

STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "shall", "should", "may", "might", "must", "can", "could", "not",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "we", "us", "our", "you", "your", "i", "me", "my", "he", "she", "him",
    "his", "her", "as", "if", "so", "no", "all", "also", "more", "other",
    "than", "then", "when", "where", "which", "who", "how", "what", "any",
    "some", "each", "only", "into", "about", "through", "after", "before",
    "up", "out", "just", "such", "while", "however", "therefore",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def term_to_index(term: str) -> int:
    """
    Deterministically map a term string to a non-negative 31-bit integer.
    CRC32 is stable across Python versions and processes (unlike hash()).
    """
    return binascii.crc32(term.encode("utf-8")) & 0x7FFFFFFF


def tokenize(text: str) -> list[str]:
    """
    Tokenize text into lowercase alphanumeric tokens, removing stopwords.
    Preserves code identifiers (underscores are kept as word characters
    since technical docs are full of things like `add_middleware` or `Depends`).
    """
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def build_sparse_vector(text: str) -> dict[int, float]:
    """
    Build a {term_index: tf_weight} sparse vector from text.

    The result is ready to be passed to Qdrant's SparseVector as
    indices=list(result.keys()), values=list(result.values()).

    Returns an empty dict for empty/stopword-only input.
    """
    tokens = tokenize(text)
    if not tokens:
        return {}

    counts = Counter(tokens)
    total = len(tokens)

    result: dict[int, float] = {}
    for term, count in counts.items():
        idx = term_to_index(term)
        tf = count / total
        # On hash collision, keep the higher weight (conservative)
        result[idx] = max(result.get(idx, 0.0), tf)

    return result
