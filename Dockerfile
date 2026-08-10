# Use official slim Python base image
FROM python:3.11-slim

# Set system environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency configuration
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the necessary backend files for production execution
COPY app.py bot.py responses.json ./
COPY frontend/faq.html ./frontend/faq.html

# Expose the default port (Render overrides this via the PORT environment variable)
EXPOSE 5000

# Run FastAPI app using Uvicorn
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT}
