# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### 1. **DO NOT** Create a Public Issue

Please do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.

### 2. Report Privately

Send details to: **[INSERT YOUR SECURITY EMAIL]**

Include the following information:
- Type of vulnerability
- Full paths of source files related to the vulnerability
- Location of affected source code (tag/branch/commit)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability
- Any potential mitigations you've identified

### 3. Response Timeline

- **Initial Response**: Within 48 hours
- **Detailed Response**: Within 7 days
- **Fix Timeline**: Depends on severity (see below)

### 4. Severity Levels

| Severity | Response Time | Fix Timeline |
|----------|--------------|--------------|
| **Critical** | 24 hours | 7 days |
| **High** | 48 hours | 14 days |
| **Medium** | 7 days | 30 days |
| **Low** | 14 days | 60 days |

---

## Security Measures

### Current Protections

Nemo Server implements multiple security layers:

#### 1. **Authentication & Authorization**
- ✅ JWT-based service-to-service authentication
- ✅ Session-based user authentication with encrypted cookies
- ✅ Role-based access control (RBAC)
- ✅ Password hashing with bcrypt
- ✅ Session expiration and rotation

#### 2. **Data Protection**
- ✅ Encrypted databases (SQLCipher)
- ✅ Docker secrets for credential management
- ✅ No secrets in environment variables or code
- ✅ TLS/SSL support for production deployments
- ✅ Encrypted data at rest

#### 3. **Network Security**
- ✅ CORS configuration
- ✅ Internal Docker network isolation
- ✅ Rate limiting on authentication endpoints
- ✅ Request validation with Pydantic models

#### 4. **Service Security**
- ✅ Replay attack protection with request IDs
- ✅ Service-to-service JWT verification
- ✅ Docker secrets for sensitive data
- ✅ Minimal container privileges

#### 5. **Input Validation**
- ✅ File upload size limits
- ✅ Audio format validation
- ✅ SQL injection prevention (parameterized queries)
- ✅ XSS protection in frontend

---

## Known Security Considerations

### 1. **GPU Access**
- GPU containers require `--gpus all` which grants device access
- Mitigation: Run in isolated environment, use resource quotas

### 2. **Docker Socket**
- Services do not mount Docker socket
- All coordination via Redis/PostgreSQL

### 3. **Model Files**
- Large ML models are gitignored but must be secured on host
- Recommendation: Verify model checksums before deployment

### 4. **Secrets Management**
- Secrets stored in `docker/secrets/` directory
- **Critical**: Ensure proper file permissions (600) and never commit to git
- Use environment-specific secrets for dev/staging/prod

---

## Security Best Practices for Deployment

### Development
```bash
# Generate strong secrets
openssl rand -base64 32 > docker/secrets/session_key

# Set proper permissions
chmod 600 docker/secrets/*

# Never commit secrets
git status  # Verify .gitignore works
```

### Production

1. **Use HTTPS/TLS**
   ```yaml
   # Enable secure cookies
   SESSION_COOKIE_SECURE=true
   SESSION_COOKIE_SAMESITE=strict
   ```

2. **Firewall Configuration**
   ```bash
   # Only expose API Gateway
   ufw allow 443/tcp  # HTTPS
   ufw deny 8001:8005/tcp  # Block internal services
   ```

3. **Environment Isolation**
   ```bash
   # Use separate Docker networks
   docker network create nemo_internal
   docker network create nemo_public
   ```

4. **Regular Updates**
   ```bash
   # Update base images
   docker compose pull
   docker compose up -d
   
   # Update dependencies
   pip install --upgrade -r requirements.txt
   ```

5. **Monitoring & Logging**
   - Enable audit logging
   - Monitor failed authentication attempts
   - Set up alerts for suspicious activity
   - Rotate logs regularly

6. **Backup Encryption**
   ```bash
   # Backup encrypted databases and vector store (host paths)
   tar -czf backup.tar.gz docker/gateway_instance/ docker/rag_instance/ docker/faiss_index/
   gpg -c backup.tar.gz
   ```

---

## Security Checklist

Before deploying to production:

- [ ] All secrets are randomly generated (32+ bytes)
- [ ] Secret files have 600 permissions
- [ ] `.gitignore` prevents secret commits
- [ ] HTTPS/TLS configured
- [ ] Firewall rules restrict internal services
- [ ] Docker secrets used (not environment variables)
- [ ] Rate limiting enabled
- [ ] Session timeout configured appropriately
- [ ] CORS origins restricted to known domains
- [ ] Audit logging enabled
- [ ] Regular security updates scheduled
- [ ] Backup strategy implemented
- [ ] Monitoring and alerting configured

---

## Vulnerability Disclosure Policy

We follow **Coordinated Disclosure**:

1. Security researcher reports vulnerability privately
2. We confirm and investigate the issue
3. We develop and test a fix
4. We release the fix
5. We publicly disclose the vulnerability (with credit to researcher)
6. Researcher may publish detailed findings after fix is deployed

### Recognition

We appreciate responsible disclosure and will:
- Publicly acknowledge researchers (unless they prefer anonymity)
- Provide updates throughout the process
- Consider adding researchers to our Hall of Fame

---

## Security Updates

Security patches are released as:
- **Critical/High**: Immediate patch release (e.g., v2.0.1)
- **Medium/Low**: Included in next minor version (e.g., v2.1.0)

Subscribe to releases on GitHub to receive notifications.

---

## Compliance

This project aims to follow:
- **OWASP Top 10** - Web application security risks
- **CWE Top 25** - Most dangerous software weaknesses
- **Docker Security Best Practices**
- **NIST Cybersecurity Framework** principles

---

## Security Audit

Last security audit: **November 2025**

Next scheduled audit: **Q2 2026**

Audit areas:
- Authentication & Authorization
- Data encryption
- Container security
- Dependency vulnerabilities
- Code injection prevention
- Network isolation

---

## Third-Party Dependencies

We monitor dependencies for known vulnerabilities using:
- GitHub Dependabot
- Safety checks in CI/CD
- Regular dependency updates

To check your installation:
```bash
pip install safety
safety check -r services/*/requirements.txt
```

---

## Questions?

For security questions (non-vulnerabilities):
- Open a [discussion](https://github.com/pruittcolon/NeMo_Server/discussions)
- Check documentation
- Email: [INSERT CONTACT EMAIL]

---

**Thank you for helping keep Nemo Server secure!** 🔒
