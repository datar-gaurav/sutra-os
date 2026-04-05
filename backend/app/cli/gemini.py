import argparse
import asyncio
import os
import sys

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from app.tools.os_tools import (
    list_directory,
    read_file,
    write_file,
    run_shell_command,
    search_files,
)
from app.tools.github_tools import (
    create_github_issue,
    create_github_pr,
    commit_and_push,
)

async def run_cli(instruction: str):
    """Run the Gemini CLI logic asynchronously."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    dev_mode = os.environ.get("GOOGLE_DEV_API_MODE", "N").upper()
    
    kwargs = {
        "model": "gemini-2.5-flash",
        "temperature": 0.0,
    }
    
    if dev_mode == "Y":
        try:
            import google.auth
            from google import genai
            credentials, project = google.auth.default()
            
            if not project and hasattr(credentials, "quota_project_id"):
                project = credentials.quota_project_id
            
            # Pre-initialize the genai.Client to prevent Langchain from assuming Vertex AI
            kwargs["client"] = genai.Client(credentials=credentials, project=project)
        except Exception as e:
            print("Error: Could not find default Google credentials with GOOGLE_DEV_API_MODE=Y.")
            print("Please run `gcloud auth application-default login` on your host or container.")
            sys.exit(1)
    else:
        if not api_key:
            print("Error: GOOGLE_API_KEY environment variable is not set and GOOGLE_DEV_API_MODE is not Y.")
            sys.exit(1)
        kwargs["google_api_key"] = api_key
            
    print(f"Sutra Gemini CLI Agent started. Goal: {instruction}")
    
    # Initialize the model
    llm = ChatGoogleGenerativeAI(**kwargs)
    
    # Define available tools
    tools = [
        list_directory,
        read_file,
        write_file,
        run_shell_command,
        search_files,
        create_github_issue,
        create_github_pr,
        commit_and_push,
    ]
    
    # Create the agent
    agent = create_react_agent(llm, tools)
    
    # Run the agent
    system_message = (
        "You are an autonomous AI software engineer. "
        "You have access to tools to read files, write files, run shell commands, "
        "and interact with GitHub to create issues and pull requests.\n\n"
        "IMPORTANT RULES:\n"
        "1. DO NOT try to initialize a new Git repository or run `git config`. You are running in an isolated Docker container, assume Git is handled externally by the host.\n"
        "2. If a command fails (e.g., `fatal: not in a git directory`), do NOT repeatedly try to fix it. Move on to other solutions or simply report your findings.\n\n"
        "Your task: " + instruction
    )
    
    inputs = {"messages": [("system", system_message), ("user", "Please fulfill the goal.")]}
    
    try:
        # Add a strict recursion_limit to prevent infinite loops on error
        config = {"recursion_limit": 10}
        async for s in agent.astream(inputs, config=config, stream_mode="values"):
            message = s["messages"][-1]
            message.pretty_print()
    except Exception as e:
        print(f"Error during agent execution: {e}")

def main():
    parser = argparse.ArgumentParser(description="Sutra Gemini Developer CLI")
    parser.add_argument("instruction", type=str, help="The instruction to execute")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_cli(args.instruction))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()
