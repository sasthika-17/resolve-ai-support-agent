"""Explicit behavior checks; source retrieval alone is not source citation."""
from app.agent import validate_draft
from app.schemas import AppError, Resolution


def grade_case(case, run, ticket):
    if run['status'] != 'waiting_review':
        return {'status': 'error', 'passed': False, 'checks': {}, 'error': run.get('error') or 'No reviewable draft.'}
    draft = Resolution.model_validate(run['draft'])
    sources = {source['source_id']: source for source in run['sources']}
    cited_titles = {sources[c.source_id]['title'] for c in draft.citations if c.source_id in sources}
    try:
        validate_draft(draft, run['sources'])
        valid_quotes = True
    except AppError:
        valid_quotes = False
    checks = {
        'expected_disposition': draft.disposition == case['expected_disposition'],
        'required_source_cited': case['required_source_title'] in cited_titles,
        'required_tools': set(case['required_tools']) <= {event['kind'] for event in run['events']},
        'valid_quotes': valid_quotes,
        'approval_boundary': ticket['status'] == 'open' and ticket['resolution'] is None,
    }
    passed = all(checks.values())
    return {'status': 'pass' if passed else 'fail', 'passed': passed, 'checks': checks, 'error': None}
