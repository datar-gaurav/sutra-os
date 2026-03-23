"""OS-native tools for AI agents — file system, shell, system info, and more."""

import os
import platform
import subprocess
from datetime import datetime

import psutil
from langchain_core.tools import tool

from app.config import settings


def _is_path_allowed(target_path: str) -> bool:
    """Check if the given absolute path is within the allowed directories."""
    allowed_str = settings.allowed_agent_file_paths.strip()
    if not allowed_str:
        return True  # If no whitelist is configured, allow all
        
    resolved_target = os.path.abspath(os.path.expanduser(target_path))
    
    # Check if the target is exactly an allowed path or a child of it
    for allowed_path in [p.strip() for p in allowed_str.split(",") if p.strip()]:
        resolved_allowed = os.path.abspath(os.path.expanduser(allowed_path))
        
        # Check if the target path starts with the allowed path
        # os.path.commonpath ensures we don't accidentally match prefixes (e.g. /data and /data2)
        try:
            if os.path.commonpath([resolved_target, resolved_allowed]) == resolved_allowed:
                return True
        except ValueError:
             # ValueError occurs if paths are on different drives on Windows
             pass
             
    return False


# ─── File System Tools ────────────────────────────────────────────────────────

@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file at the given path.

    Args:
        file_path: Absolute path to the file to read.
    """
    try:
        path = os.path.expanduser(file_path)
        if not _is_path_allowed(path):
            return f"Access Denied: The path '{file_path}' is outside the allowed directories."
            
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        file_path: Absolute path to the file to write.
        content: Content to write to the file.
    """
    try:
        path = os.path.expanduser(file_path)
        if not _is_path_allowed(path):
            return f"Access Denied: The path '{file_path}' is outside the allowed directories."
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def list_directory(directory_path: str) -> str:
    """List all files and directories at the given path.

    Args:
        directory_path: Absolute path to the directory to list.
    """
    try:
        path = os.path.expanduser(directory_path)
        if not _is_path_allowed(path):
            return f"Access Denied: The path '{directory_path}' is outside the allowed directories."
            
        entries = []
        for entry in sorted(os.listdir(path)):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                entries.append(f"📁 {entry}/")
            else:
                size = os.path.getsize(full_path)
                entries.append(f"📄 {entry} ({_format_size(size)})")
        return "\n".join(entries) if entries else "Directory is empty."
    except Exception as e:
        return f"Error listing directory: {e}"


@tool
def search_files(directory: str, pattern: str) -> str:
    """Search for files matching a pattern in a directory tree.

    Args:
        directory: Root directory to search in.
        pattern: Glob pattern to match filenames (e.g., '*.py').
    """
    import glob

    try:
        path = os.path.expanduser(directory)
        if not _is_path_allowed(path):
            return f"Access Denied: The path '{directory}' is outside the allowed directories."
            
        matches = glob.glob(os.path.join(path, "**", pattern), recursive=True)
        if matches:
            return "\n".join(matches[:50])  # Cap at 50 results
        return "No files found matching the pattern."
    except Exception as e:
        return f"Error searching files: {e}"


# ─── Shell Tools ──────────────────────────────────────────────────────────────

@tool
def run_shell_command(command: str, working_directory: str = "~") -> str:
    """Execute a shell command and return its output.

    Args:
        command: The shell command to execute.
        working_directory: Directory to run the command in (default: home).
    """
    try:
        cwd = os.path.expanduser(working_directory)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        output += f"\nReturn code: {result.returncode}"
        return output.strip()
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds."
    except Exception as e:
        return f"Error running command: {e}"


# ─── System Info Tools ────────────────────────────────────────────────────────

@tool
def get_system_info() -> str:
    """Get system information including OS, CPU, memory, and disk usage."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return f"""System Information:
- OS: {platform.system()} {platform.release()} ({platform.machine()})
- Python: {platform.python_version()}
- CPU: {psutil.cpu_count()} cores, {cpu_percent}% usage
- Memory: {_format_size(memory.total)} total, {_format_size(memory.available)} available ({memory.percent}% used)
- Disk: {_format_size(disk.total)} total, {_format_size(disk.free)} free ({disk.percent}% used)
- Hostname: {platform.node()}
- Time: {datetime.now().isoformat()}"""
    except Exception as e:
        return f"Error getting system info: {e}"


@tool
def list_processes(sort_by: str = "memory") -> str:
    """List the top 15 running processes sorted by CPU or memory usage.

    Args:
        sort_by: Sort by 'cpu' or 'memory' (default: memory).
    """
    try:
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        key = "memory_percent" if sort_by == "memory" else "cpu_percent"
        procs.sort(key=lambda x: x.get(key, 0) or 0, reverse=True)

        lines = [f"{'PID':<8} {'Name':<25} {'CPU%':<8} {'Mem%':<8}"]
        lines.append("-" * 50)
        for p in procs[:15]:
            lines.append(
                f"{p['pid']:<8} {(p['name'] or 'N/A')[:24]:<25} "
                f"{(p['cpu_percent'] or 0):<8.1f} {(p['memory_percent'] or 0):<8.1f}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing processes: {e}"


# ─── App & Notification Tools ────────────────────────────────────────────────

@tool
def open_url(url: str) -> str:
    """Open a URL in the default web browser.

    Args:
        url: The URL to open.
    """
    import webbrowser

    try:
        webbrowser.open(url)
        return f"Opened {url} in the default browser."
    except Exception as e:
        return f"Error opening URL: {e}"


@tool
def send_notification(title: str, message: str) -> str:
    """Send a macOS native notification.

    Args:
        title: Notification title.
        message: Notification body text.
    """
    try:
        if platform.system() == "Darwin":
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{message}" with title "{title}"',
                ],
                check=True,
            )
            return f"Notification sent: {title}"
        else:
            return "Notifications are only supported on macOS."
    except Exception as e:
        return f"Error sending notification: {e}"


@tool
def get_clipboard() -> str:
    """Read the current clipboard contents (macOS only)."""
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return result.stdout or "(clipboard is empty)"
        return "Clipboard access is only supported on macOS."
    except Exception as e:
        return f"Error reading clipboard: {e}"


@tool
def set_clipboard(content: str) -> str:
    """Copy text to the clipboard (macOS only).

    Args:
        content: Text to copy to clipboard.
    """
    try:
        if platform.system() == "Darwin":
            subprocess.run(["pbcopy"], input=content, text=True, check=True)
            return f"Copied {len(content)} characters to clipboard."
        return "Clipboard access is only supported on macOS."
    except Exception as e:
        return f"Error writing to clipboard: {e}"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
