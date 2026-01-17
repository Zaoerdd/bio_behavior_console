# Bio-Behavior Experiment Console

**[中文版本](README.md)** | **English**

A Python-based graphical control system designed for ethological experiments (such as fish conditioned reflex training and behavioral trajectory monitoring). This system runs on embedded Linux platforms (such as Orange Pi 5 Plus) and integrates multi-channel computer vision monitoring, real-time motion detection, automated hardware stimulus feedback, and data logging.

![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![Platform](https://img.shields.io/badge/Platform-OrangePi%20%2F%20Linux%20%2F%20Windows-lightgrey)

## ✨ Key Features

* **Multi-Camera Visual Monitoring**: Automatically scans and stitches multiple camera feeds with real-time preview support.
* **Interactive ROI Setup**: Freely draw regions of interest (ROI) on the screen through mouse dragging, corresponding to different experimental boxes.
* **Real-Time Motion Detection**: Calculates target motion intensity in real-time based on background subtraction algorithms.
* **Dual-Mode Experiment Logic**:
    * **⚡ Training Mode**: Automatically triggers GPIO electric stimulation/shock when motion threshold is reached, supporting dual termination conditions of "time" and "count".
    * **👁️ Monitoring Mode**: Pure observation mode that records behavioral data without triggering hardware stimulation.
* **Data Recording**: Automatically saves experimental videos (.mp4) and CSV data reports.
* **Remote Notifications**: Integrates Pushplus for WeChat notifications on experiment status changes.

## 🚀 Quick Start (Binary Release)

**Recommended Method: No need to install Python or OpenCV environment. Download and run directly on Orange Pi.**

### 1. Preparation
Ensure your development board has `wiringOP` library installed (for GPIO control):
```bash
# Check if gpio command is available
gpio -v

# If "command not found" error appears, refer to Orange Pi official documentation to install wiringOP
# For Orange Pi 5 Plus:
git clone https://github.com/orangepi-xunlong/wiringOP
cd wiringOP
./build clean
./build
```

### 2. Download and Run

Visit the project [Releases page](https://github.com/Zaoerdd/bio_behavior_console/releases) to download the latest version `bio_behavior_console`.

Open a terminal in the file directory, grant executable permission, and run:

```bash
# 1. Grant execute permission
chmod +x bio_behavior_console

# 2. Start the program (must use sudo to access GPIO and USB cameras)
sudo ./bio_behavior_console
```

**Tip:** On first run, the program will automatically generate config.json in the current directory. You can modify it to disable test mode or remap pins.

## 🛠️ Hardware and Environment Requirements

### Hardware
* **Computing Platform**: Orange Pi 5 Plus (or development board compatible with wiringOP/gpio command)
* **Cameras**: USB plug-and-play cameras (supports multiple)
* **Peripherals**: Relay module or electric shock stimulator (connected to GPIO)

### Software Dependencies
* Python 3.8+ (Python 3.10 recommended)
* **System Libraries**: `wiringOP` (for GPIO control, must ensure terminal can run `gpio readall`)
* **Python Libraries**:
    * `opencv-python`
    * `pillow` (PIL)
    * `numpy`
    * `requests`
    * `tkinter` (usually installed with Python; may need separate installation on Linux)

## 📦 Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/your-username/bio-behavior-console.git
    cd bio-behavior-console
    ```

2.  **Install Dependencies**
    ```bash
    # Linux (Debian/Ubuntu/Armbian) install Tkinter
    sudo apt-get update
    sudo apt-get install python3-tk

    # Install Python dependencies
    pip install -r requirements.txt
    ```

3.  **Check GPIO Tool**
    Ensure that entering `gpio -v` in the terminal produces the correct version information. If not installed, refer to Orange Pi official documentation to install `wiringOP`.

## ⚙️ Configuration File (config.json)

When the program runs for the first time, it will automatically generate `config.json` in the root directory. You can modify this file to adjust default parameters:

| Parameter Key | Description | Default Value |
| :--- | :--- | :--- |
| `IS_TEST_MODE` | `true` reads video file (Windows/Debug); `false` reads camera and controls GPIO | `true` |
| `TEST_VIDEO_PATH` | Video file path used in test mode | `"test_video.mp4"` |
| `GPIO_PINS` | Mapping of experiment box IDs to wPi pin numbers | `{'Box_1': 3, ...}` |
| `PUSHPLUS_TOKEN` | (Optional) Pushplus push token | `"0"` |

> **⚠️ Note**: `config.json` may contain sensitive tokens, please do not commit it to a public code repository.

## 🚀 Usage

It is recommended to run with `sudo` in a Linux environment to ensure proper permissions for accessing GPIO and camera devices.

```bash
sudo python bio_behavior_console.py
```
