import librosa
import numpy as np
import scipy.ndimage

# ==============================================================================
# DETECÇÃO DE ACORDES — pipeline cosseno + Viterbi (beat-sync)
# ------------------------------------------------------------------------------
# Substitui o classificador V4 (energia + inércia +0.5) por:
#   - chroma sincronizado por batida (extraído UMA vez na faixa inteira);
#   - classificação por SIMILARIDADE DE COSSENO contra templates binários
#     (escala p/ tétrades sem bias manual);
#   - viés pró-tríade ADAPTATIVO (só penaliza a 7ª quando ela está ausente);
#   - suavização temporal por VITERBI (substitui a inércia +0.5);
#   - gate de silêncio RELATIVO ao nível da faixa (grava baixa != silêncio).
#
# CONTRATO DE SAÍDA (NÃO ALTERAR — consumido pelo front):
#   {
#     "chords":     ["C", "Am", ...],
#     "timestamps": [{"start": float, "end": float, "chord": str}, ...]
#   }
# Segmentos sem acorde são OMITIDOS (como no código antigo, que pulava vazios).
# ==============================================================================

SR = 22050              # taxa de amostragem. 11025 é ~2x mais rápido, porém
                        # menos preciso. Ver nota no README/handoff.
METHOD = "cqt"          # 'cqt' | 'cens' | 'stft'
SMOOTH = 21             # janela do median filter temporal no chroma

# --- parâmetros do classificador / Viterbi (calibrados em áudio real) ---
COMPLEXITY_PENALTY = 0.06   # viés pró-tríade adaptativo (0 desliga)
EXT_SHARPNESS = 4.0         # limiar p/ aceitar a 7ª como real
CHANGE_PENALTY = 2.0        # custo de trocar de acorde (suavidade do Viterbi)
TEMP = 0.1                  # temperatura do softmax das emissões
N_LOGPROB = -2.5            # log-prob base do estado "sem acorde"
REL_GATE = 0.2              # silêncio = RMS < 20% da mediana da faixa
ABS_FLOOR = 5e-4            # piso absoluto p/ silêncio digital
MIN_DUR = 0.6               # absorve segmentos curtos (igual ao código antigo)

NO_CHORD = "N"
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Vocabulário MEDIUM: maior, menor, 7, maj7, m7.
CHORD_TYPES = {
    '':     [0, 4, 7],
    'm':    [0, 3, 7],
    '7':    [0, 4, 7, 10],
    'maj7': [0, 4, 7, 11],
    'm7':   [0, 3, 7, 10],
}


# ==============================================================================
# CLASSIFICADOR POR COSSENO (com viés pró-tríade adaptativo)
# ==============================================================================
class _CosineClassifier:
    def __init__(self):
        names, vecs, ext_idx = [], [], []
        for suffix, intervals in CHORD_TYPES.items():
            for root in range(12):
                name = f"{NOTE_NAMES[root]}{suffix}"
                vec = np.zeros(12)
                for iv in intervals:
                    vec[(root + iv) % 12] = 1.0
                names.append(name)
                vecs.append(vec)
                exts = [iv for iv in intervals if iv >= 8]   # 6ª/7ª
                ext_idx.append((root + exts[-1]) % 12 if exts else -1)

        self.names = names
        M = np.stack(vecs)
        self.M = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
        self.ext_idx = np.array(ext_idx, dtype=int)

    def emission(self, chroma_vec):
        """Cosseno do segmento contra todos os templates, com viés adaptativo."""
        n = np.linalg.norm(chroma_vec)
        if n < 1e-9:
            return np.zeros(len(self.names))
        sims = self.M @ (chroma_vec / n)
        if COMPLEXITY_PENALTY > 0:
            cn = chroma_vec / (np.max(chroma_vec) + 1e-9)
            for k in range(len(self.names)):
                ei = self.ext_idx[k]
                if ei >= 0:
                    factor = max(0.0, 1.0 - EXT_SHARPNESS * cn[ei])
                    sims[k] -= COMPLEXITY_PENALTY * factor
        return sims


_CLF = _CosineClassifier()


# ==============================================================================
# VITERBI (suavização temporal) — substitui a inércia +0.5
# ==============================================================================
def _softmax(x, temp):
    z = (x - np.max(x)) / max(temp, 1e-6)
    e = np.exp(z)
    return e / (np.sum(e) + 1e-12)


def _viterbi_decode(emissions, names, force_n):
    n_frames, n_chords = emissions.shape
    n_states = n_chords + 1
    n_idx = n_chords
    state_names = list(names) + [NO_CHORD]

    log_em = np.full((n_frames, n_states), -50.0)
    for t in range(n_frames):
        probs = _softmax(emissions[t], TEMP)
        log_em[t, :n_chords] = np.log(probs + 1e-12)
        log_em[t, n_idx] = N_LOGPROB
        if force_n[t]:
            log_em[t, :] = -50.0
            log_em[t, n_idx] = 0.0

    log_T = np.full((n_states, n_states), -CHANGE_PENALTY)
    np.fill_diagonal(log_T, 0.0)

    delta = np.full((n_frames, n_states), -np.inf)
    psi = np.zeros((n_frames, n_states), dtype=int)
    delta[0] = log_em[0]
    for t in range(1, n_frames):
        for j in range(n_states):
            cand = delta[t - 1] + log_T[:, j]
            psi[t, j] = int(np.argmax(cand))
            delta[t, j] = np.max(cand) + log_em[t, j]

    path = np.zeros(n_frames, dtype=int)
    path[-1] = int(np.argmax(delta[-1]))
    for t in range(n_frames - 2, -1, -1):
        path[t] = psi[t + 1, path[t]]
    return [state_names[i] for i in path]


# ==============================================================================
# REFINO DE SEGMENTOS (mescla vizinhos iguais + absorve curtos)
# ==============================================================================
def refinar_beat_tracking(segmentos_brutos):
    """Mantida a função pública: mescla vizinhos de mesmo acorde e absorve
    segmentos < MIN_DUR no anterior. Mesmo comportamento do código antigo."""
    if not segmentos_brutos:
        return []

    cifra_refinada = []
    segmento_atual = segmentos_brutos[0].copy()
    for i in range(1, len(segmentos_brutos)):
        prox_seg = segmentos_brutos[i]
        if prox_seg['chord'] == segmento_atual['chord']:
            segmento_atual['end'] = prox_seg['end']
        else:
            cifra_refinada.append(segmento_atual)
            segmento_atual = prox_seg.copy()
    cifra_refinada.append(segmento_atual)

    cifra_limpa = []
    for seg in cifra_refinada:
        duracao = seg['end'] - seg['start']
        if duracao < MIN_DUR and len(cifra_limpa) > 0:
            cifra_limpa[-1]['end'] = seg['end']
        else:
            cifra_limpa.append(seg)
    return cifra_limpa


# ==============================================================================
# PROCESSAMENTO PRINCIPAL
# ==============================================================================
def detectar_acordes(audio_path) -> dict:
    y, sr = librosa.load(audio_path, sr=SR, mono=True)
    y_h, y_p = librosa.effects.hpss(y, margin=3.0)

    # --- chroma sincronizado por batida (extraído UMA vez) ---
    tempo, beats = librosa.beat.beat_track(y=y_p, sr=sr)
    if METHOD == "cens":
        chroma = librosa.feature.chroma_cens(y=y_h, sr=sr)
    elif METHOD == "stft":
        chroma = librosa.feature.chroma_stft(y=y_h, sr=sr)
    else:
        chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, bins_per_octave=36)
    if SMOOTH and SMOOTH > 1:
        chroma = scipy.ndimage.median_filter(chroma, size=(1, SMOOTH))

    beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    tempos = librosa.frames_to_time(beats, sr=sr)
    n_seg = chroma_sync.shape[1]

    if n_seg == 0:
        return {"chords": [], "timestamps": []}

    # --- RMS por segmento -> gate de silêncio RELATIVO ao nível da faixa ---
    seg_rms = np.zeros(n_seg)
    for i in range(n_seg):
        a = int(tempos[i] * sr)
        b = int(tempos[i + 1] * sr) if i + 1 < len(tempos) else a
        chunk = y[a:b]
        seg_rms[i] = np.sqrt(np.mean(chunk ** 2) + 1e-12) if len(chunk) else 0.0
    valid = seg_rms[seg_rms > ABS_FLOOR]
    median_rms = float(np.median(valid)) if valid.size else 0.0
    gate = max(ABS_FLOOR, REL_GATE * median_rms)

    # --- emissões + máscara de silêncio ---
    emissions = np.zeros((n_seg, len(_CLF.names)))
    force_n = np.zeros(n_seg, dtype=bool)
    for i in range(n_seg):
        emissions[i] = _CLF.emission(chroma_sync[:, i])
        if seg_rms[i] < gate:
            force_n[i] = True

    labels = _viterbi_decode(emissions, _CLF.names, force_n)

    # --- monta timestamps no MESMO formato do contrato; OMITE 'N' ---
    timestamps = []
    for i in range(n_seg):
        acorde = labels[i]
        if acorde in ("", NO_CHORD, "N/A"):
            continue
        start = float(round(tempos[i], 2))
        end = float(round(tempos[i + 1], 2)) if i + 1 < len(tempos) else start
        timestamps.append({"start": start, "end": end, "chord": acorde})

    timestamps_refinados = refinar_beat_tracking(timestamps)
    chords = list(dict.fromkeys(t["chord"] for t in timestamps_refinados))

    return {
        "chords": chords,
        "timestamps": timestamps_refinados,
    }
