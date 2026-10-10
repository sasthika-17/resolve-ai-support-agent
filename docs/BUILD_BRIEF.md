# Resolve: build brief

## Confirmed requirements

- A second, separate resume project: entirely GenAI, with no data analyst component.
- Build the application, rather than only suggesting a project.
- Use the OpenAI Developers integration. A new credential has been securely saved to this project's ignored `.env.local`.
- Explain the implementation so the owner can demonstrate and defend it in interviews.

## Chosen scope

Resolve is a local support-resolution workbench for a fictional SaaS product, OrbitDesk. One tool-using agent searches a knowledge base, looks up a synthetic customer record, and prepares a cited resolution. Its final write tool pauses for human approval using the OpenAI Agents SDK. Approval records the resolution locally; the app has no email-sending or real account-changing integration.

The app owns the agent loop and approval state, so it uses the Agents SDK. FastAPI serves both a plain HTML/CSS/JavaScript interface and the API. SQLite persists tickets, chunk embeddings, audit events, and paused runs. The knowledge base combines cosine vector search with SQLite FTS5 keyword search using reciprocal rank fusion. This exact vector search is appropriate for a small portfolio corpus; production scale would need an ANN index.

## Verification targets

Real OpenAI generation and embeddings when account quota permits; deterministic tests for retrieval, source validation, persistence, approval/rejection, and invalid requests; a reproducible, opt-in live evaluation set. Only measured results belong in resume bullets.

## Open questions and limits

Live model access and account quota must be verified. No interview-call guarantee is possible. This version is localhost-only, single-user, uses synthetic customers and policies, and does not claim production authentication, delivery, customer impact, or benchmark generalization.
