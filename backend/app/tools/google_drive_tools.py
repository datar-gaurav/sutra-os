"""Google Drive integration tools — search, read, upload, and organise files."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from io import BytesIO

from langchain_core.tools import tool

from app.config import settings
from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_TOOL_IDS = {
    "gdrive_search_files",
    "gdrive_read_file",
    "gdrive_save_text",
    "gdrive_upload_file",
    "gdrive_create_document",
    "gdrive_list_folder",
    "gdrive_create_folder",
    "gdrive_move_file",
    "gdrive_ensure_path",
}

# Google Workspace MIME types → export format for reading
_EXPORT_MIME_MAP: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document":     ("text/plain", "text"),
    "application/vnd.google-apps.spreadsheet":  ("text/csv", "csv"),
    "application/vnd.google-apps.presentation": ("text/plain", "text"),
    "application/vnd.google-apps.drawing":      ("image/svg+xml", "svg"),
}

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def _get_drive_credentials(agent_id: str):
    """Fetch and refresh Google Drive OAuth credentials for the given agent."""
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from sqlalchemy import nullslast, select

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "google_drive", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide

    if not row or not row.credentials_enc:
        raise ValueError(
            "No active Google Drive integration found. "
            "Connect Google Drive via Settings → Integrations."
        )

    creds_data = json.loads(decrypt_secret(row.credentials_enc))
    refresh_token = creds_data.get("refresh_token")
    if not refresh_token:
        raise ValueError("Google Drive refresh token missing. Please reconnect.")

    from app.core.env_utils import get_config, get_secret
    client_id = get_config("GOOGLE_CLIENT_ID", settings.google_client_id)
    client_secret = await get_secret("GOOGLE_CLIENT_SECRET", settings.google_client_secret)
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    creds.refresh(Request())
    return creds


async def _build_service(agent_id: str, api: str, version: str):
    """Build a Google API service client for the given agent."""
    from googleapiclient.discovery import build
    creds = await _get_drive_credentials(agent_id)
    return build(api, version, credentials=creds, cache_discovery=False)


def create_google_drive_tools(agent_id: str):

    @tool
    async def gdrive_search_files(query: str, folder_id: str = "", max_results: int = 20) -> str:
        """Search Google Drive files by name or content.

        Args:
            query: Search term — file name, content keywords, or Drive search operators.
            folder_id: Optional folder ID to restrict search scope. Empty = all of Drive.
            max_results: Maximum results to return (default 20, max 100).
        """
        try:
            service = await _build_service(agent_id, "drive", "v3")
            q_parts = [
                f"(fullText contains '{query}' or name contains '{query}')",
                "trashed = false",
            ]
            if folder_id:
                q_parts.append(f"'{folder_id}' in parents")

            resp = service.files().list(
                q=" and ".join(q_parts),
                pageSize=min(max_results, 100),
                fields="files(id, name, mimeType, modifiedTime, size, webViewLink)",
            ).execute()

            files = resp.get("files", [])
            if not files:
                return "No files found matching your query."

            lines = []
            for f in files:
                size = f.get("size", "")
                size_str = f" ({int(size) // 1024}KB)" if size else ""
                type_label = f["mimeType"].split(".")[-1].split("/")[-1]
                lines.append(
                    f"[{type_label}] {f['name']}{size_str}\n"
                    f"  ID: {f['id']} | Modified: {f.get('modifiedTime', 'unknown')}\n"
                    f"  Link: {f.get('webViewLink', 'N/A')}"
                )
            return "\n\n".join(lines)
        except Exception as e:
            logger.error("gdrive_search_files error: %s", e)
            return f"Error searching Google Drive: {e}"

    @tool
    async def gdrive_read_file(file_id: str) -> str:
        """Read the content of a file from Google Drive.

        Google Docs are exported as plain text, Sheets as CSV, Slides as plain text.
        Binary files (images, executables) return metadata and a link only.
        Files larger than 10 MB are refused.

        Args:
            file_id: The Google Drive file ID.
        """
        try:
            service = await _build_service(agent_id, "drive", "v3")

            meta = service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, webViewLink",
            ).execute()

            mime = meta.get("mimeType", "")
            name = meta.get("name", file_id)

            # Google Workspace document — export as text
            if mime in _EXPORT_MIME_MAP:
                export_mime, _ = _EXPORT_MIME_MAP[mime]
                content_bytes = service.files().export_media(
                    fileId=file_id, mimeType=export_mime
                ).execute()
                text = content_bytes.decode("utf-8", errors="replace")
                return f"# {name}\n\n{text[:50000]}"

            # Size guard for binary/text files
            size = int(meta.get("size", 0))
            if size > _MAX_FILE_SIZE:
                return (
                    f"File '{name}' is {size // 1024 // 1024}MB — too large to read directly.\n"
                    f"Link: {meta.get('webViewLink', 'N/A')}"
                )

            # Non-text binary files — return metadata only
            if not mime.startswith("text/"):
                return (
                    f"File '{name}' is a binary file ({mime}) and cannot be read as text.\n"
                    f"ID: {file_id} | Link: {meta.get('webViewLink', 'N/A')}"
                )

            # Plain text file
            from googleapiclient.http import MediaIoBaseDownload
            buf = BytesIO()
            downloader = MediaIoBaseDownload(buf, service.files().get_media(fileId=file_id))
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buf.getvalue().decode("utf-8", errors="replace")[:50000]

        except Exception as e:
            logger.error("gdrive_read_file error: %s", e)
            return f"Error reading file from Google Drive: {e}"

    @tool
    async def gdrive_save_text(filename: str, content: str, folder_id: str = "") -> str:
        """Save a text string directly to Google Drive as a file (no local file needed).

        Use this to save generated content (LaTeX, markdown, plain text, code, etc.)
        directly to Drive without writing a local file first.

        Args:
            filename: Name for the file in Google Drive (e.g. "resume.latex").
            content: The text content to save.
            folder_id: ID of the destination folder. Defaults to My Drive root.
        """
        try:
            from googleapiclient.http import MediaIoBaseUpload
            service = await _build_service(agent_id, "drive", "v3")

            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "text/plain"

            file_metadata: dict = {"name": filename}
            if folder_id:
                file_metadata["parents"] = [folder_id]

            buf = BytesIO(content.encode("utf-8"))
            media = MediaIoBaseUpload(buf, mimetype=mime_type, resumable=False)
            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink",
            ).execute()

            return (
                f"File saved to Google Drive.\n"
                f"Name: {uploaded['name']}\n"
                f"ID: {uploaded['id']}\n"
                f"Link: {uploaded.get('webViewLink', 'N/A')}"
            )
        except Exception as e:
            logger.error("gdrive_save_text error: %s", e)
            return f"Error saving file to Google Drive: {e}"

    @tool
    async def gdrive_upload_file(local_path: str, filename: str = "", folder_id: str = "") -> str:
        """Upload a local file to Google Drive.

        Args:
            local_path: Absolute path to the local file to upload.
            filename: Name for the file in Google Drive. Defaults to the local filename.
            folder_id: ID of the destination folder. Defaults to My Drive root.
        """
        try:
            from googleapiclient.http import MediaFileUpload
            service = await _build_service(agent_id, "drive", "v3")

            if not os.path.exists(local_path):
                return f"File not found: {local_path}"

            display_name = filename or os.path.basename(local_path)
            mime_type, _ = mimetypes.guess_type(local_path)
            mime_type = mime_type or "application/octet-stream"

            file_metadata: dict = {"name": display_name}
            if folder_id:
                file_metadata["parents"] = [folder_id]

            media = MediaFileUpload(local_path, mimetype=mime_type, resumable=False)
            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink",
            ).execute()

            return (
                f"File uploaded successfully.\n"
                f"Name: {uploaded['name']}\n"
                f"ID: {uploaded['id']}\n"
                f"Link: {uploaded.get('webViewLink', 'N/A')}"
            )
        except Exception as e:
            logger.error("gdrive_upload_file error: %s", e)
            return f"Error uploading file to Google Drive: {e}"

    @tool
    async def gdrive_create_document(title: str, content: str = "", folder_id: str = "") -> str:
        """Create a new Google Doc with the given content.

        Args:
            title: Title of the new document.
            content: Text content to insert into the document body.
            folder_id: ID of the folder to place the document in. Defaults to root.
        """
        try:
            creds = await _get_drive_credentials(agent_id)
            from googleapiclient.discovery import build
            drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
            docs_service = build("docs", "v1", credentials=creds, cache_discovery=False)

            # Create blank Google Doc via Drive API (sets parent folder)
            file_metadata: dict = {
                "name": title,
                "mimeType": "application/vnd.google-apps.document",
            }
            if folder_id:
                file_metadata["parents"] = [folder_id]

            doc = drive_service.files().create(
                body=file_metadata, fields="id, webViewLink"
            ).execute()
            doc_id = doc["id"]

            # Insert content via Docs API
            if content:
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {"insertText": {"location": {"index": 1}, "text": content}}
                        ]
                    },
                ).execute()

            return (
                f"Document created successfully.\n"
                f"Title: {title}\n"
                f"ID: {doc_id}\n"
                f"Link: {doc.get('webViewLink', 'N/A')}"
            )
        except Exception as e:
            logger.error("gdrive_create_document error: %s", e)
            return f"Error creating Google Doc: {e}"

    @tool
    async def gdrive_list_folder(folder_id: str = "root", max_results: int = 50) -> str:
        """List files and subfolders in a Google Drive folder.

        Args:
            folder_id: ID of the folder to list. Use 'root' for My Drive root.
            max_results: Maximum items to return (default 50).
        """
        try:
            service = await _build_service(agent_id, "drive", "v3")
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                pageSize=min(max_results, 100),
                fields="files(id, name, mimeType, modifiedTime, size)",
                orderBy="folder,name",
            ).execute()

            files = resp.get("files", [])
            if not files:
                return "Folder is empty."

            lines = []
            for f in files:
                is_folder = f["mimeType"] == "application/vnd.google-apps.folder"
                icon = "📁" if is_folder else "📄"
                size = f.get("size", "")
                size_str = f" ({int(size) // 1024}KB)" if size else ""
                lines.append(f"{icon} {f['name']}{size_str}  (id: {f['id']})")
            return "\n".join(lines)
        except Exception as e:
            logger.error("gdrive_list_folder error: %s", e)
            return f"Error listing folder: {e}"

    @tool
    async def gdrive_create_folder(name: str, parent_folder_id: str = "") -> str:
        """Create a new folder in Google Drive.

        Args:
            name: Name of the new folder.
            parent_folder_id: ID of the parent folder. Defaults to My Drive root.
        """
        try:
            service = await _build_service(agent_id, "drive", "v3")
            file_metadata: dict = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_folder_id:
                file_metadata["parents"] = [parent_folder_id]

            folder = service.files().create(
                body=file_metadata, fields="id, name, webViewLink"
            ).execute()
            return f"Folder created: '{folder['name']}' (id: {folder['id']})"
        except Exception as e:
            logger.error("gdrive_create_folder error: %s", e)
            return f"Error creating folder: {e}"

    @tool
    async def gdrive_move_file(file_id: str, destination_folder_id: str) -> str:
        """Move a file to a different folder in Google Drive.

        Args:
            file_id: ID of the file to move.
            destination_folder_id: ID of the destination folder.
        """
        try:
            service = await _build_service(agent_id, "drive", "v3")
            file_meta = service.files().get(
                fileId=file_id, fields="id, name, parents"
            ).execute()
            previous_parents = ",".join(file_meta.get("parents", []))

            updated = service.files().update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=previous_parents,
                fields="id, name",
            ).execute()
            return f"File '{updated['name']}' moved to folder {destination_folder_id}."
        except Exception as e:
            logger.error("gdrive_move_file error: %s", e)
            return f"Error moving file: {e}"

    @tool
    async def gdrive_ensure_path(path: str, root_folder_id: str = "") -> str:
        """Ensure a nested folder path exists in Google Drive, creating folders as needed.

        Given a path like "Career/Google/Software Engineer", this tool navigates from
        root (or a specified folder) and creates any missing intermediate folders,
        returning the ID of the deepest (leaf) folder.

        Args:
            path: Slash-separated folder path, e.g. "Career/Acme Corp/Senior Engineer".
            root_folder_id: ID of the folder to start from. Defaults to My Drive root.
        """
        try:
            service = await _build_service(agent_id, "drive", "v3")
            parts = [p.strip() for p in path.split("/") if p.strip()]
            if not parts:
                return "Error: path is empty."

            current_parent = root_folder_id or "root"
            created: list[str] = []

            for part in parts:
                # Check if this folder already exists under current_parent
                q = (
                    f"name = '{part.replace(chr(39), chr(39)+chr(39))}' "
                    f"and mimeType = 'application/vnd.google-apps.folder' "
                    f"and '{current_parent}' in parents "
                    f"and trashed = false"
                )
                resp = service.files().list(
                    q=q, pageSize=1, fields="files(id, name)"
                ).execute()
                files = resp.get("files", [])

                if files:
                    current_parent = files[0]["id"]
                else:
                    # Create the missing folder
                    meta: dict = {
                        "name": part,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [current_parent],
                    }
                    folder = service.files().create(
                        body=meta, fields="id, name"
                    ).execute()
                    current_parent = folder["id"]
                    created.append(part)

            summary = f"Path ready: {path}\nLeaf folder ID: {current_parent}"
            if created:
                summary += f"\nCreated new folders: {', '.join(created)}"
            else:
                summary += "\nAll folders already existed."
            return summary

        except Exception as e:
            logger.error("gdrive_ensure_path error: %s", e)
            return f"Error ensuring path in Google Drive: {e}"

    return [
        gdrive_search_files,
        gdrive_read_file,
        gdrive_save_text,
        gdrive_upload_file,
        gdrive_create_document,
        gdrive_list_folder,
        gdrive_create_folder,
        gdrive_move_file,
        gdrive_ensure_path,
    ]
