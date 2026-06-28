"""
pipeline.py
===========
Pipeline de análise de faixa: segmentação por beat-sync (igual ao V4) +
classificação por cosseno + suavização por Viterbi.

POR QUE BEAT-SYNC: o V4 mostrou que segmentar por batidas e agregar o chroma
por beat dá segmentos estáveis (~0.85s) e resultado limpo. Crucialmente, o
chroma é extraído UMA vez no áudio inteiro e depois sincronizado por batida --
ao contrário do musicas.py antigo, que extraía chroma de cada pedacinho de
~22ms (gerando os avisos n_fft e chroma-lixo).

Funções:
  - beat_sync_chroma : (chroma 12xN sincronizado por batida, tempos das batidas)
  - analyze_track    : amarra segmentação + emissão + Viterbi -> segmentos
"""

import numpy as np
import scipy.ndimage
import librosa

from classifier_V2 import NO_CHORD
import viterbi as vit


def beat_sync_chroma(y, sr, method='cqt', smooth=21, margin=3.0):
    """
    Extrai chroma do áudio inteiro e sincroniza por batida.

    Retorna
    -------
    chroma_sync : (12, n_beats)   chroma agregado por batida
    beat_times  : (n_beats+1,)    bordas temporais dos segmentos
    y_harmonic  : componente harmônico (reaproveitado p/ RMS por segmento)
    """
    y_harmonic, y_perc = librosa.effects.hpss(y, margin=margin)

    tempo, beats = librosa.beat.beat_track(y=y_perc, sr=sr)

    if method == 'cens':
        chroma = librosa.feature.chroma_cens(y=y_harmonic, sr=sr)
    elif method == 'stft':
        chroma = librosa.feature.chroma_stft(y=y_harmonic, sr=sr)
    else:
        chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr,
                                             bins_per_octave=36)
    if smooth and smooth > 1:
        chroma = scipy.ndimage.median_filter(chroma, size=(1, smooth))

    beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    beat_times = librosa.frames_to_time(beats, sr=sr)
    return chroma_sync, beat_times, y_harmonic


def _segment_rms(y, sr, t0, t1):
    a, b = int(t0 * sr), int(t1 * sr)
    chunk = y[a:b]
    if len(chunk) == 0:
        return 0.0
    return float(np.sqrt(np.mean(chunk ** 2) + 1e-12))


def _merge(segments):
    merged = []
    for seg in segments:
        if seg['end'] <= seg['start']:
            continue
        if merged and merged[-1]['label'] == seg['label']:
            merged[-1]['end'] = seg['end']
        else:
            merged.append(dict(seg))
    return merged


def _absorb_short(segments, min_dur):
    """
    Absorve segmentos curtos (< min_dur) no vizinho mais longo, relabelando-os.
    Remove os blips de transição (ex.: um 'C' de 0.6s entre G e A) sem mexer
    nos acordes reais. Itera até estabilizar.
    """
    if min_dur <= 0:
        return segments
    segs = [dict(s) for s in segments]
    changed = True
    while changed and len(segs) > 1:
        changed = False
        durs = [s['end'] - s['start'] for s in segs]
        # acha o menor segmento curto
        idx = min(range(len(segs)), key=lambda i: durs[i])
        if durs[idx] >= min_dur:
            break
        # escolhe o vizinho mais longo p/ herdar o rótulo
        left = segs[idx - 1] if idx > 0 else None
        right = segs[idx + 1] if idx < len(segs) - 1 else None
        if left and right:
            donor = left if (left['end'] - left['start']) >= (right['end'] - right['start']) else right
        else:
            donor = left or right
        segs[idx]['label'] = donor['label']
        segs = _merge(segs)
        changed = True
    return segs


def analyze_track(y, sr, classifier, method='cqt',
                  use_viterbi=True, change_penalty=2.0, temp=0.1,
                  n_logprob=-2.5, rel_gate=0.2, abs_floor=5e-4, min_dur=0.8):
    """
    Analisa uma faixa inteira e devolve a lista de segmentos de acorde.

    classifier : CosineChordClassifier (usa .emission() e .names)
    use_viterbi: True -> suaviza com Viterbi; False -> argmax por segmento
    change_penalty : custo de log p/ trocar de acorde (suavidade do Viterbi)
    rel_gate   : fração da RMS mediana da faixa abaixo da qual um segmento é
                 considerado silêncio. É RELATIVO ao nível da própria gravação,
                 não absoluto -- gravações baixas (ex.: Tempo_Perdido, RMS
                 ~0.01) não são tratadas como silêncio.
    abs_floor  : piso absoluto p/ silêncio digital real (pega faixas vazias).

    Retorna lista de {'start','end','label'} já mesclada.
    """
    chroma_sync, beat_times, y_h = beat_sync_chroma(y, sr, method=method)
    n_seg = chroma_sync.shape[1]
    if n_seg == 0:
        return []

    # RMS por segmento -> gate RELATIVO ao nível da faixa
    seg_rms = np.zeros(n_seg)
    for i in range(n_seg):
        t0 = beat_times[i]
        t1 = beat_times[i + 1] if i + 1 < len(beat_times) else t0
        seg_rms[i] = _segment_rms(y, sr, t0, t1)
    median_rms = float(np.median(seg_rms[seg_rms > abs_floor])) if np.any(seg_rms > abs_floor) else 0.0
    gate = max(abs_floor, rel_gate * median_rms)

    # emissões + máscara de silêncio
    emissions = np.zeros((n_seg, len(classifier.names)))
    force_n = np.zeros(n_seg, dtype=bool)
    for i in range(n_seg):
        emissions[i] = classifier.emission(chroma_sync[:, i])
        if seg_rms[i] < gate:
            force_n[i] = True

    if use_viterbi:
        labels = vit.decode(emissions, classifier.names,
                            change_penalty=change_penalty, temp=temp,
                            n_logprob=n_logprob, force_n=force_n)
    else:
        labels = []
        for i in range(n_seg):
            if force_n[i]:
                labels.append(NO_CHORD)
            else:
                labels.append(classifier.classify_vector(chroma_sync[:, i]))

    segments = []
    for i in range(n_seg):
        t0 = beat_times[i]
        t1 = beat_times[i + 1] if i + 1 < len(beat_times) else t0
        segments.append({'start': float(t0), 'end': float(t1),
                         'label': labels[i]})
    return _absorb_short(_merge(segments), min_dur)


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    from classifier_V2 import CosineChordClassifier
    from chord_templates import build_templates, MEDIUM
    from synth import synth_chord
    # monta uma "faixa" sintética: C(2s) + G(2s) + Am(2s)
    sr = 22050
    y = np.concatenate([
        synth_chord(0, '', sr=sr, dur=2.0, n_harmonics=6),
        synth_chord(7, '', sr=sr, dur=2.0, n_harmonics=6),
        synth_chord(9, 'm', sr=sr, dur=2.0, n_harmonics=6),
    ])
    clf = CosineChordClassifier(templates=build_templates(MEDIUM))
    segs = analyze_track(y, sr, clf, use_viterbi=True)
    for s in segs:
        print(f"{s['start']:.1f}-{s['end']:.1f}s | {s['label']}")
