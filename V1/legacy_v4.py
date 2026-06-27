"""
legacy_v4.py
============
VERSÃO PRESERVADA -- seu classificador V4 (inércia temporal) + comparar_metodos.

Mantida SEPARADA e com a lógica intocada, a seu pedido, para registro histórico
e comparação. Só foram adicionados os imports que faltavam no snippet original
(time, matplotlib) para que o arquivo rode sozinho. A função classificar_segmento_v4
está exatamente como você enviou (cobre apenas tríades maior/menor; os demais
tipos seguem comentados como no original).

Use este módulo como BASELINE no bench (via adaptador em bench.py) para medir
o ganho do classificador por cosseno.
"""

import time
import numpy as np
import scipy.ndimage
import librosa
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


# ==========================================
# 1. CLASSIFICADOR V4 (INÉRCIA TEMPORAL) -- INTOCADO
# ==========================================
def classificar_segmento_v4(chroma_segmento, acorde_anterior=""):
    # 1. Gate e Normalização
    if np.sum(chroma_segmento) < 0.1: return ""
    chroma_norm = chroma_segmento / (np.max(chroma_segmento) + 1e-6)

    notas_nomes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    # 2. Definição de Templates (Mantendo a rigo do V3)
    tipos_acordes = {
        '':     {'idx': [0, 4, 7],     'bias': 0.15, 'required': None},
        'm':    {'idx': [0, 3, 7],     'bias': 0.15, 'required': None},
       # 'sus2': {'idx': [0, 2, 7],     'bias': -0.1, 'required': 2},
       # 'sus4': {'idx': [0, 5, 7],     'bias': -0.1, 'required': 5},
       # '7':    {'idx': [0, 4, 7, 10], 'bias': -0.2, 'required': 10},
    }

    melhor_score = -float('inf')
    acorde_vencedor = "N/A"

    for i, root in enumerate(notas_nomes):
        for sufixo, dados in tipos_acordes.items():
            nome_atual = f"{root}{sufixo}"

            intervalos = dados['idx']
            bias = dados['bias']
            required_interval = dados['required']

            indices_reais = [(i + interval) % 12 for interval in intervalos]

            if required_interval is not None:
                idx_critico = (i + required_interval) % 12
                if chroma_norm[idx_critico] < 0.25:
                    continue

            energia_util = np.sum(chroma_norm[indices_reais])
            mask = np.ones(12, dtype=bool)
            mask[indices_reais] = False
            energia_ruido = np.sum(chroma_norm[mask])

            score = energia_util - (0.6 * energia_ruido) + bias

            # INÉRCIA TEMPORAL (Context Score)
            if nome_atual == acorde_anterior:
                score += 0.5

            if acorde_anterior and len(acorde_anterior) < len(nome_atual):
                 score -= 0.1

            if score > melhor_score:
                melhor_score = score
                acorde_vencedor = nome_atual

    return acorde_vencedor


# ==========================================
# 2. ALGORITMOS DE SEGMENTAÇÃO (versão CQT) -- INTOCADO
# ==========================================
def run_beat_tracking(y, sr, y_harmonic, y_percussive):
    tempo, beats = librosa.beat.beat_track(y=y_percussive, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, bins_per_octave=36)
    beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    tempos = librosa.frames_to_time(beats, sr=sr)
    segmentos = []
    acorde_anterior = ""
    for i in range(chroma_sync.shape[1]):
        acorde = classificar_segmento_v4(chroma_sync[:, i], acorde_anterior)
        segmentos.append({'start': tempos[i], 'end': tempos[i + 1], 'label': acorde})
        acorde_anterior = acorde
    return segmentos, tempo


def run_onset_detection(y, sr, y_harmonic, y_percussive):
    onsets = librosa.onset.onset_detect(y=y_percussive, sr=sr, backtrack=True,
                                         wait=10, units='frames')
    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, bins_per_octave=36)
    onsets = librosa.util.fix_frames(onsets, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, onsets, aggregate=np.median)
    tempos = librosa.frames_to_time(onsets, sr=sr)
    segmentos = []
    acorde_anterior = ""
    for i in range(chroma_sync.shape[1]):
        acorde = classificar_segmento_v4(chroma_sync[:, i], acorde_anterior)
        segmentos.append({'start': tempos[i], 'end': tempos[i + 1], 'label': acorde})
        acorde_anterior = acorde
    return segmentos


def run_agglomerative(y, sr, y_harmonic):
    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, bins_per_octave=36)
    chroma_stack = librosa.feature.stack_memory(chroma, n_steps=3)
    duracao = librosa.get_duration(y=y, sr=sr)
    k = max(2, int(duracao / 1.5))
    bounds = librosa.segment.agglomerative(chroma_stack, k)
    bounds = librosa.util.fix_frames(bounds, x_max=chroma.shape[1])
    tempos = librosa.frames_to_time(bounds, sr=sr)
    segmentos = []
    acorde_anterior = ""
    for i in range(len(bounds) - 1):
        bloco = np.mean(chroma[:, bounds[i]:bounds[i + 1]], axis=1)
        acorde = classificar_segmento_v4(bloco, acorde_anterior)
        segmentos.append({'start': tempos[i], 'end': tempos[i + 1], 'label': acorde})
        acorde_anterior = acorde
    return segmentos


# ==========================================
# 3. COMPARAÇÃO VISUAL (GANTT) -- INTOCADO
# ==========================================
def comparar_metodos(audio_path):
    print(f"--- Comparando algoritmos (V4 - Stateful) para: {audio_path.split('/')[-1]} ---")
    y, sr = librosa.load(audio_path)
    y_harmonic, y_percussive = librosa.effects.hpss(y, margin=3.0)

    resultados = {}
    times = {}

    start = time.time()
    resultados['Beat'], _ = run_beat_tracking(y, sr, y_harmonic, y_percussive)
    times['Beat'] = time.time() - start

    start = time.time()
    resultados['Onset'] = run_onset_detection(y, sr, y_harmonic, y_percussive)
    times['Onset'] = time.time() - start

    start = time.time()
    resultados['Agglom'] = run_agglomerative(y, sr, y_harmonic)
    times['Agglom'] = time.time() - start

    fig, ax = plt.subplots(figsize=(15, 6))
    cores_base = plt.cm.tab20.colors
    mapa_cores = {}
    y_positions = {'Beat': 3, 'Onset': 2, 'Agglom': 1}
    height = 0.6
    idx_cor = 0

    print(f"\n{'MÉTODO':<15} | {'TEMPO(s)':<10} | {'SEGMENTOS':<10}")
    print("-" * 40)

    for metodo, segments in resultados.items():
        print(f"{metodo:<15} | {times[metodo]:.4f}     | {len(segments)}")
        merged = []
        if segments:
            curr = segments[0].copy()
            for next_seg in segments[1:]:
                if next_seg['label'] == curr['label']:
                    curr['end'] = next_seg['end']
                else:
                    merged.append(curr)
                    curr = next_seg.copy()
            merged.append(curr)

        for seg in merged:
            label = seg['label']
            if label not in mapa_cores:
                mapa_cores[label] = cores_base[idx_cor % len(cores_base)]
                idx_cor += 1
            start_t = seg['start']
            duration = seg['end'] - start_t
            rect = mpatches.Rectangle((start_t, y_positions[metodo] - height / 2),
                                      duration, height,
                                      color=mapa_cores[label], ec='white')
            ax.add_patch(rect)
            if duration > 0.5:
                ax.text(start_t + duration / 2, y_positions[metodo], label,
                        ha='center', va='center', color='white',
                        fontweight='bold', fontsize=9)

    ax.set_yticks([1, 2, 3])
    ax.set_yticklabels(['Agglomerative', 'Onset', 'Beat Tracking'])
    ax.set_ylim(0, 4)
    ax.set_xlim(0, librosa.get_duration(y=y, sr=sr))
    ax.set_xlabel("Tempo (segundos)")
    ax.set_title("Comparação: V4 com Inércia Temporal")
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # Ajuste o caminho para um arquivo seu:
    # comparar_metodos('/content/drive/MyDrive/MusicaFFT/Tempo_Perdido.mp3')
    print("legacy_v4.py carregado. Chame comparar_metodos('seu_arquivo.mp3').")
