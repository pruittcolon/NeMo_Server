#!/usr/bin/env python3
"""
Security Hardening Script
Generates all required secrets for production deployment
"""

import os
import secrets
import base64
from pathlib import Path


def generate_secrets():
    """Generate all required secrets"""
    # Base directory
    base_dir = Path(__file__).parent.parent
    secrets_dir = base_dir / "docker" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    
    secrets_map = {}
    
    print("🔒 Generating security secrets...")
    print("=" * 60)
    
    # 1. Session encryption key (32 bytes, base64 encoded)
    if not (secrets_dir / "session_key").exists():
        session_key = base64.b64encode(secrets.token_bytes(32)).decode()
        secrets_map['session_key'] = session_key
        print("✓ Generated session_key")
    else:
        print("⏭  session_key already exists (skipping)")
    
    # 2. Database password
    if not (secrets_dir / "postgres_password").exists():
        db_password = secrets.token_urlsafe(24)
        secrets_map['postgres_password'] = db_password
        print("✓ Generated postgres_password")
    else:
        print("⏭  postgres_password already exists (skipping)")
    
    # 3. Database user
    if not (secrets_dir / "postgres_user").exists():
        secrets_map['postgres_user'] = 'nemo_admin'
        print("✓ Generated postgres_user")
    else:
        print("⏭  postgres_user already exists (skipping)")
    
    # 4. JWT secret for inter-service auth
    if not (secrets_dir / "jwt_secret").exists():
        jwt_secret = secrets.token_urlsafe(32)
        secrets_map['jwt_secret'] = jwt_secret
        print("✓ Generated jwt_secret")
    else:
        print("⏭  jwt_secret already exists (skipping)")
    
    # 5. Gateway users database encryption key (Phase 6)
    if not (secrets_dir / "users_db_key").exists():
        users_db_key = base64.b64encode(secrets.token_bytes(32)).decode()
        secrets_map['users_db_key'] = users_db_key
        print("✓ Generated users_db_key (for gateway users.db encryption)")
    else:
        print("⏭  users_db_key already exists (skipping)")
    
    # 6. RAG database encryption key (Phase 6)
    if not (secrets_dir / "rag_db_key").exists():
        rag_db_key = base64.b64encode(secrets.token_bytes(32)).decode()
        secrets_map['rag_db_key'] = rag_db_key
        print("✓ Generated rag_db_key (for RAG service rag.db encryption)")
    else:
        print("⏭  rag_db_key already exists (skipping)")
    
    # 7. Redis password (Phase 7 - optional for dev)
    if not (secrets_dir / "redis_password").exists():
        redis_password = secrets.token_urlsafe(24)
        secrets_map['redis_password'] = redis_password
        print("✓ Generated redis_password (for Redis auth)")
    else:
        print("⏭  redis_password already exists (skipping)")
    
    # Write newly generated secrets
    for name, value in secrets_map.items():
        filepath = secrets_dir / name
        filepath.write_text(value)
        filepath.chmod(0o644)  # Readable by container non-root user

    # Ensure permissions for existing secrets (including ones we didn't regenerate)
    for secret_file in secrets_dir.iterdir():
        if secret_file.is_file() and secret_file.name != "generate_secrets.sh":
            try:
                secret_file.chmod(0o644)
            except Exception as exc:
                print(f"⚠️  Warning: could not set permissions on {secret_file}: {exc}")

    return secrets_map, secrets_dir


def update_gitignore():
    """Ensure sensitive files are ignored"""
    base_dir = Path(__file__).parent.parent
    gitignore_path = base_dir / ".gitignore"
    
    entries_to_add = [
        "",
        "# Security - DO NOT COMMIT",
        "docker/.env",
        "docker/secrets/",
        ".env",
        "*.key",
        "*.pem",
        "*.crt",
    ]
    
    existing_content = gitignore_path.read_text() if gitignore_path.exists() else ""
    
    new_entries = []
    for entry in entries_to_add:
        if entry and entry not in existing_content:
            new_entries.append(entry)
    
    if new_entries:
        with gitignore_path.open('a') as f:
            f.write('\n' + '\n'.join(new_entries) + '\n')
        print(f"\n✓ Updated .gitignore with {len(new_entries)} entries")
    else:
        print("\n✓ .gitignore already up to date")


def create_env_file():
    """Create .env file with safe defaults for development"""
    base_dir = Path(__file__).parent.parent
    env_path = base_dir / "docker" / ".env"
    
    if env_path.exists():
        print("\n⏭  docker/.env already exists (skipping)")
        return
    
    # Check if HuggingFace token exists as a secret
    hf_secret = base_dir / "docker" / "secrets" / "huggingface_token"
    hf_token_line = ""
    
    if hf_secret.exists():
        print("\n✓ Found existing HuggingFace token secret")
    else:
        print("\n⚠️  No HuggingFace token found - you'll need to add it manually")
        hf_token_line = "# HUGGINGFACE_TOKEN=<your_token_here>"
    
    env_content = f"""# Nemo Server Configuration
# Generated by security_hardening.py

# Test Mode (NEVER enable in production!)
TEST_MODE=true

# Demo users (NEVER enable in production!)
ENABLE_DEMO_USERS=true

# CORS (comma-separated list of allowed origins)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Session settings
SESSION_COOKIE_SECURE=false
SESSION_DURATION_SECONDS=86400

# Rate limiting
RATE_LIMIT_PER_MINUTE=60
LOGIN_RATE_LIMIT_PER_MINUTE=5

# File uploads
MAX_UPLOAD_SIZE_MB=100

# HuggingFace Token (add your token here or in docker/secrets/huggingface_token)
{hf_token_line}
"""
    
    env_path.write_text(env_content)
    print(f"✓ Created {env_path}")


def check_huggingface_token():
    """Check if HuggingFace token is available, create empty file if missing"""
    base_dir = Path(__file__).parent.parent
    hf_secret = base_dir / "docker" / "secrets" / "huggingface_token"
    
    if not hf_secret.exists():
        # Create empty file so Docker secrets mount doesn't fail
        hf_secret.write_text("")
        hf_secret.chmod(0o600)
        print("\n" + "=" * 60)
        print("⚠️  WARNING: No HuggingFace token found!")
        print("=" * 60)
        print("Created empty placeholder file for HuggingFace token.")
        print("To download models, you need to add your token:")
        print(f"  echo 'hf_YOUR_TOKEN' > {hf_secret}")
        print("\nGet a token from: https://huggingface.co/settings/tokens")
        print("=" * 60)
    else:
        content = hf_secret.read_text().strip()
        if not content:
            print("\n⚠️  HuggingFace token file exists but is empty (models will use cache)")
        else:
            print("\n✓ HuggingFace token found")


def main():
    """Run security hardening"""
    print("\n🔒 Nemo Server Security Hardening")
    print("=" * 60)
    
    try:
        # 1. Generate secrets
        secrets_map, secrets_dir = generate_secrets()
        
        # 2. Update .gitignore
        update_gitignore()
        
        # 3. Create .env file
        create_env_file()
        
        # 4. Check HuggingFace token
        check_huggingface_token()
        
        print("\n" + "=" * 60)
        print("✅ Security hardening complete!")
        print("=" * 60)
        
        if secrets_map:
            print("\n📝 Generated secrets:")
            for name in secrets_map.keys():
                print(f"   - {name}")
        
        print(f"\n📁 Secrets directory: {secrets_dir}")
        print("\n⚠️  IMPORTANT:")
        print("- Never commit docker/.env or docker/secrets/ to git")
        print("- For production, set TEST_MODE=false and ENABLE_DEMO_USERS=false")
        print("- Add your HuggingFace token if you need to download models")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
