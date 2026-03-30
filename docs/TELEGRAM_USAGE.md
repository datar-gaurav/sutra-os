# Telegram Integration Guide

Connect your Sutra agents to Telegram for mobile conversations, approval management, and project-scoped workflows.

---

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts to name your bot
3. Copy the **bot token** (e.g. `7123456789:AAH...`)

### 2. Configure Sutra

Add the bot token to your environment or set it in the Sutra UI under **Settings > Environment Variables**:

```env
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxx
```

Optionally set a default chat ID for system-wide notifications (approval alerts, agent online status, etc.):

```env
TELEGRAM_DEFAULT_CHAT_ID=123456789
```

The bot starts automatically when the backend launches. You'll see `Starting Telegram bot...` in the logs.

---

## Starting a Chat with the Bot

### Private chat (1-on-1)

1. Open Telegram and search for your bot by its username (e.g. `@YourSutraBotName`)
2. Open the chat and tap **Start**
3. Run `/connect <agent-name>` to link an agent
4. Start talking — the bot sees all messages in a private chat

### Group chat

1. Create a new Telegram group
2. Add your Sutra bot to the group
3. **Important**: By default, bots can only see `/commands` in groups (privacy mode). To let the bot see regular text messages, do one of:
   - **Disable privacy mode** (recommended): Go to **@BotFather** → `/setprivacy` → select your bot → **Disable**. Then **remove and re-add** the bot to the group (the change only applies to groups joined after the setting change).
   - **Make the bot a group admin**: This also bypasses privacy mode.
4. Run `/connect <agent-name>` in the group

Use `/chatid` in any chat to see its Telegram chat ID (useful for manual configuration). Group IDs are negative numbers (e.g. `-5205817399`) — this is normal.

---

## Connecting an Agent to a Chat

The easiest way to link an agent is directly from Telegram:

```
/connect Trader
```

That's it. The current chat is now linked to the Trader agent. All messages you send here will auto-route to Trader with full conversation history.

To check the current connection:
```
/connect
```

To switch to a different agent:
```
/connect DevOps
```
This automatically unlinks the previous agent and links the new one.

To unlink:
```
/disconnect
```

### Manual setup (alternative)

You can also link agents from the Sutra dashboard:

1. Go to **Agent Settings** for the agent
2. Set **Telegram Chat ID** to the chat/group ID
3. Enable **Telegram Enabled** toggle

### Multiple agents

Create separate Telegram groups for different agents:

1. Create a group (e.g. "Trading Bot")
2. Add your Sutra bot to the group
3. In the group, run `/connect Trader`

Repeat for other agents. Each group is an independent conversation with its linked agent.

---

## Commands

| Command | Description |
|---------|-------------|
| `/switch <agent>` | Switch active agent (keeps history per agent) |
| `/switch` | Show which agent is currently active |
| `/connect <agent>` | Link this chat to an agent (persists to DB) |
| `/connect` | Show which agent is linked to this chat |
| `/disconnect` | Unlink this chat from its agent |
| `/agents` | List all currently running agents |
| `/ask <agent> <message>` | Send a one-off message to a specific agent |
| `/project <name>` | Set the active project for this chat |
| `/project list` | List all available projects |
| `/project clear` | Remove the active project from this chat |
| `/project` | Show the currently active project |
| `/newchat` | Start a fresh conversation (clears history context) |
| `/chatid` | Show this chat's Telegram ID |
| `/status` | Check Sutra system status |
| `/forge <description>` | Start an autonomous feature build via Sutra Forge |
| `/start` | Show welcome message and command list |

### Talking to Agents

There are several ways to direct a message to a specific agent:

1. **Switch** (best for private chats) — `/switch Trader`, then just type normally. Switch between agents anytime and each keeps its own history.
2. **Connect** (best for groups) — `/connect Trader` permanently links a group chat to an agent in the DB.
3. **@mention** — Prefix your message: `@Trader what's my portfolio?`
4. **/ask command** — `/ask Trader what's my portfolio?` (one-off, doesn't change active agent)

If none of these match, the message goes to the default agent (Dash, or the first running agent).

### Switch vs Connect

| | `/switch` | `/connect` |
|---|---|---|
| Persists across bot restarts | No (session only) | Yes (saved to DB) |
| Changes agent DB settings | No | Yes (`telegram_chat_id`) |
| Multiple agents in one chat | Yes, swap anytime | One agent per chat |
| Best for | Private chats, quick switching | Dedicated group per agent |

---

## Conversations

The bot maintains **persistent conversation history** per agent per chat. When you send follow-up messages, the agent has full context of prior exchanges — just like the web UI.

Conversations are scoped by:
- **Agent** — each agent has its own conversation thread
- **Chat** — different Telegram chats maintain separate histories
- **Project** — switching projects starts a new conversation thread

Use `/newchat` to start a fresh thread without prior context.

---

## Projects

Set a project context to scope the agent's memory and decision tracking to a specific project.

```
/project list
/project my-project
```

Once set, all messages in that chat use the project's memory context. The agent will reference project-specific decisions, memories, and context.

```
/project clear
```

Removes the project scope. Messages return to the agent's default context.

---

## Approvals

When an agent requests human approval (for financial, destructive, external, or strategic actions), you'll receive a Telegram notification with **Approve** and **Reject** buttons.

```
Approval Required

Deploy v2.3.1 to production

Agent: DevOps
Category: destructive | Risk: high
ID: a1b2c3d4

[Approve]  [Reject]
```

Tap a button to decide. The message updates to show the result, and the agent proceeds (or stops) accordingly. Approved actions with an `action_payload` execute automatically.

### Where notifications are sent

1. If the requesting agent has a `telegram_chat_id` configured, the notification goes there
2. Otherwise, it falls back to the `TELEGRAM_DEFAULT_CHAT_ID`
3. If neither is set, the notification is skipped (approval is still visible in the web UI)

---

## Forge (Autonomous Builds)

Use `/forge` to kick off autonomous feature builds:

```
/forge Add dark mode toggle to the settings page in owner/repo
/forge Fix the login redirect bug in myorg/backend
```

The bot will report progress and ask for feedback inline via buttons.

Check active forge requests with `/forge status`.

---

## Quick Start Example

**Private chat with multiple agents:**
```
1. /switch Trader            — talk to Trader
2. What's my portfolio?      — Trader responds
3. Buy 10 shares of AAPL     — Trader requests approval
4. [Approve]                 — tap the button
5. /switch DevOps            — switch to DevOps
6. Deploy status?            — DevOps responds
7. /switch Trader            — back to Trader (history preserved)
8. How did that AAPL order go? — Trader remembers the context
```

**Dedicated group chat:**
```
1. /connect Trader           — permanently link group to Trader
2. /project alpha-fund       — scope to a project
3. Summarize recent trades   — project-scoped response
4. /newchat                  — start fresh conversation
```

## Tips

- **Group chats**: Add the bot to a Telegram group, run `/connect`, and everyone in the group shares the conversation with that agent.
- **Multiple agents**: Create separate groups and `/connect` each to a different agent.
- **Project switching**: `/project` changes context instantly. The agent starts a new conversation thread scoped to that project.
- **Approval speed**: Approvals via Telegram buttons are instant — no need to open the web UI for routine sign-offs.
- **One-off questions**: Use `/ask OtherAgent question` to ask a different agent without switching your connected agent.
