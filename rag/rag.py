#!/usr/bin/env python3
"""
Retrieval for the Pi assistant: answer from Moonlighter's own documents
(~/rag/docs/) instead of from the model's memory.

Everything runs on the Pi. The LLM stays on the AI HAT+ 2 (hailo-ollama); the
only CPU work is a 65 MB sentence-embedding model (BAAI/bge-small-en-v1.5 via
fastembed/onnxruntime): ~15 ms per question, ~1 min to index a 160-page manual.

  ~/voice/.venv/bin/python ~/rag/rag.py build              # (re)index ~/rag/docs -> ~/rag/index
  ~/voice/.venv/bin/python ~/rag/rag.py search "question"  # show the chunks that would be used
  ~/voice/.venv/bin/python ~/rag/rag.py ask "question"     # retrieval + hailo-ollama answer, with sources

Documents: PDF (text extracted with pdftotext; image-only pages are OCR'd with
tesseract if it is installed), .txt and .md. Chunks are ~180 words with overlap
and remember their file and page. hailo-ollama models have a 2048-token
context, so the context handed to the LLM is capped (MAX_CONTEXT_WORDS).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

DOCS_DIR = "/home/admin/rag/docs"
INDEX_DIR = "/home/admin/rag/index"
MODEL_DIR = "/home/admin/rag/models"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
CHUNK_WORDS = 180
OVERLAP_WORDS = 40
TOP_K = 3
MAX_CONTEXT_WORDS = 420          # ~550 tokens; leaves room for history + answer in 2048
MIN_SCORE = 0.60                 # cosine; bge-small scores unrelated text ~0.5-0.6
OCR_MIN_WORDS_PER_PAGE = 20      # below this a page is treated as an image and OCR'd
KEYWORD_BOOST = 0.04             # added per unit of question-term coverage / density (see Retriever.search)
STOPWORDS = set("the a an and or of to in on for with is are was were be been what which who how do does did "
                "can could should would will i you it its this that these those my your from by at as about".split())

RAG_INSTRUCTIONS = (
    "Use the document excerpts below to answer. If they do not contain the answer, "
    "say you do not know; do not guess. Mention the document name when it helps."
)

_model = None


def embedder():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL_NAME, cache_dir=MODEL_DIR)
    return _model


# ---------------------------------------------------------------- extraction
def pdf_pages(path):
    """Text per page. Uses pdftotext; OCRs pages that come back (nearly) empty."""
    out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    empty = [i for i, p in enumerate(pages) if len(p.split()) < OCR_MIN_WORDS_PER_PAGE]
    if empty:
        if shutil.which("tesseract"):
            print(f"   OCR {len(empty)}/{len(pages)} image pages ...", flush=True)
            for i in empty:
                pages[i] = ocr_page(path, i + 1) or pages[i]
        else:
            print(f"   {len(empty)}/{len(pages)} pages have no text and tesseract is not installed "
                  f"(sudo apt install tesseract-ocr); skipping them", flush=True)
    return pages


def ocr_page(path, pageno):
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "p")
        subprocess.run(["pdftoppm", "-r", "200", "-f", str(pageno), "-l", str(pageno), "-png", path, base],
                       check=True, capture_output=True)
        pngs = sorted(f for f in os.listdir(d) if f.endswith(".png"))
        if not pngs:
            return ""
        r = subprocess.run(["tesseract", os.path.join(d, pngs[0]), "-", "--psm", "3", "-l", "eng"],
                           capture_output=True, text=True)
        return r.stdout


def doc_pages(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return pdf_pages(path)
    if ext in (".txt", ".md"):
        with open(path, encoding="utf-8", errors="replace") as f:
            return [f.read()]
    return []


def clean(text):
    text = text.replace("­", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # drop table-of-contents dot leaders and page-number-only lines
    text = re.sub(r"\.{4,}\s*\d*", " ", text)
    return text.strip()


def chunk_pages(doc, pages):
    chunks = []
    for pageno, page in enumerate(pages, 1):
        words = clean(page).split()
        if len(words) < 8:
            continue
        start = 0
        while start < len(words):
            piece = words[start:start + CHUNK_WORDS]
            chunks.append({"doc": doc, "page": pageno, "text": " ".join(piece)})
            if start + CHUNK_WORDS >= len(words):
                break
            start += CHUNK_WORDS - OVERLAP_WORDS
    return chunks


# ---------------------------------------------------------------- index
def build(docs_dir=DOCS_DIR, index_dir=INDEX_DIR):
    files = sorted(f for f in os.listdir(docs_dir) if f.lower().endswith((".pdf", ".txt", ".md")))
    if not files:
        sys.exit(f"no documents in {docs_dir}")
    chunks, manifest = [], {}
    for name in files:
        path = os.path.join(docs_dir, name)
        t0 = time.time()
        print(f"{name}", flush=True)
        pages = doc_pages(path)
        c = chunk_pages(name, pages)
        words = sum(len(x["text"].split()) for x in c)
        print(f"   {len(pages)} pages, {len(c)} chunks, {words} words, {time.time() - t0:.1f} s", flush=True)
        chunks += c
        manifest[name] = {"pages": len(pages), "chunks": len(c), "words": words,
                          "size": os.path.getsize(path), "mtime": os.path.getmtime(path)}
    print(f"embedding {len(chunks)} chunks with {MODEL_NAME} ...", flush=True)
    t0 = time.time()
    vecs = np.array(list(embedder().embed([c["text"] for c in chunks], batch_size=32)), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    print(f"   {time.time() - t0:.1f} s", flush=True)
    os.makedirs(index_dir, exist_ok=True)
    np.save(os.path.join(index_dir, "vectors.npy"), vecs)
    with open(os.path.join(index_dir, "chunks.json"), "w") as f:
        json.dump(chunks, f)
    with open(os.path.join(index_dir, "manifest.json"), "w") as f:
        json.dump({"model": MODEL_NAME, "built": time.time(), "docs": manifest}, f, indent=1)
    print(f"index written to {index_dir}: {len(chunks)} chunks from {len(files)} documents")


class Retriever:
    def __init__(self, index_dir=INDEX_DIR):
        self.index_dir = index_dir
        self.vecs = self.chunks = None

    @property
    def available(self):
        return os.path.exists(os.path.join(self.index_dir, "vectors.npy"))

    def load(self):
        if self.vecs is None:
            self.vecs = np.load(os.path.join(self.index_dir, "vectors.npy"))
            with open(os.path.join(self.index_dir, "chunks.json")) as f:
                self.chunks = json.load(f)
        return self

    def search(self, question, k=TOP_K, min_score=MIN_SCORE):
        """Cosine similarity plus a small boost for chunks that repeat the question's own
        terms (helps short acronym questions like "what is the AMS": the embedding alone
        ranked a passage that merely mentions AMS above the one that defines it)."""
        self.load()
        q = np.array(list(embedder().query_embed(question))[0], dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        scores = self.vecs @ q
        terms = [t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) >= 3 and t not in STOPWORDS]
        if terms:
            top = np.argsort(-scores)[:k * 10]
            for i in top:
                text = self.chunks[i]["text"].lower()
                counts = [len(re.findall(r"\b" + re.escape(t) + r"\b", text)) for t in terms]
                present = sum(1 for c in counts if c) / len(terms)
                dense = sum(1 for c in counts if c >= 3) / len(terms)
                scores[i] += KEYWORD_BOOST * (present + dense)
        order = np.argsort(-scores)[:k]
        return [dict(self.chunks[i], score=float(scores[i])) for i in order if scores[i] >= min_score]

    def context(self, question, k=TOP_K, max_words=MAX_CONTEXT_WORDS):
        """(context_text, sources). Empty context if nothing scores high enough."""
        hits = self.search(question, k)
        parts, sources, used = [], [], 0
        for h in hits:
            words = h["text"].split()
            room = max_words - used
            if room < 40:
                break
            text = " ".join(words[:room])
            used += min(len(words), room)
            label = f"{short(h['doc'])}, page {h['page']}"
            parts.append(f"[{label}] {text}")
            sources.append(label)
        return " ".join(parts), sources  # one line: hailo-ollama 5.3.0 rejects newlines in messages


def short(doc):
    return re.sub(r"\.(pdf|txt|md)$", "", doc, flags=re.I)


def build_messages(system_prompt, history, question, context):
    """Messages for /api/chat with the excerpts in the user turn (history stays clean)."""
    if context:
        system = system_prompt + " " + RAG_INSTRUCTIONS
        user = f"Document excerpts: {context} Question: {question}"
    else:
        system, user = system_prompt, question
    return [{"role": "system", "content": system}] + list(history) + [{"role": "user", "content": user}]


# ---------------------------------------------------------------- CLI
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("build", "search", "ask"):
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "build":
        return build()
    question = " ".join(sys.argv[2:])
    if not question:
        sys.exit("give a question")
    r = Retriever()
    if not r.available:
        sys.exit(f"no index in {INDEX_DIR}; run: rag.py build")
    t0 = time.time()
    hits = r.search(question, k=5, min_score=0.0)
    print(f"retrieval {1000 * (time.time() - t0):.0f} ms")
    for h in hits:
        flag = " " if h["score"] >= MIN_SCORE else "x"
        print(f"{flag} {h['score']:.3f}  {short(h['doc'])} p.{h['page']}: {h['text'][:140]}...")
    if cmd == "search":
        return
    import requests
    context, sources = r.context(question)
    sys.path.insert(0, "/home/admin/voice")
    from assistant import DEFAULT_MODEL, LLM_URL, SYSTEM_PROMPT
    messages = build_messages(SYSTEM_PROMPT, [], question, context)
    print(f"\ncontext words: {len(context.split())}  sources: {sources or 'none'}\n")
    t0 = time.time()
    from assistant import hailo_safe
    rsp = requests.post(LLM_URL, json={"model": DEFAULT_MODEL, "messages": hailo_safe(messages), "stream": False}, timeout=300)
    rsp.raise_for_status()
    print("ANSWER:", rsp.json()["message"]["content"].strip())
    print(f"({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
