

#!/usr/bin/env python3
"""
Android Automation Suite - Hardened Single-File Version

Features:
- Device discovery
- Wireless ADB setup
- Tap / swipe / gestures / typing
- Screenshots and screen recording
- OCR text detection
- Template matching
- Macro recording and playback
- Performance monitoring
- Local web control panel
- SQLite persistence
- API token protected web interface

Author: Dr codewell edition
"""

import subprocess
import os
import sys
import time
import threading
import json
import cv2
import numpy as np
from datetime import datetime
import argparse
import sqlite3
import re
import urllib.parse
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import warnings

warnings.filterwarnings("ignore")

# ============================================================================
# OPTIONAL IMPORTS
# ============================================================================

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from flask import Flask, jsonify, request, send_from_directory, abort
    from flask_socketio import SocketIO
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# ============================================================================
# LOGGING
# ============================================================================

LOG_DIR = Path.home() / ".android_automation" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "automation.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("android_automation")

# ============================================================================
# DATABASE
# ============================================================================

class Database:
    """SQLite persistence layer"""

    def __init__(self, db_path: str = None):
        self.base_dir = Path.home() / ".android_automation"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or str(self.base_dir / "automation.db")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    model TEXT,
                    android_version TEXT,
                    last_seen TIMESTAMP,
                    connection_type TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS macros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    actions TEXT,
                    created TIMESTAMP,
                    modified TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS screenshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    filename TEXT,
                    timestamp TIMESTAMP,
                    tags TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    action TEXT,
                    status TEXT,
                    details TEXT,
                    timestamp TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            conn.commit()

    def add_device(self, device_id: str, info: Dict):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO devices
                (id, name, model, android_version, last_seen, connection_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                device_id,
                info.get("name", device_id),
                info.get("model", "Unknown"),
                info.get("android_version", "Unknown"),
                datetime.now(),
                info.get("type", "usb")
            ))
            conn.commit()

    def save_macro(self, name: str, actions: List[Dict]):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            now = datetime.now()
            c.execute("""
                INSERT OR REPLACE INTO macros (name, actions, created, modified)
                VALUES (?, ?, ?, ?)
            """, (name, json.dumps(actions), now, now))
            conn.commit()

    def get_macro(self, name: str) -> Optional[List[Dict]]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT actions FROM macros WHERE name = ?", (name,))
            row = c.fetchone()
            return json.loads(row[0]) if row else None

    def list_macros(self) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM macros ORDER BY name")
            return [r[0] for r in c.fetchall()]

    def add_log(self, device_id: str, action: str, status: str, details: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO logs (device_id, action, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (device_id, action, status, details, datetime.now()))
            conn.commit()

    def set_setting(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            """, (key, value))
            conn.commit()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = c.fetchone()
            return row[0] if row else default

# ============================================================================
# ADB CLIENT
# ============================================================================

class ADBClient:
    """Centralized ADB handler"""

    def __init__(self):
        self.default_timeout = 12
        self.retry_count = 3

    def _run(self, device_id: Optional[str], *args, capture_output: bool = True,
             timeout: Optional[int] = None, check: bool = False, binary: bool = False):
        cmd = ["adb"]
        if device_id:
            cmd += ["-s", device_id]
        cmd += list(args)

        timeout = timeout or self.default_timeout

        last_error = None
        for attempt in range(self.retry_count):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=capture_output,
                    text=not binary,
                    timeout=timeout
                )
                if check and result.returncode != 0:
                    raise RuntimeError(result.stderr if hasattr(result, "stderr") else "ADB command failed")
                return result
            except Exception as e:
                last_error = e
                if attempt < self.retry_count - 1:
                    time.sleep(1)
        raise last_error

    def shell(self, device_id: str, command: str, timeout: int = None) -> str:
        result = self._run(device_id, "shell", command, timeout=timeout)
        return result.stdout.strip()

    def get_devices(self) -> List[Dict]:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        devices = []

        for line in result.stdout.strip().splitlines()[1:]:
            if "\tdevice" in line:
                device_id = line.split("\t")[0]
                conn_type = "wireless" if ":" in device_id else "usb"
                devices.append({"id": device_id, "type": conn_type})

        return devices

    def tap(self, device_id: str, x: int, y: int):
        self._run(device_id, "shell", "input", "tap", str(x), str(y))

    def swipe(self, device_id: str, x1: int, y1: int, x2: int, y2: int, duration: int = 100):
        self._run(device_id, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration))

    def input_text(self, device_id: str, text: str):
        safe_text = urllib.parse.quote(text, safe="")
        self._run(device_id, "shell", "input", "text", safe_text)

    def keyevent(self, device_id: str, keycode: int):
        self._run(device_id, "shell", "input", "keyevent", str(keycode))

    def screenshot(self, device_id: str, output_path: str):
        result = self._run(device_id, "exec-out", "screencap", "-p", capture_output=True, binary=True, timeout=30)
        with open(output_path, "wb") as f:
            f.write(result.stdout)

    def get_property(self, device_id: str, prop: str) -> str:
        return self.shell(device_id, f"getprop {prop}")

    def install(self, device_id: str, apk_path: str, reinstall: bool = False) -> bool:
        cmd = ["install"]
        if reinstall:
            cmd.append("-r")
        cmd.append(apk_path)
        result = self._run(device_id, *cmd)
        return "Success" in result.stdout

    def uninstall(self, device_id: str, package: str) -> bool:
        result = self._run(device_id, "uninstall", package)
        return "Success" in result.stdout

    def start_app(self, device_id: str, package: str, activity: str = None):
        if activity:
            self._run(device_id, "shell", "am", "start", "-n", f"{package}/{activity}")
        else:
            self._run(device_id, "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")

    def stop_app(self, device_id: str, package: str):
        self._run(device_id, "shell", "am", "force-stop", package)

# ============================================================================
# DEVICE MANAGER
# ============================================================================

class DeviceManager:
    """Handles device info and selection"""

    def __init__(self, adb: ADBClient, db: Database):
        self.adb = adb
        self.db = db
        self.active_device = None

    def get_all_devices(self) -> List[Dict]:
        devices = []
        for device in self.adb.get_devices():
            info = self._get_device_info(device["id"])
            info["type"] = device["type"]
            devices.append({
                "id": device["id"],
                "type": device["type"],
                "info": info
            })
            self.db.add_device(device["id"], info)
        return devices

    def _get_device_info(self, device_id: str) -> Dict:
        info = {}

        try:
            info["model"] = self.adb.get_property(device_id, "ro.product.model")
            info["manufacturer"] = self.adb.get_property(device_id, "ro.product.manufacturer")
            info["android_version"] = self.adb.get_property(device_id, "ro.build.version.release")
            info["sdk_version"] = self.adb.get_property(device_id, "ro.build.version.sdk")

            resolution_output = self.adb.shell(device_id, "wm size")
            match = re.search(r"(\d+)x(\d+)", resolution_output)
            if match:
                info["resolution"] = f"{match.group(1)}x{match.group(2)}"
            else:
                info["resolution"] = "Unknown"

            battery_output = self.adb.shell(device_id, "dumpsys battery")
            level_match = re.search(r"level:\s*(\d+)", battery_output)
            temp_match = re.search(r"temperature:\s*(\d+)", battery_output)

            info["battery"] = level_match.group(1) if level_match else "Unknown"
            info["battery_temp"] = f"{int(temp_match.group(1))/10:.1f}°C" if temp_match else "Unknown"

            ram_output = self.adb.shell(device_id, "cat /proc/meminfo")
            ram_match = re.search(r"MemTotal:\s+(\d+)", ram_output)
            if ram_match:
                total_kb = int(ram_match.group(1))
                info["total_ram"] = f"{total_kb / 1024 / 1024:.2f} GB"
            else:
                info["total_ram"] = "Unknown"

            storage_output = self.adb.shell(device_id, "df /data")
            storage_lines = storage_output.splitlines()
            if len(storage_lines) > 1:
                parts = storage_lines[1].split()
                info["storage"] = parts[3] if len(parts) > 3 else "Unknown"
            else:
                info["storage"] = "Unknown"

            cpu_output = self.adb.shell(device_id, "cat /proc/cpuinfo")
            info["cpu_cores"] = str(cpu_output.count("processor")) + " cores" if cpu_output else "Unknown"

            wifi_output = self.adb.shell(device_id, "ip addr show wlan0")
            ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", wifi_output)
            info["wifi_ip"] = ip_match.group(1) if ip_match else "Unknown"

            info["name"] = f"{info.get('manufacturer', 'Android')} {info.get('model', 'Device')}"

        except Exception as e:
            logger.error(f"Error getting device info for {device_id}: {e}")

        return info

    def get_device_resolution(self, device_id: str) -> Tuple[int, int]:
        output = self.adb.shell(device_id, "wm size")
        match = re.search(r"(\d+)x(\d+)", output)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 1080, 1920

    def test_connection(self, device_id: str = None) -> bool:
        device = device_id or self.active_device
        if not device:
            return False
        try:
            result = self.adb.shell(device, 'echo "test"')
            return result.strip() == "test"
        except Exception:
            return False

    def select_device(self, device_id: str = None) -> bool:
        if device_id:
            self.active_device = device_id
            return True

        devices = self.get_all_devices()
        if devices:
            self.active_device = devices[0]["id"]
            return True

        return False

    def wireless_setup(self, device_id: str = None) -> bool:
        if not device_id:
            devices = self.get_all_devices()
            usb_devices = [d for d in devices if d["type"] == "usb"]
            if not usb_devices:
                print("❌ No USB device found")
                return False
            device_id = usb_devices[0]["id"]

        wifi_output = self.adb.shell(device_id, "ip addr show wlan0")
        match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", wifi_output)

        if not match:
            print("❌ Could not find WiFi IP")
            return False

        ip = match.group(1)
        print(f"📱 Phone IP: {ip}")

        subprocess.run(["adb", "-s", device_id, "tcpip", "5555"], capture_output=True)
        time.sleep(2)
        result = subprocess.run(["adb", "connect", f"{ip}:5555"], capture_output=True, text=True)

        if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
            print(f"✅ Wireless connection established: {ip}:5555")
            return True

        print(f"❌ Wireless connection failed: {result.stdout.strip()}")
        return False

# ============================================================================
# GESTURES
# ============================================================================

class GestureController:
    """Touch and keyboard control"""

    def __init__(self, adb: ADBClient, device_manager: DeviceManager):
        self.adb = adb
        self.device_manager = device_manager
        self.recording_callback = None
        self.resolution_cache = {}

    def set_recording_callback(self, callback):
        self.recording_callback = callback

    def _record_action(self, action_type: str, params: Dict):
        if self.recording_callback:
            self.recording_callback(action_type, params)

    def _get_scaled_coords(self, device_id: str, x: int, y: int) -> Tuple[int, int]:
        if device_id not in self.resolution_cache:
            self.resolution_cache[device_id] = self.device_manager.get_device_resolution(device_id)

        width, height = self.resolution_cache[device_id]
        base_width, base_height = 1080, 1920

        scaled_x = int(x * width / base_width)
        scaled_y = int(y * height / base_height)
        return scaled_x, scaled_y

    def tap(self, x: int, y: int, device_id: str = None, scale: bool = False):
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        if scale:
            x, y = self._get_scaled_coords(device, x, y)

        self.adb.tap(device, x, y)
        print(f"✓ Tapped at ({x}, {y})")
        self._record_action("tap", {"x": x, "y": y})

    def double_tap(self, x: int, y: int, device_id: str = None, scale: bool = False):
        self.tap(x, y, device_id, scale=scale)
        time.sleep(0.08)
        self.tap(x, y, device_id, scale=scale)
        print(f"✓ Double tapped at ({x}, {y})")
        self._record_action("double_tap", {"x": x, "y": y})

    def long_press(self, x: int, y: int, duration: int = 2000, device_id: str = None, scale: bool = False):
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        if scale:
            x, y = self._get_scaled_coords(device, x, y)

        self.adb.swipe(device, x, y, x, y, duration)
        print(f"✓ Long pressed at ({x}, {y}) for {duration}ms")
        self._record_action("long_press", {"x": x, "y": y, "duration": duration})

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 100, device_id: str = None, scale: bool = False):
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        if scale:
            x1, y1 = self._get_scaled_coords(device, x1, y1)
            x2, y2 = self._get_scaled_coords(device, x2, y2)

        self.adb.swipe(device, x1, y1, x2, y2, duration)
        print(f"✓ Swiped from ({x1}, {y1}) to ({x2}, {y2})")
        self._record_action("swipe", {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration
        })

    def pinch(self, center_x: int, center_y: int, radius: int = 100, direction: str = "in", device_id: str = None):
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        if direction == "in":
            self.adb.swipe(device, center_x - radius, center_y, center_x - radius // 2, center_y, 150)
            self.adb.swipe(device, center_x + radius, center_y, center_x + radius // 2, center_y, 150)
        else:
            self.adb.swipe(device, center_x - radius // 2, center_y, center_x - radius, center_y, 150)
            self.adb.swipe(device, center_x + radius // 2, center_y, center_x + radius, center_y, 150)

        print(f"✓ Pinch {direction} at ({center_x}, {center_y})")
        self._record_action("pinch", {
            "center_x": center_x,
            "center_y": center_y,
            "radius": radius,
            "direction": direction
        })

    def type_text(self, text: str, device_id: str = None):
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        self.adb.input_text(device, text)
        print(f"✓ Typed: {text}")
        self._record_action("text", {"text": text})

    def press_key(self, key: str, device_id: str = None):
        keycodes = {
            "home": 3,
            "back": 4,
            "call": 5,
            "endcall": 6,
            "volume_up": 24,
            "volume_down": 25,
            "power": 26,
            "camera": 27,
            "clear": 28,
            "menu": 82,
            "search": 84,
            "enter": 66,
            "delete": 67,
            "space": 62,
            "tab": 61
        }

        keycode = keycodes.get(key.lower(), key)
        if isinstance(keycode, str):
            try:
                keycode = int(keycode)
            except ValueError:
                raise RuntimeError(f"Unknown key: {key}")

        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        self.adb.keyevent(device, keycode)
        print(f"✓ Pressed key: {key}")
        self._record_action("key", {"key": key})

# ============================================================================
# SCREEN CAPTURE
# ============================================================================

class ScreenCapture:
    """Screenshots and recordings"""

    def __init__(self, adb: ADBClient, device_manager: DeviceManager, db: Database):
        self.adb = adb
        self.device_manager = device_manager
        self.db = db
        self.screenshot_dir = Path.home() / ".android_automation" / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def take_screenshot(self, device_id: str = None, filename: str = None,
                        region: Tuple[int, int, int, int] = None) -> str:
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.screenshot_dir / f"screenshot_{timestamp}.png"
        else:
            filename = Path(filename)
            if not filename.suffix:
                filename = filename.with_suffix(".png")
            filename = self.screenshot_dir / filename.name

        self.adb.screenshot(device, str(filename))

        if region:
            img = cv2.imread(str(filename))
            if img is not None:
                x, y, w, h = region
                cropped = img[y:y+h, x:x+w]
                cv2.imwrite(str(filename), cropped)

        self.db.add_log(device, "screenshot", "success", str(filename))
        print(f"📸 Screenshot saved: {filename}")
        return str(filename)

    def screen_record(self, duration: int = 30, filename: str = None,
                      bitrate: int = 4, resolution: str = None,
                      show_touches: bool = False, device_id: str = None) -> Optional[str]:
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.mp4"

        cmd = ["adb", "-s", device, "shell", "screenrecord"]

        if show_touches:
            cmd.append("--show-touches")
        if resolution:
            cmd.extend(["--size", resolution])

        cmd.extend(["--bit-rate", str(bitrate * 1000000)])
        cmd.extend(["--time-limit", str(duration)])
        cmd.append(f"/sdcard/{filename}")

        print(f"🎬 Recording for {duration} seconds...")
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            process.wait()
        except KeyboardInterrupt:
            process.terminate()
            print("\n⏹️ Recording stopped early")

        pull_result = subprocess.run(["adb", "-s", device, "pull", f"/sdcard/{filename}", filename], capture_output=True)

        if pull_result.returncode == 0:
            subprocess.run(["adb", "-s", device, "shell", "rm", f"/sdcard/{filename}"])
            print(f"🎥 Recording saved: {filename}")
            return filename

        print("❌ Failed to pull recording")
        return None

# ============================================================================
# COMPUTER VISION
# ============================================================================

class VisionProcessor:
    """OCR + template matching"""

    def __init__(self, screen_capture: ScreenCapture):
        self.screen_capture = screen_capture

    def find_element(self, template_path: str, device_id: str = None,
                     threshold: float = 0.8, region: Tuple[int, int, int, int] = None) -> Optional[List[Dict]]:
        screenshot = self.screen_capture.take_screenshot(device_id, "find_temp.png")

        screen = cv2.imread(screenshot)
        template = cv2.imread(template_path)

        if screen is None or template is None:
            print("❌ Could not load images")
            return None

        if region:
            x, y, w, h = region
            screen = screen[y:y+h, x:x+w]

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            x = max_loc[0] + template.shape[1] // 2
            y = max_loc[1] + template.shape[0] // 2

            if region:
                x += region[0]
                y += region[1]

            matches = [{
                "x": x,
                "y": y,
                "confidence": float(max_val)
            }]

            print(f"✓ Found element at ({x}, {y}) with confidence {max_val:.2f}")
            return matches

        print(f"❌ No match found (best confidence: {max_val:.2f})")
        return []

    def find_and_tap(self, template_path: str, gesture: GestureController,
                     device_id: str = None, threshold: float = 0.8) -> bool:
        matches = self.find_element(template_path, device_id, threshold)
        if matches:
            gesture.tap(matches[0]["x"], matches[0]["y"], device_id)
            return True
        return False

    def detect_text(self, device_id: str = None, region: Tuple[int, int, int, int] = None,
                    language: str = "eng") -> Optional[str]:
        if not OCR_AVAILABLE:
            print("❌ OCR not installed. Run:")
            print("pip install pytesseract pillow")
            print("sudo apt install tesseract-ocr")
            return None

        screenshot = self.screen_capture.take_screenshot(device_id, "ocr_temp.png")

        img = Image.open(screenshot)
        if region:
            img = img.crop(region)

        text = pytesseract.image_to_string(img, lang=language)

        print("📝 Detected text:")
        print("-" * 60)
        print(text)
        print("-" * 60)
        return text

    def compare_screenshots(self, baseline: str, current: str = None,
                            device_id: str = None, threshold: float = 0.95) -> Optional[str]:
        if not current:
            current = self.screen_capture.take_screenshot(device_id, "compare_current.png")

        img1 = cv2.imread(baseline)
        img2 = cv2.imread(current)

        if img1 is None or img2 is None:
            print("❌ Could not load images")
            return None

        if img1.shape != img2.shape:
            img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

        diff = cv2.absdiff(img1, img2)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

        non_zero = np.count_nonzero(gray)
        total = gray.size
        similarity = 100 - (non_zero / total * 100)

        print(f"📊 Similarity: {similarity:.2f}%")

        if similarity >= threshold * 100:
            print("✓ Screens are similar")
            return None

        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        result = img2.copy()
        for contour in contours:
            if cv2.contourArea(contour) > 100:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(result, (x, y), (x + w, y + h), (0, 0, 255), 2)

        diff_file = f"diff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        cv2.imwrite(diff_file, result)
        print(f"📸 Differences saved: {diff_file}")
        return diff_file

# ============================================================================
# MACROS
# ============================================================================

class MacroRecorder:
    """Macro recording and playback"""

    def __init__(self, db: Database):
        self.db = db
        self.recording = False
        self.current_macro = None
        self.actions = []
        self.last_action_time = None

    def start_recording(self, name: str):
        self.recording = True
        self.current_macro = name
        self.actions = []
        self.last_action_time = time.time()
        print(f"🎬 Recording macro '{name}'... Press Ctrl+C to stop")

    def stop_recording(self) -> bool:
        if self.recording:
            self.recording = False
            self.db.save_macro(self.current_macro, self.actions)
            print(f"✓ Macro '{self.current_macro}' saved with {len(self.actions)} actions")
            self.current_macro = None
            return True
        return False

    def record_action(self, action_type: str, params: Dict):
        if self.recording:
            now = time.time()
            delay = round(now - self.last_action_time, 3) if self.last_action_time else 0.2
            self.last_action_time = now

            self.actions.append({
                "type": action_type,
                "params": params,
                "delay": delay,
                "timestamp": now
            })

    def play_macro(self, name: str, gesture: GestureController) -> bool:
        actions = self.db.get_macro(name)
        if not actions:
            print(f"❌ Macro '{name}' not found")
            return False

        print(f"▶️ Playing macro '{name}' ({len(actions)} actions)...")

        for i, action in enumerate(actions, 1):
            print(f"  Step {i}: {action['type']}")
            try:
                if action["type"] == "tap":
                    gesture.tap(**action["params"])
                elif action["type"] == "double_tap":
                    gesture.double_tap(**action["params"])
                elif action["type"] == "long_press":
                    gesture.long_press(**action["params"])
                elif action["type"] == "swipe":
                    gesture.swipe(**action["params"])
                elif action["type"] == "pinch":
                    gesture.pinch(**action["params"])
                elif action["type"] == "text":
                    gesture.type_text(**action["params"])
                elif action["type"] == "key":
                    gesture.press_key(**action["params"])
            except Exception as e:
                print(f"  ✗ Failed at step {i}: {e}")
                return False

            time.sleep(action.get("delay", 0.2))

        print("✓ Macro completed")
        return True

    def list_macros(self) -> List[str]:
        return self.db.list_macros()

# ============================================================================
# PERFORMANCE MONITOR
# ============================================================================

class PerformanceMonitor:
    """App performance stats"""

    def __init__(self, adb: ADBClient, device_manager: DeviceManager):
        self.adb = adb
        self.device_manager = device_manager

    def monitor_app(self, package_name: str, duration: int = 30,
                    device_id: str = None, output_file: str = None) -> Dict:
        device = device_id or self.device_manager.active_device
        if not device:
            raise RuntimeError("No device selected")

        print(f"📊 Monitoring {package_name} for {duration} seconds...")

        metrics = {
            "cpu": [],
            "memory": [],
            "battery": [],
            "timestamps": []
        }

        start_time = time.time()

        while time.time() - start_time < duration:
            timestamp = round(time.time() - start_time, 2)

            try:
                cpu_output = self.adb.shell(device, f"top -n 1 -b | grep {package_name}")
                if cpu_output:
                    cpu_parts = cpu_output.split()
                    for part in cpu_parts:
                        if part.endswith("%"):
                            try:
                                metrics["cpu"].append(float(part.replace("%", "")))
                                break
                            except ValueError:
                                pass
            except Exception:
                pass

            try:
                mem_output = self.adb.shell(device, f"dumpsys meminfo {package_name}")
                mem_match = re.search(r"TOTAL\s+(\d+)", mem_output)
                if mem_match:
                    metrics["memory"].append(round(int(mem_match.group(1)) / 1024, 2))
            except Exception:
                pass

            try:
                battery_output = self.adb.shell(device, "dumpsys battery")
                level_match = re.search(r"level:\s*(\d+)", battery_output)
                if level_match:
                    metrics["battery"].append(int(level_match.group(1)))
            except Exception:
                pass

            metrics["timestamps"].append(timestamp)
            time.sleep(1)

        if not output_file:
            output_file = f"perf_{package_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_file, "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"✓ Performance metrics saved: {output_file}")

        if metrics["cpu"]:
            print(f"  CPU Avg: {sum(metrics['cpu']) / len(metrics['cpu']):.1f}%")
            print(f"  CPU Max: {max(metrics['cpu']):.1f}%")
        if metrics["memory"]:
            print(f"  Memory Avg: {sum(metrics['memory']) / len(metrics['memory']):.1f} MB")
            print(f"  Memory Max: {max(metrics['memory']):.1f} MB")

        return metrics

# ============================================================================
# WEB SERVER
# ============================================================================

class WebServer:
    """Local-only secure web panel"""

    def __init__(self, db: Database, device_manager: DeviceManager, screen_capture: ScreenCapture,
                 gesture: GestureController, macro_recorder: MacroRecorder):
        self.db = db
        self.device_manager = device_manager
        self.screen_capture = screen_capture
        self.gesture = gesture
        self.macro_recorder = macro_recorder
        self.app = None
        self.socketio = None

        token = self.db.get_setting("api_token")
        if not token:
            token = secrets.token_hex(16)
            self.db.set_setting("api_token", token)
        self.api_token = token

    def _check_auth(self):
        token = request.headers.get("X-API-Token") or request.args.get("token")
        if token != self.api_token:
            abort(401)

    def start(self, port: int = 5000):
        if not FLASK_AVAILABLE:
            print("❌ Flask not installed. Run:")
            print("pip install flask flask-socketio")
            return False

        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins=[])

        self._setup_routes()

        print(f"🌐 Web UI: http://127.0.0.1:{port}")
        print(f"🔐 API Token: {self.api_token}")
        print("Press Ctrl+C to stop")

        try:
            self.socketio.run(self.app, host="127.0.0.1", port=port, debug=False)
        except KeyboardInterrupt:
            print("\nWeb server stopped")

        return True

    def _setup_routes(self):
        @self.app.route("/")
        def index():
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Android Automation Suite</title>
                <style>
                    body {{ font-family: Arial; margin: 20px; background: #f0f0f0; }}
                    .container {{ max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 10px; }}
                    .device {{ border: 1px solid #ddd; margin: 10px 0; padding: 10px; border-radius: 5px; cursor: pointer; }}
                    .device:hover {{ background: #f9f9f9; }}
                    .device.selected {{ background: #e3f2fd; border-color: #2196f3; }}
                    button {{ margin: 5px; padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
                    button:hover {{ background: #0056b3; }}
                    #screenshot {{ max-width: 100%; margin-top: 20px; border: 1px solid #ddd; }}
                    input {{ padding: 8px; width: 400px; margin-bottom: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📱 Android Automation Suite</h1>
                    <p><strong>API Token:</strong> <code>{self.api_token}</code></p>
                    <input id="token" value="{self.api_token}" />
                    <div id="devices"></div>

                    <div>
                        <button onclick="takeScreenshot()">📸 Screenshot</button>
                        <button onclick="startRecording()">🎬 Record Macro</button>
                        <button onclick="stopRecording()">⏹️ Stop Recording</button>
                        <button onclick="refreshDevices()">🔄 Refresh</button>
                    </div>

                    <div id="screenshot-container"></div>
                </div>

                <script>
                    let selectedDevice = null;

                    function authHeaders() {{
                        return {{
                            "Content-Type": "application/json",
                            "X-API-Token": document.getElementById("token").value
                        }};
                    }}

                    function refreshDevices() {{
                        fetch('/api/devices', {{
                            headers: authHeaders()
                        }})
                        .then(r => r.json())
                        .then(data => {{
                            let html = '<h2>Devices</h2>';
                            data.devices.forEach(device => {{
                                const isSelected = selectedDevice === device.id;
                                html += `<div class="device ${{isSelected ? 'selected' : ''}}" onclick="selectDevice('${{device.id}}')">
                                    <strong>${{device.id}}</strong><br>
                                    Model: ${{device.info.model}}<br>
                                    Android: ${{device.info.android_version}}<br>
                                    Battery: ${{device.info.battery}}%<br>
                                    <small>${{device.type}}</small>
                                </div>`;
                            }});
                            document.getElementById('devices').innerHTML = html;
                        }});
                    }}

                    function selectDevice(deviceId) {{
                        selectedDevice = deviceId;
                        fetch('/api/select_device', {{
                            method: 'POST',
                            headers: authHeaders(),
                            body: JSON.stringify({{device_id: deviceId}})
                        }}).then(() => refreshDevices());
                    }}

                    function takeScreenshot() {{
                        fetch('/api/screenshot', {{
                            headers: authHeaders()
                        }})
                        .then(r => r.json())
                        .then(data => {{
                            if (data.success) {{
                                document.getElementById('screenshot-container').innerHTML =
                                    `<img id="screenshot" src="/screenshots/${{data.filename}}?token=${{document.getElementById("token").value}}">`;
                            }}
                        }});
                    }}

                    function startRecording() {{
                        const name = prompt('Macro name:');
                        if (name) {{
                            fetch('/api/start_recording', {{
                                method: 'POST',
                                headers: authHeaders(),
                                body: JSON.stringify({{name}})
                            }});
                        }}
                    }}

                    function stopRecording() {{
                        fetch('/api/stop_recording', {{
                            method: 'POST',
                            headers: authHeaders()
                        }});
                    }}

                    refreshDevices();
                    setInterval(refreshDevices, 5000);
                </script>
            </body>
            </html>
            """

        @self.app.route("/api/devices")
        def api_devices():
            self._check_auth()
            return jsonify({"devices": self.device_manager.get_all_devices()})

        @self.app.route("/api/select_device", methods=["POST"])
        def api_select_device():
            self._check_auth()
            data = request.json or {}
            self.device_manager.select_device(data.get("device_id"))
            return jsonify({"success": True})

        @self.app.route("/api/screenshot")
        def api_screenshot():
            self._check_auth()
            try:
                filename = self.screen_capture.take_screenshot()
                return jsonify({"success": True, "filename": os.path.basename(filename)})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})

        @self.app.route("/api/start_recording", methods=["POST"])
        def api_start_recording():
            self._check_auth()
            data = request.json or {}
            self.macro_recorder.start_recording(data.get("name", "web_macro"))
            return jsonify({"success": True})

        @self.app.route("/api/stop_recording", methods=["POST"])
        def api_stop_recording():
            self._check_auth()
            self.macro_recorder.stop_recording()
            return jsonify({"success": True})

        @self.app.route("/screenshots/<filename>")
        def serve_screenshot(filename):
            self._check_auth()
            safe_name = Path(filename).name
            return send_from_directory(str(self.screen_capture.screenshot_dir), safe_name)

# ============================================================================
# MAIN APP
# ============================================================================

class AndroidAutomation:
    """Main orchestrator"""

    def __init__(self):
        self.db = Database()
        self.adb = ADBClient()
        self.device_manager = DeviceManager(self.adb, self.db)
        self.gesture = GestureController(self.adb, self.device_manager)
        self.screen_capture = ScreenCapture(self.adb, self.device_manager, self.db)
        self.vision = VisionProcessor(self.screen_capture)
        self.macro_recorder = MacroRecorder(self.db)
        self.performance_monitor = PerformanceMonitor(self.adb, self.device_manager)
        self.web_server = WebServer(self.db, self.device_manager, self.screen_capture, self.gesture, self.macro_recorder)

        self.gesture.set_recording_callback(self.macro_recorder.record_action)

    def list_devices(self):
        devices = self.device_manager.get_all_devices()
        print("\nConnected Devices")
        print("-" * 80)
        for device in devices:
            print(f"ID: {device['id']}")
            print(f"  Type: {device['type']}")
            print(f"  Model: {device['info'].get('model', 'Unknown')}")
            print(f"  Android: {device['info'].get('android_version', 'Unknown')}")
            print(f"  Battery: {device['info'].get('battery', 'Unknown')}%")
            print(f"  RAM: {device['info'].get('total_ram', 'Unknown')}")
            print()
        return devices

    def run_interactive(self):
        print("\n" + "=" * 70)
        print("📱 Android Automation Suite - Interactive Mode")
        print("=" * 70)
        print("""
Commands:
  devices                      - List all devices
  select <id>                  - Select a device
  screenshot                   - Take screenshot
  record <sec>                 - Record screen
  tap x y                      - Tap at coordinates
  double x y                   - Double tap
  long x y                     - Long press
  swipe x1 y1 x2 y2            - Swipe
  pinch x y in|out             - Pinch gesture
  text <msg>                   - Type text
  key <name>                   - Press key
  macro record <name>          - Start recording macro
  macro stop                   - Stop recording macro
  macro play <name>            - Play macro
  macro list                   - List macros
  install <apk>                - Install APK
  uninstall <package>          - Uninstall app
  start <pkg>                  - Start app
  stop <pkg>                   - Stop app
  find <image>                 - Find and tap element
  ocr                          - Detect text
  monitor <pkg> <sec>          - Monitor app performance
  wireless                     - Setup wireless ADB
  web [port]                   - Start web UI
  help                         - Show help
  exit                         - Exit
""")

        devices = self.device_manager.get_all_devices()
        if devices:
            self.device_manager.select_device(devices[0]["id"])
            print(f"Auto-selected device: {self.device_manager.active_device}")

        while True:
            try:
                raw = input(f"\n[{self.device_manager.active_device or 'no-device'}]> ").strip()
                if not raw:
                    continue

                cmd = raw.split()
                command = cmd[0].lower()

                if command == "exit":
                    break

                elif command == "devices":
                    self.list_devices()

                elif command == "select" and len(cmd) > 1:
                    self.device_manager.select_device(cmd[1])
                    print(f"✓ Selected: {cmd[1]}")

                elif command == "screenshot":
                    self.screen_capture.take_screenshot()

                elif command == "record":
                    duration = int(cmd[1]) if len(cmd) > 1 else 30
                    self.screen_capture.screen_record(duration=duration)

                elif command == "tap" and len(cmd) == 3:
                    self.gesture.tap(int(cmd[1]), int(cmd[2]))

                elif command == "double" and len(cmd) == 3:
                    self.gesture.double_tap(int(cmd[1]), int(cmd[2]))

                elif command == "long" and len(cmd) == 3:
                    self.gesture.long_press(int(cmd[1]), int(cmd[2]))

                elif command == "swipe" and len(cmd) == 5:
                    self.gesture.swipe(int(cmd[1]), int(cmd[2]), int(cmd[3]), int(cmd[4]))

                elif command == "pinch" and len(cmd) == 4:
                    self.gesture.pinch(int(cmd[1]), int(cmd[2]), direction=cmd[3])

                elif command == "text":
                    self.gesture.type_text(" ".join(cmd[1:]))

                elif command == "key" and len(cmd) > 1:
                    self.gesture.press_key(cmd[1])
                #
                elif command == "macro" and len(cmd) > 1:
                    if cmd[1] == "record" and len(cmd) > 2:
                        self.macro_recorder.start_recording(cmd[2])
                        print(f"🎬 Recording macro '{cmd[2]}'...")
                        print("Now run tap/swipe/text/etc commands.")
                        print("Use: macro stop")
                
                    elif cmd[1] == "stop":
                        if self.macro_recorder.stop_recording():
                            print("✓ Recording stopped")
                        else:
                            print("❌ No active recording")
                
                    elif cmd[1] == "play" and len(cmd) > 2:
                        self.macro_recorder.play_macro(cmd[2], self.gesture)
                
                    elif cmd[1] == "list":
                        macros = self.macro_recorder.list_macros()
                        print("\nSaved Macros:")
                        for m in macros:
                            print(f"  {m}")
                    else:
                        print("Usage: macro record|stop|play|list <name>")

                elif command == "install" and len(cmd) > 1:
                    success = self.adb.install(self.device_manager.active_device, cmd[1])
                    print("✓ Installed" if success else "❌ Install failed")

                elif command == "uninstall" and len(cmd) > 1:
                    success = self.adb.uninstall(self.device_manager.active_device, cmd[1])
                    print("✓ Uninstalled" if success else "❌ Uninstall failed")

                elif command == "start" and len(cmd) > 1:
                    self.adb.start_app(self.device_manager.active_device, cmd[1])

                elif command == "stop" and len(cmd) > 1:
                    self.adb.stop_app(self.device_manager.active_device, cmd[1])

                elif command == "find" and len(cmd) > 1:
                    self.vision.find_and_tap(cmd[1], self.gesture)

                elif command == "ocr":
                    self.vision.detect_text()

                elif command == "monitor" and len(cmd) > 2:
                    self.performance_monitor.monitor_app(cmd[1], int(cmd[2]))

                elif command == "wireless":
                    self.device_manager.wireless_setup()

                elif command == "web":
                    port = int(cmd[1]) if len(cmd) > 1 else 5000
                    def run_web():
                        self.web_server.start(port)
                    threading.Thread(target=run_web, daemon=True).start()

                elif command == "help":
                    print("Use the command list shown at startup.")

                else:
                    print(f"Unknown command: {command}")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
                logger.exception("Interactive command failed")

# ============================================================================
# CLI ENTRY
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Android Automation Suite")
    parser.add_argument("--devices", "-d", action="store_true", help="List devices")
    parser.add_argument("--device", help="Select specific device")
    parser.add_argument("--screenshot", "-s", action="store_true", help="Take screenshot")
    parser.add_argument("--record", "-r", type=int, help="Record screen in seconds")
    parser.add_argument("--tap", nargs=2, type=int, help="Tap at x y")
    parser.add_argument("--double-tap", nargs=2, type=int, help="Double tap at x y")
    parser.add_argument("--long-press", nargs=2, type=int, help="Long press at x y")
    parser.add_argument("--swipe", nargs=4, type=int, help="Swipe x1 y1 x2 y2")
    parser.add_argument("--text", help="Type text")
    parser.add_argument("--key", help="Press key")
    parser.add_argument("--install", help="Install APK")
    parser.add_argument("--uninstall", help="Uninstall package")
    parser.add_argument("--start", help="Start package")
    parser.add_argument("--stop", help="Stop package")
    parser.add_argument("--find-image", help="Find and tap image template")
    parser.add_argument("--ocr", action="store_true", help="OCR current screen")
    parser.add_argument("--monitor-perf", nargs=2, help="Monitor app performance: package duration")
    parser.add_argument("--macro-record", help="Record macro")
    parser.add_argument("--macro-play", help="Play macro")
    parser.add_argument("--macro-list", action="store_true", help="List macros")
    parser.add_argument("--wireless", action="store_true", help="Setup wireless ADB")
    parser.add_argument("--web", nargs="?", const=5000, type=int, help="Start web UI")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")

    args = parser.parse_args()
    app = AndroidAutomation()

    if args.interactive:
        app.run_interactive()
        return

    if args.devices:
        app.list_devices()
        return

    if args.device:
        app.device_manager.select_device(args.device)
    else:
        devices = app.device_manager.get_all_devices()
        if devices:
            app.device_manager.select_device(devices[0]["id"])
        else:
            print("❌ No devices found")
            return

    if args.wireless:
        app.device_manager.wireless_setup()
        return

    if args.web:
        app.web_server.start(args.web)
        return

    if args.macro_list:
        macros = app.macro_recorder.list_macros()
        print("\nSaved Macros:")
        for m in macros:
            print(f"  {m}")
        return

    if args.macro_record:
        app.macro_recorder.start_recording(args.macro_record)
        print("Recording... Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            app.macro_recorder.stop_recording()
        return

    if args.macro_play:
        app.macro_recorder.play_macro(args.macro_play, app.gesture)
        return

    if args.screenshot:
        app.screen_capture.take_screenshot()

    if args.record:
        app.screen_capture.screen_record(duration=args.record)

    if args.tap:
        app.gesture.tap(args.tap[0], args.tap[1])

    if args.double_tap:
        app.gesture.double_tap(args.double_tap[0], args.double_tap[1])

    if args.long_press:
        app.gesture.long_press(args.long_press[0], args.long_press[1])

    if args.swipe:
        app.gesture.swipe(args.swipe[0], args.swipe[1], args.swipe[2], args.swipe[3])

    if args.text:
        app.gesture.type_text(args.text)

    if args.key:
        app.gesture.press_key(args.key)

    if args.install:
        success = app.adb.install(app.device_manager.active_device, args.install)
        print("✓ Installed" if success else "❌ Install failed")

    if args.uninstall:
        success = app.adb.uninstall(app.device_manager.active_device, args.uninstall)
        print("✓ Uninstalled" if success else "❌ Uninstall failed")

    if args.start:
        app.adb.start_app(app.device_manager.active_device, args.start)

    if args.stop:
        app.adb.stop_app(app.device_manager.active_device, args.stop)

    if args.find_image:
        app.vision.find_and_tap(args.find_image, app.gesture)

    if args.ocr:
        app.vision.detect_text()

    if args.monitor_perf:
        package, duration = args.monitor_perf
        app.performance_monitor.monitor_app(package, int(duration))

if __name__ == "__main__":
    main()
