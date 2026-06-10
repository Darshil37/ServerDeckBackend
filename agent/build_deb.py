import io
import os
import tarfile
from pathlib import Path

def make_ar_header(name: str, size: int, mtime: int = 1718000000, owner: int = 0, group: int = 0, mode: int = 0o100644) -> bytes:
    """Create a 60-byte header for the GNU ar archive format."""
    # GNU ar format terminates filenames with a '/'
    formatted_name = f"{name}/"
    header = f"{formatted_name:<16}{mtime:<12}{owner:<6}{group:<6}{mode:<8o}{size:<10}`\n"
    return header.encode("ascii")

def make_ar_archive(files: list[tuple[str, bytes]]) -> bytes:
    """Package a list of (filename, file_bytes) into a GNU ar archive."""
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in files:
        size = len(data)
        header = make_ar_header(name, size)
        out.write(header)
        out.write(data)
        if size % 2 != 0:
            out.write(b"\n")
    return out.getvalue()

def build_deb_in_memory(agent_root: Path) -> bytes:
    """Build a Debian package in memory and return its bytes."""
    agent_root = Path(agent_root).resolve()
    
    # 1. Build debian-binary
    debian_binary = b"2.0\n"

    # 2. Build control.tar.gz
    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz") as tar:
        for name in ["control", "postinst", "prerm", "postrm"]:
            file_path = agent_root / "debian" / name
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().replace("\r\n", "\n")
                content_bytes = content.encode("utf-8")
                
                tarinfo = tarfile.TarInfo(name=name)
                tarinfo.size = len(content_bytes)
                tarinfo.mode = 0o755 if name in ["postinst", "prerm", "postrm"] else 0o644
                tarinfo.uid = 0
                tarinfo.gid = 0
                tarinfo.uname = "root"
                tarinfo.gname = "root"
                
                tar.addfile(tarinfo, io.BytesIO(content_bytes))
    control_tar_gz = control_buf.getvalue()

    # 3. Build data.tar.gz
    data_buf = io.BytesIO()
    with tarfile.open(fileobj=data_buf, mode="w:gz") as tar:
        # Helper to add directory entry
        def add_dir(path):
            tarinfo = tarfile.TarInfo(name=path)
            tarinfo.type = tarfile.DIRTYPE
            tarinfo.mode = 0o755
            tarinfo.uid = 0
            tarinfo.gid = 0
            tarinfo.uname = "root"
            tarinfo.gname = "root"
            tar.addfile(tarinfo)

        # Helper to add file entry
        def add_file(arcname, content_bytes, mode=0o644):
            tarinfo = tarfile.TarInfo(name=arcname)
            tarinfo.size = len(content_bytes)
            tarinfo.mode = mode
            tarinfo.uid = 0
            tarinfo.gid = 0
            tarinfo.uname = "root"
            tarinfo.gname = "root"
            tar.addfile(tarinfo, io.BytesIO(content_bytes))

        # Add directories
        add_dir("opt")
        add_dir("opt/serverdeck")
        add_dir("opt/serverdeck/serverdeck_agent")
        add_dir("etc")
        add_dir("etc/systemd")
        add_dir("etc/systemd/system")

        # Add requirements.txt
        req_path = agent_root / "requirements.txt"
        if req_path.exists():
            with open(req_path, "r", encoding="utf-8") as f:
                req_content = f.read().replace("\r\n", "\n").encode("utf-8")
            add_file("opt/serverdeck/requirements.txt", req_content)

        # Add systemd service
        service_path = agent_root / "serverdeck-agent.service"
        if service_path.exists():
            with open(service_path, "r", encoding="utf-8") as f:
                service_content = f.read().replace("\r\n", "\n").encode("utf-8")
            add_file("etc/systemd/system/serverdeck-agent.service", service_content)

        # Add serverdeck_agent python module
        agent_pkg = agent_root / "serverdeck_agent"
        for root, dirs, files in os.walk(agent_pkg):
            for d in dirs:
                if d == "__pycache__":
                    continue
                full_dir_path = Path(root) / d
                rel_dir_path = os.path.relpath(full_dir_path, agent_root)
                rel_dir_path = rel_dir_path.replace("\\", "/")
                add_dir(f"opt/serverdeck/{rel_dir_path}")

            for f in files:
                if f.endswith((".py", ".json")):
                    full_file_path = Path(root) / f
                    rel_file_path = os.path.relpath(full_file_path, agent_root)
                    rel_file_path = rel_file_path.replace("\\", "/")
                    
                    with open(full_file_path, "r", encoding="utf-8") as file_handle:
                        file_content = file_handle.read().replace("\r\n", "\n").encode("utf-8")
                    
                    add_file(f"opt/serverdeck/{rel_file_path}", file_content)
    data_tar_gz = data_buf.getvalue()

    # 4. Assemble standard debian package ar archive
    deb_archive = make_ar_archive([
        ("debian-binary", debian_binary),
        ("control.tar.gz", control_tar_gz),
        ("data.tar.gz", data_tar_gz),
    ])
    
    return deb_archive

if __name__ == "__main__":
    import sys
    script_dir = Path(__file__).resolve().parent
    output_path = script_dir / "serverdeck-agent.deb"
    print(f"Building Debian package for ServerDeck Agent from {script_dir}...")
    deb_bytes = build_deb_in_memory(script_dir)
    with open(output_path, "wb") as out_f:
        out_f.write(deb_bytes)
    print(f"Successfully created: {output_path} ({len(deb_bytes)} bytes)")
