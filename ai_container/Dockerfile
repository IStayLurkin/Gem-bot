# Base image with Python and Playwright
FROM mcr.microsoft.com/playwright/python:v1.56.0-jammy

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    whois \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Set Docker flag
ENV IS_DOCKER=true

# Copy all application files
COPY discord_bot.py .
COPY gembot_views.py .
COPY config.py .
COPY core.py .
COPY memory_db.py .
COPY tool_handlers.py .
COPY local_image_gen.py .

# Copy plugins directory
COPY plugins/ ./plugins/

# Create directories for models and generated images
RUN mkdir -p models generated

# Copy .env file if it exists (optional - can also use docker-compose env vars)
# COPY .env .env

# Run the bot with unbuffered output (-u) so logs show up instantly
CMD ["python", "-u", "discord_bot.py"]

