# Use Python slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=audit_service.settings

# Use remote LanguageTool API (saves ~300MB memory by not needing Java)
ENV GRAMMAR_USE_REMOTE_API=true

# Set work directory
WORKDIR /app

# Install system dependencies (NO Java - using remote API instead)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For pdf2image (Poppler)
    poppler-utils \
    # For pytesseract (Tesseract OCR)
    tesseract-ocr \
    tesseract-ocr-eng \
    # Build essentials for Python packages
    build-essential \
    libffi-dev \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Tesseract and Poppler paths
ENV TESSERACT_CMD=/usr/bin/tesseract
ENV POPPLER_PATH=/usr/bin

# Set NLTK data path
ENV NLTK_DATA=/app/nltk_data

# Copy requirements first (for Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Download NLTK data during build (not runtime)
RUN python -c "import nltk; nltk.download('cmudict', download_dir='/app/nltk_data', quiet=True)" || true

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p /app/media /app/hashFiles /app/staticfiles

# Collect static files
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Expose port
EXPOSE 8000

# Run with gunicorn - memory optimized for free tier
# - Single worker to minimize memory
# - 2 threads for concurrent requests  
# - Long timeout for AI processing
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "300", "--worker-class", "gthread", "audit_service.wsgi:application"]
