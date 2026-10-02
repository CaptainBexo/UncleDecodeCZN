"""CZN Mod Tool - one window: mods manager + injector (CustomTkinter).

Apply / revert / enable / disable all run through cznmod.py as subprocesses, so the
GUI and the command line can never disagree. Listing/status is read straight from
Mods/ and .state.json - the GUI never writes game files itself.

  python czn_gui.py              normal GUI
  python czn_gui.py --selftest   headless build/destroy smoke check
"""
import ctypes
import os
import queue
import subprocess
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cznmod  # noqa: E402

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CLR = {"ok": "#3FB950", "pending": "#D29922", "error": "#F85149", "off": "#6E7681"}
STATUS_TXT = {"ok": "In game", "pending": "Pending", "error": "Last run failed", "off": "Disabled"}


def _alive(pid):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        k.CloseHandle(h)
        return True
    return False


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CZN Mod Tool")
        self.geometry("880x700")
        self.minsize(760, 560)
        self.busy = False
        self.q = queue.Queue()
        self._build()
        self.refresh()
        self._sync_watch()
        self.after(80, self._drain)

    # ---------- layout ----------

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.game_lbl = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=13))
        self.game_lbl.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 2))
        self.btn_apply = ctk.CTkButton(bar, text="Apply Mods", width=170, height=34,
                                       font=ctk.CTkFont(size=14, weight="bold"), command=self._apply)
        self.btn_apply.pack(side="left")
        self.btn_revert = ctk.CTkButton(bar, text="Revert All", width=140, height=34, command=self._revert_all)
        self.btn_revert.pack(side="left", padx=(8, 0))
        self.btn_refresh = ctk.CTkButton(bar, text="Refresh", width=90, height=34, command=self.refresh)
        self.btn_refresh.pack(side="left", padx=(8, 0))
        ctk.CTkButton(bar, text="Open Mods Folder", width=140, height=34, fg_color="transparent",
                      border_width=1, command=self._open_mods).pack(side="left", padx=(8, 0))
        self.sw = ctk.CTkSwitch(bar, text="Auto-apply (Watcher)", command=self._toggle_watch)
        self.sw.pack(side="right")

        self.list_lbl = ctk.CTkLabel(self, text="Mods", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.list_lbl.grid(row=2, column=0, sticky="w", padx=18, pady=(10, 0))
        self.listbox = ctk.CTkScrollableFrame(self)
        self.listbox.grid(row=3, column=0, sticky="nsew", padx=14, pady=(2, 6))

        ctk.CTkLabel(self, text="Log", anchor="w", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=4, column=0, sticky="w", padx=18)
        self.logbox = ctk.CTkTextbox(self, height=170, font=ctk.CTkFont(family="Consolas", size=12))
        self.logbox.grid(row=5, column=0, sticky="ew", padx=14, pady=(2, 12))
        self.log('[i] Ready. Drop mods into the Mods/ folder, then click "Apply Mods".')

    # ---------- listing ----------

    def _game_line(self):
        try:
            import czn_paths
            self.game_lbl.configure(text=f"Game: {czn_paths.GAME_ROOT}", text_color=CLR["ok"])
        except SystemExit:
            self.game_lbl.configure(
                text="Chaos Zero Nightmare not found — run Setup.bat or create a game_path.txt file",
                text_color=CLR["error"])

    @staticmethod
    def _status(key, path, st):
        ent = st.get(key)
        if not ent:
            return "pending"
        try:
            h = cznmod._sha1(open(path, "rb").read())
        except OSError:
            return "error"
        if ent.get("png_sha1") != h:
            return "pending"
        if not ent.get("sct_sha1"):
            return "error"
        return "ok"

    @staticmethod
    def _merge(a, b):
        return "error" if "error" in (a, b) else ("pending" if "pending" in (a, b) else "ok")

    def refresh(self):
        self._game_line()
        for w in self.listbox.winfo_children():
            w.destroy()
        self.act_btns = [self.btn_apply, self.btn_revert, self.btn_refresh]
        st = cznmod._load_state()
        try:
            mods = cznmod.mod_targets()
        except Exception as e:
            mods = []
            self.log(f"[X] reading Mods/ failed: {type(e).__name__}: {e}")
        groups = {}
        for key, path, _target in mods:
            top = key.split("/")[0]
            is_pack = os.path.isfile(os.path.join(cznmod.MODS, top, "manifest.json"))
            groups.setdefault(top if is_pack else key, {"keys": [], "pack": is_pack})
            groups[top if is_pack else key]["keys"].append((key, path))
        for label, g in sorted(groups.items()):
            s = "ok"
            for key, path in g["keys"]:
                s = self._merge(s, self._status(key, path, st))
            kind = f"mod pack · {len(g['keys'])} images" if g["pack"] else "loose image"
            self._row(label, kind, s, label, disabled=False)
        off = cznmod.disabled_mods()
        for name in off:
            self._row(name, "disabled", "off", name, disabled=True)
        if not groups and not off:
            ctk.CTkLabel(self.listbox, text="No mods yet — drop .png images or a mod pack (manifest.json) into the Mods/ folder",
                         text_color=CLR["off"]).pack(pady=14)
        self.list_lbl.configure(text=f"Mods  ({len(groups)} active, {len(off)} disabled)")

    def _row(self, label, kind, status, arg, disabled):
        f = ctk.CTkFrame(self.listbox, corner_radius=6)
        f.pack(fill="x", pady=2)
        b = ctk.CTkButton(f, text="Enable" if disabled else "Disable", width=64, height=26,
                          font=ctk.CTkFont(size=12),
                          command=(lambda n=arg: self._enable(n)) if disabled else (lambda n=arg: self._disable(n)))
        b.pack(side="right", padx=8, pady=6)
        self.act_btns.append(b)
        ctk.CTkLabel(f, text=f"{kind} · {STATUS_TXT[status]}", text_color=CLR[status],
                     anchor="e").pack(side="right", padx=4)
        ctk.CTkLabel(f, text=label, anchor="w").pack(side="left", padx=(4, 2))
        ctk.CTkLabel(f, text="●", text_color=CLR[status], width=14).pack(side="left", padx=(6, 0))

    # ---------- actions ----------

    def _apply(self):
        self._run_cli(["apply"], "Apply Mods")

    def _revert_all(self):
        if not messagebox.askyesno(
                "Revert all mods",
                "Restore every original image in the game and move the mods into Mods\\_disabled\\?"):
            return
        self._run_cli(["revert"], "Revert All")

    def _disable(self, name):
        self._run_cli(["disable", name], f"Disable mod: {name}")

    def _enable(self, name):
        self._run_cli(["enable", name], f"Enable mod: {name}")

    def _open_mods(self):
        os.makedirs(cznmod.MODS, exist_ok=True)
        os.startfile(cznmod.MODS)

    # ---------- watcher ----------

    def _watch_pid(self):
        try:
            pid = int(open(cznmod.PIDF).read().strip())
        except Exception:
            return None
        return pid if _alive(pid) else None

    def _toggle_watch(self):
        pid = self._watch_pid()
        if self.sw.get():
            if not pid:
                subprocess.Popen([sys.executable, os.path.join(HERE, "cznmod.py"), "watch"],
                                 cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True,
                                 creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS)
                self.log("[i] Watcher on — runs hidden, auto-applies when Mods/ changes (game must be closed).")
            self.after(800, self._sync_watch)
        else:
            if pid:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW)
                self.log("[i] Watcher off.")
            self.after(500, self._sync_watch)

    def _sync_watch(self):
        if self._watch_pid():
            self.sw.select()
        else:
            self.sw.deselect()

    # ---------- cli runner ----------

    def log(self, s):
        self.logbox.insert("end", s + "\n")
        self.logbox.see("end")

    def _run_cli(self, args, what):
        if self.busy:
            return
        self.busy = True
        for b in self.act_btns:
            b.configure(state="disabled")
        self.log(f"\n> {what}")
        cmd = [sys.executable, os.path.join(HERE, "cznmod.py")] + args

        def worker():
            try:
                p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace",
                                     creationflags=CREATE_NO_WINDOW)
                for line in p.stdout:
                    self.q.put(("log", line.rstrip("\r\n")))
                p.wait()
                self.q.put(("done", p.returncode))
            except Exception as e:
                self.q.put(("log", f"[X] {type(e).__name__}: {e}"))
                self.q.put(("done", -1))

        threading.Thread(target=worker, daemon=True).start()

    def _drain(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log(val)
                else:
                    self.busy = False
                    self.refresh()
                    for b in self.act_btns:
                        b.configure(state="normal")
                    self._sync_watch()
        except queue.Empty:
            pass
        self.after(80, self._drain)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        ctk.set_appearance_mode("dark")
        app = App()
        app.withdraw()
        for _ in range(6):
            app.update_idletasks()
            app.update()
        app.destroy()
        print("selftest OK")
        sys.exit(0)
    App().mainloop()
