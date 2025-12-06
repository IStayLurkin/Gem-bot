import aiohttp
import asyncio
import config 

async def query_llm(prompt, model=None, return_stats=False, is_routing=False, system_context="", chat_history=None, attachments=None):
    target_model = model if model else config.ROUTER_MODEL

    if not config.OLLAMA_URL: return "Error: Ollama not connected." 
    
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
            payload = {"model": target_model, "prompt": final_prompt, "stream": False, "options": options}
            async with session.post(f"{config.OLLAMA_URL}/api/generate", json=payload, timeout=120) as response:
                if response.status == 200:
                    data = await response.json()
                    text = data.get('response', "Error: No response key.")
                    if return_stats: return text, data
                    return text
                else: return f"Error: Status {response.status}"
    except Exception as e: return f"Connection Error: {str(e)}"
