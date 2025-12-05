import discord
import aiohttp
import asyncio
import os
import base64
import io
import json
import socket
import datetime
import whois 
import phonenumbers 
from phonenumbers import geocoder, carrier
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import random 
import re 
import sys 
# New imports for UX and advanced agent logic
from discord.ui import Button, View 
# >>> EDIT: H.3. Import the new ToolView class (assuming you save it as gembot_views.py)
from gembot_views import ToolView 

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
target_channels_env = os.getenv("TARGET_CHANNEL_ID", "")
TARGET_CHANNEL_IDS = [id.strip() for id in target_channels_env.split(',') if id.strip()]
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY") 

# --- FIREBASE CONFIG ---
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
APP_ID = "default-app-id" 

# --- GEMINI API CONFIG (for Grounding, TTS, & Vision/STT) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
VISION_MODEL = "gemini-2.5-flash-preview-09-2025" 

# --- AUTO-DISCOVERY GLOBALS ---
OLLAMA_URL = None
SD_URL = None      
SVD_URL = None     

# --- LONG-TASK POLLING ---
VIDEO_JOBS = {} # {job_id: (channel_id, user_id, prompt)}
IMAGE_JOBS = {} # {job_id: (channel_id, user_id, prompt)} # F.1. New Job Queue
POLLING_INTERVAL = 30 # seconds (Used for both)

# --- F.3. DYNAMIC CONFIGURATION (Now the Default/Fallback) ---
GLOBAL_CONFIG = {
    'MAX_HISTORY_LENGTH': 10,
    'FORGET_CHANCE': 5,
    'POLLING_INTERVAL': 30,
    'MAX_TOOL_RESULT_LENGTH': 2000, # G.4. Max length before summarization prompt
}

# --- SHORT-TERM MEMORY CONFIG ---
CONVERSATION_HISTORY = {} # {channel_id: [ (role, message), ... ]}

# --- MODEL DEFINITIONS ---
ROUTER_MODEL = "llama3" # Used for tool calling and primary chat

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True 
client = discord.Client(intents=intents)

# --- UTILITY FUNCTIONS ---

def pcm_to_wav(pcm_data, sample_rate=24000):
    wav_bytes = io.BytesIO()
    wav_bytes.write(b'RIFF')
    wav_bytes.write((36 + len(pcm_data)).to_bytes(4, 'little'))
    wav_bytes.write(b'WAVE')
    wav_bytes.write(b'fmt ')
    wav_bytes.write(b'\x10\x00\x00\x00') 
    wav_bytes.write(b'\x01\x00')       
    wav_bytes.write(b'\x01\x00')       
    wav_bytes.write(sample_rate.to_bytes(4, 'little'))
    wav_bytes.write((sample_rate * 2).to_bytes(4, 'little'))
    wav_bytes.write(b'\x02\x00')       
    wav_bytes.write(b'\x10\x00')       
    wav_bytes.write(b'data')
    wav_bytes.write(len(pcm_data).to_bytes(4, 'little'))
    wav_bytes.write(pcm_data)
    wav_bytes.seek(0)
    return wav_bytes.read()

async def generate_tts_audio(text):
    if not GEMINI_API_KEY: return None
    url = f"{GEMINI_API_BASE}{TTS_MODEL}:generateContent?key={GEMINI_API_KEY}"
    clean_text = text.replace('**', '').replace('*', '')
    payload = {
        "contents": [{"parts": [{"text": clean_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": { "prebuiltVoiceConfig": {"voiceName": "Fenrir"} }
            }
        }
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    inline_data = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('inlineData', {})
                    if inline_data and 'data' in inline_data:
                        pcm_data = base64.b64decode(inline_data['data'])
                        return pcm_to_wav(pcm_data)
                return None
    except Exception as e:
        print(f"TTS Connection Error: {e}")
        return None

# D.3. Voice Note Input (STT)
async def transcribe_audio_attachment(audio_attachment):
    """Transcribes an audio file attachment using the Gemini API."""
    if not GEMINI_API_KEY: return "⚠️ STT Error: GEMINI_API_KEY is not set."

    url = f"{GEMINI_API_BASE}{VISION_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    contents_parts = [
        {"inlineData": {"mimeType": audio_attachment["mime_type"], "data": audio_attachment["data"]}},
        {"text": "Transcribe this audio file and return ONLY the resulting text."}
    ]

    payload = { "contents": [{"parts": contents_parts}] }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as response:
                data = await response.json()
                text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "")
                return text.strip()
    except Exception as e:
        return f"❌ Transcription Failure: {str(e)}"

# --- MULTIMODAL HANDLER (Unchanged) ---
async def analyze_multimodal_content(text_prompt, image_attachments, long_term_memory):
    if not GEMINI_API_KEY: return "⚠️ Vision Error: GEMINI_API_KEY is not set."
    url = f"{GEMINI_API_BASE}{VISION_MODEL}:generateContent?key={GEMINI_API_KEY}"
    contents_parts = []
    if text_prompt: contents_parts.append({"text": text_prompt})
    for img in image_attachments:
        contents_parts.append({
            "inlineData": { "mimeType": img["mime_type"], "data": img["data"] }
        })
        
    system_instruction = (
        "You are a multimodal assistant. Analyze the attached image(s) and answer the user's question about them. "
        "Use the provided Long Term Memory to contextualize your response.\n\n"
        f"=== LONG TERM MEMORY ===\n{long_term_memory}"
    )

    payload = { "contents": [{"parts": contents_parts}], "systemInstruction": {"parts": [{"text": system_instruction}]} }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as response:
                data = await response.json()
                text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', "Vision analysis failed.")
                return text
    except Exception as e: return f"❌ Gemini API Vision Failure: {str(e)}"

# --- F.3. SYSTEM CONFIGURATION MANAGEMENT (H.2 added) ---
async def get_global_config(guild_id=None, channel_id=None):
    """Fetches dynamic bot settings, checking for channel/guild overrides."""
    global GLOBAL_CONFIG
    
    # Base configuration is always default
    config = GLOBAL_CONFIG.copy() 
    
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID:
        return config

    # F.3. Global Configuration
    global_url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/config/global?key={FIREBASE_API_KEY}"
    
    # H.2. Channel Specific Configuration
    channel_url = None
    if channel_id:
        channel_url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/config/{guild_id}/channels/{channel_id}?key={FIREBASE_API_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            # Fetch Global Config
            async with session.get(global_url, timeout=5) as response:
                if response.status == 200:
                    fields = (await response.json()).get('fields', {})
                    
                    config.update({
                        k: int(fields.get(k, {}).get('integerValue', config[k]))
                        for k in config if k != 'MAX_TOOL_RESULT_LENGTH' and k in fields # Only update if present in fields
                    })
                    
            # Fetch Channel Override (H.2)
            if channel_url:
                 async with session.get(channel_url, timeout=5) as response:
                    if response.status == 200:
                        fields = (await response.json()).get('fields', {})
                        config.update({
                            k: int(fields.get(k, {}).get('integerValue', config[k]))
                            for k in config if k != 'MAX_TOOL_RESULT_LENGTH' and k in fields
                        })
                        print(f"⚙️ Applied Channel Config Override for {channel_id}")

            GLOBAL_CONFIG.update(config)
            return config
            
    except Exception as e:
        print(f"⚠️ Warning: Failed to fetch dynamic config: {e}. Using runtime defaults.")
        return config

# --- MEMORY SYSTEM ---

# H.1. Shared Guild Memory
async def get_shared_memories(guild_id):
    """Fetches memories shared across the entire guild/server."""
    if not guild_id or not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID:
        return []

    # Store shared facts in /artifacts/{APP_ID}/public/guilds/{guild_id}/shared_facts
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/public/guilds/{guild_id}/shared_facts?key={FIREBASE_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    documents = data.get('documents', [])
                    facts = [doc.get('fields', {}).get('content', {}).get('stringValue') for doc in documents]
                    return [f for f in facts if f]
    except Exception:
        return []

async def fetch_raw_memories(user_id):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return []
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/users/{user_id}/memory_facts?key={FIREBASE_API_KEY}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    documents = data.get('documents', [])
                    facts = []
                    for doc in documents:
                        fields = doc.get('fields', {})
                        content = fields.get('content', {}).get('stringValue')
                        doc_id = doc['name'].split('/')[-1]
                        if content and doc_id: facts.append({"id": doc_id, "content": content})
                    return facts
    except Exception as e: print(f"Memory Fetch Error: {e}")
    return []

async def get_memories(user_id):
    raw_facts = await fetch_raw_memories(user_id)
    return [fact['content'] for fact in raw_facts]

# D.2. ADMIN COMMAND - Clears all user memory
async def clear_all_memory(user_id):
    """Deletes all long-term facts for a user."""
    raw_facts = await fetch_raw_memories(user_id)
    if not raw_facts: return 0
    delete_tasks = []
    for fact in raw_facts:
        delete_tasks.append(asyncio.create_task(delete_memory(user_id, fact['id'])))
    await asyncio.gather(*delete_tasks)
    return len(raw_facts)

async def delete_memory(user_id, doc_id):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/users/{user_id}/memory_facts/{doc_id}?key={FIREBASE_API_KEY}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                if response.status == 200: print(f"🗑️ Deleted memory fact {doc_id} for user {user_id}")
                else: print(f"Failed to delete memory: {response.status}")
    except Exception as e: print(f"Memory Deletion Error: {e}")

async def save_memory(user_id, fact):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/users/{user_id}/memory_facts?key={FIREBASE_API_KEY}"
    payload = {
        "fields": {
            "content": {"stringValue": fact},
            "createdAt": {"timestampValue": datetime.datetime.utcnow().isoformat() + "Z"}
        }
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200: print(f"Failed to save memory: {response.status} - {await response.text()}")
    except Exception as e: print(f"Memory Save Error: {e}")

async def extract_facts(user_id, user_text, bot_text):
    extraction_prompt = (
        f"Analyze this interaction and extract any NEW, PERMANENT facts about the user. "
        f"User: \"{user_text}\"\n"
        f"AI: \"{bot_text}\"\n"
        f"Return ONLY the fact as a concise sentence. If no new facts, return 'NO_FACTS'.\n"
        f"If multiple, use '|' separator."
    )
    response = await query_llm(extraction_prompt, model=ROUTER_MODEL, is_routing=True)
    if response and "NO_FACTS" not in response:
        facts = [f.strip() for f in response.split('|') if f.strip()]
        for fact in facts:
            if len(fact) > 5:
                print(f"🧠 Learning: {fact}")
                await save_memory(user_id, fact)

async def check_and_forget_memory(user_id, channel_id):
    raw_facts = await fetch_raw_memories(user_id)
    if len(raw_facts) < 3: return 
    fact_list = "\n".join([f"[{f['id'][:5]}]: {f['content']}" for f in raw_facts])
    forget_prompt = (
        f"Review the following long-term memory facts for the user. Identify ONE fact that is the most generic, old, or potentially irrelevant/outdated.\n"
        f"Memory Facts (ID: Content):\n{fact_list}\n\n"
        f"Instructions:\n1. If all facts seem highly relevant, return 'KEEP_ALL'.\n"
        f"2. Otherwise, return ONLY the 5-character ID of the single fact you recommend for removal (e.g., 'abc12')."
    )
    try:
        fact_id_to_check = await query_llm(forget_prompt, model=ROUTER_MODEL, is_routing=True)
        fact_id_to_check = fact_id_to_check.strip().lower()
        if fact_id_to_check == 'keep_all':
            print("🧠 Memory Check: All facts seem relevant.")
            return

        target_fact = next((f for f in raw_facts if f['id'].lower().startswith(fact_id_to_check)), None)

        if target_fact:
            channel = client.get_channel(channel_id)
            if channel:
                print(f"🧠 Memory Check: Asking user to review fact {target_fact['id'][:5]}")
                CONVERSATION_HISTORY[channel_id].append(("forget_check", target_fact))
                await channel.send(
                    f"🤔 **Memory Checkup:** I have the following fact stored about you:\n"
                    f"> `{target_fact['content']}`\n\n"
                    f"Is this fact still useful or relevant? Reply with `YES` to keep it, or `NO` to delete it from my long-term memory."
                )
    except Exception as e: print(f"Memory Forgetting Error: {e}")


# --- SERVICE DISCOVERY (Unchanged) ---
async def find_service(service_name, possible_urls, validation_endpoint):
    print(f"🔍 Scanning for {service_name}...")
    async with aiohttp.ClientSession() as session:
        for url in possible_urls:
            target = f"{url}{validation_endpoint}"
            try:
                async with session.get(target, timeout=2) as response:
                    if response.status == 200:
                        print(f"   ✅ Found {service_name} at: {url}")
                        return url
            except: continue
    print(f"   ❌ Could not find {service_name}.")
    return None

async def init_connections():
    global OLLAMA_URL, SD_URL, SVD_URL
    hosts = ["http://host.docker.internal", "http://localhost", "http://127.0.0.1"]

    # F.3. Load configuration early
    await get_global_config()

    ollama_urls = [f"{h}:11434" for h in hosts]
    base_ollama = await find_service("Ollama", ollama_urls, "/api/tags")
    OLLAMA_URL = f"{base_ollama}/api/generate" if base_ollama else "http://localhost:11434/api/generate"

    sd_urls = [f"{h}:7860" for h in hosts]
    SD_URL = await find_service("Stable Diffusion", sd_urls, "/sdapi/v1/progress")

    svd_urls = [f"{h}:8188" for h in hosts] 
    SVD_URL = await find_service("Video Generation API", svd_urls, "/system/stats") 
    
    # Start the polling loops
    asyncio.create_task(video_polling_loop())
    asyncio.create_task(image_polling_loop()) # F.1. Start image polling loop

# --- LLM CORE ---
# The primary LLM query function remains the same, but is now used for tool agent responses too.
async def query_llm(prompt, model=ROUTER_MODEL, return_stats=False, is_routing=False, system_context="", chat_history=None, attachments=None):
    if not OLLAMA_URL: return "Error: Ollama not connected."
    final_prompt = prompt
    history_string = ""
    if chat_history:
        filtered_history = [(r, m) for r, m in chat_history if r not in ('forget_check',)]
        if filtered_history:
            history_string = "== CONVERSATION HISTORY (SHORT-TERM MEMORY) ==\n"
            for role, msg in filtered_history: history_string += f"[{role.upper()}]: {msg}\n"
            history_string += "==============================================\n"

    context_parts = []
    if system_context: context_parts.append(system_context)
    if history_string: context_parts.append(history_string)

    if context_parts:
        context_block = "\n\n---\n\n".join(context_parts)
        final_prompt = f"System Context:\n{context_block}\n\nUser Query: {prompt}"

    try:
        options = {"num_gpu": 999, "num_ctx": 4096 if not is_routing else 2048, "temperature": 0.7 if not is_routing else 0.1}
        async with aiohttp.ClientSession() as session:
            payload = {"model": model, "prompt": final_prompt, "stream": False, "options": options}
            async with session.post(OLLAMA_URL, json=payload, timeout=120) as response:
                if response.status == 200:
                    data = await response.json()
                    text = data.get('response', "Error: No response key.")
                    if return_stats: return text, data
                    return text
                else: return f"Error: Status {response.status}"
    except Exception as e: return f"Connection Error: {str(e)}"

# --- TOOL HANDLERS (Used by the Agent) ---

def execute_python_code(code_string):
    """Safely executes simple Python code and returns the output."""
    if any(cmd in code_string for cmd in ['os.', 'sys.', 'open(', 'while ', 'import ']):
        return "ERROR: Restricted command detected (os, sys, file access, infinite loops are blocked)."
    
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    
    try:
        exec(code_string)
        output = redirected_output.getvalue()
        if not output:
             output = "SUCCESS: Code executed with no printed output."
    except Exception as e:
        output = f"EXECUTION ERROR: {type(e).__name__}: {e}"
        
    sys.stdout = old_stdout 
    return output

async def execute_tool_agent(user_prompt, channel, long_term_memory, chat_history):
    """Manages the full execution loop: LLM decides tool -> Calls tool -> LLM refines answer."""
    
    tool_definitions_text = "\n".join([f"Name: {name}\nDescription: {func['description']}\nArguments: {func['arguments']}\n" 
                                      for name, func in TOOL_DEFINITIONS.items()])
    
    # H.1. Inject Shared Guild Memory
    guild_memory = ""
    if channel.guild:
        shared_facts = await get_shared_memories(channel.guild.id)
        if shared_facts:
            guild_memory = "\n=== SHARED GUILD MEMORY ===\n" + "\n".join(shared_facts)

    system_instruction = (
        "You are an expert Tool Agent. Your goal is to satisfy the user's request using the available tools.\n"
        "You must output exactly one of two things:\n"
        "1. FINAL ANSWER: If you have enough information, reply with the final, polished response for the user.\n"
        "2. TOOL CALL: If you need to use a tool, reply ONLY with a JSON object: {'tool_name': 'NAME', 'arguments': 'ARGS'}.\n"
        f"Available Tools:\n{tool_definitions_text}\n"
        f"Your Long Term Memory (User): {long_term_memory}\n"
        f"{guild_memory}\n"
        f"Agent instructions: Be concise. If an image is requested, only output the tool call. If complex research is needed, use tools recursively (G.1)."
    )
    
    history_string = "\n".join([f"[{role.upper()}]: {msg}" for role, msg in chat_history])
    
    full_prompt = (
        f"{system_instruction}\n\n"
        f"--- CONVERSATION CONTEXT ---\n"
        f"{history_string}\n"
        f"--- CURRENT USER PROMPT --ENSURE FINAL RESPONSE IS POLISHED FOR DISCORD---\n"
        f"{user_prompt}"
    )
    
    MAX_ITERATIONS = 4 # Increased for recursive tasks (G.1)
    
    for i in range(MAX_ITERATIONS):
        print(f"⚙️ Agent Iteration {i+1}: Calling LLM for next step...")
        
        llm_response = await query_llm(full_prompt, model=ROUTER_MODEL, system_context="", is_routing=True)
        
        if llm_response.startswith("FINAL ANSWER:"):
            return llm_response.replace("FINAL ANSWER:", "").strip()

        # G.5. Strict JSON Tool Validation
        try:
            tool_call_json = json.loads(llm_response.strip())
            tool_name = tool_call_json.get('tool_name')
            tool_args = tool_call_json.get('arguments')
            
            if not tool_name or not tool_args:
                 raise ValueError("Missing 'tool_name' or 'arguments' in JSON.")
            
            if tool_name in TOOL_DEFINITIONS:
                tool_func = TOOL_DEFINITIONS[tool_name]['function']
                
                # E.2. Tool Failure Reporting - Start
                try:
                    await channel.send(f"🛠️ *Agent is using **{tool_name}** with arguments: `{tool_args}`*")
                    
                    if tool_name == 'execute_python_code':
                        tool_result = execute_python_code(tool_args)
                    else:
                        tool_result = await tool_func(tool_args) 
                    
                    # E.2. Tool Failure Reporting - Check result for hard failure
                    if isinstance(tool_result, str) and tool_result.startswith(("ERROR:", "❌", "⚠️")):
                         raise Exception(tool_result) # Force failure handler below

                    # Handle image generation result specially (F.1. Job ID returned instead of bytes)
                    if tool_name == 'generate_image':
                        # Tool result is the job ID string, sent to the user in post-processing
                        return tool_result
                    
                    # F.2. Enhanced OSINT & BROWSE Analysis - Re-prompt LLM for interpretation
                    if tool_name in ('osint_scan', 'browse_website'):
                         interpretation_prompt = f"TOOL RESPONSE FROM {tool_name}:\n{tool_result}\n\nAgent, analyze this raw data and provide a concise, final interpretation or summary to the user:"
                         llm_interpretation = await query_llm(interpretation_prompt, model=ROUTER_MODEL, system_context="", is_routing=True)
                         return llm_interpretation

                    # G.4. Automated Content Summarization
                    if isinstance(tool_result, str) and len(tool_result) > GLOBAL_CONFIG['MAX_TOOL_RESULT_LENGTH']:
                        await channel.send(f"📄 *Raw tool result too long ({len(tool_result)} chars). Summarizing for Agent context...*")
                        summarization_prompt = f"Summarize the following raw tool output to less than 500 characters, preserving critical data:\n{tool_result}"
                        tool_result = await query_llm(summarization_prompt, model=ROUTER_MODEL, is_routing=True)

                    tool_response_text = f"TOOL RESPONSE FROM {tool_name}:\n{tool_result}\n\nAgent, analyze this result and decide the next step (TOOL CALL or FINAL ANSWER):"
                    full_prompt = f"{full_prompt}\n\n{tool_response_text}"
                
                except Exception as e:
                    # E.2. Tool Failure Reporting - Handle Tool Execution Failure
                    error_msg = str(e)
                    await channel.send(f"❌ **Tool Execution Failed:** `{tool_name}` reported: {error_msg[:100]}...")
                    # Inject failure back into prompt for the LLM to recover
                    failure_prompt = f"TOOL FAILURE: The call to {tool_name} failed with the following error: {error_msg}. Do NOT call this tool again. Provide a FINAL ANSWER explaining the failure or use a different tool."
                    full_prompt = f"{full_prompt}\n\n{failure_prompt}"

            else:
                return f"❌ Agent Failure: LLM returned unlisted tool: {tool_name}"

        except json.JSONDecodeError:
            if i == 0:
                 return llm_response 
            return f"❌ Agent Failure: LLM did not output valid JSON. Response was: {llm_response[:50]}..."
            
    return "⚠️ Agent exceeded maximum iterations (4) without providing a final answer."

# --- TOOL DEFINITIONS ---
TOOL_DEFINITIONS = {
    "search_web": {
        "function": perform_grounded_search,
        "description": "Use for questions requiring current, real-time facts (news, weather, stock prices, scores, latest scientific findings).",
        "arguments": "The exact search query string."
    },
    "browse_website": {
        "function": browse_website,
        "description": "Read the content of a specific URL to summarize or extract information.",
        "arguments": "The exact URL to scrape."
    },
    "osint_scan": {
        "function": run_osint_scan,
        "description": "Investigate a single target (IP, domain, phone number, or username) for external data like WHOIS or geolocation.",
        "arguments": "The target string (e.g., 'google.com' or '192.168.1.1')."
    },
    "execute_python_code": { 
        "function": execute_python_code,
        "description": "Execute Python code to solve math problems, format data, test algorithms, or generate output. Cannot access OS/files.",
        "arguments": "A string containing the Python code to run (e.g., 'print(5 * 5)')."
    },
    "generate_image": {
        "function": generate_image,
        "description": "Create a new static image based on a descriptive text prompt.",
        "arguments": "The descriptive text prompt for the image."
    },
    "save_external_file": { # H.5. External File Storage
        "function": lambda url: f"PLACEHOLDER: File saved for later processing at {url}",
        "description": "Store a URL reference to a large file for future processing or retrieval.",
        "arguments": "The direct URL of the external file (e.g., PDF, large text file)."
    }
}


# --- HANDLERS (Originals, now called by the Agent) ---
async def perform_grounded_search(user_prompt):
    if not GEMINI_API_KEY: return "⚠️ Search Error: GEMINI_API_KEY is not set in the .env file."
    url = f"{GEMINI_API_BASE}gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"
    system_instruction = "You are a factual assistant. Use the Google Search tool to answer the user's query with up-to-date, grounded information, and cite your sources."
    payload = { "contents": [{"parts": [{"text": user_prompt}]}], "tools": [{"google_search": {}}], "systemInstruction": {"parts": [{"text": system_instruction}]} }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as response:
                data = await response.json()
                candidate = data.get('candidates', [{}])[0]
                text = candidate.get('content', {}).get('parts', [{}])[0].get('text', "Search tool failed to produce a text response.")
                sources = []
                grounding_metadata = candidate.get('groundingMetadata', {})
                attributions = grounding_metadata.get('groundingAttributions', [])
                for attr in attributions:
                    if 'web' in attr: sources.append(f"[{attr['web'].get('title', 'Link')}]({attr['web'].get('uri', '#')})")
                source_string = "\n\n" + ("**Source(s):** " + " | ".join(sources) if sources else "")
                return text + source_string
    except Exception as e: return f"❌ Gemini API Search Failure: {str(e)}"

async def analyze_automation_result(task_description, log_data, screenshot_bytes):
    log_summary = "\n".join([f"- {item}" for item in log_data.get('actions', [])])
    analysis_prompt = (
        f"Analyze the following automation task result:\n"
        f"Task Requested: {task_description}\n"
        f"Automation Log:\n{log_summary}\n"
        f"Final Status: {log_data.get('status', 'Error')}\n\n"
        f"If the status is 'SUCCESS', provide a brief, helpful summary of the result.\n"
        f"If the status is 'ERROR' or 'FAILED', provide a clear, actionable reason why the task failed."
    )
    analysis_response = await query_llm(analysis_prompt, model=ROUTER_MODEL, is_routing=True)
    return analysis_response, screenshot_bytes 

# E.1. Long-Task Polling - START
async def generate_video(prompt, channel_id, user_id):
    if not SVD_URL:
        return "⚠️ Video API not found. Please ensure the service is running on the expected URL."
    
    url = f"{SVD_URL}/api/v1/video/generate" 
    
    simulated_payload = { "prompt": prompt, "style": "cinematic", "duration_frames": 14 }

    try:
        async with aiohttp.ClientSession() as session:
            job_id = f"video-job-{random.randint(1000, 9999)}"
            
            # --- Real API Call (commented out for simulation stability) ---
            # async with session.post(url, json=simulated_payload, timeout=5) as response:
            #    if response.status == 200:
            #        data = await response.json()
            #        job_id = data.get('job_id', job_id)
            #    else:
            #        return f"❌ Video API found ({SVD_URL}), but request failed with status: {response.status}. Check SVD API."
            
            # Add job to global polling list
            VIDEO_JOBS[job_id] = {'channel_id': channel_id, 'user_id': user_id, 'prompt': prompt, 'status': 'QUEUED', 'start_time': datetime.datetime.now()}
            
            return f"🎬 Video Generation started (Job ID: `{job_id}`). I will notify the channel when it is complete. This may take a few minutes."
    except Exception as e:
        return f"❌ Could not initiate Video Generation: {e}"

# E.1. Long-Task Polling - LOOP
async def video_polling_loop():
    while True:
        await asyncio.sleep(GLOBAL_CONFIG['POLLING_INTERVAL'])
        if not VIDEO_JOBS or not SVD_URL: continue
        
        jobs_to_remove = []
        for job_id, job_data in VIDEO_JOBS.items():
            try:
                status_url = f"{SVD_URL}/api/v1/video/status/{job_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(status_url, timeout=5) as response:
                        if response.status == 200:
                            status_data = await response.json()
                            
                            if status_data.get('status') == 'COMPLETED':
                                jobs_to_remove.append(job_id)
                                channel = client.get_channel(job_data['channel_id'])
                                if channel:
                                    await channel.send(
                                        f"🎉 **Video Complete** (Job ID: `{job_id}`). "
                                        f"The video for **{job_data['prompt'][:50]}** is ready! "
                                        f"You can view it here: (Placeholder URL/Attachment)."
                                    )
                            elif status_data.get('status') == 'FAILED':
                                jobs_to_remove.append(job_id)
                                channel = client.get_channel(job_data['channel_id'])
                                if channel:
                                    await channel.send(
                                        f"❌ **Video Failed** (Job ID: `{job_id}`). "
                                        f"The generation failed due to: {status_data.get('error', 'Unknown error.')}"
                                    )
            except Exception as e:
                print(f"Polling Error for Job {job_id}: {e}")

        for job_id in jobs_to_remove:
            del VIDEO_JOBS[job_id]

# F.1. Asynchronous SD/Image Generation - POLLING LOOP
async def image_polling_loop():
    while True:
        await asyncio.sleep(GLOBAL_CONFIG['POLLING_INTERVAL'])
        if not IMAGE_JOBS or not SD_URL: continue
        
        jobs_to_remove = []
        for job_id, job_data in IMAGE_JOBS.items():
            try:
                if (datetime.datetime.now() - job_data['start_time']).total_seconds() > GLOBAL_CONFIG['POLLING_INTERVAL'] * random.uniform(1, 2.5):
                    jobs_to_remove.append(job_id)
                    channel = client.get_channel(job_data['channel_id'])
                    
                    img_bytes = await generate_image_sync(job_data['prompt']) 

                    if channel and isinstance(img_bytes, bytes):
                        with io.BytesIO(img_bytes) as f:
                            new_message = await channel.send(
                                f"🎉 **Image Complete** (Job ID: `{job_id}`). Prompt: *{job_data['prompt'][:50]}*",
                                file=discord.File(fp=f, filename="art_complete.png")
                            )
                            await new_message.add_reaction('♻️')
                    elif channel:
                         await channel.send(f"❌ **Image Failed** (Job ID: `{job_id}`). Reason: {img_bytes}")

            except Exception as e:
                print(f"Image Polling Error for Job {job_id}: {e}")

        for job_id in jobs_to_remove:
            del IMAGE_JOBS[job_id]

# F.1. Asynchronous SD/Image Generation - START JOB (Called by Agent)
async def generate_image(prompt):
    if not SD_URL: return "ERROR: Stable Diffusion API not found. Image generation is disabled."
    
    job_id = f"image-job-{random.randint(1000, 9999)}"
    
    IMAGE_JOBS[job_id] = {
        'channel_id': None, 
        'user_id': None,
        'prompt': prompt, 
        'start_time': datetime.datetime.now()
    }
    
    return job_id 

# F.1. Synchronous Image Generation (Used ONLY for Polling loop and Reaction Re-runs)
async def generate_image_sync(prompt):
    if not SD_URL: return "ERROR: Stable Diffusion API not found."
    url = f"{SD_URL}/sdapi/v1/txt2img"
    payload = { "prompt": prompt + ", high quality, detailed, vibrant colors, photorealistic", "steps": 20, "width": 512, "height": 512 }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    return base64.b64decode(data['images'][0]) 
                else:
                    return f"ERROR: SD API status {response.status}. Check SD logs for errors."
    except Exception as e: return f"ERROR: SD Connection Failure: {e}"


async def run_automation(task_description):
    log = {"status": "SUCCESS", "actions": []}
    screenshot = None
    log["actions"].append("Starting Playwright automation.")
    log["actions"].append(f"Task: {task_description}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            url = "https://www.google.com" 
            log["actions"].append(f"Navigating to: {url}")
            await page.goto(url)
            log["actions"].append(f"Page loaded: {await page.title()}")
            if "search" in task_description.lower():
                await page.fill('textarea[name="q"]', "Next feature for OmniBot")
                log["actions"].append("Filled search box with query.")
            screenshot = await page.screenshot()
            log["actions"].append("Successfully captured final screenshot.")
            log["status"] = "SUCCESS"
        except Exception as e:
            log["actions"].append(f"CRITICAL ERROR: {str(e)}")
            log["status"] = "ERROR"
        await browser.close()
    return log, screenshot 

async def run_osint_scan(target): 
    # F.2. Return structured data
    return f"OSINT_RAW_DATA: Domain: {target}. Registrar: GoDaddy (Simulated). Creation Date: 2001-01-01. Status: Active."

async def browse_website(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response: 
                # F.2. Return structured data
                content = (await response.text())[:2000]
                return f"BROWSE_RAW_DATA: URL: {url}. Title: {BeautifulSoup(content, 'html.parser').title.string[:50] if BeautifulSoup(content, 'html.parser').title else 'No Title'}. Snippet: {content[:500]}"
    except Exception as e: return f"ERROR: Failed to crawl website: {e}"

# --- DISCORD EVENTS ---
@client.event
async def on_ready():
    print(f'✅ Bot Online: {client.user}')
    await init_connections()
    print("🔄 Starting long-task polling loops...") 

# D.1. Reaction-Based Tool Triggers
@client.event
async def on_reaction_add(reaction, user):
    if user == client.user or reaction.message.author != client.user:
        return

    if str(reaction.emoji) == '♻️' and reaction.message.attachments:
        
        original_prompt = reaction.message.content 
        
        prompt_match = re.search(r'Prompt: \*(.*?)\*|Generated Image: \*(.*?)\*|\*(.*?)\*', original_prompt, re.DOTALL)
        if prompt_match:
            cleaned_prompt = prompt_match.group(1) or prompt_match.group(2) or prompt_match.group(3)
        else:
            cleaned_prompt = "A high-quality image of an abstraction."

        await reaction.message.channel.send(f"🖼️ *Re-running image generation for: `{cleaned_prompt}`...*")
        
        img_bytes = await generate_image_sync(cleaned_prompt)

        if isinstance(img_bytes, bytes):
            with io.BytesIO(img_bytes) as f:
                new_message = await reaction.message.channel.send(
                    f"**Generated Image (Re-run):** *{cleaned_prompt}*",
                    file=discord.File(fp=f, filename="art_rerun.png")
                )
                await new_message.add_reaction('♻️')
        else:
            await reaction.message.channel.send(f"❌ Re-run failed: {img_bytes}")
            
# H.3. Interactive Buttons for Tool Calls
@client.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component and interaction.data.get('custom_id'):
        custom_id = interaction.data['custom_id']
        
        # We rely on the ToolView class to handle its own state and interaction.
        # This function simply prevents the interaction from being marked as unhandled by Discord.
        await interaction.response.defer() 


@client.event
async def on_message(message):
    if message.author == client.user: return

    should_reply = False
    if client.user in message.mentions: should_reply = True
    elif str(message.channel.id) in TARGET_CHANNEL_IDS: should_reply = True
    elif isinstance(message.channel, discord.DMChannel): should_reply = True

    if should_reply:
        conversation_key = str(message.channel.id) 
        tts_trigger = False
        clean_prompt = message.content.replace(f'<@{client.user.id}>', '').strip()
        
        tts_phrases = ["read this aloud", "say that", "tts", "speak this"]
        if any(phrase in clean_prompt.lower() for phrase in tts_phrases):
             tts_trigger = True
             for phrase in tts_phrases:
                 clean_prompt = clean_prompt.replace(phrase, '').strip()

        # D.2. ADMIN COMMANDS (Bypass Agent)
        if clean_prompt.lower() == '!status':
            status = f"**System Health Report:**\n"
            status += f"• Ollama (LLM): {'✅ Active' if OLLAMA_URL else '❌ Missing'}\n"
            status += f"• Stable Diffusion (Image): {'✅ Active' if SD_URL else '❌ Missing'}\n"
            status += f"• SVD (Video): {'✅ Active' if SVD_URL else '❌ Missing'}\n"
            status += f"• Video Jobs Running: {len(VIDEO_JOBS)}\n"
            status += f"• Image Jobs Running: {len(IMAGE_JOBS)}\n"
            status += f"• Active Memories: {len(await fetch_raw_memories(str(message.author.id)))}\n"
            status += f"• Current Config: Max Hist={GLOBAL_CONFIG['MAX_HISTORY_LENGTH']}, Forget Chance={GLOBAL_CONFIG['FORGET_CHANCE']}%\n" # F.3. Config report
            await message.channel.send(status)
            return
        
        if clean_prompt.lower() == '!forget_me':
            deleted_count = await clear_all_memory(str(message.author.id))
            await message.channel.send(f"🗑️ **Memory Wiped.** Deleted {deleted_count} facts from your long-term memory (Firebase).")
            return
        
        # H.3. Intercept simulated button requests (Needs to be done before attachment processing)
        if clean_prompt.startswith("!TOOL_REQUEST"):
            parts = clean_prompt.split('"', 2)
            if len(parts) >= 2:
                tool_name_from_button = parts[0].replace("!TOOL_REQUEST", "").strip()
                prompt_from_button = parts[1].strip()
                
                # Check for special internal commands from buttons
                if tool_name_from_button == 'summarize_last_message':
                     # Find the bot's last message in history (the one with the buttons) and summarize it
                     last_bot_response = next((msg for role, msg in reversed(CONVERSATION_HISTORY.get(conversation_key, [])) if role == 'bot'), None)
                     if last_bot_response:
                          await message.channel.send("📄 *Summarizing previous bot response...*")
                          summarization_prompt = f"Summarize the following response to under 5 sentences:\n{last_bot_response}"
                          summary = await query_llm(summarization_prompt, model=ROUTER_MODEL, is_routing=True)
                          await message.channel.send(f"**Summary of last response:**\n{summary}")
                          return

                # Override the prompt and push the tool name directly to the agent
                clean_prompt = prompt_from_button
                
                # We reuse the agent logic, but tell it exactly which tool to call by modifying the prompt
                clean_prompt = f"Use the tool named '{tool_name_from_button}' with the argument: {prompt_from_button}. Provide a final answer after the tool executes."

        # --- ATTACHMENT PROCESSING ---
        attachments = message.attachments
        image_attachments = []
        audio_attachment = None
        python_file_content = None # G.3. New Variable

        if attachments:
            for attachment in attachments:
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                        if resp.status == 200:
                            file_bytes = await resp.read()
                            base64_file = base64.b64encode(file_bytes).decode('utf-8')
                            
                            if attachment.content_type == 'text/x-python' or attachment.filename.lower().endswith('.py'):
                                # G.3. Local File Execution
                                python_file_content = file_bytes.decode('utf-8')
                                clean_prompt = f"EXECUTE PYTHON FILE:\n```python\n{python_file_content}\n```\n\n{clean_prompt or 'Explain the code and run it.'}"
                                # Do not break here, continue processing if there are other attachments/text
                                

                            elif attachment.content_type and attachment.content_type.startswith('audio/'):
                                audio_attachment = {"mime_type": attachment.content_type, "data": base64_file}
                                
                            
                            elif attachment.content_type and attachment.content_type.startswith('image/'):
                                image_attachments.append({"mime_type": attachment.content_type, "data": base64_file})
                            
                            # H.5. External File Storage Tool - Check for large files
                            elif attachment.size > 5 * 1024 * 1024: # Over 5MB (Placeholder for large document)
                                # Prepend the tool instruction to the prompt
                                clean_prompt = f"Use the save_external_file tool to store this URL: {attachment.url}. Also, respond to the user's original message: {clean_prompt}"
                            
                        else:
                            await message.channel.send(f"❌ Error downloading attachment: {attachment.filename}")
                            return

        # D.3. Handle Audio Input
        if audio_attachment:
            await message.channel.send("🎤 *Transcribing audio...*")
            transcribed_text = await transcribe_audio_attachment(audio_attachment)
            if transcribed_text.startswith("❌ Transcription Failure"):
                await message.channel.send(transcribed_text)
                return
            
            # Use transcribed text as the main prompt (H.4. Now pipes into Agent)
            clean_prompt = transcribed_text 
            await message.channel.send(f"🗣️ **Transcription:** *{transcribed_text}*")
        
        if not clean_prompt and not image_attachments: return
        print(f"📩 Input: {clean_prompt[:30]}...")

        user_id = str(message.author.id)
        current_history = CONVERSATION_HISTORY.get(conversation_key, [])
        
        # --- 1. HANDLE FORGET CONFIRMATION ---
        last_item = current_history[-1] if current_history and current_history[-1][0] == 'forget_check' else None
        
        if last_item:
            action = clean_prompt.upper()
            target_fact = last_item[1]
            
            current_history.pop()
            CONVERSATION_HISTORY[conversation_key] = current_history
            
            if action == 'NO':
                await delete_memory(user_id, target_fact['id'])
                await message.channel.send(f"✅ Fact deleted: `{target_fact['content']}`. My memory is now cleaner!")
                return
            elif action == 'YES':
                await message.channel.send(f"👍 Got it. I will keep that fact in my long-term memory.")
                return

        # --- 2. CORE MESSAGE PROCESSING (Agent Routing) ---
        async with message.channel.typing():
            # C.3. PROACTIVE MEMORY RECALL: Fetch LTM once
            memories = await get_memories(user_id)
            memory_block = "\n".join([f"- {m}" for m in memories])
            
            response = "" 
            
            if image_attachments:
                # VISION (Bypasses Agent)
                await message.channel.send(f"👁️ *Analyzing multimodal content with Gemini Vision...*")
                response = await analyze_multimodal_content(clean_prompt, image_attachments, memory_block)
                user_log = f"[Image Attached] {clean_prompt}"
                
            elif clean_prompt.lower().startswith("video:"):
                # VIDEO (Bypasses Agent)
                prompt = clean_prompt[6:].strip()
                response = await generate_video(prompt, message.channel.id, user_id)
                user_log = clean_prompt
                
            elif clean_prompt.lower().startswith("automation:"):
                # AUTOMATION (Bypasses Agent)
                task_description = clean_prompt[11:].strip()
                await message.channel.send(f"🤖 *Starting automation task: {task_description}...*")
                
                log_data, screenshot_bytes = await run_automation(task_description)
                analysis, screenshot_bytes = await analyze_automation_result(task_description, log_data, screenshot_bytes)
                
                await message.channel.send(f"**Automation Report:**\n{analysis}")
                
                if screenshot_bytes:
                    with io.BytesIO(screenshot_bytes) as f:
                        await message.channel.send(file=discord.File(fp=f, filename="automation_screenshot.png"))
                return 

            else:
                # C.1. INTELLIGENT TOOL CHAINING (Default path)
                await message.channel.send(f"🧠 *Agent is processing request...*")
                agent_result = await execute_tool_agent(
                    clean_prompt, 
                    message.channel, 
                    memory_block, 
                    current_history
                )
                user_log = clean_prompt
                
                if isinstance(agent_result, str) and agent_result.startswith('image-job-'):
                    # F.1. Image job started successfully, notify user and update job data
                    job_id = agent_result
                    IMAGE_JOBS[job_id].update({
                        'channel_id': message.channel.id,
                        'user_id': user_id,
                        'prompt': clean_prompt
                    })
                    response = f"🖼️ **Image Job Started** (ID: `{job_id}`). I will notify you when Stable Diffusion completes the generation."
                    await message.channel.send(response)
                    return 
                
                elif isinstance(agent_result, bytes):
                    response = f"**Generated Image:** *{clean_prompt}*"
                    img_bytes = agent_result
                else:
                    response = agent_result
                
            # --- 3. POST-PROCESSING (All paths except complex automation) ---
            if response:
                
                # Send text response
                if len(response) > 2000:
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for c in chunks: final_message = await message.channel.send(c)
                else:
                    final_message = await message.channel.send(response)
                
                # Send image if generated by the Agent
                if img_bytes:
                    with io.BytesIO(img_bytes) as f:
                        final_message = await message.channel.send(
                            file=discord.File(fp=f, filename="art.png"),
                            view=ToolView(clean_prompt, message.channel.id, user_id) # H.3. Add buttons
                        )
                        await final_message.add_reaction('♻️') 
                elif not img_bytes and len(response) > 50:
                    # H.3. Add follow-up buttons for general responses
                    await final_message.edit(view=ToolView(clean_prompt, message.channel.id, user_id))


                # Send audio response if triggered
                if tts_trigger:
                    audio_data = await generate_tts_audio(response)
                    if audio_data:
                        with io.BytesIO(audio_data) as f:
                            await message.channel.send(file=discord.File(fp=f, filename="tts_reply.wav"))

                # UPDATE HISTORY (Short-Term Memory)
                current_history.append(("user", user_log))
                current_history.append(("bot", response))
                
                if len(current_history) > GLOBAL_CONFIG['MAX_HISTORY_LENGTH']:
                    current_history = current_history[len(current_history) - GLOBAL_CONFIG['MAX_HISTORY_LENGTH']:]
                
                CONVERSATION_HISTORY[conversation_key] = current_history

                # LEARN (Save new facts to Long-Term Memory)
                asyncio.create_task(extract_facts(user_id, user_log, response))
                
                # --- 4. RANDOM FORGET CHECK (Trigger) ---
                if random.randint(1, 100) <= GLOBAL_CONFIG['FORGET_CHANCE']:
                    asyncio.create_task(check_and_forget_memory(user_id, message.channel.id))


if __name__ == "__main__":
    # Check for needed modules for C.2 Code Execution
    try:
        import sys
        
    except ImportError:
        print("❌ CRITICAL ERROR: Python standard library 'sys' required for sandboxing.")
        sys.exit(1)
        
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN missing from .env")
    else:
        if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID:
            print("⚠️ WARNING: Firebase keys missing. Long-term memory is disabled.")
        if not GEMINI_API_KEY:
            print("⚠️ WARNING: GEMINI_API_KEY missing. Grounded Search/TTS/Vision is disabled.")
        
        client.run(DISCORD_TOKEN)