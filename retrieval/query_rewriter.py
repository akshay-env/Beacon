import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

GENERATION_MODEL = "models/gemini-2.5-flash"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_REWRITE_PROMPT = """\
You are a search query optimizer for a technical documentation search engine.

Rewrite the user's question into a precise, keyword-rich search query that will \
retrieve the most relevant documentation chunks. Focus on technical terms. \
Remove filler words. Do NOT answer the question — only rewrite it.

User question: {query}

Rewritten query (one line, no explanation):"""

_CONTEXTUALIZE_PROMPT = """\
Given a chat history and the latest user question which might reference context \
in the chat history (e.g. using pronouns like "it", "that", "this"), formulate a \
standalone question which can be understood without the chat history. \
Do NOT answer the question, just reformulate it if needed and otherwise return it as is.

Chat History:
{history_str}

Latest User Question: {query}

Standalone Question:"""

_HYDE_PROMPT = """\
You are a technical documentation expert.

Given the user's question, write a short passage (3–5 sentences) that would \
plausibly appear in official technical documentation and directly answer the question. \
Write in documentation style — precise, factual, and technical. \
Do NOT say "I" or answer conversationally.

User question: {query}

Hypothetical documentation passage:"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rewrite_query(query: str, history: list[dict] = None) -> str:
    """
    Rewrite the user's query to be more precise for vector search.
    If history is provided, contextualize the query first.
    """
    if history:
        history_str = "\n".join([f"{h['role'].capitalize()}: {h['content']}" for h in history])
        prompt = _CONTEXTUALIZE_PROMPT.format(history_str=history_str, query=query)
    else:
        prompt = _REWRITE_PROMPT.format(query=query)
        
    try:
        response = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt
        )
        rewritten = response.text.strip()
        if not rewritten or len(rewritten) > 500:
            return query
        return rewritten
    except Exception as e:
        print(f"  [QueryRewriter] rewrite failed: {e}. Using original query.")
        return query


def generate_hyde_passage(query: str, history: list[dict] = None) -> str:
    """
    Generate a Hypothetical Document Embedding (HyDE) passage.
    """
    # If we have history, contextualize the query first so HyDE isn't confused by pronouns
    actual_query = query
    if history:
        actual_query = rewrite_query(query, history)
        
    prompt = _HYDE_PROMPT.format(query=actual_query)
    try:
        response = client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt
        )
        passage = response.text.strip()
        if not passage:
            return actual_query
        return passage
    except Exception as e:
        print(f"  [QueryRewriter] HyDE generation failed: {e}. Using original query.")
        return actual_query


def expand_query(query: str, history: list[dict] = None) -> list[str]:
    """
    Full query expansion pipeline. Returns a list of query variants to search with.
    If history is provided, the rewritten query acts as the contextualized base.
    """
    rewritten = rewrite_query(query, history)
    hyde = generate_hyde_passage(query, history)

    # Deduplicate
    queries = [query]
    if rewritten.lower() != query.lower():
        queries.append(rewritten)
    queries.append(hyde)

    return queries
