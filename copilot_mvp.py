"""
Phase 1 MVP: Northwind Support Copilot
========================================

Full pipeline: question → semantic retrieval → Groq LLM → cited answer

Stack:
  Embeddings : sentence-transformers (local, free, no API key)
  Vector DB  : ChromaDB (in-memory)
  LLM        : Groq (llama3-8b-8192 by default - fast & free tier)

Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and add your GROQ_API_KEY
     Get a free key from: https://console.groq.com/keys
  3. python copilot_mvp.py

Run: python copilot_mvp.py
"""

import os
import sys
import json
import time
from typing import List, Tuple, Optional
from datetime import datetime

# Fix Windows cp1252 terminal encoding (allows emoji/unicode output)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================================
# DEPENDENCY CHECKS
# ============================================================================

try:
    import chromadb
except ImportError:
    print("ERROR: chromadb not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: sentence-transformers not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from groq import Groq
except ImportError:
    print("ERROR: groq not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from pydantic import BaseModel
except ImportError:
    print("ERROR: pydantic not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

import dotenv
dotenv.load_dotenv()

# Import data contracts
try:
    from data_contracts import (
        RetrievalQuery,
        LLMResponse,
        CopilotResponse,
        ConfidenceLevel,
        CopilotAction,
        ActionType,
    )
except ImportError:
    print("ERROR: data_contracts.py not found. Make sure it's in the same directory.")
    sys.exit(1)


# ============================================================================
# SAMPLE DOCS (same as retrieval_spike.py)
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


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are a helpful Northwind customer support expert.

RULES:
1. Answer ONLY using information from the provided documents.
2. Every factual claim MUST cite the source document name (e.g. [Enterprise_SLA.pdf]).
3. If the answer is not in the documents, say: "I don't have information on this. Please ask a human agent."
4. Be concise and direct. Customers want quick answers.
5. Never guess or invent information.

FORMAT:
- Give a clear, direct answer first.
- Then add citations.
- Keep responses under 150 words.
"""


# ============================================================================
# COPILOT MVP CLASS
# ============================================================================

class CopilotMVP:
    """
    Phase 1 MVP: Full retrieval + LLM pipeline.
    
    Uses:
    - sentence-transformers for local embeddings (no API key)
    - ChromaDB for vector storage and retrieval
    - Groq (LLaMA3) for LLM answer generation
    """

    def __init__(self):
        # Validate Groq API key
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key or self.groq_api_key.startswith("gsk_your"):
            raise ValueError(
                "GROQ_API_KEY not set or still placeholder.\n"
                "  1. Get a free key from: https://console.groq.com/keys\n"
                "  2. Add it to .env: GROQ_API_KEY=gsk_..."
            )

        self.groq_client = Groq(api_key=self.groq_api_key)
        self.llm_model = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "500"))
        self.top_k = int(os.getenv("RETRIEVAL_TOP_K", "3"))

        # Load sentence-transformers embedding model (local, no API)
        embed_model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        print(f"  Loading embedding model: {embed_model_name} (first run downloads ~90MB)...")
        self.embed_model = SentenceTransformer(embed_model_name)

        # ChromaDB in-memory vector store
        self.chroma = chromadb.EphemeralClient()
        self.collection = None

        print(f"  LLM: Groq / {self.llm_model}")
        print(f"  Embeddings: {embed_model_name} (local)")

    def ingest_docs(self, docs: dict) -> int:
        """
        Ingest documents into ChromaDB vector store.
        
        Args:
            docs: {filename: text_content}
        Returns:
            Total chunks indexed
        """
        print("\n📥 INGESTION PHASE")
        print("-" * 50)

        self.collection = self.chroma.get_or_create_collection(
            name="northwind_support",
            metadata={"hnsw:space": "cosine"}
        )

        total_chunks = 0

        for source_name, text_content in docs.items():
            print(f"  Ingesting: {source_name}")

            # Chunk by sentences, group into ~150-word chunks
            sentences = text_content.split(".")
            chunks = []
            current = []

            for sentence in sentences:
                current.append(sentence)
                if len(" ".join(current).split()) >= 150:
                    chunks.append(". ".join(current) + ".")
                    current = []
            if current:
                chunks.append(". ".join(current))

            # Filter out tiny chunks
            valid = [(i, c.strip()) for i, c in enumerate(chunks) if len(c.strip()) >= 10]
            if not valid:
                continue

            indices, texts = zip(*valid)

            # Batch embed (local, instant)
            embeddings = self.embed_model.encode(list(texts), show_progress_bar=False).tolist()

            self.collection.add(
                ids=[f"{source_name}_chunk_{i}" for i in indices],
                embeddings=embeddings,
                documents=list(texts),
                metadatas=[{"source": source_name, "chunk_index": i} for i in indices]
            )

            total_chunks += len(valid)
            print(f"    ✓ {len(valid)} chunks indexed")

        print(f"\n✅ Total chunks indexed: {total_chunks}")
        return total_chunks

    def retrieve(self, question: str) -> Tuple[List[str], List[str], List[float]]:
        """
        Retrieve top-k relevant chunks for a question.
        
        Returns:
            (sources, texts, scores)
        """
        question_embedding = self.embed_model.encode(question).tolist()

        results = self.collection.query(
            query_embeddings=[question_embedding],
            n_results=self.top_k,
            include=["documents", "metadatas", "distances"]
        )

        sources, texts, scores = [], [], []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            sources.append(meta["source"])
            texts.append(doc)
            scores.append(round(1 - dist, 3))  # Convert distance → similarity

        return sources, texts, scores

    def generate_answer(self, question: str, context: str, sources: List[str]) -> LLMResponse:
        """
        Generate a cited answer using Groq LLM.
        
        Args:
            question: The support agent's question
            context: Retrieved document chunks (formatted)
            sources: Source filenames for the context
        
        Returns:
            LLMResponse with answer, citations, confidence
        """
        user_message = f"""Question: {question}

Documents:
{context}

Answer (with citations):"""

        start = datetime.utcnow()

        response = self.groq_client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
        answer_text = response.choices[0].message.content

        # Extract which sources were cited in the answer
        cited = [s for s in sources if s in answer_text]
        if not cited:
            cited = sources[:1]  # Fallback: at least cite the top retrieved doc

        confidence = 0.9 if len(cited) >= 1 else 0.5
        contains_uncertainty = any(
            phrase in answer_text.lower()
            for phrase in ["i don't have", "i don't know", "not sure", "unclear", "[uncertain]"]
        )
        if contains_uncertainty:
            confidence = 0.4

        return LLMResponse(
            answer=answer_text,
            citations=cited,
            confidence=confidence,
            contains_uncertainty=contains_uncertainty,
            model_used=self.llm_model,
            generation_latency_ms=round(latency_ms, 1),
        )

    def answer(self, question: str, agent_id: Optional[str] = None) -> dict:
        """
        Full pipeline: question → retrieval → LLM → response.
        
        Args:
            question: Support agent's question
            agent_id: Optional agent identifier for logging
        
        Returns:
            dict with answer, citations, sources, timing, confidence
        """
        if self.collection is None:
            raise RuntimeError("Call ingest_docs() before answer()")

        total_start = datetime.utcnow()

        # STEP 1: Retrieve
        retrieval_start = datetime.utcnow()
        sources, texts, scores = self.retrieve(question)
        retrieval_ms = (datetime.utcnow() - retrieval_start).total_seconds() * 1000

        # STEP 2: Format context
        context_parts = []
        for src, txt, score in zip(sources, texts, scores):
            context_parts.append(f"[Source: {src} | Score: {score}]\n{txt.strip()}")
        context = "\n\n".join(context_parts)

        # STEP 3: Generate answer with Groq
        llm_response = self.generate_answer(question, context, sources)

        total_ms = (datetime.utcnow() - total_start).total_seconds() * 1000

        # STEP 4: Determine confidence level
        if llm_response.confidence >= 0.8:
            conf_level = ConfidenceLevel.HIGH
        elif llm_response.confidence >= 0.5:
            conf_level = ConfidenceLevel.MEDIUM
        else:
            conf_level = ConfidenceLevel.LOW

        return {
            "question": question,
            "answer": llm_response.answer,
            "citations": llm_response.citations,
            "sources_retrieved": sources,
            "retrieval_scores": scores,
            "confidence": conf_level.value,
            "confidence_score": round(llm_response.confidence, 2),
            "contains_uncertainty": llm_response.contains_uncertainty,
            "model": llm_response.model_used,
            "timing": {
                "retrieval_ms": round(retrieval_ms, 1),
                "generation_ms": llm_response.generation_latency_ms,
                "total_ms": round(total_ms, 1),
            },
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat(),
        }


# ============================================================================
# HALLUCINATION AUDIT HELPER
# ============================================================================

def run_hallucination_audit(copilot: CopilotMVP, questions: List[str]) -> None:
    """
    Run multiple questions and print answers for manual hallucination audit.
    Human auditor checks: Is every claim supported by the cited document?
    """
    print("\n" + "="*70)
    print("📋 HALLUCINATION AUDIT - Manual Review Required")
    print("   For each answer: Is every claim in the cited document? (Y/N)")
    print("="*70)

    results = []
    for i, question in enumerate(questions, 1):
        print(f"\n[Q{i}] {question}")
        print("-" * 60)

        response = copilot.answer(question)

        print(f"Answer  : {response['answer'][:300]}...")
        print(f"Citations: {response['citations']}")
        print(f"Confidence: {response['confidence']} ({response['confidence_score']})")
        print(f"Latency: {response['timing']['total_ms']:.0f}ms "
              f"(retrieval: {response['timing']['retrieval_ms']:.0f}ms | "
              f"LLM: {response['timing']['generation_ms']:.0f}ms)")
        print(f"\n⚠️  AUDIT: Hallucination? [ ] YES  [ ] NO")

        results.append(response)

    # Save audit results
    audit_file = "hallucination_audit_results.json"
    with open(audit_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Full results saved to: {audit_file}")
    print("   Review manually and fill in the hallucination column.")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*60)
    print("🚀 NORTHWIND SUPPORT COPILOT - Phase 1 MVP")
    print("   Powered by Groq (LLaMA3) + sentence-transformers")
    print("="*60)

    try:
        # Initialize
        print("\n🔧 Initializing...")
        copilot = CopilotMVP()

        # Ingest documents
        copilot.ingest_docs(SAMPLE_DOCS)

        # Demo: Run a few example questions
        DEMO_QUESTIONS = [
            "What's the SLA response time for P1 issues for Enterprise customers?",
            "How much does the Professional plan cost per month?",
            "Can I get a refund if I cancel after 15 days?",
            "How do I reset my password?",
            "Does Northwind integrate with Slack?",
        ]

        print("\n" + "="*60)
        print("💬 DEMO: Running sample support questions")
        print("="*60)

        for question in DEMO_QUESTIONS:
            print(f"\n❓ Question: {question}")
            response = copilot.answer(question)
            print(f"✅ Answer  : {response['answer']}")
            print(f"📎 Citations: {response['citations']}")
            print(f"⏱️  Latency : {response['timing']['total_ms']:.0f}ms total "
                  f"(LLM: {response['timing']['generation_ms']:.0f}ms)")
            print(f"🎯 Confidence: {response['confidence']} ({response['confidence_score']})")
            print("-" * 60)

        # Interactive mode
        print("\n" + "="*60)
        print("🎤 INTERACTIVE MODE - Type your questions (or 'quit' to exit)")
        print("="*60)

        while True:
            print()
            question = input("Your question: ").strip()
            if question.lower() in ("quit", "exit", "q"):
                print("\n👋 Goodbye!")
                break
            if not question:
                continue

            response = copilot.answer(question)
            print(f"\n✅ Answer: {response['answer']}")
            print(f"📎 Citations: {response['citations']}")
            print(f"⏱️  Latency: {response['timing']['total_ms']:.0f}ms")
            print(f"🎯 Confidence: {response['confidence']}")

    except ValueError as e:
        print(f"\n❌ CONFIGURATION ERROR:\n   {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
