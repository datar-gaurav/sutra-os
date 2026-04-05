import subprocess
from langchain_core.tools import tool

@tool
def run_gemini_cli(instruction: str) -> str:
    """
    Run the Sutra Gemini Developer CLI to autonomously code a feature or fix a bug based on instructions.
    
    Args:
        instruction: A detailed description of what the CLI needs to do (e.g., 'implement a new login endpoint in app/api/auth.py')
    """
    try:
        # Run the gemini cli as a subprocess
        result = subprocess.run(
            ["sutra-gemini", instruction],
            capture_output=True,
            text=True,
            check=True
        )
        return f"CLI executed successfully.\nOutput:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"CLI execution failed with exit code {e.returncode}.\nOutput:\n{e.stdout}\nError:\n{e.stderr}"
    except Exception as e:
        return f"Failed to run CLI: {str(e)}"
