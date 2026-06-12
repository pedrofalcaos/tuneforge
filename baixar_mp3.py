# -*- coding: utf-8 -*-
"""
Baixador de Música do YouTube -> MP3
------------------------------------
Interface gráfica simples para baixar áudio do YouTube e converter em MP3
de alta qualidade, sem corromper o arquivo.

Dependências (instale com):
    pip install yt-dlp imageio-ffmpeg

O ffmpeg vem embutido no pacote imageio-ffmpeg, então NÃO precisa instalar
ffmpeg manualmente no Windows.
"""

import os
import sys
import shutil
import tempfile
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Importação das dependências com mensagem amigável caso faltem
# ---------------------------------------------------------------------------
try:
    import yt_dlp
except ImportError:
    print("Falta a biblioteca yt-dlp. Instale com:  pip install yt-dlp")
    sys.exit(1)

def _preparar_ffmpeg():
    """
    O binário do imageio-ffmpeg tem um nome que o yt-dlp não reconhece
    (ex: ffmpeg-win-x86_64-v7.1.exe). Copiamos para uma pasta de cache com
    o nome 'ffmpeg.exe' para que o yt-dlp o encontre automaticamente.
    Retorna a pasta contendo o ffmpeg, ou None se indisponível.
    """
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
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
    except Exception:
        # Se a cópia falhar, tenta usar a pasta original mesmo assim
        return os.path.dirname(src)
    return cache_dir


FFMPEG_DIR = _preparar_ffmpeg()
FFMPEG_PATH = FFMPEG_DIR  # apenas para checagem de disponibilidade na UI


# ---------------------------------------------------------------------------
# Lógica de download
# ---------------------------------------------------------------------------
class Downloader:
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def _hook(self, d):
        """Recebe atualizações de progresso do yt-dlp."""
        status = d.get("status")
        if status == "downloading":
            pct = d.get("_percent_str", "").strip()
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            self.log_queue.put(("progress", d.get("_percent_estimate", 0)))
            self.log_queue.put(("log", f"Baixando... {pct}  {speed}  ETA {eta}"))
        elif status == "finished":
            self.log_queue.put(("log", "Download concluído. Convertendo para MP3..."))
            self.log_queue.put(("progress", 100))

    def baixar(self, url, pasta, nome, bitrate, embed_thumb, embed_meta):
        # Define o template do nome do arquivo de saída
        if nome and nome.strip():
            # Remove caracteres inválidos para nome de arquivo no Windows
            nome_limpo = "".join(c for c in nome.strip() if c not in '\\/:*?"<>|')
            outtmpl = os.path.join(pasta, nome_limpo + ".%(ext)s")
        else:
            outtmpl = os.path.join(pasta, "%(title)s.%(ext)s")

        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(bitrate),
            }
        ]
        if embed_meta:
            postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
        if embed_thumb:
            postprocessors.append({"key": "EmbedThumbnail"})

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": postprocessors,
            "writethumbnail": embed_thumb,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._hook],
            # Garante integridade: refaz partes que falharem
            "retries": 10,
            "fragment_retries": 10,
            "continuedl": True,
            # Mantém o arquivo limpo, sem sobrescrever silenciosamente
            "overwrites": False,
        }

        # Aponta para o ffmpeg embutido, se disponível
        if FFMPEG_DIR:
            ydl_opts["ffmpeg_location"] = FFMPEG_DIR

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            titulo = info.get("title", "arquivo")
            return titulo


# ---------------------------------------------------------------------------
# Interface gráfica
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube -> MP3")
        self.geometry("620x430")
        self.resizable(False, False)

        self.log_queue = queue.Queue()
        self.downloader = Downloader(self.log_queue)
        self.baixando = False

        self._build_ui()
        self.after(100, self._processar_fila)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)

        # Link
        ttk.Label(frame, text="Link do YouTube:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.url_var, width=58).grid(
            row=1, column=0, columnspan=3, sticky="we", pady=(0, 8)
        )

        # Pasta
        ttk.Label(frame, text="Pasta para salvar:").grid(row=2, column=0, sticky="w")
        self.pasta_var = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Music")
        )
        ttk.Entry(frame, textvariable=self.pasta_var, width=46).grid(
            row=3, column=0, columnspan=2, sticky="we"
        )
        ttk.Button(frame, text="Escolher...", command=self._escolher_pasta).grid(
            row=3, column=2, sticky="we", padx=(8, 0)
        )

        # Nome
        ttk.Label(
            frame, text="Nome do arquivo (vazio = título do vídeo):"
        ).grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.nome_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.nome_var, width=58).grid(
            row=5, column=0, columnspan=3, sticky="we", pady=(0, 8)
        )

        # Opções: qualidade + checkboxes
        opt = ttk.Frame(frame)
        opt.grid(row=6, column=0, columnspan=3, sticky="we", pady=(4, 4))

        ttk.Label(opt, text="Qualidade (kbps):").pack(side="left")
        self.bitrate_var = tk.StringVar(value="320")
        ttk.Combobox(
            opt,
            textvariable=self.bitrate_var,
            values=["128", "192", "256", "320"],
            width=6,
            state="readonly",
        ).pack(side="left", padx=(6, 16))

        self.thumb_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Capa (thumbnail)", variable=self.thumb_var).pack(
            side="left", padx=(0, 12)
        )
        self.meta_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Metadados", variable=self.meta_var).pack(side="left")

        # Botão baixar
        self.btn = ttk.Button(frame, text="Baixar MP3", command=self._iniciar)
        self.btn.grid(row=7, column=0, columnspan=3, sticky="we", pady=(12, 6))

        # Barra de progresso
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=8, column=0, columnspan=3, sticky="we", pady=(0, 6))

        # Log
        self.log = tk.Text(frame, height=6, width=70, state="disabled", wrap="word")
        self.log.grid(row=9, column=0, columnspan=3, sticky="we")

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        if not FFMPEG_PATH:
            self._log(
                "AVISO: ffmpeg não encontrado. Instale com: pip install imageio-ffmpeg"
            )

    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(initialdir=self.pasta_var.get() or "/")
        if pasta:
            self.pasta_var.set(pasta)

    def _log(self, texto):
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _iniciar(self):
        if self.baixando:
            return
        url = self.url_var.get().strip()
        pasta = self.pasta_var.get().strip()

        if not url:
            messagebox.showwarning("Atenção", "Cole o link do YouTube.")
            return
        if not pasta:
            messagebox.showwarning("Atenção", "Escolha uma pasta para salvar.")
            return
        os.makedirs(pasta, exist_ok=True)

        self.baixando = True
        self.btn.configure(state="disabled", text="Baixando...")
        self.progress["value"] = 0
        self._log(f"Iniciando: {url}")

        t = threading.Thread(
            target=self._worker,
            args=(
                url,
                pasta,
                self.nome_var.get(),
                self.bitrate_var.get(),
                self.thumb_var.get(),
                self.meta_var.get(),
            ),
            daemon=True,
        )
        t.start()

    def _worker(self, url, pasta, nome, bitrate, thumb, meta):
        try:
            titulo = self.downloader.baixar(url, pasta, nome, bitrate, thumb, meta)
            self.log_queue.put(("done", titulo))
        except Exception as e:
            self.log_queue.put(("error", str(e)))

    def _processar_fila(self):
        try:
            while True:
                tipo, dado = self.log_queue.get_nowait()
                if tipo == "log":
                    self._log(dado)
                elif tipo == "progress":
                    try:
                        self.progress["value"] = float(dado)
                    except (ValueError, TypeError):
                        pass
                elif tipo == "done":
                    self.progress["value"] = 100
                    self._log(f"✅ Pronto! '{dado}' salvo em MP3.")
                    messagebox.showinfo("Concluído", f"MP3 salvo com sucesso!\n\n{dado}")
                    self._resetar()
                elif tipo == "error":
                    self._log(f"❌ Erro: {dado}")
                    messagebox.showerror("Erro", dado)
                    self._resetar()
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _resetar(self):
        self.baixando = False
        self.btn.configure(state="normal", text="Baixar MP3")


if __name__ == "__main__":
    App().mainloop()
