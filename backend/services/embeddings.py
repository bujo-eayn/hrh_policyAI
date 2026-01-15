"""
Embeddings service for generating and managing vector embeddings.
Uses Ollama's mxbai-embed-large model for 1024-dimensional embeddings.
"""
import asyncio
import re
from typing import List, Dict, Any
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
import tiktoken

from backend.services.ollama_client import ollama_client
from backend.database.models import DocumentChunk
from backend.config import settings


class EmbeddingService:
    """Service for generating and managing embeddings."""

    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
        #mxbai-embed-large has a context windoow of 512 tokens
        self.max_context_tokens = 512
        self.safe_token_limit = int(self.max_context_tokens * 0.5)  # 256 tokens

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
            "COC": "Council of Optometrists",
            "PPB": "Pharmacy and Poisons Board",
            "PHOTC": "Physical Therapists and Occupational Therapists Council",
        }
    
    def normalize_query(self, text: str) -> str:
        """
        Normalize query by expanding domain acronyms.
        This improves matching with document embeddings.
        
        Args:
            text: Query text to normalize
            
        Returns:
            Normalized query with expanded acronyms
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
                # Fallback to conservative character-based estimate
                return int(len(text) / 3.5)  # More conservative: 1 token ≈ 3.5 characters
        else:
            # Fallback: very conservative estimate - 1 token ≈ 3.5 characters
            # This errs on the side of underestimating text length
            return int(len(text) / 3.5)

    def _split_text_by_tokens(self, text: str, max_tokens: int) -> List[str]:
        """
        Split text into chunks that don't exceed max_tokens.
        
        Args:
            text: Text to split
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List of text chunks within token limits
        """
        chunks = []
        
        if self.tokenizer:
            # Token-based splitting
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
                # Fall through to character-based splitting
        
        # Character-based fallback (very conservative - 1 token ≈ 3.5 characters)
        char_limit = int(max_tokens * 3.5)
        
        for i in range(0, len(text), char_limit):
            chunk = text[i:i + char_limit].strip()
            if chunk:
                chunks.append(chunk)
        
        return chunks

    def _validate_and_truncate_text(self, text: str, max_chars: int = 1200) -> str:
        """
        Validate text length and truncate if necessary.
        This is a safety net to ensure text never exceeds embedding model limits.
        
        Args:
            text: Text to validate
            max_chars: Maximum allowed characters (conservative for 512-token limit)
            
        Returns:
            Text, possibly truncated to safe length
        """
        if len(text) <= max_chars:
            return text
        
        # Truncate and try to break at a sentence boundary
        truncated = text[:max_chars]
        
        # Try to break at last period/newline
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')
        break_point = max(last_period, last_newline)
        
        if break_point > max_chars * 0.8:  # Only if break point is reasonably close
            truncated = text[:break_point + 1]
        
        return truncated.strip()

    async def generate_embedding(self, text: str, retry_count: int = 0, max_retries: int = 3) -> List[float]:
        """
        Generate embedding for a single text, handling long texts by splitting.

        Args:
            text: Text to embed
            retry_count: Internal counter for retry attempts
            max_retries: Maximum number of retry attempts with more aggressive chunking

        Returns:
            Embedding vector as list of floats
        
        Raises:
            ValueError: If text is empty
        """

        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # First, validate and possibly truncate text at Ollama client level (1536 chars = 512 tokens * 3)
        text = self._validate_and_truncate_text(text, max_chars=1200)
        
        # Hard limit: split aggressively if text exceeds 900 characters (very conservative)
        if len(text) > 900:
            print(f"Text exceeds 900 character hard limit ({len(text)} chars). Splitting aggressively...")
            # Split at hard character boundaries
            char_limit = 600  # Fallback conservative limit
            chunks = []
            for i in range(0, len(text), char_limit):
                chunk = text[i:i + char_limit].strip()
                if chunk:
                    chunks.append(chunk)
            
            embeddings = []
            for i, chunk in enumerate(chunks):
                try:
                    chunk_embedding = await ollama_client.embed(chunk)
                    embeddings.append(chunk_embedding)
                except Exception as e:
                    print(f"Error embedding chunk {i+1}/{len(chunks)} (hard limit split): {e}")
                    raise
            
            if embeddings:
                avg_embedding = np.mean(embeddings, axis=0).tolist()
                return avg_embedding
            else:
                raise ValueError("Failed to generate any embeddings for text")

        # Check if text exceeds safe token limit
        token_count = self._count_tokens(text)
        
        # Calculate chunk size with retry strategy (get more aggressive on retries)
        chunk_size = self.safe_token_limit
        if retry_count > 0:
            # On retry, use more conservative limits
            chunk_size = int(self.safe_token_limit * (0.6 ** retry_count))
            print(f"Retry attempt {retry_count}: Using chunk size ({chunk_size} tokens)")
        
        if token_count <= chunk_size:
            # Text is small enough to embed directly
            try:
                print(f"Embedding text: {len(text)} chars, {token_count} tokens")
                embedding = await ollama_client.embed(text)
                return embedding
            except Exception as e:
                # If embedding fails and we haven't retried yet, try with more aggressive chunking
                if retry_count < max_retries:
                    print(f"Embedding failed ({str(e)}), retrying with smaller chunks...")
                    return await self.generate_embedding(text, retry_count + 1, max_retries)
                else:
                    raise
        else:
            # Text is too long - split and average embeddings
            print(f"Text exceeds token limit ({token_count} tokens > {chunk_size} token limit). "
                  f"Splitting into chunks for embedding...")
            
            chunks = self._split_text_by_tokens(text, chunk_size)
            print(f"Split into {len(chunks)} chunks")
            embeddings = []
            
            for i, chunk in enumerate(chunks):
                try:
                    print(f"Embedding chunk {i+1}/{len(chunks)}: {len(chunk)} chars")
                    chunk_embedding = await ollama_client.embed(chunk)
                    embeddings.append(chunk_embedding)
                except Exception as e:
                    print(f"Error embedding chunk {i+1}/{len(chunks)}: {e}")
                    # If a chunk fails and we haven't retried, try with smaller chunks
                    if retry_count < max_retries:
                        print(f"Chunk embedding failed, retrying entire text with smaller chunks...")
                        return await self.generate_embedding(text, retry_count + 1, max_retries)
                    else:
                        raise
            
            # Average the chunk embeddings
            if embeddings:
                avg_embedding = np.mean(embeddings, axis=0).tolist()
                return avg_embedding
            else:
                raise ValueError("Failed to generate any embeddings for text")

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        embeddings = await asyncio.gather(
            *(self.generate_embedding(text) for text in texts)
        )
        return embeddings

    def normalize_embedding(self, embedding: List[float]) -> List[float]:
        """
        Normalize embedding vector to unit length.
        Useful for cosine similarity calculations.

        Args:
            embedding: Embedding vector

        Returns:
            Normalized embedding vector
        """
        arr = np.array(embedding)
        norm = np.linalg.norm(arr)
        if norm == 0:
            return embedding
        return (arr / norm).tolist()

    async def store_chunk_embedding(
        self,
        db: Session,
        chunk_id: str,
        embedding: List[float]
    ) -> bool:
        """
        Store embedding for a document chunk in database.

        Args:
            db: Database session
            chunk_id: UUID of the document chunk
            embedding: Embedding vector to store

        Returns:
            True if successful, False otherwise
        """
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
        regulatory_body: str = None,
        similarity_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search to find most relevant document chunks.

        Args:
            db: Database session
            query_embedding: Query embedding vector
            top_k: Number of results to return
            regulatory_body: Optional filter by regulatory body
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of dicts with chunk data and similarity scores
        """
        try:
            threshold = similarity_threshold or settings.SIMILARITY_THRESHOLD
            print(f"Similarity search: threshold={threshold}, top_k={top_k}, regulatory_body={regulatory_body}")

            # Build query with pgvector cosine similarity
            # Convert embedding list to string format for pgvector: [val1,val2,...,valn]
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            query = """
                SELECT
                    dc.id,
                    dc.document_id,
                    dc.content,
                    dc.chunk_index,
                    dc.metadata,
                    d.title as document_title,
                    d.regulatory_body,
                    1 - (dc.embedding <=> cast(:query_embedding::vector)) as similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.embedding IS NOT NULL
            """

            # Add regulatory body filter if specified
            params = {"query_embedding": embedding_str, "top_k": top_k}
            if regulatory_body:
                query += " AND d.regulatory_body = :regulatory_body"
                params["regulatory_body"] = regulatory_body

            # First, get total count of available chunks for debugging
            count_query = "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
            count_result = db.execute(text(count_query))
            total_chunks = count_result.scalar()
            print(f"Total chunks with embeddings in database: {total_chunks}")

            # Order by similarity and limit (NO threshold filter - get best matches regardless)
            query += " ORDER BY similarity DESC LIMIT :top_k"

            result = db.execute(text(query), params)
            rows = result.fetchall()

            print(f"Top {len(rows)} similar chunks (before any threshold filtering):")

            # Convert to list of dicts
            results = []
            for row in rows:
                similarity_score = float(row[7])
                print(f"  Match: {row[5]} (similarity: {similarity_score:.3f})")
                results.append({
                    "chunk_id": str(row[0]),
                    "document_id": str(row[1]),
                    "content": row[2],
                    "chunk_index": row[3],
                    "metadata": row[4],
                    "document_title": row[5],
                    "regulatory_body": row[6],
                    "similarity_score": float(row[7])
                })

            return results

        except Exception as e:
            print(f"Similarity search error: {e}")
            return []

    async def create_ivfflat_index(self, db: Session, lists: int = 100) -> bool:
        """
        Create IVFFlat index for faster similarity search.
        Should be called after documents are ingested.

        Args:
            db: Database session
            lists: Number of lists for IVFFlat (typically sqrt(total_rows))

        Returns:
            True if successful, False otherwise
        """
        try:
            # Drop existing index if present
            db.execute(text("DROP INDEX IF EXISTS idx_document_chunks_embedding"))

            # Create new IVFFlat index
            create_index_query = f"""
                CREATE INDEX idx_document_chunks_embedding
                ON document_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """
            db.execute(text(create_index_query))
            db.commit()

            print(f"IVFFlat index created with {lists} lists")
            return True

        except Exception as e:
            db.rollback()
            print(f"Error creating IVFFlat index: {e}")
            return False


# Global embedding service instance
embedding_service = EmbeddingService()
