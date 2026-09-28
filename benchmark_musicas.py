"""
benchmark_musicas.py
====================
Benchmark em ÁUDIO REAL: V4 vs atual, pontuado com mir_eval em vários níveis
(root, majmin, sevenths, mirex). Foco em Tempo Perdido e Boate Azul.

Os níveis 'root' e 'majmin' comparam só a TÔNICA / acorde principal (ignoram a
7ª), então são justos com o V4 (que não emite acordes com 7ª). O nível
'sevenths' mostra o que se ganha ao reconhecer as 7ªs.

GROUND TRUTH:
  - Tempo Perdido: C Am Bm Em em loop (cifra conhecida).
  - Boate Azul (Am): cifra do verso (Am G F E7 Dm Am ...) + refrão modulado
    para Lá maior (E D A ...). Timing aproximado, anotado sobre a estrutura da
    faixa. A comparação V4-vs-atual é justa: ambos pontuam contra o MESMO GT.

Saída: out/musicas_bench/comparativo.png + tabela no terminal + metrics.json
"""

import os
import sys
import json
import warnings
warnings.filterwarnings("ignore")

# Console do Windows costuma vir em cp1252 e quebra ao imprimir 'Δ', 'á' etc.
# Força UTF-8 na saída quando possível (no-op em terminais que já são UTF-8).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import librosa

from chord_templates import build_templates, MEDIUM
from classifier import CosineChordClassifier, chroma_vector, NO_CHORD
from config import PRE_CHROMA, POST_CHROMA
from legacy_v4 import classificar_segmento_v4, run_beat_tracking
from pipeline import analyze_track
from evaluate import score_segments

OUT = os.path.join(os.path.dirname(__file__), "out", "musicas_bench")
os.makedirs(OUT, exist_ok=True)
MUS = os.path.join(os.path.dirname(__file__), "Musicas")

# Hiperparâmetros: fonte única em config.py.
PRE = PRE_CHROMA
POST = POST_CHROMA
SR = PRE.sr

_cos = CosineChordClassifier(templates=build_templates(MEDIUM),
                             complexity_penalty=POST.complexity_penalty,
                             ext_sharpness=POST.ext_sharpness)


# ==========================================================================
# GROUND TRUTH
# ==========================================================================
# Tempo Perdido — C Am Bm Em em loop (intro instrumental = N).
GT_TEMPO = [
    (0.0, 6.0, 'N'),
    (6.0, 10.5, 'C'), (10.5, 13.1, 'Am'), (13.1, 16.5, 'Bm'), (16.5, 19.9, 'Em'),
    (19.9, 23.7, 'C'), (23.7, 26.3, 'Am'), (26.3, 30.0, 'Bm'), (30.0, 33.2, 'Em'),
    (33.2, 37.4, 'C'), (37.4, 39.9, 'Am'), (39.9, 43.6, 'Bm'), (43.6, 46.7, 'Em'),
]

# Boate Azul — cifra em Am. Verso: Am G F E7 Dm Am E7 Am A7 (com variações);
# refrão modula para Lá maior: E D A. Timing aproximado.
GT_BOATE = [
    (0.0, 9.4, 'N'),
    # --- verso 1 ---
    (9.4, 11.5, 'G'), (11.5, 13.1, 'C'), (13.1, 15.3, 'Am'), (15.3, 16.4, 'Dm'),
    (16.4, 18.2, 'E7'), (18.2, 20.4, 'Am'), (20.4, 21.5, 'A7'), (21.5, 23.3, 'Dm'),
    (23.3, 24.9, 'G'), (24.9, 26.6, 'C'), (26.6, 28.9, 'Am'), (28.9, 30.0, 'Dm'),
    (30.0, 31.7, 'E7'), (31.7, 38.5, 'Am'), (38.5, 41.9, 'G'), (41.9, 45.3, 'F'),
    (45.3, 49.3, 'E7'), (49.3, 52.7, 'Dm'), (52.7, 56.1, 'Am'), (56.1, 58.9, 'E7'),
    (58.9, 61.2, 'Am'), (61.2, 62.3, 'A7'), (62.3, 66.3, 'Dm'), (66.3, 69.1, 'Am'),
    (69.1, 72.5, 'E7'), (72.5, 74.7, 'Am'), (74.7, 75.9, 'A7'), (75.9, 79.9, 'Dm'),
    (79.9, 82.7, 'Am'), (82.7, 84.4, 'F'), (84.4, 86.0, 'E7'),
    # --- refrão 1 (Lá maior) ---
    (86.0, 89.8, 'A'), (89.8, 91.5, 'E'), (91.5, 93.2, 'D'), (93.2, 96.6, 'A'),
    (96.6, 100.0, 'E'), (100.0, 103.2, 'A'), (103.2, 104.8, 'E'), (104.8, 107.0, 'D'),
    (107.0, 109.8, 'A'), (109.8, 111.5, 'E'), (111.5, 113.2, 'D'), (113.2, 118.4, 'A'),
    # --- verso 2 ---
    (118.4, 120.1, 'G'), (120.1, 121.8, 'C'), (121.8, 124.1, 'Am'), (124.1, 125.2, 'Dm'),
    (125.2, 126.9, 'E7'), (126.9, 129.7, 'Am'), (129.7, 134.1, 'Dm'), (134.1, 137.0, 'Am'),
    (137.0, 140.4, 'E7'), (140.4, 142.7, 'Am'), (142.7, 144.4, 'A7'), (144.4, 147.8, 'Dm'),
    (147.8, 151.1, 'Am'), (151.1, 152.3, 'F'), (152.3, 154.4, 'E7'),
    # --- refrão 2 + final ---
    (154.4, 157.7, 'A'), (157.7, 158.8, 'E'), (158.8, 161.7, 'D'), (161.7, 164.5, 'A'),
    (164.5, 166.1, 'E'), (166.1, 167.9, 'D'), (167.9, 171.3, 'A'), (171.3, 172.9, 'E'),
    (172.9, 174.6, 'D'), (174.6, 178.1, 'A'), (178.1, 181.5, 'E'), (181.5, 193.7, 'A'),
]

GROUND_TRUTH = {
    "Tempo_Perdido": GT_TEMPO,
    "Boate_azul__Am__2": GT_BOATE,
}

# Nome real do arquivo em Musicas/ quando difere da chave acima (espaços,
# parênteses). Chaves ausentes caem no padrão "<chave>.mp3".
AUDIO_FILES = {
    "Boate_azul__Am__2": "Boate azul (Am) 2.mp3",
}

LEVELS = ['root', 'majmin', 'sevenths', 'mirex']


# ==========================================================================
# Runners
# ==========================================================================
def run_v4(y, sr):
    y_h, y_p = librosa.effects.hpss(y, margin=3.0)
    segs, _ = run_beat_tracking(y, sr, y_h, y_p)
    out = []
    for s in segs:
        lab = s['label'] if s['label'] not in ('', 'N/A') else 'N'
        out.append((s['start'], s['end'], lab))
    return out


def run_atual(y, sr):
    # Todos os parâmetros vêm de config.py e são passados explicitamente.
    # Antes, 'method', 'temp', 'n_logprob' e 'abs_floor' eram omitidos e caíam
    # nos defaults de analyze_track; os valores são os mesmos, mas agora mudar
    # config.py muda o benchmark (era o furo apontado em HIPERPARAMETROS.md §3).
    segs = analyze_track(y, sr, _cos,
                         method=PRE.method,
                         use_viterbi=POST.use_viterbi,
                         change_penalty=POST.change_penalty,
                         temp=POST.temp,
                         n_logprob=POST.n_logprob,
                         rel_gate=POST.rel_gate,
                         abs_floor=POST.abs_floor,
                         min_dur=POST.min_dur)
    return [(s['start'], s['end'], s['label']) for s in segs]


# ==========================================================================
def main():
    print("=" * 68)
    print("BENCHMARK EM ÁUDIO REAL — V4 vs ATUAL (mir_eval)")
    print("=" * 68)

    resultados = {}
    for name, gt in GROUND_TRUTH.items():
        path = os.path.join(MUS, AUDIO_FILES.get(name, name + ".mp3"))
        if not os.path.exists(path):
            print(f"  (faltando: {name}.mp3)")
            continue
        y, sr = librosa.load(path, sr=SR, mono=True)

        est_v4 = run_v4(y, sr)
        est_at = run_atual(y, sr)

        sc_v4 = score_segments(est_v4, gt, levels=LEVELS)
        sc_at = score_segments(est_at, gt, levels=LEVELS)
        resultados[name] = {"v4": sc_v4, "atual": sc_at}

        print(f"\n--- {name} ---")
        print(f"{'nível':<10} | {'V4':>8} | {'Atual':>8} | {'Δ':>7}")
        print("-" * 42)
        for lvl in LEVELS:
            d = (sc_at[lvl] - sc_v4[lvl]) * 100
            print(f"{lvl:<10} | {sc_v4[lvl]*100:7.1f}% | {sc_at[lvl]*100:7.1f}% | {d:+6.1f}")

    # ---- figura comparativa ----
    songs = list(resultados.keys())
    fig, axs = plt.subplots(1, len(songs), figsize=(7 * len(songs), 5), squeeze=False)
    for ax, name in zip(axs[0], songs):
        x = np.arange(len(LEVELS)); w = 0.38
        v4 = [resultados[name]['v4'][l] * 100 for l in LEVELS]
        at = [resultados[name]['atual'][l] * 100 for l in LEVELS]
        ax.bar(x - w/2, v4, w, label='V4', color='#e76f51')
        ax.bar(x + w/2, at, w, label='Atual', color='#2a9d8f')
        ax.set_xticks(x); ax.set_xticklabels(LEVELS)
        ax.set_ylim(0, 105); ax.set_ylabel("Acurácia (%)")
        ax.set_title(name.replace('_', ' '))
        ax.legend()
        for i, (a, b) in enumerate(zip(v4, at)):
            ax.text(i - w/2, a + 1, f"{a:.0f}", ha='center', fontsize=8)
            ax.text(i + w/2, b + 1, f"{b:.0f}", ha='center', fontsize=8)
    fig.suptitle("V4 vs Atual em áudio real — root/majmin ignoram a 7ª (justo p/ V4)",
                 fontsize=12)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, "comparativo.png"), dpi=120)
    plt.close(fig)

    with open(os.path.join(OUT, "metrics.json"), "w") as fp:
        json.dump(resultados, fp, indent=2, ensure_ascii=False)

    print(f"\nArquivos em: {OUT}")
    for f in sorted(os.listdir(OUT)):
        print("  out/musicas_bench/" + f)


if __name__ == "__main__":
    main()
