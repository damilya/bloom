"""Chunk → embed → store.   python -m app.rag.index

Chunking strategy (documented in ARCHITECTURE.md):
  • section-aware: never mix two sections in one chunk (keeps citations precise: "Results, p.7")
  • 450 tokens / 60 overlap (cl100k): the FlashRank cross-encoder truncates at 512 tokens, so larger
    chunks would be silently cut during reranking; 450 + header stays under the limit
  • contextual header prepended to the *embedded* text only: "<ref> — <title> | <section>" — lets
    short chunks ("Results showed no difference…") still match topical queries
  • page taken from the ⟦pN⟧ markers emitted by the PDF parser
"""
import json
import re
from pathlib import Path

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.llm import get_embeddings
from app.rag.papers import BY_PMCID
from app.rag.parse import parse_file

CHUNK_TOKENS = 450
CHUNK_OVERLAP = 60
MARK = re.compile(r"⟦p(\d+)⟧")


def index_dir() -> Path:
    d = get_settings().abs_path("data/index")
    d.mkdir(parents=True, exist_ok=True)
    return d


def chunk_paper(path: Path, chunk_tokens: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    pmcid = path.stem
    meta = BY_PMCID.get(pmcid, {"ref": pmcid, "title": pmcid, "year": None, "doi": None, "level": "unknown", "topics": []})
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=chunk_tokens, chunk_overlap=overlap,
        separators=["\n\n", ". ", "; ", ", ", " ", ""],
    )
    chunks = []
    for sec in parse_file(path):
        marked = sec.text
        pos = 0
        for piece in splitter.split_text(marked):
            start = marked.find(piece[:60], pos)
            start = start if start >= 0 else pos
            pos = start + 1
            before = MARK.findall(marked[: start + len(piece) // 2])
            page = int(before[-1]) if before else sec.page
            text = MARK.sub("", piece).strip()
            text = re.sub(r"\s+", " ", text).lstrip(".;, ")
            if len(text) < 120:
                continue
            chunks.append({
                "id": f"{pmcid}-{len(chunks):03d}", "pmcid": pmcid, "ref": meta["ref"], "title": meta["title"],
                "year": meta["year"], "doi": meta["doi"], "level": meta["level"], "topics": meta["topics"],
                "section": sec.title[:120], "page": page or None, "text": text,
                "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
            })
    return chunks


def embed_text(c: dict) -> str:
    return f"{c['ref']} — {c['title']} | {c['section']}\n{c['text']}"


def build_index(papers: Path | None = None) -> dict:
    papers = papers or get_settings().abs_path("data/papers")
    chunks: list[dict] = []
    for f in sorted(papers.iterdir()):
        if f.suffix.lower() in (".pdf", ".xml"):
            chunks += chunk_paper(f)
    emb = get_embeddings()
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), 96):
        vectors += emb.embed_documents([embed_text(c) for c in chunks[i:i + 96]])
    out = index_dir()
    with open(out / "chunks.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    np.save(out / "vectors.npy", np.array(vectors, dtype=np.float32))

    from app.rag.store import reset_store
    reset_store()  # (re)load into Qdrant
    return {"papers": len({c["pmcid"] for c in chunks}), "chunks": len(chunks)}


if __name__ == "__main__":
    print(build_index())
