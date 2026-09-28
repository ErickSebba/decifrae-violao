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

O pipeline está partido em DUAS etapas, pela fronteira que os experimentos do
artigo precisam (ver CLAUDE.md, "Hiperparâmetros: pré-chroma e pós-chroma"):

  extract_features : etapa CARA (HPSS, beat track, CQT, mediana, sync). Depende
                     só de PreChromaConfig. O resultado é cacheável em disco.
  decode           : etapa BARATA (gate de silêncio, emissão, Viterbi, merge,
                     absorção). Depende só de PostChromaConfig e do
                     classificador. Uma busca varre estes parâmetros reusando o
                     mesmo Features, sem recalcular o chroma.

Funções:
  - extract_features : áudio -> Features (chroma sync, bordas, RMS por segmento)
  - decode           : Features + classificador -> segmentos
  - analyze_track    : composição das duas, com a assinatura de sempre
  - beat_sync_chroma : forma antiga da etapa cara, mantida por compatibilidade
"""

from dataclasses import dataclass

import numpy as np
import scipy.ndimage
import librosa

from chord_templates import NO_CHORD
from config import PreChromaConfig, PostChromaConfig
import viterbi as vit

# Defaults das assinaturas antigas, lidos da configuração para não duplicar
# literais. São avaliados uma vez, no import (as dataclasses são frozen).
_PRE_DEFAULT = PreChromaConfig()
_POST_DEFAULT = PostChromaConfig()


@dataclass(eq=False)
class Features:
    """
    Saída da etapa cara. É tudo que o `decode` precisa do áudio -- depois
    daqui, nem o waveform nem o `sr` são consultados.

    chroma     : (12, n_seg)    chroma agregado por batida
    beat_times : (n_seg+1,)     bordas temporais dos segmentos, em segundos
    seg_rms    : (n_seg,)       RMS do áudio ORIGINAL em cada segmento

    `eq=False` porque comparar dataclasses de arrays com `==` levantaria
    ambiguidade do numpy; compare campo a campo com np.array_equal.
    """

    chroma: np.ndarray
    beat_times: np.ndarray
    seg_rms: np.ndarray

    @property
    def n_seg(self):
        return self.chroma.shape[1]

    def save(self, path):
        """Serializa em .npz. numpy acrescenta '.npz' se o path não tiver."""
        np.savez(path, chroma=self.chroma, beat_times=self.beat_times,
                 seg_rms=self.seg_rms)
        return path

    @classmethod
    def load(cls, path):
        """Lê de volta um .npz escrito por save(). Round-trip exato."""
        with np.load(path) as data:
            return cls(chroma=data['chroma'], beat_times=data['beat_times'],
                       seg_rms=data['seg_rms'])


def _beat_sync_chroma(y, sr, pre):
    """
    Miolo da etapa cara. Extrai chroma do áudio inteiro e sincroniza por
    batida, usando os parâmetros de `pre` (PreChromaConfig).

    `pre.sr` NÃO é consultado aqui: a taxa vem do argumento `sr`, que é a do
    áudio já carregado. `pre.sr` é o que os entry points passam ao
    `librosa.load`.

    Retorna
    -------
    chroma_sync : (12, n_beats)   chroma agregado por batida
    beat_times  : (n_beats+1,)    bordas temporais dos segmentos
    y_harmonic  : componente harmônico
    """
    y_harmonic, y_perc = librosa.effects.hpss(y, margin=pre.hpss_margin)

    tempo, beats = librosa.beat.beat_track(y=y_perc, sr=sr)

    if pre.method == 'cens':
        chroma = librosa.feature.chroma_cens(y=y_harmonic, sr=sr)
    elif pre.method == 'stft':
        chroma = librosa.feature.chroma_stft(y=y_harmonic, sr=sr)
    else:
        chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr,
                                             bins_per_octave=pre.bins_per_octave)
    if pre.smooth and pre.smooth > 1:
        chroma = scipy.ndimage.median_filter(chroma, size=(1, pre.smooth))

    beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    beat_times = librosa.frames_to_time(beats, sr=sr)
    return chroma_sync, beat_times, y_harmonic


def beat_sync_chroma(y, sr, method=_PRE_DEFAULT.method,
                     smooth=_PRE_DEFAULT.smooth,
                     margin=_PRE_DEFAULT.hpss_margin):
    """
    Forma antiga da etapa cara, mantida para quem já a chamava. Devolve a
    mesma tupla de sempre. Código novo deve preferir `extract_features`.
    """
    pre = PreChromaConfig(method=method, smooth=smooth, hpss_margin=margin)
    return _beat_sync_chroma(y, sr, pre)


def extract_features(y, sr, pre=_PRE_DEFAULT):
    """
    Etapa CARA: áudio -> Features. HPSS, beat track, CQT, filtro de mediana,
    sincronização por batida e o RMS de cada segmento.

    Não toca em nenhum parâmetro pós-chroma e não conhece o classificador: o
    resultado depende só de (y, sr, pre), e por isso pode ser cacheado em
    disco com Features.save().
    """
    chroma_sync, beat_times, _ = _beat_sync_chroma(y, sr, pre)

    # RMS por segmento, medido no áudio ORIGINAL (não no harmônico).
    n_seg = chroma_sync.shape[1]
    seg_rms = np.zeros(n_seg)
    for i in range(n_seg):
        t0 = beat_times[i]
        t1 = beat_times[i + 1] if i + 1 < len(beat_times) else t0
        seg_rms[i] = _segment_rms(y, sr, t0, t1)

    return Features(chroma=chroma_sync, beat_times=beat_times, seg_rms=seg_rms)


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


def decode(features, classifier, post=_POST_DEFAULT):
    """
    Etapa BARATA: Features + classificador -> segmentos. Gate relativo de
    silêncio, matriz de emissão, Viterbi, merge de vizinhos iguais e absorção
    de segmentos curtos.

    ATENÇÃO — `post.complexity_penalty` e `post.ext_sharpness` NÃO são lidos
    aqui: eles configuram o CLASSIFICADOR, que chega pronto. Quem quiser variar
    esses dois precisa construir outro CosineChordClassifier. Os outros sete
    campos de PostChromaConfig são usados nesta função.

    classifier : CosineChordClassifier (usa .emission() e .names)
    post.use_viterbi : True -> suaviza com Viterbi; False -> argmax por segmento
    post.rel_gate    : fração da RMS mediana da faixa abaixo da qual um segmento
                       é silêncio. É RELATIVO ao nível da própria gravação --
                       gravações baixas (ex.: Tempo_Perdido, RMS ~0.01) não são
                       tratadas como silêncio.
    post.abs_floor   : piso absoluto p/ silêncio digital real (faixas vazias).

    Retorna lista de {'start','end','label'} já mesclada.
    """
    chroma_sync = features.chroma
    beat_times = features.beat_times
    seg_rms = features.seg_rms
    n_seg = chroma_sync.shape[1]
    if n_seg == 0:
        return []

    # gate RELATIVO ao nível da faixa
    abs_floor = post.abs_floor
    median_rms = float(np.median(seg_rms[seg_rms > abs_floor])) if np.any(seg_rms > abs_floor) else 0.0
    gate = max(abs_floor, post.rel_gate * median_rms)

    # emissões + máscara de silêncio
    emissions = np.zeros((n_seg, len(classifier.names)))
    force_n = np.zeros(n_seg, dtype=bool)
    for i in range(n_seg):
        emissions[i] = classifier.emission(chroma_sync[:, i])
        if seg_rms[i] < gate:
            force_n[i] = True

    if post.use_viterbi:
        labels = vit.decode(emissions, classifier.names,
                            change_penalty=post.change_penalty, temp=post.temp,
                            n_logprob=post.n_logprob, force_n=force_n)
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
    return _absorb_short(_merge(segments), post.min_dur)


def analyze_track(y, sr, classifier, method='cqt',
                  use_viterbi=True, change_penalty=2.0, temp=0.1,
                  n_logprob=-2.5, rel_gate=0.2, abs_floor=5e-4, min_dur=0.8):
    """
    Analisa uma faixa inteira e devolve a lista de segmentos de acorde.

    Composição de extract_features + decode, com a assinatura de sempre. Os
    parâmetros pré-chroma que não estão na assinatura (`smooth`, `hpss_margin`,
    `bins_per_octave`) vêm dos defaults de PreChromaConfig, que são os mesmos
    literais de antes (21, 3.0, 36). `sr` é o do áudio recebido; `pre.sr` não é
    consultado nesta rota.

    Retorna lista de {'start','end','label'} já mesclada.
    """
    pre = PreChromaConfig(method=method)
    post = PostChromaConfig(use_viterbi=use_viterbi,
                            change_penalty=change_penalty, temp=temp,
                            n_logprob=n_logprob, rel_gate=rel_gate,
                            abs_floor=abs_floor, min_dur=min_dur)
    return decode(extract_features(y, sr, pre), classifier, post)


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    from classifier import CosineChordClassifier
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
