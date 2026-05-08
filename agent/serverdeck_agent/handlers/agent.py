import asyncio
import subprocess
import logging

logger = logging.getLogger("serverdeck.agent.handlers.agent")

async def handle_uninstall(params: dict) -> dict:
    """
    Self-uninstalls the agent from the server.
    
    1. Responds to the portal immediately (success).
    2. Launches a detached shell script to cleanup and stop the service.
    """
    logger.info("Uninstall command received. Initiating self-destruct...")
    
    # We use systemd-run to launch a transient unit that survives the agent's own termination.
    # This ensures that even when the service stops, the cleanup script continues to run.
    uninstall_script = (
        "systemd-run --on-active=2s /bin/bash -c '"
        "systemctl stop serverdeck-agent; "
        "systemctl disable serverdeck-agent; "
        "rm -f /etc/systemd/system/serverdeck-agent.service; "
        "systemctl daemon-reload; "
        "rm -rf /opt/serverdeck /etc/serverdeck; "
        "logger \"ServerDeck Agent uninstalled and files removed\"'"
    )
    
    try:
        # Run the systemd-run command
        subprocess.run(["/bin/bash", "-c", uninstall_script], check=True)
        return {"status": "success", "message": "Uninstallation scheduled"}
    except Exception as e:
        logger.error(f"Failed to initiate uninstallation: {e}")
        return {"error": str(e)}
