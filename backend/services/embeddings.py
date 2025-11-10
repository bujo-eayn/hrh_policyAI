"""
Embeddings service for generating and managing vector embeddings.
Uses Ollama's mxbai-embed-large model for 1024-dimensional embeddings.
"""
from typing import List, Dict, Any
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.services.ollama_client import ollama_client
from backend.database.models import DocumentChunk
from backend.config import settings


class EmbeddingService:
    """Service for generating and managing embeddings."""

    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        embedding = await ollama_client.embed(text)
        return embedding

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

        embeddings = await ollama_client.embed_batch(texts)
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

            # Build query with pgvector cosine similarity
            query = """
                SELECT
                    dc.id,
                    dc.document_id,
                    dc.content,
                    dc.chunk_index,
                    dc.metadata,
                    d.title as document_title,
                    d.regulatory_body,
                    1 - (dc.embedding <=> :query_embedding::vector) as similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.embedding IS NOT NULL
            """

            # Add regulatory body filter if specified
            params = {"query_embedding": query_embedding, "top_k": top_k}
            if regulatory_body:
                query += " AND d.regulatory_body = :regulatory_body"
                params["regulatory_body"] = regulatory_body

            # Add similarity threshold
            query += " AND (1 - (dc.embedding <=> :query_embedding::vector)) >= :threshold"
            params["threshold"] = threshold

            # Order by similarity and limit
            query += " ORDER BY similarity DESC LIMIT :top_k"

            result = db.execute(text(query), params)
            rows = result.fetchall()

            # Convert to list of dicts
            results = []
            for row in rows:
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
