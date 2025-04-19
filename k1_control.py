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

def upload_file(ip, local_file_path):
    import os
    import sys
    import requests
    from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

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

        # Progress bar callback
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

# --- MAIN FUNCTION ---
def live_status(ws_url):
    def draw_screen(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.clear()
        if curses.has_colors():
            curses.start_color()

        height, width = stdscr.getmaxyx()
        fixed_info_height = 12  # Height for the fixed info window
        log_height = height - fixed_info_height
        if log_height < 3:
            fixed_info_height = max(1, height - 3)
            log_height = height - fixed_info_height
            if log_height < 3 or fixed_info_height < 3:
                print("Terminal too small for all windows.")
                return

        fixed_info_win = curses.newwin(fixed_info_height, width, 0, 0)
        log_win = curses.newwin(log_height, width, fixed_info_height, 0)

        log_win.scrollok(True)
        log_win.idlok(True)

        stdscr.refresh()
        fixed_info_win.box()
        safe_addstr(fixed_info_win, 0, 2, " Printer Status ")
        fixed_info_win.refresh()
        log_win.box()
        safe_addstr(log_win, 0, 2, " Logs ")
        log_win.refresh()

        raw_info_cache = {
            "Total Layers": None,
            "Current Layer": None,
            "Nozzle Temp": None,
            "Bed Temp": None,
            "Progress": None,
            "Position": None,
            "Print Time": None,
            "Time Left": None,
        }
        formatted_info = {key: "N/A" for key in raw_info_cache}
        previous_formatted_info = {}
        needs_redraw_fixed = True

        ws = None
        try:
            ws = create_connection(ws_url, timeout=10)
            needs_redraw_fixed = True
        except Exception as e:
            curses.flash()
            stdscr.clear()
            safe_addstr(stdscr, 0, 0, f"Connection error: {e}. Press any key to exit.")
            stdscr.refresh()
            stdscr.nodelay(0)
            stdscr.getch()
            return

        # --- Main Loop ---
        while True:
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == curses.KEY_RESIZE:
                height, width = stdscr.getmaxyx()
                fixed_info_height = 12
                log_height = height - fixed_info_height
                if log_height < 3:
                    fixed_info_height = max(1, height - 3)
                    log_height = height - fixed_info_height
                try:
                    fixed_info_win.resize(fixed_info_height, width)
                    log_win.resize(log_height, width)
                    log_win.mvwin(fixed_info_height, 0)
                    stdscr.clear()
                    stdscr.refresh()
                    fixed_info_win.box()
                    safe_addstr(fixed_info_win, 0, 2, " Printer Status ")
                    log_win.box()
                    safe_addstr(log_win, 0, 2, " Logs ")
                    needs_redraw_fixed = True
                    log_win.refresh()
                except curses.error:
                    pass
                continue

            # --- WebSocket Message Handling ---
            log_entry_to_add = None
            try:
                msg = ws.recv()
                if msg:
                    try:
                        data = json.loads(msg)
                        log_entry_to_add = msg
                    except json.JSONDecodeError:
                        log_entry_to_add = f"Malformed JSON: {msg}"
                        data = None
                    if data:
                        raw_info_cache["Total Layers"] = data.get("TotalLayer", raw_info_cache["Total Layers"])
                        raw_info_cache["Current Layer"] = data.get("layer", raw_info_cache["Current Layer"])
                        raw_info_cache["Nozzle Temp"] = data.get("nozzleTemp", raw_info_cache["Nozzle Temp"])
                        raw_info_cache["Bed Temp"] = data.get("bedTemp0", raw_info_cache["Bed Temp"])
                        raw_info_cache["Progress"] = data.get("printProgress", raw_info_cache["Progress"])
                        raw_info_cache["Position"] = data.get("curPosition", raw_info_cache["Position"])
                        raw_info_cache["Print Time"] = data.get("printJobTime", raw_info_cache["Print Time"])
                        raw_info_cache["Time Left"] = data.get("printLeftTime", raw_info_cache["Time Left"])
                        formatted_info = {
                            "Total Layers": raw_info_cache["Total Layers"] if raw_info_cache["Total Layers"] is not None else "N/A",
                            "Current Layer": raw_info_cache["Current Layer"] if raw_info_cache["Current Layer"] is not None else "N/A",
                            "Nozzle Temp": f"{float(raw_info_cache['Nozzle Temp']):.2f}°C" if raw_info_cache["Nozzle Temp"] is not None else "N/A",
                            "Bed Temp": f"{float(raw_info_cache['Bed Temp']):.2f}°C" if raw_info_cache["Bed Temp"] is not None else "N/A",
                            "Progress": f"{raw_info_cache['Progress']}%" if raw_info_cache["Progress"] is not None else "N/A",
                            "Position": raw_info_cache["Position"] if raw_info_cache["Position"] else "N/A",
                            "Print Time": (
                                f"{int(raw_info_cache['Print Time'] // 3600):02}:{int((raw_info_cache['Print Time'] % 3600) // 60):02}:{int(raw_info_cache['Print Time'] % 60):02}"
                                if raw_info_cache["Print Time"] is not None
                                else "N/A"
                            ),
                            "Time Left": (
                                f"{int(raw_info_cache['Time Left'] // 3600):02}:{int((raw_info_cache['Time Left'] % 3600) // 60):02}:{int(raw_info_cache['Time Left'] % 60):02}"
                                if raw_info_cache["Time Left"] is not None
                                else "N/A"
                            ),
                        }
                        if formatted_info != previous_formatted_info:
                            needs_redraw_fixed = True
                            previous_formatted_info = formatted_info.copy()
            except KeyboardInterrupt:
                safe_addstr(fixed_info_win, 2, 1, " " * (width - 2))
                safe_addstr(fixed_info_win, 2, 1, " Stopping...")
                fixed_info_win.refresh()
                time.sleep(0.5)
                break
            except Exception as e:
                log_entry_to_add = f"WebSocket/Other Error: {e}"
                time.sleep(1)

            # --- Drawing Phase ---
            if needs_redraw_fixed:
                max_h_fixed, max_w_fixed = fixed_info_win.getmaxyx()
                status_line_y = 2
                safe_addstr(fixed_info_win, status_line_y, 1, " " * (max_w_fixed - 2))
                safe_addstr(fixed_info_win, status_line_y, 2, "Status: Connected", max_w_fixed - 3)
                data_start_y = 3
                value_start_col = 18
                for i, (key, value) in enumerate(formatted_info.items()):
                    data_line_y = i + data_start_y
                    if data_line_y < (max_h_fixed - 1):
                        label_text = f"{key}:"
                        safe_addstr(fixed_info_win, data_line_y, 1, " " * (max_w_fixed - 2))
                        safe_addstr(fixed_info_win, data_line_y, 2, label_text)
                        if value_start_col < max_w_fixed - 1:
                            safe_addstr(fixed_info_win, data_line_y, value_start_col, value, max_w_fixed - value_start_col - 1)
                    else:
                        break
                fixed_info_win.refresh()
                needs_redraw_fixed = False

            if log_entry_to_add:
                current_log_h, current_log_w = log_win.getmaxyx()
                if current_log_h >= 3 and current_log_w >= 4:
                    log_win.scroll(1)
                    add_y = current_log_h - 2
                    add_x = 1
                    try:
                        log_win.move(add_y, 0)
                        log_win.clrtoeol()
                    except curses.error:
                        pass
                    display_line = log_entry_to_add[:current_log_w - 2]
                    safe_addstr(log_win, add_y, add_x, display_line)
                    log_win.box()
                    safe_addstr(log_win, 0, 2, " Logs ")
                    log_win.refresh()
                log_entry_to_add = None

            curses.napms(50)

        if ws and ws.connected:
            ws.close()

    try:
        curses.wrapper(draw_screen)
        print("Program exited.")
    except curses.error as e:
        print(f"Curses error: {e}")
        print("Check your terminal settings.")
    except Exception as e:
        print(f"Unexpected error: {e}")

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
                layer_height = float(parts[3])
                timestamp = int(parts[4])
                filament_mm = int(parts[5])
                size_mb = size_bytes / 1048576 # Calculate MB here for filtering

                if filter_keyword and filter_keyword.lower() not in name.lower():
                    continue
                # Corrected logic: delete if size is GREATER than delete_over_size
                if delete_over_size is not None and size_mb <= delete_over_size:
                    continue

                # If delete_mode is active due to --delete-larger, ensure we only add files matching the size criteria
                if delete_mode and delete_over_size is not None and size_mb <= delete_over_size:
                     continue # Skip if we are in delete mode for larger files but this one is not larger

                results.append((path, name, size_bytes, layer_height, timestamp, filament_mm))

        # Sort the results based on the specified criteria
        if sort_by == "size":
            results.sort(key=lambda x: x[2], reverse=True)
        elif sort_by == "time":
            results.sort(key=lambda x: x[4], reverse=True)
        else:
            results.sort(key=lambda x: x[1].lower())

        # Display the results and optionally delete files
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


            # Only prompt for deletion confirmation in delete mode
            if delete_mode:
                if not force:
                    confirm = input("\nDelete these files? [y/N]: ").strip().lower()
                    if confirm != "y":
                        print("Aborted.")
                        ws.close()
                        return
                print("\nDeleting files...")
                for path, name, size_bytes, *_ in results:  # Adjusted to handle extra values
                    delete_file(ws_url, path, name)
                    time.sleep(0.3)
                print("Done.")
        else:
            print("No matching files found.")

        ws.close()
    except Exception as e:
        print("Connection error:", e)

def fetch_photo2(ip):
    import requests
    from PIL import Image
    from io import BytesIO
    import numpy as np
    import shutil  # To get terminal size

    url = f"http://{ip}:8080/?action=snapshot"
    try:
        print("Fetching photo from printer...")
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Raise an exception if the HTTP status code indicates an error

        # Load the image
        img = Image.open(BytesIO(response.content))

        # Get terminal dimensions
        terminal_size = shutil.get_terminal_size((80, 24))  # Default to 80x24 if size cannot be determined
        terminal_width = terminal_size.columns
        terminal_height = terminal_size.lines

        # Calculate the image dimensions
        img_width = terminal_width
        img_height = int((img_width * 9 / 16) / 2)  # Adjust height for ANSI pixel aspect ratio (half height)

        # Resize the image to fit the terminal
        img = img.resize((img_width, img_height))
        img = img.convert("RGB")  # Ensure the image is in RGB format

        # Convert the image to a NumPy array
        img_array = np.array(img)

        # ANSI escape codes for RGB colors
        for row in img_array:
            for pixel in row:
                r, g, b = pixel
                print(f"\033[48;2;{r};{g};{b}m ", end="")
            print("\033[0m")  # Reset at the end of each row
    except requests.exceptions.RequestException as e:
        print(f"Error fetching photo: {e}")
    except Exception as e:
        print(f"Error processing photo: {e}")

def fetch_video(ip, interval=0.5):
    import requests
    from PIL import Image
    from io import BytesIO
    import numpy as np
    import shutil
    import time
    import sys

    url = f"http://{ip}:8080/?action=snapshot"
    try:
        first_frame = True
        img_height = 0  # Initialwert
        while True:
            # Hole aktuelle Terminalgröße für jedes Frame
            terminal_size = shutil.get_terminal_size((80, 24))
            img_width = terminal_size.columns
            img_height = int((img_width * 9 / 16) / 2)

            # Cursor nur bewegen, wenn nicht das erste Frame
            if not first_frame:
                sys.stdout.write(f"\033[{img_height}A")
            else:
                first_frame = False

            # Fetch the video frame
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            img = Image.open(BytesIO(response.content))
            img = img.resize((img_width, img_height))
            img = img.convert("RGB")
            img_array = np.array(img)

            buffer = []
            for row in img_array:
                line = ""
                for pixel in row:
                    r, g, b = pixel
                    line += f"\033[48;2;{r};{g};{b}m "
                line += "\033[0m"
                buffer.append(line)

            print("\n".join(buffer), end="", flush=True)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nVideo stream stopped.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching video frame: {e}")
    except Exception as e:
        print(f"Error processing video frame: {e}")

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
    parser.add_argument("--video", action="store_true", help="Fetch and display a video stream from the printer's camera (updates every 5 seconds)")
    parser.add_argument("--interval", type=float, default=0.5, help="Interval in seconds between video frames (default: 0.5)")
    args = parser.parse_args()

    ip = args.ip or get_default_ip()
    if not ip:
        print("Error: No IP address provided and no default IP found in config.json.")
        exit(1)

    ws_url = f"ws://{ip}:9999/websocket"

    default_gcode_path = "/usr/data/printer_data/gcodes/"

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
        fetch_video(ip, interval=args.interval)  # Pass the interval argument
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
