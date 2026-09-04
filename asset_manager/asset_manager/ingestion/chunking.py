"""Word-based chunking and content hashing for document ingestion.

Chunking is measured in words, not tokens — a reasonable approximation for
v1 (roughly 0.75 words per token) without adding a tokenizer dependency.
"""

import hashlib


def chunk_text(text: str, words_per_chunk: int = 600, overlap_words: int = 75) -> list[str]:
    """Split text into overlapping chunks along word boundaries."""
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    step = max(words_per_chunk - overlap_words, 1)
    while start < len(words):
        chunk_words = words[start : start + words_per_chunk]
        chunks.append(" ".join(chunk_words))
        if start + words_per_chunk >= len(words):
            break
        start += step
    return chunks


def file_hash(content: bytes) -> str:
    """SHA-256 hex digest of raw file bytes — used to detect changed/removed files."""
    return hashlib.sha256(content).hexdigest()
