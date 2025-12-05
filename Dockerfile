# We switch to the official Playwright image which has browsers pre-installed
FROM mcr.microsoft.com/playwright/python:v1.56.0-jammy

# Set working directory to /bot
WORKDIR /bot

# 1. Install system-level 'whois' tool
RUN apt-get update && apt-get install -y whois

# 2. Install Python dependencies
RUN pip install discord.py[voice] aiohttp python-dotenv beautifulsoup4 python-whois phonenumbers playwright

# Set Docker flag
ENV IS_DOCKER=true

# --- FIX: Package Initialization File ---
# NOTE: Keeping this file is technically correct for package structure, but we rely on absolute imports now.
COPY __init__.py .
# ----------------------------------------

# Copy all modular Python files and configuration into /bot
COPY discord_bot.py .
COPY gembot_views.py .
COPY config.py .
COPY core.py .
COPY memory_db.py .
COPY tool_handlers.py .

COPY .env .

# Run the bot with unbuffered output (-u) so logs show up instantly
CMD ["python", "-u", "discord_bot.py"]