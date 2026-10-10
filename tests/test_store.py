import pytest

from app.schemas import AppError, TicketInput


def test_ticket_creation_requires_known_customer(store):
    with pytest.raises(AppError) as error:
        store.add_ticket(TicketInput(subject='Where is export?', body='I need help finding my export today.', customer_id='missing'))
    assert error.value.code == 'customer_missing'


def test_only_one_active_run_per_ticket(store):
    run_id = store.create_run('ticket_export', 'hybrid', '', 'test')
    assert store.run(run_id)['status'] == 'running'
    with pytest.raises(AppError) as error:
        store.create_run('ticket_export', 'hybrid', '', 'test')
    assert error.value.code == 'run_active'


def test_approved_write_is_exact_draft_and_closes_ticket(store):
    run_id = store.create_run('ticket_export', 'hybrid', '', 'test')
    draft = {'reply': 'Use Settings > Workspace > Export and choose CSV or JSON.', 'summary': 'A documented admin export request.',
             'category': 'access', 'disposition': 'resolved', 'escalation_reason': None,
             'citations': [{'source_id': 'source', 'quote': 'Use Settings > Workspace > Export.'}]}
    store.save_sources(run_id, [{'source_id': 'source', 'text': 'Use Settings > Workspace > Export.', 'title': 'Policy', 'method': 'test'}])
    store.waiting(run_id, 'state', draft, {}, 5)
    store.claim_review(run_id, 'Looks good')
    store.commit_resolution(run_id, draft)
    assert store.run(run_id)['status'] == 'approved'
    assert store.ticket('ticket_export')['status'] == 'resolved'


def test_replay_or_changed_approval_does_not_write(store):
    run_id = store.create_run('ticket_export', 'hybrid', '', 'test')
    draft = {'reply': 'A cited response that is long enough for the model schema.', 'summary': 'A draft for review.', 'category': 'access',
             'disposition': 'resolved', 'escalation_reason': None, 'citations': []}
    store.waiting(run_id, 'state', draft, {}, 5)
    store.claim_review(run_id, '')
    changed = {**draft, 'reply': 'A changed answer that must not be committed by replay.'}
    with pytest.raises(AppError) as error:
        store.commit_resolution(run_id, changed)
    assert error.value.code == 'approval_mismatch'
    assert store.ticket('ticket_export')['status'] == 'open'
