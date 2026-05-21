"""
MiMo API Client — wrapper for Xiaomi MiMo V2.5-Pro inference.

Handles: chat completions, token tracking, retry logic.
Token usage is logged per-call to SQLite for proof-of-work reporting.
"""

import os
import time
import json
import sqlite3
import requests
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class MiMoResponse:
    content: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    finish_reason: str = ""


class MiMoClient:
    """Client for Xiaomi MiMo V2.5-Pro API (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "MiMo-V2.5-Pro",
        db_path: str = "logs/token_tracker.db",
    ):
        self.api_key = api_key or os.getenv("MIMO_API_KEY", "")
        self.base_url = (base_url or os.getenv("MIMO_BASE_URL", "https://api.platform.xiaomimimo.com/v1")).rstrip("/")
        self.model = model
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite token tracker."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_type TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                latency_ms REAL,
                model TEXT,
                prompt_preview TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _log_usage(self, task_type: str, usage: TokenUsage, prompt_preview: str = ""):
        """Log token usage to SQLite."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO token_usage 
               (timestamp, task_type, prompt_tokens, completion_tokens, total_tokens, latency_ms, model, prompt_preview)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                task_type,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.latency_ms,
                self.model,
                prompt_preview[:200],
            ),
        )
        conn.commit()
        conn.close()

    def chat(
        self,
        messages: list[dict],
        task_type: str = "general",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        retry: int = 3,
    ) -> MiMoResponse:
        """Send chat completion request to MiMo API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error = None
        for attempt in range(retry):
            try:
                t0 = time.time()
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                latency_ms = (time.time() - t0) * 1000
                resp.raise_for_status()
                data = resp.json()

                usage_data = data.get("usage", {})
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                    latency_ms=latency_ms,
                )

                choice = data["choices"][0]
                result = MiMoResponse(
                    content=choice["message"]["content"],
                    usage=usage,
                    model=data.get("model", self.model),
                    finish_reason=choice.get("finish_reason", ""),
                )

                # Log usage
                preview = messages[-1].get("content", "")[:200] if messages else ""
                self._log_usage(task_type, usage, preview)

                return result

            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                wait = 2 ** attempt
                print(f"  ⚠️ MiMo API timeout (attempt {attempt+1}/{retry}), retrying in {wait}s...")
                time.sleep(wait)
            except requests.HTTPError as e:
                last_error = e
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    print(f"  ⚠️ MiMo rate limited, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError(f"MiMo API failed after {retry} retries: {last_error}")

    def plan_tasks(self, tasks_json: dict, context: str = "") -> str:
        """Use MiMo to plan task execution strategy."""
        system = """You are an autonomous testnet task executor agent. 
Given a list of onchain tasks from a testnet protocol, plan the optimal execution order.
Consider: token balances, gas costs, dependency chains (mint before stake, etc).
Output a numbered plan with exact function calls and parameters."""

        user = f"""Today's tasks from API:
```json
{json.dumps(tasks_json, indent=2)}
```

{f'Additional context: {context}' if context else ''}

Plan the execution order. For each step, specify:
1. Task type (mint/stake/bridge/send/receive/daily_tx)
2. Token and amount
3. Contract to call
4. Any prerequisites (approve, balance check)"""

        response = self.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            task_type="planning",
            temperature=0.2,
        )
        return response.content

    def diagnose_error(self, error_msg: str, tx_context: str = "") -> str:
        """Use MiMo to diagnose transaction errors."""
        system = """You are a blockchain transaction debugger.
Given an error message and transaction context, diagnose the root cause and suggest fixes.
Common issues: insufficient gas, wrong function selector, nonce mismatch, contract revert."""

        user = f"""Error: {error_msg}

Transaction context:
{tx_context}

Diagnose the error and provide:
1. Root cause
2. Fix recommendation  
3. Should retry? (yes/no)"""

        response = self.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            task_type="error_recovery",
            temperature=0.1,
        )
        return response.content

    def get_usage_summary(self) -> dict:
        """Get token usage summary from SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT 
                task_type,
                COUNT(*) as calls,
                SUM(prompt_tokens) as prompt_total,
                SUM(completion_tokens) as completion_total,
                SUM(total_tokens) as total,
                AVG(latency_ms) as avg_latency
            FROM token_usage
            GROUP BY task_type
        """)
        summary = {}
        for row in cursor.fetchall():
            summary[row[0]] = {
                "calls": row[1],
                "prompt_tokens": row[2],
                "completion_tokens": row[3],
                "total_tokens": row[4],
                "avg_latency_ms": round(row[5], 1),
            }
        conn.close()
        return summary


if __name__ == "__main__":
    client = MiMoClient()
    print("MiMo Client initialized")
    print(f"  API: {client.base_url}")
    print(f"  Model: {client.model}")
    print(f"  Tracker: {client.db_path}")
