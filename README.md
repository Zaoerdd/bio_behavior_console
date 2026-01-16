# Bio-Behavior Experiment Console (生物行为实验控制台)

这是一个基于 Python 的图形化控制系统，专为生物行为学实验（如鱼类条件反射训练、行为轨迹监测）设计。该系统运行于嵌入式 Linux 平台（如 Orange Pi 5 Plus），集成了多路计算机视觉监控、实时运动检测、自动化硬件刺激反馈以及数据记录功能。

![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![Platform](https://img.shields.io/badge/Platform-OrangePi%20%2F%20Linux%20%2F%20Windows-lightgrey)

## ✨ 主要功能

* **多摄视觉监控**: 自动扫描并拼接多个摄像头画面，支持实时预览。
* **交互式 ROI 设置**: 通过鼠标拖拽在画面上自由绘制感兴趣区域（ROI），对应不同的实验箱。
* **实时运动检测**: 基于背景差分算法，实时计算目标运动强度。
* **双模式实验逻辑**:
    * **⚡ 训练模式 (Training)**: 达到运动阈值自动触发 GPIO 电击/刺激，支持“时间”与“次数”双重终止条件。
    * **👁️ 监测模式 (Monitoring)**: 纯观察模式，记录行为数据但不触发硬件刺激。
* **数据记录**: 自动保存实验视频 (.mp4) 和 CSV 数据报表。
* **远程通知**: 集成 Pushplus，实验状态变化时发送微信通知。

## 🛠️ 硬件与环境要求

### 硬件
* **计算平台**: Orange Pi 5 Plus (或兼容 wiringOP/gpio 命令的开发板)
* **摄像头**: USB 免驱摄像头 (支持多路)
* **外设**: 继电器模块或电击刺激器 (连接至 GPIO)

### 软件依赖
* Python 3.8+(建议使用Python 3.10)
* **系统库**: `wiringOP` (用于 GPIO 控制，必须确保终端能运行 `gpio readall`)
* **Python 库**:
    * `opencv-python`
    * `pillow` (PIL)
    * `numpy`
    * `requests`
    * `tkinter` (通常随 Python 安装，Linux 下可能需单独安装)

## 📦 安装说明

1.  **克隆项目**
    ```bash
    git clone [https://github.com/your-username/bio-behavior-console.git](https://github.com/your-username/bio-behavior-console.git)
    cd bio-behavior-console
    ```

2.  **安装依赖**
    ```bash
    # Linux (Debian/Ubuntu/Armbian) 安装 Tkinter
    sudo apt-get update
    sudo apt-get install python3-tk

    # 安装 Python 依赖
    pip install -r requirements.txt
    ```

3.  **检查 GPIO 工具**
    确保在终端输入 `gpio -v` 能正确输出版本信息。如果未安装，请参考 Orange Pi 官方文档安装 `wiringOP`。

## ⚙️ 配置文件 (config.json)

首次运行程序时，系统会自动在根目录生成 `config.json`。你可以修改此文件来调整默认参数：

| 参数键名 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `IS_TEST_MODE` | `true` 为读取视频文件(Windows/调试用)；`false` 为读取摄像头并控制 GPIO | `true` |
| `TEST_VIDEO_PATH` | 测试模式下使用的视频文件路径 | `"test_video.mp4"` |
| `GPIO_PINS` | 实验箱 ID 与 wPi 引脚编号的映射 | `{'Box_1': 3, ...}` |
| `PUSHPLUS_TOKEN` | (可选) Pushplus 推送 Token | `"0"` |

> **⚠️ 注意**: `config.json` 可能包含敏感 Token，请勿将其提交到公共代码仓库。

## 🚀 使用方式

建议在 Linux 环境下使用 `sudo` 运行，以确保有权限访问 GPIO 和摄像头设备。

```bash
sudo python bio_behavior_console.py