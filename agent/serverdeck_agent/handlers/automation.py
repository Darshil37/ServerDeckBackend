import logging
from serverdeck_agent.utils import run_cmd

logger = logging.getLogger("serverdeck.agent.automation")

async def handle_run_script(params: dict) -> dict:
    """Run a shell script/command."""
    script = params.get("script", "")
    if not script:
        return {"error": "No script provided"}
    
    timeout = params.get("timeout", 60)
    result = await run_cmd(script, timeout=timeout)
    
    return {
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "returncode": result["returncode"]
    }
