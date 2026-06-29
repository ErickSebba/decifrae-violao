"""
audio_processing_baixo — Sistema de Transcrição de Baixo
=========================================================
Módulos integrados:
  1. Detecção de Pitch (pYIN)
  2. Posições no Braço do Baixo
  3. Menor Caminho (Programação Dinâmica)
  4. Renderização de Tablatura em ASCII
  5. Geradores de Ruído (Lee & Shen 2011)
  6. Pipeline Completo
"""

import math
import librosa
import numpy as np
import random
from numpy import arange, multiply as mult
from enum import Enum
import warnings

warnings.filterwarnings("ignore")


def _numpy_to_python(obj):
    """Converte tipos numpy para tipos Python nativos para serialização JSON."""
    if isinstance(obj, dict):
        return {k: _numpy_to_python(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_numpy_to_python(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — DETECÇÃO DE PITCH (pYIN)
# ══════════════════════════════════════════════════════════════════════════════

def analisar_baixo(audio_path: str, plotar: bool = False,
                   prob_min: float = 0.6) -> list[dict]:
    """
    Processa um arquivo de áudio e detecta as notas do baixo via pYIN.

    Parâmetros
    ----------
    audio_path : str
        Caminho para o arquivo de áudio (.mp3 ou .wav).
    plotar : bool
        Se True, exibe o gráfico duplo (espectrograma + piano roll).
    prob_min : float
        Probabilidade mínima de voicing aceita por frame (0–1).
        Frames abaixo desse limiar são descartados como silêncio.
        Padrão 0.6 elimina estimativas de baixa confiança do pYIN.

    Retorna
    -------
    list[dict]
        Lista de segmentos de nota detectados, ordenados por tempo.
    """
    # sr=44100 dobra a resolução espectral nos graves (B0–G2) vs o padrão 22050,
    # o que reduz erros de oitava e semitom no pYIN para frequências baixas.
    y, sr = librosa.load(audio_path, sr=44100)

    fmin = librosa.note_to_hz('B0')
    fmax = librosa.note_to_hz('G4')

    # Com sr=44100, frame_length=8192 mantém ~186ms de janela (igual ao original)
    # mas com resolução em frequência duas vezes maior — crucial para graves.
    frame_length = 8192
    hop_length   = 2048

    y_harmonic, _ = librosa.effects.hpss(y, margin=2.0)

    f0, voiced_flag, voiced_probs = librosa.pyin(
        y_harmonic,
        fmin=fmin,
        fmax=fmax,
        sr=sr,
        frame_length=frame_length,
        hop_length=hop_length,
    )

    # Máscara combinada: flag booleano do pYIN + limiar de probabilidade.
    # voiced_probs < prob_min descarta frames onde o pYIN hesitou, prevenindo
    # notas fantasmas entre transições e em regiões de decaimento.
    mascara_valida = voiced_flag & (voiced_probs >= prob_min)
    f0_clean = f0.copy()
    f0_clean[~mascara_valida] = np.nan

    midi_notes = librosa.hz_to_midi(f0_clean)

    # Filtro de mediana (janela de 3 frames) antes de quantizar:
    # suaviza jitter de ±1 semitom que ocorre em frames de transição,
    # evitando que oscilações rápidas abram segmentos espúrios.
    from scipy.signal import medfilt
    midi_suavizado = medfilt(
        np.where(np.isnan(midi_notes), 0.0, midi_notes).astype(np.float32),
        kernel_size=3,
    )
    # Restaura NaN nas posições que eram silêncio
    midi_suavizado = np.where(np.isnan(midi_notes), np.nan, midi_suavizado)

    midi_quantized = np.round(midi_suavizado)
    times          = librosa.times_like(f0, sr=sr, hop_length=hop_length)

    segmentos  = []
    nota_atual = None
    inicio_idx = 0

    for i, nota in enumerate(midi_quantized):
        if np.isnan(nota):
            if nota_atual is not None:
                segmentos.append({
                    "nota_midi": nota_atual,
                    "inicio":    times[inicio_idx],
                    "fim":       times[i],
                })
                nota_atual = None
        else:
            if nota_atual is None:
                nota_atual = nota
                inicio_idx = i
            elif nota != nota_atual:
                segmentos.append({
                    "nota_midi": nota_atual,
                    "inicio":    times[inicio_idx],
                    "fim":       times[i],
                })
                nota_atual = nota
                inicio_idx = i

    if nota_atual is not None:
        segmentos.append({
            "nota_midi": nota_atual,
            "inicio":    times[inicio_idx],
            "fim":       times[-1],
        })

    if plotar:
        _plotar(audio_path, y, y_harmonic, sr, fmin, fmax, hop_length,
                times, f0_clean, segmentos)

    return segmentos


def bridge_pyin_para_notas(segmentos: list[dict],
                            duracao_minima: float = 0.08) -> list[dict]:
    """
    Converte a saída do pYIN para o formato esperado pelo Módulo 2.

    duracao_minima : float
        Segmentos menores que este valor (s) são descartados.
        0.08s (80ms) é o limiar recomendado para baixo: notas legítimas
        raramente duram menos que isso, enquanto artefatos de transição
        entre notas costumam ficar abaixo desse valor.
    """
    resultado = []
    for seg in segmentos:
        duracao = seg["fim"] - seg["inicio"]
        if duracao < duracao_minima:
            continue
        nome = librosa.midi_to_note(int(seg["nota_midi"]))
        resultado.append({
            "nome":   nome,
            "inicio": seg["inicio"],
            "fim":    seg["fim"],
        })
    return resultado


def _plotar(audio_path, y, y_harmonic, sr, fmin, fmax, hop_length,
            times, f0_clean, segmentos):
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import librosa.display
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(15, 10), sharex=True,
        gridspec_kw={"height_ratios": [2, 1.5]},
    )
    fig.suptitle(
        f'Transcrição de Baixo: {audio_path.split("/")[-1]}',
        fontsize=16, fontweight="bold",
    )

    C    = np.abs(librosa.cqt(y_harmonic, sr=sr, fmin=fmin,
                               n_bins=60, bins_per_octave=12,
                               hop_length=hop_length))
    C_db = librosa.amplitude_to_db(C, ref=np.max)
    librosa.display.specshow(C_db, sr=sr, x_axis="time", y_axis="cqt_hz",
                              fmin=fmin, bins_per_octave=12,
                              hop_length=hop_length, cmap="magma",
                              alpha=0.7, ax=ax1)
    ax1.plot(times, f0_clean, label="Pitch ($f_0$) Detectado",
             color="lime", linewidth=3)
    ax1.set_title("Visão DSP: Espectrograma e Frequência Fundamental", fontsize=12)
    ax1.set_ylabel("Frequência (Hz)")
    ax1.set_ylim(fmin, fmax)
    ax1.legend(loc="upper right")

    cores      = plt.cm.tab20.colors
    mapa_cores = {}
    idx_cor    = 0
    notas_usadas = set()

    for seg in segmentos:
        nome_nota = librosa.midi_to_note(seg["nota_midi"])
        notas_usadas.add(seg["nota_midi"])
        if nome_nota not in mapa_cores:
            mapa_cores[nome_nota] = cores[idx_cor % len(cores)]
            idx_cor += 1
        start_t  = seg["inicio"]
        duration = seg["fim"] - start_t
        if duration > 0.05:
            rect = mpatches.Rectangle(
                (start_t, seg["nota_midi"] - 0.4), duration, 0.8,
                color=mapa_cores[nome_nota], ec="white", lw=1.5,
            )
            ax2.add_patch(rect)
            if duration > 0.15:
                ax2.text(start_t + duration / 2, seg["nota_midi"], nome_nota,
                         ha="center", va="center", color="black",
                         fontweight="bold", fontsize=9)

    ax2.set_title("Visão do Músico: Transcrição Quantizada (Piano Roll)", fontsize=12)
    ax2.set_ylabel("Nota (MIDI)")
    ax2.set_xlabel("Tempo (segundos)")
    if notas_usadas:
        ax2.set_ylim(min(notas_usadas) - 2, max(notas_usadas) + 2)
        yticks = np.arange(min(notas_usadas) - 1, max(notas_usadas) + 2)
        ax2.set_yticks(yticks)
        ax2.set_yticklabels([librosa.midi_to_note(int(y)) for y in yticks])
    ax2.grid(axis="x", linestyle="--", alpha=0.5)
    ax2.grid(axis="y", linestyle=":",  alpha=0.3)
    ax2.set_xlim(0, librosa.get_duration(y=y, sr=sr))

    plt.tight_layout()
    plt.show()


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 2 — POSIÇÕES NO BRAÇO DO BAIXO
# ══════════════════════════════════════════════════════════════════════════════

_MAPA_NOTAS = {
    "C": 0, "C#": 1, "C♯": 1, "Db": 1, "D": 2, "D#": 3, "D♯": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "F♯": 6, "Gb": 6, "G": 7, "G#": 8, "G♯": 8,
    "Ab": 8, "A": 9, "A#": 10, "A♯": 10, "Bb": 10, "B": 11,
}

_CORDAS_INFO = {
    20: 1,  # G2
    15: 2,  # D2
    10: 3,  # A1
    5:  4,  # E1
    0:  5,  # B0
}

_MAX_CASAS = 24

_CORDA_NOME_PARA_NUMERO = {
    "G": 1,
    "D": 2,
    "A": 3,
    "E": 4,
    "B": 5,
}


def _prioridade_corda(posicao: list[int]) -> tuple[int, int, int]:
    """Retorna chave de ordenação que prefere cordas G/D/A e depois casas mais baixas."""
    corda, traste = posicao
    prioridade = 0 if corda <= 3 else 1 if corda == 4 else 2
    return (prioridade, traste, corda)


def _nota_para_indice(nota: str) -> int:
    """Converte "A#1" → índice interno."""
    nome   = nota[:-1]
    oitava = int(nota[-1])
    return (oitava * 12) + _MAPA_NOTAS[nome] - 11


def converter_notas_para_indices(vetor_notas: list[str]) -> list[int]:
    """Converte uma lista de nomes de notas para índices internos."""
    return [_nota_para_indice(n) for n in vetor_notas]


def _nota_para_midi(nota: str) -> int:
    nome   = nota[:-1]
    oitava = int(nota[-1])
    return oitava * 12 + _MAPA_NOTAS[nome]


def calcular_casas_baixo(vetor_notas: list[str]) -> dict[str, list[list[int]]]:
    """
    Para cada nota, calcula todas as posições válidas no braço do baixo.
    """
    notas_unicas = list(dict.fromkeys(vetor_notas))
    notas_num    = converter_notas_para_indices(notas_unicas)

    matriz_resultados = {}
    for i, nota_nome in enumerate(notas_unicas):
        valor_nota     = notas_num[i]
        possibilidades = []
        for valor_corda, num_corda in _CORDAS_INFO.items():
            casa_nota = valor_nota - valor_corda
            if 0 <= casa_nota <= _MAX_CASAS:
                possibilidades.append([num_corda, casa_nota])
        possibilidades.sort(key=_prioridade_corda)
        matriz_resultados[nota_nome] = possibilidades

    return matriz_resultados


def _mapear_corda_preferida(corda) -> int | None:
    if corda is None:
        return None
    if isinstance(corda, int):
        return corda
    if isinstance(corda, str):
        return _CORDA_NOME_PARA_NUMERO.get(corda.upper())
    return None


def bridge_notas_para_dp(
    sequencia_notas: list[dict],
    posicoes_dict: dict[str, list[list[int]]],
    preferir_corda_detectada: bool = True,
) -> list[dict]:
    """
    Converte a saída do Módulo 2 para o formato de entrada do Módulo 3 (DP).
    """
    notas_dp = []
    for nota in sequencia_notas:
        nome = nota["nome"]
        if nome not in posicoes_dict or not posicoes_dict[nome]:
            continue
        posicoes = list(posicoes_dict[nome])
        if preferir_corda_detectada:
            corda_pref = _mapear_corda_preferida(nota.get("corda"))
            if corda_pref in (1, 2, 3):
                posicoes.sort(key=lambda p: (p[0] != corda_pref, _prioridade_corda(p)))
            else:
                posicoes.sort(key=_prioridade_corda)
        else:
            posicoes.sort(key=_prioridade_corda)
        entrada = {"nome": nome, "posicoes": posicoes}
        if "inicio" in nota:
            entrada["inicio"] = nota["inicio"]
        if "fim" in nota:
            entrada["fim"] = nota["fim"]
        if "corda" in nota:
            entrada["corda"] = nota["corda"]
        notas_dp.append(entrada)
    return notas_dp


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 3 — MENOR CAMINHO (PROGRAMAÇÃO DINÂMICA)
# ══════════════════════════════════════════════════════════════════════════════

def custo_manhattan(pos1: list[int], pos2: list[int]) -> float:
    """|Δtraste| + |Δcorda|"""
    return abs(pos2[1] - pos1[1]) + abs(pos2[0] - pos1[0])


def custo_euclidiano(pos1: list[int], pos2: list[int]) -> float:
    """sqrt(Δtraste² + Δcorda²)"""
    return math.sqrt((pos2[1] - pos1[1])**2 + (pos2[0] - pos1[0])**2)


def custo_ponderado(pos1: list[int], pos2: list[int], peso_traste: float = 2.0) -> float:
    """|Δtraste|*peso + |Δcorda|"""
    return abs(pos2[1] - pos1[1]) * peso_traste + abs(pos2[0] - pos1[0])


def custo_fingering(pos1: list[int], pos2: list[int],
                    peso_corda: float = 2.5, peso_traste: float = 1.0) -> float:
    """|Δtraste| + |Δcorda|*peso_corda com penalidade por corda aguda."""
    if pos2[0] <= 3:
        penalidade_corda = 0.0
    elif pos2[0] == 4:
        penalidade_corda = 2.5
    else:
        penalidade_corda = 5.0
    return abs(pos2[1] - pos1[1]) * peso_traste + abs(pos2[0] - pos1[0]) * peso_corda + penalidade_corda


_custo_padrao = custo_fingering


def menor_caminho_DP(
    notas: list[dict],
    fn_custo=None,
    preferir_corda_detectada: bool = True,
    bonus_corda: float = 0.5,
) -> tuple[float, list[dict]]:
    """
    Encontra a sequência de posições com menor custo total usando Programação Dinâmica.
    """
    if not notas:
        raise ValueError("Lista de notas está vazia.")
    for i, n in enumerate(notas):
        if not n.get("posicoes"):
            raise ValueError(f"Nota no índice {i} ('{n.get('nome')}') não tem posições.")

    fn = fn_custo or _custo_padrao
    n  = len(notas)

    dp = [[None] * len(notas[i]["posicoes"]) for i in range(n)]

    for j in range(len(notas[0]["posicoes"])):
        dp[0][j] = (0.0, None)

    for i in range(1, n):
        corda_pref = _mapear_corda_preferida(notas[i].get("corda")) if preferir_corda_detectada else None
        for j, pos_atual in enumerate(notas[i]["posicoes"]):
            melhor  = float("inf")
            de_onde = None
            for k, pos_ant in enumerate(notas[i - 1]["posicoes"]):
                c = dp[i - 1][k][0] + fn(pos_ant, pos_atual)
                if corda_pref is not None and pos_atual[0] == corda_pref:
                    c -= bonus_corda
                if c < melhor:
                    melhor, de_onde = c, k
            dp[i][j] = (melhor, de_onde)

    melhor_j    = min(range(len(notas[-1]["posicoes"])),
                      key=lambda j: dp[-1][j][0])
    custo_total = dp[-1][melhor_j][0]

    caminho, j = [], melhor_j
    for i in range(n - 1, -1, -1):
        entrada = {
            "nota":    notas[i]["nome"],
            "posicao": notas[i]["posicoes"][j],
        }
        for chave, valor in notas[i].items():
            if chave not in ("nome", "posicoes"):
                entrada[chave] = valor
        caminho.append(entrada)
        if i > 0:
            j = dp[i][j][1]

    return custo_total, list(reversed(caminho))


def bridge_caminho_para_tab(caminho: list[dict]) -> list[list]:
    """
    Converte a saída de menor_caminho_DP() para o formato de entrada
    de print_tab_multiplas_notas().
    """
    return [
        [passo["posicao"][0], passo["posicao"][1], i]
        for i, passo in enumerate(caminho)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 4 — RENDERIZAÇÃO DE TABLATURA EM ASCII
# ══════════════════════════════════════════════════════════════════════════════

_NOMES_CORDAS_5 = {1: "G", 2: "D", 3: "A", 4: "E", 5: "B"}
_NOMES_CORDAS_4 = {1: "G", 2: "D", 3: "A", 4: "E"}


def print_tab_multiplas_notas(
    sequencia_escolhida: list[list[int]],
    num_cordas: int = 5,
) -> str:
    """
    Retorna a tablatura ASCII para uma sequência de notas.
    """
    nomes_cordas = _NOMES_CORDAS_5 if num_cordas == 5 else _NOMES_CORDAS_4
    tablatura    = {i: f"{nomes_cordas[i]}|--" for i in range(1, num_cordas + 1)}

    if not sequencia_escolhida:
        return "\n".join(tablatura[i] for i in range(1, num_cordas + 1))

    blocos_tempo = []
    bloco_atual  = []
    tempo_ref    = sequencia_escolhida[0][2]

    for nota in sequencia_escolhida:
        corda, casa, tempo = nota
        if tempo == tempo_ref:
            bloco_atual.append((corda, casa))
        else:
            blocos_tempo.append(bloco_atual)
            bloco_atual = [(corda, casa)]
            tempo_ref   = tempo
    blocos_tempo.append(bloco_atual)

    for bloco in blocos_tempo:
        pular_tempo = any(n[0] == 0 for n in bloco)

        if pular_tempo:
            for c in range(1, num_cordas + 1):
                tablatura[c] += "---"
            continue

        largura        = max(len(str(n[1])) for n in bloco) if bloco else 1
        notas_no_bloco = {n[0]: n[1] for n in bloco}

        for c in range(1, num_cordas + 1):
            if c in notas_no_bloco:
                casa      = str(notas_no_bloco[c])
                tablatura[c] += casa + "-" * (largura - len(casa) + 1)
            else:
                tablatura[c] += "-" * (largura + 1)

        for c in range(1, num_cordas + 1):
            tablatura[c] += "-"

    return "\n".join(tablatura[i] for i in range(1, num_cordas + 1))


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 5 — GERADORES DE RUÍDO (LEE & SHEN 2011)
# ══════════════════════════════════════════════════════════════════════════════

SR_AUDIO  = 22050
AMPLITUDE = 0.8


class RuidoMusical(Enum):
    """Enum de todos os tipos de perturbação disponíveis."""
    NORMAL                = 0
    SAG                   = 1
    SWELL                 = 2
    INTERRUPTION          = 3
    FLICKER               = 4
    OSCILLATORY_TRANSIENT = 5
    HARMONIC              = 6
    SAG_HARMONIC          = 7
    SWELL_HARMONIC        = 8
    NOTCH                 = 9
    SPIKE                 = 10
    INTERRUPTION_HARMONIC = 11
    FLICKER_HARMONIC      = 12
    FLICKER_SAG           = 13
    FLICKER_SWELL         = 14
    IMPULSIVE_TRANSIENT   = 15


DESCRICAO_MUSICAL = {
    RuidoMusical.NORMAL:                "Sinal limpo (baseline)",
    RuidoMusical.SAG:                   "Queda de amplitude janelada (dedo mal posicionado / muffled)",
    RuidoMusical.SWELL:                 "Crescimento de amplitude janelado (crescendo / mais pressão)",
    RuidoMusical.INTERRUPTION:          "Mute quase total (palm mute pesado, alpha≈1)",
    RuidoMusical.FLICKER:               "Tremolo / vibrato de amplitude (modulação AM lenta)",
    RuidoMusical.OSCILLATORY_TRANSIENT: "Fret buzz / ressonância parasita amortecida",
    RuidoMusical.HARMONIC:              "Distorção suave (harmônicos ímpares, 3°/5°/7°)",
    RuidoMusical.SAG_HARMONIC:          "Mute + distorção simultâneos",
    RuidoMusical.SWELL_HARMONIC:        "Crescimento + distorção simultâneos",
    RuidoMusical.NOTCH:                 "Pickup noise / interferência RF periódica (entalhes)",
    RuidoMusical.SPIKE:                 "Click de traste / pop de palheta (picos periódicos)",
    RuidoMusical.INTERRUPTION_HARMONIC: "Mute total + distorção",
    RuidoMusical.FLICKER_HARMONIC:      "Tremolo + distorção",
    RuidoMusical.FLICKER_SAG:           "Tremolo + mute parcial",
    RuidoMusical.FLICKER_SWELL:         "Tremolo + crescimento (vibrato expressivo)",
    RuidoMusical.IMPULSIVE_TRANSIENT:   "Bump de cabo / interferência impulsiva isolada",
}


def _u(x: np.ndarray) -> np.ndarray:
    """Função degrau de Heaviside."""
    return np.heaviside(x, 0)


def _time_axis(duracao: float, sr: int) -> np.ndarray:
    """Gera o eixo de tempo uniforme."""
    return arange(0, duracao, 1.0 / sr)


def _gen_normal(f: float, duracao: float, sr: int, A: float) -> np.ndarray:
    t = _time_axis(duracao, sr)
    return A * np.sin(2 * np.pi * f * t)


def _gen_sag(f: float, duracao: float, sr: int, A: float,
             alpha: float, t1: float, t2: float) -> np.ndarray:
    """Queda de amplitude entre t1 e t2."""
    t        = _time_axis(duracao, sr)
    envelope = 1 - alpha * (_u(t - t1) - _u(t - t2))
    return A * envelope * np.sin(2 * np.pi * f * t)


def _gen_swell(f: float, duracao: float, sr: int, A: float,
               alpha: float, t1: float, t2: float) -> np.ndarray:
    """Crescimento de amplitude entre t1 e t2."""
    t        = _time_axis(duracao, sr)
    envelope = 1 + alpha * (_u(t - t1) - _u(t - t2))
    return A * envelope * np.sin(2 * np.pi * f * t)


def _gen_interruption(f, duracao, sr, A, alpha, t1, t2) -> np.ndarray:
    """Mute quase total (sag com alpha próximo de 1)."""
    return _gen_sag(f, duracao, sr, A, alpha, t1, t2)


def _gen_flicker(f: float, duracao: float, sr: int, A: float,
                 alpha: float, beta: float) -> np.ndarray:
    """Modulação de amplitude por senoide de baixa frequência beta (Hz)."""
    t         = _time_axis(duracao, sr)
    modulator = 1 + alpha * np.sin(2 * np.pi * beta * t)
    return A * modulator * np.sin(2 * np.pi * f * t)


def _gen_oscillatory_transient(f: float, duracao: float, sr: int, A: float,
                                alpha: float, tau: float,
                                fn: float, t1: float, t2: float) -> np.ndarray:
    """Transiente oscilatório amortecido adicionado ao sinal base."""
    t          = _time_axis(duracao, sr)
    base       = A * np.sin(2 * np.pi * f * t)
    c          = alpha * np.exp(-((t - t1) / tau))
    d          = _u(t - t1) - _u(t - t2)
    e          = np.sin(2 * np.pi * fn * t)
    transiente = mult(mult(c, d), e)
    y          = base + transiente
    pico       = np.max(np.abs(y))
    return y / pico * A if pico > 0 else y


def _gen_harmonic(f: float, duracao: float, sr: int, A: float,
                  alpha: list[float]) -> np.ndarray:
    """Adiciona harmônicos ímpares (3°, 5°, 7°) ao sinal fundamental."""
    t  = _time_axis(duracao, sr)
    a1 = np.sqrt(1 - sum(a**2 for a in alpha))
    s  = a1 * np.sin(2 * np.pi * f * t)
    for k, a in enumerate(alpha):
        ordem = 2 * (k + 1) + 1
        s += a * np.sin(f * 2 * np.pi * t * ordem)
    pico = np.max(np.abs(s))
    return A * s / pico if pico > 0 else s


def _gen_sag_harmonic(f, duracao, sr, A, alpha_s, t1, t2, alpha) -> np.ndarray:
    """SAG aplicado sobre sinal com harmônicos."""
    t        = _time_axis(duracao, sr)
    envelope = 1 - alpha_s * (_u(t - t1) - _u(t - t2))
    h        = _gen_harmonic(f, duracao, sr, A=1.0, alpha=alpha)
    y        = envelope * h
    pico     = np.max(np.abs(y))
    return A * y / pico if pico > 0 else y


def _gen_swell_harmonic(f, duracao, sr, A, alpha_s, t1, t2, alpha) -> np.ndarray:
    """SWELL aplicado sobre sinal com harmônicos."""
    t        = _time_axis(duracao, sr)
    envelope = 1 + alpha_s * (_u(t - t1) - _u(t - t2))
    h        = _gen_harmonic(f, duracao, sr, A=1.0, alpha=alpha)
    y        = envelope * h
    pico     = np.max(np.abs(y))
    return A * y / pico if pico > 0 else y


def _gen_notch(f: float, duracao: float, sr: int, A: float,
               k: float, t1: float, t2: float) -> np.ndarray:
    """Entalhes (notches) periódicos sincronizados com a fundamental."""
    t        = _time_axis(duracao, sr)
    base     = np.sin(2 * np.pi * f * t)
    notch_   = np.zeros(len(t))
    n_ciclos = int(duracao * f) + 1
    for n in range(n_ciclos):
        notch_ += k * (_u(t - (t1 + n / f)) - _u(t - (t2 + n / f)))
    return A * (base + np.multiply(notch_, -np.sign(base)))


def _gen_spike(f: float, duracao: float, sr: int, A: float,
               k: float, t1: float, t2: float) -> np.ndarray:
    """Picos positivos periódicos sincronizados com a fundamental."""
    t        = _time_axis(duracao, sr)
    base     = np.sin(2 * np.pi * f * t)
    spike_   = np.zeros(len(t))
    n_ciclos = int(duracao * f) + 1
    for n in range(n_ciclos):
        spike_ += k * (_u(t - (t1 + n / f)) - _u(t - (t2 + n / f)))
    return A * (base + np.multiply(spike_, +np.sign(base)))


def _gen_interruption_harmonic(f, duracao, sr, A, alpha_i, t1, t2, alpha) -> np.ndarray:
    """INTERRUPTION (mute quase total) + harmônicos ímpares."""
    t        = _time_axis(duracao, sr)
    envelope = 1 - alpha_i * (_u(t - t1) - _u(t - t2))
    h        = _gen_harmonic(f, duracao, sr, A=1.0, alpha=alpha)
    y        = envelope * h
    pico     = np.max(np.abs(y))
    return A * y / pico if pico > 0 else y


def _gen_flicker_harmonic(f, duracao, sr, A, alpha_f, beta_f, alpha) -> np.ndarray:
    """FLICKER (tremolo) + harmônicos ímpares."""
    t         = _time_axis(duracao, sr)
    modulator = 1 + alpha_f * np.sin(2 * np.pi * beta_f * t)
    h         = _gen_harmonic(f, duracao, sr, A=1.0, alpha=alpha)
    y         = modulator * h
    pico      = np.max(np.abs(y))
    return A * y / pico if pico > 0 else y


def _gen_flicker_sag(f, duracao, sr, A, alpha, t1, t2, alpha_f, beta_f) -> np.ndarray:
    """FLICKER (tremolo) aplicado sobre sag."""
    t         = _time_axis(duracao, sr)
    sag_env   = 1 - alpha * (_u(t - t1) - _u(t - t2))
    fl_signal = _gen_flicker(f, duracao, sr, A=1.0, alpha=alpha_f, beta=beta_f)
    y         = sag_env * fl_signal
    pico      = np.max(np.abs(y))
    return A * y / pico if pico > 0 else y


def _gen_flicker_swell(f, duracao, sr, A, alpha, t1, t2, alpha_f, beta_f) -> np.ndarray:
    """FLICKER (tremolo) aplicado sobre swell."""
    t         = _time_axis(duracao, sr)
    swell_env = 1 + alpha * (_u(t - t1) - _u(t - t2))
    fl_signal = _gen_flicker(f, duracao, sr, A=1.0, alpha=alpha_f, beta=beta_f)
    y         = swell_env * fl_signal
    pico      = np.max(np.abs(y))
    return A * y / pico if pico > 0 else y


def _gen_impulsive_transient(f, duracao, sr, A, alpha, t1, t2) -> np.ndarray:
    """Perturbação impulsiva breve e isolada."""
    return _gen_sag(f, duracao, sr, A, alpha, t1, t2)


class ParamsAleatorios:
    """Gera parâmetros aleatórios válidos para cada tipo de perturbação."""

    def __init__(self, tipo: RuidoMusical, f: float, duracao: float):
        self.f       = f
        self.duracao = duracao

        tamanho = random.uniform(0.2, 0.6) * duracao
        self.t1 = random.uniform(0.05 * duracao, (duracao - tamanho) * 0.95)
        self.t2 = self.t1 + tamanho

        if tipo == RuidoMusical.SAG:
            self.alpha = random.uniform(0.1, 0.9)

        elif tipo == RuidoMusical.SWELL:
            self.alpha = random.uniform(0.1, 0.8)

        elif tipo == RuidoMusical.INTERRUPTION:
            self.alpha = random.uniform(0.9, 1.0)

        elif tipo == RuidoMusical.FLICKER:
            self.alpha = random.uniform(0.05, 0.25)
            self.beta  = random.uniform(2.0, 8.0)

        elif tipo == RuidoMusical.OSCILLATORY_TRANSIENT:
            self.alpha = random.uniform(0.1, 0.5)
            self.fn    = f * random.choice([2, 3, 4, 5])
            self.tau   = random.uniform(0.05, 0.2) * duracao
            self.t1    = random.uniform(0.1, 0.4) * duracao
            self.t2    = self.t1 + random.uniform(0.05, 0.15) * duracao

        elif tipo == RuidoMusical.HARMONIC:
            self.alpha = [
                random.uniform(0.05, 0.20),
                random.uniform(0.03, 0.15),
                random.uniform(0.02, 0.10),
            ]

        elif tipo in (RuidoMusical.SAG_HARMONIC, RuidoMusical.SWELL_HARMONIC):
            self.alpha_s = random.uniform(0.1, 0.7)
            self.alpha   = [
                random.uniform(0.05, 0.20),
                random.uniform(0.03, 0.15),
                random.uniform(0.02, 0.10),
            ]

        elif tipo in (RuidoMusical.NOTCH, RuidoMusical.SPIKE):
            self.k  = random.uniform(0.05, 0.3)
            periodo = 1.0 / f
            self.t1 = random.uniform(0, 0.3 * periodo)
            self.t2 = self.t1 + random.uniform(0.01, 0.08) * periodo

        elif tipo == RuidoMusical.INTERRUPTION_HARMONIC:
            self.alpha_i = random.uniform(0.9, 1.0)
            self.alpha   = [
                random.uniform(0.05, 0.20),
                random.uniform(0.03, 0.15),
                random.uniform(0.02, 0.10),
            ]

        elif tipo == RuidoMusical.FLICKER_HARMONIC:
            self.alpha_f = random.uniform(0.05, 0.20)
            self.beta_f  = random.uniform(2.0, 8.0)
            self.alpha   = [
                random.uniform(0.05, 0.20),
                random.uniform(0.03, 0.15),
                random.uniform(0.02, 0.10),
            ]

        elif tipo in (RuidoMusical.FLICKER_SAG, RuidoMusical.FLICKER_SWELL):
            self.alpha   = random.uniform(0.1, 0.7)
            self.alpha_f = random.uniform(0.05, 0.20)
            self.beta_f  = random.uniform(2.0, 8.0)

        elif tipo == RuidoMusical.IMPULSIVE_TRANSIENT:
            self.alpha = random.uniform(0.3, 0.8)
            self.t1    = random.uniform(0.1, 0.8) * duracao
            self.t2    = self.t1 + random.uniform(0.01, 0.05) * duracao


def gerar_sinal_perturbado(
    tipo: RuidoMusical,
    freq_hz: float,
    duracao: float,
    sr: int = SR_AUDIO,
    amplitude: float = AMPLITUDE,
    params: ParamsAleatorios = None,
) -> tuple[np.ndarray, str]:
    """Gera um sinal com a perturbação especificada a partir de parâmetros aleatórios."""
    if params is None:
        params = ParamsAleatorios(tipo, freq_hz, duracao)

    p = params
    f = freq_hz
    A = amplitude
    d = duracao

    if tipo == RuidoMusical.NORMAL:
        y = _gen_normal(f, d, sr, A)
    elif tipo == RuidoMusical.SAG:
        y = _gen_sag(f, d, sr, A, p.alpha, p.t1, p.t2)
    elif tipo == RuidoMusical.SWELL:
        y = _gen_swell(f, d, sr, A, p.alpha, p.t1, p.t2)
    elif tipo == RuidoMusical.INTERRUPTION:
        y = _gen_interruption(f, d, sr, A, p.alpha, p.t1, p.t2)
    elif tipo == RuidoMusical.FLICKER:
        y = _gen_flicker(f, d, sr, A, p.alpha, p.beta)
    elif tipo == RuidoMusical.OSCILLATORY_TRANSIENT:
        y = _gen_oscillatory_transient(f, d, sr, A, p.alpha, p.tau, p.fn, p.t1, p.t2)
    elif tipo == RuidoMusical.HARMONIC:
        y = _gen_harmonic(f, d, sr, A, p.alpha)
    elif tipo == RuidoMusical.SAG_HARMONIC:
        y = _gen_sag_harmonic(f, d, sr, A, p.alpha_s, p.t1, p.t2, p.alpha)
    elif tipo == RuidoMusical.SWELL_HARMONIC:
        y = _gen_swell_harmonic(f, d, sr, A, p.alpha_s, p.t1, p.t2, p.alpha)
    elif tipo == RuidoMusical.NOTCH:
        y = _gen_notch(f, d, sr, A, p.k, p.t1, p.t2)
    elif tipo == RuidoMusical.SPIKE:
        y = _gen_spike(f, d, sr, A, p.k, p.t1, p.t2)
    elif tipo == RuidoMusical.INTERRUPTION_HARMONIC:
        y = _gen_interruption_harmonic(f, d, sr, A, p.alpha_i, p.t1, p.t2, p.alpha)
    elif tipo == RuidoMusical.FLICKER_HARMONIC:
        y = _gen_flicker_harmonic(f, d, sr, A, p.alpha_f, p.beta_f, p.alpha)
    elif tipo == RuidoMusical.FLICKER_SAG:
        y = _gen_flicker_sag(f, d, sr, A, p.alpha, p.t1, p.t2, p.alpha_f, p.beta_f)
    elif tipo == RuidoMusical.FLICKER_SWELL:
        y = _gen_flicker_swell(f, d, sr, A, p.alpha, p.t1, p.t2, p.alpha_f, p.beta_f)
    elif tipo == RuidoMusical.IMPULSIVE_TRANSIENT:
        y = _gen_impulsive_transient(f, d, sr, A, p.alpha, p.t1, p.t2)
    else:
        raise ValueError(f"Tipo de ruído desconhecido: {tipo}")

    descricao = DESCRICAO_MUSICAL.get(tipo, str(tipo))
    return y.astype(np.float32), descricao


def aplicar_ruido(
    sinal: np.ndarray,
    freq_hz: float,
    tipo: RuidoMusical,
    sr: int = SR_AUDIO,
    params: ParamsAleatorios = None,
) -> tuple[np.ndarray, str]:
    """Aplica uma perturbação sobre um sinal existente."""
    duracao   = len(sinal) / sr
    amplitude = float(np.max(np.abs(sinal))) or AMPLITUDE
    y, desc   = gerar_sinal_perturbado(tipo, freq_hz, duracao, sr, amplitude, params)
    n = len(sinal)
    if len(y) >= n:
        return y[:n], desc
    return np.pad(y, (0, n - len(y))), desc


def suite_ruidos_musicais(
    nota_hz: float = 110.0,
    nota_nome: str = "A2",
    duracao: float = 1.5,
    sr: int = SR_AUDIO,
    seed: int = 42,
) -> list[tuple]:
    """Gera uma suite completa de casos de teste com todos os tipos de perturbação."""
    random.seed(seed)
    np.random.seed(seed)

    gabarito_base = [{
        "freq_hz":   nota_hz,
        "nota_nome": nota_nome,
        "inicio":    0.0,
        "fim":       duracao,
    }]

    casos = []
    for tipo in RuidoMusical:
        try:
            audio, descricao = gerar_sinal_perturbado(tipo, nota_hz, duracao, sr)
            nome = f"{nota_nome} | {descricao}"
            casos.append((audio, gabarito_base, nome))
        except Exception:
            pass

    return casos


def listar_ruidos() -> dict[str, str]:
    """Retorna dicionário de todos os tipos de perturbação com suas analogias musicais."""
    return {tipo.name: desc for tipo, desc in DESCRICAO_MUSICAL.items()}


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 6 — PIPELINE COMPLETO
# ══════════════════════════════════════════════════════════════════════════════

def pipeline_completo(
    audio_path: str,
    plotar: bool = False,
    duracao_minima: float = 0.08,
    num_cordas: int = 5,
    prob_min: float = 0.6,
) -> dict:
    """
    Executa o pipeline completo: áudio → tablatura.

    Parâmetros
    ----------
    audio_path     : str    Caminho do arquivo de áudio.
    plotar         : bool   Se True, exibe o gráfico do pYIN.
    duracao_minima : float  Notas menores que este valor (s) são descartadas.
    num_cordas     : int    4 ou 5 cordas.
    prob_min       : float  Limiar de probabilidade de voicing do pYIN (0–1).

    Retorna
    -------
    dict com as saídas intermediárias de cada módulo.
    """
    segmentos = analisar_baixo(audio_path, plotar=plotar, prob_min=prob_min)

    sequencia = bridge_pyin_para_notas(segmentos, duracao_minima=duracao_minima)
    if not sequencia:
        return {}

    nomes_unicos  = list(dict.fromkeys(n["nome"] for n in sequencia))
    posicoes_dict = calcular_casas_baixo(nomes_unicos)

    notas_dp = bridge_notas_para_dp(sequencia, posicoes_dict)
    if not notas_dp:
        return {}

    custo_total, caminho = menor_caminho_DP(notas_dp)

    tab_input   = bridge_caminho_para_tab(caminho)
    tab_ascii   = print_tab_multiplas_notas(tab_input, num_cordas=num_cordas)

    resultado = {
        "segmentos":     segmentos,
        "sequencia":     sequencia,
        "posicoes_dict": posicoes_dict,
        "notas_dp":      notas_dp,
        "custo_total":   custo_total,
        "caminho":       caminho,
        "tab_input":     tab_input,
        "tab_ascii":     tab_ascii,
    }
    
    return _numpy_to_python(resultado)