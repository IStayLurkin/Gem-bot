OmniBot v2.0 - Multi-Modal Tool Agent (Docker + Firebase)

This repository contains the full, modular code for a powerful AI assistant capable of persistent memory, multi-step tool execution, and multimodal communication (text, voice, vision, image generation).

The system runs on Windows (via Docker Desktop/WSL2) and uses local and cloud services simultaneously.

🧠 Architecture Overview

The system is split into multiple services:

gembot (Python Container): The core intelligence running discord_bot.py. It handles all reasoning, memory lookups, and tool coordination (Tool Agent).

omnibot-v2 (Nginx Container): Hosts the static web interface (index.html) for administration and a graphical chat interface.

Stable Diffusion (Native Windows): Handles local image generation for maximum GPU speed.

Firebase Firestore (Cloud): Stores shared, persistent Long-Term Memory (LTM) under the PRIMARY_USER ID.

⚙️ Setup and Configuration (CRITICAL)

Before building, you MUST configure your API keys and Firebase settings.

Step 1: Configure Secrets

Update the .env file in the root directory:

Variable

Source

Purpose

DISCORD_TOKEN

Discord Developer Portal

Bot connection

GEMINI_API_KEY

Google AI Studio

Search, Vision, TTS (Web/Python)

FIREBASE_API_KEY

Firebase Console (Web App Config)

Firestore REST API access

FIREBASE_PROJECT_ID

Firebase Console (Web App Config)

Identifies your database

Step 2: Configure Web Interface (omnibot-docker/index.html)

You must manually paste the secrets into the <script> tag inside index.html (since the browser cannot read .env).

Step 3: Database Preparation

Ensure a Native Firestore Database is created, and Anonymous Sign-in is enabled in the Firebase Console.

📦 File Structure

Directory/File

Purpose

discord_bot.py

Main Orchestrator. Handles Discord events and calls the Tool Agent.

tool_handlers.py

Contains all tool functions (e.g., generate_image, browse_website).

memory_db.py

Handles all CRUD operations with Firebase Firestore, using the hardcoded PRIMARY_USER ID for unified memory storage.

core.py

Contains the core query_llm function and configuration loader.

config.py

Global constants and environment variables.

gembot_views.py

Discord UI logic for interactive buttons.

omnibot-docker/

Contains the Dockerfile and index.html for the web server.

.dockerignore

Crucial for speed. Prevents large files (like Stable Diffusion) from being copied into the container during the build.

🚀 Launch Sequence (Windows)

Use the local launcher.bat script to start the entire system:

Build Images: Run this command first to ensure all modular files are compiled into the latest image:

docker build -t gembot .


Launch: Execute the launcher to start Stable Diffusion, the two containers, and open the web interface.

.\launcher.bat
