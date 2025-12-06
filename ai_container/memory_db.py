import sqlite3
import json
import os
import math
from datetime import datetime
from typing import List, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "gem_memory.db")


class SQLiteMemoryDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT,
            created_at TEXT NOT NULL
        )
        """)

        conn.commit()
        conn.close()

    # -----------------------------------------------------
    # INSERTS
    # -----------------------------------------------------

    def insert_memory(self, role: str, content: str, embedding: Optional[List[float]] = None):
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO memory (role, content, embedding, created_at)
        VALUES (?, ?, ?, ?)
        """, (
            role,
            content,
            json.dumps(embedding) if embedding else None,
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()

    # -----------------------------------------------------
    # RETRIEVAL
    # -----------------------------------------------------

    def get_recent_messages(self, limit: int = 20) -> List[Dict]:
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("""
        SELECT role, content, created_at FROM memory
        ORDER BY id DESC
        LIMIT ?
        """, (limit,))

        rows = cur.fetchall()
        conn.close()

        return [
            {"role": r[0], "content": r[1], "created_at": r[2]}
            for r in rows
        ][::-1]

    # -----------------------------------------------------
    # SEMANTIC SEARCH
    # -----------------------------------------------------

    def search_by_embedding(self, query_embedding: List[float], top_k: int = 5):
        conn = self._connect()
        cur = conn.cursor()

        cur.execute("SELECT id, role, content, embedding FROM memory WHERE embedding IS NOT NULL")
        rows = cur.fetchall()
        conn.close()

        scored = []

        for r in rows:
            stored_embedding = json.loads(r[3])
            score = self._cosine_similarity(query_embedding, stored_embedding)

            scored.append({
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "score": score
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # -----------------------------------------------------
    # WIPE / RESET
    # -----------------------------------------------------

    def wipe(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM memory")
        conn.commit()
        conn.close()

    # -----------------------------------------------------
    # HELPERS
    # -----------------------------------------------------

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)


# Singleton for easy import
memory_db = SQLiteMemoryDB()

# Compatibility functions for existing code
async def get_memories(user_id):
    """Get memories for a user (SQLite version - returns recent memories)"""
    # Note: SQLite version doesn't filter by user_id yet
    # For multi-user support, we'd need to add a user_id column
    messages = memory_db.get_recent_messages(50)
    # Filter to only return content strings (compatibility)
    return [m["content"] for m in messages if m.get("role") in ["user", "assistant", "fact"]]

async def fetch_raw_memories(user_id):
    """Fetch raw memory facts (compatibility wrapper)"""
    messages = memory_db.get_recent_messages(50)
    return [
        {"id": str(m.get("id", i)), "content": m["content"]}
        for i, m in enumerate(messages)
    ]

async def save_memory(user_id, fact):
    """Save a memory fact"""
    memory_db.insert_memory("fact", fact)

async def delete_memory(user_id, doc_id):
    """Delete a memory by ID"""
    conn = memory_db._connect()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM memory WHERE id = ?", (int(doc_id),))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

async def clear_all_memory(user_id):
    """Clear all memories for a user"""
    count = len(memory_db.get_recent_messages(1000))
    memory_db.wipe()
    return count

async def extract_facts(user_id, user_text, bot_text):
    """Extract and save facts from conversation"""
    from core import query_llm
    extraction_prompt = (
        f"Extract NEW facts about user. User: {user_text}\nAI: {bot_text}\n"
        f"Return facts separated by '|' or NO_FACTS."
    )
    response = await query_llm(extraction_prompt, is_routing=True)
    if response and "NO_FACTS" not in response:
        facts = [f.strip() for f in response.split('|') if f.strip()]
        for fact in facts:
            if len(fact) > 5:
                await save_memory(user_id, fact)

async def get_global_config(guild_id=None, channel_id=None):
    """Get global config (compatibility - returns default config)"""
    from config import GLOBAL_CONFIG
    return GLOBAL_CONFIG

async def get_shared_memories(guild_id):
    """Get shared guild memories (compatibility)"""
    return []

async def check_and_forget_memory(user_id, channel_id, conversation_history, query_llm_func):
    """Check and forget memory (placeholder for now)"""
    pass

