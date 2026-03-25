#!/usr/bin/env python3
"""
XFreeRDP GUI - A graphical frontend for FreeRDP on Linux
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import json
import os
import shutil
from pathlib import Path

try:
    import sv_ttk
    _SV_TTK = True
except ImportError:
    _SV_TTK = False


def _detect_system_dark() -> bool:
    """Return True if the desktop colour-scheme is set to dark."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        )
        return "dark" in result.stdout.lower()
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            capture_output=True, text=True, timeout=2,
        )
        return "dark" in result.stdout.lower()
    except Exception:
        pass
    return False

CONFIG_DIR = Path.home() / ".config" / "xfreerdp-gui"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Drive-redirection dialog
# ─────────────────────────────────────────────────────────────────────────────
class DriveDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Drive Redirection")
        self.geometry("360x155")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()

        f = ttk.Frame(self, padding=15)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="Share name:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.name_var = tk.StringVar(value="share")
        ttk.Entry(f, textvariable=self.name_var, width=22).grid(
            row=0, column=1, sticky=tk.EW, padx=(10, 0), pady=4
        )

        ttk.Label(f, text="Local path:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.path_var = tk.StringVar()
        path_row = ttk.Frame(f)
        path_row.grid(row=1, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        ttk.Entry(path_row, textvariable=self.path_var, width=22).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(
            path_row,
            text="…",
            width=3,
            command=lambda: self.path_var.set(
                filedialog.askdirectory(title="Select folder") or self.path_var.get()
            ),
        ).pack(side=tk.LEFT, padx=(3, 0))

        btn = ttk.Frame(f)
        btn.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

        f.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

    def _ok(self):
        name = self.name_var.get().strip()
        path = self.path_var.get().strip()
        if name and path:
            self.result = f"{name},{path}"
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────
class XFreeRDPApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("XFreeRDP GUI")
        self.geometry("800x720")
        self.minsize(800, 720)

        ensure_config_dir()
        self.profiles = self._load_profiles()
        self._dark_mode = self._load_theme_setting()

        self._apply_theme()
        self._set_window_icon()
        self._build_ui()
        self._refresh_command_preview()

    # ── Window icon ─────────────────────────────────────────────────────
    def _set_window_icon(self):
        src = Path(__file__).parent / "icon.svg"
        dst = Path(__file__).parent / "icon.png"
        if not dst.exists() and src.exists():
            for cmd in (
                ["rsvg-convert", "-w", "64", "-h", "64", "-o", str(dst), str(src)],
                ["convert", "-background", "none", str(src), "-resize", "64x64", str(dst)],
                ["inkscape", "--export-type=png", f"--export-filename={dst}",
                 "--export-width=64", "--export-height=64", str(src)],
            ):
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    if result.returncode == 0 and dst.exists():
                        break
                except Exception:
                    pass
        if dst.exists():
            try:
                img = tk.PhotoImage(file=str(dst))
                self.iconphoto(True, img)
                self._icon_img = img  # prevent garbage collection
            except Exception:
                pass

    # ── Theme ──────────────────────────────────────────────────────────────
    def _apply_theme(self):
        if _SV_TTK:
            sv_ttk.set_theme("dark" if self._dark_mode else "light", self)
        else:
            self._apply_manual_theme()
        style = ttk.Style(self)
        style.configure("TNotebook.Tab", padding=[10, 4])
        style.configure("Connect.TButton", font=("", 10, "bold"))

    def _apply_manual_theme(self):
        """Fallback dark/light colouring when sv-ttk is not available."""
        style = ttk.Style(self)
        if self._dark_mode:
            bg, fg   = "#2b2b2b", "#e0e0e0"
            ebg, efg = "#3c3c3c", "#e0e0e0"
            selbg    = "#0062cc"
            trough   = "#404040"
            self.configure(bg=bg)
            style.theme_use("clam")
            style.configure(".",            background=bg, foreground=fg, fieldbackground=ebg)
            style.configure("TFrame",       background=bg)
            style.configure("TLabel",       background=bg, foreground=fg)
            style.configure("TLabelframe",  background=bg, foreground=fg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg)
            style.configure("TNotebook",    background=bg)
            style.configure("TNotebook.Tab",background=bg, foreground=fg)
            style.map("TNotebook.Tab",      background=[("selected", selbg)], foreground=[("selected", "#ffffff")])
            style.configure("TEntry",       fieldbackground=ebg, foreground=efg, insertcolor=fg)
            style.configure("TCombobox",    fieldbackground=ebg, foreground=efg, selectbackground=selbg)
            style.configure("TButton",      background="#4a4a4a", foreground=fg)
            style.map("TButton",            background=[("active", "#5a5a5a")])
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TScrollbar",   background=bg, troughcolor=trough)
        else:
            style.theme_use("clam")

    def _toggle_dark_mode(self):
        self._dark_mode = not self._dark_mode
        self._apply_theme()
        self._update_cmd_text_colors()
        label = "☀ Light" if self._dark_mode else "☾ Dark"
        self._theme_btn.config(text=label)
        self._save_theme_setting()

    def _update_cmd_text_colors(self):
        if hasattr(self, "cmd_text"):
            if self._dark_mode:
                self.cmd_text.config(background="#1e1e2e", foreground="#cdd6f4")
            else:
                self.cmd_text.config(background="#f5f5f5", foreground="#1a1a1a")

    # ── Layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        root_pad = ttk.Frame(self, padding=10)
        root_pad.pack(fill=tk.BOTH, expand=True)

        self._build_profile_bar(root_pad)

        self.notebook = ttk.Notebook(root_pad)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self._build_connection_tab()
        self._build_display_tab()
        self._build_network_tab()
        self._build_features_tab()
        self._build_security_tab()
        self._build_advanced_tab()

        self._build_command_preview(root_pad)
        self._build_bottom_buttons(root_pad)

    # ── Profile bar ────────────────────────────────────────────────────────
    def _build_profile_bar(self, parent):
        bar = ttk.LabelFrame(parent, text="Profile", padding=(8, 4))
        bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(bar, text="Name:").pack(side=tk.LEFT, padx=(0, 4))
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(bar, textvariable=self.profile_var, width=26)
        self.profile_combo.pack(side=tk.LEFT, padx=(0, 4))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        self._refresh_profile_list()

        ttk.Button(bar, text="💾 Save",   command=self._save_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="📂 Load",   command=self._load_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="🗑️  Delete", command=self._delete_profile).pack(side=tk.LEFT, padx=2)

    # ── Connection tab ─────────────────────────────────────────────────────
    def _build_connection_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🔌 Connection")
        g = ttk.Frame(frame, padding=14)
        g.pack(fill=tk.BOTH, expand=True)

        fields = [
            ("Server  (/v:) *",  "server_var",  "", 30),
            ("Port    (/port:)", "port_var",   "3389", 8),
            ("Username (/u:)",   "user_var",   "", 26),
            ("Domain  (/d:)",    "domain_var", "", 26),
            ("Gateway (/g:)",    "gateway_var","", 30),
        ]
        for row, (label, attr, default, width) in enumerate(fields):
            ttk.Label(g, text=label).grid(row=row, column=0, sticky=tk.W, pady=5, padx=(0, 10))
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(g, textvariable=var, width=width).grid(row=row, column=1, sticky=tk.W, pady=5)
            var.trace_add("write", self._refresh_command_preview)

        # Password row (special – show/hide toggle)
        pw_row = len(fields)
        ttk.Label(g, text="Password (/p:)").grid(row=pw_row, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.pass_var = tk.StringVar()
        self.pass_var.trace_add("write", self._refresh_command_preview)
        pw_entry = ttk.Entry(g, textvariable=self.pass_var, width=26, show="●")
        pw_entry.grid(row=pw_row, column=1, sticky=tk.W, pady=5)
        self.show_pass = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            g, text="Show",
            variable=self.show_pass,
            command=lambda: pw_entry.config(show="" if self.show_pass.get() else "●"),
        ).grid(row=pw_row, column=2, padx=(8, 0), sticky=tk.W)

        # Security note about passwords in CLI
        note = ttk.Label(
            g,
            text="⚠  Password will be visible in the process list.",
            foreground="#c0392b",
        )
        note.grid(row=pw_row + 1, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))

        g.columnconfigure(1, weight=1)

    # ── Display tab ────────────────────────────────────────────────────────
    def _build_display_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🖥️  Display")
        g = ttk.Frame(frame, padding=14)
        g.pack(fill=tk.BOTH, expand=True)

        row = 0

        self.fullscreen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            g, text="Fullscreen  (/f)",
            variable=self.fullscreen_var, command=self._refresh_command_preview,
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=4)
        row += 1

        self.dynres_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            g, text="Dynamic Resolution  (/dynamic-resolution)",
            variable=self.dynres_var, command=self._refresh_command_preview,
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=4)
        row += 1

        # Width / Height
        for label, attr, default in [
            ("Width  (/w:)",  "width_var",  "1920"),
            ("Height (/h:)",  "height_var", "1080"),
        ]:
            ttk.Label(g, text=label).grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(g, textvariable=var, width=8).grid(row=row, column=1, sticky=tk.W, pady=4)
            var.trace_add("write", self._refresh_command_preview)
            row += 1

        # Color depth
        ttk.Label(g, text="Color depth (/bpp:)").grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.bpp_var = tk.StringVar(value="32")
        ttk.Combobox(
            g, textvariable=self.bpp_var,
            values=["8", "15", "16", "24", "32"], width=6, state="readonly",
        ).grid(row=row, column=1, sticky=tk.W, pady=4)
        self.bpp_var.trace_add("write", self._refresh_command_preview)
        row += 1

        # Checkboxes
        bool_flags = [
            ("GFX acceleration  (/gfx)",       "gfx_var",         True),
            ("RemoteFX  (/rfx)",               "rfx_var",         False),
            ("Smart sizing  (/smart-sizing)",  "smart_sizing_var", False),
            ("Multi-monitor  (/multimon)",     "multimon_var",    False),
            ("Span monitors  (/span)",         "span_var",        False),
        ]
        for label, attr, default in bool_flags:
            var = tk.BooleanVar(value=default)
            setattr(self, attr, var)
            ttk.Checkbutton(
                g, text=label, variable=var, command=self._refresh_command_preview,
            ).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=3)
            row += 1

        g.columnconfigure(1, weight=1)

    # ── Network tab ────────────────────────────────────────────────────────
    def _build_network_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🌐 Network")
        g = ttk.Frame(frame, padding=14)
        g.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(g, text="Network type  (/network:)").grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.network_var = tk.StringVar(value="lan")
        ttk.Combobox(
            g, textvariable=self.network_var,
            values=["modem", "broadband-low", "satellite", "broadband-high", "wan", "lan", "autodetect"],
            width=15, state="readonly",
        ).grid(row=row, column=1, sticky=tk.W, pady=4)
        self.network_var.trace_add("write", self._refresh_command_preview)
        row += 1

        bool_net = [
            ("Compression  (+compression)",           "compression_var",   False),
            ("Auto-reconnect  (+auto-reconnect)",     "autoreconnect_var",  True),
        ]
        for label, attr, default in bool_net:
            var = tk.BooleanVar(value=default)
            setattr(self, attr, var)
            ttk.Checkbutton(
                g, text=label, variable=var, command=self._refresh_command_preview,
            ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=4)
            row += 1

        ttk.Label(g, text="Max reconnect retries  (/auto-reconnect-max-retries:)").grid(
            row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10)
        )
        self.reconnect_retries_var = tk.StringVar(value="20")
        ttk.Entry(g, textvariable=self.reconnect_retries_var, width=6).grid(
            row=row, column=1, sticky=tk.W, pady=4
        )
        self.reconnect_retries_var.trace_add("write", self._refresh_command_preview)

        g.columnconfigure(1, weight=1)

    # ── Features tab ───────────────────────────────────────────────────────
    def _build_features_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="✨ Features")
        g = ttk.Frame(frame, padding=14)
        g.pack(fill=tk.BOTH, expand=True)

        row = 0
        bool_feats = [
            ("Clipboard redirection  (+clipboard)",  "clipboard_var",  True),
            ("Audio playback  (/sound)",             "sound_var",      False),
            ("Microphone  (/microphone)",            "mic_var",        False),
            ("Printer  (/printer)",                  "printer_var",    False),
            ("USB redirection  (/usb:id)",           "usb_var",        False),
        ]
        for label, attr, default in bool_feats:
            var = tk.BooleanVar(value=default)
            setattr(self, attr, var)
            ttk.Checkbutton(
                g, text=label, variable=var, command=self._refresh_command_preview,
            ).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=3)
            row += 1

        # Drive redirection
        ttk.Separator(g, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=8
        )
        row += 1
        ttk.Label(g, text="Drive redirection  (/drive:name,path)").grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 4)
        )
        row += 1

        drives_frame = ttk.Frame(g)
        drives_frame.grid(row=row, column=0, columnspan=3, sticky=tk.EW)
        self.drives_listbox = tk.Listbox(drives_frame, height=5, selectmode=tk.SINGLE)
        self.drives_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(drives_frame, orient=tk.VERTICAL, command=self.drives_listbox.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        self.drives_listbox.configure(yscrollcommand=scrollbar.set)
        dr_btns = ttk.Frame(drives_frame)
        dr_btns.pack(side=tk.LEFT, padx=(6, 0), anchor=tk.N)
        ttk.Button(dr_btns, text="➕ Add",    command=self._add_drive).pack(pady=2, fill=tk.X)
        ttk.Button(dr_btns, text="➖ Remove", command=self._remove_drive).pack(pady=2, fill=tk.X)
        row += 1

        # RemoteApp
        ttk.Separator(g, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=8
        )
        row += 1
        ttk.Label(g, text="Remote App  (/app:)").grid(
            row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10)
        )
        self.app_var = tk.StringVar()
        ttk.Entry(g, textvariable=self.app_var, width=36).grid(
            row=row, column=1, sticky=tk.EW, pady=4
        )
        self.app_var.trace_add("write", self._refresh_command_preview)

        g.columnconfigure(1, weight=1)

    # ── Security tab ───────────────────────────────────────────────────────
    def _build_security_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🔒 Security")
        g = ttk.Frame(frame, padding=14)
        g.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(g, text="Certificate  (/cert:)").grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.cert_var = tk.StringVar(value="ignore")
        ttk.Combobox(
            g, textvariable=self.cert_var,
            values=["ignore", "tofu", "deny"],
            width=16,
        ).grid(row=row, column=1, sticky=tk.W, pady=4)
        self.cert_var.trace_add("write", self._refresh_command_preview)
        row += 1

        ttk.Label(g, text="Security protocol  (/sec:)").grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.sec_var = tk.StringVar(value="")
        ttk.Combobox(
            g, textvariable=self.sec_var,
            values=["", "rdp", "tls", "nla", "ext"],
            width=8, state="readonly",
        ).grid(row=row, column=1, sticky=tk.W, pady=4)
        self.sec_var.trace_add("write", self._refresh_command_preview)
        row += 1

        bool_sec = [
            ("Disable authentication  (/authentication:0)", "noauth_var",  False),
            ("Admin / console session  (/admin)",           "admin_var",   False),
        ]
        for label, attr, default in bool_sec:
            var = tk.BooleanVar(value=default)
            setattr(self, attr, var)
            ttk.Checkbutton(
                g, text=label, variable=var, command=self._refresh_command_preview,
            ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=4)
            row += 1

        g.columnconfigure(1, weight=1)

    # ── Advanced tab ───────────────────────────────────────────────────────
    def _build_advanced_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="⚙️  Advanced")
        g = ttk.Frame(frame, padding=14)
        g.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(g, text="Extra flags:").grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.extra_flags_var = tk.StringVar()
        ttk.Entry(g, textvariable=self.extra_flags_var, width=46).grid(
            row=row, column=1, columnspan=2, sticky=tk.EW, pady=4
        )
        self.extra_flags_var.trace_add("write", self._refresh_command_preview)
        row += 1

        ttk.Label(g, text="xfreerdp binary:").grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.binary_var = tk.StringVar(value=self._find_xfreerdp())
        bin_frame = ttk.Frame(g)
        bin_frame.grid(row=row, column=1, columnspan=2, sticky=tk.EW, pady=4)
        ttk.Entry(bin_frame, textvariable=self.binary_var, width=36).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(bin_frame, text="Browse…", command=self._browse_binary).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self.binary_var.trace_add("write", self._refresh_command_preview)

        g.columnconfigure(1, weight=1)

    # ── Command preview ────────────────────────────────────────────────────
    def _build_command_preview(self, parent):
        self._preview_visible = True  # start packed, then hide below if needed
        self._preview_lf = ttk.LabelFrame(parent, text="Command preview", padding=(6, 4))
        self._preview_lf.pack(fill=tk.X, pady=(8, 0))

        cmd_bg = "#1e1e2e" if self._dark_mode else "#f5f5f5"
        cmd_fg = "#cdd6f4" if self._dark_mode else "#1a1a1a"
        self.cmd_text = tk.Text(
            self._preview_lf,
            height=3,
            wrap=tk.WORD,
            state=tk.DISABLED,
            background=cmd_bg,
            foreground=cmd_fg,
            insertbackground=cmd_fg,
            font=("Monospace", 9),
            relief=tk.FLAT,
            padx=6,
            pady=4,
        )
        self.cmd_text.pack(fill=tk.X)
        ttk.Button(self._preview_lf, text="📋 Copy to clipboard", command=self._copy_command).pack(
            anchor=tk.E, pady=(4, 2)
        )

    def _apply_initial_preview_state(self):
        """Called after bottom bar is built so before= reference is valid."""
        if not self._load_settings().get("preview_visible", False):
            self._preview_lf.pack_forget()
            self._preview_visible = False
            self._preview_btn.config(text="👁️  Show")
        else:
            self._preview_btn.config(text="👁️  Hide")

    def _toggle_preview(self):
        if self._preview_visible:
            self._preview_lf.pack_forget()
            self._preview_btn.config(text="👁️  Show")
        else:
            self._preview_lf.pack(fill=tk.X, pady=(8, 0), before=self._bottom_bar)
            self._preview_btn.config(text="👁️  Hide")
        self._preview_visible = not self._preview_visible
        self._save_settings()

    # ── Bottom buttons ─────────────────────────────────────────────────────
    def _build_bottom_buttons(self, parent):
        self._bottom_bar = ttk.Frame(parent)
        self._bottom_bar.pack(fill=tk.X, pady=(8, 0))

        ttk.Button(self._bottom_bar, text="⛔ Quit", command=self.quit).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(
            self._bottom_bar,
            text="🔗 Connect",
            command=self._connect,
            style="Connect.TButton",
        ).pack(side=tk.RIGHT)

        theme_label = "☀ Light" if self._dark_mode else "☾ Dark"
        self._theme_btn = ttk.Button(self._bottom_bar, text=theme_label, command=self._toggle_dark_mode, width=9)
        self._theme_btn.pack(side=tk.LEFT)

        self._preview_btn = ttk.Button(self._bottom_bar, text="👁️  Show", command=self._toggle_preview, width=10)
        self._preview_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._apply_initial_preview_state()
    # ── Helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _find_xfreerdp():
        for candidate in ("xfreerdp3", "xfreerdp", "/usr/bin/xfreerdp", "/usr/local/bin/xfreerdp"):
            found = shutil.which(candidate)
            if found:
                return found
        return "xfreerdp"

    def _browse_binary(self):
        path = filedialog.askopenfilename(
            title="Select xfreerdp binary",
            initialdir="/usr/bin",
        )
        if path:
            self.binary_var.set(path)

    def _add_drive(self):
        dlg = DriveDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self.drives_listbox.insert(tk.END, dlg.result)
            self._refresh_command_preview()

    def _remove_drive(self):
        sel = self.drives_listbox.curselection()
        if sel:
            self.drives_listbox.delete(sel[0])
            self._refresh_command_preview()

    # ── Command builder ────────────────────────────────────────────────────
    def _build_command(self):
        cmd = [self.binary_var.get() or "xfreerdp"]

        server = self.server_var.get().strip()
        if server:
            port = self.port_var.get().strip()
            if port and port != "3389":
                cmd.append(f"/v:{server}:{port}")
            else:
                cmd.append(f"/v:{server}")

        user = self.user_var.get().strip()
        if user:
            cmd.append(f"/u:{user}")

        password = self.pass_var.get()
        if password:
            cmd.append(f"/p:{password}")

        domain = self.domain_var.get().strip()
        if domain:
            cmd.append(f"/d:{domain}")

        gateway = self.gateway_var.get().strip()
        if gateway:
            cmd.append(f"/g:{gateway}")

        # ── Display ──
        if self.fullscreen_var.get():
            cmd.append("/f")
        else:
            w = self.width_var.get().strip()
            h = self.height_var.get().strip()
            if w:
                cmd.append(f"/w:{w}")
            if h:
                cmd.append(f"/h:{h}")

        if self.dynres_var.get():
            cmd.append("/dynamic-resolution")

        bpp = self.bpp_var.get().strip()
        if bpp and bpp != "32":
            cmd.append(f"/bpp:{bpp}")

        if self.gfx_var.get():
            cmd.append("/gfx")
        if self.rfx_var.get():
            cmd.append("/rfx")
        if self.smart_sizing_var.get():
            cmd.append("/smart-sizing")
        if self.multimon_var.get():
            cmd.append("/multimon")
        if self.span_var.get():
            cmd.append("/span")

        # ── Network ──
        network = self.network_var.get().strip()
        if network:
            cmd.append(f"/network:{network}")
        if self.compression_var.get():
            cmd.append("+compression")
        if self.autoreconnect_var.get():
            cmd.append("+auto-reconnect")
            retries = self.reconnect_retries_var.get().strip()
            if retries and retries != "20":
                cmd.append(f"/auto-reconnect-max-retries:{retries}")

        # ── Features ──
        if self.clipboard_var.get():
            cmd.append("+clipboard")
        if self.sound_var.get():
            cmd.append("/sound")
        if self.mic_var.get():
            cmd.append("/microphone")
        if self.printer_var.get():
            cmd.append("/printer")
        if self.usb_var.get():
            cmd.append("/usb:id")

        for i in range(self.drives_listbox.size()):
            cmd.append(f"/drive:{self.drives_listbox.get(i)}")

        app = self.app_var.get().strip()
        if app:
            cmd.append(f"/app:{app}")

        # ── Security ──
        cert = self.cert_var.get().strip()
        if cert:
            cmd.append(f"/cert:{cert}")
        sec = self.sec_var.get().strip()
        if sec:
            cmd.append(f"/sec:{sec}")
        if self.noauth_var.get():
            cmd.append("/authentication:0")
        if self.admin_var.get():
            cmd.append("/admin")

        # ── Extra ──
        extra = self.extra_flags_var.get().strip()
        if extra:
            cmd.extend(extra.split())

        return cmd

    def _refresh_command_preview(self, *_args):
        cmd_str = " ".join(self._build_command())
        self.cmd_text.config(state=tk.NORMAL)
        self.cmd_text.delete("1.0", tk.END)
        self.cmd_text.insert("1.0", cmd_str)
        self.cmd_text.config(state=tk.DISABLED)

    def _copy_command(self):
        self.clipboard_clear()
        self.clipboard_append(" ".join(self._build_command()))
        messagebox.showinfo("Copied", "Command copied to clipboard.")

    def _connect(self):
        if not self.server_var.get().strip():
            messagebox.showerror("Validation", "Server address is required.")
            return
        cmd = self._build_command()
        try:
            subprocess.Popen(cmd)  # noqa: S603 – user-controlled binary path
        except FileNotFoundError:
            messagebox.showerror(
                "Not found",
                f"Could not find xfreerdp at:\n  {self.binary_var.get()}\n\n"
                "Install FreeRDP or set the correct path in the Advanced tab.",
            )
        except Exception as exc:
            messagebox.showerror("Launch failed", f"Could not launch xfreerdp:\n{exc}")

    # ── Profile management ─────────────────────────────────────────────────
    def _refresh_profile_list(self):
        self.profile_combo["values"] = sorted(self.profiles.keys())

    def _get_current_config(self):
        return {
            "server":            self.server_var.get(),
            "port":              self.port_var.get(),
            "user":              self.user_var.get(),
            "password":          self.pass_var.get(),
            "domain":            self.domain_var.get(),
            "gateway":           self.gateway_var.get(),
            "fullscreen":        self.fullscreen_var.get(),
            "dynres":            self.dynres_var.get(),
            "width":             self.width_var.get(),
            "height":            self.height_var.get(),
            "bpp":               self.bpp_var.get(),
            "gfx":               self.gfx_var.get(),
            "rfx":               self.rfx_var.get(),
            "smart_sizing":      self.smart_sizing_var.get(),
            "multimon":          self.multimon_var.get(),
            "span":              self.span_var.get(),
            "network":           self.network_var.get(),
            "compression":       self.compression_var.get(),
            "autoreconnect":     self.autoreconnect_var.get(),
            "reconnect_retries": self.reconnect_retries_var.get(),
            "clipboard":         self.clipboard_var.get(),
            "sound":             self.sound_var.get(),
            "mic":               self.mic_var.get(),
            "printer":           self.printer_var.get(),
            "usb":               self.usb_var.get(),
            "drives":            [self.drives_listbox.get(i) for i in range(self.drives_listbox.size())],
            "app":               self.app_var.get(),
            "cert":              self.cert_var.get(),
            "sec":               self.sec_var.get(),
            "noauth":            self.noauth_var.get(),
            "admin":             self.admin_var.get(),
            "extra_flags":       self.extra_flags_var.get(),
            "binary":            self.binary_var.get(),
        }

    def _apply_config(self, cfg):
        self.server_var.set(cfg.get("server", ""))
        self.port_var.set(cfg.get("port", "3389"))
        self.user_var.set(cfg.get("user", ""))
        self.pass_var.set(cfg.get("password", ""))
        self.domain_var.set(cfg.get("domain", ""))
        self.gateway_var.set(cfg.get("gateway", ""))
        self.fullscreen_var.set(cfg.get("fullscreen", False))
        self.dynres_var.set(cfg.get("dynres", True))
        self.width_var.set(cfg.get("width", "1920"))
        self.height_var.set(cfg.get("height", "1080"))
        self.bpp_var.set(cfg.get("bpp", "32"))
        self.gfx_var.set(cfg.get("gfx", True))
        self.rfx_var.set(cfg.get("rfx", False))
        self.smart_sizing_var.set(cfg.get("smart_sizing", False))
        self.multimon_var.set(cfg.get("multimon", False))
        self.span_var.set(cfg.get("span", False))
        self.network_var.set(cfg.get("network", "lan"))
        self.compression_var.set(cfg.get("compression", False))
        self.autoreconnect_var.set(cfg.get("autoreconnect", True))
        self.reconnect_retries_var.set(cfg.get("reconnect_retries", "20"))
        self.clipboard_var.set(cfg.get("clipboard", True))
        self.sound_var.set(cfg.get("sound", False))
        self.mic_var.set(cfg.get("mic", False))
        self.printer_var.set(cfg.get("printer", False))
        self.usb_var.set(cfg.get("usb", False))
        self.drives_listbox.delete(0, tk.END)
        for d in cfg.get("drives", []):
            self.drives_listbox.insert(tk.END, d)
        self.app_var.set(cfg.get("app", ""))
        self.cert_var.set(cfg.get("cert", "ignore"))
        self.sec_var.set(cfg.get("sec", ""))
        self.noauth_var.set(cfg.get("noauth", False))
        self.admin_var.set(cfg.get("admin", False))
        self.extra_flags_var.set(cfg.get("extra_flags", ""))
        self.binary_var.set(cfg.get("binary", self._find_xfreerdp()))
        self._refresh_command_preview()

    def _save_profile(self):
        name = self.profile_var.get().strip()
        if not name:
            messagebox.showerror("Validation", "Enter a profile name first.")
            return
        self.profiles[name] = self._get_current_config()
        self._write_profiles()
        self._refresh_profile_list()
        messagebox.showinfo("Saved", f"Profile «{name}» saved.")

    def _load_profile(self):
        name = self.profile_var.get().strip()
        if name not in self.profiles:
            messagebox.showerror("Not found", f"No profile named «{name}».")
            return
        self._apply_config(self.profiles[name])

    def _on_profile_selected(self, _event=None):
        name = self.profile_var.get().strip()
        if name in self.profiles:
            self._apply_config(self.profiles[name])

    def _delete_profile(self):
        name = self.profile_var.get().strip()
        if name not in self.profiles:
            messagebox.showerror("Not found", f"No profile named «{name}».")
            return
        if messagebox.askyesno("Confirm delete", f"Delete profile «{name}»?"):
            del self.profiles[name]
            self._write_profiles()
            self._refresh_profile_list()
            self.profile_var.set("")

    def _load_profiles(self):
        if PROFILES_FILE.exists():
            try:
                with open(PROFILES_FILE) as fh:
                    return json.load(fh)
            except Exception:
                pass
        return {}

    def _write_profiles(self):
        with open(PROFILES_FILE, "w") as fh:
            json.dump(self.profiles, fh, indent=2)

    def _load_theme_setting(self) -> bool:
        return self._load_settings().get("dark_mode", _detect_system_dark())

    def _save_theme_setting(self):
        self._save_settings()

    def _load_settings(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE) as fh:
                    return json.load(fh)
            except Exception:
                pass
        return {}

    def _save_settings(self):
        data = self._load_settings()
        data["dark_mode"] = self._dark_mode
        data["preview_visible"] = self._preview_visible if hasattr(self, "_preview_visible") else False
        with open(SETTINGS_FILE, "w") as fh:
            json.dump(data, fh)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = XFreeRDPApp()
    app.mainloop()
