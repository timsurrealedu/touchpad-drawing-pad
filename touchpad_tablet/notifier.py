"""Desktop notification dispatcher using notify-send."""

import subprocess
import shutil
from typing import Optional


class Notifier:
    """Sends desktop notifications via standard system notify-send."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._notify_send_path = shutil.which("notify-send")

    def notify(self, title: str, message: str, icon: Optional[str] = None, urgency: str = "normal") -> None:
        if not self.enabled or not self._notify_send_path:
            return

        cmd = [
            self._notify_send_path,
            "--app-name=Touchpad Drawing Pad",
            f"--urgency={urgency}",
        ]
        if icon:
            cmd.append(f"--icon={icon}")
        cmd.extend([title, message])

        try:
            subprocess.run(cmd, check=False, timeout=1)
        except Exception:
            pass

    def notify_mode_change(self, tablet_mode: bool) -> None:
        if tablet_mode:
            self.notify(
                title="Touchpad Drawing Pad",
                message="Tablet Mode ENABLED (1:1 Digitizer active, cursor suppressed)",
                icon="input-tablet",
            )
        else:
            self.notify(
                title="Touchpad Drawing Pad",
                message="Mouse Mode RESTORED (Standard cursor active)",
                icon="input-touchpad",
            )
