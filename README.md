# Argos — Sistema RAG Modulare Multimodale

**Argos** è un sistema RAG (Retrieval-Augmented Generation) modulare per l'ingestion, la trasformazione semantica, l'archiviazione crittografata e il retrieval di documenti multimodali — PDF, Word, immagini, audio, video, Markdown e testo.

> 🏷️ Il nome: Argo era il cane di Ulisse che riconobbe il padrone dopo 20 anni. Argos riconosce e recupera i tuoi documenti ovunque e in qualsiasi formato.

## ✨ Caratteristiche

- 📄 **Ingestion multimodale**: PDF, Word, Excel, PowerPoint, Markdown, testo, immagini, audio, video
- 🔍 **Ricerca semantica ibrida**: full-text + vettoriale con Qdrant
- 🧠 **Embedding multimodale**: testo (multilingual-e5), immagini (CLIP), audio (CLAP + Whisper)
- 🧩 **GLM-OCR integrato**: parsing PDF complessi in Markdown con tabelle e formule
- 🔐 **Crittografia AES-256-GCM**: documenti cifrati at-rest con Argon2id key derivation
- 🔗 **Attribuzione certa**: ogni documento legato a fonte verificata (email/telefono/alias)
- 📦 **Storage flessibile**: filesystem locale o S3/MinIO compatibile
- 🐳 **Docker-ready**: sviluppo locale e produzione con docker-compose
- 🌐 **API REST**: FastAPI con Swagger auto-documentato
- 🎨 **UI moderna**: React 19 + Vite + Tailwind CSS 4

## 🏗️ Architettura

```
argos/
├── core/           # Configurazione, modelli condivisi, logging
├── ingestion/      # Parser per ogni tipo di documento
├── embeddings/     # Pipeline di embedding multimodale
├── storage/        # Archiviazione file + metadati (SQL/Postgres)
├── encryption/     # AES-256-GCM + Argon2id + gestione chiavi
├── api/            # FastAPI REST endpoints + Celery tasks
├── ui/             # Frontend React
├── deploy/         # Docker, docker-compose, guide cloud
└── tests/          # Test suite
```

## 🚀 Quick Start

### Prerequisiti

- Python 3.12+
- Docker (opzionale, per Qdrant/Redis/MinIO)
- Node.js 22+ (per la UI)

### Sviluppo locale

```bash
# 1. Clona
git clone https://github.com/doureallydo/argos.git
cd argos

# 2. Ambiente virtuale
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Config
cp .env.example .env
# (modifica .env con i tuoi valori)

# 4. Servizi (Qdrant, Redis, MinIO)
docker compose -f deploy/docker-compose.yml up -d

# 5. Avvia API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 6. (Opzionale) Frontend
cd ui && npm install && npm run dev
```

API docs: http://localhost:8000/docs

## 📦 Moduli Opzionali

### GLM-OCR

```bash
pip install -e ".[glm-ocr]"
# Abilita in .env: GLM_OCR_ENABLED=true
```

### Gemini Embedding 2 (cloud)

```bash
pip install -e ".[google-embeddings]"
# Abilita in .env: GOOGLE_API_KEY=...
```

## 🛡️ Sicurezza

- **AES-256-GCM**: crittografia documenti con autenticazione integrata
- **Argon2id**: derivazione chiavi resistente a GPU/ASIC
- **JWT + OAuth2**: autenticazione API
- **Chiavi mai in chiaro**: gestite via variabili d'ambiente

## 📋 Roadmap

- [x] M1 — Fondamenta (setup, struttura, Docker)
- [ ] M2 — Ingestion Engine
- [ ] M3 — Semantic Layer
- [ ] M4 — Storage & Retrieval
- [ ] M5 — Encryption & Auth
- [ ] M6 — API Layer
- [ ] M7 — Frontend UI
- [ ] M8 — Deployment & Docs

## 📄 Licenza

MIT — vedi [LICENSE](LICENSE)

---

_Argos: "Il cane che riconobbe Ulisse dopo vent'anni." Il tuo sistema che riconosce ogni documento._
