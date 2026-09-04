from asset_manager.ingestion.chunking import chunk_text, file_hash


def test_chunk_text_short_text_returns_one_chunk():
    text = "one two three four five"
    chunks = chunk_text(text, words_per_chunk=10, overlap_words=2)
    assert chunks == ["one two three four five"]


def test_chunk_text_splits_on_word_boundaries():
    words = [f"w{i}" for i in range(20)]
    text = " ".join(words)
    chunks = chunk_text(text, words_per_chunk=10, overlap_words=2)
    assert len(chunks) == 3
    assert chunks[0] == " ".join(words[0:10])
    # second chunk starts `overlap_words` before the end of the first
    assert chunks[1].startswith(" ".join(words[8:10]))


def test_chunk_text_empty_string_returns_no_chunks():
    assert chunk_text("", words_per_chunk=10, overlap_words=2) == []


def test_file_hash_is_deterministic_and_content_sensitive():
    h1 = file_hash(b"hello world")
    h2 = file_hash(b"hello world")
    h3 = file_hash(b"hello mars")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # sha256 hex digest
