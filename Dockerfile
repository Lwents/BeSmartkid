# Multi-stage build để giảm kích thước image
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libtiff-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy file requirements trước để tận dụng cache
COPY requirements.txt .

# Cài dependencies vào /install
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage
FROM python:3.12-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    libjpeg62-turbo \
    zlib1g \
    libpng16-16 \
    libfreetype6 \
    liblcms2-2 \
    libtiff6 \
    libwebp7 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && pip install --no-cache-dir yt-dlp

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Set working directory
WORKDIR /app

# Copy toàn bộ project vào container (exclude unnecessary files)
COPY --chown=nobody:nogroup . .

# Tạo thư mục logs và file log
RUN mkdir -p /app/logs /app/staticfiles /app/media /app/runtime_logs && \
    touch /app/logs/ai_personalization.log && \
    chown -R nobody:nogroup /app/logs /app/staticfiles /app/media /app/runtime_logs

# Remove unnecessary files to reduce image size
RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find . -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find . -type f -name "*.pyo" -delete 2>/dev/null || true && \
    rm -rf .git .github tests */tests *.md 2>/dev/null || true

# Switch to non-root user for security
USER nobody

# Expose port 8000 cho Django
EXPOSE 8000

# Biến môi trường cơ bản
ENV DJANGO_SETTINGS_MODULE=backend.settings
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/admin/ || exit 1

# Command mặc định (production dùng gunicorn)
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
