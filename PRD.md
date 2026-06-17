# Product Requirements Document (PRD)
## Northwind Support Copilot - v1.0

**Last Updated:** [Today]  
**Owner:** AI Copilot Team  
**Status:** In Design Phase

---

## 1. Problem Statement

### Current State (The Pain)

**Who Hurts:** Northwind support agents (25 people) + new hires

**The Cost:**
- **Handle Time:** Average 18 minutes per ticket → 2 hours/day per agent digging through docs
- **Ramp Time:** New agents take 3-4 weeks to answer confidently (vs. 1 week desired)
- **Inconsistency:** Same question gets 3 different answers depending on which agent fields it
- **Stress:** Agents feel unsupported; customers wait; SLA breaches rising

**Business Impact:**
- ~50 tickets/day × 15 min wasted = 12.5 hours/day of support labor
- At $30/hr fully loaded = **~$375/day in waste** (~$91K/year)
- Customer satisfaction declining due to slow/inconsistent responses

### Root Cause
Support knowledge lives in **scattered, unindexed places:**
- 200+ help center articles (Zendesk)
- 50+ product PDFs (changelogs, integrations)
- 30+ policy docs (SLA, refund, etc.)
- 10+ Slack threads (undocumented fixes)

Agents manually search, often miss the right doc, give hedged or wrong answers.

---

## 2. Proposed Solution

**Northwind Support Copilot:** An AI agent that:
1. **Listens** to what an agent needs (natural language question)
2. **Retrieves** the exact doc/page that answers it (with confidence score)
3. **Drafts** a cited response (agent reviews before sending)
4. **Acts** (optional: draft ticket reply, look up customer order, link to KB)

**User Experience:**
```
Agent: "What's our SLA for Enterprise customers?"
Copilot: "Based on Pricing_Enterprise.pdf §3.2:
  SLA: 4-hour first response for P1, 24h for P2.
  
  [Draft Reply] [Link to Doc] [Look Up Customer] [Copy Answer]"
```

Agent spends 30 seconds reviewing instead of 15 minutes searching.

---

## 3. Users & User Stories

### Primary User: Support Agent (24/7)
**Story 1:** As a support agent, I need the copilot to answer a customer question with the source document cited, so I can respond quickly and confidently.  
*Acceptance: Agent sees answer + source in <2 seconds.*

**Story 2:** As a new agent (week 1), I need the copilot to teach me which docs exist and how to find answers, so I ramp faster.  
*Acceptance: New agent answers 80% of common questions using copilot by day 3.*

**Story 3:** As a support agent, I need to draft and send a reply directly from the copilot, so I don't copy-paste into the ticketing system.  
*Acceptance: One-click "draft reply" appears in ticket system.*

### Secondary User: Support Lead (Weekly)
**Story 4:** As a support manager, I need to upload new docs (changelogs, policies) and have them indexed automatically, so the copilot stays fresh.  
*Acceptance: New doc searchable within 5 minutes of upload.*

### Tertiary User: Exec (Monthly)
**Story 5:** As a Northwind exec, I need to see that this copilot reduces handle time and improves consistency, so I know the investment pays off.  
*Acceptance: Monthly dashboard shows handle time -40%, rework rate -60%.*

---

## 4. Scope: v1.0

### In Scope ✅
- Semantic search across 200+ documents (Chroma + embeddings)
- LLM-powered answer generation (OpenAI GPT-4 or Claude)
- Citation + source linking (which doc answered this?)
- One bounded action: **Draft ticket reply** (agent copies into Zendesk)
- Latency <2s (p95)
- Works on 99% of support question types (pricing, product, policy)

### Explicitly Out of Scope ❌
- Real-time Slack integration (Phase 2)
- Automated ticket reply (too risky; always agent-reviewed for v1)
- Sentiment analysis or escalation logic (Phase 2)
- Multi-language support (Phase 2)
- Custom RAG fine-tuning (Phase 2)
- Integration with Zendesk API (Phase 1.5)

---

## 5. Functional Requirements

| Requirement | Description |
|-------------|-------------|
| **FR-1: Document Ingestion** | System accepts PDFs, Markdown, and text files. Auto-chunks into 512-token pieces. Indexes into Chroma. |
| **FR-2: Semantic Retrieval** | Given a question, return top-3 most relevant chunks with confidence scores. |
| **FR-3: Answer Generation** | LLM reads retrieved chunks, generates answer citing source documents. |
| **FR-4: Source Linking** | Answer includes clickable link to source PDF/page. |
| **FR-5: Bounded Action** | Agent can click "Draft Reply" → pre-formatted response appears (ready to copy to ticket). |
| **FR-6: Refresh Mechanism** | New docs indexed within 5 minutes of upload. |
| **FR-7: Conversation Memory** | Support agent can ask follow-ups in same session (e.g., "And what about refunds for Enterprise?"). |

---

## 6. Non-Functional Requirements

| Requirement | Target | Floor |
|-------------|--------|-------|
| **Latency (p95)** | <2 seconds | <5 seconds |
| **Availability** | 99.5% uptime | 95% uptime |
| **Cost per Query** | <$0.01 | <$0.05 |
| **Hallucination Rate** | <5% | <15% |
| **Data Privacy** | GDPR-compliant (no customer PII in embeddings) | No customer data in logs |
| **Concurrent Users** | 5 agents at once | 2 agents at once |

---

## 7. Success Metrics / KPIs

### Metric 1: Retrieval Hit Rate ⭐ **Riskiest**
**Definition:** % of support questions where the correct source document appears in the top-3 retrieved chunks.

**How Measured:**
- Run copilot on 50 recent support tickets
- Manually verify: does the source doc we retrieved match what agent used?
- Hit = retrieved doc was the right answer source

**Target:** ≥90% (must have)  
**Floor:** ≥70% (minimum viable)  
**Why it matters:** If retrieval fails, LLM hallucination is guaranteed. This is the load-bearing brick.

---

### Metric 2: Answer Relevance
**Definition:** Agent rating of copilot answer relevance on 1-5 scale (1=useless, 5=perfect).

**How Measured:**
- Support lead manually reviews 20 copilot answers
- Scores: Does answer directly address the question? Any missing info?
- Average score

**Target:** ≥4.2/5  
**Floor:** ≥3.5/5  
**Why it matters:** High retrieval doesn't guarantee a good answer. We measure what agents actually see.

---

### Metric 3: Latency (p95)
**Definition:** 95th percentile end-to-end response time (question → answer ready).

**How Measured:**
- Log timestamp on every query
- Track: question received → answer displayed
- Weekly p95 calculation

**Target:** <2 seconds  
**Floor:** <5 seconds  
**Why it matters:** >5s and agents alt-tab back to manual search. Latency kills adoption.

---

### Metric 4: Hallucination Rate
**Definition:** % of copilot answers containing claims unsupported by the retrieved documents.

**How Measured:**
- Support lead audits 30 copilot answers
- Red-team: does answer say something the source docs don't justify?
- Hallucination = claim in answer but not in source

**Target:** <5%  
**Floor:** <15%  
**Why it matters:** One hallucination = lost trust. Customers see it = brand damage. This is a hard gate.

---

### Metric 5: Cost per Resolved Query
**Definition:** Total API cost (LLM + embeddings) ÷ number of queries answered.

**How Measured:**
- Sum OpenAI/Claude API bills monthly
- Divide by total queries answered
- Track: embedding cost + generation cost per query

**Target:** <$0.01/query  
**Floor:** <$0.05/query  
**Why it matters:** At 50 tickets/day, exceeding $0.05/query = $2,500/month. Must be <$500/month.

---

### Metric 6: Handle Time Reduction ⭐ **Business KPI**
**Definition:** % reduction in time agents spend per ticket (before vs. after copilot).

**How Measured:**
- Zendesk native: avg time per ticket
- Compare: 2 weeks before copilot launch vs. 2 weeks after
- Calculation: (Before - After) / Before × 100%

**Target:** ≥40% reduction  
**Floor:** ≥20% reduction  
**Why it matters:** Justifies the build. Without this, we shipped a cool demo, not a product.

---

## 8. Assumptions & Dependencies

### Assumptions
1. **Retrieval is the bottleneck** → If we solve retrieval, LLM generation is easy
2. **Indexed docs are current** → Support will keep PDFs/changelogs updated
3. **Agents will actually use it** → Adoption curve: 0-30 days = 20%, 30-90 days = 60%, 90+ days = 85%
4. **Hallucination <5% is acceptable** → Not zero; humans also make mistakes

### Dependencies
- Support lead provides 25-30 real docs (PDFs, Markdown)
- OpenAI API access (or Claude API)
- Zendesk webhook for real-time ticket logging (Phase 1.5)

---

## 9. Risk Highlights (See RISK_REGISTER.md)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Retrieval misses the right doc | HIGH | CRITICAL | De-risk spike: test on 10 real questions |
| LLM hallucination (makes up facts) | MEDIUM | CRITICAL | Enforce citations; red-team with real agent |
| Slow response (>5s) | MEDIUM | HIGH | Load test; optimize embedding model |
| Agents ignore copilot (low adoption) | MEDIUM | HIGH | Demo with top 3 agents first; collect feedback daily |
| Doc updates break indexing | LOW | MEDIUM | Auto-versioning; test re-index flow |

---

## 10. Timeline & Phases

| Phase | Deliverable | Timeline |
|-------|-------------|----------|
| **Phase 0** | Spec + Design (this PRD) | Week 15 (1 day) |
| **Phase 1** | MVP (retrieval + generation, no action) | Week 16 (3 days) |
| **Phase 2** | Add bounded action (draft reply) | Week 17 (2 days) |
| **Phase 3** | Closed-loop eval + refinement | Week 18+ (1 week) |
| **Phase 4** | Soft launch (5 agents) | Week 19 |
| **Phase 5** | Full launch + monitoring | Week 20 |

---

## 11. Success Criteria for v1.0 Launch

- [x] ≥90% retrieval hit rate on 50 real tickets
- [x] <5% hallucination rate (30-answer audit)
- [x] <2s p95 latency
- [x] <$0.01 per query
- [x] Agent feedback: ≥4.0/5 usability rating
- [x] One month of clean logs, no support escalations about AI errors

---

## 12. Post-Launch (Phase 2+)

- Multi-turn conversation (context from previous q's)
- Slack integration
- Automatic ticket escalation (out-of-scope → human)
- Fine-tuned embeddings on Northwind terminology
- Sentiment detection + priority routing
- Monthly doc refresh from Zendesk + Slack

---

**Approved by:** [Your name]  
**Date:** [Today]
