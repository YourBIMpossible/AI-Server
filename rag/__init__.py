"""rag — local retrieval over your own docs (ingest, query, drift). Depends on `aiserver`.

Vector store: sqlite-vec, single file at out/rag/index.db. Embeddings via the same
OpenAI-compatible endpoint as chat (EMBED_MODEL). Read-only on sources; outputs under out/.
"""
