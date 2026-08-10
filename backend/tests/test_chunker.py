from app.rag.chunker import chunk_text, count_tokens


def make_paragraph(i: int, sentences: int = 8) -> str:
    return " ".join(
        f"This is sentence {j} of paragraph {i} discussing artificial intelligence policy in detail."
        for j in range(sentences)
    )


LONG_TEXT = "\n\n".join(make_paragraph(i) for i in range(30))


def test_short_text_single_chunk():
    chunks = chunk_text("A short article body.")
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_long_text_respects_target_size():
    chunks = chunk_text(LONG_TEXT, target_tokens=300, overlap_tokens=50)
    assert len(chunks) > 1
    for chunk in chunks:
        # paragraphs are atomic, so allow modest overshoot
        assert count_tokens(chunk.text) <= 300 * 1.6


def test_chunk_indexes_sequential():
    chunks = chunk_text(LONG_TEXT, target_tokens=300, overlap_tokens=50)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_overlap_carries_content():
    # overlap budget must fit at least one whole paragraph (~120 tokens here);
    # overlap is carried at unit (paragraph) granularity by design
    chunks = chunk_text(LONG_TEXT, target_tokens=300, overlap_tokens=150)
    tail_paragraph = chunks[0].text.split("\n\n")[-1]
    assert tail_paragraph in chunks[1].text


def test_oversized_single_paragraph_is_split():
    huge = " ".join(f"Sentence number {i} keeps going with more words." for i in range(500))
    chunks = chunk_text(huge, target_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1


def test_empty_text():
    assert chunk_text("") == []
