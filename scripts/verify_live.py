"""Bounded live verification: one agent run, then reject its draft to avoid recording a resolution."""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import ResolutionEngine, WORKFLOW_VERSION
from app.config import ROOT, Settings
from app.provider import Provider
from app.retrieval import KnowledgeBase
from app.schemas import ReviewInput
from app.store import Store


async def main():
    settings = Settings.load()
    if not settings.api_key:
        raise SystemExit('OPENAI_API_KEY is not configured.')
    runtime = ROOT / '.runtime-live-verification' / uuid4().hex
    store = Store(runtime)
    store.seed(json.loads((ROOT / 'data' / 'seed.json').read_text(encoding='utf-8')))
    provider = Provider(settings)
    knowledge = KnowledgeBase(store, provider.embed, settings.embedding_model)
    engine = ResolutionEngine(store, knowledge, provider, settings)
    run_id = store.create_run('ticket_export', 'hybrid', 'Keep the reply concise.', WORKFLOW_VERSION)
    try:
        await engine.execute(run_id)
        run = store.run(run_id)
        print({'status': run['status'], 'error_code': run['error_code'], 'sources': len(run['sources']),
               'events': [event['kind'] for event in run['events']], 'usage': run['usage']})
        if run['status'] != 'waiting_review':
            raise SystemExit(run['error'] or 'The agent did not reach the review boundary.')
        ticket = store.ticket('ticket_export')
        if ticket['status'] != 'open' or ticket['resolution'] is not None:
            raise SystemExit('Unexpected write before approval.')
        # Verify that an unapproved draft causes no durable ticket-side effect.
        await engine.review(run_id, ReviewInput(approve=False, note='Verification only; draft not approved.'))
        print({'after_rejection': store.run(run_id)['status'], 'ticket_status': store.ticket('ticket_export')['status']})
    finally:
        await provider.client.close()


if __name__ == '__main__':
    asyncio.run(main())
