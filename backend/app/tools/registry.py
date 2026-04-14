from langchain_core.tools import BaseTool

from app.tools.agent_tools import ask_agent_async, control_agent_async, discuss_with_agent_async
from app.tools.data_tools import analyze_data
from app.tools.ollama_tools import manage_ollama_model, pull_ollama_model
from app.tools.os_tools import (
    get_clipboard,
    get_system_info,
    list_directory,
    list_processes,
    open_url,
    read_file,
    run_shell_command,
    search_files,
    send_notification,
    set_clipboard,
    write_file,
)
from app.tools.github_tools import commit_and_push, create_github_issue, create_github_pr
from app.tools.developer_tools import run_gemini_cli
from app.tools.scraper_tools import append_to_google_sheet, scrape_webpage
from app.tools.job_application_tools import update_job_application
from app.core.mcp_manager import mcp_manager
from app.tools.discussion_tools import DISCUSSION_TOOL_IDS, create_discussion_tools
from app.tools.task_tools import TASK_TOOL_IDS, create_task_tools
from app.tools.approval_tools import APPROVAL_TOOL_IDS, create_approval_tools
from app.tools.rag_tools import RAG_TOOL_IDS, create_rag_tools
from app.tools.agent_factory_tools import FACTORY_TOOL_IDS, create_factory_tools
from app.tools.email_tools import EMAIL_TOOL_IDS, create_email_tools
from app.tools.webhook_tools import WEBHOOK_TOOL_IDS, create_webhook_tools
from app.tools.notion_tools import NOTION_TOOL_IDS, create_notion_tools
from app.tools.linear_tools import LINEAR_TOOL_IDS, create_linear_tools
from app.tools.jira_tools import JIRA_TOOL_IDS, create_jira_tools
from app.tools.slack_integration_tools import SLACK_INTEGRATION_TOOL_IDS, create_slack_integration_tools
from app.tools.gitlab_tools import GITLAB_TOOL_IDS, create_gitlab_tools
from app.tools.github_integration_tools import GITHUB_INTEGRATION_TOOL_IDS, create_github_integration_tools
from app.tools.goal_tools import GOAL_TOOL_IDS, create_goal_tools
from app.tools.telegram_tools import TELEGRAM_TOOL_IDS, create_telegram_tools
from app.tools.forge_tools import FORGE_TOOL_IDS, create_forge_tools
from app.tools.google_drive_tools import GOOGLE_DRIVE_TOOL_IDS, create_google_drive_tools
from app.tools.scheduling_tools import SCHEDULING_TOOL_IDS, create_scheduling_tools
from app.tools.evolve_tools import EVOLVE_TOOL_IDS, create_evolve_tools
from app.tools.google_calendar_tools import GCAL_TOOL_IDS, create_google_calendar_tools
from app.tools.workflow_tools import WORKFLOW_TOOL_IDS, create_workflow_tools
from app.tools.browser_tools import BROWSER_TOOL_IDS, create_browser_tools
from app.tools.playbook_tools import PLAYBOOK_TOOL_IDS, create_playbook_tools
from app.tools.extensions import (
    discover_extensions,
    get_all_extension_tool_ids,
    get_extension_registry,
    get_extension_tool_catalog,
)

# Auto-discover extensions at startup
discover_extensions()

# Tool metadata for the UI
TOOL_CATALOG: list[dict] = [
    {
        "id": "ask_agent",
        "name": "Ask Agent",
        "description": "Ask another running agent a question or delegate a task to them.",
        "category": "agent",
        "is_dangerous": False,
    },
    {
        "id": "control_agent",
        "name": "Control Agent",
        "description": "Start or stop an agent by its name.",
        "category": "agent",
        "is_dangerous": False,
    },
    {
        "id": "discuss_with_agent",
        "name": "Discuss With Agent",
        "description": "Have a multi-turn conversation with another agent for collaborative problem-solving, negotiation, or iterative refinement.",
        "category": "agent",
        "is_dangerous": False,
    },
    {
        "id": "analyze_data",
        "name": "Analyze Data",
        "description": "Load an Excel or CSV file into pandas and run Python code over it.",
        "category": "data",
        "is_dangerous": True,
    },
    {
        "id": "read_file",
        "name": "Read File",
        "description": "Read the contents of a file.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "write_file",
        "name": "Write File",
        "description": "Write content to a file.",
        "category": "os",
        "is_dangerous": True,
    },
    {
        "id": "manage_ollama_model",
        "name": "Manage Ollama Model",
        "description": "Load or unload a model in Ollama to manage memory.",
        "category": "agent",
        "is_dangerous": False,
    },
    {
        "id": "pull_ollama_model",
        "name": "Pull Ollama Model",
        "description": "Download a model into Ollama from the registry.",
        "category": "agent",
        "is_dangerous": False,
    },
    {
        "id": "list_directory",
        "name": "List Directory",
        "description": "List files and directories at a path.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "search_files",
        "name": "Search Files",
        "description": "Search for files matching a pattern.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "run_shell_command",
        "name": "Run Shell Command",
        "description": "Execute a shell command.",
        "category": "os",
        "is_dangerous": True,
    },
    {
        "id": "get_system_info",
        "name": "System Info",
        "description": "Get CPU, memory, disk, and OS information.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "list_processes",
        "name": "List Processes",
        "description": "List top running processes by CPU or memory.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "open_url",
        "name": "Open URL",
        "description": "Open a URL in the default browser.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "send_notification",
        "name": "Send Notification",
        "description": "Send a macOS notification.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "get_clipboard",
        "name": "Get Clipboard",
        "description": "Read clipboard contents.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "set_clipboard",
        "name": "Set Clipboard",
        "description": "Copy text to clipboard.",
        "category": "os",
        "is_dangerous": False,
    },
    {
        "id": "create_github_issue",
        "name": "Create GitHub Issue",
        "description": "Create a new issue on GitHub.",
        "category": "developer",
        "is_dangerous": False,
    },
    {
        "id": "create_github_pr",
        "name": "Create GitHub PR",
        "description": "Create a new pull request on GitHub.",
        "category": "developer",
        "is_dangerous": False,
    },
    {
        "id": "commit_and_push",
        "name": "Commit and Push",
        "description": "Commit changes locally and push to a new branch.",
        "category": "developer",
        "is_dangerous": True,
    },
    {
        "id": "run_gemini_cli",
        "name": "Run Gemini CLI",
        "description": "Run the developer CLI to autonomously code features.",
        "category": "developer",
        "is_dangerous": True,
    },
    {
        "id": "scrape_webpage",
        "name": "Scrape Webpage",
        "description": "Scrape visible text and links from a webpage (supports JavaScript).",
        "category": "data",
        "is_dangerous": False,
    },
    {
        "id": "append_to_google_sheet",
        "name": "Append to Google Sheet",
        "description": "Append scraped data rows to a Google Sheet.",
        "category": "data",
        "is_dangerous": True,
    },
    {
        "id": "save_memory",
        "name": "Save Memory",
        "description": "Save important information to long-term memory for future conversations. Supports core/recall/archival tiers.",
        "category": "memory",
        "is_dangerous": False,
    },
    {
        "id": "search_memory",
        "name": "Search Memory",
        "description": "Search long-term memory for relevant information across all tiers.",
        "category": "memory",
        "is_dangerous": False,
    },
    {
        "id": "memory_update",
        "name": "Update Memory",
        "description": "Rewrite the content of an existing memory when information has changed.",
        "category": "memory",
        "is_dangerous": False,
    },
    {
        "id": "memory_forget",
        "name": "Forget Memory",
        "description": "Soft-delete a memory that is no longer accurate or relevant, with a reason.",
        "category": "memory",
        "is_dangerous": False,
    },
    {
        "id": "memory_promote",
        "name": "Promote/Demote Memory",
        "description": "Move a memory between tiers: core (always in context), recall (searchable), or archival (long-term).",
        "category": "memory",
        "is_dangerous": False,
    },
    {
        "id": "create_task",
        "name": "Create Task",
        "description": "Create a new task with title, description, priority, and optional project/agent assignment.",
        "category": "tasks",
        "is_dangerous": False,
    },
    {
        "id": "list_tasks",
        "name": "List Tasks",
        "description": "List tasks, optionally filtered by project, status, or assignee agent.",
        "category": "tasks",
        "is_dangerous": False,
    },
    {
        "id": "update_task",
        "name": "Update Task",
        "description": "Update a task's status, priority, assignee, or notes by task ID.",
        "category": "tasks",
        "is_dangerous": False,
    },
    {
        "id": "get_task",
        "name": "Get Task",
        "description": "Retrieve full details of a specific task by its ID.",
        "category": "tasks",
        "is_dangerous": False,
    },
    {
        "id": "decompose_task",
        "name": "Decompose Task",
        "description": "Break a task into subtasks by providing a structured JSON list of sub-items with titles, descriptions, and priorities.",
        "category": "tasks",
        "is_dangerous": False,
    },
    {
        "id": "start_discussion",
        "name": "Start Discussion",
        "description": "Start a multi-agent group discussion (brainstorm, debate, review, standup, or retrospective).",
        "category": "collaboration",
        "is_dangerous": False,
    },
    {
        "id": "request_approval",
        "name": "Request Human Approval",
        "description": "Pause and request human sign-off before executing a high-stakes action (financial, external, destructive, or strategic).",
        "category": "safety",
        "is_dangerous": False,
    },
    {
        "id": "search_knowledge_base",
        "name": "Search Knowledge Base",
        "description": "Search the organization's knowledge bases (documents, PDFs, web pages) for relevant information using semantic search.",
        "category": "knowledge",
        "is_dangerous": False,
    },
    {
        "id": "ingest_url_to_kb",
        "name": "Ingest URL to Knowledge Base",
        "description": "Fetch a web page and add it to a knowledge base so it can be retrieved in future searches.",
        "category": "knowledge",
        "is_dangerous": False,
    },
    {
        "id": "create_agent_from_template",
        "name": "Create Agent from Template",
        "description": "Create a new agent from a named template. Specify the template name, a unique agent name, and optional custom instructions.",
        "category": "factory",
        "is_dangerous": False,
    },
    {
        "id": "list_agent_templates",
        "name": "List Agent Templates",
        "description": "List all available agent templates, optionally filtered by category.",
        "category": "factory",
        "is_dangerous": False,
    },
    {
        "id": "archive_agent",
        "name": "Archive Agent",
        "description": "Retire (archive) an agent by ID. Stops it, marks it archived, and preserves its history.",
        "category": "factory",
        "is_dangerous": True,
    },
    {
        "id": "send_email",
        "name": "Send Email",
        "description": "Send an email to one or more recipients. Only whitelisted addresses are allowed.",
        "category": "communication",
        "is_dangerous": True,
    },
    {
        "id": "read_emails",
        "name": "Read Emails",
        "description": "Read emails from the configured IMAP mailbox (inbox or specified folder).",
        "category": "communication",
        "is_dangerous": False,
    },
    {
        "id": "draft_email",
        "name": "Draft Email",
        "description": "Create a draft email in the user's Gmail account without sending it.",
        "category": "communication",
        "is_dangerous": False,
    },
    {
        "id": "call_webhook",
        "name": "Call Webhook",
        "description": "Send an HTTP POST/PUT to an external URL — Zapier, Make, n8n, Slack webhooks, or any REST API.",
        "category": "communication",
        "is_dangerous": True,
    },
    {
        "id": "send_telegram_message",
        "name": "Send Telegram Message",
        "description": "Proactively send a message (summary, alert, update) to a Telegram chat or user without waiting for them to initiate a conversation.",
        "category": "communication",
        "is_dangerous": False,
    },
    # ── Notion ──────────────────────────────────────────────────────────────────
    {
        "id": "notion_search",
        "name": "Notion Search",
        "description": "Search pages and databases in the Notion workspace.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "notion_get_page",
        "name": "Notion Get Page",
        "description": "Retrieve the content of a Notion page by ID.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "notion_create_page",
        "name": "Notion Create Page",
        "description": "Create a new page in Notion under a parent page or database.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "notion_query_database",
        "name": "Notion Query Database",
        "description": "Query a Notion database with an optional filter and return matching rows.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Linear ──────────────────────────────────────────────────────────────────
    {
        "id": "linear_create_issue",
        "name": "Linear Create Issue",
        "description": "Create a new issue in Linear with title, description, and priority.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "linear_list_issues",
        "name": "Linear List Issues",
        "description": "List Linear issues filtered by team and status.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "linear_update_issue",
        "name": "Linear Update Issue",
        "description": "Update the status, title, or priority of a Linear issue.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Jira ────────────────────────────────────────────────────────────────────
    {
        "id": "jira_create_issue",
        "name": "Jira Create Issue",
        "description": "Create a new Jira issue in a project.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "jira_search_issues",
        "name": "Jira Search Issues",
        "description": "Search Jira issues using JQL query language.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "jira_update_issue",
        "name": "Jira Update Issue",
        "description": "Update a Jira issue: change status, summary, or add a comment.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Slack ───────────────────────────────────────────────────────────────────
    {
        "id": "slack_post_message",
        "name": "Slack Post Message",
        "description": "Post a message to a Slack channel using the integration credentials.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "slack_list_channels",
        "name": "Slack List Channels",
        "description": "List available Slack channels.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── GitLab ──────────────────────────────────────────────────────────────────
    {
        "id": "gitlab_create_issue",
        "name": "GitLab Create Issue",
        "description": "Create a new issue in a GitLab project.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gitlab_list_issues",
        "name": "GitLab List Issues",
        "description": "List issues in a GitLab project filtered by state.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gitlab_create_mr",
        "name": "GitLab Create Merge Request",
        "description": "Create a GitLab Merge Request from a source branch to a target branch.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── GitHub (extended) ───────────────────────────────────────────────────────
    {
        "id": "github_list_issues",
        "name": "GitHub List Issues",
        "description": "List GitHub issues for a repository filtered by state and labels.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "github_get_file",
        "name": "GitHub Get File",
        "description": "Retrieve the contents of a file from a GitHub repository.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "github_search_code",
        "name": "GitHub Search Code",
        "description": "Search code across a GitHub repository using GitHub's code search syntax.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Google Drive ────────────────────────────────────────────────────────────
    {
        "id": "gdrive_search_files",
        "name": "Google Drive: Search Files",
        "description": "Search Google Drive files by name or content keywords.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_read_file",
        "name": "Google Drive: Read File",
        "description": "Read the content of a Google Drive file. Google Docs/Sheets/Slides are exported as text/CSV.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_save_text",
        "name": "Google Drive: Save Text",
        "description": "Save generated text content (LaTeX, markdown, code, etc.) directly to Google Drive without needing a local file.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_upload_file",
        "name": "Google Drive: Upload File",
        "description": "Upload a local file to Google Drive.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_create_document",
        "name": "Google Drive: Create Document",
        "description": "Create a new Google Doc with a given title and text content.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_list_folder",
        "name": "Google Drive: List Folder",
        "description": "List files and subfolders inside a Google Drive folder.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_create_folder",
        "name": "Google Drive: Create Folder",
        "description": "Create a new folder in Google Drive.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_move_file",
        "name": "Google Drive: Move File",
        "description": "Move a file to a different folder in Google Drive.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gdrive_ensure_path",
        "name": "Google Drive: Ensure Path",
        "description": "Ensure a nested folder path exists (e.g. 'Career/Google/SWE'), creating any missing folders, and return the leaf folder ID.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Google Calendar ─────────────────────────────────────────────────────────
    {
        "id": "gcal_list_events",
        "name": "Google Calendar: List Events",
        "description": "List upcoming events from the user's primary Google Calendar.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gcal_create_event",
        "name": "Google Calendar: Create Event",
        "description": "Create a new event in Google Calendar, supporting descriptions, locations, and recurrence rules.",
        "category": "integrations",
        "is_dangerous": False,
    },
    {
        "id": "gcal_delete_event",
        "name": "Google Calendar: Delete Event",
        "description": "Delete a Google Calendar event by its ID.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Forge ────────────────────────────────────────────────────────────────────
    {
        "id": "forge_start",
        "name": "Forge: Start",
        "description": "Clone a GitHub repo and generate an implementation plan using any LLM provider/model.",
        "category": "forge",
        "is_dangerous": True,
    },
    {
        "id": "forge_generate_plan",
        "name": "Forge: Generate Plan",
        "description": "Revise the implementation plan, optionally incorporating user feedback.",
        "category": "forge",
        "is_dangerous": False,
    },
    {
        "id": "forge_execute_plan",
        "name": "Forge: Execute Plan",
        "description": "Run the coding agent to implement the approved plan, then run tests.",
        "category": "forge",
        "is_dangerous": True,
    },
    {
        "id": "forge_create_pr",
        "name": "Forge: Create PR",
        "description": "Commit all changes, push the branch, and open a GitHub pull request with test results.",
        "category": "forge",
        "is_dangerous": True,
    },
    {
        "id": "forge_cancel",
        "name": "Forge: Cancel",
        "description": "Cancel a forge request and clean up its workspace.",
        "category": "forge",
        "is_dangerous": False,
    },
    # ── Workflows ───────────────────────────────────────────────────────────────
    {
        "id": "create_workflow",
        "name": "Create Workflow",
        "description": "Create a new multi-agent workflow from a Markdown definition. Supports agent, conditional, parallel, loop, approval_gate, and sub_workflow nodes.",
        "category": "workflows",
        "is_dangerous": False,
    },
    {
        "id": "list_workflows",
        "name": "List Workflows",
        "description": "List all workflows with their schedule, status, and last run info.",
        "category": "workflows",
        "is_dangerous": False,
    },
    {
        "id": "execute_workflow",
        "name": "Execute Workflow",
        "description": "Trigger a workflow to run by its ID, with an optional initial input string.",
        "category": "workflows",
        "is_dangerous": False,
    },
    {
        "id": "get_workflow_details",
        "name": "Get Workflow Details",
        "description": "Get the full node/edge structure, schedule, and last execution logs for a workflow.",
        "category": "workflows",
        "is_dangerous": False,
    },
    # ── Self-Scheduling ────────────────────────────────────────────────────────
    {
        "id": "schedule_self",
        "name": "Schedule Self",
        "description": "Create a cron-based trigger that will invoke this agent on a recurring schedule. Enables autonomous check-ins and monitoring.",
        "category": "autonomy",
        "is_dangerous": False,
    },
    {
        "id": "list_my_triggers",
        "name": "List My Triggers",
        "description": "List all triggers configured for this agent, including cron schedules and fire counts.",
        "category": "autonomy",
        "is_dangerous": False,
    },
    {
        "id": "cancel_trigger",
        "name": "Cancel Trigger",
        "description": "Deactivate one of this agent's triggers so it no longer fires.",
        "category": "autonomy",
        "is_dangerous": False,
    },
    # ── Goals ───────────────────────────────────────────────────────────────────
    {
        "id": "get_my_goals",
        "name": "Get My Goals",
        "description": "List your currently assigned goals with progress, deadlines, and success criteria.",
        "category": "goals",
        "is_dangerous": False,
    },
    {
        "id": "update_goal_progress",
        "name": "Update Goal Progress",
        "description": "Report progress on a goal. Call this whenever you make meaningful progress toward an objective.",
        "category": "goals",
        "is_dangerous": False,
    },
    {
        "id": "request_goal_completion",
        "name": "Request Goal Completion",
        "description": "Request human approval to mark a goal as completed, providing evidence of success criteria met.",
        "category": "goals",
        "is_dangerous": False,
    },
    # ── Evolve ──────────────────────────────────────────────────────────────
    {
        "id": "evolve_get_platform_stats",
        "name": "Evolve: Platform Stats",
        "description": "Get platform health statistics: agent count, invocation count, error rate, avg latency, token usage.",
        "category": "evolve",
        "is_dangerous": False,
    },
    {
        "id": "evolve_get_error_patterns",
        "name": "Evolve: Error Patterns",
        "description": "Get top error patterns from execution traces grouped by agent, with sample error messages.",
        "category": "evolve",
        "is_dangerous": False,
    },
    {
        "id": "evolve_submit_suggestion",
        "name": "Evolve: Submit Suggestion",
        "description": "Submit an improvement suggestion for the platform. Creates a suggestion and approval request for human review.",
        "category": "evolve",
        "is_dangerous": False,
    },
    # ── Browser Automation ─────────────────────────────────────────────────
    {
        "id": "browser_open",
        "name": "Browser: Open URL",
        "description": "Open a URL in a persistent browser session. Returns page title, URL, and interactive elements.",
        "category": "browser",
        "is_dangerous": True,
    },
    {
        "id": "browser_click",
        "name": "Browser: Click",
        "description": "Click an element by CSS selector or visible text.",
        "category": "browser",
        "is_dangerous": True,
    },
    {
        "id": "browser_type",
        "name": "Browser: Type",
        "description": "Type text into an input field identified by CSS selector.",
        "category": "browser",
        "is_dangerous": True,
    },
    {
        "id": "browser_screenshot",
        "name": "Browser: Screenshot",
        "description": "Take a screenshot and return a text description of the visible page via accessibility tree.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_extract_text",
        "name": "Browser: Extract Text",
        "description": "Extract visible text content from an element on the page.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_extract_data",
        "name": "Browser: Extract Data",
        "description": "Extract structured data (text + attributes) from multiple matching elements as JSON.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_wait",
        "name": "Browser: Wait",
        "description": "Wait for an element to reach a specific state (visible, hidden, attached, detached).",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_select",
        "name": "Browser: Select",
        "description": "Select an option from a dropdown by value or label.",
        "category": "browser",
        "is_dangerous": True,
    },
    {
        "id": "browser_scroll",
        "name": "Browser: Scroll",
        "description": "Scroll the page or a specific element up or down.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_navigate",
        "name": "Browser: Navigate",
        "description": "Navigate back or forward in browser history.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_close",
        "name": "Browser: Close",
        "description": "Close the current browser session and free resources.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_record_start",
        "name": "Browser: Start Recording",
        "description": "Start recording browser actions to auto-generate a reusable playbook.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_record_stop",
        "name": "Browser: Stop Recording",
        "description": "Stop recording and save captured actions as a playbook .md file with auto-detected parameters.",
        "category": "browser",
        "is_dangerous": False,
    },
    {
        "id": "browser_record_status",
        "name": "Browser: Recording Status",
        "description": "Check if recording is active and how many actions have been captured.",
        "category": "browser",
        "is_dangerous": False,
    },
    # ── Job Applications ───────────────────────────────────────────────────
    {
        "id": "update_job_application",
        "name": "Update Job Application",
        "description": "Patch a job_application row with resume Drive URL, fit score, status, or notes. Used by the Resume Builder after tailoring.",
        "category": "integrations",
        "is_dangerous": False,
    },
    # ── Playbook Tools ─────────────────────────────────────────────────────
    {
        "id": "list_playbooks",
        "name": "Playbook: List",
        "description": "List available browser automation playbooks with their parameters and tags.",
        "category": "automation",
        "is_dangerous": False,
    },
    {
        "id": "load_playbook",
        "name": "Playbook: Load",
        "description": "Load a playbook by name, substitute parameters, and return step-by-step browser instructions.",
        "category": "automation",
        "is_dangerous": False,
    },
]

# Map tool ID → LangChain tool instance
_TOOL_MAP: dict[str, BaseTool] = {
    "ask_agent": ask_agent_async,
    "analyze_data": analyze_data,
    "control_agent": control_agent_async,
    "discuss_with_agent": discuss_with_agent_async,
    "manage_ollama_model": manage_ollama_model,
    "pull_ollama_model": pull_ollama_model,
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "search_files": search_files,
    "run_shell_command": run_shell_command,
    "get_system_info": get_system_info,
    "list_processes": list_processes,
    "open_url": open_url,
    "send_notification": send_notification,
    "get_clipboard": get_clipboard,
    "set_clipboard": set_clipboard,
    "create_github_issue": create_github_issue,
    "create_github_pr": create_github_pr,
    "commit_and_push": commit_and_push,
    "run_gemini_cli": run_gemini_cli,
    "scrape_webpage": scrape_webpage,
    "append_to_google_sheet": append_to_google_sheet,
    "list_playbooks": create_playbook_tools()[0],
    "load_playbook": create_playbook_tools()[1],
    "update_job_application": update_job_application,
}


MEMORY_TOOL_IDS = {"save_memory", "search_memory", "memory_update", "memory_forget", "memory_promote"}


def get_tools_by_ids(tool_ids: list[str], agent_id: str | None = None) -> list[BaseTool]:
    """Get LangChain tool instances by their IDs.

    Memory and task tools require agent_id and are created as closures
    bound to the specific agent.
    """
    tools = []
    needs_memory_tools = any(tid in MEMORY_TOOL_IDS for tid in tool_ids)
    needs_task_tools = any(tid in TASK_TOOL_IDS for tid in tool_ids)

    if needs_memory_tools and agent_id:
        from app.tools.memory_tools import create_memory_tools
        tools.extend(create_memory_tools(agent_id))

    if needs_task_tools and agent_id:
        task_tools_map = {t.name: t for t in create_task_tools(agent_id)}
        for tid in tool_ids:
            if tid in TASK_TOOL_IDS and tid in task_tools_map:
                tools.append(task_tools_map[tid])

    needs_discussion_tools = any(tid in DISCUSSION_TOOL_IDS for tid in tool_ids)
    if needs_discussion_tools and agent_id:
        disc_tools_map = {t.name: t for t in create_discussion_tools(agent_id)}
        for tid in tool_ids:
            if tid in DISCUSSION_TOOL_IDS and tid in disc_tools_map:
                tools.append(disc_tools_map[tid])

    needs_approval_tools = any(tid in APPROVAL_TOOL_IDS for tid in tool_ids)
    if needs_approval_tools and agent_id:
        approval_tools_map = {t.name: t for t in create_approval_tools(agent_id)}
        for tid in tool_ids:
            if tid in APPROVAL_TOOL_IDS and tid in approval_tools_map:
                tools.append(approval_tools_map[tid])

    needs_rag_tools = any(tid in RAG_TOOL_IDS for tid in tool_ids)
    if needs_rag_tools:
        rag_tools_map = {t.name: t for t in create_rag_tools(agent_id or "")}
        for tid in tool_ids:
            if tid in RAG_TOOL_IDS and tid in rag_tools_map:
                tools.append(rag_tools_map[tid])

    needs_factory_tools = any(tid in FACTORY_TOOL_IDS for tid in tool_ids)
    if needs_factory_tools and agent_id:
        factory_tools_map = {t.name: t for t in create_factory_tools(agent_id)}
        for tid in tool_ids:
            if tid in FACTORY_TOOL_IDS and tid in factory_tools_map:
                tools.append(factory_tools_map[tid])

    needs_email_tools = any(tid in EMAIL_TOOL_IDS for tid in tool_ids)
    if needs_email_tools and agent_id:
        email_tools_map = {t.name: t for t in create_email_tools(agent_id)}
        for tid in tool_ids:
            if tid in EMAIL_TOOL_IDS and tid in email_tools_map:
                tools.append(email_tools_map[tid])

    needs_webhook_tools = any(tid in WEBHOOK_TOOL_IDS for tid in tool_ids)
    if needs_webhook_tools and agent_id:
        webhook_tools_map = {t.name: t for t in create_webhook_tools(agent_id)}
        for tid in tool_ids:
            if tid in WEBHOOK_TOOL_IDS and tid in webhook_tools_map:
                tools.append(webhook_tools_map[tid])

    needs_notion_tools = any(tid in NOTION_TOOL_IDS for tid in tool_ids)
    if needs_notion_tools and agent_id:
        notion_tools_map = {t.name: t for t in create_notion_tools(agent_id)}
        for tid in tool_ids:
            if tid in NOTION_TOOL_IDS and tid in notion_tools_map:
                tools.append(notion_tools_map[tid])

    needs_linear_tools = any(tid in LINEAR_TOOL_IDS for tid in tool_ids)
    if needs_linear_tools and agent_id:
        linear_tools_map = {t.name: t for t in create_linear_tools(agent_id)}
        for tid in tool_ids:
            if tid in LINEAR_TOOL_IDS and tid in linear_tools_map:
                tools.append(linear_tools_map[tid])

    needs_jira_tools = any(tid in JIRA_TOOL_IDS for tid in tool_ids)
    if needs_jira_tools and agent_id:
        jira_tools_map = {t.name: t for t in create_jira_tools(agent_id)}
        for tid in tool_ids:
            if tid in JIRA_TOOL_IDS and tid in jira_tools_map:
                tools.append(jira_tools_map[tid])

    needs_slack_int_tools = any(tid in SLACK_INTEGRATION_TOOL_IDS for tid in tool_ids)
    if needs_slack_int_tools and agent_id:
        slack_int_tools_map = {t.name: t for t in create_slack_integration_tools(agent_id)}
        for tid in tool_ids:
            if tid in SLACK_INTEGRATION_TOOL_IDS and tid in slack_int_tools_map:
                tools.append(slack_int_tools_map[tid])

    needs_gitlab_tools = any(tid in GITLAB_TOOL_IDS for tid in tool_ids)
    if needs_gitlab_tools and agent_id:
        gitlab_tools_map = {t.name: t for t in create_gitlab_tools(agent_id)}
        for tid in tool_ids:
            if tid in GITLAB_TOOL_IDS and tid in gitlab_tools_map:
                tools.append(gitlab_tools_map[tid])

    needs_github_int_tools = any(tid in GITHUB_INTEGRATION_TOOL_IDS for tid in tool_ids)
    if needs_github_int_tools and agent_id:
        github_int_tools_map = {t.name: t for t in create_github_integration_tools(agent_id)}
        for tid in tool_ids:
            if tid in GITHUB_INTEGRATION_TOOL_IDS and tid in github_int_tools_map:
                tools.append(github_int_tools_map[tid])

    needs_goal_tools = any(tid in GOAL_TOOL_IDS for tid in tool_ids)
    if needs_goal_tools and agent_id:
        goal_tools_map = {t.name: t for t in create_goal_tools(agent_id)}
        for tid in tool_ids:
            if tid in GOAL_TOOL_IDS and tid in goal_tools_map:
                tools.append(goal_tools_map[tid])

    needs_telegram_tools = any(tid in TELEGRAM_TOOL_IDS for tid in tool_ids)
    if needs_telegram_tools:
        telegram_tools_map = {t.name: t for t in create_telegram_tools()}
        for tid in tool_ids:
            if tid in TELEGRAM_TOOL_IDS and tid in telegram_tools_map:
                tools.append(telegram_tools_map[tid])

    needs_forge_tools = any(tid in FORGE_TOOL_IDS for tid in tool_ids)
    if needs_forge_tools and agent_id:
        forge_tools_map = {t.name: t for t in create_forge_tools()}
        for tid in tool_ids:
            if tid in FORGE_TOOL_IDS and tid in forge_tools_map:
                tools.append(forge_tools_map[tid])

    needs_google_drive_tools = any(tid in GOOGLE_DRIVE_TOOL_IDS for tid in tool_ids)
    if needs_google_drive_tools and agent_id:
        gdrive_tools_map = {t.name: t for t in create_google_drive_tools(agent_id)}
        for tid in tool_ids:
            if tid in GOOGLE_DRIVE_TOOL_IDS and tid in gdrive_tools_map:
                tools.append(gdrive_tools_map[tid])

    needs_google_calendar_tools = any(tid in GCAL_TOOL_IDS for tid in tool_ids)
    if needs_google_calendar_tools and agent_id:
        gcal_tools_map = {t.name: t for t in create_google_calendar_tools(agent_id)}
        for tid in tool_ids:
            if tid in GCAL_TOOL_IDS and tid in gcal_tools_map:
                tools.append(gcal_tools_map[tid])

    needs_workflow_tools = any(tid in WORKFLOW_TOOL_IDS for tid in tool_ids)
    if needs_workflow_tools:
        wf_tools_map = {t.name: t for t in create_workflow_tools()}
        for tid in tool_ids:
            if tid in WORKFLOW_TOOL_IDS and tid in wf_tools_map:
                tools.append(wf_tools_map[tid])

    needs_scheduling_tools = any(tid in SCHEDULING_TOOL_IDS for tid in tool_ids)
    if needs_scheduling_tools and agent_id:
        sched_tools_map = {t.name: t for t in create_scheduling_tools(agent_id)}
        for tid in tool_ids:
            if tid in SCHEDULING_TOOL_IDS and tid in sched_tools_map:
                tools.append(sched_tools_map[tid])

    needs_evolve_tools = any(tid in EVOLVE_TOOL_IDS for tid in tool_ids)
    if needs_evolve_tools:
        evolve_tools_map = {t.name: t for t in create_evolve_tools()}
        for tid in tool_ids:
            if tid in EVOLVE_TOOL_IDS and tid in evolve_tools_map:
                tools.append(evolve_tools_map[tid])

    needs_browser_tools = any(tid in BROWSER_TOOL_IDS for tid in tool_ids)
    if needs_browser_tools and agent_id:
        browser_tools_map = {t.name: t for t in create_browser_tools(agent_id)}
        for tid in tool_ids:
            if tid in BROWSER_TOOL_IDS and tid in browser_tools_map:
                tools.append(browser_tools_map[tid])

    # ── Extension tools ────────────────────────────────────────────────────────
    for _ext_id, _ext_info in get_extension_registry().items():
        _needs_ext = any(tid in _ext_info.tool_ids for tid in tool_ids)
        if _needs_ext and agent_id:
            _ext_tools_map = {t.name: t for t in _ext_info.create_tools(agent_id)}
            for tid in tool_ids:
                if tid in _ext_info.tool_ids and tid in _ext_tools_map:
                    tools.append(_ext_tools_map[tid])

    _ALL_FACTORY_IDS = (
        MEMORY_TOOL_IDS | TASK_TOOL_IDS | DISCUSSION_TOOL_IDS | APPROVAL_TOOL_IDS
        | RAG_TOOL_IDS | FACTORY_TOOL_IDS | EMAIL_TOOL_IDS | WEBHOOK_TOOL_IDS
        | NOTION_TOOL_IDS | LINEAR_TOOL_IDS | JIRA_TOOL_IDS | SLACK_INTEGRATION_TOOL_IDS
        | GITLAB_TOOL_IDS | GITHUB_INTEGRATION_TOOL_IDS
        | GOAL_TOOL_IDS | TELEGRAM_TOOL_IDS | FORGE_TOOL_IDS | GOOGLE_DRIVE_TOOL_IDS
        | GCAL_TOOL_IDS | WORKFLOW_TOOL_IDS | SCHEDULING_TOOL_IDS | EVOLVE_TOOL_IDS
        | BROWSER_TOOL_IDS
        | get_all_extension_tool_ids()
    )

    for tid in tool_ids:
        if tid in _ALL_FACTORY_IDS:
            continue  # already handled above
        if tid in _TOOL_MAP:
            tools.append(_TOOL_MAP[tid])
        elif tid.startswith("mcp__"):
            mcp_tool = mcp_manager.get_langchain_tool(tid)
            if mcp_tool:
                tools.append(mcp_tool)
    return tools


def get_all_tools() -> list[BaseTool]:
    """Get all available LangChain tools."""
    return list(_TOOL_MAP.values())


def get_tool_catalog() -> list[dict]:
    """Get the full tool catalog with metadata for the UI."""
    return TOOL_CATALOG + mcp_manager.get_all_mcp_tools_metadata() + get_extension_tool_catalog()
