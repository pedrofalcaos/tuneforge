# -*- coding: utf-8 -*-
"""
Conversor de Vídeo/Áudio -> MP3
-------------------------------
Converte arquivos locais (MP4, MPEG, MPG, AVI, MKV, MOV, WEBM, M4A, WAV...)
para MP3 de alta qualidade usando o ffmpeg embutido (imageio-ffmpeg).

Dependência:
    pip install imageio-ffmpeg
"""

import os
import re
import shutil
import tempfile
import threading
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ---------------------------------------------------------------------------
# Preparação do ffmpeg embutido
# ---------------------------------------------------------------------------
def _preparar_ffmpeg():
    """Copia o binário do imageio-ffmpeg para um nome padrão e retorna o caminho."""
    try:
        import imageio_ffmpeg
        src = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    cache_dir = os.path.join(tempfile.gettempdir(), "ytmp3_ffmpeg")
    os.makedirs(cache_dir, exist_ok=True)
    nome = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    dst = os.path.join(cache_dir, nome)
    try:
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copy2(src, dst)
        return dst
    except Exception:
        return src


FFMPEG = _preparar_ffmpeg()

EXTENSOES = [
    ("Vídeo/Áudio", "*.mp4 *.mpeg *.mpg *.avi *.mkv *.mov *.webm *.flv "
                    "*.m4a *.wav *.aac *.ogg *.wma *.3gp *.ts"),
    ("Todos os arquivos", "*.*"),
]


# ---------------------------------------------------------------------------
# Paleta de cores (UI)
# ---------------------------------------------------------------------------
BG = "#1e1e2e"          # fundo principal
CARD = "#2a2a3c"        # cartões
ACCENT = "#7c5cff"      # roxo destaque
ACCENT_HOVER = "#9277ff"
TEXT = "#e6e6f0"
MUTED = "#9a9ab0"
OK = "#3ecf8e"
ERR = "#ff6b6b"


class Conversor:
    """Executa a conversão de um arquivo para MP3 reportando progresso."""

    def __init__(self, fila):
        self.fila = fila

    def converter(self, entrada, saida, bitrate):
        # Descobre a duração total para calcular o progresso (%)
        duracao = self._duracao(entrada)

        cmd = [
            FFMPEG,
            "-y",                  # sobrescreve se já existir
            "-i", entrada,
            "-vn",                 # ignora vídeo (só áudio)
            "-acodec", "libmp3lame",
            "-b:a", f"{bitrate}k",
            "-progress", "pipe:1",  # progresso legível por máquina
            "-nostats",
            saida,
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=creationflags,
        )

        for linha in proc.stdout:
            linha = linha.strip()
            if linha.startswith("out_time_ms=") and duracao:
                try:
                    ms = int(linha.split("=", 1)[1])
                    pct = min(100, (ms / 1_000_000) / duracao * 100)
                    self.fila.put(("progress", pct))
                except (ValueError, ZeroDivisionError):
                    pass
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg retornou código {proc.returncode}")

    def _duracao(self, arquivo):
        """Retorna a duração em segundos lendo a saída do ffmpeg."""
        cmd = [FFMPEG, "-i", arquivo, "-hide_banner"]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            out = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, encoding="utf-8", errors="ignore",
                creationflags=creationflags,
            ).stdout
        except Exception:
            return 0
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out or "")
        if not m:
            return 0
        h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + mn * 60 + s


# ---------------------------------------------------------------------------
# Interface gráfica
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conversor MP3")
        self.geometry("660x560")
        self.minsize(660, 560)
        self.configure(bg=BG)

        self.fila = queue.Queue()
        self.conversor = Conversor(self.fila)
        self.arquivos = []           # lista de caminhos de entrada
        self.convertendo = False

        self._setup_estilo()
        self._build_ui()
        self.after(100, self._processar_fila)

        if not FFMPEG:
            messagebox.showerror(
                "ffmpeg ausente",
                "Instale o ffmpeg embutido:\n\npip install imageio-ffmpeg",
            )

    # ---- Estilo ----------------------------------------------------------
    def _setup_estilo(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        s.configure("Title.TLabel", background=BG, foreground=TEXT,
                    font=("Segoe UI Semibold", 18))
        s.configure("Sub.TLabel", background=BG, foreground=MUTED,
                    font=("Segoe UI", 9))
        s.configure("Card.TLabel", background=CARD, foreground=TEXT,
                    font=("Segoe UI", 10))

        s.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=("Segoe UI Semibold", 11), borderwidth=0, focuscolor=BG,
                    padding=(10, 10))
        s.map("Accent.TButton",
              background=[("active", ACCENT_HOVER), ("disabled", "#4a4a5e")])

        s.configure("Ghost.TButton", background=CARD, foreground=TEXT,
                    font=("Segoe UI", 10), borderwidth=0, padding=(10, 6))
        s.map("Ghost.TButton", background=[("active", "#3a3a50")])

        s.configure("TCombobox", fieldbackground=CARD, background=CARD,
                    foreground=TEXT, arrowcolor=TEXT)
        s.configure("Accent.Horizontal.TProgressbar", background=ACCENT,
                    troughcolor=CARD, borderwidth=0, thickness=10)

    # ---- Layout ----------------------------------------------------------
    def _build_ui(self):
        root = ttk.Frame(self, padding=22)
        root.pack(fill="both", expand=True)

        # Cabeçalho
        ttk.Label(root, text="🎵  Conversor para MP3", style="Title.TLabel").pack(
            anchor="w")
        ttk.Label(root, text="Converta MP4, MPEG e outros formatos em MP3 de alta "
                             "qualidade.", style="Sub.TLabel").pack(anchor="w",
                                                                    pady=(2, 16))

        # Cartão: lista de arquivos
        card = ttk.Frame(root, style="Card.TFrame", padding=14)
        card.pack(fill="both", expand=True)

        topo = ttk.Frame(card, style="Card.TFrame")
        topo.pack(fill="x")
        ttk.Label(topo, text="Arquivos para converter", style="Card.TLabel",
                  font=("Segoe UI Semibold", 11)).pack(side="left")
        ttk.Button(topo, text="🗑 Limpar", style="Ghost.TButton",
                   command=self._limpar).pack(side="right")
        ttk.Button(topo, text="➕ Adicionar arquivos", style="Ghost.TButton",
                   command=self._adicionar).pack(side="right", padx=(0, 8))

        # Listbox com os arquivos
        lista_frame = tk.Frame(card, bg=CARD)
        lista_frame.pack(fill="both", expand=True, pady=(12, 4))
        self.listbox = tk.Listbox(
            lista_frame, bg="#23232f", fg=TEXT, selectbackground=ACCENT,
            selectforeground="white", borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10), activestyle="none",
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lista_frame, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        self.placeholder = ttk.Label(
            card, text="Nenhum arquivo. Clique em “Adicionar arquivos”.",
            style="Card.TLabel", foreground=MUTED)
        self.placeholder.pack()

        # Opções
        opc = ttk.Frame(root, padding=(0, 14, 0, 0))
        opc.pack(fill="x")

        ttk.Label(opc, text="Salvar em:").grid(row=0, column=0, sticky="w")
        self.pasta_var = tk.StringVar(value="(mesma pasta dos arquivos)")
        ent = tk.Entry(opc, textvariable=self.pasta_var, bg=CARD, fg=TEXT,
                       insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        ent.grid(row=0, column=1, sticky="we", padx=8, ipady=5)
        ttk.Button(opc, text="Escolher...", style="Ghost.TButton",
                   command=self._escolher_pasta).grid(row=0, column=2)

        ttk.Label(opc, text="Qualidade:").grid(row=1, column=0, sticky="w",
                                               pady=(12, 0))
        self.bitrate_var = tk.StringVar(value="320")
        ttk.Combobox(opc, textvariable=self.bitrate_var, state="readonly", width=8,
                     values=["128", "192", "256", "320"]).grid(
            row=1, column=1, sticky="w", padx=8, pady=(12, 0))

        opc.columnconfigure(1, weight=1)

        # Progresso + status
        self.progress = ttk.Progressbar(root, style="Accent.Horizontal.TProgressbar",
                                        maximum=100)
        self.progress.pack(fill="x", pady=(16, 4))
        self.status = ttk.Label(root, text="Pronto.", style="Sub.TLabel")
        self.status.pack(anchor="w")

        # Botão converter
        self.btn = ttk.Button(root, text="Converter para MP3", style="Accent.TButton",
                              command=self._iniciar)
        self.btn.pack(fill="x", pady=(12, 0))

    # ---- Ações -----------------------------------------------------------
    def _adicionar(self):
        novos = filedialog.askopenfilenames(title="Escolha os arquivos",
                                            filetypes=EXTENSOES)
        for caminho in novos:
            if caminho not in self.arquivos:
                self.arquivos.append(caminho)
                self.listbox.insert("end", "  " + os.path.basename(caminho))
        self._atualizar_placeholder()

    def _limpar(self):
        if self.convertendo:
            return
        self.arquivos.clear()
        self.listbox.delete(0, "end")
        self._atualizar_placeholder()

    def _atualizar_placeholder(self):
        if self.arquivos:
            self.placeholder.pack_forget()
        else:
            self.placeholder.pack()

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.pasta_var.set(pasta)

    def _iniciar(self):
        if self.convertendo:
            return
        if not self.arquivos:
            messagebox.showwarning("Atenção", "Adicione pelo menos um arquivo.")
            return
        if not FFMPEG:
            messagebox.showerror("Erro", "ffmpeg não disponível.")
            return

        self.convertendo = True
        self.btn.configure(state="disabled", text="Convertendo...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        bitrate = self.bitrate_var.get()
        pasta_destino = self.pasta_var.get()
        usar_mesma = pasta_destino.startswith("(") or not os.path.isdir(pasta_destino)

        total = len(self.arquivos)
        sucesso = 0
        for i, entrada in enumerate(self.arquivos, start=1):
            nome = os.path.splitext(os.path.basename(entrada))[0]
            destino_dir = os.path.dirname(entrada) if usar_mesma else pasta_destino
            saida = os.path.join(destino_dir, nome + ".mp3")

            self.fila.put(("status", f"Convertendo {i}/{total}: {nome}"))
            self.fila.put(("progress", 0))
            try:
                self.conversor.converter(entrada, saida, bitrate)
                sucesso += 1
                self.fila.put(("status", f"OK {i}/{total}: {nome}.mp3"))
            except Exception as e:
                self.fila.put(("erro_item", f"Falha em {nome}: {e}"))
        self.fila.put(("fim", (sucesso, total)))

    def _processar_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "progress":
                    self.progress["value"] = dado
                elif tipo == "status":
                    self.status.configure(text=dado, foreground=MUTED)
                elif tipo == "erro_item":
                    self.status.configure(text=dado, foreground=ERR)
                elif tipo == "fim":
                    sucesso, total = dado
                    self.progress["value"] = 100
                    cor = OK if sucesso == total else ERR
                    self.status.configure(
                        text=f"Concluído: {sucesso}/{total} convertido(s).",
                        foreground=cor)
                    self.convertendo = False
                    self.btn.configure(state="normal", text="Converter para MP3")
                    messagebox.showinfo(
                        "Concluído",
                        f"{sucesso} de {total} arquivo(s) convertido(s) em MP3.")
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)


if __name__ == "__main__":
    App().mainloop()
