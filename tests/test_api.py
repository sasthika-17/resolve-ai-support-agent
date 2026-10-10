from fastapi.testclient import TestClient
from agents.testing import ScriptedModel, function_call
import time

from app.agent import ResolutionEngine
from app.main import create_app
from app.provider import Provider
from app.retrieval import KnowledgeBase
from app.store import Store


async def fake_embeddings(texts):
    return [[float(len(text) % 7), 1.0, 2.0, 3.0] for text in texts]


def make_client(settings):
    store = Store(settings.data_dir)
    app = create_app(settings=settings, store=store,
                     knowledge=KnowledgeBase(store, fake_embeddings, settings.embedding_model))
    return TestClient(app)


def test_health_and_seeded_tickets_are_available(settings):
    client = make_client(settings)
    health = client.get('/api/health')
    assert health.status_code == 200
    assert health.json()['configured'] is False
    assert len(client.get('/api/tickets').json()) == 4


def test_write_header_and_validation_are_enforced(settings):
    client = make_client(settings)
    denied = client.post('/api/tickets', json={'subject': 'Need support', 'body': 'This should be rejected because the header is absent.'})
    assert denied.status_code == 403
    invalid = client.post('/api/tickets', headers={'X-Resolve-Request': '1'}, json={'subject': 'no', 'body': 'short'})
    assert invalid.status_code == 422


def test_document_lifecycle_and_search(settings):
    client = make_client(settings)
    headers = {'X-Resolve-Request': '1'}
    created = client.post('/api/documents', headers=headers, json={'title': 'Keyboard shortcuts', 'text': 'Keyboard shortcuts use Control and K to open the command palette in OrbitDesk.'})
    assert created.status_code == 201
    indexed = client.post('/api/knowledge/index', headers=headers)
    assert indexed.status_code == 200
    found = client.post('/api/knowledge/search', headers=headers, json={'query': 'What opens the command palette?', 'mode': 'hybrid'})
    assert found.status_code == 200
    assert found.json()['sources']


def test_api_run_review_export_and_replay_use_server_state(store, knowledge, settings):
    engine = ResolutionEngine(store, knowledge, Provider(settings), settings, model_override=ScriptedModel([]))
    app = create_app(settings=settings, store=store, knowledge=knowledge, engine=engine)
    headers = {'X-Resolve-Request': '1'}
    with TestClient(app) as client:
        assert client.post('/api/knowledge/index', headers=headers).status_code == 200
        result = client.post('/api/knowledge/search', headers=headers, json={'query': 'export download link', 'mode': 'hybrid'})
        source = next(source for source in result.json()['sources'] if source['title'] == 'Workspace exports')
        draft = {'reply': 'You can start your workspace export in Settings > Workspace > Export. The download link expires after 24 hours.',
                 'summary': 'A documented export request for an admin.', 'category': 'access', 'disposition': 'resolved',
                 'escalation_reason': None, 'citations': [{'source_id': source['source_id'], 'quote': 'The download link expires after 24 hours.'}]}
        engine.model_override = ScriptedModel([
            [function_call('lookup_customer', {}, call_id='customer')],
            [function_call('search_knowledge', {'query': 'export download link'}, call_id='search')],
            [function_call('record_resolution', {'resolution': draft}, call_id='write')],
        ])
        response = client.post('/api/tickets/ticket_export/runs', headers=headers, json={})
        assert response.status_code == 202
        run_id = response.json()['id']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            run = client.get(f'/api/runs/{run_id}').json()
            if run['status'] != 'running':
                break
            time.sleep(0.01)
        assert run['status'] == 'waiting_review'
        assert 'snapshot' not in run
        assert client.get('/api/tickets/ticket_export').json()['resolution'] is None
        # The client supplies only a decision, never a replacement resolution or SDK snapshot.
        rejected_payload = client.post(f'/api/runs/{run_id}/review', headers=headers, json={'approve': True, 'draft': draft})
        assert rejected_payload.status_code == 422
        approved = client.post(f'/api/runs/{run_id}/review', headers=headers, json={'approve': True})
        assert approved.status_code == 200
        assert approved.json()['status'] == 'approved'
        assert client.get('/api/tickets/ticket_export').json()['resolution'] == draft
        assert client.post(f'/api/runs/{run_id}/review', headers=headers, json={'approve': True}).status_code == 409
        exported = client.get(f'/api/runs/{run_id}/export')
        assert exported.status_code == 200
        assert 'attachment;' in exported.headers['content-disposition']
        assert 'snapshot' not in exported.json()
        engine.model_override.assert_complete()
