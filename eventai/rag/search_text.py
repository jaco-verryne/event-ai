"""Text search on the text fields: Chroma vectors and BM25 keywords, merged with RRF (D3)."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel
from rank_bm25 import BM25Okapi

from eventai.rag.chunks import Chunk

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DOCUMENTS = {"venues.csv": "venues", "packages.json": "packages", "policies.csv": "policies"}
CANDIDATES = 20  # per ranking, before the merge
RRF_K = 60
# Calibrated on 25 Oct with bge-small: relevant hits scored 0.51-0.73 (Q6 walled garden
# 0.52, cobbled courtyard 0.51); off-topic probes scored 0.45-0.62 (weather, football,
# password). The bands overlap, so this cut only removes clearly unrelated text. The
# router (out_of_scope) and the answer step handle the rest.
MIN_SIMILARITY = 0.5

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class SearchHit(BaseModel):
    chunk_id: str
    source: str
    record_id: str
    score: float  # RRF score
    vector_similarity: float | None
    bm25_score: float | None
    vector_rank: int | None
    bm25_rank: int | None
    context_text: str


class Embedder(Protocol):
    def passages(self, texts: list[str]) -> list[list[float]]: ...
    def query(self, text: str) -> list[float]: ...


class FastEmbedder:
    """Local embeddings, so search uses no API quota (D2)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        # Import here: fastembed loads onnxruntime, and the tests use a fake embedder.
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name)

    def passages(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.passage_embed(texts)]

    def query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()


@dataclass
class TextIndex:
    collection: chromadb.Collection
    bm25: BM25Okapi
    chunks: list[Chunk]
    embedder: Embedder
    min_similarity: float


def tokenize(text: str) -> list[str]:
    # Keeps IDs such as "PKG-07" as one token, so BM25 can tell PKG-01 from PKG-07.
    return _TOKEN.findall(text.lower())


def build_text_index(
    chunks: Sequence[Chunk],
    embedder: Embedder | None = None,
    min_similarity: float = MIN_SIMILARITY,
) -> TextIndex:
    embedder = embedder or FastEmbedder()
    client = chromadb.EphemeralClient(ChromaSettings(anonymized_telemetry=False))
    collection = client.create_collection(
        name=f"chunks-{uuid.uuid4().hex[:8]}",  # the in-memory client is shared in one process
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )
    collection.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=embedder.passages([c.embedding_text for c in chunks]),
        documents=[c.embedding_text for c in chunks],
        metadatas=[
            {**c.metadata, "document": DOCUMENTS[c.source], "source": c.source, "record_id": c.record_id}
            for c in chunks
        ],
    )
    # BM25 also sees the record ID; the vector text stays text fields only.
    bm25 = BM25Okapi([tokenize(f"{c.record_id} {c.embedding_text}") for c in chunks])
    return TextIndex(collection, bm25, list(chunks), embedder, min_similarity)


def search_text(
    index: TextIndex,
    query: str,
    documents: Sequence[str],
    record_ids: Sequence[str] | None = None,
    k: int = 5,
) -> list[SearchHit]:
    """Rank the chunks of `documents` by meaning and keywords. `record_ids` limits the
    search to the rows that query_sql returned. An empty list means no rows, so no hits."""
    allowed = [
        i
        for i, c in enumerate(index.chunks)
        if DOCUMENTS[c.source] in documents and (record_ids is None or c.record_id in record_ids)
    ]
    query_tokens = tokenize(query)
    if not allowed or not query_tokens:
        return []

    similarity = _vector_similarity(index, query, documents, record_ids, n=min(CANDIDATES, len(allowed)))
    bm25_all = index.bm25.get_scores(query_tokens)
    bm25 = {
        index.chunks[i].chunk_id: float(bm25_all[i])
        for i in sorted(allowed, key=lambda i: -bm25_all[i])[:CANDIDATES]
        if bm25_all[i] > 0
    }
    vector_ranking = sorted(similarity, key=lambda cid: -similarity[cid])
    bm25_ranking = sorted(bm25, key=lambda cid: -bm25[cid])
    fused = rrf_merge([vector_ranking, bm25_ranking])

    by_id = {c.chunk_id: c for c in index.chunks}
    hits = []
    for chunk_id, score in sorted(fused.items(), key=lambda item: -item[1]):
        chunk = by_id[chunk_id]
        sim = similarity.get(chunk_id)
        # The minimum score: weak matches mean that the data does not have the answer.
        # An exact record ID in the question always counts as a match.
        if (sim is None or sim < index.min_similarity) and chunk.record_id.lower() not in query_tokens:
            continue
        hits.append(
            SearchHit(
                chunk_id=chunk_id,
                source=chunk.source,
                record_id=chunk.record_id,
                score=score,
                vector_similarity=sim,
                bm25_score=bm25.get(chunk_id),
                vector_rank=_rank(vector_ranking, chunk_id),
                bm25_rank=_rank(bm25_ranking, chunk_id),
                context_text=chunk.context_text,
            )
        )
        if len(hits) == k:
            break
    return hits


def rrf_merge(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal rank fusion: each list adds 1 / (k + rank) for each ID in it."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def _vector_similarity(index, query, documents, record_ids, n) -> dict[str, float]:
    where = [{"document": {"$in": list(documents)}}]
    if record_ids is not None:
        where.append({"record_id": {"$in": list(record_ids)}})
    result = index.collection.query(
        query_embeddings=[index.embedder.query(query)],
        n_results=n,
        where=where[0] if len(where) == 1 else {"$and": where},
        include=["distances"],
    )
    # Cosine distance -> similarity.
    return {cid: 1.0 - dist for cid, dist in zip(result["ids"][0], result["distances"][0])}


def _rank(ranking: list[str], chunk_id: str) -> int | None:
    return ranking.index(chunk_id) + 1 if chunk_id in ranking else None
