"""Ollama specific tools for AI agents."""

import httpx
from langchain_core.tools import tool

from app.config import settings

@tool
def manage_ollama_model(model_name: str, action: str) -> str:
    """Load or unload a model in Ollama to manage memory.

    Args:
        model_name: The name of the model to load or unload (e.g. "llama3").
        action: The action to perform, either "load" or "unload".
    """
    if action not in ("load", "unload"):
        return f"Error: Invalid action '{action}'. Must be 'load' or 'unload'."

    # Ollama API uses keep_alive parameter to manage loaded models
    # A negative keep_alive loads the model indefinitely
    # A keep_alive of 0 unloads the model immediately
    payload = {
        "model": model_name,
        "keep_alive": -1 if action == "load" else 0
    }

    try:
        # We use the /api/generate endpoint with an empty prompt just to trigger
        # the model loading/unloading without actually generating anything.
        with httpx.Client() as client:
            response = client.post(
                f"{settings.ollama_base_url}/api/generate",
                json=payload,
                timeout=10.0
            )
            
            # 404 meaning model is not found/downloaded
            if response.status_code == 404:
                return (
                    f"Error: Model '{model_name}' not found locally in Ollama. "
                    "You should ask the user if they would like you to download "
                    "and load it. If they say yes, use the `pull_ollama_model` tool."
                )
                
            response.raise_for_status()

            if action == "load":
                return f"Successfully loaded model '{model_name}' into Ollama memory."
            else:
                return f"Successfully unloaded model '{model_name}' from Ollama memory."
                
    except httpx.ConnectError:
        return "Error: Could not connect to Ollama. Is the Ollama service running on localhost:11434?"
    except httpx.TimeoutException:
        return f"Error: Request timed out while trying to {action} model '{model_name}'."
    except Exception as e:
        return f"Error managing Ollama model: {e}"


@tool
def pull_ollama_model(model_name: str) -> str:
    """Download a model into Ollama from the registry.

    Args:
        model_name: The name of the model to download (e.g. "llama3").
    """
    payload = {
        "model": model_name,
        "stream": False # Wait for the pull to complete before returning
    }

    try:
        # A pull can take a long time, so we set a very long timeout (e.g. 10 minutes)
        with httpx.Client() as client:
            response = client.post(
                f"{settings.ollama_base_url}/api/pull",
                json=payload,
                timeout=600.0
            )
            
            response.raise_for_status()
            return f"Successfully pulled and downloaded model '{model_name}' into Ollama."
            
    except httpx.ConnectError:
        return "Error: Could not connect to Ollama. Is the Ollama service running?"
    except httpx.TimeoutException:
        return f"Error: Request timed out while trying to pull model '{model_name}'. The model might still be downloading in the background."
    except Exception as e:
        return f"Error pulling Ollama model: {e}"
