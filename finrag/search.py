from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from math import log1p
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import re

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from .extract import financial
from .store import LOCAL, ROOT

MODES = ("bm25", "vector", "hybrid", "rerank")
MODEL = ROOT / "data/models/bge"
REV = "75c43b069aac4d136ba6bc1122f995fedcfd2781"


def terms(text):
    out = []
    for word in re.findall(r"[\u3400-\u9fff]+|[a-z]+|\d+(?:\.\d+)?", text.lower()):
        if "\u3400" <= word[0] <= "\u9fff":
            out.extend(word[i:i+2] for i in range(max(1, len(word)-1)))
        else:
            out.append(word)
    return out


@dataclass(frozen=True)
class Chunk:
    doc: str
    page: int
    part: int
    title: str
    text: str

    @property
    def key(self):
        return f"{self.doc}/p{self.page}/c{self.part}"


def segments(layout, size=380):
    # Reconstruct wrapped Chinese prose; start a new unit at sections, rows or sentences.
    buffer = ""
    for line in layout.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\s{2,}", " | ", line)
        if buffer and (re.match(r"^\d+(?:\.\d+)*\s+\D", line) or "|" in line):
            yield buffer
            buffer = ""
        buffer += line
        if "|" in line or re.search(r"[。；：！？]$", buffer) or len(buffer) >= size:
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


def chunks(rows, strategy="structure", tables=True, size=380):
    result = []
    statement = {}
    for meta, page, layout in rows:
        if strategy == "fixed":
            flat = " ".join(layout.split())
            texts = [flat[i:i+size] for i in range(0, len(flat), size)]
        else:
            texts, buffer = [], ""
            units = list(segments(layout, size))
            vectors = encoder().encode(units) if strategy=="semantic" and units else None
            for index,seg in enumerate(units):
                topic_change = (vectors is not None and index > 0 and len(buffer)>=80
                                and float(vectors[index] @ vectors[index-1]) < 0.68)
                if buffer and (len(buffer) + len(seg) > size or topic_change):
                    texts.append(buffer)
                    buffer = ""
                for i in range(0, len(seg), size):
                    piece = seg[i:i+size]
                    if buffer and len(buffer) + len(piece) + 1 > size:
                        texts.append(buffer)
                        buffer = ""
                    buffer = (buffer + "\n" + piece).strip()
            if buffer:
                texts.append(buffer)
        if tables:
            seen = set()
            for rec in financial(meta, page, layout, statement=statement):
                if rec["evidence_type"] == "table" and len(rec["period"])==4 and rec["quote"] not in seen:
                    texts.append(f'{rec["unit"]} · {rec["header"]}\n{rec["quote"]}')
                    seen.add(rec["quote"])
        for i, text in enumerate(texts):
            result.append(Chunk(meta["id"], page, i+1, meta["title"], text))
    return result


class Encoder:
    def __init__(self):
        if not (MODEL / "model_quantized.onnx").is_file():
            raise ValueError("请先执行 python -m scripts.fetch_encoder")
        self.tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self.tokenizer.enable_truncation(max_length=512)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 3
        self.session = ort.InferenceSession(str(MODEL / "model_quantized.onnx"),
                                            options, providers=["CPUExecutionProvider"])

    def encode(self, texts):
        batches = []
        for start in range(0, len(texts), 6):
            tokens = self.tokenizer.encode_batch(texts[start:start+6])
            feed = {field: np.asarray([getattr(t, attr) for t in tokens], dtype=np.int64)
                    for field, attr in (("input_ids","ids"),("attention_mask","attention_mask"),
                                        ("token_type_ids","type_ids"))}
            vectors = self.session.run(None, feed)[0][:, 0, :]
            batches.append(vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12))
        return np.concatenate(batches)

    @lru_cache(maxsize=128)
    def query(self, text):
        return self.encode(["为这个句子生成表示以用于检索相关文章：" + text])[0]


@lru_cache(maxsize=1)
def encoder():
    return Encoder()


class Search:
    def __init__(self, items):
        self.items = items
        self.passages = [c.title + "\n" + c.text for c in items]
        self.tf = [Counter(terms(s)) for s in self.passages]
        self.length = [sum(c.values()) for c in self.tf]
        self.average = np.mean(self.length) if items else 1
        df = Counter(t for c in self.tf for t in c)
        self.idf = {t: log1p((len(items)-v+0.5)/(v+0.5)) for t,v in df.items()}
        self.matrix = None

    def prepare_dense(self):
        if self.matrix is not None or not self.items:
            return
        fingerprint = sha256((REV + "\0" + "\0".join(self.passages)).encode()).hexdigest()
        cache = LOCAL / "embeddings"
        cache.mkdir(parents=True, exist_ok=True)
        file = cache / (fingerprint + ".npy")
        if file.exists():
            self.matrix = np.load(file, allow_pickle=False)
        else:
            self.matrix = encoder().encode(self.passages)
            with NamedTemporaryFile(dir=cache, delete=False) as tmp:
                np.save(tmp, self.matrix)
            os.replace(tmp.name, file)

    def rank(self, query, mode="bm25", k=5, allowed=None):
        if mode not in MODES or k < 1 or not query.strip():
            raise ValueError("检查检索模式、K 和问题")
        eligible = [i for i,c in enumerate(self.items) if allowed is None or c.doc in allowed]
        if not eligible:
            return []
        keywords = set(terms(query))
        sparse, dense = [], []
        if mode != "vector":
            scores = {}
            for i in eligible:
                norm = 1.2 * (0.25 + 0.75 * self.length[i]/self.average)
                scores[i] = sum(self.idf[t] * self.tf[i][t]*2.2/(self.tf[i][t]+norm)
                                for t in keywords if t in self.tf[i])
            sparse = sorted((i for i in eligible if scores[i] > 0), key=scores.get, reverse=True)
        if mode != "bm25":
            self.prepare_dense()
            similarities = self.matrix @ encoder().query(query)
            dense = sorted(eligible, key=lambda i: -similarities[i])
        if mode == "bm25":
            ranking = sparse
        elif mode == "vector":
            ranking = dense
        else:
            fusion = Counter()
            for ranking in (sparse[:50], dense[:50]):
                for rank, i in enumerate(ranking, 1):
                    fusion[i] += 1/(60 + rank)
            ranking = sorted(fusion, key=fusion.get, reverse=True)
            if mode == "rerank":
                # Local-window IDF coverage promotes tightly co-occurring evidence.
                def score(i):
                    words = terms(self.items[i].text)
                    windows = [set(words[j:j+42]) for j in range(0, len(words), 21)]
                    denominator = sum(self.idf.get(t, 0) for t in keywords) or 1
                    concentration = max((sum(self.idf.get(t,0) for t in w & keywords)
                                         for w in windows), default=0)/denominator
                    return 30*fusion[i] + concentration
                ranking = sorted(ranking[:20], key=score, reverse=True) + ranking[20:]
        return [self.items[i] for i in ranking[:k]]

