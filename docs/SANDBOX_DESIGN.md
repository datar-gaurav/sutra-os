# Future Implementation: Container Isolation + Ollama

## Current State

| Area | Status |
|------|--------|
| Ollama in docker-compose | Host bridge only (`host.docker.internal:11434`) — Ollama runs on host |
| Shell command execution | `subprocess.run(shell=True)` directly in backend process — no isolation |
| File access | Path whitelist only (`_is_path_allowed`) — no real containment |
| LLM Registry | Full Ollama support exists (`ChatOllama`, discover, pull tools) |
| Ollama tools | `manage_ollama_model`, `pull_ollama_model` already registered |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  docker-compose                          │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ postgres │  │  redis   │  │  ollama  │ ← NEW service │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                          │
│  ┌─────────────────────────────────────┐               │
│  │  backend (FastAPI + Celery)          │               │
│  │  ┌───────────────────────────────┐  │               │
│  │  │  SandboxRunner                │  │               │
│  │  │  (Docker SDK via socket mount)│  │               │
│  │  └───────────┬───────────────────┘  │               │
│  └──────────────┼──────────────────────┘               │
│                 │ docker.sock                            │
│                 ▼                                        │
│  ┌─────────────────────────┐                           │
│  │  sutra-sandbox (image)  │ ← ephemeral per-execution │
│  │  - no network           │                           │
│  │  - tmpfs /workspace     │                           │
│  │  - mem: 256m, cpu: 0.5  │                           │
│  │  - non-root user        │                           │
│  │  - auto-removed (--rm)  │                           │
│  └─────────────────────────┘                           │
└─────────────────────────────────────────────────────────┘
```

---

## New Files

```
sutra/
├── docker-compose.yml              ← add ollama service, socket mount, sandbox config
├── sandbox/
│   ├── Dockerfile                  ← NEW: sandbox base image
│   └── build.sh                    ← NEW: build script
├── backend/
│   ├── app/
│   │   ├── config.py               ← add sandbox + ollama settings
│   │   ├── core/
│   │   │   └── sandbox.py          ← NEW: SandboxRunner class
│   │   └── tools/
│   │       └── os_tools.py         ← update run_shell_command to use SandboxRunner
│   └── start.sh                    ← add Ollama model auto-pull on startup
```

---

## Component Design

### 1. `sandbox/Dockerfile` — Sandbox Base Image

```dockerfile
FROM python:3.11-slim

# Common runtimes agents might need
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git jq bash coreutils findutils \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 sandbox
USER sandbox
WORKDIR /workspace
```

- No SSH, no package managers that need root
- Workspace is a tmpfs mount — nothing persists
- No network by default

---

### 2. `backend/app/core/sandbox.py` — SandboxRunner

```python
class SandboxRunner:
    def __init__(self):
        self.client = docker.from_env()  # via socket mount
        self.image = settings.sandbox_image
        self.memory_limit = settings.sandbox_memory_limit
        self.cpu_quota = int(settings.sandbox_cpu_limit * 100000)  # Docker units

    async def run(
        self,
        command: str,
        working_dir: str = "/workspace",
        bind_paths: list[str] = [],     # host paths to bind-mount (read-only)
        allow_network: bool = False,
        timeout: int = settings.sandbox_timeout,
        env: dict = {},
    ) -> SandboxResult:
        """
        Spins up an ephemeral container, runs command, returns stdout/stderr/exit_code.
        Container is auto-removed on completion or timeout.
        """
        volumes = {
            path: {"bind": path, "mode": "ro"}   # read-only by default
            for path in bind_paths
            if _is_path_allowed(path)
        }
        container = self.client.containers.run(
            image=self.image,
            command=["bash", "-c", command],
            working_dir=working_dir,
            volumes=volumes,
            tmpfs={"/workspace": "size=100m,uid=1000"},
            network_mode="none" if not allow_network else "bridge",
            mem_limit=self.memory_limit,
            cpu_quota=self.cpu_quota,
            user="1000",
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            environment=env,
            detach=True,
            remove=False,   # we remove manually after timeout
        )
        try:
            result = container.wait(timeout=timeout)
            stdout = container.logs(stdout=True, stderr=False).decode()
            stderr = container.logs(stdout=False, stderr=True).decode()
            return SandboxResult(stdout, stderr, result["StatusCode"])
        except Exception:
            container.kill()
            raise SandboxTimeoutError(f"Command timed out after {timeout}s")
        finally:
            container.remove(force=True)
```

---

### 3. `os_tools.py` changes — `run_shell_command`

```python
@tool
async def run_shell_command(command: str, working_directory: str = "~") -> str:
    if settings.sandbox_enabled:
        runner = SandboxRunner()
        result = await runner.run(
            command=command,
            bind_paths=settings.allowed_agent_file_paths_list,
        )
        return format_result(result)
    else:
        # existing subprocess fallback (dev mode)
        ...
```

File tools (`read_file`, `write_file`, etc.) can remain as-is since they already use path
whitelisting — or optionally move to sandbox too.

---

### 4. `docker-compose.yml` changes

```yaml
services:
  # --- NEW: Ollama local LLM server ---
  ollama:
    image: ollama/ollama:latest
    container_name: sutra-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped
    # GPU passthrough (uncomment for NVIDIA):
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

  backend:
    # existing...
    environment:
      OLLAMA_BASE_URL: http://ollama:11434   # ← change from host.docker.internal
      SANDBOX_ENABLED: "true"
      SANDBOX_IMAGE: sutra-sandbox:latest
      SANDBOX_MEMORY_LIMIT: "256m"
      SANDBOX_CPU_LIMIT: "0.5"
      SANDBOX_TIMEOUT: "60"
      OLLAMA_AUTO_PULL_MODELS: ""           # e.g. "llama3.2,mistral"
    volumes:
      # existing volumes...
      - /var/run/docker.sock:/var/run/docker.sock  # ← NEW: for SandboxRunner

volumes:
  ollama_data:   # ← NEW: persist downloaded models
```

---

### 5. `config.py` additions

```python
# Sandbox
sandbox_enabled: bool = True
sandbox_image: str = "sutra-sandbox:latest"
sandbox_memory_limit: str = "256m"
sandbox_cpu_limit: float = 0.5
sandbox_timeout: int = 60
sandbox_network_enabled: bool = False  # allow network in sandbox (for scraping tools)

# Ollama (containerized)
ollama_auto_pull_models: str = ""  # comma-separated: "llama3.2,mistral,phi4"

@property
def ollama_auto_pull_models_list(self) -> list[str]:
    return [m.strip() for m in self.ollama_auto_pull_models.split(",") if m.strip()]
```

---

### 6. `backend/start.sh` — Ollama model auto-pull

```bash
# Auto-pull configured Ollama models
if [ -n "$OLLAMA_AUTO_PULL_MODELS" ]; then
  echo "Waiting for Ollama at $OLLAMA_BASE_URL..."
  for i in $(seq 1 20); do
    curl -sf "$OLLAMA_BASE_URL/api/tags" > /dev/null && break
    sleep 3
  done
  for model in $(echo "$OLLAMA_AUTO_PULL_MODELS" | tr ',' '\n'); do
    echo "Pulling Ollama model: $model"
    curl -sf -X POST "$OLLAMA_BASE_URL/api/pull" \
      -d "{\"model\": \"$model\", \"stream\": false}" || true
  done
fi
```

---

## Security Properties After Implementation

| Threat | Before | After |
|--------|--------|-------|
| Arbitrary shell execution | Direct subprocess in backend | Isolated container, no network, tmpfs only |
| File system escape | Path whitelist only | Whitelist + bind-mount read-only, no host write |
| Resource exhaustion | 60s timeout only | Memory cap (256m), CPU cap (0.5), timeout kill |
| Internal network access from tool | Unrestricted | `--network none` (sandbox can't reach DB/Redis) |
| Ollama model persistence | Host-dependent | Named Docker volume, survives restarts |
| Ollama network exposure | Exposed on host | Internal Docker network only |

---

## Implementation Order

1. **Ollama service** in docker-compose (30 min) — no risk, fully additive
2. **Sandbox Dockerfile + build script** (30 min)
3. **`sandbox.py` SandboxRunner** (2h) — core logic
4. **Wire into `os_tools.py`** (1h) — `run_shell_command` + test
5. **`config.py` + `docker-compose.yml`** updates (30 min)
6. **`backend/start.sh`** Ollama auto-pull (30 min)
