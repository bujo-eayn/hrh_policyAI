"""
RAG (Retrieval-Augmented Generation) pipeline for policy Q&A.
Orchestrates retrieval, context assembly, and response generation.
"""
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text  # <--- Added this import

from backend.services.embeddings import embedding_service
from backend.services.ollama_client import ollama_client
from backend.config import settings


class RAGPipeline:
    """RAG pipeline for policy document question answering."""

    def __init__(self):
        self.default_top_k = settings.DEFAULT_TOP_K

    async def query(
        self,
        db: Session,
        query: str,
        regulatory_body: Optional[str] = None,
        top_k: int = None,
        include_sources: bool = True
    ) -> Dict[str, Any]:
        """
        Execute RAG pipeline for a query.
        """
        start_time = time.time()

        if top_k is None:
            top_k = self.default_top_k
        
        print(f"\n{'='*60}")
        print(f"RAG Query: '{query}'")
        print(f"Regulatory Body Filter: {regulatory_body}")
        print(f"{'='*60}")

        try:
            # Normalize query by expanding acronyms for better matching
            normalized_query = embedding_service.normalize_query(query)
            if normalized_query != query:
                print(f"Normalized query: '{normalized_query}'")

            # Step 1: Generate query embedding using normalized query
            # (This will use the new Nomic model if .env is set correctly)
            query_embedding = await embedding_service.generate_embedding(normalized_query)
            print(f"Query embedding generated (768 dimensions)")

            # Step 2: Retrieve relevant chunks (DIRECT SQL EXECUTION)
            # We execute the SQL here to ensure parameters are passed correctly.
            
            sql = text("""
                SELECT 
                    dc.content, 
                    d.title, 
                    d.regulatory_body,
                    dc.document_id,
                    dc.chunk_index,
                    1 - (dc.embedding <=> cast(:query_embedding as vector)) as similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE (:regulatory_body IS NULL OR d.regulatory_body = :regulatory_body)
                ORDER BY similarity DESC
                LIMIT :top_k
            """)

            # Convert embedding list to string for SQL and execute
            result_proxy = db.execute(sql, {
                "query_embedding": str(query_embedding),
                "regulatory_body": regulatory_body,
                "top_k": top_k
            })
            
            raw_results = result_proxy.fetchall()
            
            # Convert raw SQL results to the list-of-dicts format expected by the pipeline
            retrieved_chunks = []
            for row in raw_results:
                retrieved_chunks.append({
                    "content": row.content,
                    "document_title": row.title,
                    "regulatory_body": row.regulatory_body,
                    "document_id": row.document_id,
                    "chunk_index": row.chunk_index,
                    "similarity_score": row.similarity
                })

            print(f"Retrieved {len(retrieved_chunks)} relevant chunks")

            if not retrieved_chunks:
                print("WARNING: No chunks retrieved! Checking if documents exist...")
                return {
                    "query": query,
                    "answer": "I couldn't find any relevant information in the policy documents to answer your question. Please try rephrasing or ask about a different topic.",
                    "sources": [],
                    "regulatory_body_filter": regulatory_body,
                    "processing_time": time.time() - start_time,
                    "model_used": settings.OLLAMA_LLM_MODEL
                }

            # Step 3: Assemble context from retrieved chunks
            context = self._assemble_context(retrieved_chunks)

            # Step 4: Generate response using LLM
            answer = await self._generate_answer(query, context, regulatory_body)

            # Step 5: Prepare sources
            sources = []
            if include_sources:
                sources = [
                    {
                        "document_id": str(chunk["document_id"]),
                        "document_title": chunk["document_title"],
                        "regulatory_body": chunk["regulatory_body"],
                        "chunk_content": chunk["content"][:300] + "..." if len(chunk["content"]) > 300 else chunk["content"],
                        "similarity_score": float(chunk["similarity_score"]),
                        "chunk_index": chunk["chunk_index"]
                    }
                    for chunk in retrieved_chunks
                ]

            processing_time = time.time() - start_time

            return {
                "query": query,
                "answer": answer,
                "sources": sources,
                "regulatory_body_filter": regulatory_body,
                "processing_time": processing_time,
                "model_used": settings.OLLAMA_LLM_MODEL
            }

        except Exception as e:
            # Ensure session is cleaned up on error
            try:
                db.rollback()
            except Exception:
                pass
            print(f"Error in RAG query: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return error response instead of raising
            return {
                "query": query,
                "answer": f"Error processing your query: {str(e)}",
                "sources": [],
                "regulatory_body_filter": regulatory_body,
                "processing_time": time.time() - start_time,
                "model_used": settings.OLLAMA_LLM_MODEL
            }

    def _assemble_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Assemble context from retrieved chunks.
        """
        context_parts = []

        print(f"\nAssembling context from {len(chunks)} chunks:")

        for i, chunk in enumerate(chunks, 1):
            content_preview = chunk['content'][:100].replace('\n', ' ') + "..."
            print(f"  [{i}] {chunk['document_title']} (similarity: {chunk['similarity_score']:.3f}) - {content_preview}")
            
            context_part = f"""
                [Source {i}: {chunk['document_title']} - {chunk['regulatory_body']}]
                {chunk['content']}
                """
            context_parts.append(context_part.strip())

        context = "\n\n".join(context_parts)
        print(f"Total context size: {len(context)} characters\n")
        return context

    async def _generate_answer(
        self,
        query: str,
        context: str,
        regulatory_body: Optional[str] = None
    ) -> str:
        """
        Generate answer using LLM with retrieved context.
        """
        # Build system prompt
        system_prompt = """You are an expert assistant for Kenya's health workforce policy interpretation.
            You help healthcare professionals understand policies from regulatory bodies like KMPDB, NCK, COC, PPB, and PHOTC.

            Your role is to:
            1. Provide accurate, clear answers based on the provided policy documents
            2. Cite specific sources when making statements
            3. Explain complex policy language in simple terms
            4. Highlight important requirements, deadlines, or compliance issues
            5. If information is not in the provided context, clearly state that

            Always maintain a professional, helpful tone and prioritize accuracy over speculation."""

        if regulatory_body:
            system_prompt += f"\n\nThe user is specifically asking about {regulatory_body} policies."

        # Build user prompt with context
        user_prompt = f"""Based on the following policy document excerpts, please answer the question below.

            Policy Context:
            {context}

            Question: {query}

            Please provide a comprehensive answer based on the policy excerpts above. Include relevant citations and explain any technical terms."""

        # Generate response
        try:
            print(f"Generating answer with LLM (temperature: 0.3)...")
            answer = await ollama_client.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3  # Lower temperature for more factual responses
            )
            result = answer.strip()
            print(f"Answer generated ({len(result)} characters)\n")
            return result

        except Exception as e:
            return f"I encountered an error while generating the response: {str(e)}"

    async def compare_policies(
        self,
        db: Session,
        query: str,
        regulatory_bodies: List[str],
        top_k_per_body: int = 3
    ) -> Dict[str, Any]:
        """
        Compare policies across multiple regulatory bodies.
        """
        start_time = time.time()

        # Generate query embedding once
        query_embedding = await embedding_service.generate_embedding(query)

        # Retrieve chunks for each regulatory body
        all_chunks_by_body = {}
        for body in regulatory_bodies:
            # We use the same raw SQL logic here to be safe
            sql = text("""
                SELECT 
                    dc.content, 
                    d.title, 
                    d.regulatory_body,
                    dc.document_id,
                    dc.chunk_index,
                    1 - (dc.embedding <=> cast(:query_embedding as vector)) as similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.regulatory_body = :regulatory_body
                ORDER BY similarity DESC
                LIMIT :top_k
            """)

            result_proxy = db.execute(sql, {
                "query_embedding": str(query_embedding),
                "regulatory_body": body,
                "top_k": top_k_per_body
            })
            raw_results = result_proxy.fetchall()

            chunks = []
            for row in raw_results:
                chunks.append({
                    "content": row.content,
                    "document_title": row.title,
                    "regulatory_body": row.regulatory_body,
                    "document_id": row.document_id,
                    "chunk_index": row.chunk_index,
                    "similarity_score": row.similarity
                })
            
            all_chunks_by_body[body] = chunks

        # Assemble comparison context
        comparison_context = self._assemble_comparison_context(all_chunks_by_body)

        # Generate comparative analysis
        analysis = await self._generate_comparison_analysis(query, comparison_context, regulatory_bodies)

        processing_time = time.time() - start_time

        return {
            "query": query,
            "comparison": all_chunks_by_body,
            "analysis": analysis,
            "processing_time": processing_time
        }

    def _assemble_comparison_context(
        self,
        chunks_by_body: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Assemble context for policy comparison.
        """
        context_parts = []

        for body, chunks in chunks_by_body.items():
            if not chunks:
                context_parts.append(f"[{body}]\nNo relevant information found.\n")
                continue

            body_context = f"[{body}]\n"
            for chunk in chunks:
                body_context += f"- {chunk['document_title']}: {chunk['content'][:200]}...\n"

            context_parts.append(body_context)

        return "\n\n".join(context_parts)

    async def _generate_comparison_analysis(
        self,
        query: str,
        context: str,
        regulatory_bodies: List[str]
    ) -> str:
        """
        Generate comparative analysis across regulatory bodies.
        """
        system_prompt = """You are an expert in Kenya's health workforce policies.
            You specialize in comparing and contrasting policies across different regulatory bodies.

            Provide a clear, structured comparison that:
            1. Highlights similarities across regulatory bodies
            2. Points out key differences
            3. Notes any conflicting requirements
            4. Explains implications for healthcare professionals
            5. Provides actionable insights"""

        user_prompt = f"""Compare the policies of {', '.join(regulatory_bodies)} regarding the following question:

            Question: {query}

            Policy Information:
            {context}

            Provide a comprehensive comparison highlighting similarities, differences, and implications."""

        try:
            analysis = await ollama_client.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.4
            )
            return analysis.strip()

        except Exception as e:
            return f"Error generating comparison: {str(e)}"


# Global RAG pipeline instance
rag_pipeline = RAGPipeline()
