import aiohttp
import asyncio
import os
import base64
import io
import json
import socket
import whois
import random
import sys
import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import config

# Import plugin system
from plugins import load_plugins, get_plugin_tools, execute_plugin_tool, PLUGIN_REGISTRY

# Import local GPU image generation
try:
    from local_image_gen import local_gpu_gen
    LOCAL_GEN_AVAILABLE = True
except ImportError:
    LOCAL_GEN_AVAILABLE = False
    local_gpu_gen = None

# Load plugins on import
load_plugins()

# --- TOOL ETA CONSTANTS (in seconds) ---
ETA_SEARCH = 10
ETA_BROWSE = 15
ETA_OSINT = 12
ETA_CODE = 5
ETA_IMAGE_JOB = 120  # Image generation takes time on a local server
ETA_IMAGE_LOCAL = 30  # Local GPU is faster
ETA_VIDEO_JOB = 600  # Video generation is much longer


def execute_python_code(code_string):
    if any(cmd in code_string for cmd in ['os.', 'sys.', 'open(', 'while ', 'import ']):
        return "ERROR: Restricted command detected."
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    try:
        exec(code_string)
        output = redirected_output.getvalue()
        if not output:
            output = "SUCCESS: No output."
    except Exception as e:
        output = f"EXECUTION ERROR: {type(e).__name__}: {e}"
    sys.stdout = old_stdout
    return output


async def query_llm_external(prompt, model=None, is_routing=False):
    target_model = model if model else config.ROUTER_MODEL
    if not config.OLLAMA_URL:
        return "Error: Ollama not connected."
    try:
        options = {
            "num_gpu": 999,
            "num_ctx": 4096 if not is_routing else 2048,
            "temperature": 0.7 if not is_routing else 0.1
        }
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": target_model,
                "prompt": prompt,
                "stream": False,
                "options": options
            }
            async with session.post(f"{config.OLLAMA_URL}/api/generate", json=payload, timeout=120) as response:
                if response.status == 200:
                    return (await response.json()).get('response', "Error: No response key.")
                else:
                    return f"Error: Status {response.status}"
    except Exception as e:
        return f"Connection Error: {str(e)}"


async def generate_image(prompt):
    """Generate image using remote Stable Diffusion API"""
    if not config.SD_URL:
        return "ERROR: Stable Diffusion API not found. Image generation is disabled."
    job_id = f"image-job-{random.randint(1000, 9999)}"
    config.IMAGE_JOBS[job_id] = {
        'channel_id': None,
        'user_id': None,
        'prompt': prompt,
        'start_time': datetime.datetime.now()
    }
    return job_id


async def generate_image_local(args):
    """Generate image using local GPU Stable Diffusion"""
    prompt = args.get("prompt", "")
    negative = args.get("negative", "")
    steps = args.get("steps", None)
    guidance = args.get("guidance", None)
    
    if not LOCAL_GEN_AVAILABLE or not local_gpu_gen or not local_gpu_gen.is_available():
        return {
            "error": "Local GPU image generation is not available. Check if model is loaded and CUDA is available."
        }
    
    result_path = local_gpu_gen.generate(prompt, negative, steps, guidance)
    
    if result_path:
        return {
            "local_image_path": result_path,
            "prompt": prompt,
            "status": "success"
        }
    else:
        return {
            "error": "Failed to generate image locally"
        }


async def generate_image_sync(prompt):
    """Synchronous image generation for polling loop"""
    # Try local GPU first if available
    if LOCAL_GEN_AVAILABLE and local_gpu_gen and local_gpu_gen.is_available():
        result_path = local_gpu_gen.generate(prompt)
        if result_path and os.path.exists(result_path):
            with open(result_path, 'rb') as f:
                return f.read()
    
    # Fallback to remote API
    if not config.SD_URL:
        return "ERROR: Stable Diffusion API not found."
    url = f"{config.SD_URL}/sdapi/v1/txt2img"
    payload = {
        "prompt": prompt + ", high quality",
        "steps": 20,
        "width": 512,
        "height": 512
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as response:
                if response.status == 200:
                    data = await response.json()
                    return base64.b64decode(data['images'][0])
                else:
                    return f"ERROR: SD API status {response.status}. Check SD logs for errors."
    except Exception as e:
        return f"ERROR: SD Connection Failure: {e}"


async def generate_video(prompt, channel_id, user_id, video_jobs):
    if not config.SVD_URL:
        return "⚠️ Video API not found. Please ensure the service is running on the expected URL."
    url = f"{config.SVD_URL}/api/v1/video/generate"
    simulated_payload = {
        "prompt": prompt,
        "style": "cinematic",
        "duration_frames": 14
    }
    try:
        async with aiohttp.ClientSession() as session:
            job_id = f"video-job-{random.randint(1000, 9999)}"
            config.VIDEO_JOBS[job_id] = {
                'channel_id': channel_id,
                'user_id': user_id,
                'prompt': prompt,
                'status': 'QUEUED',
                'start_time': datetime.datetime.now()
            }
            return f"🎬 Video Generation started (Job ID: {job_id})."
    except Exception as e:
        return f"❌ Could not initiate Video Generation: {e}"


async def perform_grounded_search(user_prompt):
    if not config.GEMINI_API_KEY:
        return "⚠️ Search Error: GEMINI_API_KEY missing."
    url = f"{config.GEMINI_API_BASE}{config.VISION_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
    system_instruction = "You are a factual assistant. Use the Google Search tool."
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "tools": [{"google_search": {}}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as response:
                data = await response.json()
                candidate = data.get('candidates', [{}])[0]
                text = candidate.get('content', {}).get('parts', [{}])[0].get('text', "Search failed.")
                return text
    except Exception as e:
        return f"❌ Gemini API Search Failure: {str(e)}"


async def browse_website(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                content = (await response.text())[:2000]
                return f"BROWSE_RAW_DATA: URL: {url}. Snippet: {content[:500]}"
    except Exception as e:
        return f"ERROR: Failed to crawl website: {e}"


async def run_osint_scan(target):
    return f"OSINT_RAW_DATA: Domain: {target}. Registrar: GoDaddy (Simulated). Status: Active."


async def run_automation(task_description):
    log = {"status": "SUCCESS", "actions": ["simulated action"]}
    screenshot = None
    return log, screenshot


async def analyze_automation_result(task_description, log_data, screenshot_bytes):
    analysis_prompt = f"Analyze automation result for: {task_description}. Status: {log_data.get('status')}."
    analysis_response = await query_llm_external(analysis_prompt, model=config.ROUTER_MODEL, is_routing=True)
    return analysis_response, screenshot_bytes


async def save_external_file(url):
    return f"PLACEHOLDER: File saved at {url}"


# --- TOOL DEFINITIONS DICTIONARY (uses ETA constants) ---
TOOL_DEFINITIONS = {
    "search_web": {
        "function": perform_grounded_search,
        "description": "Search the web for current facts (news, weather, stocks).",
        "arguments": "The exact search query string.",
        "eta": ETA_SEARCH
    },
    "browse_website": {
        "function": browse_website,
        "description": "Read content of a URL.",
        "arguments": "The URL to scrape.",
        "eta": ETA_BROWSE
    },
    "osint_scan": {
        "function": run_osint_scan,
        "description": "Investigate IP/Domain/Phone.",
        "arguments": "The target string.",
        "eta": ETA_OSINT
    },
    "execute_python_code": {
        "function": execute_python_code,
        "description": "Execute simple Python code (math, logic).",
        "arguments": "The Python code string.",
        "eta": ETA_CODE
    },
    "generate_image": {
        "function": generate_image,
        "description": "Create an image from text using remote Stable Diffusion API.",
        "arguments": "The descriptive text prompt.",
        "eta": ETA_IMAGE_JOB
    },
    "generate_image_local": {
        "function": generate_image_local,
        "description": "Create an image from text using LOCAL GPU Stable Diffusion (faster, private, no cost).",
        "arguments": "Dictionary with 'prompt' (required), optional 'negative', 'steps', 'guidance'.",
        "eta": ETA_IMAGE_LOCAL
    },
    "save_external_file": {
        "function": save_external_file,
        "description": "Save a file URL.",
        "arguments": "The file URL.",
        "eta": 2
    }
}

# Add plugin tools to TOOL_DEFINITIONS for display purposes
# Actual execution is handled by execute_tool checking PLUGIN_REGISTRY
for plugin_name, plugin_info in PLUGIN_REGISTRY.items():
    if "schema" in plugin_info and "function" in plugin_info["schema"]:
        func_info = plugin_info["schema"]["function"]
        tool_name = func_info.get("name", plugin_name)
        
        # Create a placeholder function that will be handled by execute_tool
        async def plugin_wrapper(args, name=plugin_name):
            result = execute_plugin_tool(name, args)
            if asyncio.iscoroutine(result):
                return await result
            return result
        
        TOOL_DEFINITIONS[tool_name] = {
            "function": plugin_wrapper,
            "description": func_info.get("description", "Plugin tool"),
            "arguments": str(func_info.get("parameters", {})),
            "eta": plugin_info.get("eta", 5)
        }


async def execute_tool(tool_name: str, args):
    """
    Unified tool execution router (async).
    Handles both built-in tools and plugin tools.
    """
    # Check if it's a plugin tool
    if tool_name in PLUGIN_REGISTRY:
        result = execute_plugin_tool(tool_name, args)
        # Plugin tools might return async results, handle if needed
        if asyncio.iscoroutine(result):
            return await result
        return result
    
    # Check if it's a built-in tool
    if tool_name in TOOL_DEFINITIONS:
        tool_func = TOOL_DEFINITIONS[tool_name]["function"]
        
        # Handle async vs sync functions
        if asyncio.iscoroutinefunction(tool_func):
            return await tool_func(args)
        else:
            return tool_func(args)
    
    return {"error": f"Unknown tool: {tool_name}"}

