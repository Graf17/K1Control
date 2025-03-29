#!/usr/bin/env python3
import argparse
import json
import time
import os
import re
import sys  # For progress display
from io import BytesIO

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

def start_print(ws_url, filepath, countdown_minutes=1):
    # Extract the filename from the provided filepath
    filename = os.path.basename(filepath)

    # Check if the file exists on the printer
    print(f"Checking if the file '{filename}' exists on the printer...")
    file_exists = False
    try:
        # Use list_files to retrieve the list of files on the printer
        payload = {
            "method": "get",
            "params": {
                "reqGcodeFile": 1
            }
        }
        ws = create_connection(ws_url, timeout=5)
        ws.send(json.dumps(payload))
        start_time = time.time()

        # Wait for the file list response
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

        # Check if the filename exists in the file list
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

    # Start the countdown if the file exists
    countdown_seconds = countdown_minutes * 60
    print(f"Starting print in {countdown_minutes} minute(s)...")

    # Display a countdown timer with a progress bar
    for remaining in range(countdown_seconds, 0, -1):
        minutes, seconds = divmod(remaining, 60)
        progress = int((countdown_seconds - remaining) / countdown_seconds * 50)  # Progress bar (50 characters)
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

def delete_file(ws_url, path, name):
    # Send a command to delete a specific file on the printer
    payload = {
        "method": "set",
        "params": {
            "opGcodeFile": f"deleteprt:{path}/{name}"
        }
    }
    send_ws_command(ws_url, payload, expect_response=False, silent=True)

def live_status(ws_url):
    try:
        ws = create_connection(ws_url, timeout=5)
        print("Connected. Listening for live status updates (Ctrl+C to stop)...")

        # Continuously listen for status updates until interrupted
        while True:
            try:
                msg = ws.recv()
                if msg:
                    print("Status:", msg)
            except KeyboardInterrupt:
                print("Stopped.")
                break
            except:
                continue

        ws.close()
    except Exception as e:
        print("Connection error:", e)

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

        # Wait for the file list response
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

        # Parse and filter the file list
        for entry in entries:
            if not entry:
                continue
            parts = entry.split(':')
            if len(parts) >= 6:
                path = parts[0]
                name = parts[1]
                size_bytes = int(parts[2])
                size_mb = round(size_bytes / 1048576, 2)

                if filter_keyword and filter_keyword.lower() not in name.lower():
                    continue
                if delete_over_size and size_mb <= delete_over_size:
                    continue

                results.append((path, name, size_mb))
                total_size += size_mb

        # Sort the results based on the specified criteria
        if sort_by == "size":
            results.sort(key=lambda x: x[2], reverse=True)
        else:
            results.sort(key=lambda x: x[1].lower())

        # Display the results and optionally delete files
        if results:
            print("\nMatching files:")
            for _, name, size in results:
                print(f"{size:>6} MB {name:<60}")
            print(f"\nTotal size: {round(total_size, 2)} MB")

            # Only prompt for deletion confirmation in delete mode
            if delete_mode:
                if not force:
                    confirm = input("\nDelete these files? [y/N]: ").strip().lower()
                    if confirm != "y":
                        print("Aborted.")
                        ws.close()
                        return
                print("\nDeleting files...")
                for path, name, _ in results:
                    delete_file(ws_url, path, name)
                    time.sleep(0.3)
                print("Done.")
        else:
            print("No matching files found.")

        ws.close()
    except Exception as e:
        print("Connection error:", e)

def fetch_photo(ip):
    url = f"http://{ip}:8080/?action=snapshot"
    try:
        print("Fetching photo from printer...")
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Raise an exception if the HTTP status code indicates an error

        # Convert the image to grayscale
        img = Image.open(BytesIO(response.content))
        img = img.convert("L")  # Convert to grayscale
        img = img.resize((80, 22))  # Resize for terminal display

        # Map grayscale intensity to characters for terminal output
        grayscale_chars = " ░▒▓█"  # From light (space) to dark (█)
        output = ""
        for y in range(img.height):
            for x in range(img.width):
                gray = img.getpixel((x, y))
                output += grayscale_chars[gray * len(grayscale_chars) // 256]
            output += "\n"

        print(output)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching photo: {e}")
    except Exception as e:
        print(f"Error processing photo: {e}")

def main():
    parser = argparse.ArgumentParser(description="Creality K1 printer WebSocket/HTTP control tool")
    parser.add_argument("--ip", required=True, help="IP address of the printer")
    parser.add_argument("--start-file", metavar="FILENAME", help="Start print with filename")
    parser.add_argument("--countdown", type=int, default=1, help="Countdown in minutes before starting the print (default: 1)")
    parser.add_argument("--pause", action="store_true", help="Pause the current print")
    parser.add_argument("--resume", action="store_true", help="Resume the current print after pausing")
    parser.add_argument("--stop", action="store_true", help="Stop current print")
    parser.add_argument("--list-files", metavar="KEYWORD", nargs="?", const="", help="List GCODE files with optional keyword filter")
    parser.add_argument("--sort", choices=["name", "size"], default="name", help="Sort list by 'name' or 'size'")
    parser.add_argument("--delete-files", metavar="KEYWORD", nargs="?", const="", help="Delete files matching keyword")
    parser.add_argument("--delete-larger", type=float, help="Delete files larger than given size (in MB)")
    parser.add_argument("--force", action="store_true", help="Delete files without confirmation")
    parser.add_argument("--status", action="store_true", help="Show live status updates")
    parser.add_argument("--photo", action="store_true", help="Fetch and display a photo from the printer's camera")

    args = parser.parse_args()
    ws_url = f"ws://{args.ip}:9999/websocket"

    default_gcode_path = "/usr/data/printer_data/gcodes/"

    
    # Handle the command-line arguments and execute the corresponding function
    if args.start_file:
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
        list_files(ws_url, delete_over_size=args.delete_larger, sort_by=args.sort, force=args.force)
    elif args.status:
        live_status(ws_url)
    elif args.photo:
        fetch_photo(args.ip)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
