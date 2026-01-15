"""
Ollama client for local LLM and embedding model interaction.
Connects to local Ollama instance for gemma3 and mxbai-embed-large models.
"""
import httpx
import asyncio
from typing import List, Dict, Any, Optional, AsyncIterator
import json

from backend.config import settings


class OllamaClient:
    """Client for interacting with local Ollama instance."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.llm_model = settings.OLLAMA_LLM_MODEL
        self.embedding_model = settings.OLLAMA_EMBEDDING_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    async def check_connection(self) -> bool:
        """
        Check if Ollama service is running and accessible.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                return response.status_code == 200
        except Exception as e:
            print(f"Ollama connection failed: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str:
        """
        Generate text using the LLM model.

        Args:
            prompt: User prompt/question
            system: Optional system message for context
            temperature: Sampling temperature (0.0-1.0)
            stream: Whether to stream the response

        Returns:
            Generated text response

        Raises:
            Exception: If generation fails
        """
        try:
            payload = {
                "model": self.llm_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }

            if system:
                payload["system"] = system

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")

        except httpx.TimeoutException:
            raise Exception("Ollama request timed out. The model might be loading.")
        except httpx.HTTPError as e:
            raise Exception(f"Ollama HTTP error: {str(e)}")
        except Exception as e:
            raise Exception(f"Ollama generation failed: {str(e)}")

    async def generate_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """
        Generate text using the LLM model with streaming.

        Args:
            prompt: User prompt/question
            system: Optional system message for context
            temperature: Sampling temperature (0.0-1.0)

        Yields:
            Generated text chunks

        Raises:
            Exception: If generation fails
        """
        try:
            payload = {
                "model": self.llm_model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": temperature
                }
            }

            if system:
                payload["system"] = system

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                chunk = json.loads(line)
                                if "response" in chunk:
                                    yield chunk["response"]
                            except json.JSONDecodeError:
                                continue

        except Exception as e:
            raise Exception(f"Ollama streaming generation failed: {str(e)}")

    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using mxbai-embed-large.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding (1024 dimensions)

        Raises:
            Exception: If embedding generation fails or text is too long
        """
        # Pre-validation: mxbai-embed-large has 512 token limit
        # Use extremely conservative character limit (1 token ≈ 3 chars to be safe)
        max_safe_chars = 512 * 3  # 1536 characters max
        
        if len(text) > max_safe_chars:
            raise ValueError(
                f"Text too long for embedding model: {len(text)} chars > {max_safe_chars} chars "
                f"(safe limit for mxbai-embed-large). This should have been caught earlier in the pipeline."
            )
        
        try:
            payload = {
                "model": self.embedding_model,
                "prompt": text
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                embedding = result.get("embedding", [])

                # Verify embedding dimension
                if len(embedding) != settings.EMBEDDING_DIMENSION:
                    raise Exception(
                        f"Expected {settings.EMBEDDING_DIMENSION} dimensions, "
                        f"got {len(embedding)}"
                    )

                return embedding

        except httpx.TimeoutException:
            raise Exception("Ollama embedding request timed out.")
        except httpx.HTTPError as e:
            raise Exception(f"Ollama HTTP error: {str(e)}")
        except Exception as e:
            raise Exception(f"Ollama embedding failed: {str(e)}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Raises:
            Exception: If any embedding generation fails
        """
        embeddings = []
        for text in texts:
            embedding = await self.embed(text)
            embeddings.append(embedding)
        return embeddings

    async def check_model_exists(self, model_name: str) -> bool:
        """
        Check if a specific model is available in Ollama.

        Args:
            model_name: Name of the model to check

        Returns:
            True if model exists, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return any(model["name"] == model_name for model in models)
        except Exception:
            pass
        return False

    async def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama library.

        Args:
            model_name: Name of the model to pull

        Returns:
            True if successful, False otherwise
        """
        try:
            payload = {"name": model_name}

            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json=payload
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Failed to pull model {model_name}: {e}")
            return False


# Global Ollama client instance
ollama_client = OllamaClient()


# ============================================================================
# Utility Functions
# ============================================================================

async def ensure_models_available() -> Dict[str, bool]:
    """
    Check if required models are available and pull them if needed.

    Returns:
        Dictionary with model availability status
    """
    status = {}

    # Check LLM model
    llm_exists = await ollama_client.check_model_exists(settings.OLLAMA_LLM_MODEL)
    if not llm_exists:
        print(f"Pulling LLM model: {settings.OLLAMA_LLM_MODEL}")
        llm_exists = await ollama_client.pull_model(settings.OLLAMA_LLM_MODEL)
    status["llm_model"] = llm_exists

    # Check embedding model
    embed_exists = await ollama_client.check_model_exists(settings.OLLAMA_EMBEDDING_MODEL)
    if not embed_exists:
        print(f"Pulling embedding model: {settings.OLLAMA_EMBEDDING_MODEL}")
        embed_exists = await ollama_client.pull_model(settings.OLLAMA_EMBEDDING_MODEL)
    status["embedding_model"] = embed_exists

    return status
