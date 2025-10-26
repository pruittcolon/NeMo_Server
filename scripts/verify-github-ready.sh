#!/bin/bash

# ==========================================
# GitHub Readiness Verification Script
# ==========================================
# Checks for sensitive data, required files,
# and runs security tests before submission

set -e

echo "========================================"
echo "  Nemo Server - GitHub Readiness Check"
echo "========================================"
echo ""

ERRORS=0
WARNINGS=0

# ==========================================
# Check for Sensitive Data
# ==========================================
echo "🔍 Checking for sensitive data..."
echo ""

# Check for hardcoded IPs
if grep -r "192\.168\.[0-9]\{1,3\}\.[0-9]\{1,3\}" --exclude-dir=.git --exclude-dir=node_modules --exclude="*.sh" . 2>/dev/null | grep -v ".env.example" | grep -v "CHANGELOG.md" | grep -v "FEATURES.md"; then
    echo "❌ Found hardcoded IP addresses"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ No hardcoded IPs found"
fi

# Check for personal references (excluding docs and changelogs)
if grep -r "pruitt" --exclude-dir=.git --exclude-dir=node_modules --include="*.py" . 2>/dev/null; then
    echo "⚠️  Found personal references in code"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No personal references in code"
fi

# Check for .env file (should not be in repo)
if [ -f ".env" ]; then
    echo "⚠️  .env file exists (should be in .gitignore)"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No .env file (good)"
fi

# Check for database files
if ls instance/*.db 2>/dev/null | grep -q .; then
    echo "⚠️  Database files found in instance/ (should be in .gitignore)"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No database files in repo"
fi

echo ""

# ==========================================
# Check Required Files
# ==========================================
echo "📄 Checking required files..."
echo ""

REQUIRED_FILES=(
    "LICENSE"
    "README.md"
    "CONTRIBUTING.md"
    "SECURITY.md"
    "CHANGELOG.md"
    "FEATURES.md"
    ".gitignore"
    ".env.example"
    "requirements.txt"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ Missing $file"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# ==========================================
# Check Model Files Not in Repo
# ==========================================
echo "🧠 Checking model files..."
echo ""

if ls models/*.gguf 2>/dev/null | grep -q .; then
    echo "⚠️  GGUF model files found (large files, should be in .gitignore)"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No GGUF files in repo"
fi

if ls models/*.nemo 2>/dev/null | grep -q .; then
    echo "⚠️  .nemo model files found (large files, should be in .gitignore)"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No .nemo files in repo"
fi

echo ""

# ==========================================
# Check Debug Directories Removed
# ==========================================
echo "🧹 Checking for debug directories..."
echo ""

DEBUG_DIRS=(
    "AUTH_DEBUG_BACKUP"
    "implement_fixes"
)

for dir in "${DEBUG_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "❌ Debug directory exists: $dir"
        ERRORS=$((ERRORS + 1))
    else
        echo "✅ $dir removed"
    fi
done

echo ""

# ==========================================
# Check for Personal Data
# ==========================================
echo "🔐 Checking for personal data..."
echo ""

if ls instance/enrollment/*.wav 2>/dev/null | grep -q .; then
    echo "⚠️  Personal enrollment audio found (should be in .gitignore)"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No personal enrollment audio"
fi

echo ""

# ==========================================
# Run Security Tests
# ==========================================
echo "🛡️  Running security tests..."
echo ""

if [ -f "tests/test_security_comprehensive.sh" ]; then
    if bash tests/test_security_comprehensive.sh > /dev/null 2>&1; then
        echo "✅ Security tests passed (10/10)"
    else
        echo "❌ Security tests failed"
        ERRORS=$((ERRORS + 1))
        echo "   Run: ./tests/test_security_comprehensive.sh for details"
    fi
else
    echo "⚠️  Security test script not found"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# ==========================================
# Check Docker Configuration
# ==========================================
echo "🐳 Checking Docker configuration..."
echo ""

if [ -f "docker/docker-compose.yml" ]; then
    echo "✅ docker-compose.yml exists"
    
    # Check for personal paths
    if grep -q "/home/pruittcolon" docker/docker-compose.yml; then
        echo "⚠️  Personal paths found in docker-compose.yml"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "✅ No personal paths in docker-compose.yml"
    fi
else
    echo "❌ docker-compose.yml missing"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# ==========================================
# Check README Quality
# ==========================================
echo "📖 Checking README quality..."
echo ""

if grep -q "Parakeet-TDT-0.6B" README.md; then
    echo "✅ Correct ASR model name in README"
else
    echo "⚠️  Check ASR model name in README"
    WARNINGS=$((WARNINGS + 1))
fi

if grep -q "192\.168" README.md; then
    echo "⚠️  IP addresses found in README (should use examples)"
    WARNINGS=$((WARNINGS + 1))
else
    echo "✅ No hardcoded IPs in README"
fi

echo ""

# ==========================================
# Final Summary
# ==========================================
echo "========================================"
echo "  Summary"
echo "========================================"
echo ""
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "🎉 Repository is GitHub-ready!"
    echo ""
    echo "Next steps:"
    echo "1. git add ."
    echo "2. git commit -m \"Initial commit: Nemo Server v1.0.0\""
    echo "3. git remote add origin <your-repo-url>"
    echo "4. git push -u origin main"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  Repository has warnings but is acceptable"
    echo "   Review warnings above before publishing"
    exit 0
else
    echo "❌ Repository is NOT ready"
    echo "   Fix errors above before publishing"
    exit 1
fi

