-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    regulatory_body VARCHAR(100) NOT NULL,
    file_path VARCHAR(1000),
    file_type VARCHAR(50),
    file_size INTEGER,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Create document_chunks table with vector embeddings
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(768),
    chunk_index INTEGER NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_documents_regulatory_body ON documents(regulatory_body);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_index ON document_chunks(chunk_index);

-- Create IVFFlat index for vector similarity search (after data is inserted)
-- This will be created programmatically after initial data ingestion
-- CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks
-- USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for users table
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default admin user (password: admin123 - CHANGE IN PRODUCTION!)
-- Password hash for 'admin123' using bcrypt
INSERT INTO users (email, password_hash, full_name, role)
VALUES (
    'admin@hrh-policy.ke',
    '$2b$12$unSl.qh5Ad2RS4VGgb0DgeFXexjGNW80thUF939OxaTpK6tgh6nK.',
    'System Administrator',
    'admin'
) ON CONFLICT (email) DO NOTHING;

-- Insert regular test user (password: user123)
INSERT INTO users (email, password_hash, full_name, role)
VALUES (
    'user@hrh-policy.ke',
    '$2b$12$XupCMGHs93feKSwIb0Jum.Zsbk7dP3Zm2F30FKVf53wUPEGe7VyAS',
    'Test User',
    'user'
) ON CONFLICT (email) DO NOTHING;

-- Create view for document statistics
CREATE OR REPLACE VIEW document_stats AS
SELECT
    d.id,
    d.title,
    d.regulatory_body,
    d.uploaded_at,
    COUNT(dc.id) as chunk_count,
    u.full_name as uploaded_by_name
FROM documents d
LEFT JOIN document_chunks dc ON d.id = dc.document_id
LEFT JOIN users u ON d.uploaded_by = u.id
GROUP BY d.id, d.title, d.regulatory_body, d.uploaded_at, u.full_name;

-- Grant permissions (adjust as needed)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
