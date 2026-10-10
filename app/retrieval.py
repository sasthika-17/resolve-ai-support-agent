"""Small-corpus hybrid RAG: persisted embeddings + FTS5, fused by rank."""
import asyncio
import hashlib
import json
import math
import re

from app.schemas import AppError


def chunk_text(text: str, size: int = 1100, overlap: int = 180) -> list[str]:
    if size < 100 or not 0 <= overlap < size:
        raise ValueError('Invalid chunk size or overlap')
    text = text.strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + size // 2, end)
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end == len(text):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start
    return chunks


def cosine(a, b):
    if len(a) != len(b) or not a:
        raise AppError('Embedding dimensions changed. Rebuild the knowledge index.', 409, 'embedding_shape')
    denominator = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denominator if denominator else 0.0


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60):
    scores = {}
    for ranking in rankings:
        for rank, identifier in enumerate(dict.fromkeys(ranking), 1):
            scores[identifier] = scores.get(identifier, 0.0) + 1 / (k + rank)
    return sorted(scores, key=lambda identifier: (-scores[identifier], identifier))


class KnowledgeBase:
    def __init__(self, store, embeddings, model):
        self.store, self.embeddings, self.model = store, embeddings, model
        self.lock = asyncio.Lock()

    async def index(self):
        async with self.lock:
            added = 0
            for doc in self.store.documents():
                if doc['indexed_model'] == self.model:
                    continue
                chunks = chunk_text(doc['text'])
                vectors = []
                for start in range(0, len(chunks), 32):
                    vectors.extend(await self.embeddings([doc['title'] + '\n' + p for p in chunks[start:start+32]]))
                if len(vectors) != len(chunks) or not vectors or any(not v or any(not math.isfinite(x) for x in v) for v in vectors):
                    raise AppError('Embedding service returned invalid vectors.', 502, 'embedding_invalid')
                if len({len(v) for v in vectors}) != 1:
                    raise AppError('Embedding dimensions are inconsistent.', 502, 'embedding_invalid')
                with self.store.connect() as db:
                    db.execute('DELETE FROM chunks_fts WHERE id IN (SELECT id FROM chunks WHERE document_id=?)', (doc['id'],))
                    db.execute('DELETE FROM chunks WHERE document_id=?', (doc['id'],))
                    for ordinal, (part, vector) in enumerate(zip(chunks, vectors)):
                        identifier = hashlib.sha256(f"{doc['id']}:{ordinal}:{part}".encode()).hexdigest()[:16]
                        db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)', (identifier, doc['id'], doc['title'], part, json.dumps(vector), self.model))
                        db.execute('INSERT INTO chunks_fts VALUES (?,?,?)', (identifier, doc['title'], part))
                    db.execute('UPDATE documents SET indexed_model=? WHERE id=?', (self.model, doc['id']))
                added += len(chunks)
            return {'chunks_added': added, 'documents': len(self.store.documents()), 'model': self.model}

    async def search(self, query: str, mode='hybrid', limit=4):
        if mode not in {'hybrid', 'semantic', 'keyword'}:
            raise AppError('Unknown retrieval mode.', 422)
        query = query.strip()
        if not 3 <= len(query) <= 1500:
            raise AppError('Search queries must have 3–1,500 characters.', 422)
        with self.store.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM chunks WHERE model=?', (self.model,))]
        if not rows:
            raise AppError('Index the knowledge base before searching.', 409, 'index_empty')
        by_id = {row['id']: row for row in rows}
        semantic, keyword = [], []
        similarities = {}
        if mode in {'hybrid', 'semantic'}:
            query_vector = (await self.embeddings([query]))[0]
            similarities = {r['id']: cosine(query_vector, json.loads(r['embedding'])) for r in rows}
            semantic = sorted(similarities, key=lambda key: (-similarities[key], key))[:12]
        if mode in {'hybrid', 'keyword'}:
            tokens = list(dict.fromkeys(re.findall(r'[\w]+', query.lower())))[:24]
            match = ' OR '.join('"' + token + '"' for token in tokens)
            if match:
                with self.store.connect() as db:
                    keyword = [r['id'] for r in db.execute('SELECT id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 12', (match,)) if r['id'] in by_id]
        ranked = reciprocal_rank_fusion([semantic, keyword]) if mode == 'hybrid' else semantic if mode == 'semantic' else keyword
        return [{'source_id': key, 'document_id': by_id[key]['document_id'], 'title': by_id[key]['title'],
                 'text': by_id[key]['text'], 'method': mode, 'rank': index + 1,
                 'similarity': round(similarities[key], 4) if key in similarities else None}
                for index, key in enumerate(ranked[:limit])]
