# Creality K1 Control Script

A Python script – with some AI help – to control a Creality K1 running the original firmware.  
Likely compatible with the K1 Max, K2, and other related models.

---

## Features

- Start / pause / resume / stop prints  
- Upload `.gcode` files directly to the printer  
- List and delete files on the printer  
- Monitor live print status in the terminal  
- Display the printer's webcam image using ANSI color blocks  
- Stream the printer's webcam feed in the terminal (with optional high-res mode)

---

## Usage

```bash
usage: k1_control.py --ip IP [options]
```

---

## Required

| Argument   | Description               |
|------------|---------------------------|
| `--ip IP`  | IP address of the printer |

---

## Default IP Configuration

To avoid specifying the `--ip` argument every time, you can create a `config.json` file in the project directory with the following content:

```json
{
  "default_ip": "192.168.1.100"
}
```

---

## Print Control

| Argument              | Description                                          |
|-----------------------|------------------------------------------------------|
| `--start-file FILE`   | Start print with filename                            |
| `--countdown MINUTES` | Countdown in minutes before starting the print       |
| `--pause`             | Pause the current print                              |
| `--resume`            | Resume the current print                             |
| `--stop`              | Stop the current print                               |

---

## File Management

| Argument                        | Description                                      |
|----------------------------------|--------------------------------------------------|
| `--upload-file FILE`            | Upload a local `.gcode` file to the printer     |
| `--list-files [KEYWORD]`        | List `.gcode` files (optional keyword filter)   |
| `--sort {name,size,time}`       | Sort file list by name, size or time            |
| `--delete-files [KEYWORD]`      | Delete files matching keyword                   |
| `--delete-larger SIZE_MB`       | Delete files larger than given size (MB)        |
| `--force`                       | Skip confirmation when deleting files           |

---

## Monitoring

| Argument      | Description                                                                                       |
|---------------|---------------------------------------------------------------------------------------------------|
| `--status`    | Show live printer status (in curses UI)                                                           |
| `--photo`     | Show current webcam image in terminal (ANSI)                                                      |
| `--video`     | Stream webcam feed in terminal (default: 2 FPS, configurable with `--interval`)                   |
| `--interval`  | Interval in seconds between video frames (default: 0.5)                                           |
| `--highres`   | Use Unicode half-blocks for higher vertical resolution in video/photo mode (for --photo/--video)  |

---

## Requirements

Install dependencies using:

```bash
pip install -r requirements.txt
```

Contents of `requirements.txt`:

```
requests
websocket-client
pillow
numpy
requests-toolbelt
windows-curses; platform_system == "Windows"
```

---

## Notes

- Uploads require files with a `.gcode` extension and valid G-code content.
- Uploads fail with error 500 if format or structure is incorrect.
- This script communicates directly with the printer's WebSocket and HTTP interfaces.
