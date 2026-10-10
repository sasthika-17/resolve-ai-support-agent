"""Run Resolve locally at http://127.0.0.1:8010."""
import uvicorn


if __name__ == '__main__':
    uvicorn.run('app.main:app', host='127.0.0.1', port=8010, reload=False, log_level='info')
