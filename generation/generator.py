"""
generation/generator.py

The final stage of the RAG pipeline. Takes a user query + retrieved chunks
and calls Gemini to produce a grounded, cited answer.

Two public functions:
  - generate(query, chunks)  →  answer + sources  (generation only)
  - ask(query, ...)          →  full end-to-end: retrieval + generation
"""

import os
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

GENERATION_MODEL = "models/gemini-2.5-flash"
RATE_LIMIT_WAIT = 60
MAX_RETRIES = 8

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a precise technical documentation assistant.

You will receive a user question and a numbered list of reference passages \
retrieved from official documentation. Your job is to answer the question \
using ONLY the information in those passages.

Rules:
- Cite sources inline using [N] notation (e.g. "Use app.add_middleware() [1]").
- If the passages do not contain enough information, respond with exactly:
  "I don't have enough information in the provided context to answer this."
- Never fabricate or infer facts not present in the passages.
- Be concise, precise, and technical.
- Include relevant code examples from the passages when they help.
- If multiple passages support the same point, cite all relevant ones."""

_CONTEXT_TEMPLATE = """\
Reference passages:

{context_block}

Question: {query}

Answer:"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_context_block(chunks: list[dict]) -> str:
    """
    Format chunks into a numbered context block for the prompt.
    Each entry includes the breadcrumb (section hierarchy) and the text.

    Example output:
      [1] FastAPI > Middleware
      To add middleware, use the add_middleware() method...

      [2] FastAPI > Advanced Usage > CORS
      FastAPI provides a built-in CORSMiddleware...
    """
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        breadcrumb = chunk.get("breadcrumb", "").strip()
        text = chunk.get("text", "").strip()

        header = f"[{i}]" + (f" {breadcrumb}" if breadcrumb else "")
        lines.append(f"{header}\n{text}")

    return "\n\n".join(lines)


def _extract_sources(chunks: list[dict]) -> list[str]:
    """
    Extract unique source file paths from the chunks used as context.
    Deduplicates and sorts for consistency.
    """
    seen = set()
    sources = []
    for chunk in chunks:
        src = chunk.get("source", "").strip()
        if src and src not in seen:
            seen.add(src)
            sources.append(src)
    return sorted(sources)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(query: str, chunks: list[dict]) -> dict:
    """
    Generate a grounded answer from retrieved chunks.

    Args:
        query:  The original user question.
        chunks: Retrieved + reranked chunks from retrieval/pipeline.py.

    Returns:
        {
            "answer":      str           — the generated answer with [N] citations
            "sources":     list[str]     — unique source files referenced
            "chunks_used": list[dict]    — the chunks passed as context
            "model":       str           — model used for generation
        }
    """
    if not chunks:
        return {
            "answer": "I don't have enough information in the provided context to answer this.",
            "sources": [],
            "chunks_used": [],
            "model": GENERATION_MODEL,
        }

    context_block = _build_context_block(chunks)
    user_message = _CONTEXT_TEMPLATE.format(
        context_block=context_block,
        query=query
    )

    answer = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=[
                    {"role": "user", "parts": [{"text": _SYSTEM_PROMPT}]},
                    {"role": "model", "parts": [{"text": "Understood. I will answer only from the provided passages and cite sources using [N] notation."}]},
                    {"role": "user", "parts": [{"text": user_message}]},
                ]
            )
            answer = response.text.strip()
            break
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait = RATE_LIMIT_WAIT
                print(f"  [Generator] Rate limit hit. Waiting {wait}s for quota reset...")
            else:
                wait = 2 ** attempt
                print(f"  [Generator] Generation failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)

    if answer is None:
        answer = "Generation failed after retries. Please try again later."

    return {
        "answer": answer,
        "sources": _extract_sources(chunks),
        "chunks_used": chunks,
        "model": GENERATION_MODEL,
    }


def ask(
    query: str,
    top_k: int = 20,
    top_n: int = 5,
    use_hyde: bool = True,
    use_rerank: bool = True,
) -> dict:
    """
    Full end-to-end RAG pipeline: retrieval + generation in one call.

    This is the primary entry point for the API layer.
    Internally calls retrieval.pipeline.search() then generate().

    Args:
        query:      The user's question.
        top_k:      Candidates to retrieve per query variant.
        top_n:      Final chunks after reranking.
        use_hyde:   Enable HyDE query expansion.
        use_rerank: Enable LLM reranking.

    Returns:
        Same as generate() — answer, sources, chunks_used, model.
    """
    # Import here to avoid circular imports if retrieval ever imports generation
    from retrieval.pipeline import search

    print(f"[RAG] Query: {query!r}")

    chunks = search(query, top_k=top_k, top_n=top_n,
                    use_hyde=use_hyde, use_rerank=use_rerank)

    print(f"[RAG] Generating answer from {len(chunks)} chunks...")
    result = generate(query, chunks)

    print(f"[RAG] Done.\n")
    return result
