# Docker Secrets

This directory contains sensitive secrets used by Nemo Server services.

## ⚠️ IMPORTANT: Never Commit Secrets

All files in this directory (except this README and .gitkeep) are gitignored. **Never commit actual secret values.**

## Required Secrets

Generate all required secrets before starting services:

### 1. Encryption Keys (32-byte base64)

```bash
# Session encryption key
openssl rand -base64 32 > session_key

# JWT signing secret
openssl rand -base64 32 > jwt_secret

# User database encryption key
openssl rand -base64 32 > users_db_key

# RAG database encryption key
openssl rand -base64 32 > rag_db_key
```

### 2. Database Credentials

```bash
# PostgreSQL username
echo "nemo_user" > postgres_user

# PostgreSQL password (random 16-byte)
openssl rand -base64 16 > postgres_password

# Redis password (random 16-byte)
openssl rand -base64 16 > redis_password
```

### 3. External API Tokens (Optional)

```bash
# Hugging Face token (for model downloads)
# Get from: https://huggingface.co/settings/tokens
echo "hf_your_token_here" > huggingface_token
```

## Quick Setup Script

```bash
#!/bin/bash
# generate_secrets.sh

cd "$(dirname "$0")"

echo "Generating Nemo Server secrets..."

# Encryption keys
openssl rand -base64 32 > session_key
openssl rand -base64 32 > jwt_secret
openssl rand -base64 32 > users_db_key
openssl rand -base64 32 > rag_db_key

# Database credentials
echo "nemo_user" > postgres_user
openssl rand -base64 16 > postgres_password
openssl rand -base64 16 > redis_password

# Placeholder for HF token
echo "# Add your Hugging Face token here if needed" > huggingface_token

# Set appropriate permissions
chmod 600 *_key *_password *_secret *_user *_token

echo "✅ Secrets generated successfully!"
echo ""
echo "⚠️  Remember to:"
echo "  1. Add your Hugging Face token to 'huggingface_token' if needed"
echo "  2. Keep these secrets secure"
echo "  3. Never commit them to version control"
```

## Usage in Docker Compose

Secrets are mounted as files in containers at `/run/secrets/{secret_name}`:

```yaml
services:
  api-gateway:
    secrets:
      - session_key
      - jwt_secret
      - users_db_key
    # ...

secrets:
  session_key:
    file: ./secrets/session_key
  jwt_secret:
    file: ./secrets/jwt_secret
```

## Reading Secrets in Code

```python
from shared.security.secrets import get_secret

# Read secret from /run/secrets/{name}
session_key = get_secret("session_key")
jwt_secret = get_secret("jwt_secret")
```

## Security Best Practices

1. **Generate Strong Secrets**: Use `openssl rand` or similar cryptographic RNG
2. **Unique Per Environment**: Different secrets for dev/staging/prod
3. **Rotate Regularly**: Change secrets periodically (especially after team changes)
4. **Restricted Permissions**: `chmod 600` on secret files
5. **No Hardcoding**: Never hardcode secrets in code or configs
6. **Audit Access**: Log and monitor who accesses secrets

## Troubleshooting

### "Secret not found" Error

Check that:
1. Secret file exists in `docker/secrets/`
2. File is not empty
3. Docker Compose is reading from correct path
4. Container has secret mounted (`docker exec <container> ls /run/secrets/`)

### Permission Denied

```bash
# Fix permissions
chmod 600 docker/secrets/*
chown $USER:$USER docker/secrets/*
```

### Missing Secrets on Startup

Run the generation script:
```bash
cd docker/secrets
bash generate_secrets.sh
```

Then restart services:
```bash
docker compose down
docker compose up -d
```
