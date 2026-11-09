import json, os, sys, tempfile, subprocess, hashlib, base64, secrets, threading, webbrowser, http.server
import urllib.request, urllib.error, urllib.parse
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

NAMA_TOKO = "ANUGRAH FOTOCOPY"
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
  F10         Fokus ke kolom "Uang diterima" (kembalian dihitung otomatis)
  F12         Bayar: tampil preview struk dulu, Enter untuk cetak & simpan, Esc untuk batal

TRANSAKSI & BARANG
  Ctrl+S      Catat transaksi (tab Transaksi) / Simpan barang (tab Barang)
  F7          Hapus data terpilih

PRINTER STRUK
  Saat pertama kali cetak, pilih printer lalu centang "Jadikan printer default".
  Setelah itu struk langsung dicetak ke printer tersebut.
  Untuk mengganti printer, tekan F9 atau klik tombol "Ganti Printer".

TIPS
  Jika item yang sama dengan harga yang sama ditambahkan lagi, qty-nya otomatis bertambah.
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


def daftar_printer():
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Printer | Select-Object -ExpandProperty Name"],
            text=True, timeout=20, creationflags=NOWIN)
        return [x.strip() for x in out.splitlines() if x.strip()]
    except Exception:
        return []


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(NAMA_TOKO + " - Keuangan")
        self.geometry("1040x740")
        self.tema()
        self.ok = False
        self.withdraw()
        if not self.masuk():
            return
        self.deiconify()
        hd = tk.Frame(self, bg="#2563eb"); hd.pack(fill="x")
        tk.Label(hd, text=NAMA_TOKO, bg="#2563eb", fg="#ffffff", font=("Segoe UI", 15, "bold")).pack(side="left", padx=16, pady=10)
        tk.Label(hd, text="Kasir & Keuangan", bg="#2563eb", fg="#bfdbfe", font=("Segoe UI", 10)).pack(side="left")
        tk.Button(hd, text="Keluar", command=self.keluar, bg="#1d4ed8", fg="#ffffff", relief="flat", bd=0, padx=10).pack(side="right", padx=12)
        tk.Label(hd, text=SES.get("email", ""), bg="#2563eb", fg="#dbeafe", font=("Segoe UI", 10)).pack(side="right")
        self.items, self.cart, self.cocok = [], [], []
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
        s.configure("Treeview", rowheight=30, background="#ffffff", fieldbackground="#ffffff", borderwidth=0)
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
        self.b_nama, self.b_harga = tk.StringVar(), tk.StringVar()
        ttk.Label(top, text="Nama barang/jasa").pack(side="left")
        ttk.Entry(top, textvariable=self.b_nama, width=28).pack(side="left", padx=5)
        ttk.Label(top, text="Harga").pack(side="left")
        ttk.Entry(top, textvariable=self.b_harga, width=12).pack(side="left", padx=5)
        ttk.Button(top, text="Simpan/Tambah (Ctrl+S)", command=self.simpan_barang).pack(side="left", padx=3)
        ttk.Button(top, text="Hapus terpilih (F7)", command=self.hapus_barang).pack(side="left", padx=3)
        self.tv_brg = ttk.Treeview(f, columns=("nama", "harga"), show="headings", height=20)
        self.tv_brg.heading("nama", text="Nama"); self.tv_brg.heading("harga", text="Harga")
        self.tv_brg.pack(fill="both", expand=True, padx=10, pady=5)
        self.tv_brg.bind("<<TreeviewSelect>>", self.pilih_barang)

    def load_items(self):
        r = self.safe(lambda: api("GET", "items", "?select=*&order=name"))
        self.items = r or []
        self.tv_brg.delete(*self.tv_brg.get_children())
        for i in self.items:
            self.tv_brg.insert("", "end", iid=str(i["id"]), values=(i["name"], rp(i["price"])))
        self.filter()

    def pilih_barang(self, _):
        s = self.tv_brg.selection()
        if s:
            i = next(x for x in self.items if str(x["id"]) == s[0])
            self.b_nama.set(i["name"]); self.b_harga.set(int(i["price"]))

    def simpan_barang(self):
        try:
            nama, harga = self.b_nama.get().strip(), float(self.b_harga.get())
        except ValueError:
            return messagebox.showwarning("Cek", "Harga harus angka")
        if not nama:
            return
        ada = next((x for x in self.items if x["name"].lower() == nama.lower()), None)
        if ada:
            self.safe(lambda: api("PATCH", "items", "?id=eq.%s" % ada["id"], {"name": nama, "price": harga}))
        else:
            self.safe(lambda: api("POST", "items", "", {"name": nama, "price": harga}))
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
        self.lb = tk.Listbox(f, height=5, exportselection=False, font=("Segoe UI", 11), relief="flat", highlightthickness=1,
                             highlightbackground="#d5dbe9", selectbackground="#2563eb", selectforeground="#ffffff")
        self.lb.pack(fill="x", padx=10, pady=(0, 6))
        self.ent.bind("<KeyRelease>", self.on_key)
        self.ent.bind("<Return>", lambda e: self.tambah())
        self.ent.bind("<Down>", lambda e: self.geser(1)); self.ent.bind("<Up>", lambda e: self.geser(-1))
        self.ent.bind("<Escape>", lambda e: (self.q.set(""), self.filter()))
        self.lb.bind("<Double-1>", lambda e: self.tambah())

        self.tv = ttk.Treeview(f, columns=("n", "h", "q", "s"), show="headings", height=12)
        for c, t, w in (("n", "Barang", 380), ("h", "Harga", 130), ("q", "Qty", 60), ("s", "Subtotal", 140)):
            self.tv.heading(c, text=t); self.tv.column(c, width=w)
        self.tv.pack(fill="both", expand=True, padx=10)
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
        ttk.Label(card, text="Uang diterima (F10)", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.terima = tk.StringVar()
        self.ent_terima = ttk.Entry(card, textvariable=self.terima, width=16, justify="right", font=("Segoe UI", 13))
        self.ent_terima.grid(row=1, column=1, sticky="e", pady=6)
        ttk.Label(card, text="Kembalian", style="Card.TLabel").grid(row=2, column=0, sticky="w")
        self.lbl_kembali = ttk.Label(card, text="Rp 0", style="Kembali.TLabel")
        self.lbl_kembali.grid(row=2, column=1, sticky="e")
        ttk.Button(card, text="Uang Pas", command=self.uang_pas).grid(row=3, column=0, pady=(10, 0), sticky="ew")
        ttk.Button(card, text="BAYAR (F12)", style="Accent.TButton", command=self.bayar).grid(
            row=3, column=1, pady=(10, 0), sticky="ew", padx=(30, 0))
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

    def masukkan(self, nama, harga, q):
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
        self.masukkan(i["name"], float(i["price"]), self.jumlah())
        self.q.set(""); self.qty.set(1); self.filter(); self.ent.focus_set()

    def tambah_bebas(self):
        n = simpledialog.askstring("Barang bebas", "Nama barang/jasa:")
        h = simpledialog.askfloat("Barang bebas", "Harga satuan:") if n else None
        if n and h is not None:
            self.masukkan(n, h, self.jumlah())

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

    def hitung(self):
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
        b += ["-" * 32, "TOTAL   : " + rp(tot), "BAYAR   : " + rp(dibayar),
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
        if dibayar is None:
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
            "type": "income", "category": "Kasir", "description": ket, "amount": tot}) or True)
        if ok is None:
            return
        if printer:
            path = os.path.join(tempfile.gettempdir(), "struk.txt")
            open(path, "w", encoding="utf-8").write(teks)
            try:
                subprocess.Popen(["notepad.exe", "/pt", path, printer], creationflags=NOWIN)
            except Exception:
                messagebox.showinfo("Struk", teks)
        messagebox.showinfo("Selesai", "Kembalian: " + rp(dibayar - tot))
        self.cart = []; self.terima.set(""); self.draw(); self.load_trx(); self.ent.focus_set()

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
        self.lbl_sum = ttk.Label(f, text="", font=("Arial", 11, "bold")); self.lbl_sum.pack(anchor="w", padx=10)
        self.tv_trx = ttk.Treeview(f, columns=("w", "t", "k", "d", "j"), show="headings", height=20)
        for c, t, w in (("w", "Waktu", 130), ("t", "Tipe", 80), ("k", "Kategori", 100), ("d", "Keterangan", 420), ("j", "Jumlah", 120)):
            self.tv_trx.heading(c, text=t); self.tv_trx.column(c, width=w)
        self.tv_trx.pack(fill="both", expand=True, padx=10, pady=5)

    def catat(self):
        try:
            j = float(self.x_jml.get())
        except ValueError:
            return messagebox.showwarning("Cek", "Jumlah harus angka")
        self.safe(lambda: api("POST", "transactions", "", {"type": self.x_tipe.get(), "category": self.x_kat.get(),
                                                             "description": self.x_ket.get(), "amount": j}))
        self.x_jml.set(""); self.x_ket.set(""); self.load_trx()

    def hapus_trx(self):
        s = self.tv_trx.selection()
        if s and messagebox.askyesno("Hapus", "Hapus transaksi terpilih?"):
            self.safe(lambda: api("DELETE", "transactions", "?id=eq." + s[0]))
            self.load_trx()

    def load_trx(self):
        r = self.safe(lambda: api("GET", "transactions", "?select=*&order=created_at.desc&limit=500")) or []
        self.tv_trx.delete(*self.tv_trx.get_children())
        m = k = 0
        for t in r:
            w = t["created_at"][:16].replace("T", " ")
            self.tv_trx.insert("", "end", iid=str(t["id"]), values=(w, "Masuk" if t["type"] == "income" else "Keluar",
                                                                    t.get("category") or "", t.get("description") or "", rp(t["amount"])))
            if t["type"] == "income": m += t["amount"]
            else: k += t["amount"]
        self.lbl_sum.config(text="Pemasukan %s   |   Pengeluaran %s   |   Saldo %s (500 transaksi terakhir)" % (rp(m), rp(k), rp(m - k)))


if __name__ == "__main__":
    a = App()
    if a.ok:
        a.mainloop()
    else:
        a.destroy()
