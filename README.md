# Creality K1 Control Script

**AI-generated Python script to control a Creality K1 running the original firmware.**  
Likely compatible with the K1 Max, K2, and other related models as well.

---

## Usage
```bash

usage: k1_control.py [-h] --ip IP [--start-file FILENAME] [--countdown COUNTDOWN] [--pause] [--stop]
                     [--list-files [KEYWORD]] [--sort {name,size}] [--delete-files [KEYWORD]]
                     [--delete-larger DELETE_LARGER] [--force] [--status] [--photo]
```
## Options

| Argmuent                         | Description |
|--------------------------------|--------------|
| `-h`, `--help`                 | Show this help message and exit |
| `--ip IP`                      | IP address of the printer |
| `--start-file FILENAME`        | Start print with filename |
| `--countdown COUNTDOWN`        | Countdown in minutes before starting the print (default: 1) |
| `--pause`                      | Pause the current print |
| `--stop`                       | Stop current print |
| `--list-files [KEYWORD]`       | List GCODE files with optional keyword filter |
| `--sort {name,size}`           | Sort list by 'name' or 'size' |
| `--delete-files [KEYWORD]`     | Delete files matching keyword |
| `--delete-larger DELETE_LARGER`| Delete files larger than given size (in MB) |
| `--force`                      | Delete files without confirmation |
| `--status`                     | Show live status updates |
| `--photo`                      | Fetch and display a photo from the printer's camera |

