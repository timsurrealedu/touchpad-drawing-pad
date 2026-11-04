"""Command-line interface for the Touchpad Drawing Pad daemon."""

import argparse
import sys
import os
import subprocess
import json
import logging
from pathlib import Path

from .config import TabletConfig, DEFAULT_CONFIG_PATH
from .device import find_touchpads, detect_display_resolution
from .ipc import send_ipc_command, read_daemon_pid
from .daemon import TabletDaemon


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> int:
    setup_logging(args.debug)
    config = TabletConfig.load()

    # Apply CLI overrides
    if args.device:
        config.device = args.device
    if args.aspect_ratio:
        config.aspect_ratio = args.aspect_ratio
    if args.smoothing is not None:
        config.smoothing = args.smoothing
    if getattr(args, "deadzone", None) is not None:
        config.deadzone = args.deadzone
    if args.mode:
        config.start_mode = args.mode

    existing_pid = read_daemon_pid()
    if existing_pid:
        print(f"Error: Another daemon instance is already running with PID {existing_pid}.")
        print("Run 'touchpad-tablet stop' first or check 'touchpad-tablet status'.")
        return 1

    daemon = TabletDaemon(config)
    try:
        daemon.run()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    existing_pid = read_daemon_pid()
    if existing_pid:
        print(f"Touchpad Drawing Pad is already running with PID {existing_pid}.")
        return 0

    cmd = [sys.executable, "-m", "touchpad_tablet", "run"]
    if args.device:
        cmd.extend(["--device", args.device])
    if args.aspect_ratio:
        cmd.extend(["--aspect-ratio", args.aspect_ratio])
    if args.smoothing is not None:
        cmd.extend(["--smoothing", str(args.smoothing)])
    if getattr(args, "deadzone", None) is not None:
        cmd.extend(["--deadzone", str(args.deadzone)])
    if args.mode:
        cmd.extend(["--mode", args.mode])

    log_file = Path("/tmp") / f"touchpad-tablet-{os.getuid()}.log"
    with open(log_file, "a") as f:
        proc = subprocess.Popen(
            cmd,
            stdout=f,
            stderr=f,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    print(f"Started Touchpad Drawing Pad daemon (PID: {proc.pid}).")
    print(f"Log output: {log_file}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    success, resp = send_ipc_command("STOP")
    if success:
        print(f"Daemon stopping: {resp}")
        return 0

    pid = read_daemon_pid()
    if pid:
        try:
            os.kill(pid, 15)  # SIGTERM
            print(f"Sent SIGTERM to daemon PID {pid}.")
            return 0
        except OSError as e:
            print(f"Failed to terminate PID {pid}: {e}")
            return 1

    print("Touchpad Drawing Pad is not running.")
    return 0


def cmd_toggle(args: argparse.Namespace) -> int:
    success, resp = send_ipc_command("TOGGLE")
    if success:
        print(resp)
        return 0

    pid = read_daemon_pid()
    if pid:
        try:
            os.kill(pid, 10)  # SIGUSR1
            print(f"Sent SIGUSR1 (toggle) to daemon PID {pid}.")
            return 0
        except OSError as e:
            print(f"Failed to send signal to PID {pid}: {e}")
            return 1

    print("Error: Touchpad Drawing Pad is not running.")
    print("Start the daemon first with 'touchpad-tablet start' or 'touchpad-tablet run'.")
    return 1


def cmd_enable(args: argparse.Namespace) -> int:
    success, resp = send_ipc_command("ENABLE")
    if success:
        print(resp)
        return 0
    print("Error: Daemon is not running.")
    return 1


def cmd_disable(args: argparse.Namespace) -> int:
    success, resp = send_ipc_command("DISABLE")
    if success:
        print(resp)
        return 0
    print("Error: Daemon is not running.")
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    success, resp = send_ipc_command("STATUS")
    if success:
        try:
            data = json.loads(resp)
            print("Touchpad Drawing Pad Daemon: ACTIVE")
            print(f"  Current Mode:      {data.get('mode', 'unknown').upper()}")
            print(f"  Touchpad Device:   {data.get('device_name')} ({data.get('device')})")
            print(f"  Display Target:    {data.get('screen_width')}x{data.get('screen_height')}")
            print(f"  Aspect Ratio Mode: {data.get('aspect_ratio')}")
            print(f"  Smoothing Factor:  {data.get('smoothing')}")
            return 0
        except json.JSONDecodeError:
            print(f"Daemon response: {resp}")
            return 0

    pid = read_daemon_pid()
    if pid:
        print(f"Daemon running (PID: {pid}), but socket did not respond.")
        return 1

    print("Touchpad Drawing Pad Daemon: INACTIVE (not running)")
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    print("Scanning system for touchpad input devices...")
    touchpads = find_touchpads()
    if not touchpads:
        print("No touchpad devices found in /dev/input/event*.")
        return 1

    print(f"Found {len(touchpads)} touchpad(s):")
    for tp in touchpads:
        print(f"\n  Device:       {tp.path}")
        print(f"  Name:         {tp.name}")
        print(f"  Dimensions:   {tp.width_mm:.1f} mm x {tp.height_mm:.1f} mm")
        print(f"  Coordinates:  X=[{tp.axis_x.minimum}, {tp.axis_x.maximum}], Y=[{tp.axis_y.minimum}, {tp.axis_y.maximum}]")
        print(f"  Resolution:   {tp.axis_x.resolution} units/mm")
        print(f"  Multi-touch:  {'Yes' if tp.has_multitouch else 'No'}")
        print(f"  Button Pad:   {'Yes' if tp.is_buttonpad else 'No'}")

    sw, sh = detect_display_resolution()
    print(f"\nDetected Display Resolution: {sw}x{sh}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    if args.init:
        cfg = TabletConfig()
        path = cfg.save()
        print(f"Generated default configuration at: {path}")
        return 0

    if DEFAULT_CONFIG_PATH.exists():
        print(f"Configuration file found at: {DEFAULT_CONFIG_PATH}\n")
        print(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        print(f"No custom config file found at {DEFAULT_CONFIG_PATH}.")
        print("Using built-in defaults. Run 'touchpad-tablet config --init' to generate one.")
    return 0


def cmd_install_service(args: argparse.Namespace) -> int:
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_file = service_dir / "touchpad-tablet.service"

    exe_path = sys.executable
    service_content = f"""[Unit]
Description=Touchpad Drawing Pad (Absolute Digitizer Tablet Daemon)
Documentation=https://github.com/timsurrealedu/touchpad-drawing-pad
After=graphical-session.target

[Service]
Type=simple
ExecStart={exe_path} -m touchpad_tablet run --mode mouse
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""
    service_file.write_text(service_content, encoding="utf-8")
    print(f"Installed systemd user service at: {service_file}")
    print("\nTo enable and start immediately:")
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now touchpad-tablet.service")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="touchpad-tablet",
        description="Touchpad Drawing Pad: Turn laptop touchpads into an absolute graphics tablet.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # run
    p_run = subparsers.add_parser("run", help="Run daemon in the foreground")
    p_run.add_argument("--device", help="Path to /dev/input/event* device node")
    p_run.add_argument("--aspect-ratio", choices=["fit", "stretch"], help="Aspect ratio mode")
    p_run.add_argument("--smoothing", type=float, help="Smoothing factor (0.0 to 1.0)")
    p_run.add_argument("--deadzone", type=float, help="Jitter deadzone threshold in sensor units (default 2.5)")
    p_run.add_argument("--mode", choices=["tablet", "mouse"], help="Initial mode on startup")
    p_run.add_argument("--debug", action="store_true", help="Enable verbose debug logging")

    # start
    p_start = subparsers.add_parser("start", help="Start daemon in background")
    p_start.add_argument("--device", help="Path to /dev/input/event* device node")
    p_start.add_argument("--aspect-ratio", choices=["fit", "stretch"], help="Aspect ratio mode")
    p_start.add_argument("--smoothing", type=float, help="Smoothing factor (0.0 to 1.0)")
    p_start.add_argument("--deadzone", type=float, help="Jitter deadzone threshold in sensor units (default 2.5)")
    p_start.add_argument("--mode", choices=["tablet", "mouse"], help="Initial mode on startup")

    # stop / toggle / enable / disable / status
    subparsers.add_parser("stop", help="Stop running background daemon")
    subparsers.add_parser("toggle", help="Toggle between Tablet Mode and Mouse Mode")
    subparsers.add_parser("enable", help="Enable Tablet Mode (suppress mouse, activate tablet)")
    subparsers.add_parser("disable", help="Disable Tablet Mode (restore normal mouse)")
    subparsers.add_parser("status", help="Query daemon status")
    subparsers.add_parser("devices", help="List detected touchpads and display resolution")

    # config
    p_config = subparsers.add_parser("config", help="View or generate configuration")
    p_config.add_argument("--init", action="store_true", help="Generate default ~/.config/touchpad-tablet/config.toml")

    # service
    subparsers.add_parser("install-service", help="Install systemd user service")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "run": cmd_run,
        "start": cmd_start,
        "stop": cmd_stop,
        "toggle": cmd_toggle,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "status": cmd_status,
        "devices": cmd_devices,
        "config": cmd_config,
        "install-service": cmd_install_service,
    }

    exit_code = commands[args.command](args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
