"""Run a small, paid, opt-in live behavior evaluation and store only safe aggregate results."""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent import ResolutionEngine, WORKFLOW_VERSION
from app.config import Settings
from app.provider import Provider
from app.retrieval import KnowledgeBase
from app.schemas import ReviewInput
from app.store import Store
from evals.grading import grade_case


async def main():
    if '--run' not in sys.argv:
        raise SystemExit('This makes paid OpenAI requests. Re-run with: python evals/run_live.py --run')
    settings = Settings.load()
    if not settings.api_key:
        raise SystemExit('OPENAI_API_KEY is not configured.')
    cases = [json.loads(line) for line in (ROOT / 'evals' / 'cases.jsonl').read_text(encoding='utf-8').splitlines() if line]
    runtime = ROOT / '.runtime-evals' / uuid4().hex
    store = Store(runtime)
    store.seed(json.loads((ROOT / 'data' / 'seed.json').read_text(encoding='utf-8')))
    provider = Provider(settings)
    knowledge = KnowledgeBase(store, provider.embed, settings.embedding_model)
    engine = ResolutionEngine(store, knowledge, provider, settings)
    results = []
    blocked = None
    try:
        for case in cases:
            if blocked:
                results.append({'name': case['name'], 'status': 'skipped', 'passed': False, 'checks': {}, 'error': blocked})
                continue
            run_id = store.create_run(case['ticket_id'], 'hybrid', '', WORKFLOW_VERSION)
            await engine.execute(run_id)
            run = store.run(run_id)
            result = grade_case(case, run, store.ticket(case['ticket_id']))
            if run['status'] == 'waiting_review':
                await engine.review(run_id, ReviewInput(approve=False, note='Evaluation run; no resolution recorded.'))
            results.append({'name': case['name'], **result})
            if (run.get('error_code') or '').startswith('provider_'):
                blocked = run['error']
    finally:
        await provider.client.close()
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'model': settings.model,
              'embedding_model': settings.embedding_model, 'cases': results, 'passed': sum(item['passed'] for item in results),
              'graded': sum(item['status'] in {'pass', 'fail'} for item in results),
              'errors': sum(item['status'] == 'error' for item in results),
              'skipped': sum(item['status'] == 'skipped' for item in results),
              'note': 'Synthetic, small evaluation set. Provider errors and skipped cases are not model-quality measurements. Drafts are rejected without recording a resolution.'}
    output = settings.data_dir / 'latest-evaluation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if report['passed'] != len(cases):
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
