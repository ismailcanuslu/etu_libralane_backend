# LibreLane Backend

FastAPI backend; workspace dosya API'si, job orchestration ve AI uçlarını servis eder.

## Workspace

Kalıcı proje dosyaları `WORKSPACE_ROOT` altında tutulur (varsayılan `/workspace`). Docker compose bu dizini `./workspace` ile bind mount eder.

## Çalıştırma

```bash
docker compose up --build
```

Workspace listesi:

```bash
curl http://127.0.0.1:8001/files
```

## RAG (Qdrant)

Sohbet uclari (`/ai/chat`, WebSocket akisi), soruyla ilgili kod parcalarini sunucudaki hazir
Qdrant koleksiyonundan cekip modele referans baglam olarak verir. Indexleme sunucudaki
`indexer.py` ile yapilir; backend yalnizca retrieval yapar.

Gereksinimler:

- Qdrant `librelane_verilog` koleksiyonu dolu ve erisilebilir olmali (varsayilan `http://127.0.0.1:6333`).
- Embedding modeli indexer ile ayni olmali: `ollama pull nomic-embed-text`.

Ilgili env degiskenleri (bkz. `.env.example`): `RAG_ENABLED`, `QDRANT_URL`, `QDRANT_COLLECTION`,
`RAG_EMBEDDING_MODEL`, `RAG_TOP_K`, `RAG_MAX_CONTEXT_CHARS`, `RAG_TIMEOUT_SECONDS`.

Qdrant erisilemezse veya `RAG_ENABLED=false` ise sohbet, RAG olmadan calismaya devam eder.

Durum ve test:

```bash
curl http://127.0.0.1:8001/ai/rag/status
curl -X POST http://127.0.0.1:8001/ai/rag/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "AXI4-Lite slave arayuzu", "top_k": 5}'
```
