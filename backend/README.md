# Backend

FastAPI + Qdrant + Ollama RAG service for the CE workflow.

## Prerequisites

### 1. Qdrant

```bash
cd docker
docker compose up -d
```

Qdrant listens on `http://localhost:6333`.

### 2. Ollama

Install from <https://ollama.com>, then pull the required models:

```bash
ollama pull qwen3.5:4b
ollama pull nomic-embed-text:v1.5
```

Ollama listens on `http://localhost:11434`.

## Install

```bash
cp .env.example .env   # adjust models if needed
uv sync
```

## Start

```bash
uv run uvicorn main:app --reload
```

API available at `http://localhost:8000`.

## Seed the knowledge base

1. Start the frontend:

   ```bash
   cd ../frontend
   npm install
   npm run dev
   ```

   UI available at `http://localhost:5173`.

2. Open the UI, click **Upload** in the left panel, and select a PDF or plain-text document.  
   A sample DUNE cold electronics note is included at `seeds/dune_ce_intro.txt`.

3. After the upload completes, type a domain question in the chat, e.g.:  
   *"What is the purpose of the COLDADC in DUNE cold electronics?"*

The backend embeds the query, retrieves the top-5 relevant chunks via hybrid dense + sparse search, and streams a grounded answer from the LLM.

## Run tests

```bash
uv run pytest
```

Integration tests require Qdrant and Ollama to be running.
