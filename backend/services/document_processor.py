"""
Document processor for extracting and chunking text from PDF and DOCX files.
"""
import os
from typing import List, Dict, Any, Tuple
import re
from pathlib import Path

# PDF processing
import PyPDF2
import pdfplumber

# DOCX processing
from docx import Document as DocxDocument

# Tokenization
import tiktoken

from backend.config import settings


class DocumentProcessor:
    """Process documents and create chunks for RAG."""

    def __init__(self):
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        self.max_file_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024  # Convert to bytes
        self.allowed_extensions = settings.ALLOWED_FILE_TYPES

        # Initialize tokenizer for chunk size calculation
        self.tokenizer = None
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
            print(f"DocumentProcessor: Tokenizer initialized. Chunk size: {self.chunk_size} tokens")
        except Exception as e:
            # Fallback to basic word-based chunking
            print(f"DocumentProcessor: Failed to initialize tokenizer: {e}. Using fallback character-based chunking.")

    def validate_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Validate file type and size.

        Args:
            file_path: Path to the file

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if file exists
        if not os.path.exists(file_path):
            return False, "File does not exist"

        # Check file extension
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in self.allowed_extensions:
            return False, f"File type not allowed. Allowed: {', '.join(self.allowed_extensions)}"

        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            return False, f"File too large. Maximum size: {max_mb}MB"

        if file_size == 0:
            return False, "File is empty"

        return True, ""

    def extract_text_from_pdf(self, file_path: str) -> str:
        """
        Extract text from PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text
        """
        text = ""

        try:
            # Try pdfplumber first (better text extraction)
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"

        except Exception as e:
            print(f"pdfplumber failed, trying PyPDF2: {e}")
            # Fallback to PyPDF2
            try:
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
            except Exception as e2:
                raise Exception(f"Failed to extract PDF text: {e2}")

        return text.strip()

    def extract_text_from_docx(self, file_path: str) -> str:
        """
        Extract text from DOCX file.

        Args:
            file_path: Path to DOCX file

        Returns:
            Extracted text
        """
        try:
            doc = DocxDocument(file_path)
            text = ""

            # Extract from paragraphs
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text += paragraph.text + "\n"

            # Extract from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    if row_text.strip():
                        text += row_text + "\n"

            return text.strip()

        except Exception as e:
            raise Exception(f"Failed to extract DOCX text: {e}")

    def extract_text(self, file_path: str) -> str:
        """
        Extract text from file based on extension.

        Args:
            file_path: Path to file

        Returns:
            Extracted text

        Raises:
            ValueError: If file type is not supported
        """
        file_ext = Path(file_path).suffix.lower()

        if file_ext == ".pdf":
            return self.extract_text_from_pdf(file_path)
        elif file_ext == ".docx":
            return self.extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

    def clean_text(self, text: str) -> str:
        """
        Clean extracted text.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove special characters (keep basic punctuation)
        text = re.sub(r'[^\w\s\.\,\;\:\!\?\-\(\)\[\]\'\"]', '', text)

        return text.strip()

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Fallback: approximate 1 token ≈ 4 characters
            return len(text) // 4

    def create_chunks(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks.

        Args:
            text: Text to chunk

        Returns:
            List of chunks with metadata
        """
        if not text:
            return []

        chunks = []

        if self.tokenizer:
            # Token-based chunking
            tokens = self.tokenizer.encode(text)

            for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
                chunk_tokens = tokens[i:i + self.chunk_size]
                chunk_text = self.tokenizer.decode(chunk_tokens)

                chunks.append({
                    "content": chunk_text.strip(),
                    "chunk_index": len(chunks),
                    "token_count": len(chunk_tokens),
                    "char_count": len(chunk_text)
                })

                # Stop if we've processed all tokens
                if i + self.chunk_size >= len(tokens):
                    break
        else:
            # Character-based chunking (fallback)
            # 200 tokens * 3 chars/token = 600 characters max per chunk (very conservative)
            char_size = self.chunk_size * 3
            char_overlap = self.chunk_overlap * 3

            for i in range(0, len(text), char_size - char_overlap):
                chunk_text = text[i:i + char_size]

                chunks.append({
                    "content": chunk_text.strip(),
                    "chunk_index": len(chunks),
                    "char_count": len(chunk_text)
                })

                if i + char_size >= len(text):
                    break

        return chunks

    def process_document(
        self,
        file_path: str,
        additional_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process a document: extract text, clean, and chunk.

        Args:
            file_path: Path to document file
            additional_metadata: Optional additional metadata

        Returns:
            Dictionary with processed document data

        Raises:
            Exception: If processing fails
        """
        # Validate file
        is_valid, error_msg = self.validate_file(file_path)
        if not is_valid:
            raise ValueError(error_msg)

        # Extract text
        raw_text = self.extract_text(file_path)
        if not raw_text:
            raise ValueError("No text could be extracted from document")

        # Clean text
        cleaned_text = self.clean_text(raw_text)

        # Create chunks
        chunks = self.create_chunks(cleaned_text)

        # Prepare result
        result = {
            "file_path": file_path,
            "file_name": Path(file_path).name,
            "file_type": Path(file_path).suffix.lower(),
            "file_size": os.path.getsize(file_path),
            "total_text_length": len(cleaned_text),
            "total_tokens": self.count_tokens(cleaned_text),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "metadata": additional_metadata or {}
        }

        return result


# Global document processor instance
document_processor = DocumentProcessor()
