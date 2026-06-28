"""
classifier.py
=============
Classificador de acordes por SIMILARIDADE DE COSSENO.

Substitui o scoring ad-hoc do V4 (energia_util - 0.6*energia_ruido + bias).
O cosseno é auto-normalizado pelo tamanho do template: um template de 4 notas
tem norma maior (sqrt(4)), então só "vence" se houver energia real nas 4
posições. Isso elimina o viés que fazia Cmaj virar C7 e dispensa os bias
manuais -- por isso escala para tétrades sem re-tunar nada.

Inclui DOIS gates para detectar "sem acorde" (pausas/ruído):
  1. gate de energia    : sinal fraco demais -> 'N'
  2. gate de confiança  : melhor cosseno abaixo de um limiar -> 'N'
     (ruído tem chroma achatado, casa mal com qualquer template esparso)

Também expõe extract_chroma(): a extração de feature compartilhada, para que
síntese e classificação usem exatamente o mesmo pipeline.
"""

import numpy as np
import scipy.ndimage
import librosa

from chord_templates import build_templates

NO_CHORD = 'N'


# --------------------------------------------------------------------------
# Extração de feature (pipeline compartilhado)
# --------------------------------------------------------------------------
def extract_chroma(y, sr, method='cqt', smooth=21, use_hpss=True, margin=3.0):
    """
    Extrai uma matriz de chroma (12 x n_frames).

    method : 'cqt' | 'cens' | 'stft'
    smooth : tamanho da janela do median filter temporal (0 desliga)
    use_hpss : separa harmônico/percussivo antes (recomendado)
    """
    if use_hpss:
        y_h, _ = librosa.effects.hpss(y, margin=margin)
    else:
        y_h = y

    if method == 'cqt':
        chroma = librosa.feature.chroma_cqt(y=y_h, sr=sr, bins_per_octave=36)
    elif method == 'cens':
        chroma = librosa.feature.chroma_cens(y=y_h, sr=sr)
    elif method == 'stft':
        chroma = librosa.feature.chroma_stft(y=y_h, sr=sr)
    else:
        raise ValueError(f"método de chroma desconhecido: {method}")

    if smooth and smooth > 1:
        chroma = scipy.ndimage.median_filter(chroma, size=(1, smooth))
    return chroma


def chroma_vector(y, sr, **kwargs):
    """Chroma de UM segmento curto, agregado num único vetor de 12."""
    chroma = extract_chroma(y, sr, **kwargs)
    return np.median(chroma, axis=1)


# --------------------------------------------------------------------------
# Classificador por cosseno
# --------------------------------------------------------------------------
class CosineChordClassifier:
    """
    Classificador stateless por cosseno.

    Parameters
    ----------
    templates : dict[str, np.ndarray] | None
        Vocabulário {nome: vetor_12}. None usa build_templates() completo.
    confidence_gate : float
        Cosseno mínimo do melhor acorde. Abaixo disso -> 'N' (ambíguo/ruído).
        Ruído tem chroma achatado e casa mal com templates esparsos.
    rms_gate : float
        RMS mínimo do ÁUDIO para considerar que há som. Pega as pausas, que o
        chroma_cqt sozinho não pega (ele normaliza cada frame internamente,
        então até ruído fraco gera um chroma de magnitude "cheia").
        Só se aplica em classify_audio (precisa do waveform).
    """

    def __init__(self, templates=None, confidence_gate=0.72, rms_gate=0.02,
                 complexity_penalty=0.0):
        if templates is None:
            templates = build_templates()
        self.names = list(templates.keys())
        # nº de notas de cada template (p/ o viés pró-tríade)
        note_counts = np.array([np.sum(templates[n] > 0) for n in self.names])
        # matriz (n_templates x 12) já normalizada por linha (norma L2 = 1)
        M = np.stack([templates[n] for n in self.names]).astype(float)
        norms = np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
        self.M = M / norms
        self.confidence_gate = confidence_gate
        self.rms_gate = rms_gate
        # prior: penaliza acordes de 4+ notas (tríades são mais comuns no violão;
        # evita o flicker maj7/7 quando a tríade já explica o som). 0 desliga.
        self.complexity_penalty = complexity_penalty
        self.prior = np.where(note_counts >= 4, -complexity_penalty, 0.0)

    def emission(self, chroma_vec):
        """
        Vetor de cosseno do segmento contra TODOS os templates (sem gate),
        com o viés pró-tríade somado. É a "matriz de emissão" do Viterbi.
        """
        n = np.linalg.norm(chroma_vec)
        if n < 1e-9:
            return np.zeros(len(self.names))
        return self.M @ (chroma_vec / n) + self.prior

    def classify_vector(self, chroma_vec, return_score=False):
        """
        Classifica um vetor de chroma (12,) -> nome do acorde ou 'N'.
        Aplica apenas o gate de confiança (não vê o áudio).
        """
        if np.sum(chroma_vec) < 1e-6:
            return (NO_CHORD, 0.0) if return_score else NO_CHORD

        sims = self.emission(chroma_vec)
        best = int(np.argmax(sims))
        best_score = float(sims[best])

        if best_score < self.confidence_gate:
            return (NO_CHORD, best_score) if return_score else NO_CHORD

        name = self.names[best]
        return (name, best_score) if return_score else name

    def classify_audio(self, y, sr, return_score=False, **chroma_kwargs):
        """Conveniência: áudio cru -> acorde (segmento único)."""
        # gate de RMS no áudio: pega pausas / silêncio antes de tudo
        rms = np.sqrt(np.mean(y ** 2) + 1e-12)
        if rms < self.rms_gate:
            return (NO_CHORD, 0.0) if return_score else NO_CHORD
        vec = chroma_vector(y, sr, **chroma_kwargs)
        return self.classify_vector(vec, return_score=return_score)


if __name__ == "__main__":
    from synth import synth_chord, synth_pause
    sr = 22050
    clf = CosineChordClassifier()

    for suffix in ['', 'm', '7', 'maj7', 'm7']:
        y = synth_chord(0, suffix, sr=sr, dur=1.5, n_harmonics=6)
        pred, score = clf.classify_audio(y, sr, return_score=True)
        alvo = f"C{suffix}"
        ok = "OK " if pred == alvo else "XX "
        print(f"{ok}alvo={alvo:6s} -> pred={pred:6s} (cos={score:.3f})")

    # pausa: deve dar 'N'
    p = synth_pause(sr=sr, dur=1.0, noise_level=0.01)
    pred, score = clf.classify_audio(p, sr, return_score=True)
    print(f"pausa -> pred={pred} (cos={score:.3f})  [esperado N]")
