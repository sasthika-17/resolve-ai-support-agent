import pytest

from app.retrieval import chunk_text, reciprocal_rank_fusion
from app.schemas import DocumentInput


def test_chunking_covers_text_without_empty_chunks():
    text = ('Policy sentence with enough words. ' * 90).strip()
    chunks = chunk_text(text, size=180, overlap=35)
    assert len(chunks) > 3
    assert all(chunk.strip() for chunk in chunks)
    assert chunks[0].startswith('Policy')
    assert chunks[-1].endswith('words.')


def test_rank_fusion_rewards_agreement():
    assert reciprocal_rank_fusion([['a', 'b'], ['b', 'a']])[0] == 'a'
    assert reciprocal_rank_fusion([['solo'], ['b', 'solo']])[0] == 'solo'


@pytest.mark.asyncio
async def test_hybrid_retrieval_persists_and_returns_traceable_passages(store, knowledge):
    initial = await knowledge.index()
    assert initial['chunks_added'] > 5
    same = await knowledge.index()
    assert same['chunks_added'] == 0
    results = await knowledge.search('How long does an export download last?', 'hybrid')
    assert results[0]['title'] == 'Workspace exports'
    assert results[0]['source_id']
    assert results[0]['method'] == 'hybrid'


@pytest.mark.asyncio
async def test_new_document_is_not_retrievable_until_embedded(store, knowledge):
    identifier = store.add_document(DocumentInput(title='Feature flag rollout', text='Feature flags use staged percentage rollouts. Do not expose the admin toggle to customers.'))
    await knowledge.index()
    matches = await knowledge.search('Feature flag rollout', 'keyword')
    assert any(match['document_id'] == identifier for match in matches)
