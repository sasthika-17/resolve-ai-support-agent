# Presenting Resolve on your resume

This project demonstrates agent tools, hybrid RAG, structured outputs, citation validation, durable human review, evaluation, and a usable FastAPI application. A project can support your applications; it cannot guarantee interview calls.

## Resume bullets

Use these only when you understand the implementation and can demonstrate the behavior:

- Built a GenAI support-resolution application using Python, FastAPI, OpenAI Agents SDK, and a browser workbench with cited drafts and human approval before durable writes.
- Implemented hybrid RAG with OpenAI embeddings, exact cosine vector search, SQLite FTS5, and reciprocal-rank fusion over product policies; validated source IDs and exact quotations before review.
- Persisted paused agent state and enforced exact-draft approval with transactional SQLite writes, duplicate-review protection, and deterministic tests covering retrieval, provider errors, and approval/rejection workflows.

When you have a successful live report, add the actual number of graded cases, named checks, model, and date. Do not translate four synthetic cases into a general accuracy percentage or claim customers, deployment scale, time savings, or business impact you did not measure.

## Repository presentation

Keep `README.md`, `app/`, `frontend/`, `data/`, `tests/`, `evals/`, `docs/`, `.github/`, `.vscode/`, `requirements.txt`, and `.env.example`. The lock file records the verified Windows environment. CI uses `requirements.txt` because the Windows lock includes platform-specific packages.

Do not publish `.env.local`, `.venv`, `.runtime*`, test caches, or real customer content. `.gitignore` excludes these. The supplied data is synthetic.

The public repository is [sasthika-17/resolve-ai-support-agent](https://github.com/sasthika-17/resolve-ai-support-agent). For future changes, inspect `git status --short`, stage the intended source files, review the staged filenames, then commit and push. Keep credential and runtime exclusions in place.

## Demonstration order

1. Show the policy that answers the export ticket.
2. Run the agent and explain its customer lookup and retrieval tools.
3. Open an exact source quotation and show that the ticket remains open while waiting for review.
4. Reject a draft, regenerate it, then approve the reviewed version.
5. Show a billing or unsupported-compliance escalation and explain what the agent is not authorized to do.
6. Run the deterministic tests and show the live evaluation report, if API credits permit.

Live generation is currently blocked by `credit_balance_exhausted`. Explain that honestly; a mocked workflow test is not a live model demonstration. See `VERIFICATION.md` for the evidence and `INTERVIEW.md` for preparation questions.
