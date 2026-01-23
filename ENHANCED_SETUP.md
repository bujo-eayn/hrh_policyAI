# 🚀 Enhanced Chatbot Branch - Setup Guide

**Branch:** `feature/chatbot-enhanced`
**Version:** 2.0 (Modular Architecture)

This branch introduces a refactored backend, optimized local AI settings, and new integration endpoints. Follow this guide strictly to avoid common configuration errors.

## ⚠️ Critical Changes (Read First)

1.  **New Port:** The Backend API now runs on **Port 8001** (External) to avoid conflicts with the Workforce Registry.
2.  **New AI Model:** We have switched from `mxbai-embed-large` to **`nomic-embed-text`** for better stability.
3.  **Database Reset Required:** Because the embedding dimension changed (1024 → 768), you **must** wipe the old database volume when switching to this branch.

---

## 🛠️ Quick Start

### 1. Install the Correct Ollama Model
This branch uses a lighter embedding model. Run this on your host machine:

```bash
# Required for RAG (New model)
ollama pull nomic-embed-text

# Required for Chat (Existing model)
ollama pull gemma3:latest