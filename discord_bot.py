import discord
import aiohttp
import asyncio
import os
import io
import json
import socket
import datetime
import random 
import re 
import sys 

from discord.ui import Button, View 
from gembot_views import ToolView 
import config
from core import query_llm
from memory_db import *
from tool_handlers import *

# --- INITIALIZATION ---
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True 
client = discord.Client(intents=intents)

async def image_polling_loop():
    while True:
        await asyncio.sleep(config.GLOBAL_CONFIG['POLLING_INTERVAL'])
        if not config.IMAGE_JOBS or not config.SD_URL: continue
        jobs_to_remove = []
        for job_id, job_data in config.IMAGE_JOBS.items():
            try:
                if (datetime.datetime.now() - job_data['start_time']).total_seconds() > config.GLOBAL_CONFIG['POLLING_INTERVAL'] * random.uniform(1, 2.5):
                    jobs_to_remove.append(job_id)
                    channel = client.get_channel(job_data['channel_id'])
                    img_bytes = await generate_image_sync(job_data['prompt']) 
                    if channel and isinstance(img_bytes, bytes):
                        with io.BytesIO(img_bytes) as f:
                            new_message = await channel.send(f'🎉 **Image Complete** (Job ID: {job_id})', file=discord.File(fp=f, filename='art.png'))
                            await new_message.add_reaction('♻️')
            except Exception as e: print(f'Image Polling Error: {e}')
        for job_id in jobs_to_remove: del config.IMAGE_JOBS[job_id]

async def video_polling_loop():
    while True:
        await asyncio.sleep(config.GLOBAL_CONFIG['POLLING_INTERVAL'])
        if not config.VIDEO_JOBS or not config.SVD_URL: continue
        jobs_to_remove = []
        for job_id, job_data in config.VIDEO_JOBS.items():
            if (datetime.datetime.now() - job_data['start_time']).total_seconds() > config.GLOBAL_CONFIG['POLLING_INTERVAL'] * 3:
                jobs_to_remove.append(job_id)
                channel = client.get_channel(job_data['channel_id'])
                if channel: await channel.send(f'🎉 **Video Complete** (Job ID: {job_id})')
        for job_id in jobs_to_remove: del config.VIDEO_JOBS[job_id]

async def execute_tool_agent(user_prompt, channel, long_term_memory, chat_history):
    # FIX: Swapped quotes to avoid backslash in f-string
    tool_defs = '\n'.join([f'{name}: {func["description"]}' for name, func in TOOL_DEFINITIONS.items()])
    
    # --- STRICT 'NO MONOLOGUE' PROMPT ---
    system_instruction = (
        "You are OmniBot, a smart, casual, and helpful AI assistant on Discord. "
        f"I have provided your Long Term Memory below. Use it to answer personal questions instantly.\n\n"
        f"=== LONG TERM MEMORY ===\n{long_term_memory}\n========================\n\n"
        f"Available Tools:\n{tool_defs}\n\n"
        "**CRITICAL RULES:**\n"
        "1. **Direct Speech Only:** Never narrate your thought process. Do NOT say 'Let me check', 'According to records', or 'Ah-ha!'. Just give the answer directly.\n"
        "2. **Be Casual:** Speak naturally. If you know the user's name, use it.\n"
        "3. **Tool Use:** If you need a tool (search, image, code), output ONLY the JSON: {\"tool_name\": \"...\", \"arguments\": \"...\"}.\n"
        "4. **Normal Chat:** If no tool is needed, just reply with the text."
    )
    
    full_prompt = f'{system_instruction}\nContext: {chat_history}\nPrompt: {user_prompt}'
    
    for i in range(3):
        llm_response = await query_llm(full_prompt, is_routing=True)
        
        # Clean any lingering tags just in case
        clean_response = llm_response.replace('FINAL ANSWER:', '').strip()
        
        try:
            # Try to parse as JSON tool call
            tool_call = json.loads(clean_response)
            tool_name = tool_call.get('tool_name')
            tool_args = tool_call.get('arguments')
            
            if tool_name in TOOL_DEFINITIONS:
                await channel.send(f'🛠️ *Agent using {tool_name}...*')
                if tool_name == 'generate_image': return await generate_image(tool_args)
                
                tool_func = TOOL_DEFINITIONS[tool_name]['function']
                if tool_name == 'execute_python_code': result = tool_func(tool_args)
                else: result = await tool_func(tool_args)
                
                # Feed result back to LLM
                full_prompt += f'\nTOOL RESULT: {result}\nDecide next step (JSON or Text):'
            else: 
                # If valid JSON but wrong tool, return error
                return f'❌ Agent Error: Unknown tool {tool_name}'
        except json.JSONDecodeError: 
            # If it's NOT JSON, it's the final answer. Return it immediately.
            return clean_response
            
    return '⚠️ Agent timed out.'

async def find_service(service_name, possible_urls, validation_endpoint):
    async with aiohttp.ClientSession() as session:
        for url in possible_urls:
            try:
                async with session.get(f'{url}{validation_endpoint}', timeout=2) as response:
                    if response.status == 200: return url
            except: continue
    return None

async def init_connections():
    hosts = ['http://host.docker.internal', 'http://localhost', 'http://127.0.0.1']
    await get_global_config()
    base_ollama = await find_service('Ollama', [f'{h}:11434' for h in hosts], '/api/tags')
    config.OLLAMA_URL = base_ollama if base_ollama else 'http://localhost:11434'
    config.SD_URL = await find_service('Stable Diffusion', [f'{h}:7860' for h in hosts], '/sdapi/v1/progress')
    config.SVD_URL = await find_service('SVD', [f'{h}:8188' for h in hosts], '/system/stats')
    asyncio.create_task(video_polling_loop())
    asyncio.create_task(image_polling_loop())

@client.event
async def on_ready():
    print(f'✅ Bot Online: {client.user}')
    await init_connections()

@client.event
async def on_message(message):
    if message.author == client.user: return
    clean_prompt = message.content.replace(f'<@{client.user.id}>', '').strip()
    
    if clean_prompt.lower() == '!status':
        await message.channel.send(f'System Status: Ollama={bool(config.OLLAMA_URL)}, SD={bool(config.SD_URL)}')
        return

    if not clean_prompt and not message.attachments: return
    
    async with message.channel.typing():
        memories = await get_memories(str(message.author.id))
        memory_block = '\n'.join(memories)
        
        # Simple routing for now to ensure stability
        response = await execute_tool_agent(clean_prompt, message.channel, memory_block, [])
        
        if isinstance(response, str) and response.startswith('image-job-'):
            config.IMAGE_JOBS[response] = {'channel_id': message.channel.id, 'prompt': clean_prompt, 'start_time': datetime.datetime.now()}
            await message.channel.send(f'🖼️ Image Job {response} queued.')
        else:
            await message.channel.send(response)
            asyncio.create_task(extract_facts(str(message.author.id), clean_prompt, response))

if __name__ == "__main__":
    if not config.DISCORD_TOKEN: print("❌ Error: DISCORD_TOKEN missing")
    else: client.run(config.DISCORD_TOKEN)
