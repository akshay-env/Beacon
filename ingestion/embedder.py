import os
import uuid
import time
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_client.http.exceptions import UnexpectedResponse
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIM = 3072      # output dimension for gemini-embedding-2
BATCH_SIZE = 100          # max texts per API call — saturates each request
SLEEP_BETWEEN_BATCHES = 15   # seconds between batches — ~4 req/min, safe for free tier
RATE_LIMIT_WAIT = 60         # seconds to wait on a 429 — full quota window reset
MAX_RETRIES = 8              # higher since 429s just need time, not a failure signal

qdrant = QdrantClient("localhost", port=6333)


def get_embeddings(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """
    Embed a batch of texts using the Gemini embedding model.
    - On 429 (rate limit): waits RATE_LIMIT_WAIT seconds — one full quota window.
    - On other errors: exponential backoff.
    """
    for attempt in range(MAX_RETRIES):
        try:
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(task_type=task_type)
            )
            return [e.values for e in result.embeddings]

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait = RATE_LIMIT_WAIT
                print(f"  [Attempt {attempt + 1}/{MAX_RETRIES}] Rate limit hit. Waiting {wait}s for quota reset...")
            else:
                wait = 2 ** attempt
                print(f"  [Attempt {attempt + 1}/{MAX_RETRIES}] Embedding failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Failed to embed batch after {MAX_RETRIES} retries.")


def _get_existing_count() -> int:
    """Return how many points are already in the 'docs' collection, or 0 if it doesn't exist."""
    try:
        info = qdrant.get_collection("docs")
        return info.points_count or 0
    except UnexpectedResponse:
        return 0


def _ensure_collection():
    """Create the collection if it doesn't exist yet. Never wipes existing data."""
    try:
        qdrant.get_collection("docs")
    except UnexpectedResponse:
        qdrant.create_collection(
            collection_name="docs",
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
        )
        print("  Created fresh 'docs' collection.")


def embed_and_store(chunks: list[dict], fresh: bool = False):
    """
    Embed all chunks and store them in Qdrant.

    Supports resumable indexing — if interrupted, re-running will pick up
    from where it left off instead of starting over.

    Args:
        chunks: All chunks from the chunker (full list every time).
        fresh:  If True, wipe the collection and re-index from scratch.
                If False (default), skip already-indexed chunks and resume.
    """
    if fresh:
        # Explicit full re-index requested — wipe and recreate
        try:
            qdrant.delete_collection("docs")
        except Exception:
            pass
        qdrant.create_collection(
            collection_name="docs",
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
        )
        already_stored = 0
        print("  Wiped and recreated 'docs' collection.")
    else:
        _ensure_collection()
        already_stored = _get_existing_count()

    total = len(chunks)

    if already_stored >= total:
        print(f"All {total} chunks already indexed. Nothing to do.")
        return

    if already_stored > 0:
        print(f"Resuming from chunk {already_stored}/{total} (skipping already-indexed).")

    print(f"Embedding and storing chunks {already_stored + 1}–{total} "
          f"using Gemini API ({EMBEDDING_MODEL})...")

    for i in range(already_stored, total, BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [chunk["text"] for chunk in batch]

        embeddings = get_embeddings(texts, task_type="RETRIEVAL_DOCUMENT")

        points = []
        for j, embedding in enumerate(embeddings):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "text": batch[j]["text"],
                    "source": batch[j]["source"],
                    "breadcrumb": batch[j].get("breadcrumb", "")
                }
            ))

        qdrant.upsert(collection_name="docs", points=points)
        stored_so_far = min(i + BATCH_SIZE, total)
        print(f"  Stored {stored_so_far}/{total} chunks")

        # Rate-limit guard — sleep between batches to stay under RPM ceiling
        if stored_so_far < total:
            time.sleep(SLEEP_BETWEEN_BATCHES)

    print("Done! All chunks embedded and stored.")