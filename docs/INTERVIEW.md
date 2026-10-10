# Interview preparation

## Sixty-second walkthrough

"Resolve is a local AI support-resolution workbench. A support ticket enters FastAPI. An OpenAI Agents SDK agent must call two scoped tools: it looks up a synthetic customer’s plan and role, then searches a policy knowledge base. The knowledge base uses OpenAI embeddings plus SQLite full-text search, fused with reciprocal-rank fusion. The agent writes a draft with exact source quotes. Before the final `record_resolution` tool can run, the SDK interrupts for human approval. The app persists server-side run state, verifies the exact tool arguments again on approval, and only then records a local resolution. I added deterministic tests for citations, duplicate approval, escalation rules, evidence bypass, and the API flow."

## Questions to prepare

| Question | Answer |
|---|---|
| Why one agent? | One workflow has one clear owner and three narrow tools. Multiple agents would add handoff failure modes without improving this scope. |
| What becomes an embedding? | Each policy title plus chunk, and later the search query. Vectors retrieve semantically similar passages. Ticket text is not permanently embedded in this version. |
| Why hybrid RAG? | Keyword search helps exact terms like SAML. Embeddings help paraphrases. Reciprocal-rank fusion combines their order without assuming their score scales are comparable. |
| How do you reduce hallucinations? | Tool requirements, small retrieved context, exact-quote validation, escalation when evidence is missing, and human approval before the only write tool. |
| How do you handle prompt injection? | Tickets, feedback, customer data, and documents are untrusted. Tools are narrow. The model cannot browse or execute arbitrary code. Server checks reject skipped evidence steps and unauthorized writes. These checks do not prove that the model resists every injected instruction. |
| Why is approval server-side? | A browser must not submit a serialized agent state or substitute tool arguments. The server loads its own snapshot and conditionally claims the exact pending draft. |
| How is double approval prevented? | A conditional SQL transition moves `waiting_review` to `resuming`, then the write accepts only the same stored draft in that state. |
| Why not a vector database? | Exact cosine search in SQLite is transparent and sufficient for a tiny portfolio corpus. At scale I would use a vector index, tenant filters, and recall/latency benchmarks. |
| How did you test without paying on every test? | The Agents SDK `ScriptedModel` simulates tool-call turns; a stable test embedder exercises retrieval. The live script is explicit and separate. |
| What did live verification show? | OpenAI returned HTTP 429 with credit_balance_exhausted. The API account has no remaining credits, so live embeddings and generation are unverified. The 24 deterministic local tests passed; those are separate evidence. |
| Does an exact quote prove an answer is true? | No. It proves the cited text exists in a retrieved passage. Human review and semantic evaluation must check whether that text supports each claim. |
| How do you evaluate it? | Four synthetic live cases check required cited policy, expected disposition, required tools, quote validation, and the pending-review boundary. Provider errors and skipped cases are reported separately. Larger held-out and adversarial sets are needed for quality claims. |
| What happens when the server restarts? | Pending drafts keep their server-side snapshots and can resume if the workflow/SDK version matches. In-flight work is marked interrupted. A mismatched draft can be rejected and regenerated. |

## Demo script

Use `ticket_export` first. Show its retrieved policy passage, reject the first draft, then generate another and approve it. Explain that approval saves only to local SQLite; no customer email is sent. In **Quality lab**, compare keyword and semantic retrieval. Finally use the HIPAA/compliance ticket to show a required escalation where the policy does not support a compliance claim.
