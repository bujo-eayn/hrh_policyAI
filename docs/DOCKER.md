# Docker Deployment Guide - HRH-PolicyAI

Complete guide for running HRH-PolicyAI with Docker.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Building Images](#building-images)
- [Running the Stack](#running-the-stack)
- [Management Commands](#management-commands)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)

## Overview

The HRH-PolicyAI system is fully containerized with three main services:

1. **PostgreSQL Database** - Data storage with pgvector extension
2. **FastAPI Backend** - REST API and RAG pipeline
3. **Streamlit Frontend** - User interface

**Note:** Ollama runs on your host machine (not containerized) to allow GPU access.

## Prerequisites

### Required Software

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
  - Version 20.10+ recommended
  - Download: https://docs.docker.com/get-docker/

- **Docker Compose**
  - V2.0+ (included with Docker Desktop)
  - Check version: `docker compose version`

- **Ollama** (running on host)
  - Download: https://ollama.ai
  - Required models:
    ```bash
    ollama pull gemma3:latest
    ollama pull mxbai-embed-large:latest
    ```

### System Requirements

- **RAM**: 4GB minimum, 8GB recommended
- **Disk Space**: 10GB free space
- **CPU**: 2+ cores recommended
- **OS**: Windows 10+, macOS 10.15+, or Linux

## Quick Start

### 1. Ensure Ollama is Running

```bash
# Check Ollama status
ollama list

# Should show gemma3:latest and mxbai-embed-large:latest
```

### 2. Configure Environment

```bash
# Copy Docker environment template
cp .env.example .env

# IMPORTANT: Edit .env and change JWT_SECRET_KEY
# Generate a secure key:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Start All Services

```bash
# Build and start containers
docker compose up -d

# View logs
docker compose logs -f
```

### 4. Access the Application

- **Frontend**: http://localhost:8501
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### 5. Login

Use demo credentials:
- **Admin**: admin@hrh-policy.ke / admin123
- **User**: user@hrh-policy.ke / user123

## Architecture

### Service Communication

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP :8501
       ▼
┌─────────────────┐
│    Frontend     │
│   (Streamlit)   │
└────────┬────────┘
         │ HTTP (internal)
         │ http://backend:8000
         ▼
┌─────────────────┐     ┌──────────────┐
│     Backend     │────→│  PostgreSQL  │
│    (FastAPI)    │     │  + pgvector  │
└────────┬────────┘     └──────────────┘
         │
         │ HTTP :11434
         │ via host.docker.internal
         ▼
┌─────────────────┐
│  Ollama (Host)  │
│  gemma3 + mxbai │
└─────────────────┘
```

### Multi-Stage Builds

Both backend and frontend use multi-stage Docker builds for efficiency:

**Stage 1: Builder**
- Installs build dependencies
- Creates Python wheel files
- Larger image (~500MB)

**Stage 2: Runtime**
- Copies only wheels and application code
- Installs runtime dependencies only
- Smaller final image (~250-300MB)

**Benefits:**
- 40-60% smaller images
- Faster deployments
- Reduced attack surface
- No build tools in production

## Configuration

### Environment Variables

All configuration is done via `.env` file. Key variables:

#### Database
```bash
POSTGRES_HOST=postgres          # Service name (don't change)
POSTGRES_PORT=5432
POSTGRES_DB=hrh_policyai
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres      # Change in production!
```

#### JWT Security
```bash
JWT_SECRET_KEY=<your-secret-key>  # MUST change for production!
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

#### Ollama
```bash
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_LLM_MODEL=gemma3:latest
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large:latest
```

#### Ports
```bash
API_PORT=8000              # Backend API port
STREAMLIT_PORT=8501        # Frontend port
```

### Volumes

**Persistent Data:**
- `postgres_data` - Database files
- `upload_data` - Uploaded documents

View volumes:
```bash
docker volume ls | grep hrh-policyai
```

## Building Images

### Build All Services

```bash
# Build all images
docker compose build

# Build specific service
docker compose build backend
docker compose build frontend
```

### Build Options

```bash
# Build without cache (clean build)
docker compose build --no-cache

# Pull latest base images before building
docker compose build --pull

# Build with progress output
docker compose build --progress=plain
```

### Verify Images

```bash
# List images
docker images | grep hrh-policyai

# Check image sizes
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep hrh-policyai
```

**Expected sizes:**
- Backend: ~250-300MB
- Frontend: ~250-300MB

## Running the Stack

### Start Services

```bash
# Start all services (detached mode)
docker compose up -d

# Start and view logs
docker compose up

# Start specific service
docker compose up -d backend
```

### Stop Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes data!)
docker compose down -v

# Stop specific service
docker compose stop backend
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart backend
```

## Management Commands

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres

# Last 100 lines
docker compose logs --tail=100 backend

# Since timestamp
docker compose logs --since 2024-01-01T00:00:00
```

### Service Status

```bash
# Check service health
docker compose ps

# Detailed service info
docker compose ps -a

# Check specific service
docker inspect hrh-policyai-backend
```

### Execute Commands in Containers

```bash
# Access backend shell
docker compose exec backend bash

# Access database
docker compose exec postgres psql -U postgres -d hrh_policyai

# Run Python in backend
docker compose exec backend python

# Check Python packages
docker compose exec backend pip list
```

### Database Operations

```bash
# Backup database
docker compose exec postgres pg_dump -U postgres hrh_policyai > backup.sql

# Restore database
docker compose exec -T postgres psql -U postgres hrh_policyai < backup.sql

# Check database size
docker compose exec postgres psql -U postgres -c "SELECT pg_size_pretty(pg_database_size('hrh_policyai'));"

# List tables
docker compose exec postgres psql -U postgres -d hrh_policyai -c "\dt"
```

### Resource Usage

```bash
# Monitor resource usage
docker stats

# Specific services
docker stats hrh-policyai-backend hrh-policyai-frontend

# One-time snapshot
docker stats --no-stream
```

### Clean Up

```bash
# Remove stopped containers
docker compose rm

# Remove unused images
docker image prune

# Remove all unused Docker objects
docker system prune

# Remove everything (WARNING: nuclear option!)
docker system prune -a --volumes
```

## Troubleshooting

### Common Issues

#### 1. Backend Can't Connect to Ollama

**Symptoms:**
```
Ollama connection failed
```

**Solutions:**
```bash
# Check Ollama is running
ollama list

# On Windows, check Task Manager for Ollama
# On Mac, check menu bar for Ollama icon
# On Linux, check service status
systemctl status ollama

# Test Ollama from host
curl http://localhost:11434/api/tags

# Test from backend container
docker compose exec backend curl http://host.docker.internal:11434/api/tags
```

#### 2. Database Connection Refused

**Symptoms:**
```
psycopg2.OperationalError: could not connect to server
```

**Solutions:**
```bash
# Check database is running
docker compose ps postgres

# View database logs
docker compose logs postgres

# Restart database
docker compose restart postgres

# Check database health
docker compose exec postgres pg_isready -U postgres
```

#### 3. Port Already in Use

**Symptoms:**
```
Error: Port 8000 is already allocated
```

**Solutions:**
```bash
# Find process using port
# Windows
netstat -ano | findstr :8000
# Linux/Mac
lsof -i :8000

# Change ports in .env
API_PORT=8001
STREAMLIT_PORT=8502

# Restart services
docker compose down
docker compose up -d
```

#### 4. Frontend Can't Reach Backend

**Symptoms:**
- Login fails
- API calls timeout

**Solutions:**
```bash
# Check backend is healthy
curl http://localhost:8000/

# Check frontend can reach backend
docker compose exec frontend ping backend

# Check backend logs
docker compose logs backend

# Verify API_BASE_URL in frontend
docker compose exec frontend env | grep API_BASE_URL
```

#### 5. Permission Denied for Uploads

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '/app/data/uploads'
```

**Solutions:**
```bash
# Fix volume permissions
docker compose exec backend chown -R appuser:appuser /app/data

# Restart backend
docker compose restart backend
```

#### 6. Out of Memory

**Symptoms:**
- Containers crashing
- Services restarting frequently

**Solutions:**
```bash
# Check memory usage
docker stats

# Increase Docker memory limit
# Docker Desktop: Settings > Resources > Memory

# Add memory limits to docker-compose.yml
# (see Production Deployment section)
```

### Health Checks

```bash
# Check all health statuses
docker compose ps

# Backend health
curl http://localhost:8000/

# Frontend health
curl http://localhost:8501/_stcore/health

# Database health
docker compose exec postgres pg_isready
```

### Debug Mode

Enable debug logging:

```bash
# Edit .env
DEBUG=True
LOG_LEVEL=DEBUG

# Restart services
docker compose restart backend
```

## Production Deployment

### Security Checklist

Before deploying to production:

- [ ] Change `JWT_SECRET_KEY` to strong random value
- [ ] Change database password
- [ ] Set `DEBUG=False`
- [ ] Use HTTPS (add reverse proxy)
- [ ] Enable rate limiting
- [ ] Add resource limits
- [ ] Use Docker secrets for sensitive data
- [ ] Regular security updates
- [ ] Enable automated backups

### Resource Limits

Add to `docker-compose.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### HTTPS with Nginx

Create `nginx.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location / {
        proxy_pass http://frontend:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
    }
}
```

Add nginx service to docker-compose.yml:

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./ssl:/etc/ssl
    depends_on:
      - frontend
      - backend
    networks:
      - hrh-network
```

### Automated Backups

Create backup script:

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/backups"

# Backup database
docker compose exec -T postgres pg_dump -U postgres hrh_policyai | gzip > $BACKUP_DIR/db-$DATE.sql.gz

# Backup volumes
docker run --rm -v hrh-policyai_upload_data:/data -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/uploads-$DATE.tar.gz /data

# Keep only last 7 days
find $BACKUP_DIR -name "db-*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "uploads-*.tar.gz" -mtime +7 -delete
```

Schedule with cron:
```bash
0 2 * * * /path/to/backup.sh
```

### Monitoring

Use Docker health checks and external monitoring:

```bash
# Check if services are healthy
docker compose ps | grep -q "unhealthy" && echo "Alert: Service unhealthy!"

# Monitor with Prometheus
# Add cadvisor service to docker-compose.yml

# Log aggregation with ELK Stack
# Configure logging driver in docker-compose.yml
```

### Updates and Rollbacks

```bash
# Update to new version
git pull
docker compose build
docker compose up -d

# Rollback if issues
docker compose down
git checkout <previous-commit>
docker compose up -d
```

## Advanced Topics

### Development vs Production

Use separate compose files:

```bash
# Development (hot reload, debug)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Production (optimized)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

### Scaling Services

```bash
# Scale backend to 3 instances
docker compose up -d --scale backend=3

# Requires load balancer (nginx)
```

### Custom Networks

For complex setups with multiple applications:

```yaml
networks:
  frontend:
    external: true
  backend:
    external: true
```

---

## Support

For issues:
1. Check logs: `docker compose logs`
2. Review this guide
3. Check main README.md
4. Open GitHub issue with logs

## Related Documentation

- [README.md](./README.md) - Main documentation
- [QUICKSTART.md](./QUICKSTART.md) - Quick setup guide
- [PROJECT_SUMMARY.md](./PROJECT_SUMMARY.md) - Project overview
- [.env.example](./.env.example) - Environment variables reference

---

**Last Updated:** 2025-11-10
**Docker Compose Version:** 2.x
**Tested With:** Docker 20.10+, Docker Desktop 4.0+
