# Sutra — Free Tier Model Strategy

## Available Free Tier Limits

### Groq (Text/Reasoning)

| Model | Params | RPM | RPD | TPM | TPD | Quality Tier |
|---|---|---|---|---|---|---|
| `kimi-k2-instruct` | 1T MoE (32B active) | 60 | 1K | 10K | 300K | 🥇 Elite |
| `llama-3.3-70b-versatile` | 70B dense | 30 | 1K | 12K | 100K | 🥈 Strong |
| `qwen/qwen3-32b` | 32B | 60 | 1K | 6K | 500K | 🥉 Good |
| `llama-3.1-8b-instant` | 8B | 30 | 14.4K | 6K | 500K | ⚡ Fast |

### Gemini (Text)

| Model | RPM | RPD | TPM |
|---|---|---|---|
| `Gemini 2.5 Flash` | 5 | 20 | 250K |
| `Gemini 2.5 Flash Lite` | 10 | 20 | 250K |
| `Gemini 3 Flash` | 5 | 20 | 250K |
| `Gemini 3.1 Flash Lite` | 15 | 500 | 250K |
| `Gemma 3 27B` | 30 | 14.4K | 15K |

### Gemini (Specialized — No Groq Equivalent)

| Model | RPM | RPD | Purpose |
|---|---|---|---|
| `Gemini Embedding 2` | 100 | 1K | Embeddings / RAG |
| `Gemini 2.5 Flash Audio` | ∞ | ∞ | Live voice/audio |
| `Gemini 2.5 Flash TTS` | 3 | 10 | Text-to-speech |
| `Imagen 4 Fast Generate` | — | 25 | Image generation |

---

## Provider Strengths

| Dimension | Groq | Gemini |
|---|---|---|
| Daily request volume | ✅ 1K–14.4K RPD | ❌ 20–500 RPD |
| Burst speed (RPM) | ✅ 30–60 | ❌ 5–15 |
| Token window (TPM) | ❌ 6K–12K | ✅ 250K |
| Embeddings | ❌ | ✅ |
| Voice / Audio | ❌ | ✅ Unlimited |
| Image Generation | ❌ | ✅ |

> **Strategy:** Groq for all agent reasoning (~50x more daily calls). Gemini for embeddings, voice, images, and rare long-context calls.

---

## Agent Role → Model Assignment

### Tier 1 — Elite Reasoning (`kimi-k2-instruct`)

| Role | Why |
|---|---|
| 🧑‍💼 **CEO** | Highest-stakes strategic decisions need best reasoning (1T MoE) |
| 💻 **Software Engineer** | Dominant agentic coder; SWE-bench leader; 200+ sequential tool calls |
| 📊 **Data Analyst** | Tool-calling champion for SQL/code + complex data interpretation |
| 📋 **Product Manager** | Strong structured output for PRDs, roadmaps, planning |

### Tier 2 — Strict Compliance (`llama-3.3-70b-versatile`)

| Role | Why |
|---|---|
| 🔒 **Security Specialist** | Best instruction following (IFEval); security needs rigid compliance |
| 💰 **Finance Analyst** | Precision + strict adherence critical for financial accuracy |
| 🔬 **Research Specialist** | Deep synthesis from dense 70B; fallback to `qwen3-32b` for volume |

### Tier 3 — Volume + Creative (`qwen/qwen3-32b`)

| Role | Why |
|---|---|
| 📣 **Marketing Specialist** | Creative content + highest TPD (500K) for volume |
| 🤝 **Customer Success** | Quality + 60 RPM for higher-frequency interactions |
| 👥 **HR Manager** | Structured, empathetic responses; right-sized quality |

### Utility Layer

| Purpose | Model | Provider |
|---|---|---|
| Routing / Classification | `llama-3.1-8b-instant` | Groq |
| Embeddings / Memory | `Gemini Embedding 2` | Gemini |
| Voice / Live Audio | `Gemini 2.5 Flash Audio` | Gemini |
| Image Generation | `Imagen 4 Fast Generate` | Gemini |
| Long-context fallback | `Gemini 2.5 Flash Lite` | Gemini |
| High-volume overflow | `Gemma 3 27B` | Gemini |

---

## Daily Budget Estimate

| Model | RPD | Roles Sharing | ~Calls/Role/Day |
|---|---|---|---|
| `kimi-k2` | 1,000 | 4 roles | ~250 each |
| `llama-3.3-70b` | 1,000 | 3 roles | ~333 each |
| `qwen3-32b` | 1,000 | 3 roles | ~333 each |
| `llama-3.1-8b` | 14,400 | Routing only | 14,400 |
| **Total reasoning calls** | **~4,000/day** | | |
