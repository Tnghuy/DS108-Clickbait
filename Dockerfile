# Stage 1: Builder
# Compiles dependencies and builds wheels
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies needed for compiling C extensions (e.g. for lxml, newspaper3k)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies manifest
COPY requirements.txt /app/

# Install python dependencies to the user directory (/root/.local)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt


# Stage 2: Runner
# Final lightweight runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH=/root/.local/bin:$PATH
ENV OLLAMA_HOST=http://host.docker.internal:11434

# Copy only the compiled Python site-packages from the builder stage
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY . /app/

# Create required runtime directories for data and logging
RUN mkdir -p /app/data /app/logs /app/data/final/figures

# Expose Jupyter notebook port
EXPOSE 8888

# Default command runs the validation test suite
CMD ["python", "src/evaluation/run_tests.py"]
