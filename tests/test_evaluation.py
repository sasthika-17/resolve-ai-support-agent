from evals.grading import grade_case


def sample():
    case = {'expected_disposition': 'resolved', 'required_source_title': 'Workspace exports',
            'required_tools': ['customer_lookup', 'search']}
    run = {'status': 'waiting_review', 'events': [{'kind': 'search'}, {'kind': 'customer_lookup'}],
           'sources': [{'source_id': 's1', 'title': 'Workspace exports', 'text': 'The download link expires after 24 hours.'},
                       {'source_id': 's2', 'title': 'Another policy', 'text': 'Use the customer support portal for help.'}],
           'draft': {'reply': 'You can download your export with the link supplied by the workspace.',
                     'summary': 'Documented workspace export instructions.', 'category': 'access',
                     'disposition': 'resolved', 'escalation_reason': None,
                     'citations': [{'source_id': 's1', 'quote': 'The download link expires after 24 hours.'}]}}
    ticket = {'status': 'open', 'resolution': None}
    return case, run, ticket


def test_evaluation_requires_citing_the_expected_source():
    case, run, ticket = sample()
    assert grade_case(case, run, ticket)['passed']
    run['draft']['citations'] = [{'source_id': 's2', 'quote': 'Use the customer support portal for help.'}]
    result = grade_case(case, run, ticket)
    assert not result['passed']
    assert not result['checks']['required_source_cited']
    assert result['checks']['valid_quotes']


def test_provider_failure_is_an_error_not_a_quality_failure():
    result = grade_case({}, {'status': 'failed', 'error': 'API credits exhausted.'}, {})
    assert result['status'] == 'error'
    assert result['checks'] == {}
