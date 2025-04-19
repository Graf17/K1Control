# Overview: --upload-file, --start-file, --list-files, --delete-files, --delete-larger, --sort, --force
from websocket import create_connection
import requests
import json
import time
from datetime import datetime
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
import os
import sys

def upload_file(ip, local_file_path):
    def is_valid_gcode(path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(10):
                    line = f.readline().strip().lower()
                    if not line:
                        continue
                    if line.startswith(("g", "m", ";", "t", "start", "end", "init")):
                        return True
            return False
        except Exception as e:
            print(f"Warning: Could not read file: {e}")
            return False

    if not os.path.isfile(local_file_path):
        print(f"Error: File not found: {local_file_path}")
        return

    filename = os.path.basename(local_file_path)

    if not filename.lower().endswith(".gcode"):
        print("Error: File does not have a .gcode extension.")
        return

    if not is_valid_gcode(local_file_path):
        print("Error: File does not appear to be valid G-code.")
        return

    url = f"http://{ip}/upload/{filename}"
    file_size = os.path.getsize(local_file_path)

    print(f"Uploading '{filename}' to {url}...")

    with open(local_file_path, 'rb') as file_data:
        encoder = MultipartEncoder(
            fields={
                "file": (filename, file_data, "text/x.gcode")
            },
            boundary="----WebKitFormBoundaryMSFQsbe7RlEsWyBy"
        )

        def progress_callback(monitor):
            uploaded = monitor.bytes_read
            progress = int(uploaded / monitor.len * 50)
            bar = f"{'█' * progress}{'░' * (50 - progress)}"
            percent = int((uploaded / monitor.len) * 100)
            sys.stdout.write(f"\r{bar} {percent:3d}%")
            sys.stdout.flush()

        monitor = MultipartEncoderMonitor(encoder, progress_callback)

        headers = {
            "Content-Type": monitor.content_type,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": f"http://{ip}",
            "Referer": f"http://{ip}/",
        }

        response = requests.post(url, data=monitor, headers=headers)

    print()  # newline after progress bar

    if response.status_code == 200:
        try:
            data = response.json()
            if data.get("code") == 200:
                print("Upload successful.")
            else:
                print("Upload failed with response:", data)
        except Exception as e:
            print("Upload succeeded, but response was not valid JSON:", e)
            print("Raw response:", response.text)
    else:
        print(f"Upload failed with status code {response.status_code}")
        print("Response:", response.text)

def extract_fileinfo_field(message):
    try:
        parsed = json.loads(message)
        if "retGcodeFileInfo" in parsed:
            info = parsed["retGcodeFileInfo"].get("fileInfo", "")
            return info
    except:
        pass
    return None

def delete_file(ws_url, path, name):
    payload = {
        "method": "set",
        "params": {
            "opGcodeFile": f"deleteprt:{path}/{name}"
        }
    }
    send_ws_command(ws_url, payload, expect_response=False, silent=True)

def send_ws_command(ws_url, payload, expect_response=True, timeout=5, silent=False):
    try:
        ws = create_connection(ws_url, timeout=timeout)
        if not silent:
            print("Connected to printer.")

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

def list_files(ws_url, filter_keyword=None, sort_by="name", delete_over_size=None, force=False, delete_mode=False):
    payload = {
        "method": "get",
        "params": {
            "reqGcodeFile": 1
        }
    }
    try:
        ws = create_connection(ws_url, timeout=5)
        print("Connected to printer.")
        ws.send(json.dumps(payload))
        print("Requested file list, waiting for response...")

        file_info = None
        start_time = time.time()

        while time.time() - start_time < 10:
            try:
                msg = ws.recv()
                file_info = extract_fileinfo_field(msg)
                if file_info:
                    break
            except Exception:
                continue

        if not file_info:
            print("No file list received within timeout.")
            ws.close()
            return

        entries = file_info.split(';')
        total_size = 0
        results = []

        for entry in entries:
            if not entry:
                continue
            parts = entry.split(':')
            if len(parts) >= 6:
                path = parts[0]
                name = parts[1]
                size_bytes = int(parts[2])
                layer_height = float(parts[3])
                timestamp = int(parts[4])
                filament_mm = int(parts[5])
                size_mb = size_bytes / 1048576

                if filter_keyword and filter_keyword.lower() not in name.lower():
                    continue
                if delete_over_size is not None and size_mb <= delete_over_size:
                    continue
                if delete_mode and delete_over_size is not None and size_mb <= delete_over_size:
                    continue

                results.append((path, name, size_bytes, layer_height, timestamp, filament_mm))

        if sort_by == "size":
            results.sort(key=lambda x: x[2], reverse=True)
        elif sort_by == "time":
            results.sort(key=lambda x: x[4], reverse=True)
        else:
            results.sort(key=lambda x: x[1].lower())

        if results:
            print("\nMatching files:\n")
            print(f"{'Time':<20}   {'Size':<8}   Name")
            print(f"{'-'*20}   {'-'*8}   {'-'*40}")

            for path, name, size_bytes, layer_height, timestamp, filament_mm in results:
                size_mb = round(size_bytes / 1048576, 2)
                dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                print(f"{dt}   {size_mb:6.2f} MB   {name}")
            print()
            total_size_mb = sum(entry[2] for entry in results) / 1048576
            print(f"Total size: {total_size_mb:.2f} MB")

            if delete_mode:
                if not force:
                    confirm = input("\nDelete these files? [y/N]: ").strip().lower()
                    if confirm != "y":
                        print("Aborted.")
                        ws.close()
                        return
                print("\nDeleting files...")
                for path, name, size_bytes, *_ in results:
                    delete_file(ws_url, path, name)
                    time.sleep(0.3)
                print("Done.")
        else:
            print("No matching files found.")

        ws.close()
    except Exception as e:
        print("Connection error:", e)

def start_print(ws_url, filepath, countdown_minutes=1):
    filename = os.path.basename(filepath)
    print(f"Checking if the file '{filename}' exists on the printer...")
    file_exists = False
    try:
        payload = {
            "method": "get",
            "params": {
                "reqGcodeFile": 1
            }
        }
        ws = create_connection(ws_url, timeout=5)
        ws.send(json.dumps(payload))
        start_time = time.time()

        file_info = None
        while time.time() - start_time < 10:
            try:
                msg = ws.recv()
                file_info = extract_fileinfo_field(msg)
                if file_info:
                    break
            except Exception:
                continue

        ws.close()

        if not file_info:
            print("Error: Could not retrieve the file list from the printer.")
            return

        entries = file_info.split(';')
        for entry in entries:
            if not entry:
                continue
            parts = entry.split(':')
            if len(parts) >= 6:
                name = parts[1]
                if name == filename:
                    file_exists = True
                    break

    except Exception as e:
        print(f"Error while checking file existence: {e}")
        return

    if not file_exists:
        print(f"Error: The file '{filename}' does not exist on the printer.")
        print("Please upload the file to the printer and try again.")
        return

    countdown_seconds = countdown_minutes * 60
    print(f"Starting print in {countdown_minutes} minute(s)...")

    for remaining in range(countdown_seconds, 0, -1):
        minutes, seconds = divmod(remaining, 60)
        progress = int((countdown_seconds - remaining) / countdown_seconds * 50)
        bar = f"{'█' * progress}{'░' * (50 - progress)}"
        sys.stdout.write(f"\r{bar} {minutes:02}:{seconds:02} remaining...")
        sys.stdout.flush()
        time.sleep(1)

    print("\nCountdown finished. Sending print command...")
    payload = {
        "method": "set",
        "params": {
            "opGcodeFile": f"printprt:{filepath}"
        }
    }
    send_ws_command(ws_url, payload)
