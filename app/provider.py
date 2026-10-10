import openai

from app.schemas import AppError


def public_error(error):
    if isinstance(error, AppError):
        return error
    if isinstance(error, openai.AuthenticationError):
        return AppError('OpenAI rejected the configured credential. Check secure key setup.', 503, 'provider_auth')
    if isinstance(error, openai.RateLimitError):
        body = error.body if isinstance(error.body, dict) else {}
        detail = body.get('error', body)
        detail = detail if isinstance(detail, dict) else {}
        code = getattr(error, 'code', None) or detail.get('code')
        kind = getattr(error, 'type', None) or detail.get('type')
        if code == 'credit_balance_exhausted':
            return AppError('OpenAI API credits are exhausted. Add credits in API billing before trying again.', 503, 'provider_quota')
        if code in {'organization_usage_limit_exceeded', 'organization_spend_limit_exceeded', 'project_spend_limit_exceeded'}:
            return AppError('An OpenAI usage or spend limit was reached. Review your organization and project limits before trying again.', 503, 'provider_quota')
        if code == 'insufficient_quota' or kind == 'insufficient_quota':
            return AppError('This OpenAI project has no available API quota. Check its API billing and usage limits, then try again.', 503, 'provider_quota')
        if code != 'rate_limit_exceeded':
            return AppError('OpenAI refused this request with HTTP 429. Check API billing and rate limits for the reported cause.', 503, 'provider_limit')
        return AppError('OpenAI is rate limiting requests. Wait briefly, then try again.', 503, 'provider_limit')
    if isinstance(error, (openai.APIConnectionError, openai.APITimeoutError, TimeoutError)):
        return AppError('The model service could not be reached in time. Your ticket is saved; try again later.', 503, 'provider_connection')
    if isinstance(error, openai.APIError):
        return AppError('OpenAI could not complete the request. Check model access and project configuration.', 502, 'provider_error')
    return AppError('The agent could not produce a valid reviewable draft. See the run trace and try a clearer ticket.', 502, 'agent_failed')


class Provider:
    def __init__(self, settings):
        self.settings = settings
        self.client = openai.AsyncOpenAI(api_key=settings.api_key, timeout=45, max_retries=0) if settings.api_key else None

    def require_client(self):
        if self.client is None:
            raise AppError('An OpenAI API key is required. Complete secure setup for this project.', 503, 'key_missing')
        return self.client

    async def embed(self, texts):
        try:
            result = await self.require_client().embeddings.create(model=self.settings.embedding_model, input=texts)
            return [item.embedding for item in sorted(result.data, key=lambda item: item.index)]
        except Exception as exc:
            raise public_error(exc) from None
