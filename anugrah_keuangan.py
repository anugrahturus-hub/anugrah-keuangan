import json, os, sys, tempfile, subprocess, hashlib, base64, secrets, threading, webbrowser, http.server
import re, textwrap
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

NAMA_TOKO = "ANUGRAH FOTOCOPY"
VERSI = "1.2.2"
BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "config.json")
CFG = json.load(open(CFG_PATH, encoding="utf-8"))
URL = CFG["supabase_url"].rstrip("/") + "/rest/v1/"
H = {"apikey": CFG["supabase_key"], "Authorization": "Bearer " + CFG["supabase_key"],
     "Content-Type": "application/json", "Prefer": "return=minimal"}
NOWIN = 0x08000000 if os.name == "nt" else 0

BANTUAN = """PANDUAN SHORTCUT - ANUGRAH KEUANGAN

UMUM
  Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4   Pindah ke tab Kasir / Transaksi / Barang / Bantuan
  F1          Buka tab Bantuan ini
  Ctrl+R      Muat ulang data dari Supabase
  F9          Ganti printer struk (jadi default)

KASIR
  F2          Pindah ke Kasir dan fokus ke kolom cari barang
  (ketik)     Daftar barang otomatis tersaring sesuai huruf yang diketik
  Panah Atas/Bawah   Pilih barang di daftar saran
  Enter       Tambahkan barang yang dipilih ke belanjaan (jumlah sesuai kolom Qty)
  Esc         Kosongkan kolom cari
  F3          Barang bebas (nama & harga diketik manual)
  F4          Edit harga item terpilih (bisa juga Enter / klik 2x pada item)
  F5          Qty +1 (bisa ditekan berkali-kali; juga tombol "+" pada daftar belanja)
  F6          Qty -1 (juga tombol "-"; qty 0 = item terhapus)
  F7          Hapus item terpilih (juga tombol Delete pada daftar belanja)
  F8          Kosongkan semua belanjaan
  F11         Ganti metode pembayaran (Cash / QRIS / Transfer)
  F10         Fokus ke kolom "Uang diterima" (kembalian dihitung otomatis)
  F12         Bayar: tampil preview struk dulu, Enter untuk cetak & simpan, Esc untuk batal

TRANSAKSI & BARANG
  Ctrl+S      Catat transaksi (tab Transaksi) / Simpan barang (tab Barang)
  Ctrl+P      Ekspor riwayat transaksi ke PDF (pilih Hari/Minggu/Bulan/Tahun + tanggal acuan; PDF memuat rekap per hari)
  Alt+R       Ganti tampilan Riwayat / Rekap per hari (tab Transaksi)
  F7          Hapus data terpilih

PRINTER STRUK
  Saat pertama kali cetak, pilih printer lalu centang "Jadikan printer default".
  Setelah itu struk langsung dicetak ke printer tersebut.
  Untuk mengganti printer, tekan F9 atau klik tombol "Ganti Printer".

TIPS
  Jika item yang sama dengan harga yang sama ditambahkan lagi, qty-nya otomatis bertambah.
  Isi kolom Modal di tab Barang agar laba tiap transaksi terhitung (laba = harga jual - modal).
  QRIS/Transfer: uang diterima otomatis sama dengan total, kembalian Rp 0.
"""


AUTH = CFG["supabase_url"].rstrip("/") + "/auth/v1/"
PORT = 54321
SES_PATH = os.path.join(os.environ.get("APPDATA", BASE), "AnugrahKeuangan", "session.json")
SES = {}


def hdr():
    h = dict(H)
    h["Authorization"] = "Bearer " + (SES.get("access_token") or CFG["supabase_key"])
    return h


def auth_post(path, body):
    req = urllib.request.Request(AUTH + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"apikey": CFG["supabase_key"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def simpan_sesi(d):
    SES.update(access_token=d["access_token"], refresh_token=d["refresh_token"],
               email=(d.get("user") or {}).get("email", SES.get("email", "")))
    os.makedirs(os.path.dirname(SES_PATH), exist_ok=True)
    json.dump(SES, open(SES_PATH, "w"))


def refresh():
    try:
        simpan_sesi(auth_post("token?grant_type=refresh_token", {"refresh_token": SES["refresh_token"]}))
        return True
    except Exception:
        return False


def sesi_tersimpan():
    try:
        SES.update(json.load(open(SES_PATH)))
    except Exception:
        return False
    return refresh()


def login_google():
    ver = secrets.token_urlsafe(64)
    cha = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).decode().rstrip("=")
    hasil = {}

    class Hd(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            hasil["code"] = (q.get("code") or [None])[0]
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("<h2>Login berhasil. Kembali ke aplikasi Anugrah Keuangan.</h2>".encode())

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", PORT), Hd); srv.timeout = 180
    webbrowser.open(AUTH + "authorize?" + urllib.parse.urlencode({
        "provider": "google", "redirect_to": "http://127.0.0.1:%d/callback" % PORT,
        "code_challenge": cha, "code_challenge_method": "s256"}))
    srv.handle_request(); srv.server_close()
    if not hasil.get("code"):
        raise RuntimeError("Login dibatalkan atau waktu habis")
    simpan_sesi(auth_post("token?grant_type=pkce", {"auth_code": hasil["code"], "code_verifier": ver}))


def api(method, table, params="", body=None):
    for n in (0, 1):
        req = urllib.request.Request(URL + table + params, method=method, headers=hdr(),
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                t = r.read().decode()
                return json.loads(t) if t else None
        except urllib.error.HTTPError as e:
            if e.code == 401 and n == 0 and refresh():
                continue
            raise


def rp(n):
    return "Rp {:,.0f}".format(n).replace(",", ".")


def lokal(s):
    return datetime.fromisoformat(re.sub(r"\.\d+", "", s).replace("Z", "+00:00")).astimezone()


def tulis_pdf(path, judul, info, ringkas, kepala, baris):
    def esc(s):
        s = s.encode("cp1252", "replace").decode("cp1252")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    L = [("F2", 13, judul), ("F1", 9, info), ("F1", 9, "")] + [("F1", 9, r) for r in ringkas]
    L += [("F1", 9, ""), ("F2", 8, kepala), ("F1", 8, "-" * len(kepala))] + [("F1", 8, r) for r in baris]
    pages = [L[i:i + 64] for i in range(0, len(L), 64)]

    def isi(pg):
        y, o = 805, ["BT"]
        for f, sz, t in pg:
            o.append("/%s %d Tf 1 0 0 1 40 %d Tm (%s) Tj" % (f, sz, y, esc(t)))
            y -= sz + 3
        return "\n".join(o + ["ET"])

    n = len(pages)
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % (5 + 2 * i) for i in range(n)), n),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>"]
    for i, pg in enumerate(pages):
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                    "/Contents %d 0 R >>" % (6 + 2 * i))
        c = isi(pg)
        objs.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(c.encode("cp1252", "replace")), c))
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for k, o in enumerate(objs, 1):
        offs.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (k, o)).encode("cp1252", "replace")
    x = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    for o in offs:
        out += ("%010d 00000 n \n" % o).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)).encode()
    open(path, "wb").write(out)


def cetak_teks(teks, printer):
    """Cetak teks ke printer bernama lewat PowerShell Out-Printer (tidak memakai Notepad)."""
    path = os.path.join(tempfile.gettempdir(), "struk.txt")
    open(path, "w", encoding="utf-8").write(teks)
    env = dict(os.environ, STRUK_FILE=path, STRUK_PRINTER=printer)
    cmd = "Get-Content -Raw -Encoding UTF8 -LiteralPath $env:STRUK_FILE | Out-Printer -Name $env:STRUK_PRINTER"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], env=env,
                           capture_output=True, text=True, timeout=90, creationflags=NOWIN)
    except Exception as e:
        return False, str(e)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "kode %d" % r.returncode).strip()[:300]
    return True, ""


def daftar_printer():
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Printer | Select-Object -ExpandProperty Name"],
            text=True, timeout=20, creationflags=NOWIN)
        return [x.strip() for x in out.splitlines() if x.strip()]
    except Exception:
        return []


def pasang_garis(tv, kanan=()):
    """Gambar garis kolom & baris di atas Treeview supaya tampak seperti tabel."""
    for c in kanan:
        tv.column(c, anchor="e")
    garis = []

    def gambar(_=None):
        for g in garis:
            g.destroy()
        garis.clear()
        w, h = tv.winfo_width(), tv.winfo_height()
        if w < 50 or h < 50:
            return

        def mk(x, y, ww, hh):
            f = tk.Frame(tv, bg="#d3dae8")
            f.place(x=x, y=y, width=ww, height=hh)
            garis.append(f)
        atas = 0
        while atas < 80 and tv.identify_region(5, atas) == "heading":
            atas += 1
        x = 0
        for c in tv["columns"][:-1]:
            x += int(tv.column(c, "width"))
            mk(x, 0, 1, h)
        y = atas + 30
        while y < h:
            mk(0, y, w, 1)
            y += 30

    def tunda(_=None):
        tv.after_idle(gambar)
    tv.bind("<Configure>", tunda, add="+")
    tv.bind("<ButtonRelease-1>", tunda, add="+")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(NAMA_TOKO + " - Keuangan")
        self.geometry("1060x800")
        self.tema()
        self.ok = False
        self.withdraw()
        if not self.masuk():
            return
        self.deiconify()
        hd = tk.Frame(self, bg="#2563eb"); hd.pack(fill="x")
        tk.Label(hd, text=NAMA_TOKO, bg="#2563eb", fg="#ffffff", font=("Segoe UI", 15, "bold")).pack(side="left", padx=16, pady=10)
        tk.Label(hd, text="Kasir & Keuangan  v" + VERSI, bg="#2563eb", fg="#bfdbfe", font=("Segoe UI", 10)).pack(side="left")
        tk.Button(hd, text="Keluar", command=self.keluar, bg="#1d4ed8", fg="#ffffff", relief="flat", bd=0, padx=10).pack(side="right", padx=12)
        tk.Label(hd, text=SES.get("email", ""), bg="#2563eb", fg="#dbeafe", font=("Segoe UI", 10)).pack(side="right")
        self.items, self.cart, self.cocok = [], [], []
        self.modal = {}
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.t_kasir, self.t_trx, self.t_brg, self.t_help = [ttk.Frame(self.nb) for _ in range(4)]
        for f, t in ((self.t_kasir, "Kasir (Ctrl+1)"), (self.t_trx, "Transaksi & Riwayat (Ctrl+2)"),
                     (self.t_brg, "Barang & Harga (Ctrl+3)"), (self.t_help, "Bantuan (F1)")):
            self.nb.add(f, text=t)
        self.build_kasir(); self.build_trx(); self.build_brg(); self.build_help()
        self.bind_keys()
        self.refresh_all()
        self.ok = True
        self.ent.focus_set()

    def masuk(self):
        if sesi_tersimpan():
            return True
        d = tk.Toplevel(self); d.title("Masuk"); d.geometry("420x250"); d.configure(bg="#f3f5f9"); d.grab_set()
        ttk.Label(d, text=NAMA_TOKO, font=("Segoe UI", 18, "bold")).pack(pady=(32, 4))
        ttk.Label(d, text="Masuk dengan akun Google toko (sama dengan di HP)").pack()
        lbl = ttk.Label(d, text="", wraplength=380); lbl.pack(pady=8)
        res = {}

        def cek():
            if "e" in res:
                e = res.pop("e")
                if e:
                    lbl.config(text=e); btn.config(state="normal")
                else:
                    d.destroy()
            else:
                d.after(300, cek)

        def mulai():
            btn.config(state="disabled"); lbl.config(text="Menunggu login di browser... (maks 3 menit)")

            def kerja():
                try:
                    login_google(); res["e"] = None
                except Exception as e:
                    res["e"] = "Gagal: %s" % e
            threading.Thread(target=kerja, daemon=True).start(); cek()
        btn = ttk.Button(d, text="Masuk dengan Google", style="Accent.TButton", command=mulai)
        btn.pack(ipadx=14, pady=8)
        self.wait_window(d)
        return bool(SES.get("access_token"))

    def keluar(self):
        if messagebox.askyesno("Keluar", "Keluar dari akun %s?" % SES.get("email", "")):
            try:
                os.remove(SES_PATH)
            except OSError:
                pass
            self.destroy()

    def tema(self):
        s = ttk.Style(self); s.theme_use("clam")
        BG, AC = "#f3f5f9", "#2563eb"
        self.configure(bg=BG)
        s.configure(".", background=BG, font=("Segoe UI", 10))
        s.configure("TFrame", background=BG); s.configure("TLabel", background=BG)
        s.configure("TEntry", padding=6, fieldbackground="#ffffff")
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"), background="#e5e9f2")
        s.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", AC)])
        s.configure("Treeview", rowheight=30, background="#ffffff", fieldbackground="#ffffff", borderwidth=1,
                    bordercolor="#c3ccdc", lightcolor="#c3ccdc", darkcolor="#c3ccdc")
        s.configure("Treeview.Heading", background="#e9edf5", font=("Segoe UI", 10, "bold"), padding=6, relief="flat")
        s.map("Treeview", background=[("selected", AC)], foreground=[("selected", "#ffffff")])
        s.configure("TButton", padding=(12, 7), background="#e5e9f2", borderwidth=0)
        s.map("TButton", background=[("active", "#d5dbe9")])
        s.configure("Accent.TButton", background=AC, foreground="#ffffff", font=("Segoe UI", 11, "bold"))
        s.map("Accent.TButton", background=[("active", "#1d4ed8")])
        s.configure("Card.TFrame", background="#ffffff")
        s.configure("Card.TLabel", background="#ffffff", font=("Segoe UI", 11))
        s.configure("Total.TLabel", background="#ffffff", font=("Segoe UI", 24, "bold"), foreground=AC)
        s.configure("Kembali.TLabel", background="#ffffff", font=("Segoe UI", 15, "bold"), foreground="#16a34a")

    # ---------- umum ----------
    def safe(self, fn):
        try:
            return fn()
        except Exception as e:
            messagebox.showerror("Gagal", "Koneksi/Supabase bermasalah:\n%s" % e)

    def refresh_all(self, _=None):
        self.load_items(); self.load_trx()

    def tab(self):
        return self.nb.index(self.nb.select())

    def k(self, fn):
        def h(e=None):
            if self.tab() == 0:
                fn()
            return "break"
        return h

    def pindah(self, i, fokus=None):
        def h(e=None):
            self.nb.select(i)
            if fokus:
                fokus.focus_set()
            return "break"
        return h

    def bind_keys(self):
        b = self.bind_all
        for n, f in enumerate((self.ent, None, None, None)):
            b("<Control-Key-%d>" % (n + 1), self.pindah(n, f))
        b("<F1>", self.pindah(3))
        b("<F2>", self.pindah(0, self.ent))
        b("<Control-r>", self.refresh_all)
        b("<F3>", self.k(self.tambah_bebas)); b("<F4>", self.k(self.edit_harga))
        b("<F5>", self.k(lambda: self.ubah_qty(1))); b("<F6>", self.k(lambda: self.ubah_qty(-1)))
        b("<F8>", self.k(self.kosong)); b("<F12>", self.k(self.bayar))
        b("<F10>", self.k(lambda: self.ent_terima.focus_set()))
        b("<F11>", self.k(self.ganti_metode)); b("<Control-p>", lambda e: (self.ekspor_pdf(), "break")[1])
        b("<Alt-r>", lambda e: (self.toggle_view(), "break")[1])
        b("<F9>", lambda e: (self.ganti_printer(), "break")[1])
        b("<F7>", self.a_hapus); b("<Control-s>", self.a_simpan)

    def a_hapus(self, e=None):
        {0: self.hapus_item, 1: self.hapus_trx, 2: self.hapus_barang}.get(self.tab(), lambda: None)()
        return "break"

    def a_simpan(self, e=None):
        {1: self.catat, 2: self.simpan_barang}.get(self.tab(), lambda: None)()
        return "break"

    def build_help(self):
        t = tk.Text(self.t_help, wrap="word", font=("Consolas", 11), padx=15, pady=10)
        t.insert("1.0", BANTUAN); t.config(state="disabled")
        t.pack(fill="both", expand=True)

    # ---------- BARANG ----------
    def build_brg(self):
        f = self.t_brg
        top = ttk.Frame(f); top.pack(fill="x", padx=10, pady=8)
        self.b_nama, self.b_harga, self.b_modal = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(top, text="Nama barang/jasa").pack(side="left")
        ttk.Entry(top, textvariable=self.b_nama, width=28).pack(side="left", padx=5)
        ttk.Label(top, text="Harga jual").pack(side="left")
        ttk.Entry(top, textvariable=self.b_harga, width=10).pack(side="left", padx=5)
        ttk.Label(top, text="Modal").pack(side="left")
        ttk.Entry(top, textvariable=self.b_modal, width=10).pack(side="left", padx=5)
        ttk.Button(top, text="Simpan/Tambah (Ctrl+S)", command=self.simpan_barang).pack(side="left", padx=3)
        ttk.Button(top, text="Hapus terpilih (F7)", command=self.hapus_barang).pack(side="left", padx=3)
        self.tv_brg = ttk.Treeview(f, columns=("nama", "harga", "modal", "laba"), show="headings", height=20)
        for c, t in (("nama", "Nama"), ("harga", "Harga jual"), ("modal", "Modal"), ("laba", "Laba/unit")):
            self.tv_brg.heading(c, text=t)
        self.tv_brg.pack(fill="both", expand=True, padx=10, pady=5)
        pasang_garis(self.tv_brg, ("harga", "modal", "laba"))
        self.tv_brg.bind("<<TreeviewSelect>>", self.pilih_barang)

    def load_items(self):
        r = self.safe(lambda: api("GET", "items", "?select=*&order=name"))
        self.items = r or []
        self.tv_brg.delete(*self.tv_brg.get_children())
        for i in self.items:
            self.tv_brg.insert("", "end", iid=str(i["id"]), values=(i["name"], rp(i["price"]), rp(i.get("cost") or 0), rp(float(i["price"]) - float(i.get("cost") or 0))))
        self.filter()

    def pilih_barang(self, _):
        s = self.tv_brg.selection()
        if s:
            i = next(x for x in self.items if str(x["id"]) == s[0])
            self.b_nama.set(i["name"]); self.b_harga.set(int(i["price"])); self.b_modal.set(int(i.get("cost") or 0))

    def simpan_barang(self):
        try:
            nama, harga = self.b_nama.get().strip(), float(self.b_harga.get())
            modal = float(self.b_modal.get() or 0)
        except ValueError:
            return messagebox.showwarning("Cek", "Harga harus angka")
        if not nama:
            return
        ada = next((x for x in self.items if x["name"].lower() == nama.lower()), None)
        if ada:
            self.safe(lambda: api("PATCH", "items", "?id=eq.%s" % ada["id"], {"name": nama, "price": harga, "cost": modal}))
        else:
            self.safe(lambda: api("POST", "items", "", {"name": nama, "price": harga, "cost": modal}))
        self.load_items()

    def hapus_barang(self):
        s = self.tv_brg.selection()
        if s and messagebox.askyesno("Hapus", "Hapus barang terpilih?"):
            self.safe(lambda: api("DELETE", "items", "?id=eq." + s[0]))
            self.load_items()

    # ---------- KASIR ----------
    def build_kasir(self):
        f = self.t_kasir
        top = ttk.Frame(f); top.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(top, text="Cari barang (F2)").pack(side="left")
        self.q = tk.StringVar()
        self.ent = ttk.Entry(top, textvariable=self.q, width=34)
        self.ent.pack(side="left", padx=5)
        ttk.Label(top, text="Qty").pack(side="left")
        self.qty = tk.IntVar(value=1)
        ttk.Spinbox(top, from_=1, to=9999, textvariable=self.qty, width=6).pack(side="left", padx=5)
        ttk.Button(top, text="+ Tambah (Enter)", command=self.tambah).pack(side="left", padx=3)
        ttk.Button(top, text="Barang bebas (F3)", command=self.tambah_bebas).pack(side="left", padx=3)
        self.lb = tk.Listbox(f, height=4, exportselection=False, font=("Segoe UI", 11), relief="flat", highlightthickness=1,
                             highlightbackground="#d5dbe9", selectbackground="#2563eb", selectforeground="#ffffff")
        self.lb.pack(fill="x", padx=10, pady=(0, 6))
        self.ent.bind("<KeyRelease>", self.on_key)
        self.ent.bind("<Return>", lambda e: self.tambah())
        self.ent.bind("<Down>", lambda e: self.geser(1)); self.ent.bind("<Up>", lambda e: self.geser(-1))
        self.ent.bind("<Escape>", lambda e: (self.q.set(""), self.filter()))
        self.lb.bind("<Double-1>", lambda e: self.tambah())

        self.tv = ttk.Treeview(f, columns=("n", "h", "q", "s"), show="headings", height=6)
        for c, t, w in (("n", "Barang", 380), ("h", "Harga", 130), ("q", "Qty", 60), ("s", "Subtotal", 140)):
            self.tv.heading(c, text=t); self.tv.column(c, width=w)
        self.tv.pack(fill="both", expand=True, padx=10)
        pasang_garis(self.tv, ("h", "s")); self.tv.column("q", anchor="center")
        self.tv.bind("<Return>", lambda e: self.edit_harga()); self.tv.bind("<Double-1>", lambda e: self.edit_harga())
        self.tv.bind("<Delete>", lambda e: self.hapus_item())
        for ks in ("<plus>", "<KP_Add>"):
            self.tv.bind(ks, lambda e: self.ubah_qty(1))
        for ks in ("<minus>", "<KP_Subtract>"):
            self.tv.bind(ks, lambda e: self.ubah_qty(-1))

        bt = ttk.Frame(f); bt.pack(fill="x", padx=10, pady=8)
        kiri = ttk.Frame(bt); kiri.pack(side="left", anchor="n")
        for n, (txt, fn) in enumerate((("Qty +1 (F5)", lambda: self.ubah_qty(1)), ("Qty -1 (F6)", lambda: self.ubah_qty(-1)),
                                       ("Edit Harga (F4)", self.edit_harga), ("Hapus Item (F7)", self.hapus_item),
                                       ("Kosongkan (F8)", self.kosong), ("Ganti Printer (F9)", self.ganti_printer))):
            ttk.Button(kiri, text=txt, command=fn).grid(row=n // 3, column=n % 3, padx=3, pady=3, sticky="ew")
        self.lbl_prn = ttk.Label(kiri, text="")
        self.lbl_prn.grid(row=2, column=0, columnspan=3, sticky="w", padx=3, pady=(6, 0))
        self.info_printer()
        card = ttk.Frame(bt, style="Card.TFrame", padding=14); card.pack(side="right")
        ttk.Label(card, text="TOTAL", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.lbl_total = ttk.Label(card, text="Rp 0", style="Total.TLabel")
        self.lbl_total.grid(row=0, column=1, sticky="e", padx=(30, 0))
        ttk.Label(card, text="Metode (F11)", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.metode = tk.StringVar(value="Cash")
        cb = ttk.Combobox(card, textvariable=self.metode, values=["Cash", "QRIS", "Transfer"], state="readonly", width=14,
                          font=("Segoe UI", 12))
        cb.grid(row=1, column=1, sticky="e", pady=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.atur_metode())
        ttk.Label(card, text="Uang diterima (F10)", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.terima = tk.StringVar()
        self.ent_terima = ttk.Entry(card, textvariable=self.terima, width=16, justify="right", font=("Segoe UI", 13))
        self.ent_terima.grid(row=2, column=1, sticky="e", pady=4)
        ttk.Label(card, text="Kembalian", style="Card.TLabel").grid(row=3, column=0, sticky="w")
        self.lbl_kembali = ttk.Label(card, text="Rp 0", style="Kembali.TLabel")
        self.lbl_kembali.grid(row=3, column=1, sticky="e")
        ttk.Label(card, text="Laba transaksi", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=(4, 0))
        self.lbl_laba = ttk.Label(card, text="Rp 0", style="Card.TLabel", foreground="#7c3aed", font=("Segoe UI", 11, "bold"))
        self.lbl_laba.grid(row=4, column=1, sticky="e", pady=(4, 0))
        ttk.Button(card, text="Uang Pas", command=self.uang_pas).grid(row=5, column=0, pady=(10, 0), sticky="ew")
        ttk.Button(card, text="BAYAR (F12)", style="Accent.TButton", command=self.bayar).grid(
            row=5, column=1, pady=(10, 0), sticky="ew", padx=(30, 0))
        self.ent_terima.bind("<KeyRelease>", lambda e: self.hitung())
        self.ent_terima.bind("<Return>", lambda e: self.bayar())

    def on_key(self, e):
        if e.keysym not in ("Up", "Down", "Return", "Escape", "Tab"):
            self.filter()

    def filter(self):
        q = self.q.get().strip().lower()
        m = [i for i in self.items if q in i["name"].lower()]
        m.sort(key=lambda i: (not i["name"].lower().startswith(q), i["name"].lower()))
        self.cocok = m
        self.lb.delete(0, "end")
        for i in m:
            self.lb.insert("end", "%s   -   %s" % (i["name"], rp(i["price"])))
        if m:
            self.lb.selection_set(0)

    def geser(self, d):
        if self.cocok:
            c = self.lb.curselection()
            i = max(0, min((c[0] if c else -1) + d, len(self.cocok) - 1))
            self.lb.selection_clear(0, "end"); self.lb.selection_set(i); self.lb.see(i)
        return "break"

    def jumlah(self):
        try:
            return max(1, int(self.qty.get()))
        except Exception:
            return 1

    def masukkan(self, nama, harga, q, modal=0):
        self.modal[nama] = modal
        for k, it in enumerate(self.cart):
            if it[0] == nama and it[1] == harga:
                it[2] += q
                return self.draw(k)
        self.cart.append([nama, harga, q])
        self.draw(len(self.cart) - 1)

    def tambah(self):
        if not self.cocok:
            return messagebox.showinfo("Info", "Tidak ada barang yang cocok.\nGunakan 'Barang bebas' (F3).")
        c = self.lb.curselection()
        i = self.cocok[c[0] if c else 0]
        self.masukkan(i["name"], float(i["price"]), self.jumlah(), float(i.get("cost") or 0))
        self.q.set(""); self.qty.set(1); self.filter(); self.ent.focus_set()

    def tambah_bebas(self):
        n = simpledialog.askstring("Barang bebas", "Nama barang/jasa:")
        h = simpledialog.askfloat("Barang bebas", "Harga satuan:") if n else None
        m = simpledialog.askfloat("Barang bebas", "Modal/harga beli satuan (0 jika tidak ada):", initialvalue=0) if (n and h is not None) else None
        if n and h is not None:
            self.masukkan(n, h, self.jumlah(), m or 0)

    def sel(self, ketat=False):
        s = self.tv.selection()
        if s:
            return int(s[0])
        return None if ketat or not self.cart else len(self.cart) - 1

    def ubah_qty(self, d):
        i = self.sel()
        if i is not None:
            self.cart[i][2] += d
            if self.cart[i][2] <= 0:
                del self.cart[i]
            self.draw(i)

    def edit_harga(self):
        i = self.sel()
        if i is not None:
            h = simpledialog.askfloat("Edit Harga", "Harga baru untuk %s:" % self.cart[i][0], initialvalue=self.cart[i][1])
            if h is not None:
                self.cart[i][1] = h
            self.draw(i)

    def hapus_item(self):
        i = self.sel(True)
        if i is not None:
            del self.cart[i]; self.draw(i)

    def kosong(self):
        self.cart = []; self.draw()

    def total(self):
        return sum(h * q for _, h, q in self.cart)

    def draw(self, pilih=None):
        self.tv.delete(*self.tv.get_children())
        for k, (n, h, q) in enumerate(self.cart):
            self.tv.insert("", "end", iid=str(k), values=(n, rp(h), q, rp(h * q)))
        if pilih is not None and self.cart:
            p = str(min(pilih, len(self.cart) - 1))
            self.tv.selection_set(p); self.tv.focus(p); self.tv.see(p)
        self.lbl_total.config(text=rp(self.total())); self.hitung()

    def angka(self, s):
        s = s.replace("Rp", "").replace(".", "").replace(",", "").strip()
        return float(s) if s else None

    def laba(self):
        return sum((h - self.modal.get(n, 0)) * q for n, h, q in self.cart)

    def atur_metode(self):
        self.ent_terima.config(state="normal" if self.metode.get() == "Cash" else "disabled")
        self.hitung()

    def ganti_metode(self):
        v = ["Cash", "QRIS", "Transfer"]
        self.metode.set(v[(v.index(self.metode.get()) + 1) % 3]); self.atur_metode()

    def hitung(self):
        self.lbl_laba.config(text=rp(self.laba()))
        if self.metode.get() != "Cash":
            self.terima.set(str(int(self.total())))
            self.lbl_kembali.config(text="Rp 0", foreground="#16a34a")
            return
        try:
            d = self.angka(self.terima.get())
        except ValueError:
            d = None
        if d is None:
            self.lbl_kembali.config(text="Rp 0", foreground="#16a34a")
        else:
            x = d - self.total()
            self.lbl_kembali.config(text=rp(x) if x >= 0 else "Kurang " + rp(-x),
                                    foreground="#16a34a" if x >= 0 else "#dc2626")

    def uang_pas(self):
        self.terima.set(str(int(self.total()))); self.hitung(); self.ent_terima.focus_set()

    # ---------- PRINTER ----------
    def info_printer(self):
        self.lbl_prn.config(text="Printer struk: " + (CFG.get("printer") or "belum dipilih"))

    def pilih_printer(self):
        names = daftar_printer()
        if not names:
            messagebox.showwarning("Printer", "Tidak ada printer terdeteksi di komputer ini.")
            return None
        d = tk.Toplevel(self); d.title("Pilih Printer Struk"); d.transient(self); d.grab_set()
        ttk.Label(d, text="Struk dicetak ke printer mana?").pack(padx=15, pady=(12, 4), anchor="w")
        v = tk.StringVar(value=CFG.get("printer") if CFG.get("printer") in names else names[0])
        ttk.Combobox(d, textvariable=v, values=names, state="readonly", width=46).pack(padx=15)
        jd = tk.BooleanVar(value=True)
        ttk.Checkbutton(d, text="Jadikan printer default struk", variable=jd).pack(anchor="w", padx=15, pady=6)
        hasil = {}

        def ok(_=None):
            hasil["p"], hasil["d"] = v.get(), jd.get(); d.destroy()
        ttk.Button(d, text="OK (Enter)", command=ok).pack(pady=(0, 12))
        d.bind("<Return>", ok); d.bind("<Escape>", lambda e: d.destroy())
        self.wait_window(d)
        if "p" not in hasil:
            return None
        if hasil["d"]:
            CFG["printer"] = hasil["p"]
            json.dump(CFG, open(CFG_PATH, "w", encoding="utf-8"), indent=2)
            self.info_printer()
        return hasil["p"]

    def ganti_printer(self):
        self.pilih_printer()

    # ---------- BAYAR ----------
    def struk_teks(self, now, tot, dibayar):
        b = [NAMA_TOKO.center(32), now.strftime("%d-%m-%Y %H:%M").center(32), "-" * 32]
        for n, h, q in self.cart:
            b += [n[:32], "  %d x %s = %s" % (q, rp(h), rp(h * q))]
        b += ["-" * 32, "TOTAL   : " + rp(tot), "METODE  : " + self.metode.get(), "BAYAR   : " + rp(dibayar),
              "KEMBALI : " + rp(dibayar - tot), "", "Terima kasih".center(32)]
        return "\n".join(b)

    def preview(self, teks):
        d = tk.Toplevel(self); d.title("Preview Struk"); d.transient(self); d.grab_set(); d.configure(bg="#f3f5f9")
        ttk.Label(d, text="Preview struk - periksa sebelum dicetak", font=("Segoe UI", 11, "bold")).pack(padx=16, pady=(12, 6))
        t = tk.Text(d, width=34, height=min(30, teks.count("\n") + 2), font=("Consolas", 11), relief="flat", padx=12, pady=10)
        t.insert("1.0", teks); t.config(state="disabled"); t.pack(padx=16)
        ttk.Label(d, text="Printer: " + (CFG.get("printer") or "(belum dipilih)")).pack(pady=6)
        hasil = {}

        def pilih(v):
            hasil["v"] = v; d.destroy()
        bt = ttk.Frame(d); bt.pack(pady=(0, 12))
        ttk.Button(bt, text="Cetak & Simpan (Enter)", style="Accent.TButton", command=lambda: pilih("cetak")).pack(side="left", padx=4)
        ttk.Button(bt, text="Simpan tanpa cetak", command=lambda: pilih("simpan")).pack(side="left", padx=4)
        ttk.Button(bt, text="Batal (Esc)", command=d.destroy).pack(side="left", padx=4)
        d.bind("<Return>", lambda e: pilih("cetak")); d.bind("<Escape>", lambda e: d.destroy())
        d.focus_set(); self.wait_window(d)
        return hasil.get("v")

    def bayar(self):
        if not self.cart:
            return
        tot = self.total()
        try:
            dibayar = self.angka(self.terima.get())
        except ValueError:
            return messagebox.showwarning("Cek", "Uang diterima harus angka")
        if dibayar is None or self.metode.get() != "Cash":
            dibayar = tot
        if dibayar < tot:
            return messagebox.showwarning("Kurang", "Uang diterima kurang %s" % rp(tot - dibayar))
        teks = self.struk_teks(datetime.now(), tot, dibayar)
        aksi = self.preview(teks)
        if not aksi:
            return
        printer = None
        if aksi == "cetak":
            printer = CFG.get("printer") or self.pilih_printer()
            if not printer and not messagebox.askyesno("Tanpa struk", "Printer belum dipilih.\nSimpan transaksi tanpa cetak struk?"):
                return
        ket = "; ".join("%s x%d @%d" % (n, q, h) for n, h, q in self.cart)
        ok = self.safe(lambda: api("POST", "transactions", "", {
            "type": "income", "category": "Kasir", "description": ket, "amount": tot,
            "payment_method": self.metode.get(), "profit": self.laba()}) or True)
        if ok is None:
            return
        if printer:
            ok_cetak, pesan = cetak_teks(teks, printer)
            if not ok_cetak:
                messagebox.showwarning("Cetak gagal", "Transaksi sudah tersimpan, tetapi struk tidak tercetak:\n%s\n\nCek pilihan printer (F9)." % pesan)
        messagebox.showinfo("Selesai", "Kembalian: " + rp(dibayar - tot))
        self.cart = []; self.modal = {}; self.metode.set("Cash"); self.atur_metode(); self.terima.set("")
        self.draw(); self.load_trx(); self.ent.focus_set()

    # ---------- TRANSAKSI ----------
    def build_trx(self):
        f = self.t_trx
        top = ttk.Frame(f); top.pack(fill="x", padx=10, pady=8)
        self.x_tipe = tk.StringVar(value="income")
        self.x_kat, self.x_ket, self.x_jml = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Combobox(top, textvariable=self.x_tipe, values=["income", "expense"], width=9, state="readonly").pack(side="left")
        for lbl, var, w in (("Kategori", self.x_kat, 14), ("Keterangan", self.x_ket, 26), ("Jumlah", self.x_jml, 12)):
            ttk.Label(top, text=lbl).pack(side="left", padx=(8, 2))
            ttk.Entry(top, textvariable=var, width=w).pack(side="left")
        ttk.Button(top, text="Catat (Ctrl+S)", command=self.catat).pack(side="left", padx=8)
        ttk.Button(top, text="Hapus terpilih (F7)", command=self.hapus_trx).pack(side="left")
        ex = ttk.Frame(f); ex.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(ex, text="Ekspor PDF per").pack(side="left")
        self.x_per = tk.StringVar(value="Bulan")
        ttk.Combobox(ex, textvariable=self.x_per, values=["Hari", "Minggu", "Bulan", "Tahun"], width=8, state="readonly").pack(side="left", padx=5)
        ttk.Label(ex, text="tanggal acuan (YYYY-MM-DD)").pack(side="left", padx=(8, 2))
        self.x_acu = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(ex, textvariable=self.x_acu, width=12).pack(side="left")
        ttk.Button(ex, text="Ekspor PDF (Ctrl+P)", style="Accent.TButton", command=self.ekspor_pdf).pack(side="left", padx=8)
        self.x_view = tk.StringVar(value="riwayat")
        ttk.Radiobutton(ex, text="Rekap per hari", variable=self.x_view, value="rekap", command=self.ganti_view).pack(side="right", padx=4)
        ttk.Radiobutton(ex, text="Riwayat", variable=self.x_view, value="riwayat", command=self.ganti_view).pack(side="right", padx=4)
        self.lbl_sum = ttk.Label(f, text="", font=("Arial", 11, "bold")); self.lbl_sum.pack(anchor="w", padx=10)
        self.lbl_hari = ttk.Label(f, text="", font=("Segoe UI", 12, "bold"), foreground="#16a34a")
        self.lbl_hari.pack(side="bottom", anchor="e", padx=14, pady=6)
        self.tv_trx = ttk.Treeview(f, columns=("w", "t", "k", "m", "d", "j", "l"), show="headings", height=20)
        for c, t, w in (("w", "Waktu", 120), ("t", "Tipe", 60), ("k", "Kategori", 80), ("m", "Bayar", 80),
                        ("d", "Keterangan", 330), ("j", "Jumlah", 100), ("l", "Laba", 100)):
            self.tv_trx.heading(c, text=t); self.tv_trx.column(c, width=w)
        self.tv_trx.pack(fill="both", expand=True, padx=10, pady=5)
        pasang_garis(self.tv_trx, ("j", "l"))
        self.tv_rek = ttk.Treeview(f, columns=("t", "n", "m", "k", "l"), show="headings", height=20)
        for c, t, w in (("t", "Tanggal", 140), ("n", "Transaksi", 90), ("m", "Pemasukan", 160),
                        ("k", "Pengeluaran", 160), ("l", "Laba penjualan", 160)):
            self.tv_rek.heading(c, text=t); self.tv_rek.column(c, width=w)
        pasang_garis(self.tv_rek, ("n", "m", "k", "l"))

    def catat(self):
        try:
            j = float(self.x_jml.get())
        except ValueError:
            return messagebox.showwarning("Cek", "Jumlah harus angka")
        self.safe(lambda: api("POST", "transactions", "", {"type": self.x_tipe.get(), "category": self.x_kat.get(),
                                                             "description": self.x_ket.get(), "amount": j}))
        self.x_jml.set(""); self.x_ket.set(""); self.load_trx()

    def ekspor_pdf(self):
        try:
            acu = datetime.strptime(self.x_acu.get().strip(), "%Y-%m-%d")
        except ValueError:
            return messagebox.showwarning("Cek", "Tanggal acuan harus berbentuk YYYY-MM-DD, contoh 2026-11-09")
        jenis = self.x_per.get()
        if jenis == "Hari":
            a = acu; b = a + timedelta(days=1)
            nama = "Hari %s" % a.strftime("%d-%m-%Y")
        elif jenis == "Minggu":
            a = acu - timedelta(days=acu.weekday()); b = a + timedelta(days=7)
            nama = "Minggu %s s/d %s" % (a.strftime("%d-%m-%Y"), (b - timedelta(days=1)).strftime("%d-%m-%Y"))
        elif jenis == "Bulan":
            a = acu.replace(day=1); b = (a + timedelta(days=32)).replace(day=1)
            nama = "Bulan %s" % a.strftime("%m-%Y")
        else:
            a = acu.replace(month=1, day=1); b = a.replace(year=a.year + 1)
            nama = "Tahun %d" % a.year
        q = "?select=*&order=created_at.asc&limit=10000&created_at=gte.%s&created_at=lt.%s" % (
            urllib.parse.quote(a.astimezone().isoformat()), urllib.parse.quote(b.astimezone().isoformat()))
        r = self.safe(lambda: api("GET", "transactions", q))
        if r is None:
            return
        if not r:
            return messagebox.showinfo("Kosong", "Tidak ada transaksi pada periode ini")
        m = k = lb = 0; pm = {}; baris = []; hr = {}
        fmt = "%-14s %-6s %-8s %-40s %13s %11s"
        rb = lambda n: "{:,.0f}".format(float(n)).replace(",", ".")
        for t in r:
            v = float(t["amount"]); inc = t["type"] == "income"
            if inc:
                m += v; p = t.get("payment_method") or "-"; pm[p] = pm.get(p, 0) + v
            else:
                k += v
            lab = t.get("profit"); lb += float(lab or 0)
            d = lokal(t["created_at"]).date(); z = hr.setdefault(d, [0, 0.0, 0.0, 0.0]); z[0] += 1
            if inc:
                z[1] += v
            else:
                z[2] += v
            z[3] += float(lab or 0)
            ket = textwrap.wrap(t.get("description") or t.get("category") or "-", 40) or [""]
            baris.append(fmt % (lokal(t["created_at"]).strftime("%d-%m-%y %H:%M"), "Masuk" if inc else "Keluar",
                                (t.get("payment_method") or "-")[:8], ket[0], rb(v), "-" if lab is None else rb(lab)))
            baris += [" " * 31 + x for x in ket[1:]]
        ringkas = ["Jumlah transaksi : %d" % len(r), "Pemasukan        : " + rp(m), "Pengeluaran      : " + rp(k),
                   "Saldo            : " + rp(m - k), "Laba penjualan   : " + rp(lb)]
        ringkas += ["Pemasukan %-8s : %s" % (p, rp(v)) for p, v in sorted(pm.items())]
        if jenis != "Hari":
            ringkas += ["", "REKAP PER HARI", "%-12s %5s %15s %15s %15s" % ("Tanggal", "Trx", "Pemasukan", "Pengeluaran", "Laba")]
            ringkas += ["%-12s %5d %15s %15s %15s" % (d.strftime("%d-%m-%Y"), z[0], rb(z[1]), rb(z[2]), rb(z[3]))
                        for d, z in sorted(hr.items())]
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                                            initialfile=("Riwayat %s.pdf" % nama).replace("/", "-"))
        if not path:
            return
        tulis_pdf(path, NAMA_TOKO + " - Riwayat Transaksi",
                  "Periode: %s   |   Dicetak: %s" % (nama, datetime.now().strftime("%d-%m-%Y %H:%M")),
                  ringkas, fmt % ("Waktu", "Tipe", "Bayar", "Keterangan", "Jumlah", "Laba"), baris)
        try:
            os.startfile(path)
        except Exception:
            messagebox.showinfo("PDF", "Tersimpan: " + path)

    def ganti_view(self):
        self.tv_trx.pack_forget(); self.tv_rek.pack_forget()
        w = self.tv_rek if self.x_view.get() == "rekap" else self.tv_trx
        w.pack(fill="both", expand=True, padx=10, pady=5)

    def toggle_view(self):
        self.nb.select(1)
        self.x_view.set("riwayat" if self.x_view.get() == "rekap" else "rekap"); self.ganti_view()

    def load_rekap(self):
        awal = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)
        q = "?select=*&order=created_at.desc&limit=5000&created_at=gte." + urllib.parse.quote(awal.astimezone().isoformat())
        r = self.safe(lambda: api("GET", "transactions", q)) or []
        hr = {}
        for t in r:
            d = lokal(t["created_at"]).date(); z = hr.setdefault(d, [0, 0, 0, 0])
            z[0] += 1
            if t["type"] == "income":
                z[1] += t["amount"]
            else:
                z[2] += t["amount"]
            z[3] += t.get("profit") or 0
        self.tv_rek.delete(*self.tv_rek.get_children())
        for d, z in sorted(hr.items(), reverse=True):
            self.tv_rek.insert("", "end", values=(d.strftime("%d-%m-%Y"), z[0], rp(z[1]), rp(z[2]), rp(z[3])))
        h = hr.get(datetime.now().date(), [0, 0, 0, 0])
        self.lbl_hari.config(text="Total pemasukan hari ini: " + rp(h[1]))

    def hapus_trx(self):
        s = self.tv_trx.selection()
        if s and messagebox.askyesno("Hapus", "Hapus transaksi terpilih?"):
            self.safe(lambda: api("DELETE", "transactions", "?id=eq." + s[0]))
            self.load_trx()

    def load_trx(self):
        r = self.safe(lambda: api("GET", "transactions", "?select=*&order=created_at.desc&limit=500")) or []
        self.tv_trx.delete(*self.tv_trx.get_children())
        m = k = lb = 0
        for t in r:
            lab = t.get("profit")
            self.tv_trx.insert("", "end", iid=str(t["id"]), values=(
                lokal(t["created_at"]).strftime("%d-%m-%y %H:%M"), "Masuk" if t["type"] == "income" else "Keluar",
                t.get("category") or "", t.get("payment_method") or "-", t.get("description") or "", rp(t["amount"]),
                "-" if lab is None else rp(lab)))
            if t["type"] == "income": m += t["amount"]
            else: k += t["amount"]
            lb += lab or 0
        self.lbl_sum.config(text="Pemasukan %s  |  Pengeluaran %s  |  Saldo %s  |  Laba penjualan %s  (500 terakhir)"
                            % (rp(m), rp(k), rp(m - k), rp(lb)))
        self.load_rekap()


if __name__ == "__main__":
    a = App()
    if a.ok:
        a.mainloop()
    else:
        a.destroy()
