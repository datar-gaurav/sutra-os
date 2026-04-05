"""Interactive browser automation tools — persistent sessions with recording support."""

import json
import logging
import os
import re
import tempfile
import time
from ipaddress import ip_address
from urllib.parse import urlparse

import yaml
from langchain_core.tools import BaseTool, tool

from app.config import settings
from app.core.browser_session_manager import (
    browser_session_manager,
    current_conversation_id,
)

logger = logging.getLogger(__name__)

BROWSER_TOOL_IDS = {
    "browser_open",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_extract_text",
    "browser_extract_data",
    "browser_wait",
    "browser_select",
    "browser_scroll",
    "browser_navigate",
    "browser_close",
    "browser_record_start",
    "browser_record_stop",
    "browser_record_status",
}

# Blocked URL schemes and internal IP ranges for SSRF prevention
_BLOCKED_SCHEMES = {"file", "ftp", "data"}


def _is_url_safe(url: str) -> tuple[bool, str]:
    """Check if a URL is safe to navigate to. Returns (safe, reason)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL."

    if parsed.scheme.lower() in _BLOCKED_SCHEMES:
        return False, f"Blocked URL scheme: {parsed.scheme}"

    # Block internal/private IPs
    hostname = parsed.hostname or ""
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Navigation to localhost is blocked."
    try:
        addr = ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_reserved:
            return False, f"Navigation to private/reserved IP {hostname} is blocked."
    except ValueError:
        pass  # Not an IP literal — hostname is fine

    return True, ""


async def _page_summary(page) -> str:
    """Generate a concise text summary of the current page state."""
    title = await page.title()
    url = page.url

    # Get interactive elements via accessibility snapshot
    try:
        snapshot = await page.accessibility.snapshot()
        elements = []
        if snapshot and snapshot.get("children"):
            for child in snapshot["children"][:50]:
                role = child.get("role", "")
                name = child.get("name", "")
                if role in (
                    "link",
                    "button",
                    "textbox",
                    "checkbox",
                    "combobox",
                    "menuitem",
                    "tab",
                    "searchbox",
                ):
                    elements.append(f"  [{role}] {name}" if name else f"  [{role}]")
        elements_text = "\n".join(elements[:30]) if elements else "  (none detected)"
    except Exception:
        elements_text = "  (accessibility snapshot unavailable)"

    return (
        f"Page: {title}\n"
        f"URL: {url}\n"
        f"Interactive elements:\n{elements_text}"
    )


def create_browser_tools(agent_id: str) -> list[BaseTool]:
    """Factory: create browser automation tools bound to an agent."""

    async def _get_session():
        conv_id = current_conversation_id.get()
        return await browser_session_manager.get_or_create_session(agent_id, conv_id)

    # ── Navigation & page tools ─────────────────────────────────────────

    @tool
    async def browser_open(url: str, wait_until: str = "networkidle") -> str:
        """Open a URL in the browser. Returns page title, URL, and interactive elements.

        Args:
            url: The URL to navigate to.
            wait_until: When to consider navigation done — "networkidle", "load", or "domcontentloaded".
        """
        safe, reason = _is_url_safe(url)
        if not safe:
            return f"Refused to open URL: {reason}"

        try:
            session = await _get_session()
            await session.page.goto(url, wait_until=wait_until, timeout=30000)
            summary = await _page_summary(session.page)
            session.log_action("browser_open", {"url": url}, summary.split("\n")[0])
            return summary
        except Exception as e:
            return f"Failed to open {url}: {e}"

    @tool
    async def browser_click(selector: str = "", text: str = "") -> str:
        """Click an element on the page by CSS selector or visible text.

        Args:
            selector: CSS selector of the element to click (e.g., "button.submit", "#login-btn").
            text: Visible text to find and click (e.g., "Sign In"). Used if selector is empty.
        """
        if not selector and not text:
            return "Provide either a CSS selector or text to identify the element to click."
        try:
            session = await _get_session()
            if selector:
                await session.page.click(selector, timeout=15000)
                desc = f"Clicked element matching '{selector}'."
            else:
                await session.page.get_by_text(text, exact=False).first.click(timeout=15000)
                desc = f"Clicked element with text '{text}'."
            # Wait briefly for any navigation or re-render
            await session.page.wait_for_timeout(1000)
            summary = await _page_summary(session.page)
            session.log_action(
                "browser_click",
                {"selector": selector, "text": text},
                desc,
            )
            return f"{desc}\n\nCurrent state:\n{summary}"
        except Exception as e:
            return f"Click failed: {e}"

    @tool
    async def browser_type(
        selector: str, text: str, clear_first: bool = True
    ) -> str:
        """Type text into an input field.

        Args:
            selector: CSS selector of the input field (e.g., "#email", "input[name='username']").
            text: The text to type.
            clear_first: If True, clears the field before typing (uses fill). If False, appends (uses type).
        """
        try:
            session = await _get_session()
            if clear_first:
                await session.page.fill(selector, text, timeout=15000)
            else:
                await session.page.type(selector, text, timeout=15000)
            desc = f"Typed into '{selector}'."
            session.log_action(
                "browser_type",
                {"selector": selector, "text": text, "clear_first": clear_first},
                desc,
            )
            return desc
        except Exception as e:
            return f"Type failed: {e}"

    @tool
    async def browser_screenshot(full_page: bool = False) -> str:
        """Take a screenshot and return a text description of the visible page.

        The screenshot is saved to a temp file. The return value is a text
        description of the page via accessibility tree — not the image itself.

        Args:
            full_page: If True, captures the entire scrollable page.
        """
        try:
            session = await _get_session()
            path = os.path.join(
                tempfile.gettempdir(),
                f"sutra_screenshot_{agent_id}_{int(time.time())}.png",
            )
            await session.page.screenshot(path=path, full_page=full_page)
            summary = await _page_summary(session.page)
            session.log_action("browser_screenshot", {"full_page": full_page}, "Screenshot taken.")
            return f"Screenshot saved to {path}\n\n{summary}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    @tool
    async def browser_extract_text(selector: str = "body") -> str:
        """Extract visible text content from an element on the page.

        Args:
            selector: CSS selector of the element to extract from. Defaults to full page body.
        """
        try:
            session = await _get_session()
            text = await session.page.inner_text(selector, timeout=15000)
            if len(text) > 15000:
                text = text[:15000] + "\n... [TRUNCATED]"
            session.log_action("browser_extract_text", {"selector": selector}, f"Extracted {len(text)} chars.")
            return text
        except Exception as e:
            return f"Extract text failed: {e}"

    @tool
    async def browser_extract_data(
        selector: str, attributes: str = ""
    ) -> str:
        """Extract structured data from multiple matching elements.

        Returns a JSON list of objects with each element's text and requested attributes.

        Args:
            selector: CSS selector matching the elements (e.g., "table tr", ".product-card").
            attributes: Comma-separated HTML attribute names to extract (e.g., "href,data-id"). Leave empty for text only.
        """
        try:
            session = await _get_session()
            attr_list = [a.strip() for a in attributes.split(",") if a.strip()] if attributes else []

            elements = await session.page.query_selector_all(selector)
            results = []
            for el in elements[:100]:  # Cap at 100 elements
                item = {"text": (await el.inner_text()).strip()}
                for attr in attr_list:
                    item[attr] = await el.get_attribute(attr)
                results.append(item)

            output = json.dumps(results, indent=2, ensure_ascii=False)
            if len(output) > 15000:
                output = output[:15000] + "\n... [TRUNCATED]"
            session.log_action(
                "browser_extract_data",
                {"selector": selector, "attributes": attributes},
                f"Extracted {len(results)} elements.",
            )
            return output
        except Exception as e:
            return f"Extract data failed: {e}"

    @tool
    async def browser_wait(
        selector: str, state: str = "visible", timeout: int = 10000
    ) -> str:
        """Wait for an element to reach a specific state.

        Args:
            selector: CSS selector of the element to wait for.
            state: Target state — "visible", "hidden", "attached", or "detached".
            timeout: Maximum wait time in milliseconds.
        """
        try:
            session = await _get_session()
            await session.page.wait_for_selector(selector, state=state, timeout=timeout)
            desc = f"Element '{selector}' is now {state}."
            session.log_action("browser_wait", {"selector": selector, "state": state}, desc)
            return desc
        except Exception as e:
            return f"Wait failed (timeout or element not found): {e}"

    @tool
    async def browser_select(
        selector: str, value: str = "", label: str = ""
    ) -> str:
        """Select an option from a dropdown (<select>) element.

        Args:
            selector: CSS selector of the <select> element.
            value: The option's value attribute to select.
            label: The option's visible text to select (used if value is empty).
        """
        if not value and not label:
            return "Provide either value or label to select."
        try:
            session = await _get_session()
            if value:
                await session.page.select_option(selector, value=value, timeout=15000)
                desc = f"Selected value '{value}' in '{selector}'."
            else:
                await session.page.select_option(selector, label=label, timeout=15000)
                desc = f"Selected label '{label}' in '{selector}'."
            session.log_action(
                "browser_select",
                {"selector": selector, "value": value, "label": label},
                desc,
            )
            return desc
        except Exception as e:
            return f"Select failed: {e}"

    @tool
    async def browser_scroll(
        direction: str = "down", amount: int = 500, selector: str = ""
    ) -> str:
        """Scroll the page or a specific element.

        Args:
            direction: "up" or "down".
            amount: Pixels to scroll.
            selector: CSS selector of a scrollable container. Leave empty to scroll the page.
        """
        try:
            session = await _get_session()
            delta = amount if direction == "down" else -amount
            if selector:
                await session.page.eval_on_selector(
                    selector,
                    f"el => el.scrollBy(0, {delta})",
                )
            else:
                await session.page.evaluate(f"window.scrollBy(0, {delta})")
            await session.page.wait_for_timeout(500)
            scroll_y = await session.page.evaluate("window.scrollY")
            desc = f"Scrolled {direction} by {amount}px. Page scroll position: {scroll_y}px."
            session.log_action(
                "browser_scroll",
                {"direction": direction, "amount": amount},
                desc,
            )
            return desc
        except Exception as e:
            return f"Scroll failed: {e}"

    @tool
    async def browser_navigate(action: str) -> str:
        """Navigate back or forward in browser history.

        Args:
            action: "back" or "forward".
        """
        try:
            session = await _get_session()
            if action == "back":
                await session.page.go_back(timeout=15000)
            elif action == "forward":
                await session.page.go_forward(timeout=15000)
            else:
                return f"Unknown action '{action}'. Use 'back' or 'forward'."
            await session.page.wait_for_timeout(1000)
            summary = await _page_summary(session.page)
            desc = f"Navigated {action}."
            session.log_action("browser_navigate", {"action": action}, desc)
            return f"{desc}\n\n{summary}"
        except Exception as e:
            return f"Navigate {action} failed: {e}"

    @tool
    async def browser_close() -> str:
        """Close the current browser session and free resources."""
        try:
            conv_id = current_conversation_id.get()
            await browser_session_manager.close_session(agent_id, conv_id)
            return "Browser session closed."
        except Exception as e:
            return f"Close failed: {e}"

    # ── Recording tools ─────────────────────────────────────────────────

    @tool
    async def browser_record_start(name: str, description: str = "") -> str:
        """Start recording browser actions to generate a reusable playbook.

        All subsequent browser_* tool calls will be captured until browser_record_stop is called.

        Args:
            name: Name for the playbook (used as filename, e.g., "login_to_jira").
            description: Optional description of what this playbook does.
        """
        try:
            session = await _get_session()
            if session.recording:
                return f"Already recording '{session.recording_name}'. Stop it first."
            session.start_recording(name, description)
            return f"Recording started: '{name}'. All browser actions will be captured."
        except Exception as e:
            return f"Failed to start recording: {e}"

    @tool
    async def browser_record_stop(save_as_playbook: bool = True) -> str:
        """Stop recording and optionally save the captured actions as a playbook .md file.

        Args:
            save_as_playbook: If True, saves the generated playbook to the playbooks directory.
        """
        try:
            session = await _get_session()
            if not session.recording:
                return "No recording is active."

            data = session.stop_recording()
            if not data["actions"]:
                return "Recording stopped but no actions were captured."

            playbook_md = _generate_playbook(data)

            if save_as_playbook:
                playbooks_dir = getattr(settings, "playbooks_dir", "data/playbooks")
                # Resolve relative to backend directory
                if not os.path.isabs(playbooks_dir):
                    playbooks_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        playbooks_dir,
                    )
                os.makedirs(playbooks_dir, exist_ok=True)
                safe_name = re.sub(r"[^\w\-]", "_", data["name"]).lower()
                filepath = os.path.join(playbooks_dir, f"{safe_name}.md")
                with open(filepath, "w") as f:
                    f.write(playbook_md)
                return (
                    f"Recording stopped. Playbook saved to {filepath}\n\n"
                    f"--- Generated Playbook ---\n{playbook_md}"
                )
            else:
                return (
                    f"Recording stopped. {len(data['actions'])} actions captured.\n\n"
                    f"--- Generated Playbook ---\n{playbook_md}"
                )
        except Exception as e:
            return f"Failed to stop recording: {e}"

    @tool
    async def browser_record_status() -> str:
        """Check the current recording status."""
        try:
            session = await _get_session()
            if session.recording:
                return (
                    f"Recording is ACTIVE: '{session.recording_name}'\n"
                    f"Actions captured so far: {len(session.action_log)}"
                )
            else:
                return "No recording is active."
        except Exception as e:
            return f"Failed to check recording status: {e}"

    return [
        browser_open,
        browser_click,
        browser_type,
        browser_screenshot,
        browser_extract_text,
        browser_extract_data,
        browser_wait,
        browser_select,
        browser_scroll,
        browser_navigate,
        browser_close,
        browser_record_start,
        browser_record_stop,
        browser_record_status,
    ]


# ── Playbook generation from recorded actions ──────────────────────────────

# Patterns that suggest a value should be parameterised
_PARAM_PATTERNS = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "password": re.compile(r".*password.*", re.IGNORECASE),
    "url": re.compile(r"^https?://\S+$"),
    "api_key": re.compile(r"^(sk-|pk_|xox[bpsa]-)\S+$"),
}

# Selectors that hint at credential fields
_CREDENTIAL_SELECTORS = re.compile(
    r"(password|passwd|secret|token|api.?key)", re.IGNORECASE
)


def _generate_playbook(data: dict) -> str:
    """Convert a recording's action log into a playbook markdown string."""
    name = data["name"]
    description = data.get("description", "")
    actions = data["actions"]

    parameters: dict[str, dict] = {}
    steps: list[str] = []
    param_counter = 0

    def _maybe_parameterise(value: str, selector: str = "") -> str:
        """Replace likely user-specific values with {{param}} placeholders."""
        nonlocal param_counter

        # Check if selector hints at credential field
        if selector and _CREDENTIAL_SELECTORS.search(selector):
            pname = "password"
            if pname in parameters:
                return "{{" + pname + "}}"
            parameters[pname] = {"required": True, "secret": True}
            return "{{" + pname + "}}"

        # Check value patterns
        for pname_hint, pattern in _PARAM_PATTERNS.items():
            if pattern.match(value):
                if pname_hint == "url" and "login" not in value.lower():
                    continue  # Don't parameterise every URL — only login-like ones
                pname = pname_hint
                suffix = ""
                while pname + suffix in parameters:
                    param_counter += 1
                    suffix = f"_{param_counter}"
                pname = pname + suffix
                parameters[pname] = {
                    "required": True,
                    "secret": pname_hint in ("password", "api_key"),
                }
                return "{{" + pname + "}}"

        return value

    for i, action in enumerate(actions, 1):
        tool_name = action["tool"]
        args = action["args"]

        if tool_name == "browser_open":
            url = args.get("url", "")
            steps.append(f"{i}. Open `{url}`")

        elif tool_name == "browser_click":
            target = args.get("selector") or f"text '{args.get('text', '')}'"
            steps.append(f"{i}. Click `{target}`")

        elif tool_name == "browser_type":
            selector = args.get("selector", "")
            text = args.get("text", "")
            parameterised = _maybe_parameterise(text, selector)
            steps.append(f"{i}. Type `{parameterised}` into `{selector}`")

        elif tool_name == "browser_select":
            selector = args.get("selector", "")
            choice = args.get("label") or args.get("value", "")
            steps.append(f"{i}. Select `{choice}` in `{selector}`")

        elif tool_name == "browser_scroll":
            direction = args.get("direction", "down")
            amount = args.get("amount", 500)
            steps.append(f"{i}. Scroll {direction} by {amount}px")

        elif tool_name == "browser_wait":
            selector = args.get("selector", "")
            state = args.get("state", "visible")
            steps.append(f"{i}. Wait for `{selector}` to be {state}")

        elif tool_name == "browser_navigate":
            steps.append(f"{i}. Navigate {args.get('action', 'back')}")

        elif tool_name == "browser_extract_text":
            selector = args.get("selector", "body")
            steps.append(f"{i}. Extract text from `{selector}`")

        elif tool_name == "browser_extract_data":
            selector = args.get("selector", "")
            steps.append(f"{i}. Extract structured data from `{selector}`")

        elif tool_name == "browser_screenshot":
            steps.append(f"{i}. Take a screenshot")

        else:
            steps.append(f"{i}. {action.get('result_summary', tool_name)}")

    # Build YAML frontmatter
    frontmatter = {
        "name": name,
        "description": description or f"Recorded playbook: {name}",
        "parameters": [
            {
                "name": pname,
                "required": pinfo.get("required", True),
                **({"secret": True} if pinfo.get("secret") else {}),
            }
            for pname, pinfo in parameters.items()
        ],
        "tags": ["recorded"],
    }

    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    steps_str = "\n".join(steps)

    return (
        f"---\n{fm_str}\n---\n\n"
        f"# {name}\n\n"
        f"## Steps\n\n{steps_str}\n\n"
        f"## Error Handling\n\n"
        f"- If an element is not found, wait a few seconds and retry\n"
        f"- If a CAPTCHA or verification prompt appears, stop and ask the user\n"
        f"- If the page layout differs from expected, take a screenshot and describe what you see\n"
    )
