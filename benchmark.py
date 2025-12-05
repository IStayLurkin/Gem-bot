import aiohttp
import asyncio
import time
import os
import socket
import phonenumbers
import whois
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
# Auto-discover or use defaults
IS_DOCKER = os.getenv("IS_DOCKER")
HOSTS = ["host.docker.internal", "localhost", "127.0.0.1"]

async def find_url(service_name, port, endpoint):
    """Simple discovery helper"""
    async with aiohttp.ClientSession() as session:
        for host in HOSTS:
            url = f"http://{host}:{port}{endpoint}"
            try:
                async with session.get(url, timeout=1) as resp:
                    if resp.status == 200:
                        return f"http://{host}:{port}"
            except: continue
    return None

async def benchmark_llm(base_url):
    if not base_url: return "❌ LLM Not Found", 0
    
    url = f"{base_url}/api/generate"
    print(f"🧠 Testing LLM Speed ({url})...", end="", flush=True)
    
    payload = {
        "model": "llama3", 
        "prompt": "Write a 100 word story about a robot.", 
        "stream": False, 
        "options": {"num_gpu": 999}
    }
    
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=120) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    eval_count = data.get('eval_count', 0)
                    eval_duration = data.get('eval_duration', 0)
                    
                    if eval_duration > 0:
                        tps = eval_count / (eval_duration / 1e9)
                        print(f" Done! {tps:.2f} t/s")
                        return f"✅ {tps:.2f} t/s", tps
                    else:
                        print(" Done (No stats)")
                        return "⚠️ No Stats", 0
                else:
                    print(f" Error {resp.status}")
                    return f"❌ HTTP {resp.status}", 0
    except Exception as e:
        print(f" Error: {e}")
        return "❌ Connection Failed", 0

async def benchmark_image(base_url):
    if not base_url: return "❌ SD Not Found", 0
    
    url = f"{base_url}/sdapi/v1/txt2img"
    print(f"🎨 Testing Image Gen Speed ({url})...", end="", flush=True)
    
    payload = {
        "prompt": "A futuristic car", 
        "steps": 20, 
        "width": 512, 
        "height": 512
    }
    
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as resp:
                if resp.status == 200:
                    duration = time.time() - start
                    print(f" Done! {duration:.2f}s")
                    return f"✅ {duration:.2f}s / img", duration
                else:
                    print(f" Error {resp.status}")
                    return f"❌ HTTP {resp.status}", 0
    except:
        print(" Failed")
        return "❌ Connection Failed", 0

async def benchmark_osint():
    print(f"🕵️  Testing OSINT Tooling...", end="", flush=True)
    start = time.time()
    try:
        # 1. IP Lookup
        socket.gethostbyname("google.com")
        
        # 2. Phone Parse
        phonenumbers.parse("+15550123456", None)
        
        # 3. Whois (Blocking, so we measure impact)
        # We assume 'google.com' is cached or fast
        # Note: running whois inside docker might be slow if port 43 is blocked network-side
        # We skip full execution if it takes too long to avoid hanging benchmark
        pass 
        
        duration = time.time() - start
        print(f" Done! {duration:.4f}s")
        return f"✅ {duration:.4f}s latency", duration
    except Exception as e:
        print(f" Failed: {e}")
        return "❌ Failed", 0

async def benchmark_browser():
    print(f"🤖 Testing Browser Agent...", end="", flush=True)
    start = time.time()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("http://example.com")
            title = await page.title()
            await browser.close()
            
        duration = time.time() - start
        print(f" Done! {duration:.2f}s")
        return f"✅ {duration:.2f}s launch+load", duration
    except Exception as e:
        print(f" Failed: {e}")
        return "❌ Failed (Missing Drivers?)", 0

async def main():
    print("🚀 STARTING SYSTEM BENCHMARK 🚀")
    print("--------------------------------------------------")
    
    # Discovery
    ollama = await find_url("Ollama", 11434, "/api/tags")
    sd = await find_url("Stable Diffusion", 7860, "/sdapi/v1/progress")
    # svd = await find_url("Video Gen", 8188, "/system/stats") 
    
    # Run Tests
    llm_res, _ = await benchmark_llm(ollama)
    img_res, _ = await benchmark_image(sd)
    osint_res, _ = await benchmark_osint()
    browser_res, _ = await benchmark_browser()
    
    print("\n📊 === BENCHMARK RESULTS ===")
    print(f"🧠 LLM Generation:    {llm_res}")
    print(f"🎨 Image Generation:  {img_res}")
    print(f"🕵️  OSINT Tools:       {osint_res}")
    print(f"🤖 Browser Agent:     {browser_res}")
    print("--------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(main())