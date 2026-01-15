"""
RAG (Retrieval-Augmented Generation) pipeline for policy Q&A.
Orchestrates retrieval, context assembly, and response generation.
"""
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

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

        Args:
            db: Database session
            query: User's question
            regulatory_body: Optional filter by regulatory body
            top_k: Number of documents to retrieve
            include_sources: Whether to include source documents

        Returns:
            Dictionary with answer and sources
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
            query_embedding = await embedding_service.generate_embedding(normalized_query)
            print(f"Query embedding generated (1024 dimensions)")

            # Step 2: Retrieve relevant chunks
            retrieved_chunks = await embedding_service.similarity_search(
                db=db,
                query_embedding=query_embedding,
                top_k=top_k,
                regulatory_body=regulatory_body
            )

            print(f"Retrieved {len(retrieved_chunks)} relevant chunks")

            if not retrieved_chunks:
                print("WARNING: No chunks retrieved! Checking if documents exist...")
                # Debug: count documents
                from backend.database.models import Document, DocumentChunk
                try:
                    doc_count = db.query(Document).count()
                    chunk_count = db.query(DocumentChunk).count()
                    chunk_with_embedding = db.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).count()
                    print(f"Database status: {doc_count} documents, {chunk_count} total chunks, {chunk_with_embedding} with embeddings")
                except Exception as db_error:
                    print(f"Error checking database status: {db_error}")
                
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
                        "document_id": chunk["document_id"],
                        "document_title": chunk["document_title"],
                        "regulatory_body": chunk["regulatory_body"],
                        "chunk_content": chunk["content"][:300] + "..." if len(chunk["content"]) > 300 else chunk["content"],
                        "similarity_score": chunk["similarity_score"],
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

        Args:
            chunks: List of retrieved chunks with metadata

        Returns:
            Formatted context string
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

        Args:
            query: User's question
            context: Retrieved context
            regulatory_body: Optional regulatory body filter

        Returns:
            Generated answer
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

        Args:
            db: Database session
            query: Question about policies
            regulatory_bodies: List of regulatory bodies to compare
            top_k_per_body: Number of documents per body

        Returns:
            Dictionary with comparison analysis
        """
        start_time = time.time()

        # Generate query embedding once
        query_embedding = await embedding_service.generate_embedding(query)

        # Retrieve chunks for each regulatory body
        all_chunks_by_body = {}
        for body in regulatory_bodies:
            chunks = await embedding_service.similarity_search(
                db=db,
                query_embedding=query_embedding,
                top_k=top_k_per_body,
                regulatory_body=body
            )
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

        Args:
            chunks_by_body: Dictionary mapping regulatory body to chunks

        Returns:
            Formatted comparison context
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

        Args:
            query: User's question
            context: Assembled context from multiple bodies
            regulatory_bodies: List of bodies being compared

        Returns:
            Comparative analysis
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
