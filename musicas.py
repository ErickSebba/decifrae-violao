"""
musicas.py
==========
Analisa os arquivos de áudio da pasta Musicas/, estima a sequência de acordes
e gera uma timeline por faixa.

VERSÃO 2 — mudanças frente à anterior:
  - Segmentação por BEAT-SYNC (igual ao V4): chroma extraído UMA vez no áudio
    inteiro e sincronizado por batida. Isso elimina os segmentos de ~22ms e os
    avisos "n_fft too large" que vinham de extrair chroma de pedacinhos.
  - Suavização por VITERBI: mata o flicker (ex.: G / Gmaj7 / Gsus2 viram um G).
  - Estado N com base ajustável: silêncio real vira N (via gate de RMS), mas
    mix densa (violão+voz) volta a receber acordes em vez de "tudo N".
  - Bug corrigido: não há mais HPSS duplicado (o pipeline faz HPSS uma vez).

Vocabulário: MEDIUM (maior, menor, 7, maj7, m7).
"""

from __future__ import annotations

from pathlib import Path

import librosa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from classifier import CosineChordClassifier, NO_CHORD
from chord_templates import build_templates, MEDIUM
from config import PRE_CHROMA, POST_CHROMA
from pipeline import analyze_track


BASE_DIR = Path(__file__).resolve().parent
MUSICAS_DIR = BASE_DIR / "Musicas"
OUT_DIR = BASE_DIR / "out" / "musicas"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Parâmetros do pipeline: ajuste fino em config.py, não aqui ---
PRE = PRE_CHROMA
POST = POST_CHROMA

# Classificador por cosseno com o vocabulário MEDIUM.
# complexity_penalty=0.06: viés pró-tríade ADAPTATIVO. A penalidade só age
# quando a nota da 6ª/7ª está FRACA no chroma -- então flicker maj7/7 de corda
# solta é suprimido, mas sétimas REAIS (E7, A7 da Boate Azul) passam intactas.
# ext_sharpness controla o limiar: maior = mais fácil aceitar a 7ª como real.
# rms_gate fica literal: é inerte com Viterbi (só classify_audio o usa) e por
# isso não entrou em PostChromaConfig.
CLF = CosineChordClassifier(templates=build_templates(MEDIUM),
                            rms_gate=0.02,
                            complexity_penalty=POST.complexity_penalty,
                            ext_sharpness=POST.ext_sharpness)


def _format_label(label: str) -> str:
	return "N" if label in ("", NO_CHORD, "N/A") else label


def analyze_audio(audio_path: Path):
	y, sr = librosa.load(audio_path, sr=PRE.sr, mono=True)
	duration = float(librosa.get_duration(y=y, sr=sr))
	segments = analyze_track(
		y, sr, CLF,
		method=PRE.method,
		use_viterbi=POST.use_viterbi,
		change_penalty=POST.change_penalty,
		temp=POST.temp,
		n_logprob=POST.n_logprob,
		rel_gate=POST.rel_gate,
		abs_floor=POST.abs_floor,
		min_dur=POST.min_dur,
	)
	return segments, sr, duration


def print_segments(audio_path: Path, segments):
	print(f"\n=== {audio_path.name} ===")
	for seg in segments:
		label = _format_label(seg["label"])
		print(f"{seg['start']:.1f}s -> {seg['end']:.1f}s | {label}")


def plot_segments(audio_path: Path, segments, duration: float):
	fig, ax = plt.subplots(figsize=(14, 2.8))
	cores = plt.cm.tab20.colors
	palette = {}
	y_pos = 0.5
	height = 0.35

	for seg in segments:
		label = _format_label(seg["label"])
		if label not in palette:
			palette[label] = cores[len(palette) % len(cores)]
		start = seg["start"]
		width = seg["end"] - seg["start"]
		rect = plt.Rectangle((start, y_pos - height / 2), width, height,
							 facecolor=palette[label], edgecolor="white")
		ax.add_patch(rect)
		if width >= 1.2:
			ax.text(start + width / 2, y_pos, label, ha="center", va="center",
					fontsize=9, color="white", fontweight="bold")

	ax.set_xlim(0, duration)
	ax.set_ylim(0, 1)
	ax.set_yticks([])
	ax.set_xlabel("Tempo (s)")
	ax.set_title(f"{audio_path.name}  (beat-sync + Viterbi)")
	ax.grid(axis="x", alpha=0.25)
	plt.tight_layout()

	out_path = OUT_DIR / f"{audio_path.stem}_timeline.png"
	plt.savefig(out_path, dpi=140)
	plt.close(fig)
	return out_path


def iter_audio_files():
	if not MUSICAS_DIR.exists():
		return []
	exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}
	return sorted(p for p in MUSICAS_DIR.iterdir() if p.suffix.lower() in exts)


def main():
	import warnings
	warnings.filterwarnings("ignore")

	audio_files = iter_audio_files()
	if not audio_files:
		print(f"Nenhum arquivo de áudio encontrado em {MUSICAS_DIR}")
		return

	for audio_path in audio_files:
		segments, _, duration = analyze_audio(audio_path)
		print_segments(audio_path, segments)
		out_path = plot_segments(audio_path, segments, duration)
		print(f"Gráfico salvo em: {out_path}")


if __name__ == "__main__":
	main()