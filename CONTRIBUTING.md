# Contributing to Nemo Server

Thank you for your interest in contributing to Nemo Server! This document provides guidelines and instructions for contributing.

---

## 🎯 Ways to Contribute

- **Bug Reports**: Found a bug? Let us know!
- **Feature Requests**: Have an idea? We'd love to hear it!
- **Code Contributions**: Want to fix or improve something? Pull requests welcome!
- **Documentation**: Help improve our docs
- **Testing**: Test new features and report issues
- **Translation**: Help translate the UI (future feature)

---

## 🐛 Reporting Bugs

Before creating a bug report:
1. Check existing issues to avoid duplicates
2. Update to the latest version
3. Test with a clean install if possible

When reporting bugs, include:
- **Clear title** describing the issue
- **Steps to reproduce** the bug
- **Expected behavior** vs **actual behavior**
- **Environment**:
  - OS and version
  - Python version
  - Docker version
  - GPU model and CUDA version
  - Browser (for frontend issues)
- **Logs**: Include relevant error messages
- **Screenshots**: If applicable

---

## 💡 Feature Requests

We welcome feature requests! Please include:
- **Clear description** of the feature
- **Use case**: Why is this feature needed?
- **Proposed implementation**: If you have ideas
- **Alternatives considered**: Other solutions you've thought about

---

## 🔧 Development Setup

### Prerequisites
- Python 3.10+
- Docker & Docker Compose
- NVIDIA GPU with CUDA support (for GPU features)
- Git

### Setup Instructions

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/Nemo_Server.git
cd Nemo_Server

# 2. Create environment file
cp .env.example .env
# Edit .env with your settings

# 3. Build and run with Docker
cd docker
docker compose build
docker compose up -d

# 4. Verify installation
docker logs nemo_server
curl http://localhost:8000/health
```

### Development Without Docker

```bash
# 1. Create virtual environment
python3.10 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Download models (see README.md)

# 4. Run server
cd src
python main.py
```

---

## 📝 Pull Request Process

### Before Submitting

1. **Create an issue** first to discuss major changes
2. **Fork the repository** and create a branch
3. **Follow code style** (PEP 8 for Python)
4. **Write tests** for new features
5. **Update documentation** if needed
6. **Test your changes** thoroughly

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring

### Commit Messages

Use clear, descriptive commit messages:

```
Good:
✅ Add speaker enrollment API endpoint
✅ Fix authentication bypass vulnerability
✅ Update README with installation steps

Bad:
❌ Update code
❌ Fix bug
❌ Changes
```

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] New tests added
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No new warnings
- [ ] Ready for review
```

---

## 🧪 Testing

### Run All Tests

```bash
# Security tests
./tests/test_security_comprehensive.sh

# Python tests
pytest tests/

# Smoke test
./tests/smoke_test.sh
```

### Writing Tests

- Place tests in `tests/` directory
- Follow existing test patterns
- Test both success and failure cases
- Mock external dependencies

Example:
```python
def test_speaker_isolation():
    """Test that users can only see their speaker's data"""
    # Test implementation
    pass
```

---

## 📚 Documentation Guidelines

- Use clear, concise language
- Include code examples
- Add screenshots for UI features
- Keep README.md up to date
- Document API changes

---

## 🎨 Code Style

### Python
- Follow **PEP 8**
- Use **type hints** where possible
- Document functions with docstrings
- Keep functions focused and small

Example:
```python
def process_audio(
    audio_path: str,
    sample_rate: int = 16000
) -> Dict[str, Any]:
    """
    Process audio file for transcription.
    
    Args:
        audio_path: Path to audio file
        sample_rate: Target sample rate in Hz
        
    Returns:
        Dictionary with processed audio data
    """
    pass
```

### JavaScript/HTML/CSS
- Use **consistent indentation** (2 spaces)
- Use **meaningful variable names**
- Add comments for complex logic
- Follow existing code patterns

---

## 🔍 Code Review Process

All submissions require review. We aim to:
- Provide feedback within 3-5 days
- Be constructive and respectful
- Explain reasoning for changes
- Help you improve your contribution

### What We Look For
- ✅ Code quality and readability
- ✅ Test coverage
- ✅ Documentation
- ✅ Performance impact
- ✅ Security implications
- ✅ Backward compatibility

---

## 🚫 What We Don't Accept

- Code that breaks existing functionality
- Contributions without tests
- Plagiarized code
- Code with security vulnerabilities
- Changes that significantly degrade performance
- Contributions that don't follow our code style

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## 💬 Communication

- **GitHub Issues**: For bugs and features
- **Pull Requests**: For code contributions
- **Discussions**: For questions and ideas (if enabled)

---

## 🙏 Recognition

Contributors will be:
- Listed in release notes
- Added to CONTRIBUTORS.md (if significant contribution)
- Mentioned in relevant documentation

---

## ❓ Questions?

Not sure about something? Feel free to:
- Open an issue with your question
- Check existing issues for answers
- Review documentation in `docs/` directory

---

Thank you for contributing to Nemo Server! 🎉

