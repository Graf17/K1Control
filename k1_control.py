#!/usr/bin/env python3
import argparse
import json
import time
import os
import re
import sys  # For progress display
from io import BytesIO
import curses
from datetime import datetime

# Check for required dependencies
def check_dependencies():
    missing_modules = []

    try:
        from websocket import create_connection
    except ModuleNotFoundError:
        missing_modules.append("websocket-client")

    try:
        import requests
    except ModuleNotFoundError:
        missing_modules.append("requests")

    try:
        from PIL import Image
    except ModuleNotFoundError:
        missing_modules.append("pillow")

    try:
        import curses
    except ModuleNotFoundError:
        missing_modules.append("windows-curses")  # For Windows compatibility

    try:
        import numpy
    except ModuleNotFoundError:
        missing_modules.append("numpy")

    try:
        from requests_toolbelt import MultipartEncoder
    except ModuleNotFoundError:
        missing_modules.append("requests-toolbelt")

    if missing_modules:
        print("The following required modules are not installed:")
        for module in missing_modules:
            print(f"   - {module}")
        print("Please install them with:")
        print(f"    pip install {' '.join(missing_modules)}")
        sys.exit(1)

# Run the dependency check
check_dependencies()

# Import the modules after the dependency check
from websocket import create_connection
import requests
from PIL import Image
from media import fetch_photo2, fetch_video
from fileops import upload_file, list_files, delete_file, start_print
from status import live_status

def get_default_ip():
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
            return config.get("default_ip")
    return None

def send_ws_command(ws_url, payload, expect_response=True, timeout=5, silent=False):
    try:
        ws = create_connection(ws_url, timeout=timeout)
        if not silent:
            print("Connected to printer.")

        # Clear any initial messages from the WebSocket buffer
        start_time = time.time()
        while time.time() - start_time < 2:
            try:
                msg = ws.recv()
                if msg.strip() and not silent:
                    print("Received:", msg)
            except:
                break

        if not silent:
            print("Sending command...")
        ws.send(json.dumps(payload))

        # Wait for and print the response if expected
        if expect_response:
            try:
                response = ws.recv()
                if not silent:
                    print("Response:", response)
            except:
                if not silent:
                    print("No response received.")
        ws.close()
    except Exception as e:
        if not silent:
            print("Connection error:", e)

def pause_print(ws_url):
    # Send a command to pause the current print
    payload = {
        "method": "set",
        "params": {
            "pause": 1
        }
    }
    send_ws_command(ws_url, payload)

def resume_print(ws_url):
    # Send a command to resume the current print
    payload = {
        "method": "set",
        "params": {
            "pause": 0
        }
    }
    send_ws_command(ws_url, payload)

def stop_print(ws_url):
    # Send a command to stop the current print
    payload = {
        "method": "set",
        "params": {
            "stop": 1
        }
    }
    send_ws_command(ws_url, payload)

# --- HELPER FUNCTION: Safely add strings to curses windows ---
def safe_addstr(win, y, x, text, width_limit=0):
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0:
            return
        effective_limit = w - x
        if width_limit > 0:
            effective_limit = min(effective_limit, width_limit)
        if effective_limit <= 0:
            return
        text_str = str(text) if text is not None else ""
        win.addstr(y, x, text_str[:effective_limit])
    except curses.error:
        pass

def extract_fileinfo_field(message):
    # Extract the file information field from a JSON message
    try:
        parsed = json.loads(message)
        if "retGcodeFileInfo" in parsed:
            info = parsed["retGcodeFileInfo"].get("fileInfo", "")
            return info
    except:
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Creality K1 printer WebSocket/HTTP control tool")
    parser.add_argument("--ip", help="IP address of the printer")
    parser.add_argument("--upload-file", metavar="LOCALFILE", help="Upload a local GCODE file to the printer")
    parser.add_argument("--start-file", metavar="FILENAME", help="Start print with filename")
    parser.add_argument("--countdown", type=int, default=1, help="Countdown in minutes before starting the print (default: 1)")
    parser.add_argument("--pause", action="store_true", help="Pause the current print")
    parser.add_argument("--resume", action="store_true", help="Resume the current print after pausing")
    parser.add_argument("--stop", action="store_true", help="Stop current print")
    parser.add_argument("--list-files", metavar="KEYWORD", nargs="?", const="", help="List GCODE files with optional keyword filter")
    parser.add_argument("--sort", choices=["name", "size", "time"], default="name", help="Sort list by 'name', 'size' or 'time'")
    parser.add_argument("--delete-files", metavar="KEYWORD", nargs="?", const="", help="Delete files matching keyword")
    parser.add_argument("--delete-larger", type=float, help="Delete files larger than given size (in MB)")
    parser.add_argument("--force", action="store_true", help="Delete files without confirmation")
    parser.add_argument("--status", action="store_true", help="Show live status updates")
    parser.add_argument("--photo", action="store_true", help="Fetch and display a photo from the printer's camera using ANSI colors")
    parser.add_argument("--video", action="store_true", help="Fetch and display a video stream from the printer's camera (updates at the given interval)")
    parser.add_argument("--highres", action="store_true", help="Use Unicode half-blocks for higher vertical resolution in video mode")
    parser.add_argument("--interval", type=float, default=0.5, help="Interval in seconds between video frames (default: 0.5)")
    args = parser.parse_args()

    ip = args.ip or get_default_ip()
    if not ip:
        print("Error: No IP address provided and no default IP found in config.json.")
        exit(1)

    ws_url = f"ws://{ip}:9999/websocket"

    default_gcode_path = "/usr/data/printer_data/gcodes/"

    # Overview of command-line arguments:
    # --ip, --upload-file, --start-file, --countdown, --pause, --resume, --stop,
    # --list-files, --sort, --delete-files, --delete-larger, --force,
    # --status, --photo, --video, --interval

    # Handle the command-line arguments and execute the corresponding function
    if args.upload_file:
        upload_file(ip, args.upload_file)
    elif args.start_file:
        start_print(ws_url, default_gcode_path + args.start_file, countdown_minutes=args.countdown)
    elif args.pause:
        pause_print(ws_url)
    elif args.resume:
        resume_print(ws_url)
    elif args.stop:
        stop_print(ws_url)
    elif args.list_files is not None:
        list_files(ws_url, filter_keyword=args.list_files, sort_by=args.sort)
    elif args.delete_files is not None:
        list_files(ws_url, filter_keyword=args.delete_files, sort_by=args.sort, force=args.force, delete_mode=True)
    elif args.delete_larger:
        # Pass delete_mode=True and the size limit for deletion
        list_files(ws_url, delete_over_size=args.delete_larger, sort_by=args.sort, force=args.force, delete_mode=True)
    elif args.status:
        live_status(ws_url)
    elif args.photo:
        fetch_photo2(ip)  # Use the updated photo display function
    elif args.video:
        fetch_video(ip, interval=args.interval, highres=args.highres)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
