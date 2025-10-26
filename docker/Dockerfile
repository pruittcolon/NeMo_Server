FROM nvidia/cuda:12.6.2-cudnn-runtime-ubuntu24.04

# Install Python 3.10 from deadsnakes PPA
RUN apt-get update && apt-get install -y \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    build-essential \
    gcc g++ make git \
    ffmpeg \
    libsndfile1 libsndfile1-dev \
    libsox-dev libsox-fmt-all sox \
    openjdk-17-jre-headless \
    curl wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set Python 3.10 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Step 1: Upgrade pip (ignore system pip)
RUN python3 -m pip install --upgrade pip --break-system-packages --ignore-installed pip

# Step 2: CRITICAL - Install OLD setuptools for NeMo legacy dependencies
RUN python3 -m pip install "setuptools<58" wheel --break-system-packages

# Step 3: Filter and install NeMo + dependencies (works with old setuptools)
RUN grep -v "^llama-cpp-python" requirements.txt > /tmp/requirements_filtered.txt && \
    python3 -m pip install --no-cache-dir -r /tmp/requirements_filtered.txt --break-system-packages

# Step 4: Upgrade setuptools back to latest for security
RUN python3 -m pip install --upgrade setuptools --break-system-packages

# Step 5: Install pre-built wheel (GLIBC 2.39 compatible)
COPY llama_cpp_python-*.whl /tmp/
RUN python3 -m pip install --no-cache-dir /tmp/llama_cpp_python-*.whl --break-system-packages && \
    rm /tmp/llama_cpp_python-*.whl

# Step 6: Copy Parakeet TDT 0.6B V2 model (2.4GB) - now in models/
# Will be available via volume mount at /app/models/parakeet-tdt-0.6b-v2.nemo

# Runtime verification - confirm all critical imports work
RUN python3 -c "import sys; print(f'✅ Python {sys.version}')" && \
    python3 -c "import nemo; print('✅ NeMo imported successfully')" && \
    python3 -c "import torch; print(f'✅ PyTorch {torch.__version__}')" && \
    (python3 -c "import llama_cpp; print(f'✅ llama-cpp-python {llama_cpp.__version__}')" 2>&1 | grep -q "llama-cpp-python" || \
     echo "⚠️  llama_cpp import skipped (libcuda.so.1 not available at build time - will verify at runtime)") && \
    echo "✅ Build verification complete"

# Copy application code
COPY src /app/src
COPY frontend /app/frontend

# Set environment
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
