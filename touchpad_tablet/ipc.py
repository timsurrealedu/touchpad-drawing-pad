"""Inter-process communication via UNIX domain socket and PID files."""

import os
import sys
import socket
import json
from pathlib import Path
from typing import Optional, Tuple, Callable


def get_runtime_dir() -> Path:
    """Returns the XDG runtime directory for the active user."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime):
        p = Path(runtime) / "touchpad-tablet"
    else:
        p = Path(f"/tmp/touchpad-tablet-{os.getuid()}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_pid_file() -> Path:
    return get_runtime_dir() / "daemon.pid"


def get_socket_file() -> Path:
    return get_runtime_dir() / "daemon.sock"


def is_process_running(pid: int) -> bool:
    """Checks if a process with the given PID is currently active."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def read_daemon_pid() -> Optional[int]:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        if is_process_running(pid):
            return pid
        # Stale PID file
        pid_file.unlink(missing_ok=True)
        return None
    except Exception:
        return None


def write_daemon_pid() -> None:
    pid_file = get_pid_file()
    pid_file.write_text(str(os.getpid()), encoding="utf-8")


def cleanup_ipc() -> None:
    get_pid_file().unlink(missing_ok=True)
    get_socket_file().unlink(missing_ok=True)


def send_ipc_command(command: str, timeout: float = 2.0) -> Tuple[bool, str]:
    """Sends a synchronous command to the running daemon via UNIX domain socket."""
    sock_file = get_socket_file()
    if not sock_file.exists():
        pid = read_daemon_pid()
        if not pid:
            return False, "Touchpad Drawing Pad daemon is not running."
        return False, "Daemon socket not found (process might be starting or hung)."

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(sock_file))
        client.sendall((command.strip() + "\n").encode("utf-8"))
        response = client.recv(4096).decode("utf-8").strip()
        return True, response
    except socket.error as e:
        return False, f"Failed to communicate with daemon socket: {e}"
    finally:
        client.close()


class IPCServer:
    """Listens for client CLI control commands over a UNIX domain socket."""

    def __init__(self, command_handler: Callable[[str], str]):
        self.command_handler = command_handler
        self.sock_path = get_socket_file()
        self.sock_path.unlink(missing_ok=True)

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(self.sock_path))
        self.sock.setblocking(False)
        self.sock.listen(5)

    @property
    def fileno(self) -> int:
        return self.sock.fileno()

    def handle_connection(self) -> None:
        try:
            conn, _ = self.sock.accept()
        except BlockingIOError:
            return

        conn.settimeout(1.0)
        try:
            data = conn.recv(1024).decode("utf-8").strip()
            if data:
                resp = self.command_handler(data)
                conn.sendall((resp + "\n").encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall(f"ERROR: {e}\n".encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass
        self.sock_path.unlink(missing_ok=True)
