# API Reference — Argos RAG v0.1.0

Base URL: `http://localhost:8000/api`

## Authentication

Tutti gli endpoint (tranne `/health` e `/auth/token`) richiedono autenticazione.

### Ottieni token

```http
POST /api/auth/token
Content-Type: application/json

{
  "source_id": "your-source-id",
  "scope": "read"
}
```

Usa il token in tutti gli header:
```
Authorization: Bearer <token>
```

---

## System

### `GET /api/health`

Health check — nessuna auth richiesta.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "embedding_model": "sentence-transformers + CLIP + CLAP",
  "storage_backend": "local",
  "encryption_enabled": true,
  "uptime_seconds": 1234.5
}
```

---

## Sources

### `POST /api/sources` — Registra fonte

```json
{
  "source_type": "email",
  "source_value": "mario.rossi@example.com"
}
```

**source_type**: `email` | `phone` | `alias` | `system`

### `POST /api/sources/alias` — Genera alias random

```json
{
  "alias_prefix": "project-x"
}
```

Response: `src_project-x_a1b2c3d4`

### `GET /api/sources` — Lista fonti

Query params: `?limit=100&offset=0`

---

## Documents

### `POST /api/documents/upload` — Carica documento

**Form data:**
- `file`: il file da caricare
- `source_id`: ID della fonte registrata

**Response `202 Accepted`:**
```json
{
  "document_id": "abc123...",
  "filename": "report.pdf",
  "status": "completed",
  "message": "Successfully processed: 45 chunks indexed"
}
```

### `GET /api/documents/{doc_id}` — Metadata documento

### `GET /api/documents/{doc_id}/download` — Download originale

---

## Search

### `POST /api/search` — Ricerca semantica

```json
{
  "query": "risultati finanziari Q1 2026",
  "top_k": 10,
  "document_types": ["pdf", "excel"],
  "source_id": "optional-source-filter",
  "cross_modal": false
}
```

**Response:**
```json
{
  "query": "risultati finanziari Q1 2026",
  "total_results": 7,
  "embedding_model": "sentence-transformers + CLIP + CLAP",
  "took_ms": 45.2,
  "results": [
    {
      "score": 0.92,
      "collection": "argos_text",
      "document_id": "abc123...",
      "text": "...",
      "chunk_index": 3,
      "original_filename": "report_q1.pdf",
      "document_type": "pdf",
      "source_id": "xyz..."
    }
  ]
}
```

---

## Errori

| Status | Significato |
|--------|------------|
| 401 | Token mancante o invalido |
| 403 | Scope insufficiente |
| 404 | Documento o fonte non trovata |
| 413 | File troppo grande |
| 500 | Errore interno |

Tutti gli errori hanno formato:
```json
{
  "detail": "Messaggio descrittivo"
}
```
