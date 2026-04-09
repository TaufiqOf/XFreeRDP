#!/usr/bin/env python3
"""
XFreeRDP GUI - A graphical frontend for FreeRDP on Linux
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont
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
# Tooltip helper
# ─────────────────────────────────────────────────────────────────────────────
class Tooltip:
    """Simple hover tooltip for any tkinter widget."""

    def __init__(self, widget, text: str):
        self._widget = widget
        self._text = text
        self._tip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self._tip_window or not self._text:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip_window = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw,
            text=self._text,
            background="#ffffe0",
            foreground="#1a1a1a",
            relief=tk.SOLID,
            borderwidth=1,
            font=("", 8),
            padx=6,
            pady=3,
            wraplength=300,
            justify=tk.LEFT,
        ).pack()

    def _hide(self, _event=None):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


# ─────────────────────────────────────────────────────────────────────────────
# Drive-redirection dialog
# ─────────────────────────────────────────────────────────────────────────────
class DriveDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Drive Redirection")
        dialog_w = parent._scaled(360)
        dialog_h = parent._scaled(170)
        self.geometry(f"{dialog_w}x{dialog_h}")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()

        f = ttk.Frame(self, padding=parent._scaled(15))
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
        self._init_display_scaling()
        self._apply_global_font_scaling()
        self._set_initial_window_size()

        ensure_config_dir()
        self.profiles = self._load_profiles()
        self._dark_mode = self._load_theme_setting()

        self._apply_theme()
        self._set_window_icon()
        self._build_ui()
        self._refresh_command_preview()

        # Global keyboard shortcuts
        self.bind("<Control-Return>", lambda _: self._connect())
        self.bind("<Control-s>",      lambda _: self._save_profile())

    def _init_display_scaling(self):
        """Capture Tk scaling and expose a helper for scaled UI metrics."""
        baseline = 96.0 / 72.0
        try:
            tk_scaling = float(self.tk.call("tk", "scaling"))
        except Exception:
            tk_scaling = baseline

        tk_scale = max(1.0, tk_scaling / baseline)
        desktop_scale = self._detect_display_scale_hint()
        override_scale = self._read_ui_scale_override()
        self._ui_scale = max(1.0, override_scale or 1.0, tk_scale, desktop_scale)

        # On some Linux fractional-scaling setups Tk reports 1.0; force a better value.
        target_tk_scaling = baseline * self._ui_scale
        if target_tk_scaling > tk_scaling + 0.01:
            try:
                self.tk.call("tk", "scaling", target_tk_scaling)
            except Exception:
                pass

    def _read_ui_scale_override(self) -> float:
        """Optional explicit override from env or settings.json (ui_scale)."""
        raw_env = os.environ.get("XFREERDP_GUI_SCALE", "").strip()
        if raw_env:
            try:
                env_scale = float(raw_env)
            except ValueError:
                env_scale = 0.0
            if env_scale > 0:
                return env_scale

        cfg = self._load_settings()
        raw_cfg = cfg.get("ui_scale")
        if raw_cfg is None:
            return 0.0
        try:
            cfg_scale = float(raw_cfg)
        except (TypeError, ValueError):
            return 0.0
        return cfg_scale if cfg_scale > 0 else 0.0

    @staticmethod
    def _parse_gsettings_number(raw: str) -> float | None:
        txt = raw.strip().replace("'", "")
        # Handles outputs like: "1.25", "uint32 2", "0.9"
        for token in txt.split():
            try:
                return float(token)
            except ValueError:
                continue
        return None

    def _gsettings_number(self, schema: str, key: str) -> float | None:
        try:
            result = subprocess.run(
                ["gsettings", "get", schema, key],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return self._parse_gsettings_number(result.stdout)

    def _detect_display_scale_hint(self) -> float:
        scale = 1.0

        text_scale = self._gsettings_number(
            "org.gnome.desktop.interface", "text-scaling-factor"
        )
        if text_scale and text_scale > 0:
            scale = max(scale, text_scale)

        gnome_scale = self._gsettings_number(
            "org.gnome.desktop.interface", "scaling-factor"
        )
        if gnome_scale and gnome_scale > 1:
            scale = max(scale, gnome_scale)

        for env_key in ("GDK_SCALE", "QT_SCALE_FACTOR"):
            raw = os.environ.get(env_key)
            if not raw:
                continue
            try:
                env_scale = float(raw)
            except ValueError:
                continue
            if env_scale > 0:
                scale = max(scale, env_scale)

        # X11 desktops often expose effective text DPI here (e.g. 120 => 125%).
        xft_scale = self._read_xft_dpi_scale()
        if xft_scale > 0:
            scale = max(scale, xft_scale)

        return scale

    @staticmethod
    def _read_xft_dpi_scale() -> float:
        try:
            result = subprocess.run(
                ["xrdb", "-query"], capture_output=True, text=True, timeout=2
            )
        except Exception:
            return 0.0
        if result.returncode != 0:
            return 0.0

        for line in result.stdout.splitlines():
            if not line.lower().startswith("xft.dpi"):
                continue
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            try:
                dpi = float(parts[1].strip())
            except ValueError:
                continue
            if dpi > 0:
                return dpi / 96.0
        return 0.0

    def _scaled(self, value: int) -> int:
        return max(1, int(round(value * self._ui_scale)))

    def _apply_global_font_scaling(self):
        """Ensure named fonts are available; Tk scaling already handles font sizing."""
        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
            "TkFixedFont",
        ):
            try:
                tkfont.nametofont(font_name)
            except tk.TclError:
                continue

    def _set_initial_window_size(self):
        base_w = self._scaled(870)
        base_h = self._scaled(800)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Keep the initial window fully visible on fractional scaling setups.
        win_w = min(base_w, int(screen_w * 0.96))
        win_h = min(base_h, int(screen_h * 0.92))
        min_w = min(win_w, self._scaled(870))
        min_h = min(win_h, self._scaled(800))

        self.geometry(f"{win_w}x{win_h}")
        self.minsize(min_w, min_h)

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

        # Theme switches can reset font defaults, so apply scaling afterwards.
        self._apply_global_font_scaling()

        style = ttk.Style(self)
        # Build app-wide fonts from the already-scaled named fonts.
        base_font = tkfont.nametofont("TkDefaultFont").copy()
        bold_font = base_font.copy()
        bold_font.configure(weight="bold")
        mono_font = tkfont.nametofont("TkFixedFont").copy()
        self._app_font = base_font
        self._app_bold_font = bold_font
        self._app_mono_font = mono_font

        # Apply the same default font to all common ttk styles.
        style.configure(".", font=self._app_font)
        style.configure("TLabel", font=self._app_font)
        style.configure("TButton", font=self._app_font)
        style.configure("TCheckbutton", font=self._app_font)
        style.configure("TEntry", font=self._app_font)
        style.configure("TCombobox", font=self._app_font)
        style.configure("TLabelframe", font=self._app_font)
        style.configure("TLabelframe.Label", font=self._app_font)
        style.configure("TNotebook.Tab", padding=[self._scaled(12), self._scaled(5)], font=self._app_font)

        # Apply to classic Tk widgets as well.
        self.option_add("*Font", self._app_font)
        self.option_add("*Listbox.Font", self._app_font)

        # Keep Connect button emphasis while matching the base UI font size.
        style.configure("Connect.TButton", font=self._app_bold_font)

        style.configure("Shortcut.TLabel", font=self._app_bold_font)

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
            style.configure(".",                  background=bg, foreground=fg, fieldbackground=ebg)
            style.configure("TFrame",             background=bg)
            style.configure("TLabel",             background=bg, foreground=fg)
            style.configure("TLabelframe",        background=bg, foreground=fg)
            style.configure("TLabelframe.Label",  background=bg, foreground=fg)
            style.configure("TNotebook",          background=bg)
            style.configure("TNotebook.Tab",      background=bg, foreground=fg)
            style.map("TNotebook.Tab",            background=[("selected", selbg)],
                                                  foreground=[("selected", "#ffffff")])
            style.configure("TEntry",             fieldbackground=ebg, foreground=efg, insertcolor=fg)
            style.configure("TCombobox",          fieldbackground=ebg, foreground=efg,
                                                  selectbackground=selbg)
            style.configure("TButton",            background="#4a4a4a", foreground=fg)
            style.map("TButton",                  background=[("active", "#5a5a5a")])
            style.configure("TCheckbutton",       background=bg, foreground=fg)
            style.configure("TScrollbar",         background=bg, troughcolor=trough)
            style.configure(
                "Shortcut.TLabel",
                background=bg,
                foreground=fg,
                font=("", self._scaled(9), "bold"),
            )
        else:
            style.theme_use("clam")
            style.configure("Shortcut.TLabel", font=("", self._scaled(9), "bold"))

    def _toggle_dark_mode(self):
        self._dark_mode = not self._dark_mode
        self._apply_theme()
        self._update_cmd_text_colors()
        self._theme_btn.config(text="☀ Light" if self._dark_mode else "☾ Dark")
        self._save_theme_setting()

    def _update_cmd_text_colors(self):
        if hasattr(self, "cmd_text"):
            if self._dark_mode:
                self.cmd_text.config(background="#1e1e2e", foreground="#cdd6f4")
            else:
                self.cmd_text.config(background="#f5f5f5", foreground="#1a1a1a")

    # ── Layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        root_pad = ttk.Frame(self, padding=self._scaled(10))
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
        self._build_status_bar(root_pad)

    # ── Profile bar ────────────────────────────────────────────────────────
    def _build_profile_bar(self, parent):
        bar = ttk.LabelFrame(parent, text="Profiles", padding=(8, 6))
        bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(bar, text="Name:").pack(side=tk.LEFT, padx=(0, 4))
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(bar, textvariable=self.profile_var, width=28)
        self.profile_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        self._refresh_profile_list()
        Tooltip(self.profile_combo, "Type a name and click Save, or select an existing profile.")

        ttk.Button(bar, text="💾 Save",   command=self._save_profile, width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="📂 Load",   command=self._load_profile, width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="🗑 Delete", command=self._delete_profile, width=9).pack(side=tk.LEFT, padx=2)

    # ── Connection tab ─────────────────────────────────────────────────────
    def _build_connection_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🔌 Connection")
        outer = ttk.Frame(frame, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Server ────────────────────────────────────────────────────────
        srv_lf = ttk.LabelFrame(outer, text="Server", padding=(12, 8))
        srv_lf.pack(fill=tk.X, pady=(0, 10))
        srv = ttk.Frame(srv_lf)
        srv.pack(fill=tk.X)

        ttk.Label(srv, text="Address *:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.server_var = tk.StringVar()
        self.server_var.trace_add("write", self._on_server_change)
        server_entry = ttk.Entry(srv, textvariable=self.server_var, width=34)
        server_entry.grid(row=0, column=1, sticky=tk.EW, pady=5)
        Tooltip(server_entry, "Hostname or IP address of the Remote Desktop server (required).")

        ttk.Label(srv, text="Port:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.port_var = tk.StringVar(value="3389")
        self.port_var.trace_add("write", self._refresh_command_preview)
        port_entry = ttk.Entry(srv, textvariable=self.port_var, width=8)
        port_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        Tooltip(port_entry, "Default RDP port is 3389. Change only if the server uses a non-standard port.")

        ttk.Label(srv, text="Gateway:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.gateway_var = tk.StringVar()
        self.gateway_var.trace_add("write", self._refresh_command_preview)
        gw_entry = ttk.Entry(srv, textvariable=self.gateway_var, width=34)
        gw_entry.grid(row=2, column=1, sticky=tk.EW, pady=5)
        Tooltip(gw_entry, "Optional RDP gateway server address (/g:). Leave blank if not using a gateway.")

        srv.columnconfigure(1, weight=1)

        # ── Credentials ───────────────────────────────────────────────────
        cred_lf = ttk.LabelFrame(outer, text="Credentials", padding=(12, 8))
        cred_lf.pack(fill=tk.X)
        cred = ttk.Frame(cred_lf)
        cred.pack(fill=tk.X)

        ttk.Label(cred, text="Username:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.user_var = tk.StringVar()
        self.user_var.trace_add("write", self._refresh_command_preview)
        ttk.Entry(cred, textvariable=self.user_var, width=28).grid(row=0, column=1, sticky=tk.EW, pady=5)

        ttk.Label(cred, text="Domain:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.domain_var = tk.StringVar()
        self.domain_var.trace_add("write", self._refresh_command_preview)
        dom_entry = ttk.Entry(cred, textvariable=self.domain_var, width=28)
        dom_entry.grid(row=1, column=1, sticky=tk.EW, pady=5)
        Tooltip(dom_entry, "Windows domain name (/d:). Leave blank for local accounts.")

        ttk.Label(cred, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.pass_var = tk.StringVar()
        self.pass_var.trace_add("write", self._refresh_command_preview)
        pw_frame = ttk.Frame(cred)
        pw_frame.grid(row=2, column=1, sticky=tk.EW, pady=5)
        pw_entry = ttk.Entry(pw_frame, textvariable=self.pass_var, width=28, show="●")
        pw_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.show_pass = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            pw_frame, text="Show",
            variable=self.show_pass,
            command=lambda: pw_entry.config(show="" if self.show_pass.get() else "●"),
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(
            cred,
            text="⚠  Password will be visible in the process list.",
            foreground="#c0392b",
        ).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(2, 0))

        cred.columnconfigure(1, weight=1)

    def _on_server_change(self, *_):
        server = self.server_var.get().strip()
        self.title(f"XFreeRDP GUI — {server}" if server else "XFreeRDP GUI")
        self._refresh_command_preview()

    # ── Display tab ────────────────────────────────────────────────────────
    def _build_display_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🖥️  Display")
        outer = ttk.Frame(frame, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Resolution ────────────────────────────────────────────────────
        res_lf = ttk.LabelFrame(outer, text="Resolution", padding=(12, 8))
        res_lf.pack(fill=tk.X, pady=(0, 10))
        res = ttk.Frame(res_lf)
        res.pack(fill=tk.X)

        self.fullscreen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            res, text="Fullscreen  (/f)",
            variable=self.fullscreen_var, command=self._refresh_command_preview,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=4)

        self.dynres_var = tk.BooleanVar(value=True)
        dynres_cb = ttk.Checkbutton(
            res, text="Dynamic resolution  (/dynamic-resolution)",
            variable=self.dynres_var, command=self._refresh_command_preview,
        )
        dynres_cb.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=4)
        Tooltip(dynres_cb, "Automatically adjusts the remote desktop resolution when you resize the window.")

        for r, (label, attr, default) in enumerate([
            ("Width:",  "width_var",  "1920"),
            ("Height:", "height_var", "1080"),
        ], start=2):
            ttk.Label(res, text=label).grid(row=r, column=0, sticky=tk.W, pady=4, padx=(0, 10))
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(res, textvariable=var, width=8).grid(row=r, column=1, sticky=tk.W, pady=4)
            var.trace_add("write", self._refresh_command_preview)

        ttk.Label(res, text="Color depth:").grid(row=4, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.bpp_var = tk.StringVar(value="32")
        bpp_cb = ttk.Combobox(
            res, textvariable=self.bpp_var,
            values=["8", "15", "16", "24", "32"], width=6, state="readonly",
        )
        bpp_cb.grid(row=4, column=1, sticky=tk.W, pady=4)
        self.bpp_var.trace_add("write", self._refresh_command_preview)
        Tooltip(bpp_cb, "Color depth in bits per pixel. 32 bpp gives the best visual quality.")

        res.columnconfigure(1, weight=1)

        # ── Rendering ─────────────────────────────────────────────────────
        rend_lf = ttk.LabelFrame(outer, text="Rendering", padding=(12, 8))
        rend_lf.pack(fill=tk.X)

        bool_flags = [
            ("GFX acceleration  (/gfx)",      "gfx_var",          True,  "Use graphics pipeline acceleration for better performance."),
            ("RemoteFX  (/rfx)",              "rfx_var",          False, "Enable RemoteFX codec for improved graphics quality."),
            ("Smart sizing  (/smart-sizing)", "smart_sizing_var", False, "Scale the remote desktop to fit the window."),
            ("Multi-monitor  (/multimon)",    "multimon_var",     False, "Span the remote desktop across all local monitors."),
            ("Span monitors  (/span)",        "span_var",         False, "Span the remote desktop across monitors (legacy flag)."),
        ]
        for label, attr, default, tip in bool_flags:
            var = tk.BooleanVar(value=default)
            setattr(self, attr, var)
            cb = ttk.Checkbutton(rend_lf, text=label, variable=var, command=self._refresh_command_preview)
            cb.pack(anchor=tk.W, pady=3)
            Tooltip(cb, tip)

    # ── Network tab ────────────────────────────────────────────────────────
    def _build_network_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🌐 Network")
        outer = ttk.Frame(frame, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Connection quality ────────────────────────────────────────────
        conn_lf = ttk.LabelFrame(outer, text="Connection Quality", padding=(12, 8))
        conn_lf.pack(fill=tk.X, pady=(0, 10))
        conn = ttk.Frame(conn_lf)
        conn.pack(fill=tk.X)

        ttk.Label(conn, text="Network type:").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.network_var = tk.StringVar(value="lan")
        net_cb = ttk.Combobox(
            conn, textvariable=self.network_var,
            values=["modem", "broadband-low", "satellite", "broadband-high", "wan", "lan", "autodetect"],
            width=15, state="readonly",
        )
        net_cb.grid(row=0, column=1, sticky=tk.W, pady=4)
        self.network_var.trace_add("write", self._refresh_command_preview)
        Tooltip(net_cb, "Optimises RDP buffer and codec settings for the selected network type.")

        self.compression_var = tk.BooleanVar(value=False)
        comp_cb = ttk.Checkbutton(
            conn, text="Enable compression  (+compression)",
            variable=self.compression_var, command=self._refresh_command_preview,
        )
        comp_cb.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=4)
        Tooltip(comp_cb, "Compress RDP traffic — most useful on slow or high-latency connections.")

        conn.columnconfigure(1, weight=1)

        # ── Auto-reconnect ────────────────────────────────────────────────
        recon_lf = ttk.LabelFrame(outer, text="Auto-Reconnect", padding=(12, 8))
        recon_lf.pack(fill=tk.X)
        recon = ttk.Frame(recon_lf)
        recon.pack(fill=tk.X)

        self.autoreconnect_var = tk.BooleanVar(value=True)
        ar_cb = ttk.Checkbutton(
            recon, text="Enable auto-reconnect  (+auto-reconnect)",
            variable=self.autoreconnect_var, command=self._refresh_command_preview,
        )
        ar_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=4)
        Tooltip(ar_cb, "Automatically reconnect if the session is interrupted.")

        ttk.Label(recon, text="Max retries:").grid(row=1, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.reconnect_retries_var = tk.StringVar(value="20")
        retries_entry = ttk.Entry(recon, textvariable=self.reconnect_retries_var, width=6)
        retries_entry.grid(row=1, column=1, sticky=tk.W, pady=4)
        self.reconnect_retries_var.trace_add("write", self._refresh_command_preview)
        Tooltip(retries_entry, "Maximum number of automatic reconnection attempts.")

        recon.columnconfigure(1, weight=1)

    # ── Features tab ───────────────────────────────────────────────────────
    def _build_features_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="✨ Features")
        outer = ttk.Frame(frame, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Device redirection ────────────────────────────────────────────
        redir_lf = ttk.LabelFrame(outer, text="Device Redirection", padding=(12, 8))
        redir_lf.pack(fill=tk.X, pady=(0, 10))

        bool_feats = [
            ("Clipboard  (+clipboard)",   "clipboard_var", True,  "Share clipboard between local and remote desktop."),
            ("Audio playback  (/sound)",  "sound_var",     False, "Redirect remote audio playback to local speakers."),
            ("Microphone  (/microphone)", "mic_var",       False, "Redirect local microphone to the remote session."),
            ("Printer  (/printer)",       "printer_var",   False, "Redirect local printers to the remote session."),
            ("USB devices  (/usb:id)",    "usb_var",       False, "Redirect USB devices to the remote session."),
        ]
        for label, attr, default, tip in bool_feats:
            var = tk.BooleanVar(value=default)
            setattr(self, attr, var)
            cb = ttk.Checkbutton(redir_lf, text=label, variable=var, command=self._refresh_command_preview)
            cb.pack(anchor=tk.W, pady=3)
            Tooltip(cb, tip)

        # ── Drive redirection ─────────────────────────────────────────────
        drives_lf = ttk.LabelFrame(outer, text="Drive Redirection  (/drive:name,path)", padding=(12, 8))
        drives_lf.pack(fill=tk.X, pady=(0, 10))
        drives_inner = ttk.Frame(drives_lf)
        drives_inner.pack(fill=tk.X)

        self.drives_listbox = tk.Listbox(drives_inner, height=4, selectmode=tk.SINGLE)
        self.drives_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(drives_inner, orient=tk.VERTICAL, command=self.drives_listbox.yview)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.drives_listbox.configure(yscrollcommand=sb.set)
        dr_btns = ttk.Frame(drives_inner)
        dr_btns.pack(side=tk.LEFT, padx=(8, 0), anchor=tk.N)
        ttk.Button(dr_btns, text="➕ Add",    command=self._add_drive).pack(pady=2, fill=tk.X)
        ttk.Button(dr_btns, text="➖ Remove", command=self._remove_drive).pack(pady=2, fill=tk.X)

        # ── Remote app ────────────────────────────────────────────────────
        app_lf = ttk.LabelFrame(outer, text="Remote App", padding=(12, 8))
        app_lf.pack(fill=tk.X)
        app_grid = ttk.Frame(app_lf)
        app_grid.pack(fill=tk.X)

        ttk.Label(app_grid, text="App path  (/app:):").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.app_var = tk.StringVar()
        app_entry = ttk.Entry(app_grid, textvariable=self.app_var, width=36)
        app_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self.app_var.trace_add("write", self._refresh_command_preview)
        Tooltip(app_entry, "Launch a specific app instead of the full desktop, e.g. ||Explorer")

        app_grid.columnconfigure(1, weight=1)

    # ── Security tab ───────────────────────────────────────────────────────
    def _build_security_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🔒 Security")
        outer = ttk.Frame(frame, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Certificate validation ────────────────────────────────────────
        cert_lf = ttk.LabelFrame(outer, text="Certificate Validation", padding=(12, 8))
        cert_lf.pack(fill=tk.X, pady=(0, 10))
        cert_grid = ttk.Frame(cert_lf)
        cert_grid.pack(fill=tk.X)

        ttk.Label(cert_grid, text="Mode  (/cert:):").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.cert_var = tk.StringVar(value="ignore")
        cert_cb = ttk.Combobox(
            cert_grid, textvariable=self.cert_var,
            values=["ignore", "tofu", "deny"], width=16,
        )
        cert_cb.grid(row=0, column=1, sticky=tk.W, pady=4)
        self.cert_var.trace_add("write", self._refresh_command_preview)
        Tooltip(cert_cb, "ignore: accept all  |  tofu: trust on first use  |  deny: reject invalid")

        cert_grid.columnconfigure(1, weight=1)

        # ── Protocol & auth ───────────────────────────────────────────────
        proto_lf = ttk.LabelFrame(outer, text="Protocol & Authentication", padding=(12, 8))
        proto_lf.pack(fill=tk.X)
        proto_grid = ttk.Frame(proto_lf)
        proto_grid.pack(fill=tk.X)

        ttk.Label(proto_grid, text="Security protocol  (/sec:):").grid(
            row=0, column=0, sticky=tk.W, pady=4, padx=(0, 10)
        )
        self.sec_var = tk.StringVar(value="")
        sec_cb = ttk.Combobox(
            proto_grid, textvariable=self.sec_var,
            values=["", "rdp", "tls", "nla", "ext"], width=8, state="readonly",
        )
        sec_cb.grid(row=0, column=1, sticky=tk.W, pady=4)
        self.sec_var.trace_add("write", self._refresh_command_preview)
        Tooltip(sec_cb, "Leave blank for auto-negotiation (recommended).\nnla = Network Level Authentication.")

        self.noauth_var = tk.BooleanVar(value=False)
        noauth_cb = ttk.Checkbutton(
            proto_grid, text="Disable authentication  (/authentication:0)",
            variable=self.noauth_var, command=self._refresh_command_preview,
        )
        noauth_cb.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=4)
        Tooltip(noauth_cb, "⚠ Disables authentication. Use only on isolated/trusted networks.")

        self.admin_var = tk.BooleanVar(value=False)
        admin_cb = ttk.Checkbutton(
            proto_grid, text="Admin / console session  (/admin)",
            variable=self.admin_var, command=self._refresh_command_preview,
        )
        admin_cb.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=4)
        Tooltip(admin_cb, "Connect to the administrative console session (session 0).")

        proto_grid.columnconfigure(1, weight=1)

    # ── Advanced tab ───────────────────────────────────────────────────────
    def _build_advanced_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="⚙️  Advanced")
        outer = ttk.Frame(frame, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Advanced options ──────────────────────────────────────────────
        adv_lf = ttk.LabelFrame(outer, text="Advanced Options", padding=(12, 8))
        adv_lf.pack(fill=tk.X, pady=(0, 10))
        adv_grid = ttk.Frame(adv_lf)
        adv_grid.pack(fill=tk.X)

        ttk.Label(adv_grid, text="Extra flags:").grid(row=0, column=0, sticky=tk.W, pady=6, padx=(0, 10))
        self.extra_flags_var = tk.StringVar()
        extra_entry = ttk.Entry(adv_grid, textvariable=self.extra_flags_var, width=46)
        extra_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=6)
        self.extra_flags_var.trace_add("write", self._refresh_command_preview)
        Tooltip(extra_entry, "Additional xfreerdp flags appended verbatim, e.g. /log-level:DEBUG")

        ttk.Label(adv_grid, text="xfreerdp binary:").grid(row=1, column=0, sticky=tk.W, pady=6, padx=(0, 10))
        self.binary_var = tk.StringVar(value=self._find_xfreerdp())
        bin_frame = ttk.Frame(adv_grid)
        bin_frame.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=6)
        ttk.Entry(bin_frame, textvariable=self.binary_var, width=36).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(bin_frame, text="Browse…", command=self._browse_binary).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self.binary_var.trace_add("write", self._refresh_command_preview)

        adv_grid.columnconfigure(1, weight=1)

        # ── Keyboard shortcuts reference ──────────────────────────────────
        keys_lf = ttk.LabelFrame(outer, text="Keyboard Shortcuts", padding=(12, 8))
        keys_lf.pack(fill=tk.X)

        for key, action in [
            ("Ctrl+Enter", "Connect to server"),
            ("Ctrl+S",     "Save current profile"),
        ]:
            row_f = ttk.Frame(keys_lf)
            row_f.pack(anchor=tk.W, pady=2)
            ttk.Label(row_f, text=key, style="Shortcut.TLabel", width=14).pack(side=tk.LEFT)
            ttk.Label(row_f, text=action).pack(side=tk.LEFT)

    # ── Command preview ────────────────────────────────────────────────────
    def _build_command_preview(self, parent):
        self._preview_visible = True
        self._preview_lf = ttk.LabelFrame(
            parent,
            text="Command Preview",
            padding=(self._scaled(6), self._scaled(4)),
        )
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
            font=getattr(self, "_app_mono_font", tkfont.nametofont("TkFixedFont")),
            relief=tk.FLAT,
            padx=self._scaled(6),
            pady=self._scaled(4),
        )
        self.cmd_text.pack(fill=tk.X)

        btn_row = ttk.Frame(self._preview_lf)
        btn_row.pack(fill=tk.X, pady=(4, 2))
        self._copy_btn = ttk.Button(btn_row, text="📋 Copy to clipboard", command=self._copy_command)
        self._copy_btn.pack(side=tk.RIGHT)

    def _apply_initial_preview_state(self):
        """Called after bottom bar is built so before= reference is valid."""
        if not self._load_settings().get("preview_visible", False):
            self._preview_lf.pack_forget()
            self._preview_visible = False
            self._preview_btn.config(text="👁️  Show preview")
        else:
            self._preview_btn.config(text="👁️  Hide preview")

    def _toggle_preview(self):
        if self._preview_visible:
            self._preview_lf.pack_forget()
            self._preview_btn.config(text="👁️  Show preview")
        else:
            self._preview_lf.pack(fill=tk.X, pady=(8, 0), before=self._bottom_bar)
            self._preview_btn.config(text="👁️  Hide preview")
        self._preview_visible = not self._preview_visible
        self._save_settings()

    # ── Bottom buttons ─────────────────────────────────────────────────────
    def _build_bottom_buttons(self, parent):
        self._bottom_bar = ttk.Frame(parent)
        self._bottom_bar.pack(fill=tk.X, pady=(8, 0))

        # Right side
        ttk.Button(self._bottom_bar, text="⛔ Quit", command=self.quit).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(
            self._bottom_bar,
            text="🔗 Connect",
            command=self._connect,
            style="Connect.TButton",
        ).pack(side=tk.RIGHT)

        # Left side
        theme_label = "☀ Light" if self._dark_mode else "☾ Dark"
        self._theme_btn = ttk.Button(
            self._bottom_bar, text=theme_label, command=self._toggle_dark_mode, width=9
        )
        self._theme_btn.pack(side=tk.LEFT)
        Tooltip(self._theme_btn, "Toggle light / dark colour scheme.")

        self._preview_btn = ttk.Button(
            self._bottom_bar, text="👁️  Show preview", command=self._toggle_preview
        )
        self._preview_btn.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self._preview_btn, "Show or hide the command preview panel.")

        self._apply_initial_preview_state()

    # ── Status bar ──────────────────────────────────────────────────────────
    def _build_status_bar(self, parent):
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(6, 0))
        self._status_var = tk.StringVar(value="Ready  •  Ctrl+Enter to connect")
        ttk.Label(
            parent, textvariable=self._status_var,
            anchor=tk.W, font=("", self._scaled(8)),
        ).pack(fill=tk.X, pady=(2, 0))

    def _set_status(self, msg: str):
        if hasattr(self, "_status_var"):
            self._status_var.set(msg)

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
        self._copy_btn.config(text="✅ Copied!")
        self.after(2000, lambda: self._copy_btn.config(text="📋 Copy to clipboard"))
        self._set_status("Command copied to clipboard.")

    def _connect(self):
        if not self.server_var.get().strip():
            messagebox.showerror("Validation Error", "A server address is required before connecting.")
            self._set_status("Error: server address required.")
            return
        cmd = self._build_command()
        server = self.server_var.get().strip()
        self._set_status(f"Launching connection to {server} …")
        try:
            subprocess.Popen(cmd)  # noqa: S603 – user-controlled binary path
            self._set_status(f"Connected to {server}.")
        except FileNotFoundError:
            self._set_status("Error: xfreerdp binary not found.")
            messagebox.showerror(
                "Binary Not Found",
                f"Could not find xfreerdp at:\n  {self.binary_var.get()}\n\n"
                "Install FreeRDP or set the correct path in the Advanced tab.",
            )
        except Exception as exc:
            self._set_status(f"Error: {exc}")
            messagebox.showerror("Launch Failed", f"Could not launch xfreerdp:\n{exc}")

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
            messagebox.showerror("Validation Error", "Enter a profile name first.")
            return
        self.profiles[name] = self._get_current_config()
        self._write_profiles()
        self._refresh_profile_list()
        self._set_status(f"Profile «{name}» saved.")
        messagebox.showinfo("Profile Saved", f"Profile «{name}» has been saved.")

    def _load_profile(self):
        name = self.profile_var.get().strip()
        if name not in self.profiles:
            messagebox.showerror("Profile Not Found", f"No profile named «{name}».")
            return
        self._apply_config(self.profiles[name])
        self._set_status(f"Profile «{name}» loaded.")

    def _on_profile_selected(self, _event=None):
        name = self.profile_var.get().strip()
        if name in self.profiles:
            self._apply_config(self.profiles[name])
            self._set_status(f"Profile «{name}» loaded.")

    def _delete_profile(self):
        name = self.profile_var.get().strip()
        if name not in self.profiles:
            messagebox.showerror("Profile Not Found", f"No profile named «{name}».")
            return
        if messagebox.askyesno("Confirm Delete", f"Permanently delete profile «{name}»?"):
            del self.profiles[name]
            self._write_profiles()
            self._refresh_profile_list()
            self.profile_var.set("")
            self._set_status(f"Profile «{name}» deleted.")

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
