import json
from pathlib import Path

import pytest

from app.config import Settings
from app.retrieval import KnowledgeBase
from app.store import Store


async def fake_embeddings(texts):
    """Stable, deliberately tiny test vectors; production uses OpenAI embeddings."""
    vectors = []
    for text in texts:
        text = text.lower()
        vectors.append([float(sum(text.count(term) for term in terms)) for terms in (
            ('export', 'download', 'csv'), ('refund', 'charge', 'invoice'),
            ('saml', 'sign', 'certificate'), ('privacy', 'hipaa', 'compliance'),
        )])
    return vectors


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / 'runtime')
    data = json.loads((Path(__file__).parents[1] / 'data' / 'seed.json').read_text(encoding='utf-8'))
    result.seed(data)
    return result


@pytest.fixture
def knowledge(store):
    return KnowledgeBase(store, fake_embeddings, 'test-embedding')


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / 'runtime', api_key='', model='gpt-4.1-mini', embedding_model='test-embedding', timeout=10)
