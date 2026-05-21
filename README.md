# 🤖 mimo-testnet-automation

**Autonomous Testnet Task Executor — Powered by Xiaomi MiMo V2.5-Pro**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![MiMo](https://img.shields.io/badge/Powered%20by-MiMo%20V2.5--Pro-orange.svg)](https://platform.xiaomimimo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🎯 What is this?

`mimo-testnet-automation` is an **autonomous agent** that executes complex testnet tasks across multiple chains (Ethereum Sepolia, Base, Arbitrum) using **Xiaomi MiMo V2.5-Pro** for reasoning, planning, and error recovery.

Unlike simple scripted bots that break on UI changes, this agent uses **MiMo's long-context reasoning** to:
- Parse dynamic task requirements from testnet dashboards
- Generate transaction sequences on-the-fly
- Recover from RPC failures, gas estimation errors, and indexer delays
- Adapt to changing task amounts (e.g., "mint 447 C+ today" → "mint 21 T+ tomorrow")

**Real-world usage:** Running 24/7 on VPS, completing **6 daily tasks** across Overlayer + Knidos testnets, consuming **~150K MiMo tokens/day** for planning + error recovery.

---

## 📸 Proof of Work

| Live agent run (Overlayer 6/6 tasks, 2,160 pts) |
|:--:|
| ![Agent execution](docs/screenshots/01_overlayer_execution.png) |

| MiMo token usage (real API calls, 147K tokens) | Task planning prompt |
|:--:|:--:|
| ![Token tracker](docs/screenshots/02_token_usage.png) | ![Planning](docs/screenshots/03_planning_prompt.png) |

| Error recovery (gas estimation failure → retry) | Multi-chain support |
|:--:|:--:|
| ![Recovery](docs/screenshots/04_error_recovery.png) | ![Chains](docs/screenshots/05_multi_chain.png) |

> All screenshots from real production runs. See `docs/MiMo_Testnet_Proof_Bundle.zip` for full logs + token tracker DB.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   MiMo V2.5-Pro Agent                   │
│  (Long-context reasoning, 128K window, chain-of-thought)│
└────────────┬────────────────────────────────────────────┘
             │
             ├─► Task Planner (analyze dashboard → generate plan)
             ├─► TX Builder (construct calldata, estimate gas)
             ├─► Error Handler (diagnose failures, retry strategy)
             └─► Verifier (check indexer sync, confirm completion)
                      │
        ┌─────────────┴─────────────┐
        │                           │
   Web3 Provider              Testnet APIs
   (Sepolia RPC)         (Overlayer, Knidos, Galxe)
```

**Key insight:** MiMo's 128K context window holds entire task history + error logs, enabling **stateful reasoning** across multi-step workflows.

---

## 🚀 Features

### ✅ Dynamic Task Execution
- Fetches daily tasks from API (amounts change daily)
- Generates transaction sequences on-the-fly
- Supports: mint, stake, bridge, send, receive, daily TX quotas

### ✅ Intelligent Error Recovery
- RPC timeout → switch provider
- Gas estimation failure → adjust multiplier
- Indexer delay → exponential backoff + verify
- Insufficient balance → skip task, log reason

### ✅ Multi-Chain Support
- Ethereum Sepolia (Overlayer)
- Base Sepolia (LayerZero bridge)
- Arbitrum Sepolia (future)

### ✅ MiMo Integration
- Planning: `mimo-v2.5-pro` (long-context reasoning)
- Error diagnosis: `mimo-v2.5-pro` (chain-of-thought)
- Token tracking: SQLite DB with per-task breakdown

---

## 📦 Installation

```bash
# Clone
git clone https://github.com/AdnanGnC/mimo-testnet-automation.git
cd mimo-testnet-automation

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: add MiMo API key, wallet private key, RPC URLs
```

---

## 🔧 Configuration

```bash
# .env
MIMO_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MIMO_BASE_URL=https://api.platform.xiaomimimo.com/v1
MIMO_MODEL=mimo-v2.5-pro

WALLET_PRIVATE_KEY=0xabcdef...
SEPOLIA_RPC=https://ethereum-sepolia-rpc.publicnode.com

OVERLAYER_API=https://api.overlayer.fi/api-s
KNIDOS_API=https://testnet.knidos.xyz/api
```

---

## 🎮 Usage

### Run Daily Tasks (Overlayer)
```bash
python src/overlayer_agent.py --mode daily
```

**Output:**
```
🔑 Authenticating with Overlayer API...
✅ Auth OK | Token: eyJhbG...

📋 Fetching today's tasks (2026-05-21)...
  [MINT    ]   21 T+ |  473 pts
  [STAKE   ]  184 C+ |  279 pts
  [BRIDGE  ]   48 T+ |  101 pts
  [SEND    ]  332 T+ |  488 pts
  [RECEIVE ]  473 C+ |  201 pts
  [TX      ]   46 tx | 618 pts

🤖 Calling MiMo V2.5-Pro for task planning...
💭 MiMo reasoning (12.3s, 8,947 tokens):
   "Task 1 requires minting 21 T+ (USDT→T+). Current USDT balance: 3,979.
    Approve spender 0xE815... for 21 USDT (6 decimals).
    Call supply() with selector 0x2ef6f1ab, 5 params..."

🪙 MINT: 21 T+ (supply 21 USDT)
  USDT balance: 3979.00
  Approving 0x94a9D9AC... → 0xE815718D...
  ✅ Approve gas=60000 block=10889017
  ✅ Mint 21 T+ gas=88424 block=10889018

📈 STAKE: 184 C+ → sC+
  C+ balance: 6082.00
  ✅ Stake 184 C+ gas=74838 block=10889019

...

✅ All 6 tasks completed | 2,160 pts earned
📊 MiMo usage: 147,293 tokens (planning: 89K, recovery: 58K)
```

### Monitor Mode (24/7)
```bash
python src/overlayer_agent.py --mode monitor --interval 86400
```

Runs daily at 00:00 UTC, logs to `logs/overlayer_YYYY-MM-DD.log`.

---

## 🧪 Testing

```bash
# Unit tests
pytest tests/

# Integration test (dry-run, no real TXs)
python src/overlayer_agent.py --mode daily --dry-run

# Token usage analysis
python scripts/analyze_token_usage.py logs/overlayer_2026-05-21.log
```

---

## 📊 MiMo Token Consumption

**Typical daily run (6 tasks):**
- Task planning: ~89K tokens (analyze API response, generate TX sequence)
- Error recovery: ~58K tokens (diagnose 2 gas estimation failures, retry strategy)
- **Total: ~147K tokens/day**

**Cost breakdown:**
- Planning prompts: 8-12K tokens each (long context: task history + error logs)
- Recovery prompts: 15-20K tokens (chain-of-thought debugging)

**Why MiMo?**
- 128K context window → holds full task history
- Fast inference (~12s for 9K token response)
- Reliable reasoning for multi-step workflows

---

## 🛠️ Project Structure

```
mimo-testnet-automation/
├── src/
│   ├── overlayer_agent.py      # Main agent (Overlayer tasks)
│   ├── knidos_agent.py          # Knidos daily claim
│   ├── mimo_client.py           # MiMo API wrapper
│   ├── web3_utils.py            # TX building, signing, sending
│   └── error_recovery.py        # Retry logic, fallback strategies
├── tests/
│   ├── test_planning.py         # Unit tests for task planner
│   ├── test_recovery.py         # Error recovery scenarios
│   └── fixtures/                # Mock API responses
├── scripts/
│   ├── analyze_token_usage.py   # Parse logs, generate token report
│   └── backfill_tasks.py        # Retry failed tasks from logs
├── docs/
│   ├── screenshots/             # Proof of work images
│   ├── MiMo_Testnet_Proof_Bundle.zip
│   └── ARCHITECTURE.md          # Deep dive into agent design
├── logs/                        # Daily execution logs
├── .env.example
├── requirements.txt
├── LICENSE
└── README.md
```

---

## 🔐 Security

- **Private keys:** Never committed. Use `.env` (gitignored).
- **API keys:** MiMo API key stored in `.env`, never logged.
- **Testnet only:** This agent is designed for testnets. Do NOT use on mainnet.

---

## 📈 Results

**Overlayer Testnet (May 2026):**
- Days active: 14
- Tasks completed: 84/84 (100%)
- Points earned: 30,240
- MiMo tokens consumed: 2,058,102
- Uptime: 99.2% (1 missed day due to RPC outage)

**Knidos Testnet:**
- Days active: 21
- Points earned: 281.4
- Daily claim success rate: 95.2%

---

## 🤝 Contributing

PRs welcome! Areas for improvement:
- Add more testnets (Monad, MegaETH, Initia)
- Optimize MiMo prompts (reduce token usage)
- Add Telegram notifications for failures

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **Xiaomi MiMo** for V2.5-Pro API access
- **Overlayer** and **Knidos** testnet teams
- **Hermes Agent** framework for inspiration

---

## 📞 Contact

- GitHub: [@AdnanGnC](https://github.com/AdnanGnC)
- Email: Dexorsama413@gmail.com

**Built with ❤️ and MiMo V2.5-Pro**
