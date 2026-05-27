"""
Quick end-to-end test of the RAG pipeline.
Run with: python test_pipeline.py
Make sure Qdrant is running and docs are indexed first.
"""
from generation.generator import ask

# Test queries — mix of simple and multi-part questions
queries = [
    "How do I add middleware in FastAPI?",
    "What is dependency injection in FastAPI?",
    "How do I handle file uploads?",
]

for query in queries:
    print("=" * 70)
    print(f"Q: {query}")
    print("=" * 70)

    result = ask(
        query,
        top_k=20,    # candidates from Qdrant per query variant
        top_n=5,     # final chunks after reranking
        use_hyde=True,
        use_rerank=True,
    )

    print(f"\nANSWER:\n{result['answer']}")
    print(f"\nSOURCES:")
    for src in result["sources"]:
        print(f"  - {src}")
    print()
