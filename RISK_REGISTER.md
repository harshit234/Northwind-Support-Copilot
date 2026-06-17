# Risk Register
## Northwind Support Copilot v1.0

**Assessment Date:** Week 15  
**Riskiest Assumption to De-risk:** Retrieval hit-rate (Risk #1)  
**De-risk Method:** Spike test on 10 real questions  

---

## Risk Summary Matrix

| Rank | Risk | Likelihood | Impact | Priority | Mitigation |
|------|------|-----------|--------|----------|-----------|
| **1** | Retrieval misses right doc (HIGH) | HIGH | CRITICAL | **RED** | Spike test on 10 Q's → hit rate ≥70% to proceed |
| **2** | LLM hallucination (makes up facts) | MEDIUM | CRITICAL | **RED** | Enforce citations; human-in-the-loop; red-team |
| **3** | Slow response (>5s latency) | MEDIUM | HIGH | **YELLOW** | Load testing; optimize embedding model |
| **4** | Low adoption (agents don't use it) | MEDIUM | HIGH | **YELLOW** | Pilot with top 3 agents; daily feedback loops |
| **5** | Doc updates break indexing | LOW | MEDIUM | **YELLOW** | Auto-versioning; test re-index flow |

---

## 🔴 Risk #1: Retrieval Misses the Right Document

### Description
If the semantic retrieval system fails to fetch the document containing the answer, even the best LLM will hallucinate or give wrong information. This is the load-bearing brick.

### Likelihood: **HIGH** (70% chance if untested)
- Semantic search can fail if:
  - Question is phrased differently than doc text
  - Embedding model doesn't capture domain-specific terms
  - Chunking strategy breaks context

### Impact: **CRITICAL**
- **Cost:** Core feature broken; agents go back to manual search
- **Reputation:** Customer gets wrong answer from AI (hallucinated)
- **Project:** Entire copilot deemed unreliable; sunk investment

### Current Mitigation (pre-spike)
- Using proven model: `text-embedding-3-small` (battle-tested by OpenAI)
- 512-token chunk size: balances context + precision
- Top-3 retrieval: gives LLM fallback if first choice is wrong

### **De-risk Approach (THE SPIKE)**

**What We Test:**
- Load 25 real Northwind docs (PDFs + support tickets)
- Create 10 realistic support questions from agent/customer data
- Chunk & embed everything
- For each question, check: is correct doc in top-3 results?

**Success Criteria:**
- ✅ Hit rate ≥90%: Ship immediately
- ⚠️ Hit rate 70-90%: Proceed with caution; add retrieval tuning to Phase 2
- ❌ Hit rate <70%: **BLOCKER** — go back to design (maybe hybrid retrieval or re-chunking)

**Spike Output:**
```
Question 1: "What's our SLA for Enterprise?"
Retrieved: [Enterprise_SLA.pdf (0.89), pricing.pdf (0.71), changelog.pdf (0.62)]
Correct: Enterprise_SLA.pdf
Hit: ✓ YES

Question 2: "How do I reset a password?"
Retrieved: [general_faq.pdf (0.84), auth.pdf (0.70), security.pdf (0.65)]
Correct: auth.pdf
Hit: ✗ NO

...

TOTAL: 9/10 hits (90%)
Confidence: PROCEED
```

**Responsibility:** You (AI engineer) — Run spike in Phase 5 before Phase 2 kickoff

---

## 🔴 Risk #2: LLM Hallucination (Makes Up Facts)

### Description
The LLM generates confident-sounding answers that aren't supported by the retrieved documents. Customer sees made-up SLA, policy, or product feature.

### Likelihood: **MEDIUM** (40% for GPT-4, 60% for cheaper models)
- GPT-4 is better than GPT-3.5, but still hallucinates
- Temperature 0.2 reduces it but doesn't eliminate it
- No document context = high hallucination risk

### Impact: **CRITICAL**
- **Legal:** Customer relies on fabricated policy → disputes, chargeback
- **Trust:** One visible hallucination = brand damage + product killed
- **KPI:** Do-not-ship floor is 15% hallucination rate; <5% is target

### Current Mitigation
- **Enforce citations:** Prompt says "Only answer using the provided docs. Every claim must cite a source."
- **Temperature 0.2:** Reduces randomness
- **Human-in-the-loop:** Agent reviews before sending; catches obvious errors

### Deeper Mitigation (Phase 2+)
- Red-team the prompt: LLM plays devil's advocate, tries to break the answer
- Fine-tuning: Train on Q&A pairs from Northwind docs (not yet, too expensive)
- Structured output: Use constraint-based generation to force citations

### Testing the Fix
- **Week 16 (Phase 1):** Manually audit 30 generated answers
- Track: Does answer claim X? Is X in the source doc?
- Calculate: Hallucination rate
- **Gate:** If >15%, refine prompt + retrain; don't launch

**Responsibility:** Support lead (manual audit) + You (prompt tuning)

---

## 🟡 Risk #3: Slow Response (>5s Latency)

### Description
End-to-end response takes >5 seconds. Agents wait, get frustrated, switch back to manual search. Kills adoption.

### Likelihood: **MEDIUM** (50%)
- Embedding lookup: ~50-150ms (usually fast)
- LLM generation: ~1-2 seconds (varies by model)
- Network: ~100-500ms (API roundtrips)
- **Total:** Usually <2s, but p95 could hit 5-10s under load

### Impact: **HIGH**
- **Adoption:** >3s → users start alt-tabbing
- **Cost:** Slower queries might mean more retries
- **UX:** Copilot feels slow; doesn't beat manual search

### Mitigation
- **Model choice:** GPT-4-turbo (optimized for speed)
- **Caching:** Same question asked twice → answer cached
- **Async:** Don't wait for LLM; stream chunks while generating
- **Load testing:** Week 16 → simulate 5 concurrent agents, measure latency

**Success Criteria:**
- p95 latency <2s: ✅ Ship
- p95 latency 2-5s: ⚠️ Monitor; optimize if p99 > 5s
- p95 latency >5s: ❌ Blocker; reduce max_tokens or switch model

**Responsibility:** You (load testing in Phase 1)

---

## 🟡 Risk #4: Low Adoption (Agents Don't Use It)

### Description
Even if the copilot works technically, agents don't trust it or don't know it exists. Usage stays low (<20% of questions in month 1).

### Likelihood: **MEDIUM** (45%)
- Agents have ingrained manual-search habits (strong inertia)
- If copilot is "nice to have," they'll skip it
- If it makes them slower (latency >3s), they'll abandon it

### Impact: **HIGH**
- **Project ROI:** Can't justify continued investment
- **Cost:** Licensing + infra costs with zero return
- **Org:** Narrative of "AI project that didn't work"

### Mitigation Strategy

**Week 19 (Soft Launch):**
- Pick 3 trusted agents (not the skeptics, not the enthusiasts)
- Install copilot in their Zendesk interface
- Daily check-ins: "What was broken? What was helpful?"
- Fix top 3 bugs every 2 days

**Week 20 (Rollout):**
- Expand to all 25 agents
- Show dashboard: "You saved 45 min using the copilot today"
- Incentivize: "If hit rate ≥90%, team gets $500 bonus"

**Support**
- Weekly "copilot clinic" office hours (you + support lead)
- Slack channel for agent questions
- Video training: 5 min "How to use the copilot"

**Success Metric:**
- Week 20: ≥60% of agents use it for ≥50% of questions
- If <40% by week 21: pause, re-interview agents, redesign

**Responsibility:** You + Support Manager (joint ownership of adoption)

---

## 🟡 Risk #5: Doc Updates Break Indexing

### Description
Support team uploads a new changelog or policy PDF. System fails to chunk/embed it. Index becomes stale. Copilot gives outdated answers.

### Likelihood: **LOW** (20%)
- Chroma is stable
- Python embedding pipeline is straightforward
- But edge cases: corrupted PDFs, very large files, special encodings

### Impact: **MEDIUM**
- **Latency:** Takes 1-2 days to notice outdated answer
- **Trust:** "The copilot said X, but that's not our policy anymore"
- **Fix time:** 1-2 hours to re-index

### Mitigation

**Preventive:**
- Auto-versioning: Each document upload creates a new version
- Test re-index flow: Weekly, intentionally re-index one old doc
- Rollback: Keep previous index; can swap back if new one corrupts

**Detective:**
- Monthly audit: Compare top 10 customer questions → answers unchanged
- If doc updated, copilot should mention date: "Based on Enterprise_SLA.pdf (updated 2024-06-15)"

**Corrective:**
- Support lead can re-upload single doc without full re-index
- Automated daily check: Verify ingestion logs for errors

**Success Criteria:**
- 100% of uploads succeed (test before hand-off to support)
- 0 stale docs discovered in month 1 audit

**Responsibility:** You (build robust ingestion pipeline)

---

## 🟢 Risk #6: Cost Overruns (Honorable Mention)

### Description
API costs exceed budget. Each query costs $0.10, not $0.01. At 50 queries/day, that's $500/month.

### Likelihood: **LOW** (15%)
- `text-embedding-3-small` is cheap (~$0.02 per 1M tokens)
- GPT-4-turbo is expensive but fast
- Spike will show real costs

### Impact: **MEDIUM**
- **Budget:** $500/month vs. budgeted $100/month
- **ROI:** Cost per ticket higher than current agent salary (~$30/ticket agent vs. $0.01/ticket copilot)

### Mitigation
- **Cache embeddings:** Don't re-embed same question
- **Batch processing:** If off-hours, use GPT-3.5 (cheaper)
- **Monitor closely:** Weekly cost dashboard
- **Fallback:** If costs spike, switch to local embedding model (free, slightly worse quality)

---

## Risk Ownership & Timeline

| Risk | Owner | Review Date | Status |
|------|-------|-------------|--------|
| #1: Retrieval | You | After spike (Week 15) | 🔴 **BLOCKER** — Spike required |
| #2: Hallucination | You + Support Lead | After Phase 1 (Week 16) | 🔴 Must audit 30 answers |
| #3: Latency | You | After Phase 1 (Week 16) | 🟡 Monitor p95 |
| #4: Adoption | You + Manager | After soft launch (Week 20) | 🟡 Pilot with 3 agents |
| #5: Doc Updates | You | After Phase 1 (Week 16) | 🟡 Test re-index once |
| #6: Cost | You | Monthly | 🟢 Track weekly |

---

## Decision Gates

### Gate 1: After De-risk Spike (Week 15)
**Retrieval hit rate ≥70%?**
- YES → Proceed to Phase 1 (build MVP)
- NO → Return to design; reconsider chunking strategy or embedding model

### Gate 2: After Phase 1 (Week 16)
**Hallucination rate <15%?**
- YES → Proceed to Phase 2 (add actions)
- NO → Refine prompt; red-team more; revisit

### Gate 3: After Pilot (Week 20)
**Agent adoption ≥40%?**
- YES → Full rollout
- NO → Pause; interview agents; redesign UX

---

## Red-Team Checklist

Ask yourself these hard questions:

- [ ] If retrieval fails silently (returns low-confidence chunks), what happens?
- [ ] If agent asks out-of-scope question (not in docs), how does copilot respond?
- [ ] If copilot is slow (>5s), do agents really wait or just search manually?
- [ ] If hallucination happens in front of a customer, how do we mitigate?
- [ ] If support team gets busy, will they update docs?
- [ ] If copilot breaks (API down), do agents have a fallback?
- [ ] Can the copilot admit uncertainty, or does it always sound confident?

---

## Escalation Path

**If a risk hits RED (blocker):**
1. Immediately notify: Support Manager + Tech Lead
2. You: 4-hour spike to characterize the problem
3. Team meeting: Decide go/no-go within 24 hours
4. If no-go: Document learnings; pivot or cancel

**If a risk hits YELLOW (caution):**
1. Add to Phase 2 backlog (don't let it slip)
2. Monitor weekly; escalate if trend worsens
3. Mitigation doesn't block launch; mitigates after

**If a risk hits GREEN (low concern):**
1. Monitor quarterly; no action needed

---

**Last Updated:** Week 15 Mini-Project  
**Next Review:** After De-risk Spike (Week 15)
