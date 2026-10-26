import pytest

from eventai.rag.loaders import build_chunks, read_sources
from eventai.rag.search_text import build_text_index, rrf_merge, search_text, tokenize

ALL = ["venues", "packages", "policies"]


@pytest.fixture(scope="module")
def index(fake_embedder):
    return build_text_index(build_chunks(read_sources()), fake_embedder, min_similarity=0.1)


def test_tokenize_keeps_ids_whole():
    assert tokenize("What does PKG-07 include?") == ["what", "does", "pkg-07", "include"]


def test_rrf_merge():
    scores = rrf_merge([["a", "b"], ["b", "c"]], k=60)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["c"] == pytest.approx(1 / 62)
    assert max(scores, key=scores.get) == "b"


def test_document_filter(index):
    hits = search_text(index, "Victorian hall with a ballroom", ["venues"])
    assert hits
    assert {h.source for h in hits} == {"venues.csv"}


def test_record_ids_filter(index):
    hits = search_text(index, "brick mill with a courtyard", ["venues"], record_ids=["V012", "V002"])
    assert {h.record_id for h in hits} <= {"V012", "V002"}
    assert hits[0].record_id == "V012"


def test_empty_record_ids_means_no_rows(index):
    assert search_text(index, "courtyard", ALL, record_ids=[]) == []


def test_exact_id_passes_the_minimum_score(index, fake_embedder):
    strict = build_text_index(index.chunks, fake_embedder, min_similarity=0.99)
    hits = search_text(strict, "What does PKG-07 include?", ALL)
    assert [h.record_id for h in hits] == ["PKG-07"]
    assert hits[0].bm25_rank == 1


def test_off_topic_query_has_no_hits(index):
    assert search_text(index, "xylophone quantum zebra", ALL) == []
    assert search_text(index, "   ", ALL) == []


def test_k_limit_and_order(index):
    hits = search_text(index, "dinner with wine and music", ALL, k=3)
    assert 0 < len(hits) <= 3
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_hit_carries_context_and_scores(index):
    hit = search_text(index, "converted mill courtyard exposed brick", ["venues"])[0]
    assert hit.record_id == "V012"
    assert hit.chunk_id == "venues.csv#V012"
    assert hit.context_text.startswith("Source: venues.csv | ID: V012")
    assert hit.vector_rank == 1 and hit.vector_similarity > 0.1
