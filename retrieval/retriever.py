import os
import time
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, SparseVector, Fusion
from dotenv import load_dotenv

from ingestion.sparse import build_sparse_vector

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
qdrant = QdrantClient("localhost", port=6333)

EMBEDDING_MODEL = "models/gemini-embedding-2"
COLLECTION_NAME = "docs"
SPARSE_VECTOR_NAME = "text_sparse"
RATE_LIMIT_WAIT = 60
MAX_RETRIES = 8


def _embed_query(text: str) -> list[float]:
    """
    Embed a single query string using task_type=RETRIEVAL_QUERY.
    Uses RETRIEVAL_QUERY (not RETRIEVAL_DOCUMENT) — this is important:
    the model applies asymmetric encoding so queries and docs are comparable.
    """
    for attempt in range(MAX_RETRIES):
        try:
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=[text],
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
            )
            return result.embeddings[0].values

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait = RATE_LIMIT_WAIT
                print(f"  [Retriever] Rate limit hit. Waiting {wait}s...")
            else:
                wait = 2 ** attempt
                print(f"  [Retriever] Embedding failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError("Failed to embed query after retries.")


def retrieve(query: str, top_k: int = 20) -> list[dict]:
    """
    Hybrid search: combines dense semantic search + sparse keyword search
    via Qdrant's native Reciprocal Rank Fusion (RRF).

    How it works:
      1. Dense leg:   embed query → cosine similarity search over Gemini vectors
      2. Sparse leg:  tokenize query → TF keyword search over sparse vectors
      3. RRF fusion:  Qdrant merges both ranked lists using RRF scoring
                      (rank_score = Σ 1/(k + rank_i) for each result list)

    Dense search excels at semantic similarity ("how do I handle errors?").
    Sparse search excels at exact term matching ("HTTPException", "Depends").
    Together they cover what neither does alone.

    Falls back to dense-only search if sparse vectors aren't present
    (e.g. collection was indexed with the old schema).
    """
    dense_vector = _embed_query(query)
    sparse_dict = build_sparse_vector(query)

    try:
        # Hybrid search with RRF
        hits = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(
                    query=dense_vector,
                    limit=top_k,
                ),
                Prefetch(
                    query=SparseVector(
                        indices=list(sparse_dict.keys()),
                        values=list(sparse_dict.values()),
                    ),
                    using=SPARSE_VECTOR_NAME,
                    limit=top_k,
                ),
            ],
            query=Fusion.RRF,
            limit=top_k,
            with_payload=True,
        )
    except Exception:
        # Fallback: dense-only search (for collections without sparse vectors)
        hits = qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=dense_vector,
            limit=top_k,
            with_payload=True,
        )

    return [
        {
            "text":       hit.payload.get("text", ""),
            "source":     hit.payload.get("source", ""),
            "breadcrumb": hit.payload.get("breadcrumb", ""),
            "score":      round(hit.score, 4),
        }
        for hit in hits.points
    ]


def multi_retrieve(queries: list[str], top_k: int = 20) -> list[dict]:
    """
    Run retrieve() for each query and merge results, deduplicating on text content.
    Used when query_rewriter generates multiple query variants (HyDE + rewrite).
    Preserves the highest score seen for each unique chunk.
    """
    seen: dict[str, dict] = {}  # text → best result dict

    for query in queries:
        results = retrieve(query, top_k=top_k)
        for r in results:
            key = r["text"]
            if key not in seen or r["score"] > seen[key]["score"]:
                seen[key] = r

    # Return merged results sorted by score descending
    merged = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
    return merged
