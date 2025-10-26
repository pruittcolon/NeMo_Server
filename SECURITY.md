# Security Policy

## 🔒 Security Features

Nemo Server implements multiple layers of security:

### Authentication & Authorization
- **Session-based authentication** with HTTP-only cookies
- **Bcrypt password hashing** (industry standard, salted)
- **Role-based access control** (Admin, User roles)
- **100% speaker-based data isolation** at SQL level
- **Job ownership tracking** for AI analysis tasks

### Rate Limiting
- **100 requests per minute per IP address** (configurable)
- Protects against brute force attacks
- Prevents API abuse

### Data Protection
- **Speaker isolation**: Users can only access their own speaker's data
- **Admin override**: Administrators can view all data for system management
- **Session expiry**: Automatic logout after 24 hours (configurable)

### Network Security
- **IP whitelisting** for Flutter app transcription endpoint
- **CORS configuration** for web security
- **Security headers** (X-Frame-Options, Content-Security-Policy)

---

## ⚠️ Known Limitations

### HTTP Only (No TLS/SSL)
**Current State**: The default configuration uses unencrypted HTTP.

**Risk**: Traffic between client and server is not encrypted, making it vulnerable to:
- Man-in-the-middle attacks
- Password interception
- Session hijacking on public networks

**Mitigation**: 
- Only use on trusted local networks
- Configure HTTPS with reverse proxy (Nginx/Caddy) for production
- Use Let's Encrypt for free SSL certificates

### Default Passwords
**Risk**: The system ships with default credentials:
- `admin` / `admin123`
- `user1` / `user1pass`
- `television` / `tvpass123`

**Mitigation**: **CHANGE ALL DEFAULT PASSWORDS IMMEDIATELY** in `src/auth/auth_manager.py`

### Database Encryption
**Current State**: SQLite database is stored in plaintext.

**Risk**: Anyone with file system access can read the database.

**Mitigation**:
- Restrict file permissions on `instance/` directory
- Consider encrypted file system for sensitive deployments
- Implement database-level encryption if needed

### Local Network Only
**Current State**: Designed for local network deployment.

**Risk**: Not hardened for internet exposure.

**Mitigation**: 
- **DO NOT expose port 8000 directly to the internet**
- Use VPN for remote access
- Implement additional firewall rules
- Consider adding API key authentication for production

---

## 🚨 Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please email: **[Your Email Here]** with:
1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if you have one)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Depends on severity
  - Critical: 1-3 days
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Next release cycle

### Disclosure Policy

- We follow **responsible disclosure** practices
- We will acknowledge your contribution in release notes (unless you prefer anonymity)
- We will notify you when the fix is released
- Please allow us to fix the issue before public disclosure

---

## 🛡️ Security Best Practices for Deployment

### For Development/Testing
✅ Use default configuration  
✅ Local network only  
✅ Default passwords acceptable  

### For Production
❌ Change ALL default passwords  
❌ Set `SECRET_KEY` and `DB_ENCRYPTION_KEY` environment variables  
❌ Configure HTTPS (Let's Encrypt + Nginx)  
❌ Restrict `FLUTTER_WHITELIST` to specific IPs  
❌ Enable firewall rules  
❌ Regular security updates  
❌ Monitor access logs  
❌ Implement backup strategy  

### Recommended Production Setup

```bash
# 1. Set strong secrets
export SECRET_KEY="$(openssl rand -hex 32)"
export DB_ENCRYPTION_KEY="$(openssl rand -hex 32)"

# 2. Configure whitelist
export FLUTTER_WHITELIST="192.168.1.100,192.168.1.101"

# 3. Use HTTPS reverse proxy
# (See docs/HTTPS_SETUP.md for Nginx configuration)

# 4. Restrict Docker container
# Run as non-root user
# Limit resource usage
```

---

## 📚 Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [Let's Encrypt](https://letsencrypt.org/)

---

## 🔄 Security Updates

We regularly review and update security measures. Check the [CHANGELOG](CHANGELOG.md) for security-related updates.

**Latest Security Review**: October 2025

---

## 📝 Security Audit Checklist

Before deploying to production:

- [ ] All default passwords changed
- [ ] `SECRET_KEY` set to random value
- [ ] `DB_ENCRYPTION_KEY` set to random value
- [ ] HTTPS configured and working
- [ ] `FLUTTER_WHITELIST` limited to specific IPs
- [ ] Firewall rules configured
- [ ] Security headers verified
- [ ] Rate limiting tested
- [ ] Speaker isolation verified (run `tests/test_security_comprehensive.sh`)
- [ ] Backup strategy implemented
- [ ] Monitoring and logging configured

---

**Remember**: Security is a continuous process, not a one-time setup. Regularly review and update your security measures.

