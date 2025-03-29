#!/usr/bin/env python3
import argparse
import json
import time
import os
import requests
from websocket import create_connection
import re

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

def start_print(ws_url, filepath):
    payload = {
        "method": "set",
        "params": {
            "opGcodeFile": f"printprt:{filepath}"
        }
    }
    send_ws_command(ws_url, payload)

def pause_print(ws_url):
    payload = {
        "method": "set",
        "params": {
            "pause": 1
        }
    }
    send_ws_command(ws_url, payload)

def stop_print(ws_url):
    payload = {
        "method": "set",
        "params": {
            "stop": 1
        }
    }
    send_ws_command(ws_url, payload)

def delete_file(ws_url, path, name):
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
    try:
        parsed = json.loads(message)
        if "retGcodeFileInfo" in parsed:
            info = parsed["retGcodeFileInfo"].get("fileInfo", "")
            return info
    except:
        pass
    return None

def list_files(ws_url, filter_keyword=None, sort_by="name", delete_over_size=None, force=False):
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
                size_mb = round(size_bytes / 1048576, 2)

                if filter_keyword and filter_keyword.lower() not in name.lower():
                    continue
                if delete_over_size and size_mb <= delete_over_size:
                    continue

                results.append((path, name, size_mb))
                total_size += size_mb

        if sort_by == "size":
            results.sort(key=lambda x: x[2], reverse=True)
        else:
            results.sort(key=lambda x: x[1].lower())

        if results:
            print("\nMatching files:")
            for _, name, size in results:
                print(f"{size:>6} MB {name:<60}")
            print(f"\nTotal size: {round(total_size, 2)} MB")

            if delete_over_size is not None or filter_keyword is not None:
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

def main():
    parser = argparse.ArgumentParser(description="Creality K1 printer WebSocket/HTTP control tool")
    parser.add_argument("--ip", required=True, help="IP address of the printer")
    parser.add_argument("--start-file", metavar="FILENAME", help="Start print with filename")
    parser.add_argument("--pause", action="store_true", help="Pause the current print")
    parser.add_argument("--stop", action="store_true", help="Stop current print")
    parser.add_argument("--list", action="store_true", help="Request file list from printer")
    parser.add_argument("--list-files", metavar="KEYWORD", nargs="?", const="", help="List GCODE files with optional keyword filter")
    parser.add_argument("--sort", choices=["name", "size"], default="name", help="Sort list by 'name' or 'size'")
    parser.add_argument("--delete-files", metavar="KEYWORD", nargs="?", const="", help="Delete files matching keyword")
    parser.add_argument("--delete-larger", type=float, help="Delete files larger than given size (in MB)")
    parser.add_argument("--force", action="store_true", help="Delete files without confirmation")
    parser.add_argument("--status", action="store_true", help="Show live status updates")

    args = parser.parse_args()
    ws_url = f"ws://{args.ip}:9999/websocket"

    default_gcode_path = "/usr/data/printer_data/gcodes/"

    if args.start_file:
        start_print(ws_url, default_gcode_path + args.start_file)
    elif args.pause:
        pause_print(ws_url)
    elif args.stop:
        stop_print(ws_url)
    elif args.list:
        list_files(ws_url, sort_by=args.sort)
    elif args.list_files is not None:
        list_files(ws_url, filter_keyword=args.list_files, sort_by=args.sort)
    elif args.delete_files is not None:
        list_files(ws_url, filter_keyword=args.delete_files, sort_by=args.sort, force=args.force)
    elif args.delete_larger:
        list_files(ws_url, delete_over_size=args.delete_larger, sort_by=args.sort, force=args.force)
    elif args.status:
        live_status(ws_url)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
