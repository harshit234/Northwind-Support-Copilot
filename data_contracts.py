"""
Data Contracts for Northwind Support Copilot
All components speak through typed Pydantic models
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class DocCategory(str, Enum):
    """Document categories for filtering"""
    PRICING = "pricing"
    POLICY = "policy"
    PRODUCT = "product"
    CHANGELOG = "changelog"
    INTEGRATION = "integration"
    GENERAL = "general"


class ActionType(str, Enum):
    """Available bounded actions"""
    DRAFT_REPLY = "draft_reply"
    LOOKUP_ORDER = "lookup_order"
    ESCALATE = "escalate"


class ConfidenceLevel(str, Enum):
    """Confidence buckets"""
    HIGH = "high"      # ≥0.8
    MEDIUM = "medium"  # 0.5-0.8
    LOW = "low"        # <0.5


# ============================================================================
# INGEST PIPELINE
# ============================================================================

class IngestRequest(BaseModel):
    """Incoming document for indexing"""
    
    file_path: str = Field(..., description="Path to PDF or Markdown file")
    source_name: str = Field(..., description="e.g., 'pricing-enterprise', 'changelog-v5.2'")
    category: DocCategory = Field(default=DocCategory.GENERAL)
    uploaded_by: Optional[str] = Field(None, description="Support lead email")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "/uploads/Enterprise_SLA.pdf",
                "source_name": "SLA_Enterprise_2024",
                "category": "policy",
                "uploaded_by": "sarah@northwind.com"
            }
        }


class IngestResponse(BaseModel):
    """Result of ingesting a document"""
    
    source_name: str
    num_chunks: int = Field(..., description="Number of 512-token chunks created")
    status: str = Field(..., description="'success' or 'failed'")
    error: Optional[str] = None
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_name": "SLA_Enterprise_2024",
                "num_chunks": 8,
                "status": "success",
                "indexed_at": "2024-06-17T10:30:00Z"
            }
        }


# ============================================================================
# CHUNK & VECTOR STORE
# ============================================================================

class Chunk(BaseModel):
    """A single indexed text chunk"""
    
    chunk_id: str = Field(..., description="Unique ID, e.g., 'sla_enterprise_chunk_3'")
    text: str = Field(..., description="512-token plain text snippet")
    source_doc: str = Field(..., description="Original filename (e.g., 'Enterprise_SLA.pdf')")
    page_number: Optional[int] = Field(None, description="Page in PDF (if available)")
    category: DocCategory = Field(default=DocCategory.GENERAL)
    chunk_index: int = Field(..., description="Order in document (0-indexed)")
    embedding: Optional[List[float]] = Field(
        None, 
        description="384-dim vector from sentence-transformers all-MiniLM-L6-v2 (local)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "sla_enterprise_chunk_3",
                "text": "Enterprise SLA: 4-hour first response for P1 issues...",
                "source_doc": "Enterprise_SLA.pdf",
                "page_number": 2,
                "category": "policy",
                "chunk_index": 3,
                "embedding": [0.123, -0.456, 0.789, ...]
            }
        }


class ChunkWithScore(BaseModel):
    """Chunk + retrieval score"""
    
    chunk: Chunk
    similarity_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Cosine similarity (0-1)"
    )


# ============================================================================
# RETRIEVAL
# ============================================================================

class RetrievalQuery(BaseModel):
    """Input to retriever"""
    
    question: str = Field(..., description="Agent's natural language question")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of chunks to retrieve")
    score_threshold: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0, 
        description="Min similarity score"
    )
    category_filter: Optional[DocCategory] = Field(
        None, 
        description="Optional: only search in one category"
    )
    agent_id: Optional[str] = Field(None, description="For logging")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What's the SLA for Enterprise customers?",
                "top_k": 3,
                "score_threshold": 0.7,
                "category_filter": "policy",
                "agent_id": "agent_42"
            }
        }


class RetrievalResult(BaseModel):
    """Output from retriever"""
    
    chunks_with_scores: List[ChunkWithScore] = Field(
        ..., 
        description="Retrieved chunks ranked by score"
    )
    query: str
    top_score: float = Field(..., description="Highest similarity score")
    hit: bool = Field(
        ..., 
        description="True if top result has score >= threshold"
    )
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: float = Field(..., description="Retrieval time in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunks_with_scores": [
                    {
                        "chunk": {...},
                        "similarity_score": 0.89
                    }
                ],
                "query": "What's the SLA for Enterprise customers?",
                "top_score": 0.89,
                "hit": True,
                "latency_ms": 145
            }
        }


# ============================================================================
# LLM PROMPTING
# ============================================================================

class LLMPrompt(BaseModel):
    """Formatted prompt ready to send to LLM"""
    
    system_prompt: str = Field(
        ..., 
        description="System instructions for the LLM"
    )
    user_message: str = Field(..., description="The agent's question")
    context: str = Field(
        ..., 
        description="Formatted retrieved chunks with citations"
    )
    chat_history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Previous messages in conversation"
    )
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=500, ge=100, le=2000)
    
    class Config:
        json_schema_extra = {
            "example": {
                "system_prompt": "You are a Northwind support expert...",
                "user_message": "What's the SLA for Enterprise customers?",
                "context": "Source: Enterprise_SLA.pdf (p2)\nEnterprise SLA: ...",
                "chat_history": [],
                "temperature": 0.2,
                "max_tokens": 500
            }
        }


class LLMResponse(BaseModel):
    """Response from LLM"""
    
    answer: str = Field(
        ..., 
        description="Full answer with inline citations"
    )
    citations: List[str] = Field(
        ..., 
        description="List of source filenames cited"
    )
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Confidence score (0-1)"
    )
    contains_uncertainty: bool = Field(
        default=False,
        description="True if answer includes [UNCERTAIN] tag"
    )
    model_used: str = Field(default="llama-3.1-8b-instant")  # Default Groq model
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generation_latency_ms: float = Field(..., description="Time to generate in ms")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Based on Enterprise_SLA.pdf, the SLA is: 4-hour first response for P1 issues, 8-hour for P2.",
                "citations": ["Enterprise_SLA.pdf"],
                "confidence": 0.95,
                "contains_uncertainty": False,
                "model_used": "llama-3.1-8b-instant",
                "generation_latency_ms": 200
            }
        }


# ============================================================================
# ACTIONS
# ============================================================================

class DraftReplyPayload(BaseModel):
    """Payload for draft_reply action"""
    
    reply_text: str = Field(..., description="Full reply ready to send to customer")
    cite_sources: List[str] = Field(..., description="Source PDFs to attach")
    ticket_id: str = Field(..., description="Zendesk ticket ID")
    suggested_tone: str = Field(
        default="professional",
        description="'professional', 'empathetic', 'technical'"
    )


class CopilotAction(BaseModel):
    """Bounded action the copilot can take"""
    
    action_type: ActionType = Field(...)
    target: Optional[str] = Field(None, description="e.g., ticket ID")
    payload: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "action_type": "draft_reply",
                "target": "ticket_12345",
                "payload": {
                    "reply_text": "Based on our documentation...",
                    "cite_sources": ["Enterprise_SLA.pdf"],
                    "ticket_id": "ticket_12345",
                    "suggested_tone": "professional"
                }
            }
        }


# ============================================================================
# END-TO-END RESPONSE
# ============================================================================

class CopilotResponse(BaseModel):
    """Complete response from copilot (question → answer → action)"""
    
    question: str
    answer: str = Field(..., description="Full answer with citations")
    citations: List[str] = Field(..., description="Source documents")
    confidence: ConfidenceLevel = Field(..., description="High/Medium/Low")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    
    action: Optional[CopilotAction] = Field(
        None, 
        description="Optional bounded action (e.g., draft reply)"
    )
    
    # Retrieval metrics
    retrieval_score: float = Field(
        ..., 
        description="Top result similarity score"
    )
    retrieval_hit: bool = Field(
        ..., 
        description="True if correct doc retrieved"
    )
    
    # Timing
    total_latency_ms: float = Field(..., description="End-to-end time")
    retrieval_latency_ms: float
    generation_latency_ms: float
    
    # Logging
    agent_id: Optional[str] = None
    query_id: str = Field(default_factory=lambda: str(datetime.utcnow().timestamp()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Cost tracking
    embedding_cost: float = Field(default=0.0, description="Cost of embeddings in $")
    generation_cost: float = Field(default=0.0, description="Cost of LLM in $")
    total_cost: float = Field(default=0.0, description="Total API cost in $")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What's the SLA for Enterprise customers?",
                "answer": "Based on Enterprise_SLA.pdf, the SLA is...",
                "citations": ["Enterprise_SLA.pdf"],
                "confidence": "high",
                "confidence_score": 0.95,
                "action": {
                    "action_type": "draft_reply",
                    "target": "ticket_12345",
                    "payload": {...}
                },
                "retrieval_score": 0.89,
                "retrieval_hit": True,
                "total_latency_ms": 1400,
                "retrieval_latency_ms": 150,
                "generation_latency_ms": 1100,
                "agent_id": "agent_42",
                "embedding_cost": 0.0001,
                "generation_cost": 0.0075,
                "total_cost": 0.0076
            }
        }


# ============================================================================
# EVALUATION & METRICS
# ============================================================================

class HitRateRecord(BaseModel):
    """Single record for hit-rate evaluation"""
    
    question_id: int = Field(..., description="1-50")
    question: str
    retrieved_source: str = Field(..., description="Top source retrieved")
    correct_source: str = Field(..., description="What was correct")
    hit: bool = Field(..., description="True if retrieved == correct")
    retrieval_score: float


class HitRateEvaluation(BaseModel):
    """Hit-rate results"""
    
    records: List[HitRateRecord]
    total_questions: int
    total_hits: int
    hit_rate_percent: float = Field(..., description="(hits / total) * 100")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "records": [
                    {
                        "question_id": 1,
                        "question": "What's the SLA?",
                        "retrieved_source": "Enterprise_SLA.pdf",
                        "correct_source": "Enterprise_SLA.pdf",
                        "hit": True,
                        "retrieval_score": 0.89
                    }
                ],
                "total_questions": 10,
                "total_hits": 9,
                "hit_rate_percent": 90.0
            }
        }


class QueryMetrics(BaseModel):
    """Metrics for a single query"""
    
    query_id: str
    question: str
    latency_ms: float
    cost_usd: float
    hit: bool
    confidence: float
    hallucinated: bool = Field(False, description="Manual flag: answer unsupported by source")


class AggregateMetrics(BaseModel):
    """Weekly/monthly aggregate metrics"""
    
    num_queries: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_cost_usd: float
    hit_rate_percent: float
    hallucination_rate_percent: float
    avg_confidence: float
    period: str = Field(..., description="'week', 'month'")
    
    class Config:
        json_schema_extra = {
            "example": {
                "num_queries": 250,
                "p50_latency_ms": 1200,
                "p95_latency_ms": 1800,
                "p99_latency_ms": 2200,
                "avg_cost_usd": 0.0078,
                "hit_rate_percent": 88.5,
                "hallucination_rate_percent": 2.1,
                "avg_confidence": 0.87,
                "period": "week"
            }
        }
