# Contributing to Nemo Server

First off, thank you for considering contributing to Nemo Server! 🎉

Following these guidelines helps communicate that you respect the time of the developers managing and developing this open source project. In return, they should reciprocate that respect in addressing your issue, assessing changes, and helping you finalize your pull requests.

---

## 🌟 How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the issue list as you might find that you don't need to create one. When you are creating a bug report, please include as many details as possible using our [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).

**How to submit a good bug report:**

- Use a clear and descriptive title
- Describe the exact steps to reproduce the problem
- Provide specific examples to demonstrate the steps
- Describe the behavior you observed and what you expected
- Include logs, screenshots, or error messages
- Specify your environment:
  - OS (Ubuntu, Debian, etc.)
  - Python version
  - Docker version
  - GPU model and CUDA version
  - Docker Compose logs

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

- A clear and descriptive title
- A detailed description of the proposed functionality
- Explain why this enhancement would be useful
- List any alternative solutions you've considered

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following our code standards
3. **Test your changes** thoroughly
4. **Update documentation** if needed
5. **Submit a pull request** using our template

---

## 🔧 Development Setup

### Prerequisites

- Docker 24.0+
- Docker Compose
- NVIDIA GPU with CUDA 12.6+ (recommended)
- Git
- Python 3.12+ (for local development)

### Getting Started

1. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/NeMo_Server.git
   cd NeMo_Server
   ```

2. **Create a branch:**
   ```bash
   git checkout -b feature/my-new-feature
   # or
   git checkout -b fix/bug-description
   ```

3. **Set up development environment:**
   ```bash
   # Generate secrets
   cd docker/secrets
   bash generate_secrets.sh
   cd ../..
   
   # Start services
   ./start.sh
   ```

4. **Make your changes**

5. **Run tests:**
   ```bash
   # Run all tests (unit + smoke + security by default)
   ./scripts/run_tests.sh
   
   # Run specific tests
   pytest -m unit -v
   RUN_INTEGRATION=1 pytest -m integration -v
   pytest -m smoke -v
   ```

---

## 📝 Code Standards

### Python Code Style

- Follow [PEP 8](https://pep8.org/)
- Use type hints where appropriate
- Maximum line length: 120 characters
- Use meaningful variable and function names
- Add docstrings for all functions and classes

**Example:**
```python
def transcribe_audio(audio_file: bytes, enable_diarization: bool = True) -> TranscriptionResult:
    """
    Transcribe audio file with optional speaker diarization.
    
    Args:
        audio_file: Raw audio bytes
        enable_diarization: Whether to perform speaker diarization
        
    Returns:
        TranscriptionResult with text and segments
        
    Raises:
        AudioProcessingError: If audio format is invalid
    """
    pass
```

### Docker Best Practices

- Use multi-stage builds where appropriate
- Minimize layer count
- Don't include secrets in images
- Use specific version tags, not `latest`
- Document environment variables

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `ci`: CI/CD changes

**Examples:**
```
feat(transcription): add support for multiple languages

Implement language detection and multi-language transcription
using NeMo's multilingual models.

Closes #123
```

```
fix(api-gateway): resolve session timeout issue

Sessions were expiring too quickly due to incorrect TTL calculation.
Updated the session manager to use proper timestamp conversion.

Fixes #456
```

---

## 🧪 Testing Guidelines

### Writing Tests

- Write tests for all new features
- Update tests when modifying existing features
- Aim for >80% code coverage
- Use descriptive test names

**Test Structure:**
```python
def test_transcription_with_diarization():
    """Test that transcription correctly identifies multiple speakers."""
    # Arrange
    audio_file = load_test_audio("multi_speaker.wav")
    
    # Act
    result = transcribe(audio_file, enable_diarization=True)
    
    # Assert
    assert len(result.segments) > 0
    assert "SPEAKER_01" in [s.speaker for s in result.segments]
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=services --cov-report=html

# Specific service
pytest tests/unit/test_transcription.py

# Integration tests (requires running services)
pytest tests/integration/ --docker

# Security tests
./scripts/verify_security.py
```

---

## 📚 Documentation

### When to Update Documentation

- Adding new features
- Changing API endpoints
- Modifying configuration options
- Changing deployment procedures
- Adding new environment variables

### Documentation Locations

- **README.md**: Overview, quick start, main features
- **services/*/README.md**: Service-specific documentation
- **API changes**: Update service README with examples
- **Configuration**: Document in main README and service README

---

## 🔍 Code Review Process

1. **Automated checks must pass:**
   - CI/CD pipeline
   - Code style checks
   - Security scans
   - Test coverage

2. **Maintainer review:**
   - Code quality
   - Design patterns
   - Performance implications
   - Security considerations

3. **Changes requested:**
   - Address all feedback
   - Push additional commits
   - Request re-review

4. **Approval and merge:**
   - Squash and merge (usually)
   - Descriptive merge commit message

---

## 🏷️ Branch Naming

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions/updates
- `chore/` - Maintenance tasks

Examples:
- `feature/multi-language-support`
- `fix/session-timeout-bug`
- `docs/update-api-examples`

---

## 🐛 Issue Labels

- `bug` - Something isn't working
- `enhancement` - New feature or request
- `documentation` - Documentation improvements
- `good first issue` - Good for newcomers
- `help wanted` - Extra attention needed
- `priority: high` - High priority
- `priority: medium` - Medium priority
- `priority: low` - Low priority
- `wontfix` - Won't be worked on
- `duplicate` - Duplicate issue

---

## 💡 Questions?

- Open a [discussion](https://github.com/pruittcolon/NeMo_Server/discussions)
- Ask in an issue
- Check existing documentation

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## 🙏 Thank You!

Your contributions make Nemo Server better for everyone! 

**Hall of Fame:** Check out our [Contributors](https://github.com/pruittcolon/NeMo_Server/graphs/contributors)! ⭐
