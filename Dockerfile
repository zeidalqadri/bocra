# BOCRA Backend Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-ara \
    tesseract-ocr-chi-sim \
    tesseract-ocr-fra \
    tesseract-ocr-deu \
    tesseract-ocr-spa \
    imagemagick \
    libpq-dev \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create directories
RUN mkdir -p /var/lib/bocra/storage \
    && mkdir -p /var/log/bocra \
    && chmod 755 /var/lib/bocra/storage \
    && chmod 755 /var/log/bocra

# Copy requirements and install Python dependencies
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ /app/backend/
COPY database/ /app/database/
COPY ocr_fulltext.py /app/

# Create __init__.py files for proper imports
RUN touch /app/__init__.py \
    && touch /app/backend/__init__.py

# Create non-root user for security
RUN groupadd -r bocra && useradd -r -g bocra bocra \
    && chown -R bocra:bocra /app /var/lib/bocra /var/log/bocra

# Switch to non-root user
USER bocra

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Command to run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]