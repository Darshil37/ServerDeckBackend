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
    
    # The script to run in the background
    # It waits 2 seconds to allow the response to be sent back to the portal
    uninstall_script = (
        "sleep 2; "
        "systemctl stop serverdeck-agent; "
        "systemctl disable serverdeck-agent; "
        "rm -f /etc/systemd/system/serverdeck-agent.service; "
        "systemctl daemon-reload; "
        "rm -rf /opt/serverdeck /etc/serverdeck; "
        "logger 'ServerDeck Agent uninstalled and files removed'"
    )
    
    try:
        # Run the script in the background without waiting for it
        subprocess.Popen(["/bin/bash", "-c", uninstall_script], start_new_session=True)
        return {"status": "success", "message": "Uninstallation initiated"}
    except Exception as e:
        logger.error(f"Failed to initiate uninstallation: {e}")
        return {"error": str(e)}
