# Gem-bot Quick Start Guide

## 🚀 Next Steps to Get Running

### 1. Create Environment File

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Then edit `.env` with your actual values:
- **DISCORD_TOKEN**: Get from https://discord.com/developers/applications
- **GEMINI_API_KEY**: Get from https://makersuite.google.com/app/apikey
- **TARGET_CHANNEL_ID**: Optional - Discord channel IDs where bot should respond (comma-separated)

### 2. Set Up Ollama (Required for LLM)

The bot uses Ollama for LLM responses. Install and run:

**Windows:**
- Download from https://ollama.ai/download
- Run: `ollama pull llama3`
- Start Ollama service

**Docker:**
```bash
docker run -d -p 11434:11434 ollama/ollama
docker exec -it <container> ollama pull llama3
```

### 3. Optional: Set Up Stable Diffusion (for Image Generation)

**Option A: Use Remote Stable Diffusion WebUI**
- If you have `stable-diffusion-webui` running locally on port 7860, the bot will auto-discover it
- No additional setup needed

**Option B: Use Local GPU Generation**
1. Place SDXL model files in `ai_container/models/sdxl/`
2. Set in `.env`: `LOCAL_SD_ENABLED=true`
3. Install PyTorch with CUDA support (already in requirements.txt)

### 4. Run the Bot

**Option A: Docker (Recommended)**
```bash
docker compose up --build
```

**Option B: Local Python**
```bash
cd ai_container
pip install -r requirements.txt
python discord_bot.py
```

### 5. Test the Bot

1. Invite your bot to a Discord server
2. Mention the bot or send a message in configured channels
3. Try commands:
   - `!status` - Check system health
   - Ask questions - Bot will use tools automatically
   - Request images - Bot will generate using available services

## 📁 Project Structure

```
GemBot/
├── ai_container/          # Main bot code
│   ├── plugins/           # Drop custom plugins here
│   ├── models/            # Place SDXL models here (if using local GPU)
│   └── generated/         # Generated images stored here
├── docker-compose.yml      # Docker orchestration
└── .env                   # Your API keys (create from .env.example)
```

## 🔧 Configuration Options

### Memory System
- Uses SQLite by default (no setup needed)
- Database: `ai_container/gem_memory.db`
- Automatically created on first run

### Plugin System
- Drop `.py` files in `ai_container/plugins/`
- Each plugin needs a `register()` function
- See `plugins/example_plugin.py` for template

### Tool System
Available tools (auto-discovered):
- `search_web` - Web search via Gemini
- `browse_website` - Read URL content
- `generate_image` - Remote SD API
- `generate_image_local` - Local GPU (if enabled)
- `execute_python_code` - Safe code execution
- Plus any plugins you add

## 🐛 Troubleshooting

**Bot won't start:**
- Check `.env` file exists and has DISCORD_TOKEN
- Verify Ollama is running: `curl http://localhost:11434/api/tags`

**No image generation:**
- Check if SD_URL is found (bot logs will show)
- For local GPU: verify model files in `ai_container/models/sdxl/`
- Check `LOCAL_SD_ENABLED=true` in `.env` if using local

**Memory not working:**
- SQLite database auto-creates
- Check file permissions on `ai_container/gem_memory.db`

**Plugins not loading:**
- Check plugin has `register()` function
- Check console logs for plugin load errors
- Verify plugin file is in `ai_container/plugins/`

## 📝 Notes

- Old files (`bot.py`, root `config.py`, etc.) are kept for reference but not used
- The new structure uses `ai_container/` for all bot code
- SQLite replaces Firestore - no cloud setup needed
- All dependencies are in `requirements.txt`

## 🎯 What's New

✅ SQLite memory (no Firestore needed)
✅ Local GPU image generation support
✅ Plugin system for extensibility
✅ Clean Docker deployment
✅ Modular architecture

