import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import sys
import os
import webbrowser
import ctypes
import re
import json
import urllib.request
import subprocess

# Windows'ta arka plan konsol pencerelerini gizle
if sys.platform == 'win32':
    import subprocess
    _original_Popen = subprocess.Popen
    def _silent_Popen(*args, **kwargs):
        if sys.platform == 'win32':
            kwargs.setdefault('creationflags', 0x08000000)  # CREATE_NO_WINDOW
        return _original_Popen(*args, **kwargs)
    subprocess.Popen = _silent_Popen

# ── Versiyon ──────────────────────────────────────────────────────
__version__ = "1.0.0"
GUNCELLEME_URL = "https://raw.githubusercontent.com/playlistindirici/youtube-mp3-indirici/main/releases.json"

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

if getattr(sys, 'frozen', False):
    program_klasoru = os.path.dirname(sys.executable)
else:
    program_klasoru = os.path.dirname(os.path.abspath(__file__))

os.environ["PATH"] += os.pathsep + program_klasoru


def versiyon_karsilastir(mevcut, yeni):
    """1.0.0 formatındaki iki versiyonu karşılaştırır. Yeni > mevcut ise True döner."""
    try:
        m = [int(x) for x in mevcut.split(".")]
        y = [int(x) for x in yeni.split(".")]
        return y > m
    except Exception:
        return False


class YoutubeMp3IndiriciApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Youtube MP3 \u0130ndirici  v" + __version__)
        self.root.geometry("600x640")
        self.root.protocol("WM_DELETE_WINDOW", self._pencere_kapat)

        self.koyu_tema = {
            "bg": "#121212", "fg": "#E0E0E0", "entry_bg": "#2A2A2A",
            "accent": "#FF8C00", "accent_hover": "#CC7000", "link": "#4DA8DA"
        }
        self.acik_tema = {
            "bg": "#F0F0F0", "fg": "#121212", "entry_bg": "#FFFFFF",
            "accent": "#FF8C00", "accent_hover": "#CC7000", "link": "#0056b3"
        }
        self.guncel_tema = self.koyu_tema
        self.is_dark_mode = True

        self.root.configure(bg=self.guncel_tema["bg"])

        self.baslik_font = ("Arial", 16, "bold")
        self.etiket_font = ("Arial", 11)
        self.buton_font  = ("Arial", 10, "bold")

        self._animasyon_calisiyor = False
        self._animasyon_nokta_sayisi = 0
        self._indirme_devam_ediyor = False

        # ── Üst bar ────────────────────────────────────────────────
        self.tema_frame = tk.Frame(root, bg=self.guncel_tema["bg"])
        self.tema_frame.pack(fill="x", pady=(8, 0), padx=12)

        # Versiyon etiketi (sol)
        self.versiyon_label = tk.Label(
            self.tema_frame,
            text="v" + __version__,
            font=("Arial", 9),
            fg="#666",
            bg=self.guncel_tema["bg"]
        )
        self.versiyon_label.pack(side="left")

        # Toggle switch (sağ)
        self.toggle_cerceve = tk.Frame(
            self.tema_frame, bg="#333", bd=0, relief="flat", padx=3, pady=3
        )
        self.toggle_cerceve.pack(side="right")

        self.gunes_btn = tk.Label(
            self.toggle_cerceve, text="\u2600", font=("Arial", 13),
            bg="#333", fg="#888", cursor="hand2", padx=6, pady=2
        )
        self.gunes_btn.pack(side="left")
        self.gunes_btn.bind("<Button-1>", lambda e: self._tema_ac())

        self.ay_btn = tk.Label(
            self.toggle_cerceve, text="\u263e", font=("Arial", 13),
            bg="#FF8C00", fg="#fff", cursor="hand2", padx=6, pady=2
        )
        self.ay_btn.pack(side="left")
        self.ay_btn.bind("<Button-1>", lambda e: self._tema_koy())

        # ── Başlık ─────────────────────────────────────────────────
        self.baslik = tk.Label(
            root, text="YOUTUBE MP3 \u0130ND\u0130R\u0130C\u0130",
            font=self.baslik_font, fg=self.guncel_tema["accent"],
            bg=self.guncel_tema["bg"], pady=10
        )
        self.baslik.pack()

        # ── Güncelleme Banner (başlangıçta gizli) ──────────────────
        self.guncelleme_frame = tk.Frame(root, bg="#1a3a1a")
        self.guncelleme_label = tk.Label(
            self.guncelleme_frame,
            text="",
            font=("Arial", 10, "bold"),
            fg="#5fcc5f",
            bg="#1a3a1a",
            cursor="hand2",
            pady=6
        )
        self.guncelleme_label.pack(fill="x")
        self.guncelleme_label.bind("<Button-1>", self._guncelleme_linkine_git)
        self._guncelleme_indirme_url = ""

        # ── Link Alanı ─────────────────────────────────────────────
        self.link_frame = tk.Frame(root, bg=self.guncel_tema["bg"])
        self.link_frame.pack(fill="x", padx=30, pady=5)

        self.link_label = tk.Label(
            self.link_frame,
            text="Playlist linkinizi veya video linkinizi giriniz:",
            font=self.etiket_font, fg=self.guncel_tema["accent"],
            bg=self.guncel_tema["bg"]
        )
        self.link_label.pack(anchor="w")

        self.link_var = tk.StringVar()
        self.link_var.trace_add("write", self.link_uzunluk_kontrol)

        self.link_entry = tk.Entry(
            self.link_frame, textvariable=self.link_var,
            font=("Arial", 11),
            bg=self.guncel_tema["entry_bg"],
            fg=self.guncel_tema["accent"],
            insertbackground=self.guncel_tema["accent"],
            relief="flat"
        )
        self.link_entry.pack(fill="x", ipady=6, pady=5)

        # ── Klasör Alanı ───────────────────────────────────────────
        self.klasor_frame = tk.Frame(root, bg=self.guncel_tema["bg"])
        self.klasor_frame.pack(fill="x", padx=30, pady=5)

        self.klasor_label = tk.Label(
            self.klasor_frame,
            text="Hedef klas\u00f6r\u00fcn\u00fcz\u00fc se\u00e7iniz:",
            font=self.etiket_font, fg=self.guncel_tema["accent"],
            bg=self.guncel_tema["bg"]
        )
        self.klasor_label.pack(anchor="w")

        self.secilen_klasor_yolu = tk.StringVar()

        self.klasor_alt_frame = tk.Frame(self.klasor_frame, bg=self.guncel_tema["bg"])
        self.klasor_alt_frame.pack(fill="x")

        self.klasor_entry = tk.Entry(
            self.klasor_alt_frame, textvariable=self.secilen_klasor_yolu,
            font=("Arial", 11),
            bg=self.guncel_tema["entry_bg"],
            fg=self.guncel_tema["accent"],
            readonlybackground=self.guncel_tema["entry_bg"],
            disabledforeground=self.guncel_tema["accent"],
            state="readonly", relief="flat"
        )
        self.klasor_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))

        self.klasor_button = tk.Button(
            self.klasor_alt_frame, text="G\u00d6ZAT",
            command=self.klasor_sec,
            font=self.buton_font,
            bg=self.guncel_tema["accent"], fg="#FFF",
            activebackground=self.guncel_tema["accent_hover"],
            relief="flat", cursor="hand2"
        )
        self.klasor_button.pack(side="right", ipadx=10, ipady=4)

        # ── İndir Butonu ───────────────────────────────────────────
        self.indir_button = tk.Button(
            root, text="\u2193  \u0130ND\u0130RMEYE BA\u015eLA  \u2193",
            command=self.indirme_islemini_baslat,
            font=("Arial", 13, "bold"),
            bg=self.guncel_tema["accent"], fg="#FFF",
            activebackground=self.guncel_tema["accent_hover"],
            relief="flat", cursor="hand2"
        )
        self.indir_button.pack(pady=20, ipadx=20, ipady=10)

        # ── Durum Etiketi ──────────────────────────────────────────
        self.durum_label = tk.Label(
            root, text="",
            font=("Arial", 10, "italic"),
            fg=self.guncel_tema["fg"],
            bg=self.guncel_tema["bg"],
            wraplength=480
        )
        self.durum_label.pack()

        # ── Progress Bar ───────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TProgressbar", thickness=15, background=self.guncel_tema["accent"])
        self.progress_bar = ttk.Progressbar(
            root, orient="horizontal", length=400,
            mode="determinate", style="TProgressbar"
        )

        self.ilerleme_label = tk.Label(
            root, text="",
            font=("Arial", 10, "bold"),
            fg=self.guncel_tema["accent"],
            bg=self.guncel_tema["bg"]
        )
        self.ilerleme_label.pack(pady=2)

        # ── GitHub Linki ───────────────────────────────────────────
        self.github_link = tk.Label(
            root, text="GitHub: playlistindirici",
            font=("Arial", 10, "underline"),
            fg=self.guncel_tema["link"],
            bg=self.guncel_tema["bg"],
            cursor="hand2"
        )
        self.github_link.pack(side="bottom", pady=15)
        self.github_link.bind(
            "<Button-1>",
            lambda e: webbrowser.open_new("https://github.com/playlistindirici")
        )

        self.indirme_thread = None
        self.bekleme_animasyonu_baslat()

        # Güncelleme kontrolünü arka planda başlat
        threading.Thread(target=self._guncelleme_kontrol, daemon=True).start()

    # ── Güncelleme Kontrolü ────────────────────────────────────────
    def _guncelleme_kontrol(self):
        """GitHub'daki releases.json'a bakarak yeni versiyon var mı kontrol eder."""
        try:
            req = urllib.request.Request(
                GUNCELLEME_URL,
                headers={"User-Agent": "YoutubeMp3Indirici/" + __version__}
            )
            with urllib.request.urlopen(req, timeout=5) as yanit:
                veri = json.loads(yanit.read().decode("utf-8"))

            yeni_versiyon  = veri.get("version", "")
            aciklama       = veri.get("description", "")
            indirme_url    = veri.get("download_url", "")

            if versiyon_karsilastir(__version__, yeni_versiyon):
                self._guncelleme_indirme_url = indirme_url
                mesaj = (
                    "\u2b06  Yeni s\u00fcr\u00fcm mevcut: v"
                    + yeni_versiyon
                    + "  \u2014  "
                    + aciklama
                    + "  (indirmek i\u00e7in t\u0131kla)"
                )
                self.root.after(0, self._guncelleme_banner_goster, mesaj)
        except Exception:
            # İnternet yoksa veya dosya bulunamazsa sessizce geç
            pass

    def _guncelleme_banner_goster(self, mesaj):
        self.guncelleme_label.config(text=mesaj)
        # Banner'ı başlık ile link alanı arasına yerleştir
        self.guncelleme_frame.pack(fill="x", after=self.baslik, pady=(0, 5))

    def _guncelleme_linkine_git(self, event=None):
        url = self._guncelleme_indirme_url or "https://github.com/playlistindirici/youtube-mp3-indirici/releases"
        webbrowser.open_new(url)

    # ── Tema toggle ────────────────────────────────────────────────
    def _tema_ac(self):
        if not self.is_dark_mode:
            return
        self.is_dark_mode = False
        self.guncel_tema = self.acik_tema
        self._tema_uygula()

    def _tema_koy(self):
        if self.is_dark_mode:
            return
        self.is_dark_mode = True
        self.guncel_tema = self.koyu_tema
        self._tema_uygula()

    def tema_degistir(self):
        if self.is_dark_mode:
            self._tema_ac()
        else:
            self._tema_koy()

    def _tema_uygula(self):
        t = self.guncel_tema

        if self.is_dark_mode:
            self.toggle_cerceve.configure(bg="#333")
            self.gunes_btn.configure(bg="#333", fg="#888")
            self.ay_btn.configure(bg="#FF8C00", fg="#fff")
            self.versiyon_label.configure(bg=t["bg"], fg="#666")
        else:
            self.toggle_cerceve.configure(bg="#ddd")
            self.gunes_btn.configure(bg="#FF8C00", fg="#fff")
            self.ay_btn.configure(bg="#ddd", fg="#aaa")
            self.versiyon_label.configure(bg=t["bg"], fg="#999")

        for w in [self.root, self.tema_frame, self.link_frame,
                  self.klasor_frame, self.klasor_alt_frame]:
            w.configure(bg=t["bg"])

        self.baslik.configure(bg=t["bg"], fg=t["accent"])
        self.link_label.configure(bg=t["bg"], fg=t["accent"])
        self.klasor_label.configure(bg=t["bg"], fg=t["accent"])
        self.durum_label.configure(bg=t["bg"], fg=t["fg"])
        self.ilerleme_label.configure(bg=t["bg"], fg=t["accent"])
        self.github_link.configure(bg=t["bg"], fg=t["link"])

        self.link_entry.configure(
            bg=t["entry_bg"], fg=t["accent"],
            insertbackground=t["accent"]
        )
        self.klasor_entry.configure(
            bg=t["entry_bg"], fg=t["accent"],
            readonlybackground=t["entry_bg"]
        )
        self.klasor_button.configure(bg=t["accent"], activebackground=t["accent_hover"])
        if not self._indirme_devam_ediyor:
            self.indir_button.configure(
                bg=t["accent"], activebackground=t["accent_hover"], fg="#FFF"
            )

        ttk.Style().configure("TProgressbar", background=t["accent"])

    # ── Pencere kapatma ────────────────────────────────────────────
    def _pencere_kapat(self):
        self._animasyon_calisiyor = False
        self.root.destroy()

    # ── Animasyon ──────────────────────────────────────────────────
    def bekleme_animasyonu_baslat(self):
        self._animasyon_calisiyor = True
        self._animasyon_nokta_sayisi = 0
        self._animasyon_dongus()

    def bekleme_animasyonu_durdur(self):
        self._animasyon_calisiyor = False

    def _animasyon_dongus(self):
        if not self._animasyon_calisiyor:
            return
        noktalar = "." * (self._animasyon_nokta_sayisi % 4)
        self.durum_label.config(
            text="Haz\u0131r, link bekleniyor" + noktalar,
            fg=self.guncel_tema["fg"]
        )
        self._animasyon_nokta_sayisi += 1
        self.root.after(500, self._animasyon_dongus)

    # ── Yardımcılar ────────────────────────────────────────────────
    def link_uzunluk_kontrol(self, *args):
        metin = self.link_var.get()
        if len(metin) > 1000:
            self.link_var.set(metin[:1000])

    def klasor_sec(self):
        yol = filedialog.askdirectory(title="Klas\u00f6r Se\u00e7")
        if yol:
            self.secilen_klasor_yolu.set(yol)

    # ── İlerleme hook'u ────────────────────────────────────────────
    def ilerleme_durumu(self, d):
        if d["status"] == "downloading":
            yuzde_str = d.get("_percent_str", "0%").replace("%", "").strip()
            yuzde_str = re.sub(r"\x1b\[[0-9;]*m", "", yuzde_str)
            try:
                yuzde_float = float(yuzde_str)
            except ValueError:
                yuzde_float = 0.0

            kalan_sure = d.get("_eta_str", "Bilinmiyor")
            hiz        = d.get("_speed_str", "Bilinmiyor")
            dosya_adi  = os.path.basename(d.get("filename", ""))
            if len(dosya_adi) > 40:
                dosya_adi = dosya_adi[:37] + "..."

            self.root.after(
                0, self.arayuz_ilerleme_guncelle,
                yuzde_str, yuzde_float, kalan_sure, hiz, dosya_adi
            )

    def arayuz_ilerleme_guncelle(self, yuzde_str, yuzde_float, kalan_sure, hiz, dosya_adi):
        self.progress_bar["value"] = yuzde_float
        self.ilerleme_label.config(
            text="%" + yuzde_str + " | Kalan: " + kalan_sure + " | H\u0131z: " + hiz
        )
        self.durum_label.config(text="\u015eu an indirilen:\n" + dosya_adi)

    # ── İndirme başlatma ───────────────────────────────────────────
    def indirme_islemini_baslat(self):
        if self._indirme_devam_ediyor:
            return

        link       = self.link_entry.get().strip()
        kayit_yeri = self.secilen_klasor_yolu.get()

        if not link:
            messagebox.showwarning("Hata", "Link girmediniz!")
            return

        youtube_regex = r"^(https?\:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$"
        if not re.match(youtube_regex, link):
            messagebox.showerror(
                "Hatal\u0131 Link",
                "Girdi\u011finiz link ge\u00e7ersiz.\nL\u00fctfen do\u011fru bir YouTube linki yap\u0131\u015ft\u0131r\u0131n."
            )
            return

        if not kayit_yeri:
            messagebox.showwarning("Hata", "Kay\u0131t yeri se\u00e7mediniz!")
            return

        if not os.path.isdir(kayit_yeri):
            messagebox.showerror(
                "Klas\u00f6r Bulunamad\u0131",
                "Se\u00e7ilen klas\u00f6r art\u0131k mevcut de\u011fil.\nL\u00fctfen tekrar klas\u00f6r se\u00e7in."
            )
            self.secilen_klasor_yolu.set("")
            return

        self._indirme_devam_ediyor = True
        self.bekleme_animasyonu_durdur()

        self.progress_bar.pack(pady=10, before=self.ilerleme_label)
        self.durum_label.config(
            text="Ba\u011flant\u0131 kuruluyor, liste taranıyor...",
            fg=self.guncel_tema["accent"]
        )
        self.ilerleme_label.config(text="")
        self.progress_bar["value"] = 0
        self.indir_button.config(
            state="disabled", bg=self.guncel_tema["entry_bg"], fg="#555"
        )

        self.indirme_thread = threading.Thread(
            target=self.indirme_islemini_yap,
            args=(link, kayit_yeri),
            daemon=True
        )
        self.indirme_thread.start()

    # ── İndirme işlemi (ayrı thread) ──────────────────────────────
    def indirme_islemini_yap(self, url, kayit_yeri):
        try:
            import yt_dlp
        except ImportError:
            self.root.after(
                0, self.indirme_hatasi,
                "yt-dlp kurulu de\u011fil!\nKomut sat\u0131r\u0131nda: pip install yt-dlp"
            )
            return

        ayarlar = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "outtmpl": os.path.join(kayit_yeri, "%(title)s.%(ext)s"),
            "ignoreerrors": True,
            "keepvideo": False,
            "quiet": True,
            "no_warnings": True,
            "nocolor": True,
            "progress_hooks": [self.ilerleme_durumu],
        }

        try:
            with yt_dlp.YoutubeDL(ayarlar) as ydl:
                ydl.download([url])
            self.root.after(0, self.indirme_tamamlandi)
        except yt_dlp.utils.DownloadError:
            self.root.after(
                0, self.indirme_hatasi,
                "Ba\u011flant\u0131 reddedildi.\nLink k\u0131r\u0131k veya video/liste gizli olabilir."
            )
        except Exception as e:
            self.root.after(0, self.indirme_hatasi, str(e))

    # ── Sonuç metodları ────────────────────────────────────────────
    def indirme_tamamlandi(self):
        self._indirme_devam_ediyor = False
        self.durum_label.config(
            text="\u2705 TAMAMLANDI! T\u00fcm \u015fark\u0131lar klas\u00f6rde.",
            fg="#28a745"
        )
        self.ilerleme_label.config(text="")
        self.progress_bar["value"] = 100
        self.indir_button.config(state="normal", bg=self.guncel_tema["accent"], fg="#FFF")
        messagebox.showinfo("Ba\u015far\u0131l\u0131", "\u0130ndirme i\u015flemi ba\u015far\u0131yla tamamland\u0131.")
        self.bekleme_animasyonu_baslat()

    def indirme_hatasi(self, hata_mesaji):
        self._indirme_devam_ediyor = False
        self.durum_label.config(text="\u274c Bir hata olu\u015ftu!", fg="red")
        self.ilerleme_label.config(text="")
        self.progress_bar["value"] = 0
        self.indir_button.config(state="normal", bg=self.guncel_tema["accent"], fg="#FFF")
        messagebox.showerror("Hata", "\u0130ndirme ba\u015far\u0131s\u0131z:\n" + hata_mesaji)
        self.bekleme_animasyonu_baslat()


if __name__ == "__main__":
    root = tk.Tk()
    app = YoutubeMp3IndiriciApp(root)
    root.mainloop()
