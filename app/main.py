import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.agent import ResolutionEngine, WORKFLOW_VERSION
from app.config import ROOT, Settings
from app.provider import Provider, public_error
from app.retrieval import KnowledgeBase
from app.schemas import AppError, DocumentInput, ReviewInput, RunInput, SearchInput, TicketInput
from app.store import Store


def create_app(settings=None, store=None, knowledge=None, engine=None):
    settings = settings or Settings.load()
    store = store or Store(settings.data_dir)
    store.seed(json.loads((ROOT / 'data' / 'seed.json').read_text(encoding='utf-8')))
    provider = Provider(settings)
    knowledge = knowledge or KnowledgeBase(store, provider.embed, settings.embedding_model)
    engine = engine or ResolutionEngine(store, knowledge, provider, settings)
    jobs = set()

    @asynccontextmanager
    async def lifespan(_app):
        store.recover_interrupted()
        yield
        for task in list(jobs):
            task.cancel()
        if jobs:
            await asyncio.gather(*list(jobs), return_exceptions=True)
        if provider.client:
            await provider.client.close()

    def application_header(x_resolve_request: str | None = Header(default=None,
            description='Enter 1 for local write requests. This application header is not user authentication.')):
        # Middleware enforces the value for mutations; this exposes it in Swagger's request form.
        return x_resolve_request

    app = FastAPI(title='Resolve — AI Support Resolution Agent', version='1.0.0', lifespan=lifespan,
                  dependencies=[Depends(application_header)])
    app.state.store, app.state.knowledge, app.state.engine = store, knowledge, engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_request_boundary(request: Request, call_next):
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            if request.headers.get('x-resolve-request') != '1':
                return JSONResponse({'error': {'code': 'request_header', 'message': 'Missing application request header.'}}, status_code=403)
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'error': {'code': 'origin', 'message': 'Cross-origin writes are not allowed.'}}, status_code=403)
            body = await request.body()
            if len(body) > 1_000_000:
                return JSONResponse({'error': {'code': 'body_limit', 'message': 'Request exceeds the 1 MB limit.'}}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path in {'/docs', '/docs/oauth2-redirect', '/redoc'}:
            # FastAPI's documentation renderer uses CDN assets and inline bootstrap code.
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'"
        else:
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        # A local development workbench must pick up frontend edits on reload too.
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(AppError)
    async def application_error(_request, exc):
        return JSONResponse({'error': {'code': exc.code, 'message': exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return JSONResponse({'error': {'code': 'validation', 'message': 'Check the required fields and length limits.'}}, status_code=422)

    @app.get('/health')
    @app.get('/api/health')
    def health():
        documents = store.documents()
        return {'status': 'ok', 'configured': bool(settings.api_key), 'model': settings.model,
                'embedding_model': settings.embedding_model, 'documents': len(documents),
                'indexed': sum(doc['indexed_model'] == settings.embedding_model for doc in documents),
                'chunks': sum(doc['chunks'] for doc in documents), 'workflow_version': WORKFLOW_VERSION}

    @app.get('/api/tickets')
    def list_tickets():
        return store.tickets()

    @app.get('/api/customers')
    def list_customers():
        return store.customers()

    @app.post('/api/tickets', status_code=201)
    def create_ticket(body: TicketInput):
        return store.add_ticket(body)

    @app.get('/api/tickets/{ticket_id}')
    def get_ticket(ticket_id: str):
        return store.ticket(ticket_id)

    @app.post('/api/tickets/{ticket_id}/runs', status_code=202)
    async def start_run(ticket_id: str, body: RunInput):
        if not engine.model_override:
            provider.require_client()
        if len(jobs) >= 8:
            raise AppError('Eight runs are already queued. Wait for one to finish.', 429, 'queue_full')
        identifier = store.create_run(ticket_id, body.retrieval_mode, body.feedback, WORKFLOW_VERSION)
        task = asyncio.create_task(engine.execute(identifier))
        jobs.add(task)
        task.add_done_callback(jobs.discard)
        return store.run(identifier)

    @app.get('/api/runs/{run_id}')
    def get_run(run_id: str):
        return store.run(run_id)

    @app.post('/api/runs/{run_id}/review')
    async def review(run_id: str, body: ReviewInput):
        return await engine.review(run_id, body)

    @app.get('/api/runs/{run_id}/export')
    def export_run(run_id: str):
        run = store.run(run_id)
        return JSONResponse(run, headers={'Content-Disposition': f'attachment; filename="resolve-{run["id"]}.json"'})

    @app.get('/api/documents')
    def list_documents():
        return store.documents()

    @app.post('/api/documents', status_code=201)
    def add_document(body: DocumentInput):
        return {'id': store.add_document(body)}

    @app.post('/api/documents/upload', status_code=201)
    async def upload_document(file: UploadFile):
        if Path(file.filename or '').suffix.lower() not in {'.md', '.txt'}:
            raise AppError('Knowledge uploads support Markdown and plain text.', 415, 'file_type')
        content = await file.read(120_001)
        await file.close()
        if len(content) > 120_000:
            raise AppError('Use a text document below 120 KB and 30,000 characters.', 413, 'file_size')
        try:
            doc = DocumentInput(title=Path(file.filename).stem, text=content.decode('utf-8-sig'))
        except (UnicodeDecodeError, ValidationError):
            raise AppError('Use UTF-8 text with a title of 3–120 characters and content of 30–30,000 characters.', 400, 'file_invalid') from None
        return {'id': store.add_document(doc)}

    @app.post('/api/knowledge/index')
    async def index_knowledge():
        try:
            return await asyncio.wait_for(knowledge.index(), timeout=180)
        except Exception as exc:
            raise public_error(exc) from None

    @app.post('/api/knowledge/search')
    async def search_knowledge(body: SearchInput):
        try:
            return {'sources': await knowledge.search(body.query, body.mode)}
        except Exception as exc:
            raise public_error(exc) from None

    @app.get('/api/evaluations')
    def evaluations():
        result_path = settings.data_dir / 'latest-evaluation.json'
        if not result_path.exists():
            return {'available': False}
        return {'available': True, 'report': json.loads(result_path.read_text(encoding='utf-8'))}

    @app.get('/')
    def frontend():
        return FileResponse(ROOT / 'frontend' / 'index.html')

    app.mount('/static', StaticFiles(directory=ROOT / 'frontend'), name='static')
    return app


app = create_app()
