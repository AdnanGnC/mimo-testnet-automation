"""
Overlayer Testnet Agent — autonomous task executor powered by MiMo V2.5-Pro.

Workflow:
1. Authenticate with Overlayer API (SIWE)
2. Fetch daily tasks
3. Call MiMo to plan execution
4. Execute transactions (mint, stake, bridge, send, receive)
5. On error, call MiMo to diagnose and recover
6. Verify completion via leaderboard
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

import requests
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import eth_abi
from dotenv import load_dotenv

from mimo_client import MiMoClient

load_dotenv()


class OverlayerAgent:
    """Autonomous Overlayer testnet task executor."""

    # Sepolia contract addresses
    USDC = Web3.to_checksum_address("0x94a9D9AC8a22534E3FaCa9F4e7F2E2cf85d5E4C8")
    USDT = Web3.to_checksum_address("0xaA8E23Fb1079EA71e0a56F48a2aA51851D8433D0")
    CPLUS = Web3.to_checksum_address("0xE815718D44694ec4637CB775C468d87f6e15B538")
    TPLUS = Web3.to_checksum_address("0xe20534a32f9162488a90026F268a74fBE28d272D")
    SCPLUS = Web3.to_checksum_address("0x753937137Eb92871A6F3517514d4f1Ee860e3FDF")
    STPLUS = Web3.to_checksum_address("0x079a4Bf1Cbd0E4ce15391340cB46efA6396aBc82")

    # Custom function selector for Overlayer's supply() function
    # Discovered via reverse engineering: NOT standard ERC4626 supply(uint256,address)
    # Real signature: (receiver, onBehalfOf, asset, usdcAmount, expectedCplusAmount)
    SUPPLY_SELECTOR = "0x2ef6f1ab"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.api_base = os.getenv("OVERLAYER_API", "https://api.overlayer.fi/api-s")
        self.rpc_url = os.getenv("SEPOLIA_RPC", "https://ethereum-sepolia-rpc.publicnode.com")

        # Load wallet
        pk = os.getenv("WALLET_PRIVATE_KEY")
        if not pk:
            raise RuntimeError("WALLET_PRIVATE_KEY not set in .env")
        self.account = Account.from_key(pk)
        self.wallet = self.account.address

        # Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        assert self.w3.is_connected(), f"RPC connection failed: {self.rpc_url}"

        # MiMo client
        self.mimo = MiMoClient()

        print(f"🤖 Overlayer Agent initialized")
        print(f"   Wallet: {self.wallet}")
        print(f"   RPC:    {self.rpc_url}")
        print(f"   MiMo:   {self.mimo.model}")
        print(f"   Mode:   {'DRY-RUN' if dry_run else 'LIVE'}")

    def authenticate(self) -> str:
        """SIWE-based auth with Overlayer API."""
        r = requests.get(f"{self.api_base}/auth/nonce/{self.wallet}", timeout=15)
        r.raise_for_status()
        nd = r.json()

        from datetime import timezone
        expires_dt = datetime.fromisoformat(nd["expiresAt"].replace("Z", "+00:00"))
        ts = int(expires_dt.timestamp()) - 15 * 60 + 5 * 60
        msg = f"Request Overlayer social session\n{self.wallet}\n{ts}\n{nd['nonce']}"
        sig = "0x" + self.account.sign_message(encode_defunct(text=msg)).signature.hex()

        r = requests.post(
            f"{self.api_base}/auth/verify/{self.wallet}",
            json={"message": msg, "signature": sig},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["token"]

    def fetch_tasks(self, token: str) -> list[dict]:
        """Fetch today's onchain tasks."""
        r = requests.get(
            f"{self.api_base}/socials/onchain-tasks",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("tasks", [])

    def plan_execution(self, tasks: list[dict]) -> str:
        """Use MiMo to plan execution order and strategy."""
        print(f"\n🤖 Calling MiMo {self.mimo.model} for task planning...")
        t0 = time.time()
        plan = self.mimo.plan_tasks({"tasks": tasks})
        latency = time.time() - t0
        print(f"💭 MiMo planning complete ({latency:.1f}s)")
        print(f"   Preview: {plan[:200]}...")
        return plan

    def execute_task(self, task: dict) -> tuple[bool, str]:
        """Execute a single task. Returns (success, tx_hash_or_error)."""
        task_type = task["type"]
        product = task.get("product", "")
        amount = task["amount"]

        print(f"\n➡️  Executing {task_type.upper()} {amount} ({product})")

        if self.dry_run:
            print(f"   [DRY-RUN] Would execute: {task['id']}")
            return True, "0xdry-run"

        try:
            if task_type == "mint":
                return self._execute_mint(product, amount)
            elif task_type == "stake":
                return self._execute_stake(product, amount)
            elif task_type == "bridge":
                return self._execute_bridge(amount)
            elif task_type in ("send", "receive"):
                return self._execute_transfer(product, amount)
            elif task_type == "transaction":
                return self._execute_daily_txs(amount)
            else:
                return False, f"Unknown task type: {task_type}"
        except Exception as e:
            # Use MiMo to diagnose error
            diagnosis = self.mimo.diagnose_error(
                str(e),
                f"Task: {task_type} {amount} {product}\nWallet: {self.wallet}",
            )
            print(f"   ❌ Error: {e}")
            print(f"   🩺 MiMo diagnosis: {diagnosis[:300]}")
            return False, str(e)

    def _execute_mint(self, product: str, amount: int) -> tuple[bool, str]:
        """Mint C+ from USDC or T+ from USDT."""
        if product == "usdc":
            token = self.USDC
            target = self.CPLUS
            decimals = 6
        elif product == "usdt":
            token = self.USDT
            target = self.TPLUS
            decimals = 6
        else:
            return False, f"Unknown product for mint: {product}"

        amount_raw = int(amount * 10**decimals)
        expected_output = int(amount * 1e18)  # 18 decimals for C+/T+

        # Encode supply() call: selector + 5 params
        data = self.SUPPLY_SELECTOR + eth_abi.encode(
            ["address", "address", "address", "uint256", "uint256"],
            [self.wallet, self.wallet, token, amount_raw, expected_output],
        ).hex()

        tx = {
            "to": target,
            "from": self.wallet,
            "data": data,
            "nonce": self.w3.eth.get_transaction_count(self.wallet),
            "gas": 350000,
            "maxFeePerGas": self.w3.to_wei("5", "gwei"),
            "maxPriorityFeePerGas": self.w3.to_wei("1.5", "gwei"),
            "chainId": 11155111,
        }

        return self._send_tx(tx, f"Mint {amount} {product.upper()}")

    def _execute_stake(self, product: str, amount: int) -> tuple[bool, str]:
        """Stake C+→sC+ or T+→sT+."""
        # Stub: real implementation calls deposit(amount, receiver) on staking contract
        return False, "Stake not implemented in this snippet"

    def _execute_bridge(self, amount: int) -> tuple[bool, str]:
        """Bridge T+ via LayerZero OFT."""
        return False, "Bridge not implemented in this snippet"

    def _execute_transfer(self, product: str, amount: int) -> tuple[bool, str]:
        """Self-transfer for send/receive tasks."""
        return False, "Transfer not implemented in this snippet"

    def _execute_daily_txs(self, count: int) -> tuple[bool, str]:
        """Execute N small transactions to meet daily TX quota."""
        return False, "Daily TX not implemented in this snippet"

    def _send_tx(self, tx: dict, label: str) -> tuple[bool, str]:
        """Sign, send, and wait for transaction receipt."""
        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] == 1:
            print(f"   ✅ {label} gas={receipt['gasUsed']} block={receipt['blockNumber']}")
            return True, tx_hash.hex()
        else:
            return False, f"TX reverted: {tx_hash.hex()}"

    def run_daily(self):
        """Main entry point: run all daily tasks."""
        print(f"\n{'='*60}")
        print(f"🚀 Overlayer Daily Run | {datetime.utcnow().isoformat()}")
        print(f"{'='*60}\n")

        token = self.authenticate()
        print(f"✅ Authenticated")

        tasks = self.fetch_tasks(token)
        print(f"\n📋 {len(tasks)} tasks today:")
        for t in tasks:
            print(f"   [{t['type'].upper():8}] {t['amount']:6} ({t.get('product','')}) | {t['points']:4} pts")

        # MiMo planning
        plan = self.plan_execution(tasks)

        # Execute
        results = []
        for task in tasks:
            success, result = self.execute_task(task)
            results.append({"task": task["id"], "success": success, "result": result})
            time.sleep(2)

        # Summary
        print(f"\n{'='*60}")
        print(f"📊 SUMMARY")
        print(f"{'='*60}")
        for r in results:
            mark = "✅" if r["success"] else "❌"
            print(f"   {mark} {r['task']}")

        # MiMo usage
        usage = self.mimo.get_usage_summary()
        if usage:
            print(f"\n💎 MiMo Token Usage:")
            for task_type, stats in usage.items():
                print(f"   {task_type:20} | {stats['calls']:3} calls | {stats['total_tokens']:8} tokens")


def main():
    parser = argparse.ArgumentParser(description="Overlayer Testnet Agent (MiMo-powered)")
    parser.add_argument("--mode", choices=["daily", "monitor"], default="daily")
    parser.add_argument("--interval", type=int, default=86400, help="Monitor interval (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Plan but don't send transactions")
    args = parser.parse_args()

    agent = OverlayerAgent(dry_run=args.dry_run)

    if args.mode == "daily":
        agent.run_daily()
    elif args.mode == "monitor":
        while True:
            try:
                agent.run_daily()
            except Exception as e:
                print(f"❌ Daily run failed: {e}")
            print(f"\n⏳ Sleeping {args.interval}s until next run...")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
