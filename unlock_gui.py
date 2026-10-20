#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unlock  # noqa: E402

BG = "#1e1f22"
PANEL = "#26282c"
FIELD = "#2f3237"
FG = "#e3e5e8"
DIM = "#9aa0a6"
ACCENT = "#3d7eff"
OK = "#3fb950"
ERR = "#f85149"

FONT = "Microsoft YaHei UI"
CFG = os.path.join(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP", "."),
                   "LauncherRegionUnlock.ini")


def load_last() -> str:
    try:
        with open(CFG, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_last(path: str):
    try:
        with open(CFG, "w", encoding="utf-8") as f:
            f.write(path)
    except OSError:
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue: "queue.Queue" = queue.Queue()
        self.busy = False
        self.s = root.winfo_fpixels("1i") / 96.0

        root.title("启动器区域限制解除器")
        root.configure(bg=BG)

        self._build()
        self._detect()
        self._fit()
        self.root.after(80, self._drain)
        self.root.after(self.px(250), self._auto_launch)

    def px(self, v):
        return int(round(v * self.s))

    def _build(self):
        p = self.px

        tk.Label(self.root, text="启动器区域限制解除器", bg=BG, fg=FG,
                 font=(FONT, 14, "bold")).pack(anchor="w", pady=(p(16), p(2)), padx=p(18))

        box = tk.Frame(self.root, bg=PANEL)
        box.pack(fill="x", pady=(p(14), 0), padx=p(18))
        self.sig = tk.Label(box, text="读取中…", bg=PANEL, fg=DIM, font=(FONT, 9),
                            justify="left", anchor="w", padx=p(12), pady=p(9))
        self.sig.pack(fill="x")

        opt = tk.Frame(self.root, bg=PANEL)
        opt.pack(fill="x", pady=(p(10), 0), padx=p(18))
        tk.Label(opt, text="伪装项", bg=PANEL, fg=DIM, font=(FONT, 9)).grid(
            row=0, column=0, sticky="w", padx=(p(12), p(10)), pady=(p(9), p(4)))

        rows = [
            ("地区", "GetUserDefaultGeoName → US", "GetUserGeoID → 244"),
            ("时区", "Singapore Standard Time（UTC+8 无夏令时）", "钟点与国内一致"),
            ("初始地区", "LocaleName → en-US", "LCID → 0x0409"),
            ("设备区域", "DeviceRegion → 244（美国）", "安装时选定的区域"),
            ("输入法", "键盘布局 → 0x04090409（美国）", "UI 语言 → en-US"),
        ]
        for i, (title, desc, desc2) in enumerate(rows):
            tk.Label(opt, text=title, bg=PANEL, fg=OK, font=(FONT, 9, "bold"),
                     anchor="w").grid(row=i + 1, column=0, sticky="w",
                                      padx=(p(12), p(10)), pady=p(1))
            tk.Label(opt, text=desc + "    " + desc2, bg=PANEL, fg=DIM,
                     font=(FONT, 8)).grid(row=i + 1, column=1, sticky="w", pady=p(1))

        # ---- 目标路径 ----
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", pady=(p(14), 0), padx=p(18))
        tk.Label(row, text="启动器路径", bg=BG, fg=DIM, font=(FONT, 9)).pack(side="left")
        self.path = tk.Entry(row, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                             font=(FONT, 9))
        self.path.pack(side="left", fill="x", expand=True, padx=p(8), ipady=p(5))
        tk.Button(row, text="浏览", command=self._browse, bg=FIELD, fg=FG, relief="flat",
                  font=(FONT, 9), padx=p(12), activebackground=ACCENT,
                  activeforeground="#fff", cursor="hand2").pack(side="left", ipady=p(4))

        row2 = tk.Frame(self.root, bg=BG)
        row2.pack(fill="x", pady=(p(14), 0), padx=p(18))
        self.btn = tk.Button(row2, text="启动并解锁", command=self._launch, bg=ACCENT, fg="#fff",
                             relief="flat", font=(FONT, 10, "bold"), padx=p(20),
                             activebackground="#2f6ad9", cursor="hand2")
        self.btn.pack(side="left", ipady=p(6))
        self.state = tk.Label(row2, text="就绪", bg=BG, fg=DIM, font=(FONT, 9))
        self.state.pack(side="left", padx=p(12))

        wrap = tk.Frame(self.root, bg=PANEL)
        wrap.pack(fill="both", expand=True, pady=(p(14), p(8)), padx=p(18))
        self.log = tk.Text(wrap, bg=PANEL, fg="#c9ccd1", relief="flat", font=("Consolas", 9),
                           wrap="word", padx=p(10), pady=p(8), height=7, state="disabled",
                           insertbackground=FG)
        self.log.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(wrap, command=self.log.yview, width=p(10))
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

        # 底栏
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", pady=(0, p(12)), padx=p(18))
        tk.Label(foot, text="必须从这里启动启动器",
                 bg=BG, fg="#6f7479", font=(FONT, 8), wraplength=p(560),
                 justify="left").pack(side="left", anchor="w")
        tk.Label(foot, text="STCaoMei", bg=BG, fg="#6f7479",
                 font=(FONT, 8)).pack(side="right", anchor="e")

    def _fit(self):
        self.root.update_idletasks()
        rw, rh = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        self.root.minsize(rw, rh)
        self._dark_title()
        if os.environ.get("LAUNCHER_UNLOCK_UI_DEBUG") == "1":
            with open(os.path.join(os.environ.get("TEMP", "."), "launcher_ui.txt"), "w",
                      encoding="utf-8") as f:
                f.write(f"req={rw}x{rh} geom={self.root.winfo_geometry()} "
                        f"scale={self.s} tk={self.root.tk.call('tk', 'scaling')} "
                        f"screen={self.root.winfo_screenwidth()}x"
                        f"{self.root.winfo_screenheight()}\n")

    def _dark_title(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            on = ctypes.c_int(1)
            for attr in (20, 19):   # Win10 20H1+ / 旧版
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                    break
        except Exception:   # noqa: BLE001
            pass

    def _groups(self):
        """所有伪装项固定全开。"""
        return list(unlock.ALL_GROUPS)

    def _sync_summary(self):
        """显示将应用的伪装内容。"""
        self.state.config(text="将伪装：" + unlock.group_summary(self._groups()),
                          fg=DIM)

    def _detect(self):
        sig = unlock.current_signals()
        perm = "管理员" if unlock.is_admin() else "普通（会失败）"
        self.sig.config(text=f"本机真实信号    地区 GeoName = {sig['geo']}    "
                             f"时区 = {sig['tz']}    "
                             f"初始地区 LocaleName = {sig['locale']}    "
                             f"设备区域 = {sig.get('device', '?')}    "
                             f"键盘布局 = {sig.get('kbl', '?')}    权限 = {perm}")
        # 不做任何自动探测，exe 必须由用户手动选择
        last = load_last()
        if last and os.path.isfile(last):
            self.path.insert(0, last)
        else:
            self.path.insert(0, "")
            self._log("请点「浏览」手动选择启动器的 exe。")
        self._sync_summary()

    def _browse(self):
        p = filedialog.askopenfilename(title="选择启动器的 exe",
                                       filetypes=[("可执行文件", "*.exe")])
        if p:
            p = os.path.normpath(p)
            self.path.delete(0, "end")
            self.path.insert(0, p)
            save_last(p)

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _auto_launch(self):
        if self.path.get().strip().strip('"'):
            self._launch()

    def _launch(self):
        if self.busy:
            return
        exe = self.path.get().strip().strip('"')
        if not exe or not os.path.isfile(exe):
            messagebox.showwarning("路径不对", "先选一个存在的启动器 exe。")
            return
        groups = self._groups()
        save_last(exe)
        self.busy = True
        self.btn.config(state="disabled", text="启动中…")
        self.state.config(text="正在注入", fg=DIM)
        threading.Thread(target=self._work, args=(exe, groups), daemon=True).start()

    def _work(self, exe: str, groups):
        try:
            unlock.run(exe, log=lambda m: self.queue.put(m), groups=groups)
            self.queue.put(("__ok__", "已解锁，启动器正在启动"))
        except Exception as exc:   # noqa: BLE001
            self.queue.put(("__err__", str(exc)))
            self.queue.put(f"完整堆栈：{unlock.dump_trace(exc)}")

    def _drain(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, tuple):
                    kind, msg = item
                    if kind == "__ok__":
                        self.state.config(text=msg, fg=OK)
                        self._log("— " + msg)
                    else:
                        self.state.config(text="失败", fg=ERR)
                        self._log("! " + msg)
                    self.busy = False
                    self.btn.config(state="normal", text="启动并解锁")
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)


def main():
    try:   # 高 DPI 下字别糊
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:   # noqa: BLE001
        pass
    if not unlock.is_admin() and not unlock.skip_elevate():
        if unlock.relaunch_as_admin():
            return
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("需要管理员权限",
                             "启动器自身要求管理员权限，本工具也必须以管理员身份运行。\n"
                             "请在弹窗里点是，或右键→以管理员身份运行。")
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
