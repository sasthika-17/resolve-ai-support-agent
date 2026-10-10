# Verification record — 9 October 2026

## Passed locally

- `pytest -q`: **24 passed** in 6.11 seconds with isolated temporary test storage.
- `pip check`: no broken requirements.
- FastAPI health endpoint: HTTP 200, eight synthetic documents loaded.
- Credential presence check: configured, without exposing the secret.

Tests exercise chunking, rank fusion, persisted indexing, retrieval, customer validation, one-active-run protection, exact-draft write protection, citation checks, escalation rules, attempted evidence bypass, obsolete workflow rejection, and OpenAI Agents SDK scripted pause/approval/rejection behavior. Approval is tested after recreating the engine and store. The API integration test covers 202 → polling → pending review → exact approval → export and rejects duplicate approval and replacement draft payloads.

Provider tests distinguish exhausted credits and spend limits from transient rate limits. Evaluation tests reject a case that retrieved the expected document but cited another. Python and JavaScript syntax checks passed. These controlled tests do not measure live LLM quality or prompt-injection resistance.

After the final documentation-header change, the four API integration tests passed again in 4.35 seconds. The final frontend change fixes the narrow-screen ticket-list overflow and refreshes cached assets. It was verified visually with five tickets: the conversation, draft area, and evidence panels fit the available window.

## Browser and repository checks

- Created one explicitly fictional ticket through the actual browser form; it appeared immediately and persisted after reload.
- Opened the Workspace exports source document without making an embedding request.
- FastAPI Swagger loaded its schema and exposed the `x-resolve-request` header for write requests.
- Browser console check returned no warnings or errors after the final reload.
- Saved the actual workbench screenshot as `resolve-workbench.jpg` for the README.
- Initialized local Git on `main`; verified `.env.local`, `.venv`, and `.runtime` are ignored.
- Added a GitHub Actions workflow; its hosted run is unverified until the repository is published.

Generation was not retried through the UI after credit exhaustion was confirmed. There is no live evaluation report or live quality claim.

## GitHub publication — 10 October 2026

The public repository is [sasthika-17/resolve-ai-support-agent](https://github.com/sasthika-17/resolve-ai-support-agent). The prepared source set contains 44 files, including the CI workflow, source screenshots, and documentation. Its publication check excludes the configured API credential, virtual environment, runtime databases, and test caches. GitHub CI results are visible on the repository's Actions page; the local results above are separate from the hosted run.

## Live provider check

`scripts/verify_live.py` started a real request using the saved credential. The run ended as `failed` during knowledge embedding with zero sources and no ticket-side write. A subsequent bounded diagnostic (one two-word embedding input, no retries) established the exact provider response:

```json
{"status": 429, "code": "credit_balance_exhausted", "type": "insufficient_quota"}
```

The provider message states that no credits remain. The earlier interpretation as ordinary rate limiting was incorrect and has been corrected in the app and documentation. Live embeddings and agent generation are **not yet verified**. This is an API billing blocker, not an accuracy or quality result; automatic retries cannot restore the balance.

Review [OpenAI API billing](https://platform.openai.com/settings/organization/billing). The saved credential remains configured and ignored by Git. No new key, credit purchase, or billing change was made during this diagnosis. See [OpenAI's error guidance](https://help.openai.com/en/articles/6614457-troubleshooting-api-usage-and-spend-limits).

When API access permits, run the bounded live verifier and then `evals/run_live.py --run`. The evaluation runner rejects each draft after grading, so it cannot save a resolution. Both commands can incur API charges.
