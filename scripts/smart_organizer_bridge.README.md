# Smart Organizer host bridge

The `smart_organizer` extension runs inside the Docker backend, which cannot
reach macOS apps. This daemon runs on the **host** and does the macOS I/O
(read Apple Mail, write Reminders/Notes) on the extension's behalf, over
`http://host.docker.internal:7477`.

## Setup

`./install.sh` handles this: it generates `SMART_ORGANIZER_BRIDGE_TOKEN`, sets
`SMART_ORGANIZER_BRIDGE_PORT=7477` in `backend/.env`, renders the launchd plist
into `~/Library/LaunchAgents/com.sutra.smart-organizer-bridge.plist`, and offers
to load it.

Then, in **Settings ▸ Integrations ▸ Smart Organizer**, set:
- **Host Bridge URL**: `http://host.docker.internal:7477`
- **Host Bridge Token**: the `SMART_ORGANIZER_BRIDGE_TOKEN` value from `backend/.env`

### First run: grant Automation access

The first time the daemon touches Mail / Reminders / Notes, macOS prompts for
Automation permission. Approve it under **System Settings ▸ Privacy & Security ▸
Automation**. Until granted, those endpoints return empty results.

### Manual control

```bash
launchctl load   ~/Library/LaunchAgents/com.sutra.smart-organizer-bridge.plist
launchctl unload ~/Library/LaunchAgents/com.sutra.smart-organizer-bridge.plist
tail -f ~/Library/Logs/sutra-smart-organizer.log
# Run in the foreground for debugging:
python3 scripts/smart_organizer_bridge.py
```

## Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | — | `{ok, envelope_index, version}` |
| GET | `/mail/new` | `?after=<rowid>&limit=<n>` | `{messages: [...]}` |
| GET | `/mail/body` | `?message_id=<id>` | `{body}` |
| POST | `/reminders` | `{title, due}` | `{ok, id}` |
| GET | `/reminders/status` | `?id=<id>` | `{status}` (completed/open/missing) |
| POST | `/notes/append` | `{line}` | `{ok}` |
| POST | `/arrival` | `{message_id?}` | `{ok}` |

## Batch schedule

The 4-hour batch cycle reuses the existing **Job** scheduler (no bridge
involvement): create a Job with `execution_type='prompt'`, cron `0 */4 * * *`,
targeting a Smart-Organizer-enabled agent, with a prompt such as
*"Ingest new mail, run the batch classification, and route the results."*

## Real-time urgency: the Mail.app rule

For immediate triage on arrival, add a Mail rule that pings `/arrival`.

**Mail ▸ Settings ▸ Rules ▸ Add Rule** — condition "Every Message", action
"Run AppleScript", pointing at a script like:

```applescript
using terms from application "Mail"
    on perform mail action with messages theMessages for rule theRule
        set bridgeURL to "http://127.0.0.1:7477/arrival"
        set bridgeToken to "PASTE_SMART_ORGANIZER_BRIDGE_TOKEN"
        repeat with m in theMessages
            set mid to message id of m
            set payload to "{\"message_id\": \"" & mid & "\"}"
            do shell script "curl -s -X POST " & quoted form of bridgeURL & ¬
                " -H 'Content-Type: application/json'" & ¬
                " -H 'Authorization: Bearer " & bridgeToken & "'" & ¬
                " -d " & quoted form of payload
        end repeat
    end perform mail action with messages theMessages
end using terms from
```

Save the script under `~/Library/Application Scripts/com.apple.mail/` so Mail can
run it. When `SMART_ORGANIZER_ARRIVAL_WEBHOOK` is set in `backend/.env`, the
bridge forwards each arrival there (e.g. an endpoint that runs the organizer
agent's ingest + urgency triage); otherwise it spools arrivals to
`backend/.local/smart_organizer_arrivals.log` for later processing.
```
