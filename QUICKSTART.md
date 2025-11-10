# Quick Start Guide

Get HRH-PolicyAI running in 5 minutes!

## Prerequisites

Before you begin, ensure you have:

✅ **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
✅ **Docker Compose V2.0+**
✅ **Ollama** with required models

## Docker Setup (Recommended) 🐳

The fastest way to get started!

### Step 1: Install Ollama Models

```bash
# Install Ollama from https://ollama.ai if not installed

# Pull required models (first time only)
ollama pull gemma3:latest
ollama pull mxbai-embed-large:latest
```

### Step 2: Configure Environment

```bash
# Copy Docker environment template
cp .env.example .env

# IMPORTANT: Edit .env and change JWT_SECRET_KEY
# Generate a secure key:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 3: Start All Services

```bash
# Build and start all containers
docker compose up -d

# View logs
docker compose logs -f
```

### Step 4: Access the Application

- **Frontend**: http://localhost:8501
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Step 5: Login

Use demo credentials:
- **Admin**: admin@hrh-policy.ke / admin123
- **User**: user@hrh-policy.ke / user123

### Management Commands

```bash
# Stop services
docker compose down

# Restart a service
docker compose restart backend

# View service status
docker compose ps

# View logs for specific service
docker compose logs -f backend
```

**That's it!** Your application is now running. 🎉

For detailed Docker documentation, see [docs/DOCKER.md](docs/DOCKER.md)

---

## Common Issues

### Docker Issues

#### "Cannot connect to Docker daemon"
```bash
# Make sure Docker Desktop is running
# Windows/Mac: Check system tray
# Linux: sudo systemctl start docker
```

#### "Port already in use"
```bash
# Check what's using the port
# Windows: netstat -ano | findstr :8000
# Linux/Mac: lsof -i :8000

# Or change ports in .env
API_PORT=8001
STREAMLIT_PORT=8502
```

#### "Backend is unhealthy"
```bash
# Check backend logs
docker compose logs backend

# Common causes:
# - Ollama not running
# - Database not ready
# - Environment variable issues
```

---

## What's Next?

### 1. Upload Documents (Admin Only)
- Go to "📚 Documents" tab
- Click "Upload New Document"
- Select PDF or DOCX file
- Choose regulatory body
- Click Upload

### 2. Ask Questions
- Go to "💬 Chat" tab
- Type your policy question
- View AI-generated answer with source citations

### 3. Compare Policies
- Go to "🔄 Compare Policies" tab
- Select multiple regulatory bodies
- Enter your comparison query
- View side-by-side analysis

### 4. Bulk Document Ingestion

Place documents in `data/documents/` folder, then:

```bash
# With Docker
docker compose exec backend python /app/scripts/ingest_documents.py

```

---

## API Access

### Interactive API Documentation

Visit http://localhost:8000/docs for interactive API documentation with:
- All available endpoints
- Request/response schemas
- Try-it-out functionality

### Example API Calls

**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@hrh-policy.ke","password":"admin123"}'
```

**Query with Authentication:**
```bash
# Save the access_token from login response
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the registration requirements?",
    "top_k": 5
  }'
```

---

## Stopping the Application

### Docker Setup:
```bash
# Stop all services
docker compose down

# Stop and remove volumes (⚠️ deletes data!)
docker compose down -v
```

---

## Next Steps

- 📖 Read [README.md](README.md) for detailed project overview
- 🐳 Check [docs/DOCKER.md](docs/DOCKER.md) for advanced Docker usage
- 📚 Review [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md) for architecture details

---

## Need Help?

1. Check the **Common Issues** section above
2. Review logs:
   - Docker: `docker compose logs -f`
3. Verify prerequisites are installed correctly
4. Check [docs/DOCKER.md](docs/DOCKER.md) for detailed troubleshooting

---

**Happy Policy Querying! 🏥🤖**
