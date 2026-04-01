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
import json
import logging
import os
import platform
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import uuid
import zlib
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ScreenConnectAgent")

# Binary message types
MSG_TYPE_FRAME = 0x01
MSG_TYPE_FILE_CHUNK = 0x02
MSG_TYPE_CAMERA_SNAP = 0x03

# Dangerous commands blocklist
BLOCKED_COMMANDS = {
    "format", "del /s", "rd /s", "rmdir /s", "rm -rf",
    "mkfs", "dd if=", "shutdown", "reboot", "halt",
}

# File transfer chunk size
CHUNK_SIZE = 64 * 1024  # 64KB


# =============================================================================
# Core Agent
# =============================================================================

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
        self._send_lock = threading.Lock()
        self._last_send_time = 0

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
        return (
            f"{self.server_url}/ws/session/{self.session_id}/"
            f"?token={self.token}&role=client"
        )

    def start(self):
        self.running = True
        self.on_status("connecting", "Connecting to server...")
        logger.info(f"Connecting to {self.ws_url}")

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        # Start background metrics if psutil is available
        if HAS_PSUTIL:
            self._metrics_thread = threading.Thread(target=self._metric_loop, daemon=True)
            self._metrics_thread.start()

        while self.running:
            try:
                self.ws.run_forever(ping_interval=15, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            if self.running:
                self.on_status("reconnecting", "Reconnecting in 3s...")
                time.sleep(3)

    def stop(self):
        self.running = False
        self.connected = False
        # Kill any active commands
        for cmd_id, proc in list(self._active_commands.items()):
            try:
                proc.kill()
            except Exception:
                pass
        self._active_commands.clear()

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

        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error handling message: {e}")

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
        interval = 1.0 / self.fps
        logger.info(f"Capturing at {self.fps} FPS (adaptive quality {self.min_quality}-{self.max_quality})")
        current_quality = self.quality
        consecutive_slow = 0

        try:
            with mss.mss() as sct:
                while self.running and self.connected:
                    if not self.streaming_enabled:
                        time.sleep(0.5)
                        continue

                    t0 = time.time()
                    try:
                        # 1. Congestion awareness: skip if we sent a frame very recently 
                        # and it was a large one (indicates slow network or high CPU)
                        if t0 - self._last_send_time < (interval * 0.8):
                            time.sleep(0.01)
                            continue

                        shot = sct.grab(sct.monitors[0])
                        # Use raw pixels for faster hashing before expensive CV2 conversions
                        frame_raw = np.array(shot)
                        
                        # 2. Block-based change detection (faster than full-thumbnail CRC)
                        # Divide screen into 4x4 blocks and check for changes
                        h_raw, w_raw = frame_raw.shape[:2]
                        
                        # Reset block hashes if resolution changes
                        if not hasattr(self, '_last_raw_dim') or self._last_raw_dim != (w_raw, h_raw):
                            self.last_block_hashes = {}
                            self._last_raw_dim = (w_raw, h_raw)

                        rows, cols = 4, 4
                        bw, bh = w_raw // cols, h_raw // rows
                        changed = False
                        
                        for r in range(rows):
                            for c in range(cols):
                                block = frame_raw[r * bh : (r + 1) * bh, c * bw : (c + 1) * bw]
                                # Fast hash using sum + xor of a subset of pixels
                                b_hash = zlib.adler32(block[::4, ::4].tobytes())
                                if self.last_block_hashes.get((r, c)) != b_hash:
                                    self.last_block_hashes[(r, c)] = b_hash
                                    changed = True
                        
                        if not changed and self.last_frame_crc is not None:
                            # Static frame — reset quality upward
                            if current_quality < self.max_quality:
                                current_quality = min(current_quality + 5, self.max_quality)
                            time.sleep(max(0, interval - (time.time() - t0)))
                            continue
                        self.last_frame_crc = 1 # Mark as not-initial

                        # 3. Processing
                        frame = cv2.cvtColor(frame_raw, cv2.COLOR_BGRA2BGR)
                        h, w = frame.shape[:2]
                        if w > self.max_width:
                            s = self.max_width / w
                            frame = cv2.resize(
                                frame, (int(w * s), int(h * s)),
                                interpolation=cv2.INTER_LINEAR)

                        # 4. Optimized JPEG Encoding
                        # IMWRITE_JPEG_OPTIMIZE: 10-15% smaller files for same quality
                        encode_param = [
                            cv2.IMWRITE_JPEG_QUALITY, current_quality,
                            cv2.IMWRITE_JPEG_OPTIMIZE, 1
                        ]
                        _, buf = cv2.imencode(".jpg", frame, encode_param)

                        # Send as binary: [type(1)] [width(2)] [height(2)] [timestamp(8)] [jpeg...]
                        fh, fw = frame.shape[:2]
                        header = struct.pack(
                            ">BHHd",
                            MSG_TYPE_FRAME,
                            fw, fh,
                            time.time()
                        )
                        self._send_binary(header + buf.tobytes())
                        self._last_send_time = time.time()

                    except Exception as e:
                        logger.error(f"Capture error: {e}")

                    elapsed = time.time() - t0

                    # Adaptive quality
                    if elapsed > interval * 1.2:
                        consecutive_slow += 1
                        if consecutive_slow >= 3 and current_quality > self.min_quality:
                            current_quality = max(current_quality - 5, self.min_quality)
                            consecutive_slow = 0
                    else:
                        consecutive_slow = 0
                        if current_quality < self.max_quality:
                            current_quality = min(current_quality + 1, self.max_quality)

                    time.sleep(max(0, interval - elapsed))
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
            self.last_frame_crc = None

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

        try:
            if action == "lock":
                os.system("rundll32.exe user32.dll,LockWorkStation")
            elif action == "logout":
                os.system("shutdown /l")
            elif action == "restart":
                os.system("shutdown /r /t 0")
            elif action == "shutdown":
                os.system("shutdown /s /t 0")
            elif action == "sleep":
                # Uses PowerShell to call SetSuspendState
                cmd = "powershell.exe -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false)\""
                subprocess.Popen(cmd, shell=True)
            elif action == "mute":
                os.system("powershell.exe -Command \"(New-Object -ComObject wscript.shell).SendKeys([char]173)\"")
            elif action == "vol_up":
                os.system("powershell.exe -Command \"(New-Object -ComObject wscript.shell).SendKeys([char]175)\"")
            elif action == "vol_down":
                os.system("powershell.exe -Command \"(New-Object -ComObject wscript.shell).SendKeys([char]174)\"")
            elif action == "empty_recycle_bin":
                os.system("powershell.exe -Command \"Clear-RecycleBin -Confirm:$false\"")
            elif action == "show_desktop":
                os.system("powershell.exe -Command \"(New-Object -ComObject shell.application).toggleDesktop()\"")
            elif action == "monitor_off":
                # SendMessage(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
                cmd = "powershell.exe -Command \"(Add-Type '[DllImport(\\\"user32.dll\\\")]public static extern int SendMessage(int hWnd, int hMsg, int wParam, int lParam);' -Name a -PassThru)::SendMessage(0xffff, 0x0112, 0xf170, 2)\""
                subprocess.Popen(cmd, shell=True)
            elif action == "brightness_up":
                os.system("powershell.exe -Command \"$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness + 10; if($b -gt 100){$b=100}; (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $b)\"")
            elif action == "brightness_down":
                os.system("powershell.exe -Command \"$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness - 10; if($b -lt 0){$b=0}; (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $b)\"")
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

    def _send_json(self, data):
        with self._send_lock:
            if self.ws and self.connected:
                try:
                    self.ws.send(json.dumps(data))
                except Exception as e:
                    logger.error(f"Send error: {e}")

    def _send_binary(self, data):
        with self._send_lock:
            if self.ws and self.connected:
                try:
                    self.ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
                except Exception as e:
                    logger.error(f"Binary send error: {e}")


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


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli()
    else:
        app = AgentGUI()
        app.run()
