"""
chord_templates.py
==================
Vocabulário de acordes e geração dos templates binários de 12 dimensões.

Este é o módulo BASE, compartilhado por todo o resto (síntese, classificador,
bench). A ideia central: cada acorde é descrito por um conjunto de intervalos
em semitons a partir da tônica. A partir disso geramos:

  - o template binário de 12 posições (vetor de chroma idealizado) -> usado
    pelo classificador por cosseno;
  - o conjunto de pitch-classes -> usado pelo sintetizador.

Para adicionar um acorde novo (ex.: m7b5, 9, add9...) basta acrescentar uma
linha em CHORD_TYPES. Nada mais precisa ser re-tunado -- esse é o ponto do
scoring por cosseno.
"""

import numpy as np

# Ordem canônica das 12 classes de altura (pitch classes), índice 0 = C
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Rótulo de "sem acorde" (pausa/silêncio/ruído). Vive aqui, no módulo base,
# porque é parte do vocabulário: classificador, pipeline e bench precisam dele
# sem depender uns dos outros.
NO_CHORD = 'N'

# Intervalos em semitons a partir da tônica.
# '' = maior (sufixo vazio, igual ao seu V4).
CHORD_TYPES = {
    '':     [0, 4, 7],          # maior
    'm':    [0, 3, 7],          # menor
    'dim':  [0, 3, 6],          # diminuto
    'aug':  [0, 4, 8],          # aumentado
    'sus2': [0, 2, 7],
    'sus4': [0, 5, 7],
    # --- tétrades (4 notas) ---
    '7':    [0, 4, 7, 10],      # dominante com 7
    'maj7': [0, 4, 7, 11],      # maior com 7 maior
    'm7':   [0, 3, 7, 10],      # menor com 7
    '6':    [0, 4, 7, 9],       # maior com 6
    'm6':   [0, 3, 7, 9],       # menor com 6
    'dim7': [0, 3, 6, 9],       # diminuto com 7 diminuta
    'm7b5': [0, 3, 6, 10],      # meio-diminuto
}

# Subconjuntos prontos para o bench escolher o "vocabulário ativo".
TRIADS = ['', 'm', 'dim', 'aug', 'sus2', 'sus4']
TETRADS = ['7', 'maj7', 'm7', '6', 'm6', 'dim7', 'm7b5']
BASIC = ['', 'm']                       # o que seu V4 cobre hoje
MEDIUM = ['', 'm', '7', 'maj7', 'm7']   # bom equilíbrio p/ violão


def chord_name(root_pc, suffix):
    """Nome legível do acorde, ex.: (0,'maj7') -> 'Cmaj7'."""
    return f"{NOTE_NAMES[root_pc]}{suffix}"


def chord_intervals(suffix):
    """Intervalos (semitons) de um tipo de acorde."""
    return CHORD_TYPES[suffix]


def template_vector(root_pc, suffix):
    """
    Vetor binário de 12 posições para um acorde.
    Ex.: Cmaj -> [1,0,0,0,1,0,0,1,0,0,0,0]
    """
    vec = np.zeros(12, dtype=float)
    for interval in CHORD_TYPES[suffix]:
        vec[(root_pc + interval) % 12] = 1.0
    return vec


def build_templates(suffixes=None):
    """
    Constrói o dicionário {nome_do_acorde: vetor_12} para todas as 12 tônicas
    de cada tipo de acorde selecionado.

    Parameters
    ----------
    suffixes : list[str] | None
        Quais tipos incluir. None = TODOS os de CHORD_TYPES.
        Use TRIADS, TETRADS, BASIC ou uma lista custom para controlar o teste.

    Returns
    -------
    dict[str, np.ndarray]  ex.: {'C': arr, 'Cm': arr, 'Cmaj7': arr, ...}
    """
    if suffixes is None:
        suffixes = list(CHORD_TYPES.keys())

    templates = {}
    for suffix in suffixes:
        for root_pc in range(12):
            name = chord_name(root_pc, suffix)
            templates[name] = template_vector(root_pc, suffix)
    return templates


def chord_pitch_classes(root_pc, suffix):
    """Conjunto de pitch-classes (0-11) que compõem o acorde."""
    return [(root_pc + interval) % 12 for interval in CHORD_TYPES[suffix]]


if __name__ == "__main__":
    # Sanity check rápido
    t = build_templates(BASIC)
    print(f"{len(t)} templates básicos (esperado 24).")
    print("Cmaj  :", template_vector(0, '').astype(int))
    print("C7    :", template_vector(0, '7').astype(int))
    print("Cmaj7 :", template_vector(0, 'maj7').astype(int))
