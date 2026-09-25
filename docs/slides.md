# Demo Day deck: outline (12 slides, 10 minutes)

Story arc required by the course: **problem → solution → demo → architecture → metrics & evals → conclusions**.

1. **Title**: *Bloom: a health coach that knows my data, my cycle and the research.* One line: "5 apps, 0 answers → 1 place, cited answers."
2. **The problem (60-second pitch)**: my data lives in Withings, Kinetix/Tanita, Apple Watch, Foodvisor. None of them talk to each other. Generic advice is male-default and often unproven ("train fasted in the morning"). With PCOS, wrong advice has real costs.
3. **The user**: one sentence. *A woman with PCOS who strength-trains and runs in Brussels and wants advice that fits her body and her data.* How she solves it today: screenshots, spreadsheets, Instagram advice.
4. **The solution**: dashboard screenshot + coach screenshot. Three personas, citations you can open, a doctor referral when needed, goals you approve.
5. **Live demo (3 min)**:
   (a) Today dashboard: cycle-phase shading on the weight trend.
   (b) Integrative Medicine: "Is fasted cardio bad for women with PCOS?" → open a citation, then show the evidence level.
   (c) "I fainted after my workout" → doctor branch.
   (d) "Set me a body-fat goal" → approve → Goals page.
   (e) Foodvisor screenshot → extraction + checks.
6. **Architecture**: the system diagram from ARCHITECTURE.md §1. Say *why* LangGraph over CrewAI/Parlant (explicit bounded loop + durable interrupt + tracing).
7. **The graph**: diagram §2. Point at the 3 branches, the citation loop and the HITL interrupt. Walk one request (§3).
8. **MCP + Skill**: why MCP (the same 8 tools serve the app *and* Claude Desktop, shown in a 10-second clip). Why a Skill (versioned domain policy, loaded only when triggered, works in Claude Code too).
9. **RAG + multimodal**: corpus choice (guidelines > meta-analyses), chunking at 450 tokens because of the reranker's 512 limit, the glued-PDF bug we found. Vision: Foodvisor has no API, so the screenshot *is* the data channel. Without vision we'd lose nutrition entirely.
10. **Evals**: golden set composition (42 examples, 8 categories). Metrics and what they *don't* show. LangSmith experiments screenshot.
11. **A/B results + cost**: gpt-4.1 vs mini, reranker on/off, prompt v1 → v2, temperature sweep. Cost per query and p50 latency. The decision each result led to.
12. **Conclusions**: what didn't work (hypotheses that failed: fasted-training claim, PDF parsing, embedded Qdrant lock), what breaks today (irregular-cycle phase estimation, judge self-bias), what's next (real users, auth, Oura/Garmin, BBT-based ovulation detection).

**Q&A prep**: see ARCHITECTURE.md §4–7 and docs/model_choice.md. Be ready for: cost per query, what happens if OpenAI is down (fallback + budget), what the metrics miss, why the cache is only for general questions.
