import librosa
import numpy as np
import json
#
# ===============================
# CLASSIFICADOR COM INÉRCIA
# ===============================
def classificar_segmento(chroma, acorde_anterior=""):
    if np.sum(chroma) < 0.1:
        return ""

    chroma = chroma / (np.max(chroma) + 1e-6)
    notas = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    templates = {
        '':  [0, 4, 7],
        'm': [0, 3, 7],
    }

    melhor_score = -1e9
    melhor_acorde = ""

    for i, root in enumerate(notas):
        for sufixo, intervalos in templates.items():
            idx = [(i + x) % 12 for x in intervalos]
            energia_acorde = np.sum(chroma[idx])
            energia_ruido = np.sum(chroma) - energia_acorde

            score = energia_acorde - 0.6 * energia_ruido + 0.15

            if f"{root}{sufixo}" == acorde_anterior:
                score += 0.5

            if score > melhor_score:
                melhor_score = score
                melhor_acorde = f"{root}{sufixo}"

    return melhor_acorde


def refinar_beat_tracking(segmentos_brutos):
    if not segmentos_brutos: return []

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
    for i, seg in enumerate(cifra_refinada):
        duracao = seg['end'] - seg['start']

        if duracao < 0.6 and len(cifra_limpa) > 0:
            cifra_limpa[-1]['end'] = seg['end']
        else:
            cifra_limpa.append(seg)

    return cifra_limpa

# ===============================
# PROCESSAMENTO PRINCIPAL
# ===============================
def detectar_acordes(audio_path) -> dict:
    y, sr = librosa.load(audio_path, sr=11025, mono=True)
    y_h, y_p = librosa.effects.hpss(y, margin=3.0)

    tempo, beats = librosa.beat.beat_track(y=y_p, sr=sr)

    chroma = librosa.feature.chroma_stft(
        y=y_h,
        sr=sr,
        n_chroma=12,
        n_fft=2048
    )

    beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    tempos = librosa.frames_to_time(beats, sr=sr)

    timestamps = []
    acorde_anterior = ""

    for i in range(chroma_sync.shape[1]):
        acorde = classificar_segmento(chroma_sync[:, i], acorde_anterior)
        

        start = float(round(tempos[i], 2))
        end = float(round(tempos[i + 1], 2)) if i + 1 < len(tempos) else start

        
        if acorde:
            timestamps.append({
                "start": start,
                "end": end,
                "chord": acorde
            })
            
        acorde_anterior = acorde

    timestamps_refinados = refinar_beat_tracking(timestamps)

    chords = list(dict.fromkeys(t["chord"] for t in timestamps_refinados))

    return {
        "chords": chords,
        "timestamps": timestamps_refinados
    }
