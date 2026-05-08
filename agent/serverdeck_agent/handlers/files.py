import os
import shutil
import logging
from datetime import datetime

logger = logging.getLogger("serverdeck.agent.handlers.files")

async def handle_list(params: dict) -> dict:
    """List contents of a directory."""
    path = params.get("path", "/")
    if not os.path.isabs(path):
        return {"error": "Path must be absolute"}
    
    if not os.path.exists(path):
        return {"error": "Path does not exist"}
    
    if not os.path.isdir(path):
        return {"error": "Path is not a directory"}
    
    try:
        items = []
        for entry in os.scandir(path):
            try:
                info = entry.stat()
                items.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": info.st_size,
                    "mtime": datetime.fromtimestamp(info.st_mtime).isoformat(),
                    "permissions": oct(info.st_mode)[-3:]
                })
            except Exception:
                # Skip entries we can't access
                continue
                
        # Sort: directories first, then alphabetical
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        
        return {
            "path": path,
            "items": items,
            "parent": os.path.dirname(path) if path != "/" else None
        }
    except Exception as e:
        return {"error": str(e)}

async def handle_read(params: dict) -> dict:
    """Read file content."""
    path = params.get("path")
    if not path:
        return {"error": "Path is required"}
    
    if not os.path.isfile(path):
        return {"error": "Path is not a file"}
        
    try:
        # Check file size (don't read massive files into memory)
        if os.path.getsize(path) > 10 * 1024 * 1024: # 10MB limit
            return {"error": "File too large (max 10MB)"}
            
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            
        return {"content": content, "path": path}
    except Exception as e:
        return {"error": str(e)}

async def handle_write(params: dict) -> dict:
    """Write content to a file."""
    path = params.get("path")
    content = params.get("content", "")
    if not path:
        return {"error": "Path is required"}
        
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {"status": "success", "path": path}
    except Exception as e:
        return {"error": str(e)}

async def handle_delete(params: dict) -> dict:
    """Delete a file or directory."""
    path = params.get("path")
    if not path:
        return {"error": "Path is required"}
        
    if path == "/" or path == "/root" or path == "/home":
         return {"error": "Safety first: cannot delete root or home directories"}

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

async def handle_mkdir(params: dict) -> dict:
    """Create a directory."""
    path = params.get("path")
    if not path:
        return {"error": "Path is required"}
        
    try:
        os.makedirs(path, exist_ok=True)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}
