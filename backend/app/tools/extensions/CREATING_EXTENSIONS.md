# Creating Sutra OS Extensions

This document is a complete reference for AI models and developers to create new Sutra OS extensions. An extension is a single Python file that adds custom tools to agents. Extensions are auto-discovered, configured via the UI, and work exactly like built-in integrations.

## File location

Place your extension file in:

```
backend/app/tools/extensions/<your_extension>.py
```

The filename must NOT start with an underscore (`_`). Files starting with `_` and `__init__.py` are ignored by the loader.

## Required exports

Every extension file must export exactly two things at the module level:

1. `EXTENSION_MANIFEST` - a dict describing the extension metadata
2. `create_tools(agent_id: str)` - a factory function returning LangChain tools

There is also one optional export:

3. `test_connection(creds: dict, config: dict)` - an async function to validate credentials

---

## EXTENSION_MANIFEST

A module-level dict with the following keys:

### Required keys

| Key | Type | Description |
|-----|------|-------------|
| `id` | `str` | Unique slug for this extension. Used as the integration type in the database. Must not collide with built-in types: `notion`, `linear`, `jira`, `slack`, `gitlab`, `github`, `google_drive`, `google_calendar`. Use lowercase with underscores. |
| `name` | `str` | Human-readable display name shown in the UI. |
| `description` | `str` | One-line description of what the extension does. |
| `credential_fields` | `list[dict]` | Fields for secrets (API keys, tokens). Each dict has keys: `key` (str), `label` (str), `secret` (bool, should be `True` for sensitive values), `placeholder` (str, optional). |
| `config_fields` | `list[dict]` | Fields for non-secret configuration (base URLs, default values). Same dict shape as `credential_fields` but `secret` should be `False`. |
| `tool_ids` | `list[str]` | List of tool ID strings. Each ID must exactly match the function name of a tool returned by `create_tools()`. |

### Optional keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `icon` | `str` | `"puzzle"` | Lucide icon name for the UI (e.g., `"bar-chart-3"`, `"wallet"`, `"send"`). See https://lucide.dev/icons for options. |
| `version` | `str` | `""` | Semver version string displayed in the UI. |
| `author` | `str` | `""` | Author name or organization. |
| `is_dangerous` | `bool` | `False` | If `True`, all tools in this extension are marked as dangerous (requires human approval when agent's `auto_approve_below` threshold is set). Set this for extensions that perform write operations (place orders, send messages, delete data). |

### Example manifest

```python
EXTENSION_MANIFEST = {
    "id": "alpaca",
    "name": "Alpaca Trading",
    "description": "Fetch portfolio positions and place trades via Alpaca Markets API",
    "icon": "bar-chart-3",
    "version": "1.0.0",
    "author": "Sutra Community",
    "credential_fields": [
        {"key": "api_key", "label": "API Key ID", "secret": True, "placeholder": "PK..."},
        {"key": "api_secret", "label": "Secret Key", "secret": True, "placeholder": "your-secret-key"},
    ],
    "config_fields": [
        {"key": "base_url", "label": "API Base URL", "secret": False, "placeholder": "https://paper-api.alpaca.markets"},
    ],
    "tool_ids": ["alpaca_get_portfolio", "alpaca_place_order"],
    "is_dangerous": True,
}
```

### credential_fields vs config_fields

- **credential_fields**: Values are encrypted at rest using the Sutra vault (Fernet encryption). Never logged, never returned by the API. Use for API keys, tokens, passwords, secrets.
- **config_fields**: Stored as plain JSON in `extra_config`. Use for base URLs, default project IDs, region selectors, toggle flags, or anything non-sensitive.

Both field types render as form inputs in the Integrations UI. The `placeholder` value is shown as the input hint.

---

## create_tools(agent_id: str)

A synchronous factory function that returns a list of LangChain tool instances. It is called each time an agent that has these tools enabled is started or invoked.

### Contract

```python
def create_tools(agent_id: str) -> list:
```

- **Input**: `agent_id` (str) - the UUID of the agent using these tools. Used to look up agent-specific or system-wide credentials.
- **Output**: A list of LangChain `BaseTool` instances (created with the `@tool` decorator).
- **Must be synchronous**: The function itself is sync. The tools it returns can (and should) be async.

### Fetching credentials inside tools

Use the provided helper to fetch credentials at tool invocation time (not at factory time):

```python
from app.tools.extensions._helpers import get_extension_creds
```

**Signature:**
```python
async def get_extension_creds(extension_id: str, agent_id: str) -> tuple[dict, dict]
```

- `extension_id`: Must match your manifest's `id` field.
- `agent_id`: Pass through the `agent_id` from `create_tools()`.
- Returns: `(credentials_dict, extra_config_dict)`.
  - `credentials_dict` contains the decrypted values from `credential_fields` (e.g., `{"api_key": "PK...", "api_secret": "..."}`).
  - `extra_config_dict` contains the plain values from `config_fields` (e.g., `{"base_url": "https://..."}`).
- Raises `ValueError` if no active integration is configured for this extension.

**Credential lookup order:**
1. Agent-specific integration (where `agent_id` matches)
2. System-wide integration (where `agent_id` is `None`)

This means users can set a global default and override per-agent if needed.

### Tool implementation rules

1. **Use the `@tool` decorator** from `langchain_core.tools`:
   ```python
   from langchain_core.tools import tool
   ```

2. **Tools must be async** (`async def`). The Sutra agent runtime is fully async.

3. **Function name = tool ID**. The function name must exactly match an entry in `tool_ids` in the manifest. If they don't match, the tool won't be found when agents try to use it.

4. **Return type must be `str`**. LangChain tools return string results to the LLM. Format your output as human-readable text that the LLM can interpret and relay to the user.

5. **Docstrings are critical**. The tool's docstring is sent to the LLM as the tool description. It determines when and how the LLM decides to call the tool. Write clear, specific docstrings that explain:
   - What the tool does
   - What each parameter means
   - What the output looks like

6. **Use `Args:` section in docstrings** for multi-parameter tools. LangChain parses this to generate the tool's input schema description:
   ```python
   @tool
   async def my_tool(symbol: str, qty: int = 1) -> str:
       """Do something with a stock.

       Args:
           symbol: Stock ticker (e.g. AAPL, TSLA).
           qty: Number of shares (default 1).
       """
   ```

7. **Type hints on parameters** are required. LangChain uses them to generate the JSON schema for the LLM's function calling. Use `str`, `int`, `float`, `bool`. For optional parameters, use defaults.

8. **Import `get_extension_creds` inside `create_tools()`**, not at the module top level. This avoids circular import issues during extension discovery:
   ```python
   def create_tools(agent_id: str):
       from app.tools.extensions._helpers import get_extension_creds
       # ...
   ```

9. **Use `httpx.AsyncClient` for HTTP calls**. It is already a project dependency. Always set a `timeout`:
   ```python
   import httpx

   async with httpx.AsyncClient(timeout=15) as client:
       resp = await client.get(url, headers=headers)
       resp.raise_for_status()
   ```

10. **Handle errors gracefully**. If an API call fails, let the exception propagate — LangChain will catch it and show the error to the LLM, which can then inform the user. For expected error cases, return a descriptive error string instead:
    ```python
    if not positions:
        return "No open positions found."
    ```

### Pattern: shared auth helper inside create_tools

When multiple tools share the same authentication setup, define a private async helper inside `create_tools()`:

```python
def create_tools(agent_id: str):
    from app.tools.extensions._helpers import get_extension_creds

    async def _auth():
        creds, config = await get_extension_creds("my_extension", agent_id)
        base = (config.get("base_url") or "https://api.example.com").rstrip("/")
        headers = {"Authorization": f"Bearer {creds['api_key']}"}
        return headers, base

    @tool
    async def my_tool_one(...) -> str:
        headers, base = await _auth()
        # ...

    @tool
    async def my_tool_two(...) -> str:
        headers, base = await _auth()
        # ...

    return [my_tool_one, my_tool_two]
```

---

## test_connection (optional)

An async function that validates credentials by making a lightweight API call. If present, it is called when the user clicks "Test" on the integration in the UI.

### Contract

```python
async def test_connection(creds: dict, config: dict) -> dict:
```

- **Input**:
  - `creds`: Decrypted credential values (same shape as what `get_extension_creds` returns as the first element).
  - `config`: Extra config values (same shape as the second element).
- **Output**: A dict with:
  - `ok` (bool): Whether the test passed.
  - `detail` (str): A human-readable message (e.g., `"Connected as user@example.com"`).

### Example

```python
async def test_connection(creds: dict, config: dict) -> dict:
    base = (config.get("base_url") or "https://api.example.com").rstrip("/")
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base}/v1/me", headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return {"ok": True, "detail": f"Connected as {data.get('name', 'unknown')}"}
```

If this function is not defined, the UI will show "No test available for this extension" when the user clicks Test.

---

## Complete template

Copy this template to start a new extension:

```python
"""<Extension Name> extension for Sutra OS.

Drop this file into backend/app/tools/extensions/ and configure
via the Integrations page.

Provides:
  - <tool_id_1>: <short description>
  - <tool_id_2>: <short description>
"""

import httpx
from langchain_core.tools import tool

EXTENSION_MANIFEST = {
    "id": "<unique_slug>",
    "name": "<Display Name>",
    "description": "<One-line description>",
    "icon": "<lucide-icon-name>",
    "version": "1.0.0",
    "author": "<Your Name>",
    "credential_fields": [
        {"key": "api_key", "label": "API Key", "secret": True, "placeholder": "your-api-key"},
    ],
    "config_fields": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "https://api.example.com"},
    ],
    "tool_ids": ["<tool_id_1>", "<tool_id_2>"],
    "is_dangerous": False,
}


def create_tools(agent_id: str):
    from app.tools.extensions._helpers import get_extension_creds

    async def _auth():
        creds, config = await get_extension_creds("<unique_slug>", agent_id)
        base = (config.get("base_url") or "https://api.example.com").rstrip("/")
        headers = {"Authorization": f"Bearer {creds['api_key']}"}
        return headers, base

    @tool
    async def <tool_id_1>() -> str:
        """<Clear description of what this tool does — this is shown to the LLM.>"""
        headers, base = await _auth()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base}/v1/resource", headers=headers)
            resp.raise_for_status()
        data = resp.json()
        return f"Result: {data}"

    @tool
    async def <tool_id_2>(param1: str, param2: int = 10) -> str:
        """<Clear description.>

        Args:
            param1: <What this parameter is.>
            param2: <What this parameter is (default 10).>
        """
        headers, base = await _auth()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base}/v1/action",
                headers=headers,
                json={"param1": param1, "param2": param2},
            )
            resp.raise_for_status()
        data = resp.json()
        return f"Done: {data.get('id')}"

    return [<tool_id_1>, <tool_id_2>]


async def test_connection(creds: dict, config: dict) -> dict:
    """Validate credentials with a lightweight API call."""
    base = (config.get("base_url") or "https://api.example.com").rstrip("/")
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{base}/v1/me", headers=headers)
        resp.raise_for_status()
    data = resp.json()
    return {"ok": True, "detail": f"Connected as {data.get('name', 'unknown')}"}
```

---

## Complete real-world example: Alpaca Trading

See `alpaca_trading.py` in this directory for a production-ready example that demonstrates:
- Two tools (read + write operations)
- Shared auth helper pattern
- Proper docstrings with `Args:` sections
- `test_connection` implementation
- Correct use of `is_dangerous: True` for write operations

---

## Validation rules

The extension loader validates these rules on discovery. If any fail, the extension is skipped with an error logged:

1. File must not start with `_`
2. File must be valid Python (no syntax errors)
3. `EXTENSION_MANIFEST` must exist as a module-level dict
4. Manifest must contain all required keys: `id`, `name`, `description`, `credential_fields`, `config_fields`, `tool_ids`
5. `id` must be a non-empty string
6. `tool_ids` must be a list of strings
7. `credential_fields` must be a list
8. `config_fields` must be a list
9. `create_tools` must exist as a callable
10. `id` must not collide with a built-in integration type

## Tool ID naming conventions

- Use lowercase with underscores: `my_extension_get_data`
- Prefix all tool IDs with the extension ID to avoid collisions: `alpaca_get_portfolio`, not `get_portfolio`
- Use verb-first naming: `get`, `list`, `create`, `update`, `delete`, `search`, `send`, `place`

## Reserved integration IDs (do not use)

`notion`, `linear`, `jira`, `slack`, `gitlab`, `github`, `google_drive`, `google_calendar`

---

## How to activate after creating the file

1. Place the file in `backend/app/tools/extensions/`
2. Either:
   - Restart the backend, OR
   - Go to the Integrations page in the UI and click "Refresh" in the Extensions section, OR
   - Call `POST /api/integrations/extensions/refresh` directly
3. The extension appears in the Extensions section of the Integrations page
4. Click it to configure credentials and settings
5. Go to any agent's settings and enable the extension's tools from the tool picker
6. Start/restart the agent — the tools are now available

---

## Tips for writing good tools

1. **Return structured, readable text.** The LLM reads the output. Use line breaks, labels, and formatting:
   ```python
   return "\n".join([
       f"Account: {data['account_number']}",
       f"Balance: ${data['balance']}",
       f"Status: {data['status']}",
   ])
   ```

2. **Keep tool count small.** 2-5 tools per extension is ideal. Each tool should do one thing well. The LLM's ability to choose the right tool degrades with too many options.

3. **Prefer fewer parameters with sane defaults.** The LLM has to fill in every required parameter. Make parameters optional with defaults where sensible.

4. **Write docstrings as if explaining to a capable assistant.** The LLM uses the docstring to decide when to call the tool and what arguments to pass. Be specific about formats, constraints, and what the tool returns.

5. **Don't return raw JSON.** Parse the API response and return a human-readable summary. The LLM will relay this to the user.

6. **Set appropriate timeouts.** Use 10-15 seconds for typical API calls. Use longer (30-60s) for operations that take time (file uploads, batch processing).

7. **Use `is_dangerous: True`** for any tool that modifies state (creates, updates, deletes, sends, or spends money). This integrates with Sutra's approval gate system.
