# HRH-PolicyAI 🏥🤖

**AI-Powered RAG Chatbot for Kenya's Health Workforce Policy Interpretation**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](docs/DOCKER.md)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-blue)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An intelligent chatbot system that helps healthcare professionals understand and navigate policies from Kenya's health workforce regulatory bodies using Retrieval-Augmented Generation (RAG) with local LLMs.

---

## 🎯 Features

### Core Capabilities
- **🔐 Secure Authentication** - JWT-based auth with access and refresh tokens
- **💬 Intelligent Q&A** - RAG pipeline powered by Ollama (gemma3) for accurate policy interpretations
- **🔍 Semantic Search** - PostgreSQL + pgvector for efficient similarity search
- **📚 Multi-Format Support** - Process PDF and DOCX documents
- **🏢 Multi-Regulatory Support** - KMPDB, NCK, COC, PPB, PHOTC policies
- **🔄 Policy Comparison** - Compare policies across different regulatory bodies
- **👤 Role-Based Access** - Admin and user roles with appropriate permissions
- **🐳 Dockerized** - Complete containerization for easy deployment

### Technical Highlights
- Async FastAPI backend with type hints
- Streamlit-based responsive UI
- Local LLM deployment (no cloud dependencies)
- Multi-stage Docker builds for optimization
- Vector embeddings with 1024 dimensions (mxbai-embed-large)
- Automatic token refresh handling
- Health checks and graceful error handling

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   HRH-PolicyAI System                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Frontend (Streamlit)   →   Backend (FastAPI)          │
│       :8501                      :8000                  │
│                                    │                    │
│                              ┌─────┴──────┐            │
│                              │            │            │
│                         PostgreSQL    Ollama           │
│                         + pgvector    (Host)           │
│                           :5432       :11434           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Streamlit | Interactive UI with session management |
| **Backend** | FastAPI | REST API with async support |
| **Database** | PostgreSQL 18 + pgvector | Structured data + vector search |
| **LLM** | Ollama (gemma3) | Local language model for generation |
| **Embeddings** | mxbai-embed-large | 1024-dim vector embeddings |
| **Auth** | JWT + bcrypt | Secure authentication |
| **Deployment** | Docker Compose | Containerized multi-service orchestration |

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** or Docker Engine (20.10+)
- **Docker Compose** (V2.0+)
- **Ollama** with models: `gemma3:latest` and `mxbai-embed-large:latest`

### 1. Install Ollama Models

```bash
ollama pull gemma3:latest
ollama pull mxbai-embed-large:latest
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and change JWT_SECRET_KEY
```

### 3. Start All Services

```bash
docker compose up -d
```

### 4. Access Application

- **Frontend**: http://localhost:8501
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### 5. Login

Demo credentials:
- **Admin**: admin@hrh-policy.ke / admin123
- **User**: user@hrh-policy.ke / user123

**See [QUICKSTART.md](QUICKSTART.md) for detailed setup instructions**

---

## 📚 Documentation

Comprehensive documentation is available in the `/docs` folder:

| Document | Description |
|----------|-------------|
| **[QUICKSTART.md](QUICKSTART.md)** | 5-minute setup guide |
| **[docs/DOCKER.md](docs/DOCKER.md)** | Docker deployment & management |
| **[docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md)** | Architecture & implementation details |

### API Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
POSTGRES_HOST=postgres
POSTGRES_DB=hrh_policyai

# JWT (⚠️ Change for production!)
JWT_SECRET_KEY=your-super-secret-key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# Ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_LLM_MODEL=gemma3:latest
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest

# RAG Settings
CHUNK_SIZE=500
CHUNK_OVERLAP=50
DEFAULT_TOP_K=5
EMBEDDING_DIMENSION=1024
```

**See [.env.example](.env.example) for complete configuration options**

---

## 🗂️ Project Structure

```
hrh-policyai/
├── backend/                    # FastAPI application
│   ├── api/                   # API routes
│   ├── services/              # Business logic (auth, RAG, Ollama)
│   ├── database/              # SQLAlchemy models & connection
│   ├── models/                # Pydantic schemas
│   └── main.py                # Application entry point
├── frontend/                   # Streamlit application
│   └── app.py                 # UI implementation
├── scripts/                    # Utility scripts
│   ├── setup_db.sql           # Database schema
│   └── ingest_documents.py     # Batch document processing
├── docs/                       # Documentation
│   ├── DOCKER.md              # Docker guide
│   ├── PROJECT_SUMMARY.md     # Architecture details
├── data/                       # Data storage
│   ├── uploads/               # Uploaded documents
│   └── documents/             # Batch ingestion folder
├── docker-compose.yml          # Service orchestration
├── .env.example                 # Docker environment template
└── README.md                   # This file
```

---

## 🔒 Security

### Authentication & Authorization
- ✅ **Bcrypt password hashing** (12 rounds)
- ✅ **JWT tokens** with 30-minute expiration
- ✅ **Refresh tokens** (7-day expiration)
- ✅ **Role-based access control** (Admin vs User)
- ✅ **HTTP-only bearer token** authentication

### Infrastructure Security
- ✅ **Non-root containers** (runs as `appuser`)
- ✅ **Network isolation** (custom Docker network)
- ✅ **File type validation** (.pdf, .docx only)
- ✅ **File size limits** (50MB default)
- ✅ **CORS configuration** (restricted origins)

### Production Recommendations
- Change JWT_SECRET_KEY to cryptographically secure value
- Use HTTPS with nginx reverse proxy
- Enable rate limiting on API endpoints
- Implement request logging and monitoring
- Regular security updates for dependencies

---

## 🧪 Testing

### Manual Testing (Completed)
- ✅ User registration & login
- ✅ JWT token generation & refresh
- ✅ Database connectivity
- ✅ Health checks
- ✅ Docker service orchestration

### Automated Testing
Currently, no automated test suite exists. Contributions welcome!

Recommended test structure:
```
tests/
├── unit/           # Service & utility tests
├── integration/    # API endpoint tests
└── e2e/            # End-to-end workflow tests
```

---

## 📊 RAG Pipeline

### Document Processing Flow

```
1. Upload (PDF/DOCX)
      ↓
2. Text Extraction
      ↓
3. Chunking (500 tokens, 50 overlap)
      ↓
4. Embedding Generation (mxbai-embed-large)
      ↓
5. Vector Storage (PostgreSQL + pgvector)
```

### Query Processing Flow

```
1. User Query
      ↓
2. Query Embedding
      ↓
3. Similarity Search (Top-K retrieval)
      ↓
4. Context Assembly
      ↓
5. Prompt Engineering
      ↓
6. LLM Generation (gemma3)
      ↓
7. Response with Citations
```

**Similarity Metric**: Cosine similarity
**Index Type**: IVFFlat (for performance)
**Default Top-K**: 5 documents

---

## 💡 Usage Examples

### API Usage

**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hrh-policy.ke","password":"admin123"}'
```

**Query with Authentication:**
```bash
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the registration requirements for nurses?",
    "regulatory_body": "NCK",
    "top_k": 5
  }'
```

**Upload Document (Admin):**
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -F "file=@policy.pdf" \
  -F "title=Registration Guidelines 2024" \
  -F "regulatory_body=KMPDB"
```

### Batch Document Ingestion

```bash
# Place documents in data/documents/
# Filename format: REGULATORY_BODY_Title.pdf

# Run ingestion
docker compose exec backend python /app/scripts/ingest_documents.py
```

---

## 🛠️ Development

### Manual Setup (Non-Docker)

For local development with hot-reload:

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# 2. Start database only
docker compose up -d postgres

# 3. Install dependencies
cd backend && pip install -r requirements.txt
cd ../frontend && pip install -r requirements.txt

# 4. Configure for local dev
cp .env.example .env
# Edit .env: POSTGRES_HOST=localhost

# 5. Start services
cd backend && python main.py  # Terminal 1
cd frontend && streamlit run app.py  # Terminal 2
```

**See [QUICKSTART.md](QUICKSTART.md) for detailed instructions**

### Docker Development

```bash
# Build images
docker compose build

# Start with logs
docker compose up

# Rebuild after code changes
docker compose build backend
docker compose restart backend
```

---

## 📈 Roadmap

### Planned Enhancements
- [ ] Comprehensive test suite (pytest)
- [ ] API rate limiting
- [ ] Input sanitization improvements
- [ ] Prometheus metrics
- [ ] CI/CD pipeline
- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Document versioning
- [ ] Audit logging

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Test coverage (unit, integration, e2e)
- Documentation enhancements
- Performance optimizations
- Security improvements
- Feature additions

Please ensure:
- Code follows PEP 8 style guide
- Type hints are included
- Docstrings for functions
- Tests for new features

---

## 📄 License

This project is provided as-is for educational and demonstration purposes.

---

## 🙏 Acknowledgments

- **FastAPI** - Excellent modern Python web framework
- **Streamlit** - Intuitive UI framework
- **Ollama** - Local LLM deployment made easy
- **PostgreSQL & pgvector** - Powerful vector search capabilities
- **Kenya's Health Workforce Regulatory Bodies** - KMPDB, NCK, COC, PPB, PHOTC

---

## 📞 Support

### Documentation
- [QUICKSTART.md](QUICKSTART.md) - Setup guide
- [docs/DOCKER.md](docs/DOCKER.md) - Docker deployment
- [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md) - Architecture details

### Troubleshooting
- Check service logs: `docker compose logs -f`
- Verify Ollama is running: `ollama list`
- Check database: `docker compose ps postgres`
- Review [QUICKSTART.md](QUICKSTART.md) Common Issues section

---

**Built with ❤️ for Kenya's Healthcare Professionals**

*Empowering healthcare workers with AI-driven policy understanding*
