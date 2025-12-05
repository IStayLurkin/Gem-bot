import aiohttp
import asyncio
import datetime
import json
# FIX: Import MASTER_USER_ID
from config import FIREBASE_API_KEY, FIREBASE_PROJECT_ID, APP_ID, GLOBAL_CONFIG, MASTER_USER_ID
from core import query_llm 

async def get_global_config(guild_id=None, channel_id=None):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return
    global_url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/config/global?key={FIREBASE_API_KEY}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(global_url, timeout=5) as response:
                if response.status == 200:
                    fields = (await response.json()).get('fields', {})
                    GLOBAL_CONFIG.update({
                        k: int(fields.get(k, {}).get('integerValue', GLOBAL_CONFIG[k]))
                        for k in GLOBAL_CONFIG if k != 'MAX_TOOL_RESULT_LENGTH' and k in fields
                    })
    except Exception as e: print(f"Config Warning: {e}")

async def get_shared_memories(guild_id):
    # Use MASTER_USER_ID for everything now
    return await fetch_raw_memories(None)

async def fetch_raw_memories(user_id):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return []
    # FIX: Use MASTER_USER_ID instead of user_id
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/users/{MASTER_USER_ID}/memory_facts?key={FIREBASE_API_KEY}"
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

async def clear_all_memory(user_id):
    raw_facts = await fetch_raw_memories(user_id)
    if not raw_facts: return 0
    delete_tasks = []
    for fact in raw_facts: delete_tasks.append(asyncio.create_task(delete_memory(user_id, fact['id'])))
    await asyncio.gather(*delete_tasks)
    return len(raw_facts)

async def delete_memory(user_id, doc_id):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return
    # FIX: Use MASTER_USER_ID
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/users/{MASTER_USER_ID}/memory_facts/{doc_id}?key={FIREBASE_API_KEY}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                if response.status != 200: print(f"Failed to delete memory: {response.status}")
    except Exception as e: print(f"Memory Deletion Error: {e}")

async def save_memory(user_id, fact):
    if not FIREBASE_API_KEY or not FIREBASE_PROJECT_ID: return
    # FIX: Use MASTER_USER_ID
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/artifacts/{APP_ID}/users/{MASTER_USER_ID}/memory_facts?key={FIREBASE_API_KEY}"
    payload = { "fields": { "content": {"stringValue": fact}, "createdAt": {"timestampValue": datetime.datetime.utcnow().isoformat() + "Z"} } }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200: print(f"Failed to save memory: {response.status}")
    except Exception as e: print(f"Memory Save Error: {e}")

async def extract_facts(user_id, user_text, bot_text):
    extraction_prompt = f"Extract NEW facts about user. User: {user_text}\nAI: {bot_text}\nReturn facts separated by '|' or NO_FACTS."
    response = await query_llm(extraction_prompt, is_routing=True)
    if response and "NO_FACTS" not in response:
        facts = [f.strip() for f in response.split('|') if f.strip()]
        for fact in facts: await save_memory(user_id, fact)

async def check_and_forget_memory(user_id, channel_id, conversation_history, query_llm_func):
    pass 
