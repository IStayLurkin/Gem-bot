# Gem-bot Setup Checklist

## ✅ Immediate Next Steps

### Step 1: Create `.env` File
Create a file named `.env` in the root directory (`G:\GemBot\.env`) with:

```env
DISCORD_TOKEN=your_discord_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
TARGET_CHANNEL_ID=  # Optional: comma-separated channel IDs
ROUTER_MODEL=llama3
LOCAL_SD_ENABLED=false
```

**Where to get keys:**
- Discord Token: https://discord.com/developers/applications → Your Bot → Token
- Gemini API Key: https://makersuite.google.com/app/apikey

### Step 2: Install Ollama
The bot requires Ollama for LLM responses.

**Windows:**
1. Download: https://ollama.ai/download
2. Install and start Ollama
3. Run: `ollama pull llama3`

**Verify it works:**
```bash
curl http://localhost:11434/api/tags
```

### Step 3: Choose Your Deployment Method

**Option A: Docker (Easiest)**
```bash
docker compose up --build
```

**Option B: Local Python**
```bash
cd ai_container
pip install -r requirements.txt
python discord_bot.py
```

### Step 4: Test the Bot
1. Invite bot to Discord server
2. Send `!status` to check health
3. Ask a question - bot should respond

## 🔧 Optional: Enable Local GPU Image Generation

1. Download SDXL model (e.g., from HuggingFace)
2. Place in: `ai_container/models/sdxl/`
3. Update `.env`: `LOCAL_SD_ENABLED=true`
4. Restart bot

## 📦 Optional: Add Custom Plugins

1. Create a new `.py` file in `ai_container/plugins/`
2. Copy structure from `example_plugin.py`
3. Implement `register()` function
4. Restart bot - plugin auto-loads

## 🐛 Common Issues

| Issue | Solution |
|-------|----------|
| "DISCORD_TOKEN missing" | Create `.env` file with token |
| "Ollama not connected" | Start Ollama service |
| "No image generation" | Check SD_URL in logs or enable LOCAL_SD_ENABLED |
| Import errors | Run `pip install -r requirements.txt` |

## 📊 What's Working Now

✅ SQLite memory (auto-creates database)
✅ Plugin system (auto-discovers plugins)
✅ Tool system (web search, image gen, etc.)
✅ Docker deployment ready
✅ Local GPU support (if configured)

## 🎯 Quick Commands

```bash
# Start with Docker
docker compose up --build

# View logs
docker compose logs -f gem_ai

# Stop
docker compose down

# Rebuild after changes
docker compose up --build --force-recreate
```

