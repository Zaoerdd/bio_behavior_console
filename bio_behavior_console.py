import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import cv2
from PIL import Image, ImageTk
import numpy as np
import threading
import time
import os
import datetime
import subprocess
import csv
import requests
import json

# ==========================================
# --- CONFIGURATION (配置区域) ---
# ==========================================

CONFIG_FILE = "config.json"

# 默认配置字典 (如果配置文件不存在，将使用这些值并生成文件)
DEFAULT_CONFIG = {
    # 【模式开关】 True = 使用视频文件测试 (Windows); False = 使用摄像头实战 (Orange Pi)
    "IS_TEST_MODE": True,
    
    # 如果是测试模式，默认加载的视频路径
    "TEST_VIDEO_PATH": "test_video.mp4",
    
    # GPIO 引脚配置 (wPi 编号, 对应 gpio readall)
    "GPIO_PINS": {
        'Box_1': 3,    # wPi 3
        'Box_2': 6,    # wPi 6
        'Box_3': 9,    # wPi 9
        'Box_4': 10    # wPi 10
    },
    
    # 辅助引脚 (wPi 编号)
    "PIN_AUX_13": 13,
    "PIN_ENABLE_21": 21,
    
    # Pushplus Token
    "PUSHPLUS_TOKEN": "0",
    "PUSHPLUS_GROUP": "0"
}

def load_config():
    """加载配置：优先读取文件，文件不存在则创建默认文件"""
    config = DEFAULT_CONFIG.copy()
    
    if not os.path.exists(CONFIG_FILE):
        print(f"[系统] 未检测到配置文件，正在生成默认 {CONFIG_FILE} ...")
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[错误] 无法写入配置文件: {e}")
    else:
        print(f"[系统] 正在读取配置文件 {CONFIG_FILE} ...")
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                # 使用用户配置覆盖默认配置 (update方法只更新存在的键)
                config.update(user_config)
        except Exception as e:
            print(f"[错误] 读取配置文件失败，将使用默认参数: {e}")

    return config

# --- 执行加载 ---
_cfg = load_config()

# --- 将配置映射回全局变量 (保持原有代码的兼容性) ---
IS_TEST_MODE = _cfg["IS_TEST_MODE"]
TEST_VIDEO_PATH = _cfg["TEST_VIDEO_PATH"]
GPIO_PINS = _cfg["GPIO_PINS"]
PIN_AUX_13 = _cfg["PIN_AUX_13"]
PIN_ENABLE_21 = _cfg["PIN_ENABLE_21"]
PUSHPLUS_TOKEN = _cfg["PUSHPLUS_TOKEN"]
PUSHPLUS_GROUP = _cfg["PUSHPLUS_GROUP"]

# ==========================================
# 1. 硬件控制抽象层 (保持不变)
# ==========================================
class Stimulator:
    def __init__(self, is_test_mode):
        self.is_test_mode = is_test_mode
        self.active_flags = {}
        self.shock_counts = {k: 0 for k in GPIO_PINS.keys()} 
        self.shock_history = [] 
        self.running = True
        self.gpio_available = False
        self.log_callback = None

        if not self.is_test_mode:
            try:
                res = subprocess.run(["gpio", "-v"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0:
                    self.gpio_available = True
                    print("[系统] 检测到 wiringOP (gpio 命令可用)")
                    for pin in GPIO_PINS.values():
                        self._gpio_mode(pin, "out")
                        self._gpio_write(pin, 0)
                    self._gpio_mode(PIN_AUX_13, "out")
                    self._gpio_write(PIN_AUX_13, 0)
                    self._gpio_mode(PIN_ENABLE_21, "out")
                    self._gpio_write(PIN_ENABLE_21, 1) # Enable HIGH
                    print("[系统] GPIO 初始化成功")
                else:
                    print("[警告] gpio 命令执行失败，降级为模拟模式")
                    self.is_test_mode = True
            except FileNotFoundError:
                print("[警告] 未找到 gpio 命令，降级为模拟模式")
                self.is_test_mode = True 

    def _gpio_mode(self, pin, mode):
        subprocess.run(["gpio", "mode", str(pin), mode], check=False)

    def _gpio_write(self, pin, value):
        subprocess.run(["gpio", "write", str(pin), str(value)], check=False)

    def set_log_callback(self, callback):
        self.log_callback = callback

    def set_active(self, box_id, should_active):
        if self.active_flags.get(box_id) == should_active:
            return

        self.active_flags[box_id] = should_active
        now_dt = datetime.datetime.now()
        time_str = now_dt.strftime("%H:%M:%S")

        if should_active:
            if box_id in self.shock_counts:
                self.shock_counts[box_id] += 1
                self.shock_history.append({
                    'timestamp': now_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    'box_id': box_id,
                    'count_index': self.shock_counts[box_id]
                })
            
            t = threading.Thread(target=self._pulse_logic, args=(box_id,))
            t.daemon = True
            t.start()
            self._log(f"[{time_str}] ⚡ START -> {box_id} (第{self.shock_counts.get(box_id, 0)}次)")
        else:
            self._log(f"[{time_str}] ⏹ STOP  -> {box_id}")

    def _pulse_logic(self, box_id):
        while self.active_flags.get(box_id, False) and self.running:
            if not self.is_test_mode and self.gpio_available:
                pin = GPIO_PINS.get(box_id)
                if pin is not None:
                    self._gpio_write(pin, 1) # HIGH
                    time.sleep(0.2)
                    self._gpio_write(pin, 0) # LOW
                    time.sleep(0.8)
            else:
                time.sleep(1.0) 

    def _log(self, msg):
        print(f"[硬件] {msg}")
        if self.log_callback:
            self.log_callback(msg)

    def reset_counts(self):
        self.shock_counts = {k: 0 for k in GPIO_PINS.keys()}
        self.shock_history = [] 

    def stop_all(self):
        for box_id in self.active_flags:
            self.active_flags[box_id] = False
        if not self.is_test_mode and self.gpio_available:
            for pin in GPIO_PINS.values():
                self._gpio_write(pin, 0)
            self._gpio_write(PIN_AUX_13, 0)

    def cleanup(self):
        self.running = False
        if not self.is_test_mode and self.gpio_available:
            for pin in GPIO_PINS.values():
                self._gpio_write(pin, 0)
            self._gpio_write(PIN_AUX_13, 0)
            self._gpio_write(PIN_ENABLE_21, 0)
            print("[系统] GPIO 已通过命令行复位")

# ==========================================
# 训练设置弹窗 (保持不变)
# ==========================================
class TrainingDialog(tk.Toplevel):
    def __init__(self, parent, existing_rois):
        super().__init__(parent)
        self.title("设置训练参数 (电击模式)")
        self.geometry("350x450")
        self.result = None 
        self.existing_rois = existing_rois
        
        self.var_enable_time = tk.BooleanVar(value=False)
        self.var_enable_count = tk.BooleanVar(value=True)

        frame_time = tk.LabelFrame(self, text="条件A: 时间限制", width=300, height=80)
        frame_time.pack(pady=5, padx=10, fill=tk.X)
        
        chk_time = tk.Checkbutton(frame_time, text="启用倒计时", variable=self.var_enable_time, command=self.toggle_time)
        chk_time.pack(side=tk.LEFT, padx=10)
        self.ent_time = tk.Entry(frame_time, width=8)
        self.ent_time.insert(0, "60")
        self.ent_time.pack(side=tk.LEFT, padx=5)
        tk.Label(frame_time, text="秒").pack(side=tk.LEFT)
        
        frame_count = tk.LabelFrame(self, text="条件B: 电击次数限制 (达标即停)", width=300)
        frame_count.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        chk_count = tk.Checkbutton(frame_count, text="启用次数阈值", variable=self.var_enable_count, command=self.toggle_count)
        chk_count.pack(anchor="w", padx=10, pady=5)
        
        self.count_entries = {}
        self.count_container = tk.Frame(frame_count)
        self.count_container.pack(fill=tk.BOTH, expand=True, padx=20)

        for box_name in sorted(GPIO_PINS.keys()):
            row = tk.Frame(self.count_container)
            row.pack(fill=tk.X, pady=2)
            is_active = box_name in self.existing_rois
            color = "black" if is_active else "gray"
            suffix = "" if is_active else " (未画)"
            tk.Label(row, text=f"{box_name}{suffix}:", fg=color, width=12, anchor="w").pack(side=tk.LEFT)
            ent = tk.Entry(row, width=8)
            ent.insert(0, "5")
            ent.pack(side=tk.RIGHT)
            if not is_active: ent.config(state=tk.DISABLED)
            self.count_entries[box_name] = ent

        # --- [修改] 在提示语上方添加推送选项 ---
        # 默认勾选 (True)，你可以根据需要改为 False
        self.var_enable_push = tk.BooleanVar(value=True)
        chk_push = tk.Checkbutton(self, text="启用 Pushplus 消息推送", variable=self.var_enable_push, fg="purple")
        chk_push.pack(pady=2)

        hint = tk.Label(self, text="提示: 若同时勾选, 满足任意条件即终止训练", fg="blue", font=("Arial", 9))
        hint.pack(pady=5)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10, fill=tk.X)
        tk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=10)
        tk.Button(btn_frame, text="开始训练", bg="#90EE90", command=self.on_confirm).pack(side=tk.RIGHT, padx=10)

        self.toggle_time()
        self.toggle_count()

    def toggle_time(self):
        state = tk.NORMAL if self.var_enable_time.get() else tk.DISABLED
        self.ent_time.config(state=state)

    def toggle_count(self):
        state = tk.NORMAL if self.var_enable_count.get() else tk.DISABLED
        for name, ent in self.count_entries.items():
            if name in self.existing_rois: 
                ent.config(state=state)

    def on_confirm(self):
        now_dt = datetime.datetime.now()
        now_epoch = time.time()
        
        data = {
            'use_time': self.var_enable_time.get(),
            'duration': None,
            'use_count': self.var_enable_count.get(),
            'targets': {},
            'click_time_dt': now_dt,
            'click_time_epoch': now_epoch,
            'enable_push': self.var_enable_push.get() # [新增] 保存推送选项
        }
        if not data['use_time'] and not data['use_count']:
            messagebox.showerror("错误", "请至少启用一种限制条件！")
            return
        try:
            if data['use_time']:
                val = int(self.ent_time.get())
                if val <= 0: raise ValueError
                data['duration'] = val
            if data['use_count']:
                for name, ent in self.count_entries.items():
                    if ent['state'] != tk.DISABLED:
                        val = int(ent.get())
                        if val < 1: raise ValueError
                        data['targets'][name] = val
            self.result = data
            self.destroy()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的正整数！")

# ==========================================
# 监测设置弹窗 (保持不变)
# ==========================================
class MonitoringDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("设置行为监测参数 (无电击)")
        self.geometry("300x180")
        self.result = None
        
        tk.Label(self, text="请输入监测时长:", font=("Arial", 10)).pack(pady=10)
        
        frame_time = tk.Frame(self)
        frame_time.pack(pady=5)
        
        self.ent_time = tk.Entry(frame_time, width=10)
        self.ent_time.insert(0, "60")
        self.ent_time.pack(side=tk.LEFT, padx=5)
        tk.Label(frame_time, text="秒").pack(side=tk.LEFT)
        
        # --- [修改] 添加推送选项 ---
        self.var_enable_push = tk.BooleanVar(value=True)
        chk_push = tk.Checkbutton(self, text="启用 Pushplus 消息推送", variable=self.var_enable_push, fg="purple")
        chk_push.pack(pady=5)
        
        tk.Label(self, text="注意: 监测模式下不会触发电击", fg="blue").pack(pady=5) # 调整了下pady

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10, fill=tk.X)
        tk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=10)
        tk.Button(btn_frame, text="开始监测", bg="#ADD8E6", command=self.on_confirm).pack(side=tk.RIGHT, padx=10)

    def on_confirm(self):
        try:
            val = int(self.ent_time.get())
            if val <= 0: raise ValueError
            
            # 记录点击时间
            self.result = {
                'duration': val,
                'click_time_dt': datetime.datetime.now(),
                'click_time_epoch': time.time(),
                'enable_push': self.var_enable_push.get() # [新增] 保存推送选项
            }
            self.destroy()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的监测时长(正整数)！")

# ==========================================
# [新增] 摄像头选择弹窗
# ==========================================
class CameraSelectionDialog(tk.Toplevel):
    def __init__(self, parent, available_cams):
        super().__init__(parent)
        self.title("选择要使用的摄像头")
        self.geometry("400x400")
        self.available_cams = available_cams # list of (index, info_str)
        self.selected_indices = []
        
        tk.Label(self, text="检测到以下摄像头，请勾选需要使用的设备:", font=("Arial", 10, "bold")).pack(pady=10)
        
        # 滚动区域 (万一摄像头很多)
        frame_container = tk.Frame(self)
        frame_container.pack(fill=tk.BOTH, expand=True, padx=10)
        canvas = tk.Canvas(frame_container)
        scrollbar = tk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.vars = {}
        if not available_cams:
            tk.Label(scrollable_frame, text="未检测到任何可用摄像头！", fg="red").pack(pady=20)
        else:
            for idx, info in available_cams:
                var = tk.IntVar()
                chk = tk.Checkbutton(scrollable_frame, text=f"Index {idx}: {info}", variable=var, font=("Arial", 10))
                chk.pack(anchor='w', pady=2)
                self.vars[idx] = var
                
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10, fill=tk.X)
        tk.Button(btn_frame, text="取消/退出", command=self.on_cancel).pack(side=tk.RIGHT, padx=10)
        tk.Button(btn_frame, text="确定选择", bg="#90EE90", command=self.on_confirm).pack(side=tk.RIGHT, padx=10)
        
        # 强制模态
        self.transient(parent)
        self.grab_set()
        
    def on_confirm(self):
        selected = []
        for idx, var in self.vars.items():
            if var.get() == 1:
                selected.append(idx)
        self.selected_indices = sorted(selected)
        if not self.selected_indices and self.available_cams:
            messagebox.showwarning("提示", "请至少选择一个摄像头，或者取消。")
            return
        self.destroy()

    def on_cancel(self):
        self.selected_indices = []
        self.destroy()

# ==========================================
# 2. GUI 主程序
# ==========================================
class UnifiedGUI:
    def __init__(self, root):
        self.root = root
        mode_str = "【测试模式 - 读取视频】" if IS_TEST_MODE else "【实战模式 - 多摄拼接】"
        self.root.title(f"生物行为实验控制台 - {mode_str}")
        self.root.geometry("1200x900")
        self.root.minsize(1100, 700)

        self.stimulator = Stimulator(IS_TEST_MODE)
        
        # [修改] 改为列表存储多摄
        self.caps = [] 
        
        self.stop_event = threading.Event()
        self.is_playing = False
        self.background_frame = None
        self.rois = {}
        self.roi_counter = 1
        # self.threshold = 5
        self.pixel_diff_threshold = 25  # 控制对光线/颜色变化的敏感度 (越小越灵敏，但也越容易受噪点干扰)
        self.motion_area_threshold = 5  # 控制对运动面积大小的敏感度 (即原本的 self.threshold) 
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        self.drawing = False
        self.display_w = 800
        self.display_h = 600
        
        # --- 训练相关变量 ---
        self.is_training = False     
        self.train_cfg = {}          
        self.train_end_ts = 0
        self.train_start_dt = None       
        self.actual_train_end_dt = None
        self.boxes_finished = set()  
        
        # --- 监测相关变量 ---
        self.is_monitoring = False  
        self.monitor_cfg = {}    
        self.monitor_end_ts = 0         
        self.monitor_start_dt = None    
        self.actual_monitor_end_dt = None
        
        self.monitor_records = {k: [] for k in GPIO_PINS.keys()}
        self.monitor_active_events = {} 

        self.train_records = {k: [] for k in GPIO_PINS.keys()}
        self.train_active_events = {}
        
        # --- 视频录制相关变量 ---
        self.video_writer = None
        self.recording_filename = None
        
        self.count_labels = {} 
        self.hw_labels = {}
        
        self._setup_ui()
        self._init_hw_info()

        self.stimulator.set_log_callback(self.update_shock_log_from_thread)

        # [修改] 启动逻辑分支
        if not IS_TEST_MODE:
            self.scan_and_load_cameras()
        elif IS_TEST_MODE and TEST_VIDEO_PATH and os.path.exists(TEST_VIDEO_PATH):
            self.load_video_file(TEST_VIDEO_PATH)

    def _setup_ui(self):
        control_frame = tk.Frame(self.root, pady=10, bg="#f0f0f0")
        control_frame.pack(side=tk.TOP, fill=tk.X)

        if IS_TEST_MODE:
            tk.Button(control_frame, text="打开视频文件", command=self.browse_video).pack(side=tk.LEFT, padx=5)
        else:
            tk.Button(control_frame, text="重新扫描摄像头", command=self.scan_and_load_cameras, bg="#FFD700").pack(side=tk.LEFT, padx=5)

        tk.Button(control_frame, text="重置背景(B)", command=self.reset_background).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="清空区域", command=self.clear_rois).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="重置计数", command=self.reset_counts).pack(side=tk.LEFT, padx=5)
        
        # 训练按钮
        self.btn_train = tk.Button(control_frame, text="▶ 设定训练", bg="#90EE90", font=("Arial", 10, "bold"), command=self.ask_start_training)
        self.btn_train.pack(side=tk.LEFT, padx=20)
        
        # 监测按钮
        self.btn_monitor = tk.Button(control_frame, text="👁 行为监测", bg="#87CEEB", font=("Arial", 10, "bold"), command=self.ask_start_monitoring)
        self.btn_monitor.pack(side=tk.LEFT, padx=5)
        
        # 导出日志按钮 (通用)
        self.btn_export = tk.Button(control_frame, text="💾 导出日志", bg="#E0E0E0", command=self.export_log_router)
        self.btn_export.pack(side=tk.LEFT, padx=5)

        self.lbl_timer = tk.Label(control_frame, text="空闲", font=("Arial", 12), fg="blue", bg="#f0f0f0", width=15)
        self.lbl_timer.pack(side=tk.LEFT, padx=5)

        tk.Label(control_frame, text="抗噪阈值:", bg="#f0f0f0").pack(side=tk.LEFT, padx=10)
        self.pixel_diff_scale = tk.Scale(control_frame, from_=1, to=100, orient=tk.HORIZONTAL, command=self.update_pixel_diff_threshold)
        self.pixel_diff_scale.set(25) 
        self.pixel_diff_scale.pack(side=tk.LEFT, padx=5)

        tk.Label(control_frame, text="运动面积阈值:", bg="#f0f0f0").pack(side=tk.LEFT, padx=10)
        self.motion_area_scale = tk.Scale(control_frame, from_=1, to=50, orient=tk.HORIZONTAL, command=self.update_motion_area_threshold)
        self.motion_area_scale.set(5) 
        self.motion_area_scale.pack(side=tk.LEFT, padx=5)

        self.pause_btn = tk.Button(control_frame, text="暂停 (Space)", command=self.toggle_pause)
        self.pause_btn.pack(side=tk.LEFT, padx=20)

        # 右侧面板
        right_panel = tk.Frame(self.root, bg="#e0e0e0")
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        stats_frame = tk.LabelFrame(right_panel, text="实时计数 / 目标", width=180, bg="white")
        stats_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        for box_name in sorted(GPIO_PINS.keys()):
            row = tk.Frame(stats_frame, bg="white")
            row.pack(fill=tk.X, padx=5, pady=2)
            tk.Label(row, text=f"{box_name}:", width=8, anchor="w", bg="white", font=("Arial", 10)).pack(side=tk.LEFT)
            lbl_count = tk.Label(row, text="0 / -", fg="blue", font=("Arial", 11, "bold"), bg="white")
            lbl_count.pack(side=tk.RIGHT)
            self.count_labels[box_name] = lbl_count

        manual_frame = tk.LabelFrame(right_panel, text="手动强行电击", width=180, bg="#e0e0e0")
        manual_frame.pack(side=tk.TOP, fill=tk.Y, padx=5, pady=10, expand=True)
        for box_name in sorted(GPIO_PINS.keys()):
            btn = tk.Button(manual_frame, text=f"{box_name}\n(Pin {GPIO_PINS[box_name]})", 
                            bg="white", fg="darkred", font=("Arial", 10, "bold"), height=2)
            btn.pack(fill=tk.X, padx=5, pady=8)
            btn.bind("<ButtonPress-1>", lambda event, b=box_name, widget=btn: self.manual_shock_start(b, widget))
            btn.bind("<ButtonRelease-1>", lambda event, b=box_name, widget=btn: self.manual_shock_stop(b, widget))

        # 底部三栏
        bottom_container = tk.Frame(self.root, height=180, bg="#f0f0f0")
        bottom_container.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        bottom_container.pack_propagate(False)

        hw_frame = tk.LabelFrame(bottom_container, text="系统状态", width=200, bg="#f0f0f0")
        hw_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        hw_frame.pack_propagate(False)
        self._create_hw_label(hw_frame, "Mode", "模式")
        self._create_hw_label(hw_frame, "GPIO", "GPIO")
        self._create_hw_label(hw_frame, "Source", "源")
        self._create_hw_label(hw_frame, "Res", "分辨率")

        shock_log_frame = tk.LabelFrame(bottom_container, text="⚡ 电击事件记录", width=400, bg="#fff0f0") 
        shock_log_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        shock_log_frame.pack_propagate(False)
        self.shock_log_text = tk.Text(shock_log_frame, state=tk.DISABLED, bg="#2b2b2b", fg="#ff4444", font=("Consolas", 10))
        shock_scroll = tk.Scrollbar(shock_log_frame, command=self.shock_log_text.yview)
        shock_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.shock_log_text.config(yscrollcommand=shock_scroll.set)
        self.shock_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sys_log_frame = tk.LabelFrame(bottom_container, text="ℹ️ 系统运行日志", bg="#f0f0f0")
        sys_log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.sys_log_text = tk.Text(sys_log_frame, state=tk.DISABLED, bg="black", fg="#00FF00", font=("Consolas", 9))
        sys_scroll = tk.Scrollbar(sys_log_frame, command=self.sys_log_text.yview)
        sys_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.sys_log_text.config(yscrollcommand=sys_scroll.set)
        self.sys_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas_frame = tk.Frame(self.root, bg="#333333")
        self.canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(self.canvas_frame, bg="black", cursor="cross")
        self.canvas.pack(anchor=tk.CENTER, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.root.bind('<space>', lambda e: self.toggle_pause())
        self.root.bind('b', lambda e: self.reset_background())

    # ==========================
    # 视频录制辅助函数
    # ==========================
    def _start_recording(self, prefix_name):
        try:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{prefix_name}_{timestamp}.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.record_fps = 20.0  # [修改] 将 fps 存为实例变量，方便后续计算
            scale_factor = 0.5 
            self.record_w = int(self.display_w * scale_factor)
            self.record_h = int(self.display_h * scale_factor)
            self.video_writer = cv2.VideoWriter(filename, fourcc, self.record_fps, (self.record_w, self.record_h))
            
            if self.video_writer.isOpened():
                self.recording_filename = filename
                self.record_start_time = time.time()  # [新增] 记录录像的真实物理开始时间
                self.recorded_frames = 0              # [新增] 记录已经写入的帧数计数器
                self.log_system(f"🎥 录像开始 (Res: {self.record_w}x{self.record_h}): {filename}")
            else:
                self.log_system("❌ 录像初始化失败！")
                self.video_writer = None
        except Exception as e:
            self.log_system(f"❌ 录像错误: {str(e)}")
            self.video_writer = None

    def _stop_recording(self):
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            self.log_system(f"💾 录像已保存: {self.recording_filename}")
            self.recording_filename = None

    # ==========================
    # 逻辑控制: 训练 (保持不变)
    # ==========================
    def ask_start_training(self):
        if self.is_monitoring:
            messagebox.showwarning("冲突", "请先停止行为监测！")
            return
        if self.is_training:
            if messagebox.askyesno("停止", "确定要中断当前训练吗？"):
                self.stop_training("手动中断")
            return
        if not self.rois:
            messagebox.showwarning("警告", "请先在画面上画出检测区域！")
            return
        dialog = TrainingDialog(self.root, self.rois)
        self.root.wait_window(dialog)
        if dialog.result:
            self.start_training(dialog.result)

    def start_training(self, cfg):
        self.is_training = True
        self.train_cfg = cfg
        self.reset_counts() 
        self.train_records = {k: [] for k in GPIO_PINS.keys()}
        self.train_active_events = {}
        self.boxes_finished = set()
        self.train_start_dt = cfg.get('click_time_dt', datetime.datetime.now())
        self.actual_train_end_dt = None

        if cfg['use_time']:
            start_epoch = cfg.get('click_time_epoch', time.time())
            self.train_end_ts = start_epoch + cfg['duration']
        
        self.btn_train.config(text="⏹ 停止训练", bg="#FF6347")
        self.btn_monitor.config(state=tk.DISABLED) 
        self.log_system("=== 训练开始 (电击模式) ===")
        self._start_recording("Train_Record")
        if cfg.get('enable_push'):
            msg = f"训练模式已启动。<br>时间: {datetime.datetime.now()}<br>配置: {cfg}"
            self._send_push("实验开始提醒 (训练)", msg)
        self.update_stats_display()

    def stop_training(self, reason):
        self.actual_train_end_dt = datetime.datetime.now()
        self.is_training = False
        self._stop_recording()
        
        for box, start_time in list(self.train_active_events.items()):
            duration = (self.actual_train_end_dt - start_time).total_seconds()
            if box in self.train_records:
                self.train_records[box].append(duration)
        self.train_active_events.clear()
        
        self.stimulator.stop_all()
        self.btn_train.config(text="▶ 设定训练", bg="#90EE90")
        self.btn_monitor.config(state=tk.NORMAL)
        self.lbl_timer.config(text="空闲", fg="blue")
        self.log_system(f"=== 训练结束: {reason} ===")
        if self.train_cfg.get('enable_push'):
            msg = f"训练模式已结束。<br>原因: {reason}<br>结束时间: {datetime.datetime.now()}"
            self._send_push("实验结束提醒 (训练)", msg)

        self.update_stats_display()
        messagebox.showinfo("结束", f"训练已结束\n原因: {reason}\n您可以点击“导出日志”保存数据。\n视频已保存。")

    # ==========================
    # 逻辑控制: 行为监测 (保持不变)
    # ==========================
    def ask_start_monitoring(self):
        if self.is_training:
            messagebox.showwarning("冲突", "请先停止训练！")
            return
        if self.is_monitoring:
            if messagebox.askyesno("停止", "确定要停止当前监测吗？"):
                self.stop_monitoring("手动停止")
            return
        if not self.rois:
            messagebox.showwarning("警告", "请先在画面上画出检测区域！")
            return

        dialog = MonitoringDialog(self.root)
        self.root.wait_window(dialog)
        
        if dialog.result:
            self.start_monitoring(dialog.result)

    def start_monitoring(self, cfg):
        self.is_monitoring = True
        self.monitor_cfg = cfg
        self.monitor_records = {k: [] for k in GPIO_PINS.keys()}
        self.monitor_active_events = {}
        self.monitor_start_dt = cfg.get('click_time_dt', datetime.datetime.now())
        self.actual_monitor_end_dt = None
        
        start_epoch = cfg.get('click_time_epoch', time.time())
        self.monitor_end_ts = start_epoch + cfg['duration']
        
        self.btn_monitor.config(text="⏹ 停止监测", bg="#FF6347")
        self.btn_train.config(state=tk.DISABLED) 
        self.log_system("=== 行为监测开始 (无电击) ===")
        self.log_system(f"时长: {cfg['duration']}秒")
        self._start_recording("Monitor_Record")
        if cfg.get('enable_push'):
            msg = f"监测模式已启动。<br>时间: {datetime.datetime.now()}<br>计划时长: {cfg['duration']}秒"
            self._send_push("实验开始提醒 (监测)", msg)

    def stop_monitoring(self, reason):
        self.actual_monitor_end_dt = datetime.datetime.now()
        self.is_monitoring = False
        self._stop_recording()
        
        for box, start_time in list(self.monitor_active_events.items()):
            duration = (self.actual_monitor_end_dt - start_time).total_seconds()
            self.monitor_records[box].append({
                'start': start_time,
                'end': self.actual_monitor_end_dt,
                'duration': duration
            })
        self.monitor_active_events.clear()
        
        self.btn_monitor.config(text="👁 行为监测", bg="#87CEEB")
        self.btn_train.config(state=tk.NORMAL)
        self.lbl_timer.config(text="空闲", fg="blue")
        self.log_system(f"=== 监测结束: {reason} ===")
        if self.monitor_cfg.get('enable_push'):
            msg = f"监测模式已结束。<br>原因: {reason}<br>结束时间: {datetime.datetime.now()}"
            self._send_push("实验结束提醒 (监测)", msg)
        messagebox.showinfo("监测结束", f"行为监测已完成\n原因: {reason}\n您可以点击“导出日志”保存监测数据。\n视频已保存。")

    # ==========================
    # 导出日志路由 (保持不变)
    # ==========================
    def export_log_router(self):
        has_train_run = self.train_start_dt is not None
        has_monitor_run = self.monitor_start_dt is not None

        if has_monitor_run and not has_train_run:
            self.export_monitor_log()
        elif has_train_run and not has_monitor_run:
            self.export_train_log()
        elif has_train_run and has_monitor_run:
            choice = messagebox.askquestion("选择导出类型", "检测到存在多种数据记录。\n\n点击【是】导出行为监测日志\n点击【否】导出电击训练日志")
            if choice == 'yes':
                self.export_monitor_log()
            else:
                self.export_train_log()
        else:
            messagebox.showwarning("无数据", "暂无数据可导出")

    def export_train_log(self):
        default_name = f"train_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default_name)
        if not filepath: return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["=== 电击训练日志 ==="])
                start_str = self.train_start_dt.strftime("%Y-%m-%d %H:%M:%S") if self.train_start_dt else "N/A"
                end_dt = self.actual_train_end_dt if self.actual_train_end_dt else datetime.datetime.now()
                end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                duration = str(end_dt - self.train_start_dt).split('.')[0] if self.train_start_dt else "N/A"
                
                writer.writerow(["开始时间", start_str])
                writer.writerow(["结束时间", end_str])
                writer.writerow(["训练时长", duration])
                writer.writerow([]) 

                writer.writerow(["=== 统计数据 ==="])
                writer.writerow(["Box名称", "电击次数"])
                for box, count in self.stimulator.shock_counts.items():
                    writer.writerow([box, count])
                writer.writerow([]) 

                writer.writerow(["=== 详细事件记录 ==="])
                writer.writerow(["时间戳", "Box名称", "次数序号"])
                for record in self.stimulator.shock_history:
                    writer.writerow([record['timestamp'], record['box_id'], record['count_index']])
            self.log_system(f"训练日志已保存: {os.path.basename(filepath)}")
            messagebox.showinfo("成功", "训练日志导出成功！")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def export_monitor_log(self):
        default_name = f"monitor_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default_name)
        if not filepath: return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["=== 行为监测日志 (无电击) ==="])
                
                start_str = self.monitor_start_dt.strftime("%Y-%m-%d %H:%M:%S") if self.monitor_start_dt else "N/A"
                end_dt = self.actual_monitor_end_dt if self.actual_monitor_end_dt else datetime.datetime.now()
                end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                duration = str(end_dt - self.monitor_start_dt).split('.')[0] if self.monitor_start_dt else "N/A"
                
                writer.writerow(["监测开始", start_str])
                writer.writerow(["监测结束", end_str])
                writer.writerow(["总监测时长", duration])
                writer.writerow([]) 

                writer.writerow(["=== 停留时长统计 (Summary) ==="])
                writer.writerow(["Box名称", "总停留时间(秒)", "进入次数"])
                for box in sorted(GPIO_PINS.keys()):
                    records = self.monitor_records.get(box, [])
                    total_dur = sum([r['duration'] for r in records])
                    count = len(records)
                    writer.writerow([box, f"{total_dur:.2f}", count])
                writer.writerow([]) 

                writer.writerow(["=== 详细进出记录 (Details) ==="])
                writer.writerow(["Box名称", "进入时间", "离开时间", "单次停留时长(秒)"])
                
                all_records = []
                for box, recs in self.monitor_records.items():
                    for r in recs:
                        all_records.append({**r, 'box': box})
                all_records.sort(key=lambda x: x['start'])
                
                for r in all_records:
                    s_str = r['start'].strftime("%H:%M:%S.%f")[:-3]
                    e_str = r['end'].strftime("%H:%M:%S.%f")[:-3]
                    writer.writerow([r['box'], s_str, e_str, f"{r['duration']:.2f}"])
                    
            self.log_system(f"监测日志已保存: {os.path.basename(filepath)}")
            messagebox.showinfo("成功", "行为监测日志导出成功！")
        except Exception as e:
            messagebox.showerror("错误", str(e))


    # ==========================
    # 【新增】Pushplus 推送辅助函数
    # ==========================
    def _send_push(self, title, content):
        """后台发送 Pushplus 通知"""
        if not PUSHPLUS_TOKEN:
            self.log_system("⚠️ 未配置 Pushplus Token，跳过推送")
            return

        def _send_task():
            url = "http://www.pushplus.plus/send"
            data = {
                "token": PUSHPLUS_TOKEN,
                "title": title,
                "content": content,
                "template": "html",
                "topic": PUSHPLUS_GROUP
            }
            try:
                resp = requests.post(url, json=data, timeout=5)
                if resp.status_code == 200:
                    self.log_system(f"✅ 推送发送成功: {title}")
                else:
                    self.log_system(f"❌ 推送发送失败: {resp.text}")
            except Exception as e:
                self.log_system(f"❌ 推送网络错误: {str(e)}")

        # 启动新线程发送，防止界面卡顿
        threading.Thread(target=_send_task, daemon=True).start()

    # ==========================
    # 辅助函数
    # ==========================
    def _create_hw_label(self, parent, key, title):
        row = tk.Frame(parent, bg="#f0f0f0")
        row.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(row, text=f"{title}:", width=6, anchor="w", bg="#f0f0f0", fg="#666").pack(side=tk.LEFT)
        val_label = tk.Label(row, text="--", anchor="w", bg="#f0f0f0", font=("Arial", 9, "bold"))
        val_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.hw_labels[key] = val_label

    def _init_hw_info(self):
        mode_text = "测试" if IS_TEST_MODE else "多摄实战"
        self.hw_labels["Mode"].config(text=mode_text, fg="blue" if IS_TEST_MODE else "red")
        gpio_status = "OK" if self.stimulator.gpio_available else "Sim"
        self.hw_labels["GPIO"].config(text=gpio_status, fg="green" if self.stimulator.gpio_available else "#888")

    def _update_video_info(self, source_name, width, height):
        self.hw_labels["Source"].config(text=str(source_name)[:15])
        self.hw_labels["Res"].config(text=f"{width}x{height}")

    def update_shock_log_from_thread(self, msg):
        self.root.after(0, lambda: self._write_to_widget(self.shock_log_text, msg))

    def log_system(self, msg):
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        self._write_to_widget(self.sys_log_text, f"[{time_str}] {msg}")

    def _write_to_widget(self, widget, msg):
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, f"{msg}\n")
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

    def manual_shock_start(self, box_id, widget):
        widget.config(bg="red", fg="white")
        self.stimulator.set_active(box_id, True)

    def manual_shock_stop(self, box_id, widget):
        widget.config(bg="white", fg="darkred")
        self.stimulator.set_active(box_id, False)

    def reset_counts(self):
        self.stimulator.reset_counts()
        self.boxes_finished = set() 
        self.train_start_dt = None 
        self.monitor_start_dt = None
        self.monitor_records = {k: [] for k in GPIO_PINS.keys()} 
        self.update_stats_display()
        self.log_system("所有计数与记录已重置")

    def update_stats_display(self):
        for box_name, count in self.stimulator.shock_counts.items():
            if box_name in self.count_labels:
                target_str = "-"
                if self.is_training and self.train_cfg.get('use_count'):
                    target = self.train_cfg['targets'].get(box_name, 9999)
                    target_str = str(target)
                text = f"{count} / {target_str}"
                fg_color = "blue"
                if box_name in self.boxes_finished:
                    fg_color = "#00AA00"
                    text += " (√)"
                self.count_labels[box_name].config(text=text, fg=fg_color)

    def browse_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.avi *.mov")])
        if path: self.load_video_file(path)

    # ==========================
    # [修改] 摄像头处理核心逻辑
    # ==========================
    def load_video_file(self, path):
        self.log_system(f"加载视频: {os.path.basename(path)}")
        self._start_capture([path], is_file=True)

    def scan_and_load_cameras(self):
        self.log_system("正在扫描可用摄像头 (0-20)... 请稍候")
        self.root.update()
        
        available = []
        # 扫描 0-20 号设备
        for i in range(21):
            cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    h, w = frame.shape[:2]
                    info = f"{w}x{h}"
                    available.append((i, info))
                cap.release()
        
        self.log_system(f"扫描完成，找到 {len(available)} 个设备")
        
        if not available:
            messagebox.showerror("错误", "未检测到任何可用摄像头！")
            return

        # 弹出选择框
        dialog = CameraSelectionDialog(self.root, available)
        self.root.wait_window(dialog)
        
        if dialog.selected_indices:
            self.log_system(f"用户选择了索引: {dialog.selected_indices}")
            self._start_capture(dialog.selected_indices, is_file=False)
        else:
            self.log_system("用户取消了摄像头选择")

    def _start_capture(self, sources, is_file=False):
        self.stop_event.set()
        
        # 释放旧资源
        for c in self.caps:
            c.release()
        self.caps = []
        
        # 稍微等待旧线程退出
        if self.is_playing:
            self.root.after(200, lambda: self._start_capture(sources, is_file))
            return

        source_name = ""
        
        if is_file:
            # 文件模式: sources[0] 是路径
            cap = cv2.VideoCapture(sources[0])
            if not cap.isOpened():
                self.log_system("无法打开视频文件")
                return
            self.caps.append(cap)
            source_name = "VideoFile"
        else:
            # 摄像头模式: sources 是索引列表 [0, 2, ...]
            for idx in sources:
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                # 设置优选分辨率
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                
                if cap.isOpened():
                    self.caps.append(cap)
                else:
                    self.log_system(f"警告: 无法打开选中摄像头 {idx}")
            
            if not self.caps:
                self.log_system("错误: 所有选中的摄像头都无法打开")
                return
            source_name = f"Multi-Cam ({len(self.caps)})"

        # 读取第一帧用于初始化显示
        frames = []
        for c in self.caps:
            ret, f = c.read()
            if ret:
                frames.append(f)
            else:
                # 假如某个坏了，给个黑帧
                frames.append(np.zeros((480, 640, 3), dtype=np.uint8))

        if not frames:
            return

        # 计算拼接后的总宽高
        # 为了拼接，所有图片高度必须一致。我们以第一张图的高度为基准。
        base_h = frames[0].shape[0]
        total_w = 0
        
        for f in frames:
            h, w = f.shape[:2]
            scale = base_h / h
            total_w += int(w * scale)

        self._init_display_geometry(total_w, base_h)
        self._update_video_info(source_name, total_w, base_h)

        self.stop_event.clear()
        self.is_playing = True
        self.video_loop()

    def _init_display_geometry(self, w, h):
        self.root.update_idletasks()
        max_w = self.canvas_frame.winfo_width()
        max_h = self.canvas_frame.winfo_height()
        if max_w < 100: max_w = 800
        if max_h < 100: max_h = 600

        scale = min(max_w/w, max_h/h, 1.0)
        self.display_w = int(w * scale)
        self.display_h = int(h * scale)
        self.scale_factor = scale
        
        self.canvas.config(width=self.display_w, height=self.display_h)
        self.background_frame = None
        self.log_system("视频系统就绪。请画框。")

    def video_loop(self):
        if self.stop_event.is_set(): return
        self.update_stats_display()
        
        # === 状态检查 ===
        current_time = time.time()
        
        # 1. 监测模式倒计时
        if self.is_monitoring:
            remaining = self.monitor_end_ts - current_time
            if remaining <= 0:
                self.stop_monitoring("时间到")
            else:
                self.lbl_timer.config(text=f"监测剩余: {int(remaining)}秒", fg="blue")
        
        # 2. 训练模式倒计时 & 计数
        elif self.is_training:
            should_stop = False
            stop_reason = ""
            if self.train_cfg['use_time']:
                remaining = self.train_end_ts - current_time
                if remaining <= 0:
                    should_stop = True
                    stop_reason = "时间到"
                else:
                    msg = f"剩余: {int(remaining)}秒"
                    if self.train_cfg['use_count']: msg = f"计次&{msg}"
                    self.lbl_timer.config(text=msg, fg="orange")
            else:
                self.lbl_timer.config(text="计次训练中", fg="red")
            
            if self.train_cfg['use_count']:
                all_finished = True
                if not self.rois: all_finished = False 
                for name in self.rois:
                    curr = self.stimulator.shock_counts.get(name, 0)
                    target = self.train_cfg['targets'].get(name, 9999)
                    if curr >= target:
                        if name not in self.boxes_finished:
                            self.boxes_finished.add(name) 
                            self.stimulator.set_active(name, False) 
                    else:
                        all_finished = False 
                if all_finished and len(self.rois) > 0:
                    should_stop = True
                    stop_reason = "所有区域达到次数"

            if should_stop:
                self.stop_training(stop_reason)
        else:
            self.lbl_timer.config(text="空闲", fg="gray")


        if self.is_playing:
            # [修改] 动态读取所有摄像头并拼接
            raw_frames = []
            valid_read = False
            
            for i, cap in enumerate(self.caps):
                ret, frame = cap.read()
                if ret:
                    raw_frames.append(frame)
                    valid_read = True
                else:
                    # 读取失败，如果是在播放文件，可能结束了
                    if IS_TEST_MODE: 
                         cap.set(cv2.CAP_PROP_POS_FRAMES, 0) # 循环播放
                         _, r_frame = cap.read()
                         raw_frames.append(r_frame)
                    else:
                        # 摄像头掉线，补黑帧
                        raw_frames.append(np.zeros((480, 640, 3), dtype=np.uint8))

            if not valid_read and not IS_TEST_MODE:
                self.log_system("所有摄像头无信号")
                return

            # [拼接逻辑] 统一高度
            if len(raw_frames) > 0:
                base_h = raw_frames[0].shape[0]
                resized_list = []
                for f in raw_frames:
                    h, w = f.shape[:2]
                    if h != base_h:
                        new_w = int(w * (base_h / h))
                        resized_list.append(cv2.resize(f, (new_w, base_h)))
                    else:
                        resized_list.append(f)
                
                # 横向拼接
                final_frame = np.hstack(resized_list)
            else:
                final_frame = np.zeros((480, 640, 3), dtype=np.uint8)

            # 调整为显示大小 (display_w, display_h)
            frame_resized = cv2.resize(final_frame, (self.display_w, self.display_h))
            
            # 转灰度做动态检测
            gray = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if self.background_frame is None:
                self.background_frame = gray
            
            # --- 绘制 Box 逻辑 ---
            for name, rect in self.rois.items():
                x, y, w, h = rect
                if x+w > self.display_w or y+h > self.display_h: continue

                roi_curr = gray[y:y+h, x:x+w]
                roi_bg = self.background_frame[y:y+h, x:x+w]
                
                diff = cv2.absdiff(roi_curr, roi_bg)
                _, diff_binary = cv2.threshold(diff, self.pixel_diff_threshold, 255, cv2.THRESH_BINARY)
                non_zero_count = cv2.countNonZero(diff_binary)
                
                total_pixels = w * h
                score = (non_zero_count / total_pixels) * 100 if total_pixels > 0 else 0
                is_active = score > self.motion_area_threshold
                
                COLOR_PREVIEW_IDLE = (0, 255, 0)   
                COLOR_PREVIEW_ACT  = (0, 0, 255)   
                
                COLOR_TRAIN_IDLE   = (0, 140, 255) 
                COLOR_TRAIN_ACT    = (0, 0, 255)   
                
                COLOR_MONITOR_IDLE = (255, 255, 0) 
                COLOR_MONITOR_ACT  = (255, 0, 0)   

                thickness = 2
                label_text = ""
                box_color = COLOR_PREVIEW_IDLE

                if self.is_training:
                    now_dt = datetime.datetime.now()
                    
                    if self.train_cfg['use_count'] and name in self.boxes_finished:
                        box_color = (0, 255, 0) 
                        label_text = f"{name}: DONE"
                        self.stimulator.set_active(name, False)
                        
                        # 如果完成了，也要结算时间（视为离开）
                        if name in self.train_active_events:
                            start_time = self.train_active_events.pop(name)
                            dur = (now_dt - start_time).total_seconds()
                            self.train_records[name].append(dur)

                    else:
                        if is_active:
                            # --- 激活状态 (进入) ---
                            box_color = COLOR_TRAIN_ACT
                            label_text = f"{name}:{int(score)}% (SHOCK)"
                            thickness = 3 
                            self.stimulator.set_active(name, True)
                            
                            if name not in self.train_active_events:
                                self.train_active_events[name] = now_dt
                        else:
                            # --- 非激活状态 (离开/静止) ---
                            box_color = COLOR_TRAIN_IDLE
                            label_text = f"{name}:{int(score)}% (TRAIN)"
                            self.stimulator.set_active(name, False)
                            
                            if name in self.train_active_events:
                                start_time = self.train_active_events.pop(name)
                                dur = (now_dt - start_time).total_seconds()
                                if name in self.train_records: 
                                    self.train_records[name].append(dur)

                elif self.is_monitoring:
                    now_dt = datetime.datetime.now()
                    if is_active:
                        box_color = COLOR_MONITOR_ACT
                        label_text = f"{name}:{int(score)}% (REC)"
                        thickness = 3 
                        if name not in self.monitor_active_events:
                            self.monitor_active_events[name] = now_dt
                    else:
                        box_color = COLOR_MONITOR_IDLE
                        label_text = f"{name}:{int(score)}% (MONITOR)"
                        if name in self.monitor_active_events:
                            start_time = self.monitor_active_events.pop(name)
                            duration = (now_dt - start_time).total_seconds()
                            self.monitor_records[name].append({
                                'start': start_time,
                                'end': now_dt,
                                'duration': duration
                            })

                else:
                    if is_active:
                        box_color = COLOR_PREVIEW_ACT
                        label_text = f"{name}:{int(score)}% (Preview)"
                    else:
                        box_color = COLOR_PREVIEW_IDLE
                        label_text = f"{name}:{int(score)}%"
                    self.stimulator.set_active(name, False)
                
                cv2.rectangle(frame_resized, (x, y), (x+w, y+h), box_color, thickness)
                cv2.putText(frame_resized, label_text, (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1)

            # 绘制全局时间戳
            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ts_pos = (20, 40)
            cv2.putText(frame_resized, timestamp_str, ts_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
            cv2.putText(frame_resized, timestamp_str, ts_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # 视频写入逻辑 (时间同步对齐)
            if self.video_writer is not None:
                try:
                    frame_to_save = cv2.resize(frame_resized, (self.record_w, self.record_h))
                    
                    # [新增计算逻辑] 计算从录像开始到现在，现实中过去了多少秒
                    elapsed_time = time.time() - self.record_start_time
                    
                    # 根据现实时间和录像的固定FPS，计算到现在为止【应该】写入多少帧
                    expected_frames = int(elapsed_time * self.record_fps)
                    
                    # 如果已写入的帧数落后于理论帧数，就不断补帧直到追上现实时间
                    # (如果代码运行非常快，expected_frames 没变，这个循环就不会执行，从而实现丢帧防加速)
                    while self.recorded_frames < expected_frames:
                        self.video_writer.write(frame_to_save)
                        self.recorded_frames += 1
                        
                except Exception as e:
                    print(f"写入帧错误: {e}")

            # UI 显示转换
            img = Image.fromarray(cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB))
            photo = ImageTk.PhotoImage(image=img)
            self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
            self.canvas.image = photo
            
            if self.drawing and self.current_rect:
                self.canvas.tag_raise(self.current_rect)

        self.root.after(30, self.video_loop)

    def update_pixel_diff_threshold(self, val): self.pixel_diff_threshold = int(val)
    def update_motion_area_threshold(self, val): self.motion_area_threshold = int(val)
    def reset_background(self): self.background_frame = None; self.log_system("背景重置")
    def clear_rois(self): self.rois = {}; self.roi_counter = 1; self.log_system("区域清空")
    def toggle_pause(self): self.is_playing = not self.is_playing

    def on_mouse_down(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.current_rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="cyan")
        self.drawing = True
    
    def on_mouse_drag(self, event):
        if self.drawing: self.canvas.coords(self.current_rect, self.start_x, self.start_y, event.x, event.y)

    def on_mouse_up(self, event):
        self.drawing = False
        x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
        x, y, w, h = min(x1, x2), min(y1, y2), abs(x2-x1), abs(y2-y1)
        if w > 10 and h > 10:
            name = f"Box_{self.roi_counter}"
            self.rois[name] = (x, y, w, h)
            self.roi_counter += 1
            self.log_system(f"添加监测区: {name}")
            self.update_stats_display()
        self.canvas.delete(self.current_rect)

    def on_close(self):
        self.stop_event.set()
        self.stimulator.cleanup()
        if self.video_writer:
            self.video_writer.release()
        # [修改] 释放所有摄像头
        for c in self.caps:
            c.release()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = UnifiedGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()