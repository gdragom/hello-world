"""Chunking, hybrid retrieval (BM25 + TF-IDF vectors), and citation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sbd_agent.models import RetrievedChunk


@dataclass
class Document:
    doc_id: str
    title: str
    text: str
    path: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """Character-window chunking with overlap — simple, predictable for eval."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(0, end - overlap)
    return [c for c in chunks if c]


class HybridRetriever:
    """In-process hybrid search: BM25 + TF-IDF cosine, with optional simple rerank."""

    def __init__(self, documents: list[Document], chunk_size: int = 500):
        self.chunks: list[Document] = []
        for doc in documents:
            for i, piece in enumerate(chunk_text(doc.text, chunk_size=chunk_size)):
                self.chunks.append(
                    Document(
                        doc_id=f"{doc.doc_id}#c{i}",
                        title=doc.title,
                        text=piece,
                        path=doc.path,
                    )
                )
        corpus = [c.text for c in self.chunks]
        tokenized = [_tokenize(t) for t in corpus]
        self._bm25 = BM25Okapi(tokenized)
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._tfidf = self._vectorizer.fit_transform(corpus)

    @classmethod
    def from_directory(cls, standards_dir: Path) -> "HybridRetriever":
        docs: list[Document] = []
        for path in sorted(standards_dir.glob("**/*")):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8")
            docs.append(
                Document(
                    doc_id=path.stem,
                    title=path.stem.replace("_", " ").title(),
                    text=text,
                    path=str(path),
                )
            )
        if not docs:
            raise FileNotFoundError(f"No standards found in {standards_dir}")
        return cls(docs)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        diversify_docs: bool = True,
        candidate_pool: int | None = None,
    ) -> list[RetrievedChunk]:
        bm25_scores = np.array(self._bm25.get_scores(_tokenize(query)), dtype=float)
        q_vec = self._vectorizer.transform([query])
        dense_scores = cosine_similarity(q_vec, self._tfidf).ravel()

        # Normalize and fuse
        def _norm(x: np.ndarray) -> np.ndarray:
            mx = x.max()
            if mx <= 0:
                return np.zeros_like(x)
            return x / mx

        fused = 0.5 * _norm(bm25_scores) + 0.5 * _norm(dense_scores)
        # Light rerank: boost chunks mentioning query keywords
        keywords = set(_tokenize(query))
        for i, chunk in enumerate(self.chunks):
            overlap = len(keywords & set(_tokenize(chunk.text)))
            fused[i] += 0.03 * overlap
            # Title/doc-id keyword hits help short standards docs surface
            parent = chunk.doc_id.split("#")[0]
            title_hits = len(keywords & set(_tokenize(chunk.title + " " + parent)))
            fused[i] += 0.05 * title_hits

        pool = candidate_pool or max(top_k * 4, 12)
        ranked = np.argsort(fused)[::-1][:pool]
        results: list[RetrievedChunk] = []
        seen_parents: set[str] = set()
        for idx in ranked:
            chunk = self.chunks[int(idx)]
            parent = chunk.doc_id.split("#")[0]
            if diversify_docs and parent in seen_parents:
                continue
            seen_parents.add(parent)
            results.append(
                RetrievedChunk(
                    doc_id=chunk.doc_id,
                    title=chunk.title,
                    text=chunk.text,
                    score=float(fused[int(idx)]),
                    citation=f"{chunk.title} ({parent})",
                )
            )
            if len(results) >= top_k:
                break
        return results
