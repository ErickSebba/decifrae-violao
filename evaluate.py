"""
evaluate.py
===========
Pontuação de segmentos de acorde com mir_eval.

Recebe listas de segmentos no formato interno do projeto -- (start, end, label),
com labels como 'C', 'Am', 'Bm', 'E7', 'Dm', 'N' -- e devolve a acurácia
ponderada por tempo (mir_eval.chord) em vários níveis de exigência:

  root     : só a tônica precisa bater (ignora qualidade e 7ª).
  majmin    : tônica + maior/menor (ignora 7ª e extensões).
  sevenths  : tônica + qualidade + 7ª (aqui a 7ª passa a contar).
  mirex     : critério MIREX (>= 3 pitch-classes em comum).

A ponte essencial é traduzir o vocabulário do projeto para a notação de acorde
do mir_eval ('Am' -> 'A:min', 'E7' -> 'E:7', '' maior -> só a tônica, 'N' ->
'N'). Os intervalos são reamostrados para uma grade comum pelo próprio mir_eval
(lacunas viram 'N'), então segmentos do V4 e do pipeline atual são comparados
contra o MESMO ground truth de forma justa.
"""

import numpy as np
import mir_eval

# Sufixo do projeto (chave de CHORD_TYPES) -> qualidade na notação do mir_eval.
_QUALITY_MAP = {
    '':     'maj',
    'm':    'min',
    'dim':  'dim',
    'aug':  'aug',
    'sus2': 'sus2',
    'sus4': 'sus4',
    '7':    '7',
    'maj7': 'maj7',
    'm7':   'min7',
    '6':    'maj6',
    'm6':   'min6',
    'dim7': 'dim7',
    'm7b5': 'hdim7',
}

_NO_CHORD = {'N', '', 'N/A', None}


def _to_mireval(label):
    """Converte um label do projeto ('Am', 'E7', 'N') para notação mir_eval."""
    if label in _NO_CHORD:
        return 'N'
    # tônica: 1 ou 2 caracteres (trata o sustenido, ex.: 'C#m').
    if len(label) >= 2 and label[1] == '#':
        root, suffix = label[:2], label[2:]
    else:
        root, suffix = label[:1], label[1:]
    qual = _QUALITY_MAP.get(suffix)
    if qual is None:
        # acorde desconhecido -> 'X' (mir_eval o ignora na ponderação).
        return 'X'
    # mir_eval entende a tônica nua como acorde maior; mantém compacto.
    return root if qual == 'maj' else f"{root}:{qual}"


def _to_arrays(segments, translate=True):
    """
    Lista de (start, end, label) -> (intervals Nx2, labels mir_eval).

    translate=False mantém os rótulos como estão: usado quando a lista já vem
    em notação Harte (anotações externas), que o mir_eval entende direto.
    """
    if not segments:
        return np.zeros((0, 2), dtype=float), []
    intervals = np.array([[float(s), float(e)] for s, e, _ in segments],
                         dtype=float)
    if translate:
        labels = [_to_mireval(lab) for _, _, lab in segments]
    else:
        labels = [str(lab) for _, _, lab in segments]
    return intervals, labels


def score_segments(est, ref, levels=('root', 'majmin', 'sevenths', 'mirex'),
                   ref_is_harte=False):
    """
    Acurácia ponderada por tempo do estimado vs. referência (ground truth).

    Parameters
    ----------
    est : list[(start, end, label)]
        Segmentos estimados pelo classificador, no vocabulário do PROJETO
        ('C', 'Am', 'E7', 'N') -- sempre traduzidos para a notação mir_eval.
    ref : list[(start, end, label)]
        Segmentos de referência (ground truth).
    levels : iterable[str]
        Quais métricas do mir_eval.chord retornar.
    ref_is_harte : bool
        False (default): a referência também está no vocabulário do projeto e
        passa pela tradução -- é o caso do GT embutido em
        `benchmark_musicas.py`.
        True: a referência JÁ está em notação Harte e vai para o mir_eval sem
        tocar em `_to_mireval`. É o caso do GuitarSet e do IDMT-SMT-Chords,
        cujos rótulos ('D#:sus2(7)/1', 'C:maj/3') não existem em
        `_QUALITY_MAP` e virariam 'X' -- ou seja, seriam ignorados na
        ponderação e a métrica sairia sem sentido.

    Returns
    -------
    dict[str, float]  ex.: {'root': 0.81, 'majmin': 0.78, ...}  (0..1)
    """
    ref_int, ref_lab = _to_arrays(ref, translate=not ref_is_harte)
    est_int, est_lab = _to_arrays(est)
    scores = mir_eval.chord.evaluate(ref_int, ref_lab, est_int, est_lab)
    return {lvl: float(scores[lvl]) for lvl in levels}


if __name__ == "__main__":
    # Sanity check: estimativa perfeita -> 100% em todos os níveis.
    gt = [(0.0, 2.0, 'C'), (2.0, 4.0, 'Am'), (4.0, 6.0, 'E7'), (6.0, 8.0, 'N')]
    perfect = score_segments(gt, gt)
    print("perfeito :", {k: round(v, 3) for k, v in perfect.items()})

    # Troca a 7ª por tríade: root/majmin ficam 100%, sevenths cai.
    no_sev = [(0.0, 2.0, 'C'), (2.0, 4.0, 'Am'), (4.0, 6.0, 'E'), (6.0, 8.0, 'N')]
    partial = score_segments(no_sev, gt)
    print("sem 7a   :", {k: round(v, 3) for k, v in partial.items()})
