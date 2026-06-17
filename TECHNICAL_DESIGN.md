# Technical Design Document
## Northwind Support Copilot - v1.0

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Support Agent UI                             │
│                  (Question Input Box)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    COPILOT SERVICE                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐         │
│  │  Retriever  │→ │  LLM Agent   │→ │  Formatter &    │         │
│  │  (Chroma)   │  │  (Groq)      │  │  Action Router  │         │
│  └─────────────┘  └──────────────┘  └─────────────────┘         │
│         ▲                                      │                 │
│         │                                      ▼                 │
│  ┌──────────────────────┐          ┌──────────────────┐         │
│  │ Vector DB (Chroma)   │          │  Tool: Draft     │         │
│  │ ·Embeddings          │          │  Reply (Mock)    │         │
│  │ ·Metadata Index      │          └──────────────────┘         │
│  └──────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
           ▲
           │
    ┌──────┴──────┐
    │  Doc Intake │
    │  Pipeline   │
    └──────┬──────┘
           │
    ┌──────▼─────────┐
    │ 25-30 Source   │
    │ PDFs/Markdown  │
    │ (Northwind     │
    │  Support Docs) │
    └────────────────┘
```

### Core Pipeline

**Step 1: Ingestion**
- Accept PDFs, Markdown, TXT files
- Extract plain text
- Clean metadata (source filename, upload date)

**Step 2: Chunking**
- Fixed 512-token chunks (overlap: 50 tokens)
- Fallback: recursive chunking if a document is very dense
- Chunk size chosen: balances context window + retrieval precision

**Step 3: Embedding**
- Model: `all-MiniLM-L6-v2` (sentence-transformers, local)
- Rationale: Runs locally — zero API cost, no key needed, ~90MB download, fast (~5ms per query)
- Alternative: `all-mpnet-base-v2` (local, free, higher quality), or `text-embedding-3-small` (OpenAI, cloud)

**Step 4: Vector Storage**
- Database: **Chroma** (in-memory or persistent)
- Why: Open-source, Python-native, integrates with LangChain
- Schema: `{id, chunk_text, source_doc, page_number, embeddings}`

**Step 5: Retrieval**
- Query embedding (same model as chunks)
- Cosine similarity search
- Return top-3 chunks (configurable)
- Score threshold: 0.7 (drop results below this)

**Step 6: Prompt Assembly**
- Format retrieved chunks with source citations
- Add system prompt: "You are a Northwind support expert. Answer only what the docs say. Cite sources."
- Include chat history (if multi-turn)

**Step 7: LLM Generation**
- Model: **Groq `llama-3.1-8b-instant`** (free tier available)
- Rationale: Ultra-fast (~200ms), free tier available, follows citation instructions well. Groq's inference is significantly faster than OpenAI for this use case.
- Temperature: 0.2 (low randomness, factual)
- Max tokens: 500

**Step 8: Post-Processing**
- Extract citations from response
- Add hyperlinks to source PDFs
- Format for ticket draft

**Step 9: Bounded Action**
- Single action available: **Draft Ticket Reply**
- Agent clicks → pre-formatted response populates Zendesk reply box
- Agent reviews before sending (human-in-the-loop)

---

## 2. Data Contracts (Pydantic Models)

All components speak one language: typed Python objects. No stringly-typed dictionaries.

### Model 1: IngestRequest
```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class IngestRequest(BaseModel):
    """Contract: Client uploads documents"""
    
    file_path: str = Field(..., description="Path to PDF or Markdown file")
    source_name: str = Field(..., description="e.g., 'pricing-enterprise', 'changelog-v5.2'")
    category: str = Field(
        default="general",
        description="One of: pricing, policy, product, changelog, integration"
    )
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "/uploads/Enterprise_SLA.pdf",
                "source_name": "SLA_Enterprise_2024",
                "category": "policy",
            }
        }
```

---

### Model 2: Chunk
```python
class Chunk(BaseModel):
    """Contract: A single indexed text chunk"""
    
    chunk_id: str = Field(..., description="Unique ID, e.g., 'sla_enterprise_chunk_3'")
    text: str = Field(..., description="512-token plain text")
    source_doc: str = Field(..., description="Original filename")
    page_number: Optional[int] = Field(None, description="Page in PDF (if available)")
    category: str = Field(..., description="Inherited from ingested doc")
    embedding: Optional[List[float]] = Field(None, description="1536-dim vector")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "sla_enterprise_chunk_3",
                "text": "Enterprise SLA: 4-hour first response for P1...",
                "source_doc": "Enterprise_SLA.pdf",
                "page_number": 2,
                "category": "policy",
                "embedding": [0.123, -0.456, ...],
            }
        }
```

---

### Model 3: RetrievalQuery
```python
class RetrievalQuery(BaseModel):
    """Contract: Input to retriever"""
    
    question: str = Field(..., description="Agent's natural language question")
    top_k: int = Field(default=3, ge=1, le=10)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    category_filter: Optional[str] = Field(None, description="Optional: only search in category")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What's the SLA for Enterprise customers?",
                "top_k": 3,
                "score_threshold": 0.7,
                "category_filter": "policy"
            }
        }
```

---

### Model 4: RetrievalResult
```python
class RetrievalResult(BaseModel):
    """Contract: Output from retriever"""
    
    chunks: List[Chunk]
    scores: List[float] = Field(..., description="Similarity scores (0-1), parallel to chunks")
    query: str
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunks": [
                    {
                        "chunk_id": "sla_enterprise_chunk_3",
                        "text": "Enterprise SLA: 4-hour...",
                        "source_doc": "Enterprise_SLA.pdf",
                        "page_number": 2,
                        "category": "policy",
                    }
                ],
                "scores": [0.89],
                "query": "What's the SLA for Enterprise customers?",
                "retrieved_at": "2024-06-17T10:30:00Z"
            }
        }
```

---

### Model 5: LLMPrompt
```python
class LLMPrompt(BaseModel):
    """Contract: Formatted prompt to send to LLM"""
    
    system_prompt: str
    user_message: str
    retrieved_context: str = Field(..., description="Formatted chunks + citations")
    chat_history: List[dict] = Field(default_factory=list)
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=500)
    
    class Config:
        json_schema_extra = {
            "example": {
                "system_prompt": "You are a Northwind support expert...",
                "user_message": "What's the SLA for Enterprise customers?",
                "retrieved_context": "Source: Enterprise_SLA.pdf, p2\nEnterprise SLA: 4-hour...",
                "chat_history": [],
                "temperature": 0.2,
                "max_tokens": 500
            }
        }
```

---

### Model 6: LLMResponse
```python
class LLMResponse(BaseModel):
    """Contract: Response from LLM"""
    
    answer: str = Field(..., description="Full answer with citations")
    citations: List[str] = Field(..., description="List of source filenames cited")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0-1 confidence score")
    model_used: str = Field(default="llama-3.1-8b-instant")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Based on Enterprise_SLA.pdf, the SLA for Enterprise customers is: 4-hour first response for P1 tickets, 8-hour for P2. See attached document for details.",
                "citations": ["Enterprise_SLA.pdf"],
                "confidence": 0.95,
                "model_used": "llama-3.1-8b-instant",
                "generated_at": "2024-06-17T10:30:05Z"
            }
        }
```

---

### Model 7: CopilotAction
```python
class CopilotAction(BaseModel):
    """Contract: Bounded action the copilot can take"""
    
    action_type: str = Field(..., description="One of: 'draft_reply', 'lookup_order', 'escalate'")
    target: Optional[str] = Field(None, description="For draft_reply: the ticket ID")
    payload: dict = Field(default_factory=dict, description="Action-specific data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "action_type": "draft_reply",
                "target": "ticket_12345",
                "payload": {
                    "reply_text": "Based on our documentation...",
                    "cite_sources": ["Enterprise_SLA.pdf"]
                }
            }
        }
```

---

### Model 8: CopilotResponse
```python
class CopilotResponse(BaseModel):
    """Contract: Complete end-to-end response"""
    
    question: str
    answer: str
    citations: List[str]
    confidence: float
    action: Optional[CopilotAction] = None
    retrieval_score: float = Field(..., description="Top result similarity score")
    latency_ms: float = Field(..., description="End-to-end time in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What's the SLA for Enterprise customers?",
                "answer": "Based on Enterprise_SLA.pdf, the SLA is...",
                "citations": ["Enterprise_SLA.pdf"],
                "confidence": 0.95,
                "action": {
                    "action_type": "draft_reply",
                    "target": "ticket_12345",
                    "payload": {...}
                },
                "retrieval_score": 0.89,
                "latency_ms": 1250
            }
        }
```

---

## 3. Model & Embedding Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Embedding Model** | `all-MiniLM-L6-v2` (sentence-transformers, local) | Free, no API key, runs locally, ~90MB. 100% hit rate on spike. |
| **LLM** | `llama-3.1-8b-instant` (Groq) | Ultra-fast (~200ms), free tier, strong citation following. |
| **Temperature** | 0.2 | Low randomness for factual answers. Not 0 (allows some paraphrasing). |
| **Vector DB** | Chroma | Python-native, simple, supports cosine similarity. |
| **Chunk Size** | ~150 words | Balances: enough context to answer most questions + precise retrieval. |

---

## 4. The One Bounded Action

### Action: Draft Ticket Reply

**Trigger:** Agent clicks "Draft Reply" button in copilot response.

**Flow:**
1. Copilot formats answer as customer-facing email
2. Adds signatures: "Based on [citations], here's what I found..."
3. Inserts into Zendesk reply field (ready to edit)
4. Agent reviews before sending

**Why bounded?** Not automated. Always human-in-the-loop. Reduces liability.

**Data Contract:**
```python
class DraftReplyAction(CopilotAction):
    action_type: str = "draft_reply"
    payload: dict = {
        "reply_text": str,           # Full reply ready to send
        "cite_sources": List[str],   # Attached doc links
        "ticket_id": str,
        "suggested_tone": str        # "Professional" / "Empathetic" / etc
    }
```

---

## 5. Deployment Architecture

### Infrastructure
```
┌─────────────────────────────────────┐
│  Local Dev / Docker Container       │
│  ├─ Chroma (in-process)             │
│  ├─ FastAPI server (port 8000)      │
│  ├─ 25-30 sample docs               │
│  └─ pytest suite                    │
└─────────────────────────────────────┘
```

### Production (Phase 2+)
```
┌──────────────┐         ┌──────────────┐
│  Zendesk     │◄────────┤  FastAPI     │
│  Webhooks    │         │  + Gunicorn  │
└──────────────┘         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │   Chroma     │
                         │  (persistent)│
                         └──────────────┘
                                │
                         ┌──────▼───────┐
                         │  S3 / Vector │
                         │  DB (backup) │
                         └──────────────┘
```

---

## 6. Testing Strategy

### Unit Tests
- Chunk ingestion: verify split correctly
- Embedding: verify output shape (1536 dims)
- Retrieval: verify top-k + threshold logic
- LLM formatting: verify citations extracted

### Integration Tests
- End-to-end: question → answer on real docs
- Latency: measure p95 on 50 queries
- Cost tracking: log every API call

### Evaluation
- Hit rate: correct doc in top-3? (Manual spot-check on 10 questions)
- Hallucination: does answer match source? (Red-team by reading answers)

---

## 7. Error Handling

| Failure Mode | Detection | Mitigation |
|--------------|-----------|-----------|
| Retrieval returns no results | `len(chunks) == 0` | Return "I don't have docs on this. Escalate to human." |
| LLM timeout (>10s) | Network error on API call | Fallback: return top chunk as-is + "Ask a human." |
| Low confidence (<0.5) | LLM response includes `[UNCERTAIN]` | Flag answer as draft; suggest manual review. |
| Hallucination detected | Answer has facts not in source | Log + alert; don't send automatically. |

---

## 8. Monitoring & Logging

Every request logs:
- `question`, `answer`, `citations`
- `retrieval_score`, `latency_ms`
- `action_taken` (if any)
- `agent_id`, `timestamp`
- Cost of API calls

Weekly dashboard:
- Hit rate trend
- Avg latency
- Cost per query
- Agent feedback (thumbs up/down)

---

## 9. Glossary

| Term | Definition |
|------|-----------|
| **Chunk** | Single 512-token piece of a document |
| **Embedding** | Vector representation of text (1536 dims) |
| **Hit Rate** | % of queries where correct doc retrieved in top-3 |
| **Citation** | Reference to source document with page number |
| **Hallucination** | Answer claim not supported by source docs |
| **Confidence** | 0-1 score: how sure is the LLM about the answer? |
| **Latency** | Time from question to answer displayed |
| **Bounded Action** | One specific action the copilot can take (vs. open-ended) |

---

**Next:** See `/diagrams/` for architecture and sequence diagrams.
