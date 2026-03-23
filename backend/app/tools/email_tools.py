"""LangChain tools for agents to send and read emails via configured SMTP/IMAP accounts."""

import asyncio
import base64
import email as email_lib
import imaplib
import json
import logging
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain_core.tools import tool

from app.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

EMAIL_TOOL_IDS = {"send_email", "read_emails", "draft_email"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Unicode junk characters used by email marketers for padding/tracking
_UNICODE_JUNK_RE = re.compile(r"[\u034f\u200b\u200c\u200d\u2060\ufeff\u00ad]+")
# HTML entities like &amp; &#39; &quot; &lt; &gt;
_HTML_ENTITY_RE = re.compile(r"&(?:#\d+|[a-zA-Z]+);")

_HTML_ENTITY_MAP = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def _clean_snippet(text: str, max_len: int = 200) -> str:
    """Strip tracking junk and HTML entities from email snippets, then truncate."""
    if not text:
        return ""
    # Replace known HTML entities
    for entity, char in _HTML_ENTITY_MAP.items():
        text = text.replace(entity, char)
    # Strip remaining HTML entities
    text = _HTML_ENTITY_RE.sub("", text)
    # Strip Unicode junk characters
    text = _UNICODE_JUNK_RE.sub("", text)
    # Collapse whitespace
    text = " ".join(text.split())
    return text[:max_len]


def _parse_addresses(raw: str) -> list[str]:
    """Split a comma-separated list of email addresses and validate each."""
    addresses = []
    for part in raw.split(","):
        addr = part.strip()
        if addr and _EMAIL_RE.match(addr):
            addresses.append(addr)
    return addresses


def _parse_newer_than(newer_than: str) -> datetime | None:
    """Parse time string (e.g., '8h', '1d', '30m') into a datetime."""
    if not newer_than:
        return None
    match = re.match(r"^(\d+)([hdm])$", newer_than.lower())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    now = datetime.now()
    if unit == "h":
        return now - timedelta(hours=amount)
    elif unit == "d":
        return now - timedelta(days=amount)
    elif unit == "m":
        return now - timedelta(minutes=amount)
    return None


def create_email_tools(agent_id: str):
    """Create email tools bound to a specific agent."""

    @tool
    async def send_email(
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        is_html: bool = False,
    ) -> str:
        """Send an email to one or more recipients.

        IMPORTANT: You may only send to email addresses that have been whitelisted
        for this agent. The tool will reject any un-whitelisted recipient.

        Args:
            to: Recipient email address(es), comma-separated.
            subject: Email subject line.
            body: Email body (plain text or HTML depending on is_html).
            cc: CC address(es), comma-separated (optional).
            is_html: If True the body is rendered as HTML; otherwise plain text.

        Returns JSON with status and message_id on success, or an error message.
        """
        from app.core.vault import decrypt_secret
        from app.models.email import EmailConfig, EmailWhitelist
        from sqlalchemy import select, or_

        to_addresses = _parse_addresses(to)
        cc_addresses = _parse_addresses(cc) if cc else []

        if not to_addresses:
            return json.dumps({"error": "No valid recipient addresses provided."})

        async with async_session_factory() as db:
            # --- Whitelist check ---
            all_recipients = to_addresses + cc_addresses
            for addr in all_recipients:
                row = await db.execute(
                    select(EmailWhitelist).where(
                        EmailWhitelist.email_address == addr,
                        EmailWhitelist.is_active == True,  # noqa: E712
                        or_(
                            EmailWhitelist.agent_id == agent_id,
                            EmailWhitelist.agent_id == None,  # noqa: E711
                        ),
                    )
                )
                if not row.scalars().first():
                    return json.dumps({
                        "error": (
                            f"Recipient '{addr}' is not whitelisted for this agent. "
                            "Ask an administrator to add this address to the email whitelist."
                        )
                    })

            # --- Load email config (agent-specific first, then system default) ---
            result = await db.execute(
                select(EmailConfig).where(EmailConfig.agent_id == agent_id)
            )
            cfg = result.scalars().first()

            if cfg is None:
                result = await db.execute(
                    select(EmailConfig).where(EmailConfig.agent_id == None)  # noqa: E711
                )
                cfg = result.scalars().first()

            if cfg is None:
                return json.dumps({
                    "error": (
                        "No email configuration found. "
                        "Ask an administrator to set up an email config in Settings → Email."
                    )
                })

            if cfg.provider == "GMAIL":
                if not cfg.google_refresh_token:
                    return json.dumps({"error": "Gmail is selected but no refresh token is available. Please reconnect Gmail."})
                refresh_token = decrypt_secret(cfg.google_refresh_token)
            else:
                smtp_password = decrypt_secret(cfg.smtp_password)

        if cfg.provider == "GMAIL":
            # --- Send via Gmail API ---
            def _send_gmail() -> str:
                creds = Credentials(
                    None,  # No access token initially
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                )
                service = build('gmail', 'v1', credentials=creds)
                
                message = MIMEMultipart("alternative")
                message["To"] = ", ".join(to_addresses)
                if cc_addresses:
                    message["Cc"] = ", ".join(cc_addresses)
                message["Subject"] = subject
                
                mime_type = "html" if is_html else "plain"
                message.attach(MIMEText(body, mime_type, "utf-8"))
                
                raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
                send_request = service.users().messages().send(userId="me", body={"raw": raw_message})
                result = send_request.execute()
                return result.get("id", "sent")

            try:
                message_id = await asyncio.get_event_loop().run_in_executor(None, _send_gmail)
                logger.info(f"Agent {agent_id} sent email to {to_addresses} via Gmail API")
                return json.dumps({
                    "status": "sent",
                    "to": to_addresses,
                    "subject": subject,
                    "message_id": message_id,
                })
            except Exception as exc:
                logger.error(f"Agent {agent_id} failed to send email via Gmail API: {exc}")
                return json.dumps({"error": f"Failed to send email via Gmail: {exc}"})
        else:
            # --- Build MIME message ---
            if cc_addresses:
                msg = MIMEMultipart("alternative")
            else:
                msg = MIMEMultipart("alternative")

            msg["Subject"] = subject
            msg["From"] = (
                f"{cfg.smtp_from_name} <{cfg.smtp_from_email}>"
                if cfg.smtp_from_name
                else cfg.smtp_from_email
            )
            msg["To"] = ", ".join(to_addresses)
            if cc_addresses:
                msg["Cc"] = ", ".join(cc_addresses)

            mime_type = "html" if is_html else "plain"
            msg.attach(MIMEText(body, mime_type, "utf-8"))

            all_rcpt = to_addresses + cc_addresses

            # --- Send via SMTP in a thread executor ---
            def _send_smtp() -> str:
                context = ssl.create_default_context()
                if cfg.smtp_use_ssl:
                    with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context) as server:
                        server.login(cfg.smtp_username, smtp_password)
                        server.sendmail(cfg.smtp_from_email, all_rcpt, msg.as_string())
                else:
                    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
                        if cfg.smtp_use_tls:
                            server.starttls(context=context)
                        server.login(cfg.smtp_username, smtp_password)
                        server.sendmail(cfg.smtp_from_email, all_rcpt, msg.as_string())
                return msg.get("Message-ID", "sent")

            try:
                message_id = await asyncio.get_event_loop().run_in_executor(None, _send_smtp)
                logger.info(f"Agent {agent_id} sent email to {to_addresses} via {cfg.smtp_host}")
                return json.dumps({
                    "status": "sent",
                    "to": to_addresses,
                    "subject": subject,
                    "message_id": message_id,
                })
            except Exception as exc:
                logger.error(f"Agent {agent_id} failed to send email: {exc}")
                return json.dumps({"error": f"Failed to send email: {exc}"})

    @tool
    async def read_emails(
        folder: str = "INBOX",
        limit: int = 10,
        unread_only: bool = False,
        newer_than: str = None,
    ) -> str:
        """Read emails from the configured IMAP mailbox.

        Args:
            folder: Mailbox folder to read from (default: INBOX).
            limit: Maximum number of emails to return (max 50).
            unread_only: If True, only return unseen/unread messages.
            newer_than: Only return messages newer than this (e.g., '8h', '1d', '30m').

        Returns a JSON list of email summaries (from, subject, date, snippet).
        Requires IMAP to be configured for this agent.
        """
        from app.core.vault import decrypt_secret
        from app.models.email import EmailConfig
        from sqlalchemy import select

        limit = min(limit, 50)

        async with async_session_factory() as db:
            result = await db.execute(
                select(EmailConfig).where(EmailConfig.agent_id == agent_id)
            )
            cfg = result.scalars().first()

            if cfg is None:
                result = await db.execute(
                    select(EmailConfig).where(EmailConfig.agent_id == None)  # noqa: E711
                )
                cfg = result.scalars().first()

            if cfg is None:
                return json.dumps({
                    "error": "No email configuration found. Set up an email config in Settings → Email."
                })

            if cfg.provider == "GMAIL":
                if not cfg.google_refresh_token:
                    return json.dumps({"error": "Gmail is selected but no refresh token is available. Please reconnect Gmail."})
                refresh_token = decrypt_secret(cfg.google_refresh_token)
            else:
                if not cfg.imap_host:
                    return json.dumps({
                        "error": "No IMAP configuration found. Set up imap_host in the email config."
                    })
                imap_password = decrypt_secret(cfg.imap_password) if cfg.imap_password else ""

        if cfg.provider == "GMAIL":
            def _fetch_gmail() -> list[dict]:
                creds = Credentials(
                    None,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                )
                service = build('gmail', 'v1', credentials=creds)
                
                query_parts = []
                if unread_only:
                    query_parts.append("is:unread")
                if newer_than:
                    query_parts.append(f"newer_than:{newer_than}")
                
                query = " ".join(query_parts)
                results = service.users().messages().list(userId='me', labelIds=[folder], q=query, maxResults=limit).execute()
                messages = results.get('messages', [])
                
                emails = []
                for msg in messages:
                    msg_info = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                    
                    headers = msg_info.get('payload', {}).get('headers', [])
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                    from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                    to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
                    message_id = next((h['value'] for h in headers if h['name'].lower() == 'Message-ID'), msg['id'])
                    
                    snippet = _clean_snippet(msg_info.get('snippet', ''))

                    emails.append({
                        "message_id": message_id,
                        "from": from_email,
                        "to": to_email,
                        "subject": subject,
                        "date": date,
                        "snippet": snippet,
                    })
                return emails

            try:
                messages = await asyncio.get_event_loop().run_in_executor(None, _fetch_gmail)
                logger.info(f"Agent {agent_id} read {len(messages)} emails via Gmail API")
                return json.dumps({"count": len(messages), "emails": messages})
            except Exception as exc:
                logger.error(f"Agent {agent_id} failed to read emails via Gmail API: {exc}")
                return json.dumps({"error": f"Failed to read emails via Gmail: {exc}"})

        else:
            def _fetch_imap() -> list[dict]:
                if cfg.imap_use_ssl:
                    conn = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
                else:
                    conn = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)

                conn.login(cfg.imap_username, imap_password)
                conn.select(folder)

                search_criteria = []
                if unread_only:
                    search_criteria.append("UNSEEN")
                
                if newer_than:
                    since_date = _parse_newer_than(newer_than)
                    if since_date:
                        # IMAP SINCE expects DD-Mon-YYYY
                        imap_date = since_date.strftime("%d-%b-%Y")
                        search_criteria.append(f"SINCE {imap_date}")

                search_query = " ".join(search_criteria) if search_criteria else "ALL"
                _, data = conn.search(None, search_query)

                msg_ids = data[0].split()
                msg_ids = msg_ids[-limit:]  # most recent N

                emails = []
                for mid in reversed(msg_ids):
                    _, msg_data = conn.fetch(mid, "(RFC822)")
                    raw = msg_data[0][1]
                    parsed = email_lib.message_from_bytes(raw)

                    # Extract plain text snippet
                    snippet = ""
                    if parsed.is_multipart():
                        for part in parsed.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    snippet = part.get_payload(decode=True).decode("utf-8", errors="replace")
                                except Exception:
                                    pass
                                break
                    else:
                        try:
                            snippet = parsed.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            pass

                    emails.append({
                        "message_id": parsed.get("Message-ID", ""),
                        "from": parsed.get("From", ""),
                        "to": parsed.get("To", ""),
                        "subject": parsed.get("Subject", ""),
                        "date": parsed.get("Date", ""),
                        "snippet": _clean_snippet(snippet),
                    })

                conn.logout()
                return emails

            try:
                messages = await asyncio.get_event_loop().run_in_executor(None, _fetch_imap)
                logger.info(f"Agent {agent_id} read {len(messages)} emails from {folder}")
                return json.dumps({"count": len(messages), "emails": messages})
            except Exception as exc:
                logger.error(f"Agent {agent_id} failed to read emails: {exc}")
                return json.dumps({"error": f"Failed to read emails: {exc}"})

    @tool
    async def draft_email(
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        is_html: bool = False,
    ) -> str:
        """Create a draft email in the user's Gmail account without sending it.

        Args:
            to: Recipient email address(es), comma-separated.
            subject: Email subject line.
            body: Email body (plain text or HTML depending on is_html).
            cc: CC address(es), comma-separated (optional).
            is_html: If True the body is rendered as HTML; otherwise plain text.

        Returns:
            A JSON string indicating success with the draft ID, or an error message.
        """
        to_addresses = _parse_addresses(to)
        cc_addresses = _parse_addresses(cc) if cc else []

        if not to_addresses:
            return json.dumps({"error": "No valid recipient email addresses provided."})

        async with async_session_factory() as db:
            from app.core.vault import decrypt_secret
            from app.models.email import EmailConfig
            from sqlalchemy import select

            result = await db.execute(select(EmailConfig).where(EmailConfig.agent_id == agent_id))
            cfg = result.scalars().first()
            if not cfg:
                result = await db.execute(select(EmailConfig).where(EmailConfig.agent_id.is_(None)))
                cfg = result.scalars().first()

            if cfg is None:
                return json.dumps({
                    "error": "No email configuration found. Set up an email config in Settings → Email."
                })

            if cfg.provider != "GMAIL":
                return json.dumps({
                    "error": "Drafting emails is currently only supported for the GMAIL provider."
                })

            if not cfg.google_refresh_token:
                return json.dumps({"error": "Gmail is selected but no refresh token is available."})
            refresh_token = decrypt_secret(cfg.google_refresh_token)

        # Build MIME message
        if cc_addresses:
            msg = MIMEMultipart("alternative")
        else:
            msg = MIMEText(body, "html" if is_html else "plain", "utf-8")

        msg["Subject"] = subject
        msg["From"] = cfg.google_email
        msg["To"] = ", ".join(to_addresses)
        if cc_addresses:
            msg["Cc"] = ", ".join(cc_addresses)
        
        if cc_addresses:
            msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))

        def _create_gmail_draft() -> str:
            creds = Credentials(
                None,
                refresh_token=refresh_token,
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                token_uri="https://oauth2.googleapis.com/token",
            )
            service = build("gmail", "v1", credentials=creds)

            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            draft_body = {
                "message": {
                    "raw": raw_message
                }
            }
            draft_request = service.users().drafts().create(userId="me", body=draft_body)
            result = draft_request.execute()
            return result.get("id", "created")

        try:
            draft_id = await asyncio.get_event_loop().run_in_executor(None, _create_gmail_draft)
            logger.info(f"Agent {agent_id} saved email draft to {to_addresses} via Gmail API")
            return json.dumps({
                "status": "draft_created",
                "to": to_addresses,
                "subject": subject,
                "draft_id": draft_id,
            })
        except Exception as exc:
            logger.error(f"Agent {agent_id} failed to save email draft via Gmail API: {exc}")
            return json.dumps({"error": f"Failed to save email draft via Gmail: {exc}"})


    return [send_email, read_emails, draft_email]
