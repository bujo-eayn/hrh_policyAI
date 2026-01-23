"""
Embeddings service for generating and managing vector embeddings.
Uses Ollama's nomic-embed-text model for 768-dimensional embeddings.
"""
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
import tiktoken

from backend.services.ollama_client import ollama_client
from backend.database.models import DocumentChunk
from backend.config import settings

# Configure logging
logger = logging.getLogger(__name__)

class EmbeddingService:
    """Service for generating and managing embeddings."""

    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
        # nomic-embed-text has a larger context, but we stick to safe limits
        self.max_context_tokens = 512
        self.safe_token_limit = settings.CHUNK_SIZE  # Use setting from .env (256)

        # Initialize tokenizer for accurate token counting
        self.tokenizer = None
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
            print(f"Tokenizer initialized successfully. Safe token limit: {self.safe_token_limit}")
        except Exception as e:
            print(f"Warning: Failed to initialize tiktoken tokenizer: {e}. Using conservative character-based estimation.")
            self.tokenizer = None
        
        # Domain-specific acronym expansion for better query matching
        self.acronym_expansions = {
            "HRH": "Human Resource for Health",
            "KMPDB": "Kenya Medical Practitioners and Dentists Board",
            "NCK": "Nursing Council of Kenya",
            "COC": "Clinical Officers Council",
            "PPB": "Pharmacy and Poisons Board",
            "PHOTC": "Physical Therapists and Occupational Therapists Council",
        }
    
    def normalize_query(self, text: str) -> str:
        """
        Normalize query by expanding domain acronyms.
        """
        normalized = text
        for acronym, expansion in self.acronym_expansions.items():
            # Replace acronym boundaries (case-insensitive)
            normalized = re.sub(r'\b' + acronym + r'\b', expansion, normalized, flags=re.IGNORECASE)
        return normalized

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as e:
                print(f"Error counting tokens with tiktoken: {e}. Using fallback estimation.")
                return int(len(text) / 3.5)
        else:
            return int(len(text) / 3.5)

    def _split_text_by_tokens(self, text: str, max_tokens: int) -> List[str]:
        """
        Split text into chunks that don't exceed max_tokens.
        """
        chunks = []
        
        if self.tokenizer:
            try:
                tokens = self.tokenizer.encode(text)
                for i in range(0, len(tokens), max_tokens):
                    chunk_tokens = tokens[i:i + max_tokens]
                    chunk_text = self.tokenizer.decode(chunk_tokens)
                    if chunk_text.strip():
                        chunks.append(chunk_text.strip())
                return chunks
            except Exception as e:
                print(f"Error during token-based splitting: {e}. Falling back to character-based splitting.")
        
        # Character-based fallback
        char_limit = int(max_tokens * 3.5)
        for i in range(0, len(text), char_limit):
            chunk = text[i:i + char_limit].strip()
            if chunk:
                chunks.append(chunk)
        return chunks

    def _validate_and_truncate_text(self, text: str, max_chars: int = 1200) -> str:
        """
        Validate text length and truncate if necessary.
        """
        if len(text) <= max_chars:
            return text
        
        truncated = text[:max_chars]
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')
        break_point = max(last_period, last_newline)
        
        if break_point > max_chars * 0.8:
            truncated = text[:break_point + 1]
        
        return truncated.strip()

    async def generate_embedding(self, text: str, retry_count: int = 0, max_retries: int = 3) -> List[float]:
        """
        Generate embedding for a single text, handling long texts by splitting.
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        text = self._validate_and_truncate_text(text, max_chars=1200)
        
        # Check token limit
        token_count = self._count_tokens(text)
        
        # Calculate chunk size with retry strategy
        chunk_size = self.safe_token_limit
        if retry_count > 0:
            chunk_size = int(self.safe_token_limit * (0.6 ** retry_count))
            print(f"Retry attempt {retry_count}: Using chunk size ({chunk_size} tokens)")
        
        if token_count <= chunk_size:
            try:
                # Direct embedding
                return await ollama_client.embed(text)
            except Exception as e:
                if retry_count < max_retries:
                    print(f"Embedding failed ({str(e)}), retrying with smaller chunks...")
                    return await self.generate_embedding(text, retry_count + 1, max_retries)
                raise
        else:
            # Text is too long - split and average embeddings
            print(f"Text exceeds limit ({token_count} > {chunk_size}). Splitting...")
            chunks = self._split_text_by_tokens(text, chunk_size)
            embeddings = []
            
            for i, chunk in enumerate(chunks):
                try:
                    chunk_embedding = await ollama_client.embed(chunk)
                    embeddings.append(chunk_embedding)
                except Exception as e:
                    print(f"Error embedding chunk {i+1}: {e}")
            
            if embeddings:
                return np.mean(embeddings, axis=0).tolist()
            else:
                raise ValueError("Failed to generate embeddings for text chunks")

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []
        return await asyncio.gather(*(self.generate_embedding(text) for text in texts))

    async def store_chunk_embedding(self, db: Session, chunk_id: str, embedding: List[float]) -> bool:
        """Store embedding for a document chunk in database."""
        try:
            chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if not chunk:
                return False
            chunk.embedding = embedding
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"Error storing embedding: {e}")
            return False

    async def similarity_search(
        self, 
        db: Session, 
        query_embedding: List[float], 
        top_k: int = 5, 
        regulatory_body: Optional[str] = None,
        similarity_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search to find most relevant document chunks.
        """
        try:
            threshold = similarity_threshold or settings.SIMILARITY_THRESHOLD
            print(f"Similarity search: threshold={threshold}, top_k={top_k}, regulatory_body={regulatory_body}")

            # Convert embedding list to string format for pgvector: [val1,val2,...,valn]
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # --- CRITICAL FIX: Correct SQL Syntax ---
            # 1. Use 'cast(:param as vector)' instead of '::vector'
            # 2. Add explicit 'ORDER BY' and 'LIMIT' in the SQL text
            
            sql = """
                SELECT 
                    dc.id,
                    dc.document_id,
                    dc.content,
                    dc.chunk_index,
                    dc.metadata,
                    d.title as document_title,
                    d.regulatory_body,
                    1 - (dc.embedding <=> cast(:query_embedding as vector)) as similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.embedding IS NOT NULL
            """

            params = {"query_embedding": embedding_str, "top_k": top_k}
            
            if regulatory_body:
                sql += " AND d.regulatory_body = :regulatory_body"
                params["regulatory_body"] = regulatory_body

            # Debug: Check total chunks (optional, wrapped safely)
            try:
                count_query = "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
                total_chunks = db.execute(text(count_query)).scalar()
                print(f"Total chunks with embeddings in database: {total_chunks}")
            except Exception as e:
                print(f"Debug count failed (ignoring): {e}")

            # Append ordering and limit
            sql += " ORDER BY similarity DESC LIMIT :top_k"

            # Execute
            result = db.execute(text(sql), params)
            rows = result.fetchall()

            print(f"Top {len(rows)} similar chunks (before any threshold filtering):")

            results = []
            for row in rows:
                similarity_score = float(row.similarity)
                # print(f"  Match: {row.document_title} (similarity: {similarity_score:.3f})")
                
                results.append({
                    "chunk_id": str(row.id),
                    "document_id": str(row.document_id),
                    "content": row.content,
                    "chunk_index": row.chunk_index,
                    "metadata": row.metadata,
                    "document_title": row.document_title,
                    "regulatory_body": row.regulatory_body,
                    "similarity_score": similarity_score
                })

            return results

        except Exception as e:
            print(f"Similarity search error: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def create_ivfflat_index(self, db: Session, lists: int = 100) -> bool:
        """Create IVFFlat index for faster similarity search."""
        try:
            db.execute(text("DROP INDEX IF EXISTS idx_document_chunks_embedding"))
            create_index_query = f"""
                CREATE INDEX idx_document_chunks_embedding 
                ON document_chunks 
                USING ivfflat (embedding vector_cosine_ops) 
                WITH (lists = {lists})
            """
            db.execute(text(create_index_query))
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"Error creating IVFFlat index: {e}")
            return False

# Global embedding service instance
embedding_service = EmbeddingService()