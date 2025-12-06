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

# Helper for time formatting
def format_time_elapsed(start_time):
    delta = datetime.datetime.now() - start_time
    minutes = int(delta.total_seconds() // 60)
    seconds = int(delta.total_seconds() % 60)
    return f"{minutes}m {seconds}s"


async def image_polling_loop():
    while True:
        await asyncio.sleep(config.GLOBAL_CONFIG['POLLING_INTERVAL'])
        if not config.SD_URL: continue
        if not config.IMAGE_JOBS: continue
        
        jobs_to_remove = []
        for job_id, job_data in config.IMAGE_JOBS.items():
            try:
                start_time = job_data['start_time']
                time_elapsed = (datetime.datetime.now() - start_time).total_seconds()
                channel = client.get_channel(job_data['channel_id'])

                if time_elapsed > config.GLOBAL_CONFIG['POLLING_INTERVAL'] * random.uniform(1, 2.5):
                    print(f"🔄 Polling: Job {job_id} ready. Attempting image retrieval...")
                    
                    img_bytes = await generate_image_sync(job_data['prompt']) 

                    if channel and isinstance(img_bytes, bytes):
                        time_spent = format_time_elapsed(start_time)
                        with io.BytesIO(img_bytes) as f:
                            new_message = await channel.send(
                                f"🎉 **Image Complete** (Took {time_spent}). Prompt: *{job_data['prompt'][:50]}*",
                                file=discord.File(fp=f, filename='art.png')
                            )
                            await new_message.add_reaction('♻️')
                        jobs_to_remove.append(job_id)

                    elif channel:
                         error_message = img_bytes if isinstance(img_bytes, str) else "Unknown API Error."
                         await channel.send(f"❌ **Image Job Failed** (Took {format_time_elapsed(start_time)}). Reason: {error_message}")
                         jobs_to_remove.append(job_id)

            except Exception as e:
                print(f"CRITICAL POLLING ERROR in job {job_id}: {e}")
                jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove: del config.IMAGE_JOBS[job_id]

async def video_polling_loop():
    while True:
        await asyncio.sleep(config.GLOBAL_CONFIG['POLLING_INTERVAL'])
        if not config.VIDEO_JOBS or not config.SVD_URL: continue
        
        jobs_to_remove = []
        for job_id, job_data in config.VIDEO_JOBS.items():
            start_time = job_data['start_time']
            time_elapsed = (datetime.datetime.now() - start_time).total_seconds()

            if time_elapsed > TOOL_DEFINITIONS['generate_video']['eta'] + config.GLOBAL_CONFIG['POLLING_INTERVAL']:
                jobs_to_remove.append(job_id)
                channel = client.get_channel(job_data['channel_id'])
                if channel:
                    time_spent = format_time_elapsed(start_time)
                    await channel.send(f"🎉 **Video Complete** (Took {time_spent}). The video for **{job_data['prompt'][:50]}** is ready! (Placeholder URL).")
            
        for job_id in jobs_to_remove: del config.VIDEO_JOBS[job_id]

async def execute_tool_agent(user_prompt, channel, long_term_memory, chat_history):
    # This list provides the function names and descriptions for the prompt
    tool_defs = '\n'.join([f'- **{name}** (ETA: {func["eta"]}s): {func["description"]}' for name, func in TOOL_DEFINITIONS.items()])
    
    # --- FIXED PROMPT: NOW INCLUDES MEMORY ---
    system_instruction = (
        "You are OmniBot, a smart, casual, and helpful AI assistant on Discord. "
        "You always prioritize natural conversation. You have access to the tools listed below. "
        f"I have provided your Long Term Memory below. Use it to answer personal questions instantly.\n\n"
        
        f"Available Tools (Use the short name in bold):\n{tool_defs}\n\n"
        
        "**CRITICAL RULES:**\n"
        "1. **Direct Speech Only:** Never narrate your thought process. Just give the answer directly.\n"
        "2. **Tool Call Format:** If you use a tool, output ONLY the JSON: {\"tool_name\": \"[short_name]\", \"arguments\": \"[argument_string]\"}.\n"
        "3. **SHORT NAME MANDATORY:** The \"tool_name\" must be one of the short names listed above (e.g., generate_image, search_web).\n"
        "4. **Final Answer:** If no tool is needed, output 'FINAL ANSWER: [Your response]'.\n"
    )
    
    full_prompt = f'{system_instruction}\nContext: {chat_history}\nPrompt: {user_prompt}'
    
    for i in range(3):
        llm_response = await query_llm(full_prompt, is_routing=True)
        
        clean_response = llm_response.replace('FINAL ANSWER:', '').strip()
        
        if 'FINAL ANSWER:' in llm_response:
            return clean_response
            
        try:
            tool_call = json.loads(clean_response)
            tool_name = tool_call.get('tool_name')
            tool_args = tool_call.get('arguments')
            
            if tool_name in TOOL_DEFINITIONS:
                # Calculate and display ETA immediately
                eta_sec = TOOL_DEFINITIONS[tool_name]['eta']
                await channel.send(f'🛠️ *Agent is using **{tool_name}** (ETA: {eta_sec}s)...*') 
                
                if tool_name == 'generate_image': 
                    job_id = await generate_image(tool_args)
                    config.IMAGE_JOBS[job_id].update({'channel_id': channel.id}) 
                    return f"Image job started. Polling for results..."

                tool_func = TOOL_DEFINITIONS[tool_name]['function']
                if tool_name == 'execute_python_code': result = tool_func(tool_args)
                else: result = await tool_func(tool_args)
                
                full_prompt += f'\nTOOL RESULT: {result}\nDecide next step (JSON or Text):'
            else: 
                return f'❌ Agent Error: Tool name must be one of the short names. Received: {tool_name}'
        except json.JSONDecodeError: 
            if i == 0: return clean_response
            return '❌ Agent failed to reason.'
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
        
        if isinstance(response, str) and response.startswith('Image job started. Polling for results...'):
             await message.channel.send(response)
             return # Polling loop handles the rest
        
        if isinstance(response, str) and response.startswith('image-job-'):
            # This path is hit if the agent returns ONLY the job ID string, which we fixed above.
            # We treat this as an immediate image job start success.
            config.IMAGE_JOBS[response].update({'channel_id': message.channel.id, 'prompt': clean_prompt})
            await message.channel.send(f'🖼️ Image Job {response} queued.')
        else:
            await message.channel.send(response)
            asyncio.create_task(extract_facts(str(message.author.id), clean_prompt, response))

if __name__ == "__main__":
    if not config.DISCORD_TOKEN: print("❌ Error: DISCORD_TOKEN missing")
    else: client.run(config.DISCORD_TOKEN)
