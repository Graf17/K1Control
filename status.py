# Overview: --status
import curses
import json
from websocket import create_connection
import time

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

def live_status(ws_url):
    def draw_screen(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.clear()
        if curses.has_colors():
            curses.start_color()

        height, width = stdscr.getmaxyx()
        fixed_info_height = 15  # Increased from 12 to 15
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

        info_keys = [
            "Progress",
            "Total Layers",
            "Current Layer",
            "Nozzle Temp",
            "Bed Temp",
            "Position",
            "Print Time",
            "Time Left",
            "Material Used",
            "Speed",
        ]
        raw_info_cache = {key: None for key in info_keys}
        formatted_info = {key: "N/A" for key in info_keys}
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

        while True:
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == curses.KEY_RESIZE:
                height, width = stdscr.getmaxyx()
                fixed_info_height = 15
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
                        # Nozzle Temp und Bed Temp können als Listen, int, float oder String kommen
                        def to_float(val, old_val):
                            if isinstance(val, list):
                                val = val[0] if val else None
                            try:
                                if isinstance(val, str):
                                    return float(val) if val.replace('.', '', 1).isdigit() else old_val
                                return float(val)
                            except (TypeError, ValueError):
                                return old_val

                        raw_info_cache["Total Layers"] = data.get("TotalLayer", raw_info_cache["Total Layers"])
                        raw_info_cache["Current Layer"] = data.get("layer", raw_info_cache["Current Layer"])
                        raw_info_cache["Nozzle Temp"] = to_float(data.get("nozzleTemp", None), raw_info_cache["Nozzle Temp"])
                        raw_info_cache["Bed Temp"] = to_float(data.get("bedTemp0", None), raw_info_cache["Bed Temp"])
                        raw_info_cache["Progress"] = data.get("printProgress", raw_info_cache["Progress"])
                        raw_info_cache["Position"] = data.get("curPosition", raw_info_cache["Position"])
                        raw_info_cache["Print Time"] = data.get("printJobTime", raw_info_cache["Print Time"])
                        raw_info_cache["Time Left"] = data.get("printLeftTime", raw_info_cache["Time Left"])
                        # Defensive: Only convert if value is not a string
                        def to_float_or_none(val):
                            try:
                                if isinstance(val, str):
                                    return float(val) if val.replace('.', '', 1).isdigit() else None
                                return float(val)
                            except Exception:
                                return None
                        mat_used = data.get("usedMaterialLength", raw_info_cache["Material Used"])
                        speed = data.get("realTimeSpeed", raw_info_cache["Speed"])
                        raw_info_cache["Material Used"] = to_float_or_none(mat_used)
                        raw_info_cache["Speed"] = to_float_or_none(speed)
                        if raw_info_cache["Progress"] is not None and isinstance(raw_info_cache["Progress"], (int, float)):
                            progress_val = int(raw_info_cache["Progress"])
                            bar_len = 30
                            filled = int(progress_val / 100 * bar_len)
                            # Show percent first, then bar
                            bar = f"{progress_val}% [{'█' * filled}{'░' * (bar_len - filled)}]"
                            progress_str = bar
                        else:
                            progress_str = "N/A"
                        formatted_info = {
                            "Progress": progress_str,
                            "Total Layers": raw_info_cache["Total Layers"] if raw_info_cache["Total Layers"] is not None else "N/A",
                            "Current Layer": raw_info_cache["Current Layer"] if raw_info_cache["Current Layer"] is not None else "N/A",
                            "Nozzle Temp": (
                                f"{float(raw_info_cache['Nozzle Temp']):.2f}°C"
                                if raw_info_cache["Nozzle Temp"] is not None and isinstance(raw_info_cache["Nozzle Temp"], (int, float))
                                else "N/A"
                            ),
                            "Bed Temp": (
                                f"{float(raw_info_cache['Bed Temp']):.2f}°C"
                                if raw_info_cache["Bed Temp"] is not None and isinstance(raw_info_cache["Bed Temp"], (int, float))
                                else "N/A"
                            ),
                            "Position": raw_info_cache["Position"] if raw_info_cache["Position"] else "N/A",
                            "Print Time": (
                                f"{int(raw_info_cache['Print Time'] // 3600):02}:{int((raw_info_cache['Print Time'] % 3600) // 60):02}:{int(raw_info_cache['Print Time'] % 60):02}"
                                if raw_info_cache["Print Time"] is not None and isinstance(raw_info_cache["Print Time"], (int, float))
                                else "N/A"
                            ),
                            "Time Left": (
                                f"{int(raw_info_cache['Time Left'] // 3600):02}:{int((raw_info_cache['Time Left'] % 3600) // 60):02}:{int(raw_info_cache['Time Left'] % 60):02}"
                                if raw_info_cache["Time Left"] is not None and isinstance(raw_info_cache["Time Left"], (int, float))
                                else "N/A"
                            ),
                            "Material Used": (
                                f"{raw_info_cache['Material Used'] / 1000:.2f} m"
                                if raw_info_cache["Material Used"] is not None and isinstance(raw_info_cache["Material Used"], (int, float))
                                else "N/A"
                            ),
                            "Speed": (
                                f"{int(round(raw_info_cache['Speed']))} mm/s"
                                if raw_info_cache["Speed"] is not None and isinstance(raw_info_cache["Speed"], (int, float))
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

            if needs_redraw_fixed:
                max_h_fixed, max_w_fixed = fixed_info_win.getmaxyx()
                status_line_y = 2
                safe_addstr(fixed_info_win, status_line_y, 1, " " * (max_w_fixed - 2))
                safe_addstr(fixed_info_win, status_line_y, 2, "Status: Connected", max_w_fixed - 3)
                data_start_y = 3
                value_start_col = 18
                for i, key in enumerate(info_keys):
                    value = formatted_info[key]
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
