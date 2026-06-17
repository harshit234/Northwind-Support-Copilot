"""
De-risk Spike: Retrieval Hit Rate Test
======================================

Tests the riskiest assumption: "Can we reliably retrieve the correct document?"

Workflow:
1. Load 15-30 real Northwind docs (PDFs/Markdown)
2. Chunk & embed into Chroma (using sentence-transformers, NO API key needed)
3. Run 10 real support questions
4. Check: Is correct doc in top-3 results?
5. Output: Table of results + summary statistics

Stack:
  Embeddings : sentence-transformers (local, free, no API key)
  Vector DB  : ChromaDB (in-memory)
  LLM        : Groq (used in Phase 1, not this spike)

Run: python retrieval_spike.py
"""

import os
import json
import time
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime
import sys

# Fix Windows cp1252 terminal encoding (allows emoji/unicode output)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Install if needed:
# pip install chromadb sentence-transformers pydantic python-dotenv

try:
    import chromadb
except ImportError:
    print("ERROR: chromadb not installed. Run: pip install chromadb")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: sentence-transformers not installed. Run: pip install sentence-transformers")
    sys.exit(1)

try:
    from pydantic import BaseModel
except ImportError:
    print("ERROR: pydantic not installed. Run: pip install pydantic")
    sys.exit(1)

import dotenv
dotenv.load_dotenv()


# ============================================================================
# DATA MODELS
# ============================================================================

class TestQuestion(BaseModel):
    """A single test question"""
    question_id: int
    question: str
    correct_source: str  # Expected source doc


class RetrievalTestResult(BaseModel):
    """Result of retrieving for one question"""
    question_id: int
    question: str
    correct_source: str
    retrieved_sources: List[str]  # Top 3, in order
    retrieved_scores: List[float]
    hit: bool  # True if correct_source in retrieved_sources
    top_score: float


# ============================================================================
# SAMPLE DATA: NORTHWIND SUPPORT DOCS
# ============================================================================

SAMPLE_DOCS = {
    "Enterprise_SLA.pdf": """
    NORTHWIND ENTERPRISE SLA
    
    Enterprise customers receive premium support:
    - First response: 4 hours for P1 issues
    - First response: 8 hours for P2 issues
    - First response: 24 hours for P3 issues
    
    P1 = System down, critical data loss
    P2 = Feature broken, workaround exists
    P3 = Minor issue, cosmetic
    
    SLA is measured from ticket creation to first agent response.
    """,
    
    "pricing.pdf": """
    NORTHWIND PRICING (2024)
    
    Standard Plan: $99/month
    - Up to 100 users
    - 5 GB storage
    - Email support
    
    Professional Plan: $299/month
    - Up to 500 users
    - 100 GB storage
    - 24/7 chat support
    
    Enterprise Plan: $999+/month
    - Unlimited users
    - Unlimited storage
    - Dedicated account manager
    - Premium SLA (see Enterprise_SLA.pdf)
    
    All plans include 2-week free trial.
    """,
    
    "refund_policy.pdf": """
    REFUND POLICY
    
    We offer a 30-day money-back guarantee.
    
    If you cancel within 30 days:
    1. Contact support@northwind.com
    2. Provide reason for cancellation
    3. Full refund processed within 5 business days
    
    Refunds are issued to original payment method.
    
    Exceptions:
    - Annual plans: 10% cancellation fee
    - Enterprise plans: Contact sales for cancellation terms
    """,
    
    "password_reset.pdf": """
    HOW TO RESET YOUR PASSWORD
    
    Option 1: Forgot password link
    1. Go to northwind.com/login
    2. Click "Forgot Password?"
    3. Enter email address
    4. Click link in reset email
    5. Enter new password
    
    Option 2: Ask your admin
    - If you're in a team workspace, ask your workspace admin to reset
    - Admin goes to Settings > Users > [Your Name] > Reset Password
    
    Option 3: Contact support
    - Email support@northwind.com
    - Verify your identity
    - We'll send reset link
    
    Password requirements: 8+ chars, 1 uppercase, 1 number
    """,
    
    "integrations.pdf": """
    NORTHWIND INTEGRATIONS
    
    Official Integrations:
    - Slack: Post updates to Slack channels
    - Zapier: Connect to 5000+ apps
    - Microsoft Teams: Share dashboards
    - Salesforce: Sync customer data
    - HubSpot: Manage leads
    
    Coming soon:
    - Google Workspace
    - Jira Cloud
    - Monday.com
    
    API: Developers can build custom integrations.
    Docs: api.northwind.com/docs
    """,
    
    "changelog_v2.3.pdf": """
    CHANGELOG - VERSION 2.3 (Released June 2024)
    
    New Features:
    - Dark mode (finally!)
    - Advanced filtering on dashboards
    - Bulk import from CSV
    
    Bugs Fixed:
    - Fixed export to PDF crashing
    - Fixed timeout on large datasets
    - Fixed mobile navigation
    
    Performance:
    - 30% faster on large workspaces
    - Reduced API latency by 50%
    
    Breaking Changes:
    - Deprecated /v1/users API (use /v2/users)
    - Custom field names now max 50 chars (was 100)
    """,
    
    "enterprise_onboarding.pdf": """
    ENTERPRISE ONBOARDING GUIDE
    
    Welcome! We'll get you up and running in 2 weeks.
    
    Week 1:
    - Day 1-2: Kickoff call + requirements
    - Day 3-4: Data migration planning
    - Day 5: Testing & training
    
    Week 2:
    - Day 6-7: Data import
    - Day 8-9: Custom setup (workflows, fields)
    - Day 10: Go-live + monitoring
    
    Dedicated Account Manager: [name] at am@northwind.com
    
    Success Metrics: By month 2, measure:
    - Adoption rate (% users active)
    - Time saved vs. old system
    - Error rate reduction
    """,
    
    "billing_faq.pdf": """
    BILLING FAQ
    
    Q: When am I billed?
    A: Monthly on your billing anniversary. First charge: immediately upon signup.
    
    Q: Can I change my plan mid-cycle?
    A: Yes. Upgrades/downgrades take effect next billing cycle. We'll prorate charges.
    
    Q: What payment methods do you accept?
    A: Credit cards (Visa, Mastercard, Amex), ACH transfers, wire transfer.
    
    Q: Can I get an invoice?
    A: Yes. Invoices emailed monthly. You can also download from Settings > Billing.
    
    Q: What's your refund policy?
    A: 30-day money-back guarantee (see refund_policy.pdf).
    
    Q: Do you offer discounts for annual commitment?
    A: Yes, 20% off annual plans.
    """,
}

# Test questions (real support scenarios)
TEST_QUESTIONS = [
    TestQuestion(
        question_id=1,
        question="What's our SLA for Enterprise customers?",
        correct_source="Enterprise_SLA.pdf"
    ),
    TestQuestion(
        question_id=2,
        question="How much does the Professional plan cost?",
        correct_source="pricing.pdf"
    ),
    TestQuestion(
        question_id=3,
        question="Can I get my money back if I change my mind?",
        correct_source="refund_policy.pdf"
    ),
    TestQuestion(
        question_id=4,
        question="How do I reset my password?",
        correct_source="password_reset.pdf"
    ),
    TestQuestion(
        question_id=5,
        question="Can we integrate with Slack?",
        correct_source="integrations.pdf"
    ),
    TestQuestion(
        question_id=6,
        question="What's new in version 2.3?",
        correct_source="changelog_v2.3.pdf"
    ),
    TestQuestion(
        question_id=7,
        question="How long does Enterprise onboarding take?",
        correct_source="enterprise_onboarding.pdf"
    ),
    TestQuestion(
        question_id=8,
        question="How do I get an invoice?",
        correct_source="billing_faq.pdf"
    ),
    TestQuestion(
        question_id=9,
        question="Is there a free trial?",
        correct_source="pricing.pdf"
    ),
    TestQuestion(
        question_id=10,
        question="What's the first response time for P2 issues?",
        correct_source="Enterprise_SLA.pdf"
    ),
]


# ============================================================================
# CORE RETRIEVAL LOGIC
# ============================================================================

class RetrieverSpike:
    """Test harness for retrieval"""
    
    def __init__(self):
        """Initialize Chroma + sentence-transformers embedding model.
        
        No API key required for the spike!
        Embeddings run locally via sentence-transformers.
        Groq API key is only needed in Phase 1 (copilot_mvp.py) for LLM generation.
        """
        embed_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        print(f"  Loading embedding model: {embed_model_name} (first run downloads ~90MB)")
        self.embed_model = SentenceTransformer(embed_model_name)
        
        # Chroma in-memory client (chromadb 0.4+ API)
        self.chroma = chromadb.EphemeralClient()
        
        self.collection = None
    
    def ingest_docs(self, docs: dict) -> int:
        """
        Ingest docs into Chroma.
        
        Args:
            docs: {filename: text_content}
        
        Returns:
            Total number of chunks created
        """
        print("\n📥 INGESTION PHASE")
        print("-" * 50)
        
        self.collection = self.chroma.get_or_create_collection(
            name="northwind_support",
            metadata={"hnsw:space": "cosine"}
        )
        
        chunk_id = 0
        total_chunks = 0
        
        for source_name, text_content in docs.items():
            print(f"Ingesting: {source_name}")
            
            # Simple chunking: split by sentence, then group into ~200-word chunks
            sentences = text_content.split(".")
            chunks_for_doc = []
            current_chunk = []
            
            for sentence in sentences:
                current_chunk.append(sentence)
                if len(" ".join(current_chunk).split()) >= 150:
                    chunks_for_doc.append(". ".join(current_chunk) + ".")
                    current_chunk = []
            
            if current_chunk:
                chunks_for_doc.append(". ".join(current_chunk))
            
            # Embed and store chunks (batch for speed)
            valid_chunks = [
                (i, chunk_text.strip())
                for i, chunk_text in enumerate(chunks_for_doc)
                if len(chunk_text.strip()) >= 10
            ]
            
            if valid_chunks:
                chunk_indices, chunk_texts = zip(*valid_chunks)
                # Batch embed with sentence-transformers (fast, local, free)
                embeddings = self.embed_model.encode(
                    list(chunk_texts), show_progress_bar=False
                ).tolist()
                
                # Store in Chroma
                self.collection.add(
                    ids=[f"{source_name}_chunk_{i}" for i in chunk_indices],
                    embeddings=embeddings,
                    documents=list(chunk_texts),
                    metadatas=[{
                        "source": source_name,
                        "chunk_index": i
                    } for i in chunk_indices]
                )
                
                chunk_id += len(valid_chunks)
                total_chunks += len(valid_chunks)
            
            print(f"  ✓ {len(chunks_for_doc)} chunks created")
        
        print(f"\n✅ Total chunks ingested: {total_chunks}")
        return total_chunks
    
    def retrieve(self, question: str, top_k: int = 3) -> Tuple[List[str], List[float]]:
        """
        Retrieve top-k chunks for a question.
        
        Args:
            question: Natural language question
            top_k: Number of results to return
        
        Returns:
            (sources, scores) - lists of source filenames and similarity scores
        """
        # Embed question locally using sentence-transformers (no API call)
        question_embedding = self.embed_model.encode(question).tolist()
        
        # Query Chroma
        results = self.collection.query(
            query_embeddings=[question_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        # Extract sources and convert distances to similarity scores
        sources = []
        scores = []
        
        for metadata, distance in zip(results["metadatas"][0], results["distances"][0]):
            source = metadata["source"]
            # Chroma returns distance; convert to similarity (cosine similarity = 1 - distance)
            similarity = 1 - distance
            sources.append(source)
            scores.append(similarity)
        
        return sources, scores
    
    def run_spike(self, questions: List[TestQuestion]) -> List[RetrievalTestResult]:
        """
        Run spike: retrieve for all test questions.
        
        Returns:
            List of RetrievalTestResult
        """
        print("\n🧪 RETRIEVAL SPIKE")
        print("-" * 50)
        
        results = []
        
        for q in questions:
            print(f"\nQ{q.question_id}: {q.question}")
            print(f"  Expected source: {q.correct_source}")
            
            sources, scores = self.retrieve(q.question, top_k=3)
            
            hit = q.correct_source in sources
            hit_str = "✓ HIT" if hit else "✗ MISS"
            
            print(f"  Retrieved: {sources}")
            print(f"  Scores: {[f'{s:.2f}' for s in scores]}")
            print(f"  Result: {hit_str}")
            
            results.append(
                RetrievalTestResult(
                    question_id=q.question_id,
                    question=q.question,
                    correct_source=q.correct_source,
                    retrieved_sources=sources,
                    retrieved_scores=scores,
                    hit=hit,
                    top_score=scores[0] if scores else 0.0
                )
            )
        
        return results


# ============================================================================
# EVALUATION & REPORTING
# ============================================================================

def evaluate_results(results: List[RetrievalTestResult]) -> dict:
    """Calculate metrics from spike results"""
    
    total = len(results)
    hits = sum(1 for r in results if r.hit)
    hit_rate = (hits / total) * 100 if total > 0 else 0.0
    
    avg_top_score = sum(r.top_score for r in results) / total if total > 0 else 0.0
    
    return {
        "total_questions": total,
        "total_hits": hits,
        "hit_rate_percent": round(hit_rate, 1),
        "avg_top_score": round(avg_top_score, 3),
    }


def print_results_table(results: List[RetrievalTestResult]):
    """Pretty-print results as table"""
    
    print("\n📊 RESULTS TABLE")
    print("-" * 120)
    print(f"{'Q':<3} {'Question':<40} {'Expected':<25} {'Top Retrieved':<25} {'Hit':<5}")
    print("-" * 120)
    
    for r in results:
        expected = r.correct_source[:24]
        top_retrieved = r.retrieved_sources[0] if r.retrieved_sources else "N/A"
        top_retrieved = top_retrieved[:24]
        hit_str = "✓" if r.hit else "✗"
        
        question = r.question[:39]
        
        print(f"{r.question_id:<3} {question:<40} {expected:<25} {top_retrieved:<25} {hit_str:<5}")
    
    print("-" * 120)


def save_results(results: List[RetrievalTestResult], metrics: dict, filename: str = "spike_results.json"):
    """Save results to JSON"""
    
    output = {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics,
        "results": [r.model_dump() for r in results]
    }
    
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Results saved to {filename}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run the spike"""
    
    print("\n" + "="*60)
    print("🚀 NORTHWIND SUPPORT COPILOT")
    print("   De-risk Spike: Retrieval Hit Rate Test")
    print("="*60)
    
    try:
        # Initialize
        print("\n🔧 Initializing...")
        spike = RetrieverSpike()
        
        # Ingest docs
        num_chunks = spike.ingest_docs(SAMPLE_DOCS)
        
        # Run spike
        results = spike.run_spike(TEST_QUESTIONS)
        
        # Evaluate
        metrics = evaluate_results(results)
        
        # Report
        print_results_table(results)
        
        print("\n📈 SUMMARY METRICS")
        print("-" * 50)
        print(f"Total questions:  {metrics['total_questions']}")
        print(f"Total hits:       {metrics['total_hits']}")
        print(f"Hit rate:         {metrics['hit_rate_percent']}%")
        print(f"Avg top score:    {metrics['avg_top_score']}")
        
        # Decision gate
        hit_rate = metrics['hit_rate_percent']
        print("\n🎯 DECISION GATE")
        print("-" * 50)
        if hit_rate >= 90:
            print(f"✅ PASS ({hit_rate}% >= 90%)")
            print("   Confidence: VERY HIGH")
            print("   Recommendation: PROCEED to Phase 1 MVP")
        elif hit_rate >= 70:
            print(f"⚠️  CAUTION ({hit_rate}% in range 70-90%)")
            print("   Confidence: MEDIUM")
            print("   Recommendation: Proceed with retrieval tuning in Phase 2")
        else:
            print(f"❌ BLOCKER ({hit_rate}% < 70%)")
            print("   Confidence: LOW")
            print("   Recommendation: Return to design; reconsider chunking/embedding")
        
        # Save
        save_results(results, metrics)
        
    except KeyError as e:
        print(f"\n❌ ERROR: Missing configuration: {e}")
        print("\nMake sure:")
        print("  1. All required packages installed: pip install -r requirements.txt")
        print("  2. NOTE: The spike uses LOCAL embeddings - no API key needed!")
        print("     (GROQ_API_KEY is only needed in Phase 1: copilot_mvp.py)")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
