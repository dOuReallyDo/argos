# Deployment Guide — Argos RAG

Questa guida copre il deploy di Argos su diverse piattaforme.

---

## 🖥️ macOS Server (On-Premises)

### Prerequisiti
- macOS 14+ (Sonoma o superiore)
- Homebrew
- Docker Desktop (per Qdrant, Redis, MinIO)

### Installazione

```bash
# 1. Clona
git clone https://github.com/doureallydo/argos.git
cd argos

# 2. Ambiente
python3 -m venv .venv && source .venv/bin/activate
pip install -e "."

# 3. Variabili d'ambiente
cp .env.example .env
# Genera chiavi:
openssl rand -hex 32   # per ENCRYPTION_KEY
openssl rand -hex 64   # per JWT_SECRET_KEY
# Inserisci i valori in .env

# 4. Servizi
docker compose -f deploy/docker-compose.yml up -d

# 5. Avvia API (con MPS acceleration se disponibile)
EMBEDDING_DEVICE=mps uvicorn api.main:app --host 0.0.0.0 --port 8000

# 6. Frontend (opzionale)
cd ui && npm install && npm run build
# Servi i file statici con Nginx o direttamente con l'API
```

### Avvio come servizio (launchd)

Crea `/Library/LaunchDaemons/com.argos.api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.argos.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/argos/.venv/bin/uvicorn</string>
        <string>api.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/argos</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

```bash
sudo launchctl load /Library/LaunchDaemons/com.argos.api.plist
```

---

## 🐧 Linux Server (Ubuntu/Debian)

### Docker Compose (consigliato)

```bash
# 1. Clona
git clone https://github.com/doureallydo/argos.git && cd argos

# 2. Configura .env
cp .env.example .env
nano .env  # Imposta le variabili

# 3. Avvia stack completo
docker compose -f deploy/docker-compose.prod.yml up -d

# 4. Verifica
curl http://localhost:8000/api/health
```

### Manuale (senza Docker)

```bash
# Dipendenze sistema
sudo apt update
sudo apt install -y ffmpeg tesseract-ocr tesseract-ocr-ita python3.12 python3.12-venv

# Qdrant, Redis, MinIO come servizi systemd
# (vedi documentazione ufficiale di ciascuno)

# Python
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Avvia
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## ☁️ AWS EC2

### Setup rapido

1. **Istanza**: t3.large (2 vCPU, 8GB RAM) — consigliata per modelli embedding
2. **AMI**: Ubuntu 22.04 LTS
3. **Security Group**: apri porte 8000 (API) e 5173 (UI, opzionale)
4. **Storage**: minimo 30GB gp3

```bash
# SSH nell'istanza
ssh -i key.pem ubuntu@<ec2-ip>

# Installa Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Clona e avvia
git clone https://github.com/doureallydo/argos.git
cd argos
docker compose -f deploy/docker-compose.prod.yml up -d
```

### Con S3 per storage

1. Crea bucket S3: `argos-documents-<region>`
2. Crea IAM user con policy S3 read/write
3. Configura `.env`:

```env
STORAGE_BACKEND=s3
S3_BUCKET=argos-documents-eu-west-1
S3_REGION=eu-west-1
S3_ACCESS_KEY=AKIA...
S3_SECRET_KEY=...
```

---

## ⚡ Vercel (solo API serverless)

> ⚠️ Vercel supporta solo API serverless. Qdrant e Redis devono essere hosted separatamente.

### Configurazione

1. **Qdrant Cloud**: crea cluster gratuito su [qdrant.io](https://qdrant.io)
2. **Redis**: usa Upstash Redis (gratuito fino a 10K richieste/giorno)

### vercel.json

```json
{
  "builds": [
    { "src": "api/vercel_app.py", "use": "@vercel/python" }
  ],
  "routes": [
    { "src": "/api/(.*)", "dest": "api/vercel_app.py" }
  ]
}
```

---

## 🌍 Cloudflare (Workers + R2)

> ⚠️ Richiede adattamento — Argos attualmente è Python, Cloudflare Workers sono JS/WASM.

### Strategia ibrida

- **Workers**: solo proxy/edge cache
- **Backend Python**: su server dedicato o container
- **R2**: storage documenti (S3-compatible)

```env
STORAGE_BACKEND=s3
S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
S3_BUCKET=argos-files
S3_ACCESS_KEY=<r2-access-key>
S3_SECRET_KEY=<r2-secret-key>
```

---

## 🔒 Hardening di Sicurezza

### Checklist produzione

- [ ] `ENCRYPTION_KEY` generata con `openssl rand -hex 32` e **mai** committata
- [ ] `JWT_SECRET_KEY` generata con `openssl rand -hex 64`
- [ ] HTTPS attivato (Nginx reverse proxy + Let's Encrypt)
- [ ] `ARGOS_ENV=production`
- [ ] CORS origins limitati ai domini reali
- [ ] API rate limiting configurato (via Nginx o FastAPI middleware)
- [ ] Backup giornaliero del database SQLite/PostgreSQL
- [ ] Qdrant snapshot automatici
- [ ] Firewall: solo porte 80/443/8000 esposte

### Nginx config (esempio)

```nginx
server {
    listen 443 ssl;
    server_name argos.example.com;

    ssl_certificate /etc/letsencrypt/live/argos.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/argos.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 500M;  # Match MAX_UPLOAD_SIZE_MB
    }
}
```

---

## 📊 Monitoring

### Logs

```bash
# Log applicativi
tail -f data/logs/argos_*.log

# Docker logs
docker logs -f argos-api
docker logs -f argos-worker
```

### Health check

```bash
curl http://localhost:8000/api/health | jq
```

Risposta attesa:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "embedding_model": "sentence-transformers + CLIP + CLAP",
  "storage_backend": "local",
  "encryption_enabled": true,
  "uptime_seconds": 3600.0
}
```
