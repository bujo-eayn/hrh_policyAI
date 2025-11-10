"""
Document ingestion script for batch processing policy documents.
Processes documents from data/documents directory and stores them in database.
"""
import os
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from backend.database.connection import SessionLocal, init_db
from backend.database.models import Document, DocumentChunk, User
from backend.services.document_processor import document_processor
from backend.services.embeddings import embedding_service
from backend.config import settings


async def ingest_document(
    db: Session,
    file_path: str,
    title: str,
    regulatory_body: str,
    admin_user_id: str
):
    """
    Ingest a single document.

    Args:
        db: Database session
        file_path: Path to document file
        title: Document title
        regulatory_body: Regulatory body
        admin_user_id: ID of admin user to attribute upload
    """
    print(f"\n📄 Processing: {title}")
    print(f"   File: {file_path}")
    print(f"   Regulatory Body: {regulatory_body}")

    try:
        # Process document
        print("   Extracting text and creating chunks...")
        processed_data = document_processor.process_document(file_path)

        print(f"   ✓ Extracted {processed_data['total_text_length']} characters")
        print(f"   ✓ Created {processed_data['chunk_count']} chunks")

        # Create document record
        document = Document(
            title=title,
            regulatory_body=regulatory_body,
            file_path=file_path,
            file_type=processed_data["file_type"],
            file_size=processed_data["file_size"],
            uploaded_by=admin_user_id
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        print(f"   ✓ Document record created (ID: {document.id})")

        # Generate embeddings and create chunks
        print(f"   Generating embeddings for {processed_data['chunk_count']} chunks...")

        for i, chunk_data in enumerate(processed_data["chunks"]):
            # Generate embedding
            embedding = await embedding_service.generate_embedding(chunk_data["content"])

            # Create chunk record
            chunk = DocumentChunk(
                document_id=document.id,
                content=chunk_data["content"],
                embedding=embedding,
                chunk_index=chunk_data["chunk_index"],
                metadata={"token_count": chunk_data.get("token_count", 0)}
            )
            db.add(chunk)

            if (i + 1) % 10 == 0:
                print(f"   Progress: {i + 1}/{processed_data['chunk_count']} chunks")

        # Mark document as processed
        document.is_processed = True
        from datetime import datetime
        document.processed_at = datetime.utcnow()

        db.commit()

        print(f"   ✓ Document ingestion complete!")
        return True

    except Exception as e:
        db.rollback()
        print(f"   ✗ Error: {str(e)}")
        return False


async def ingest_from_directory(directory: str = "./data/documents"):
    """
    Ingest all documents from a directory.

    Args:
        directory: Path to directory containing documents
    """
    print(f"\n{'='*70}")
    print(f"HRH-PolicyAI Document Ingestion Script")
    print(f"{'='*70}\n")

    # Initialize database
    print("Initializing database...")
    init_db()
    db = SessionLocal()

    # Get admin user
    admin_user = db.query(User).filter(User.role == "admin").first()
    if not admin_user:
        print("✗ No admin user found. Please create an admin user first.")
        return

    print(f"✓ Using admin user: {admin_user.email}")

    # Check if directory exists
    if not os.path.exists(directory):
        print(f"\n✗ Directory not found: {directory}")
        print(f"Creating directory...")
        os.makedirs(directory, exist_ok=True)
        print(f"✓ Directory created. Please add documents and run again.")
        return

    # Find all PDF and DOCX files
    doc_files = []
    for ext in [".pdf", ".docx"]:
        doc_files.extend(list(Path(directory).glob(f"**/*{ext}")))

    if not doc_files:
        print(f"\n✗ No documents found in {directory}")
        print(f"Supported formats: .pdf, .docx")
        return

    print(f"\n✓ Found {len(doc_files)} document(s) to process\n")

    # Process each document
    success_count = 0
    fail_count = 0

    for doc_file in doc_files:
        # Extract metadata from filename or directory structure
        # Expected format: <regulatory_body>_<title>.pdf
        filename = doc_file.stem
        parts = filename.split("_", 1)

        if len(parts) == 2 and parts[0] in settings.REGULATORY_BODIES:
            regulatory_body = parts[0]
            title = parts[1].replace("_", " ").title()
        else:
            # Default to KMPDB if not specified
            regulatory_body = "KMPDB"
            title = filename.replace("_", " ").title()

        # Check if already ingested
        existing = db.query(Document).filter(Document.title == title).first()
        if existing:
            print(f"\n⏭️  Skipping (already exists): {title}")
            continue

        # Ingest document
        result = await ingest_document(
            db=db,
            file_path=str(doc_file),
            title=title,
            regulatory_body=regulatory_body,
            admin_user_id=admin_user.id
        )

        if result:
            success_count += 1
        else:
            fail_count += 1

    # Create IVFFlat index for better performance
    print(f"\n{'='*70}")
    print("Creating vector similarity index...")

    total_chunks = db.query(DocumentChunk).count()
    if total_chunks > 0:
        # Calculate optimal number of lists (typically sqrt(total_rows))
        import math
        lists = max(10, int(math.sqrt(total_chunks)))

        if await embedding_service.create_ivfflat_index(db, lists):
            print(f"✓ IVFFlat index created with {lists} lists")
        else:
            print("✗ Failed to create index")

    # Summary
    print(f"\n{'='*70}")
    print(f"Ingestion Summary")
    print(f"{'='*70}")
    print(f"✓ Successful: {success_count}")
    print(f"✗ Failed: {fail_count}")
    print(f"Total documents in database: {db.query(Document).count()}")
    print(f"Total chunks in database: {total_chunks}")
    print(f"{'='*70}\n")

    db.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Ingest policy documents into HRH-PolicyAI")
    parser.add_argument(
        "--directory",
        "-d",
        default="./data/documents",
        help="Directory containing documents to ingest"
    )

    args = parser.parse_args()

    # Run ingestion
    asyncio.run(ingest_from_directory(args.directory))


if __name__ == "__main__":
    main()
