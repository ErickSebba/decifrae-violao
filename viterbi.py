"""
viterbi.py
==========
Suavização temporal por Viterbi (HMM) sobre as emissões de cosseno.

Substitui de vez a inércia manual (+0.5) do V4. Em vez de olhar só um passo
atrás, o Viterbi acha a sequência globalmente mais provável, equilibrando o
encaixe de cada quadro (emissão) contra a suavidade das transições.

Como funciona aqui:
  - emissão : para cada segmento, o vetor de cosseno do classificador vira uma
    distribuição de probabilidade por softmax (temperatura controla o "quão
    decidido" o quadro é).
  - estado N (sem acorde): coluna extra com uma probabilidade-base. Quando
    nenhum acorde casa bem (ruído, mix densa ambígua), N vence naturalmente --
    sem precisar do gate fixo de 0.72 que cegava o Tempo_Perdido.
  - transição : auto-transição alta (acordes persistem), resto uniforme.
  - decodificação : Viterbi em log-espaço, próprio (sem depender de versão do
    librosa).

Parâmetros que importam:
  - change_penalty : custo (em log) de TROCAR de acorde entre segmentos vizinhos
    (1.5-4). Maior = mais suave/grudento. É INDEPENDENTE do tamanho do
    vocabulário (não dividido por n_estados), por isso funciona igual com 24 ou
    156 acordes -- foi exatamente o que quebrava com matriz estocástica normal.
  - temp        : temperatura do softmax (0.05-0.2). Menor = emissão mais decidida.
  - n_logprob   : log-prob base do estado N. Menos negativo = N aparece mais
    fácil (bom p/ pegar pausas); mais negativo = N só em silêncio real.
"""

import numpy as np

NO_CHORD = 'N'


def _softmax(x, temp):
    z = (x - np.max(x)) / max(temp, 1e-6)
    e = np.exp(z)
    return e / (np.sum(e) + 1e-12)


def decode(emissions, names, change_penalty=2.0, temp=0.1,
           n_logprob=-2.5, force_n=None):
    """
    Decodifica a sequência de acordes mais provável (Viterbi em log-espaço).

    Transição: ficar no mesmo estado custa 0; trocar custa -change_penalty
    (fixo, independente do nº de acordes). Isso evita o "acorde preso" que
    acontece quando a penalidade de troca é diluída por todo o vocabulário.

    Parameters
    ----------
    emissions : np.ndarray (n_frames, n_chords)
        Cosseno de cada acorde por quadro (de classifier.emission()).
    names : list[str]
    change_penalty : float   custo de log p/ trocar de acorde (suavidade)
    temp : float             temperatura do softmax das emissões
    n_logprob : float        log-prob base do estado N (sem acorde)
    force_n : np.ndarray (n_frames,) bool | None
        Quadros forçados a N (ex.: RMS abaixo do gate -> silêncio real).

    Returns
    -------
    list[str]  rótulo por quadro (inclui 'N').
    """
    emissions = np.asarray(emissions, dtype=float)
    n_frames, n_chords = emissions.shape
    n_states = n_chords + 1            # +1 = estado N
    n_idx = n_chords
    state_names = list(names) + [NO_CHORD]

    # --- emissões em log-prob, por quadro ---
    log_em = np.full((n_frames, n_states), -50.0)
    for t in range(n_frames):
        probs = _softmax(emissions[t], temp)
        log_em[t, :n_chords] = np.log(probs + 1e-12)
        log_em[t, n_idx] = n_logprob
        if force_n is not None and force_n[t]:
            log_em[t, :] = -50.0
            log_em[t, n_idx] = 0.0

    # --- transição: 0 p/ manter, -change_penalty p/ trocar (fixo) ---
    log_T = np.full((n_states, n_states), -change_penalty)
    np.fill_diagonal(log_T, 0.0)

    # --- Viterbi (log-espaço) ---
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


if __name__ == "__main__":
    names = ['C', 'Cmaj7', 'G']
    em = np.array([
        [0.95, 0.93, 0.20],
        [0.93, 0.95, 0.20],
        [0.96, 0.92, 0.20],
        [0.20, 0.20, 0.95],
        [0.20, 0.20, 0.96],
    ])
    print("sem viterbi (argmax):",
          [names[int(np.argmax(r))] for r in em])
    print("com viterbi:        ",
          decode(em, names, change_penalty=2.0, temp=0.08))
