# Overview: --photo, --video, --interval
import requests
from PIL import Image
from io import BytesIO
import numpy as np
import shutil
import os
import sys
import time

def fetch_photo2(ip):
    url = f"http://{ip}:8080/?action=snapshot"
    try:
        print("Fetching photo from printer...")
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        img = Image.open(BytesIO(response.content))

        terminal_size = shutil.get_terminal_size((80, 24))
        terminal_width = terminal_size.columns

        img_width = terminal_width
        img_height = int((img_width * 9 / 16) / 2)

        img = img.resize((img_width, img_height))
        img = img.convert("RGB")

        img_array = np.array(img)

        for row in img_array:
            for pixel in row:
                r, g, b = pixel
                print(f"\033[48;2;{r};{g};{b}m ", end="")
            print("\033[0m")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching photo: {e}")
    except Exception as e:
        print(f"Error processing photo: {e}")

def fetch_video(ip, interval=0.5):
    url = f"http://{ip}:8080/?action=snapshot"
    try:
        first_frame = True
        last_img_height = None
        last_img_width = None
        while True:
            terminal_size = shutil.get_terminal_size((80, 24))
            img_width = terminal_size.columns
            img_height = int((img_width * 9 / 16) / 2)

            if first_frame or last_img_height != img_height or last_img_width != img_width:
                os.system("clear" if os.name == "posix" else "cls")
                first_frame = False
            else:
                sys.stdout.write(f"\033[{img_height}F")

            last_img_height = img_height
            last_img_width = img_width

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
