"""
YouTube & YouTube Music → MP3 İndirici v4.0 (Stabil Sürüm)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kurulum:
  pip install yt-dlp customtkinter

FFmpeg zorunlu (MP3 dönüşümü):
  Windows : https://www.gyan.dev/ffmpeg/builds/  → PATH'e ekle
  Mac     : brew install ffmpeg
  Linux   : sudo apt install ffmpeg

Konsol penceresi olmadan çalıştırmak (Windows):
  Dosyayı  yt_mp3_downloader.pyw  olarak yeniden adlandır
"""

import sys
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

import os
import threading
import queue
import json
import re
import time
import shutil
import subprocess
from pathlib import Path
import tkinter.filedialog as fd
import tkinter.messagebox as mb

import customtkinter as ctk
import yt_dlp


# ─── Tema paleti ─────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg":       "#0d0d0d", "card":     "#1a1a1a", "card2":    "#252525",
        "border":   "#333333", "accent":   "#ff6b00", "accent_h": "#cc5500",
        "pause":    "#ffb300", "pause_h":  "#cc8f00", "text":     "#f5f5f5",
        "subtext":  "#888888", "success":  "#4caf50", "warning":  "#ffb300",
        "error":    "#ff4444", "skip":     "#ff9a3c",
    },
    "light": {
        "bg":       "#f2f2f2", "card":     "#ffffff", "card2":    "#e6e6e6",
        "border":   "#cccccc", "accent":   "#ff6b00", "accent_h": "#cc5500",
        "pause":    "#e65100", "pause_h":  "#bf360c", "text":     "#111111",
        "subtext":  "#666666", "success":  "#2e7d32", "warning":  "#e65100",
        "error":    "#c62828", "skip":     "#bf360c",
    },
}

# ─── Yardımcılar ─────────────────────────────────────────────────────────────
def sanitize(text: str, maxlen: int = 150) -> str:
    text = re.sub(r'[^\w\s\-\.\(\)\[\]çğışöüÇĞİŞÖÜ@:/]', '', str(text))
    return text[:maxlen]

def extract_video_id(url: str):
    m = re.search(r'(?:v=|youtu\.be/|/v/|/embed/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else None

# ─── Duplikat / İndirme Geçmişi ──────────────────────────────────────────────
class DownloadHistory:
    HISTORY_FILE = Path.home() / ".yt_mp3_history.json"

    def __init__(self):
        self._data: dict = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            if self.HISTORY_FILE.exists():
                self._data = json.loads(self.HISTORY_FILE.read_text(encoding="utf-8"))
        except: self._data = {}

    def _save(self):
        try:
            self.HISTORY_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except: pass

    def is_downloaded(self, vid_id: str) -> bool:
        with self._lock: return vid_id in self._data

    def mark(self, vid_id: str, title: str, filepath: str):
        with self._lock:
            self._data[vid_id] = {"title": title[:200], "file": filepath[:400], "ts": int(time.time())}
            self._save()

    def get_info(self, vid_id: str) -> dict:
        with self._lock: return self._data.get(vid_id, {})

history = DownloadHistory()

# ─── Özel Diyalog ────────────────────────────────────────────────────────────
class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, message: str, yes_text="Evet", no_text="Hayır", T: dict = None):
        super().__init__(parent)
        self.result = False
        T = T or THEMES["dark"]
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=T["bg"])
        self.grab_set()
        self.after(10, lambda: self._center(parent))

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=18, weight="bold"), text_color=T["accent"]).pack(padx=36, pady=(28, 6))
        ctk.CTkLabel(self, text=message, font=ctk.CTkFont(size=14), text_color=T["text"], wraplength=320, justify="center").pack(padx=36, pady=(0, 24))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=36, pady=(0, 28))

        ctk.CTkButton(btn_row, text=yes_text, width=120, height=42, corner_radius=21, fg_color=T["accent"], hover_color=T["accent_h"], font=ctk.CTkFont(size=14, weight="bold"), command=self._yes).pack(side="left", padx=(0, 12))
        ctk.CTkButton(btn_row, text=no_text, width=120, height=42, corner_radius=21, fg_color=T["card2"], hover_color=T["border"], text_color=T["subtext"], font=ctk.CTkFont(size=14), command=self._no).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self._no)

    def _center(self, parent):
        self.update_idletasks()
        pw, ph = parent.winfo_x() + parent.winfo_width() // 2, parent.winfo_y() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w//2}+{ph - h//2}")

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.result = False
        self.destroy()

# ─── Ana Uygulama ─────────────────────────────────────────────────────────────
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("YT MP3 İndirici")
        self.geometry("680x600")
        self.minsize(600, 550)
        self.resizable(True, True)

        self._theme_name = "dark"
        self._T = THEMES["dark"]
        ctk.set_appearance_mode("dark")
        
        self._output_dir = str(Path.home() / "Downloads")
        
        # UI Queue (Donmaları Engellemek İçin)
        self.ui_queue = queue.Queue()

        self._is_downloading = False
        self._cancel_flag    = False
        self._pause_event    = threading.Event()
        self._pause_event.set()
        self._is_paused      = False

        self._log_lines: list[tuple] = []
        self._max_log_lines = 300

        self.configure(fg_color=self._T["bg"])
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Kontroller ve Başlangıç İşlemleri
        if not shutil.which("ffmpeg"):
            self.after(500, self._warn_ffmpeg)
            
        self._cleanup_temp_files()
        self._start_ytdlp_update()
        
        # Queue Dinleyicisini Başlat
        self._process_queue()

    # ── Başlangıç Mekanizmaları ──────────────────────────────────────────────
    def _warn_ffmpeg(self):
        self._send_log("[Kritik Hata] Sistemde FFmpeg bulunamadı! İndirilen dosyalar MP3'e dönüştürülemez.", self._T["error"])
        mb.showwarning("Bağımlılık Eksik", "Sistemde FFmpeg bulunamadı!\nDosyalar MP3 formatına dönüştürülemeyecek.")

    def _cleanup_temp_files(self):
        try:
            for ext in ["*.part", "*.ytdl"]:
                for f in Path(self._output_dir).glob(ext):
                    try: f.unlink()
                    except: pass
        except: pass

    def _start_ytdlp_update(self):
        def worker():
            # EĞER PROGRAM .EXE OLARAK ÇALIŞIYORSA GÜNCELLEMEYİ İPTAL ET (Sonsuz döngüyü önler)
            if getattr(sys, 'frozen', False):
                self.ui_queue.put(("log", "[Sistem] Exe sürümünde otomatik güncelleme kapalıdır.", self._T["warning"]))
                return

            self.ui_queue.put(("log", "[Sistem] yt-dlp sürümü denetleniyor...", self._T["subtext"]))
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "--quiet"], check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                self.ui_queue.put(("log", "[Sistem] Altyapı güncel.", self._T["success"]))
            except Exception:
                self.ui_queue.put(("log", "[Sistem] Altyapı güncellenemedi, mevcut sürüm kullanılacak.", self._T["warning"]))
        threading.Thread(target=worker, daemon=True).start()

    # ── Queue İşleyici ───────────────────────────────────────────────────────
    def _process_queue(self):
        while not self.ui_queue.empty():
            try:
                msg = self.ui_queue.get_nowait()
                action = msg[0]
                if action == "log":
                    self._real_log(msg[1], msg[2])
                elif action == "status":
                    self.status_label.configure(text=msg[1], text_color=msg[2])
                elif action == "progress":
                    self.progress_bar.set(max(0.0, min(1.0, msg[1])))
                elif action == "download_state":
                    self._real_set_downloading(msg[1])
            except queue.Empty:
                break
        self.after(100, self._process_queue)

    def _send_log(self, text, color=None):
        self.ui_queue.put(("log", text, color or self._T["subtext"]))

    def _send_status(self, text, color=None):
        self.ui_queue.put(("status", text, color or self._T["subtext"]))

    # ── Tema ─────────────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        self._T = THEMES[self._theme_name]
        ctk.set_appearance_mode(self._theme_name)
        for w in self.winfo_children(): w.destroy()
        self._log_lines.clear()
        self.configure(fg_color=self._T["bg"])
        self._build_ui()

    # ── Arayüz ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        T = self._T
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(pady=(28, 0), padx=32, fill="x")

        ctk.CTkLabel(header, text="YT MP3", font=ctk.CTkFont(family="Segoe UI", size=34, weight="bold"), text_color=T["accent"]).pack(side="left")
        ctk.CTkLabel(header, text="YouTube & Music → MP3", font=ctk.CTkFont(size=15), text_color=T["subtext"]).pack(side="left", padx=(14, 0), pady=(10, 0))

        right_box = ctk.CTkFrame(header, fg_color="transparent")
        right_box.pack(side="right")
        ctk.CTkButton(right_box, text="Tema", width=60, height=40, corner_radius=12, fg_color=T["card2"], hover_color=T["border"], text_color=T["accent"], font=ctk.CTkFont(size=14, weight="bold"), command=self._toggle_theme).pack(side="left")

        url_card = ctk.CTkFrame(self, fg_color=T["card"], corner_radius=20)
        url_card.pack(pady=(20, 0), padx=32, fill="x")
        ctk.CTkLabel(url_card, text="Şarkı veya Playlist URL", font=ctk.CTkFont(size=14, weight="bold"), text_color=T["subtext"]).pack(anchor="w", padx=22, pady=(18, 5))

        url_row = ctk.CTkFrame(url_card, fg_color="transparent")
        url_row.pack(fill="x", padx=18, pady=(0, 18))
        self.url_entry = ctk.CTkEntry(url_row, placeholder_text="https://youtube.com/watch?v=...", height=50, corner_radius=14, font=ctk.CTkFont(size=14), fg_color=T["card2"], border_color=T["border"], border_width=1, text_color=T["text"])
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._on_start())
        ctk.CTkButton(url_row, text="Yapıştır", width=92, height=50, corner_radius=14, fg_color=T["card2"], hover_color=T["border"], text_color=T["subtext"], font=ctk.CTkFont(size=13), command=self._paste_url).pack(side="left")

        dir_card = ctk.CTkFrame(self, fg_color=T["card"], corner_radius=20)
        dir_card.pack(pady=(12, 0), padx=32, fill="x")
        ctk.CTkLabel(dir_card, text="Kayıt Klasörü", font=ctk.CTkFont(size=14, weight="bold"), text_color=T["subtext"]).pack(anchor="w", padx=22, pady=(18, 5))

        dir_row = ctk.CTkFrame(dir_card, fg_color="transparent")
        dir_row.pack(fill="x", padx=18, pady=(0, 18))
        self.dir_label = ctk.CTkLabel(dir_row, text=self._output_dir, font=ctk.CTkFont(size=13), text_color=T["text"], anchor="w", wraplength=490)
        self.dir_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dir_row, text="Seç", width=74, height=40, corner_radius=12, fg_color=T["accent"], hover_color=T["accent_h"], font=ctk.CTkFont(size=13, weight="bold"), command=self._choose_dir).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(18, 0), padx=32, fill="x")
        self.start_btn = ctk.CTkButton(btn_row, text="İndir", height=56, corner_radius=28, fg_color=T["accent"], hover_color=T["accent_h"], font=ctk.CTkFont(size=19, weight="bold"), command=self._on_start)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.pause_btn = ctk.CTkButton(btn_row, text="Duraklat", width=100, height=56, corner_radius=28, fg_color=T["card2"], hover_color=T["border"], text_color=T["subtext"], font=ctk.CTkFont(size=15, weight="bold"), command=self._on_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=(0, 10))
        self.cancel_btn = ctk.CTkButton(btn_row, text="İptal", width=100, height=56, corner_radius=28, fg_color=T["card2"], hover_color=T["border"], text_color=T["subtext"], font=ctk.CTkFont(size=15, weight="bold"), command=self._on_cancel, state="disabled")
        self.cancel_btn.pack(side="left")

        prog_card = ctk.CTkFrame(self, fg_color=T["card"], corner_radius=20)
        prog_card.pack(pady=(14, 0), padx=32, fill="x")
        self.status_label = ctk.CTkLabel(prog_card, text="Hazır", font=ctk.CTkFont(size=14), text_color=T["subtext"], anchor="w", wraplength=620)
        self.status_label.pack(anchor="w", padx=22, pady=(16, 6))
        self.progress_bar = ctk.CTkProgressBar(prog_card, height=8, corner_radius=4, fg_color=T["card2"], progress_color=T["accent"])
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=22, pady=(0, 16))

        log_card = ctk.CTkFrame(self, fg_color=T["card"], corner_radius=20)
        log_card.pack(pady=(12, 26), padx=32, fill="both", expand=True)
        log_hdr = ctk.CTkFrame(log_card, fg_color="transparent")
        log_hdr.pack(fill="x", padx=22, pady=(14, 0))
        ctk.CTkLabel(log_hdr, text="İşlem Günlüğü", font=ctk.CTkFont(size=14, weight="bold"), text_color=T["subtext"]).pack(side="left")
        ctk.CTkButton(log_hdr, text="Temizle", width=76, height=30, corner_radius=8, fg_color=T["card2"], hover_color=T["border"], text_color=T["subtext"], font=ctk.CTkFont(size=12), command=self._clear_log).pack(side="right")
        self.log_box = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family="Consolas", size=13), fg_color="transparent", text_color=T["subtext"], wrap="word", state="disabled", activate_scrollbars=True)
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(6, 18))

    # ── Arayüz Fonksiyonları ─────────────────────────────────────────────────
    def _paste_url(self):
        try:
            txt = self.clipboard_get().strip()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, txt[:512])
        except: pass

    def _choose_dir(self):
        path = fd.askdirectory(initialdir=self._output_dir)
        if path:
            self._output_dir = path
            self.dir_label.configure(text=path if len(path) <= 65 else "…" + path[-62:])

    def _real_log(self, msg: str, color: str):
        safe = sanitize(str(msg), maxlen=220)
        self._log_lines.append((safe, color))
        if len(self._log_lines) > self._max_log_lines:
            self._log_lines = self._log_lines[-self._max_log_lines:]
        try:
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            for m, _ in self._log_lines: self.log_box.insert("end", m + "\n")
            self.log_box.configure(state="disabled")
            self.log_box.see("end")
        except: pass

    def _clear_log(self):
        self._log_lines.clear()
        try:
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.configure(state="disabled")
        except: pass

    def _real_set_downloading(self, state: bool):
        self._is_downloading = state
        self.start_btn.configure(state="disabled" if state else "normal")
        self.pause_btn.configure(state="normal" if state else "disabled")
        self.cancel_btn.configure(state="normal" if state else "disabled")
        if not state:
            self._is_paused = False
            self._pause_event.set()
            self._update_pause_btn()

    def _update_pause_btn(self):
        T = self._T
        if self._is_paused:
            self.pause_btn.configure(text="Devam Et", fg_color=T["pause"], hover_color=T["pause_h"], text_color="#ffffff")
        else:
            self.pause_btn.configure(text="Duraklat", fg_color=T["card2"], hover_color=T["border"], text_color=T["subtext"])

    # ── Kontroller ───────────────────────────────────────────────────────────
    def _on_close(self):
        if self._is_downloading:
            dlg = ConfirmDialog(self, title="İndirme Devam Ediyor", message="İndirme devam ediyor.\nÇıkmak isterseniz işlem iptal edilir.", yes_text="Çık", no_text="Duraklat", T=self._T)
            self.wait_window(dlg)
            if dlg.result:
                self._cancel_flag = True
                self._pause_event.set()
                self._cleanup_temp_files()
                self.destroy()
            else:
                if not self._is_paused: self._on_pause()
        else:
            dlg = ConfirmDialog(self, title="Çıkış", message="Uygulamadan çıkmak istediğinize emin misiniz?", T=self._T)
            self.wait_window(dlg)
            if dlg.result:
                self._cleanup_temp_files()
                self.destroy()

    def _on_pause(self):
        if not self._is_downloading: return
        if self._is_paused:
            self._is_paused = False
            self._pause_event.set()
            self._send_log("[Bilgi] İndirme devam ediyor.", self._T["success"])
            self._send_status("İndiriliyor...", self._T["text"])
        else:
            self._is_paused = True
            self._pause_event.clear()
            self._send_log("[Duraklatıldı] Bekletiliyor.", self._T["warning"])
            self._send_status("Duraklatıldı", self._T["warning"])
        self._update_pause_btn()

    def _on_cancel(self):
        if not self._is_downloading: return
        dlg = ConfirmDialog(self, title="İptal Et", message="İndirme iptal edilsin mi?", T=self._T)
        self.wait_window(dlg)
        if dlg.result:
            self._cancel_flag = True
            self._pause_event.set()
            self._send_log("[Bilgi] İptal sinyali gönderildi...", self._T["warning"])

    def _on_start(self):
        if self._is_downloading: return
        url = self.url_entry.get().strip()
        if not url or not url.startswith("http"):
            self._send_log("[Uyarı] Geçersiz URL.", self._T["warning"])
            return

        vid = extract_video_id(url)
        if vid and history.is_downloaded(vid):
            self._send_log(f"[Atlandı] Zaten indirilmiş: {history.get_info(vid).get('title','?')[:80]}", self._T["skip"])
            self._send_status("Zaten indirilmiş - atlandı", self._T["skip"])
            return

        self._cancel_flag = False
        self._is_paused   = False
        self._pause_event.set()
        self.ui_queue.put(("download_state", True))
        self.ui_queue.put(("progress", 0.0))
        self._send_status("Hazırlanıyor...")
        self._send_log(f"-> {url[:90]}", self._T["text"])

        threading.Thread(target=self._download_worker, args=(url, self._output_dir), daemon=True).start()

    def _download_worker(self, url: str, out_dir: str):
        T = self._T
        downloaded = [0]
        total_items = [1]
        skipped_ids = set()

        def is_cancelled(): return self._cancel_flag

        def progress_hook(d):
            self._pause_event.wait()
            if self._cancel_flag: raise yt_dlp.utils.DownloadError("Kullanıcı iptali")

            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                overall = (downloaded[0] + (done / total if total else 0)) / total_items[0]
                self.ui_queue.put(("progress", overall))
                speed = (d.get("speed") or 0) / 1024
                fname = sanitize(d.get("filename", "").replace(out_dir, "").strip("/\\"), 50)
                self._send_status(f"{fname} - {speed:.0f} KB/s - ETA {d.get('eta', 0)}s", T["text"])
            elif status == "finished":
                downloaded[0] += 1
                fname = sanitize(d.get("filename", ""), 80)
                self._send_log(f"[Başarılı] {fname}", T["success"])
                self.ui_queue.put(("progress", downloaded[0] / total_items[0]))
                vid_id = d.get("info_dict", {}).get("id")
                if vid_id: history.mark(vid_id, d.get("info_dict", {}).get("title", fname), str(d.get("filename", "")))
            elif status == "error":
                self._send_log(f"[Hata] {sanitize(str(d.get('filename','')), 50)}", T["error"])

        def build_opts():
            # MAX_PATH çözümü: Dinamik dosya adı kesme
            max_len = max(20, 240 - len(out_dir))
            def match_filter(info, *, incomplete=False):
                if is_cancelled(): return "Kullanıcı iptali"
                return "Zaten indirilmiş" if info.get("id") in skipped_ids else None
            return {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(out_dir, f"%(title).{max_len}s.%(ext)s"),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}],
                "progress_hooks": [progress_hook],
                "quiet": True, "no_warnings": True, "ignoreerrors": True,
                "socket_timeout": 30, "retries": 3, "fragment_retries": 10, # Parçalı indirme kopma koruması
                "noplaylist": False, "match_filter": match_filter,
            }

        try:
            with yt_dlp.YoutubeDL({"extract_flat": "in_playlist", "quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    self._send_log("[Hata] Metadata alınamadı.", T["error"])
                    self._send_status("Metadata hatası", T["error"])
                    self.ui_queue.put(("download_state", False))
                    return

                entries = info.get("entries") or []
                total_items[0] = len(entries) if entries else 1

                for e in entries:
                    eid = e.get("id", "")
                    if eid and history.is_downloaded(eid):
                        skipped_ids.add(eid)
                        self._send_log(f"[Atlandı] {sanitize(e.get('title','?'), 60)}", T["skip"])

                real_items = total_items[0] - len(skipped_ids)
                if real_items <= 0:
                    self._send_log("[Bilgi] Tümü zaten indirilmiş.", T["success"])
                    self._send_status("Zaten indirilmiş", T["success"])
                    self.ui_queue.put(("download_state", False))
                    return
                total_items[0] = real_items
        except Exception as e:
            self._send_log(f"[Hata] Sebep: {sanitize(str(e), 80)}", T["error"])
            self._send_status("Hatalı Link", T["error"])
            self.ui_queue.put(("download_state", False))
            return

        if is_cancelled():
            self._send_log("[İptal] İşlem iptal edildi.", T["warning"])
            self._send_status("İptal", T["warning"])
            self._cleanup_temp_files()
            self.ui_queue.put(("download_state", False))
            return

        try:
            with yt_dlp.YoutubeDL(build_opts()) as ydl:
                ydl.download([url])

            if is_cancelled():
                self._send_log("[İptal] İndirme iptal edildi.", T["warning"])
                self._send_status("İptal edildi", T["warning"])
            else:
                skip_txt = f" ({len(skipped_ids)} atlandı)" if skipped_ids else ""
                self._send_log(f"[Tamamlandı] {downloaded[0]} dosya indi{skip_txt} -> {out_dir}", T["success"])
                self._send_status(f"Tamamlandı - {downloaded[0]} dosya", T["success"])
                self.ui_queue.put(("progress", 1.0))
        except Exception as e:
            msg = str(e)
            if "Kullanıcı iptali" in msg or "cancelled" in msg.lower():
                self._send_log("[İptal] İşlem iptal edildi.", T["warning"])
                self._send_status("İptal", T["warning"])
            else:
                self._send_log(f"[Hata] {sanitize(msg, 130)}", T["error"])
                self._send_status("Hata", T["error"])
        finally:
            self._cleanup_temp_files()
            self.ui_queue.put(("download_state", False))


if __name__ == "__main__":
    app = App()
    app.mainloop()