import httpx2
import openai
import pytest

from app.provider import public_error


@pytest.mark.parametrize('detail', [
    {'code': 'credit_balance_exhausted', 'type': 'insufficient_quota'},
    {'code': 'insufficient_quota', 'type': 'insufficient_quota'},
    {'error': {'code': 'project_spend_limit_exceeded', 'type': 'insufficient_quota'}},
])
def test_quota_errors_do_not_advise_retrying_a_rate_limit(detail):
    response = httpx2.Response(429, request=httpx2.Request('POST', 'https://api.openai.com/v1/embeddings'))
    result = public_error(openai.RateLimitError('Provider rejected request', response=response, body=detail))
    assert result.code == 'provider_quota'
    assert result.status == 503
    assert 'Wait briefly' not in result.message


def test_actual_rate_limit_advises_pacing():
    response = httpx2.Response(429, request=httpx2.Request('POST', 'https://api.openai.com/v1/embeddings'))
    result = public_error(openai.RateLimitError('Provider rejected request', response=response, body={'code': 'rate_limit_exceeded'}))
    assert result.code == 'provider_limit'
    assert 'Wait briefly' in result.message
