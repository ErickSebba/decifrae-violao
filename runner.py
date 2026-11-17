"""
runner.py
=========
Matriz de ablação: roda as variantes do pipeline sobre um manifest e escreve
um CSV por experimento em `data/results/`.

As variantes A–E são INCREMENTAIS -- cada uma acrescenta uma etapa à anterior,
para que a diferença entre duas linhas vizinhas seja atribuível a uma etapa só.
F e os dois baselines saem dessa linha para isolar outras coisas.

    V4   baseline legacy_v4 completo: classificador de energia + inércia
         temporal (+0.5 no acorde repetido, -0.1 no nome mais longo)
    V4b  o MESMO classificador de energia SEM os dois termos temporais --
         cópia em runner.py, porque legacy_v4.py é intocável. Separa o que
         vem do classificador do que vem do modelo temporal guloso.
    A    smooth=0,  complexity_penalty=0,    use_viterbi=False, min_dur=0
    B    smooth=21, complexity_penalty=0,    use_viterbi=False, min_dur=0
    C    smooth=21, complexity_penalty=0.06, use_viterbi=False, min_dur=0
    D    smooth=21, complexity_penalty=0.06, use_viterbi=True,  min_dur=0
    E    smooth=21, complexity_penalty=0.06, use_viterbi=True,  min_dur=0.8
    F    igual a D, porém vocabulário BASIC (24 templates, só maj/min)
    C0   C com confidence_gate=0   (o argmax sempre rotula)
    D0   D com n_logprob=-1e9      (o estado N nunca vence no Viterbi)
    E0   E com n_logprob=-1e9
    F0   F com n_logprob=-1e9
    C0rg/D0rg/E0rg/F0rg  as mesmas, e também com rel_gate=0
    --- pós-revisão (docs/ADENDO_REVISAO.md; exigem --post-review) ---
    Crg/Drg      C/D só com rel_gate=0 (completam o fatorial 2x2x2)
    Cmatch       C com confidence_gate = THETA_MATCH (cobertura de D)
    Dmatch       D com n_logprob = BETA_MATCH (cobertura de C)
    D0rg_cal     D0rg com change_penalty = CP_CAL_MEDIUM
    F0rg_cal     F0rg com change_penalty = CP_CAL_BASIC

AS FONTES DE N
--------------
A referência do GuitarSet não tem NENHUM N (0 % do tempo em chord[0] e
chord[1]), então todo N estimado é erro puro -- e ele domina a diferença entre
as variantes: 40 % do tempo em A–C, 12 % em D/E. As variantes com sufixo 0
existem para separar "rotular mais tempo" de "rotular melhor".

Há exatamente TRÊS fontes de N, e elas não são alternativas: são camadas.

  1. confidence_gate, em `classify_vector` -- só nas variantes SEM Viterbi.
     Desligado por C0.
  2. n_logprob, o estado N do Viterbi -- só nas variantes COM Viterbi.
     Desligado por D0/E0/F0.
  3. force_n, o gate de RMS (`gate = max(abs_floor, rel_gate * mediana)`).
     Este SOBREPÕE os outros dois: `viterbi.decode` zera as emissões de
     acorde em -50 e põe N em 0.0 quando force_n[t] é True, então nem
     n_logprob=-1e9 o vence. É a única fonte que sobra em C0/D0/E0/F0, e é o
     que as versões `rg` desligam (rel_gate=0 deixa só o piso absoluto
     abs_floor=5e-4, isto é, silêncio digital de verdade).

DUAS MÉTRICAS
-------------
Cada linha traz os 4 níveis sobre a faixa TODA e os mesmos 4 sobre o TEMPO
ROTULADO (`root_rotulado` etc.), que exclui o tempo devolvido como N. A
segunda responde "quando se arrisca, acerta?"; a diferença entre as duas é o
custo do silêncio auto-imposto. Ver `acerto_no_tempo_rotulado` para a
definição exata do denominador.

E é a configuração atual do sistema: confere com os defaults de `config.py`
nos quatro campos ablacionados e nos demais (change_penalty 2.0, temp 0.1,
n_logprob -2.5, rel_gate 0.2, abs_floor 5e-4, ext_sharpness 4.0), que ficam
fixos em todas as variantes.

SOBRE A VARIANTE "G" QUE NÃO EXISTE
-----------------------------------
"E com min_dur=0" é D, campo por campo -- D já é exatamente isso. Não há
variante G; `test_runner.py` fixa a equivalência para que ninguém a recrie
achando que mede outra coisa.

DOIS PARÂMETROS QUE NÃO ESTÃO NO DECODE
---------------------------------------
`complexity_penalty` e `ext_sharpness` configuram o CLASSIFICADOR, não o
`pipeline.decode` -- que os ignora de propósito (ver o docstring dele). Um
runner que montasse um classificador só e variasse esses campos no `post`
estaria varrendo dois parâmetros sem efeito nenhum, e a ablação concluiria que
o viés pró-tríade não importa. O vocabulário tem a mesma natureza. Aqui cada
trio (complexity_penalty, ext_sharpness, vocabulário) tem o seu próprio
`CosineChordClassifier`, memoizado em `classificador_de`.

`smooth` é PRÉ-chroma, então A e B usam extrações diferentes -- o cache
resolve isso sozinho, porque a chave dele inclui todos os campos de
PreChromaConfig.

COLUNAS DE DIAGNÓSTICO
----------------------
Além dos 4 níveis, cada linha traz onde o erro está: fração do tempo estimada
como N, fração com a tônica certa e a qualidade errada, fração com a tônica
errada, e o número de segmentos estimados vs. de referência (super ou
subsegmentação). São medidas na MESMA grade que o mir_eval usa para pontuar.

REFERÊNCIA
----------
`--ref-layer 0` (default) é o lead sheet instruído; `1` é a camada
performed/inferred que o `docs/DATASETS.md` §2 declara como referência
principal do benchmark. A camada usada vai na coluna `ref_camada` e no
meta.json -- nenhum número fica órfão da sua referência.

CLI:

    python runner.py --manifest data/manifests/guitarset_comping.csv
    python runner.py --manifest ... --variants A,B,C
    python runner.py --manifest ... --ref-layer 1
    python runner.py --manifest ... --splits test     # explícito, ver abaixo

O split `test` NUNCA entra por default (CLAUDE.md: busca e ajuste só na
validação; o teste é lido uma vez, no fim).
"""

import argparse
import csv
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

import numpy as np

import cache
import dataset_io as ds
from chord_templates import BASIC, MEDIUM, build_templates
from classifier import CosineChordClassifier
from config import PRE_CHROMA, POST_CHROMA, PreChromaConfig, PostChromaConfig
from evaluate import score_segments
# _to_arrays é privado, mas é de propósito: o diagnóstico precisa montar os
# rótulos exatamente como o score_segments monta, senão mediria outra coisa.
from evaluate import _to_arrays
from pipeline import decode

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

LEVELS = ['root', 'majmin', 'sevenths', 'mirex']

# Camada de anotação usada como referência por default (0 = lead sheet).
REF_CAMADA = 0

VOCABULARIOS = {"MEDIUM": MEDIUM, "BASIC": BASIC}

# Splits que exigem menção explícita na linha de comando.
SPLITS_PROTEGIDOS = {"test"}

DIAG_FIELDS = ["frac_n_est", "frac_tonica_ok_qualidade_erro",
               "frac_tonica_erro", "n_segmentos_est", "n_segmentos_ref"]

# Segmentação do próprio mir_eval, que `chord.evaluate` já devolve junto dos
# níveis -- não custa uma avaliação a mais. Dependem SÓ dos intervalos, não
# dos rótulos, então são idênticas nas duas camadas do GuitarSet (mesmas
# fronteiras) e não são afetadas por `ref_is_harte`.
#   overseg  : 1 = não supersegmentou (fronteiras a mais)
#   underseg : 1 = não subsegmentou (fronteiras de menos)
#   seg      : min(overseg, underseg), o 'MeanSeg' do MIREX
SEG_FIELDS = ["overseg", "underseg", "seg"]


@dataclass(frozen=True)
class Variante:
    nome: str
    pre: PreChromaConfig = None
    post: PostChromaConfig = None
    motor: str = "cosseno"          # 'cosseno' | 'v4' | 'v4b'
    vocab: str = "MEDIUM"


# Valores pós-revisão, escolhidos SÓ na validação por calibracao_revisao.py e
# registrados em docs/ADENDO_REVISAO.md antes de qualquer execução no teste.
THETA_MATCH = 0.65      # confidence_gate de Cmatch
BETA_MATCH = -2.25      # n_logprob de Dmatch
CP_CAL_MEDIUM = 1.5     # change_penalty de D0rg_cal
CP_CAL_BASIC = 1.0      # change_penalty de F0rg_cal


def _variantes():
    """A matriz, montada por diferença sobre os defaults de config.py."""
    pre_sem_smooth = replace(PRE_CHROMA, smooth=0)
    sem_bias = replace(POST_CHROMA, complexity_penalty=0.0,
                       use_viterbi=False, min_dur=0.0)
    com_bias = replace(sem_bias, complexity_penalty=0.06)
    com_viterbi = replace(com_bias, use_viterbi=True)
    atual = replace(com_viterbi, min_dur=0.8)

    # Variantes que DESLIGAM as fontes de 'N', para separar "rotular mais
    # tempo" de "rotular melhor". Ver a seção AS FONTES DE N no topo.
    sem_gate = replace(com_bias, confidence_gate=0.0)      # C0: argmax sempre rotula
    n_proibido = -1e9                                      # o estado N nunca vence
    return {
        "V4": Variante("V4", motor="v4", vocab="BASIC"),
        "V4b": Variante("V4b", motor="v4b", vocab="BASIC"),
        "A": Variante("A", pre_sem_smooth, sem_bias),
        "B": Variante("B", PRE_CHROMA, sem_bias),
        "C": Variante("C", PRE_CHROMA, com_bias),
        "D": Variante("D", PRE_CHROMA, com_viterbi),
        "E": Variante("E", PRE_CHROMA, atual),
        "F": Variante("F", PRE_CHROMA, com_viterbi, vocab="BASIC"),
        # --- sem as fontes de N ---
        "C0": Variante("C0", PRE_CHROMA, sem_gate),
        "D0": Variante("D0", PRE_CHROMA, replace(com_viterbi, n_logprob=n_proibido)),
        "E0": Variante("E0", PRE_CHROMA, replace(atual, n_logprob=n_proibido)),
        "F0": Variante("F0", PRE_CHROMA, replace(com_viterbi, n_logprob=n_proibido),
                       vocab="BASIC"),
        # --- idem, e também sem o gate de RMS relativo ---
        "C0rg": Variante("C0rg", PRE_CHROMA, replace(sem_gate, rel_gate=0.0)),
        "D0rg": Variante("D0rg", PRE_CHROMA,
                         replace(com_viterbi, n_logprob=n_proibido, rel_gate=0.0)),
        "E0rg": Variante("E0rg", PRE_CHROMA,
                         replace(atual, n_logprob=n_proibido, rel_gate=0.0)),
        "F0rg": Variante("F0rg", PRE_CHROMA,
                         replace(com_viterbi, n_logprob=n_proibido, rel_gate=0.0),
                         vocab="BASIC"),
        # --- pós-revisão (camera-ready), ver docs/ADENDO_REVISAO.md ---
        # fatorial: só o gate relativo desligado, abstenção própria mantida
        "Crg": Variante("Crg", PRE_CHROMA, replace(com_bias, rel_gate=0.0)),
        "Drg": Variante("Drg", PRE_CHROMA, replace(com_viterbi, rel_gate=0.0)),
        # cobertura igualada, valores escolhidos na validação
        "Cmatch": Variante("Cmatch", PRE_CHROMA,
                           replace(com_bias, confidence_gate=THETA_MATCH)),
        "Dmatch": Variante("Dmatch", PRE_CHROMA,
                           replace(com_viterbi, n_logprob=BETA_MATCH)),
        # penalidade de transição calibrada por vocabulário, na validação
        "D0rg_cal": Variante("D0rg_cal", PRE_CHROMA,
                             replace(com_viterbi, n_logprob=n_proibido,
                                     rel_gate=0.0, change_penalty=CP_CAL_MEDIUM)),
        "F0rg_cal": Variante("F0rg_cal", PRE_CHROMA,
                             replace(com_viterbi, n_logprob=n_proibido,
                                     rel_gate=0.0, change_penalty=CP_CAL_BASIC),
                             vocab="BASIC"),
    }


VARIANTES = _variantes()
VARIANTES_POS_REVISAO = ("Crg", "Drg", "Cmatch", "Dmatch", "D0rg_cal",
                         "F0rg_cal")

# ==========================================================================
# Classificadores: um por (complexity_penalty, ext_sharpness, vocabulário)
# ==========================================================================
_CLASSIFICADORES = {}


def classificador_de(post, vocab="MEDIUM"):
    """
    O CosineChordClassifier de uma variante, memoizado pelos QUATRO campos que
    o `decode` não consegue aplicar: complexity_penalty, ext_sharpness,
    confidence_gate e o vocabulário. Duas variantes com o mesmo quarteto
    compartilham a instância; um quarteto novo constrói outra.
    """
    chave = (post.complexity_penalty, post.ext_sharpness,
             post.confidence_gate, vocab)
    if chave not in _CLASSIFICADORES:
        _CLASSIFICADORES[chave] = CosineChordClassifier(
            templates=build_templates(VOCABULARIOS[vocab]),
            complexity_penalty=post.complexity_penalty,
            ext_sharpness=post.ext_sharpness,
            confidence_gate=post.confidence_gate)
    return _CLASSIFICADORES[chave]


# ==========================================================================
# V4b: o classificador de energia do V4 sem o modelo temporal
# ==========================================================================
# Cópia de legacy_v4.classificar_segmento_v4 com DUAS linhas removidas:
#   score += 0.5                    (inércia: bônus no acorde repetido)
#   score -= 0.1                    (penalidade de nome mais longo)
# legacy_v4.py não é editado -- é o baseline intocável do projeto. Como os
# dois termos eram os únicos usos de `acorde_anterior`, V4b é stateless.
_V4_NOTAS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_V4_TIPOS = {
    '':  {'idx': [0, 4, 7], 'bias': 0.15, 'required': None},
    'm': {'idx': [0, 3, 7], 'bias': 0.15, 'required': None},
}


def classificar_segmento_v4b(chroma_segmento):
    """V4 sem inércia temporal e sem penalidade de nome longo."""
    if np.sum(chroma_segmento) < 0.1:
        return ""
    chroma_norm = chroma_segmento / (np.max(chroma_segmento) + 1e-6)

    melhor_score = -float('inf')
    acorde_vencedor = "N/A"

    for i, root in enumerate(_V4_NOTAS):
        for sufixo, dados in _V4_TIPOS.items():
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

            # (sem inércia temporal e sem penalidade de nome longo)

            if score > melhor_score:
                melhor_score = score
                acorde_vencedor = nome_atual

    return acorde_vencedor


def _beat_sync_v4(y, sr, y_harmonic, y_percussive):
    """Segmentação do legacy_v4.run_beat_tracking, sem classificar."""
    import librosa
    tempo, beats = librosa.beat.beat_track(y=y_percussive, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, bins_per_octave=36)
    beats = librosa.util.fix_frames(beats, x_max=chroma.shape[1])
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    tempos = librosa.frames_to_time(beats, sr=sr)
    return chroma_sync, tempos


def _normaliza_v4(label):
    return label if label not in ('', 'N/A') else 'N'


# ==========================================================================
# Estimativa
# ==========================================================================
def estimar(variante, features):
    """
    Segmentos estimados por uma variante do pipeline atual, já no formato
    (start, end, label) que o `evaluate.score_segments` consome -- o `decode`
    devolve dicts, e passar os dicts adiante faz o scorer desempacotar as
    CHAVES ('start', 'end', 'label') em vez dos valores.
    """
    clf = classificador_de(variante.post, variante.vocab)
    segs = decode(features, clf, variante.post)
    return [(s['start'], s['end'], s['label']) for s in segs]


def estimar_v4(y, sr):
    """Baseline completo: usa o legacy_v4 intocado."""
    import librosa
    from legacy_v4 import run_beat_tracking

    y_h, y_p = librosa.effects.hpss(y, margin=3.0)
    segs, _ = run_beat_tracking(y, sr, y_h, y_p)
    return [(s['start'], s['end'], _normaliza_v4(s['label'])) for s in segs]


def estimar_v4b(y, sr):
    """Mesma segmentação do V4, classificador sem os termos temporais."""
    import librosa
    y_h, y_p = librosa.effects.hpss(y, margin=3.0)
    chroma_sync, tempos = _beat_sync_v4(y, sr, y_h, y_p)
    saida = []
    for i in range(chroma_sync.shape[1]):
        label = classificar_segmento_v4b(chroma_sync[:, i])
        saida.append((float(tempos[i]), float(tempos[i + 1]),
                      _normaliza_v4(label)))
    return saida


# ==========================================================================
# Diagnóstico
# ==========================================================================
def _grade_comum(est, ref):
    """
    Alinha estimado e referência na mesma grade temporal que o mir_eval usa
    para pontuar, e devolve (durações, rótulos_ref, rótulos_est, máscara de N
    estimado). É a base do diagnóstico e do acerto no tempo rotulado.
    """
    import mir_eval

    ref_int, ref_lab = _to_arrays(ref, translate=False)
    est_int, est_lab = _to_arrays(est)
    est_int, est_lab = mir_eval.util.adjust_intervals(
        est_int, est_lab, ref_int.min(), ref_int.max(),
        mir_eval.chord.NO_CHORD, mir_eval.chord.NO_CHORD)
    intervalos, ref_lab, est_lab = mir_eval.util.merge_labeled_intervals(
        ref_int, ref_lab, est_int, est_lab)
    duracoes = mir_eval.util.intervals_to_durations(intervalos)

    est_roots, est_semis = mir_eval.chord.encode_many(est_lab, True)[:2]
    # convenção do mir_eval: 'sem acorde' = raiz -1 e nenhum semitom
    est_n = (est_roots == -1) & ~est_semis.any(axis=1)
    return duracoes, ref_lab, est_lab, est_n


def acerto_no_tempo_rotulado(est, ref):
    """
    Acurácia restrita ao tempo que o sistema DE FATO rotulou, por nível.

    Separa "rotular mais tempo" de "rotular melhor": uma variante que devolve
    N em 40 % da faixa tem a métrica normal puxada para baixo pelo silêncio
    auto-imposto, e esta coluna mostra o que ela acerta quando se arrisca.

    Definição: a mesma média ponderada do `mir_eval.chord.weighted_accuracy`,
    restrita aos trechos onde o estimado NÃO é N.

        soma(comparação * duração)  /  soma(duração)   , sobre os trechos
        onde a comparação é válida (>= 0) E o estimado não é N

    NOTA SOBRE A DEFINIÇÃO -- o denominador não é o "tempo total menos o tempo
    N" literal: ele também exclui o tempo que o mir_eval descarta no nível
    (comparação -1, referência fora do vocabulário daquele nível). Sem isso a
    coluna seria incomparável entre níveis e entre camadas: em chord[1] o
    `majmin` só pondera 66,7 % do tempo (ver coverage_report.py), e contar o
    resto como erro misturaria "errou" com "o mir_eval não sabe julgar".
    """
    vazio = {f"{n}_rotulado": "" for n in LEVELS}
    if not est or not ref:
        return vazio
    try:
        import mir_eval
        duracoes, ref_lab, est_lab, est_n = _grade_comum(est, ref)
        saida = {}
        for nivel in LEVELS:
            comparacoes = np.asarray(
                getattr(mir_eval.chord, nivel)(ref_lab, est_lab), dtype=float)
            valido = (comparacoes >= 0) & ~est_n
            peso = float(duracoes[valido].sum())
            saida[f"{nivel}_rotulado"] = (
                round(float((comparacoes[valido] * duracoes[valido]).sum()) / peso, 9)
                if peso > 0 else "")
        return saida
    except Exception:
        return vazio


def diagnostico(est, ref):
    """
    Onde o erro está, medido na MESMA grade temporal que o mir_eval usa: o
    estimado é alinhado ao intervalo da referência e os dois são fundidos numa
    grade comum, exatamente como `mir_eval.chord.evaluate` faz.

    Devolve frações do tempo total:
      frac_n_est                    : estimado como 'sem acorde'
      frac_tonica_ok_qualidade_erro : tônica certa, qualidade errada
      frac_tonica_erro              : tônica errada (inclui estimar N onde há
                                      acorde -- N não tem tônica)
    """
    import mir_eval

    vazio = {c: "" for c in ("frac_n_est", "frac_tonica_ok_qualidade_erro",
                             "frac_tonica_erro")}
    if not est or not ref:
        return vazio
    try:
        duracoes, ref_lab, est_lab, est_n = _grade_comum(est, ref)
        total = float(duracoes.sum())
        if total <= 0:
            return vazio

        ref_roots, ref_semis = mir_eval.chord.encode_many(ref_lab, True)[:2]
        est_roots, est_semis = mir_eval.chord.encode_many(est_lab, True)[:2]

        tonica_ok = ref_roots == est_roots
        qualidade_ok = (ref_semis == est_semis).all(axis=1)

        return {
            "frac_n_est": round(float(duracoes[est_n].sum()) / total, 6),
            "frac_tonica_ok_qualidade_erro": round(
                float(duracoes[tonica_ok & ~qualidade_ok].sum()) / total, 6),
            "frac_tonica_erro": round(
                float(duracoes[~tonica_ok].sum()) / total, 6),
        }
    except Exception:
        return vazio


# ==========================================================================
# Execução
# ==========================================================================
def _linhas(manifest, splits):
    with Path(manifest).open(encoding="utf-8", newline="") as fp:
        linhas = [r for r in csv.DictReader(fp)
                  if (r.get("excluded") or "false").strip().lower() != "true"]
    return [r for r in linhas if r.get("split") in splits]


def _duracao(segmentos):
    return float(segmentos[-1][1] - segmentos[0][0]) if segmentos else 0.0


def _linha_csv(variante, row, ref, est, dur_ref, ref_camada):
    # uma única chamada: o mir_eval devolve níveis e segmentação juntos
    scores = score_segments(est, ref, levels=LEVELS + SEG_FIELDS,
                            ref_is_harte=True)
    saida = {
        "variante": variante.nome,
        "track_id": row.get("track_id", ""),
        "split": row.get("split", ""),
        "ref_camada": f"chord[{ref_camada}]",
        "motor": variante.motor,
        "vocabulario": variante.vocab,
        "duracao_s": round(dur_ref, 3),
    }
    campos_pre = asdict(variante.pre) if variante.pre else {}
    campos_post = asdict(variante.post) if variante.post else {}
    for nome in PreChromaConfig.__dataclass_fields__:
        saida[nome] = campos_pre.get(nome, "")
    for nome in PostChromaConfig.__dataclass_fields__:
        saida[nome] = campos_post.get(nome, "")
    for nivel in LEVELS + SEG_FIELDS:
        saida[nivel] = round(scores[nivel], 9)
    saida.update(acerto_no_tempo_rotulado(est, ref))
    saida.update(diagnostico(est, ref))
    saida["n_segmentos_est"] = len(est)
    saida["n_segmentos_ref"] = len(ref)
    return saida


LEVELS_ROTULADO = [f"{n}_rotulado" for n in LEVELS]

CSV_FIELDS = (["variante", "track_id", "split", "ref_camada", "motor",
               "vocabulario", "duracao_s"]
              + list(PreChromaConfig.__dataclass_fields__)
              + list(PostChromaConfig.__dataclass_fields__)
              + LEVELS + LEVELS_ROTULADO + DIAG_FIELDS + SEG_FIELDS)


def rodar(manifest, splits, nomes_variantes, ref_camada=REF_CAMADA,
          verbose=True):
    """
    Roda a matriz. Devolve (linhas, falhas). Uma faixa que quebra é registrada
    e o lote segue.
    """
    linhas_manifest = _linhas(manifest, splits)
    if not linhas_manifest:
        raise SystemExit(f"nenhuma faixa em {manifest} com split em {sorted(splits)}")

    resultados, falhas = [], []
    total = len(linhas_manifest)

    # Referências: lidas uma vez por faixa, reusadas por todas as variantes.
    refs, duracoes = {}, {}
    for row in linhas_manifest:
        tid = row["track_id"]
        try:
            refs[tid] = ds.load_guitarset(ROOT / row["annotation_path"],
                                          index=ref_camada)
            duracoes[tid] = _duracao(refs[tid])
        except Exception as exc:
            falhas.append((f"ref/{tid}", f"{type(exc).__name__}: {exc}"))

    for nome in nomes_variantes:
        variante = VARIANTES[nome]
        t0 = time.perf_counter()
        for i, row in enumerate(linhas_manifest, start=1):
            tid = row["track_id"]
            if tid not in refs:
                continue
            try:
                audio = ROOT / row["audio_path"]
                if variante.motor == "v4":
                    import librosa
                    y, sr = librosa.load(audio, sr=PRE_CHROMA.sr, mono=True)
                    est = estimar_v4(y, sr)
                elif variante.motor == "v4b":
                    import librosa
                    y, sr = librosa.load(audio, sr=PRE_CHROMA.sr, mono=True)
                    est = estimar_v4b(y, sr)
                else:
                    features = cache.get_features(audio, variante.pre)
                    est = estimar(variante, features)
                resultados.append(_linha_csv(variante, row, refs[tid], est,
                                             duracoes[tid], ref_camada))
            except Exception as exc:
                falhas.append((f"{nome}/{tid}", f"{type(exc).__name__}: {exc}"))
            if verbose:
                sys.stdout.write(f"\r  {nome}: {i}/{total}")
                sys.stdout.flush()
        if verbose:
            print(f"   ({time.perf_counter() - t0:.0f}s)")

    return resultados, falhas


# ==========================================================================
# Saída
# ==========================================================================
def _commit():
    """Commit atual e se a árvore está suja -- sem isso o CSV não é rastreável."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=30).stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"),
                "arvore_suja": bool(git("status", "--porcelain"))}
    except Exception as exc:
        return {"commit": None, "arvore_suja": None, "erro": str(exc)}


def _meta(manifest, splits, nomes, ref_camada, n_linhas, falhas, segundos):
    import librosa
    import mir_eval
    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(manifest),
        "splits": sorted(splits),
        "variantes": list(nomes),
        "ref_camada": f"chord[{ref_camada}]",
        "ref_is_harte": True,
        "n_linhas": n_linhas,
        "falhas": [{"onde": o, "erro": e} for o, e in falhas],
        "segundos": round(segundos, 1),
        "versoes": {
            "python": sys.version.split()[0],
            "implementacao": platform.python_implementation(),
            "numpy": np.__version__,
            "librosa": librosa.__version__,
            "mir_eval": mir_eval.__version__,
        },
        "projeto": _commit(),
        "config_base": {"pre": asdict(PRE_CHROMA), "post": asdict(POST_CHROMA)},
    }


def escrever(resultados, meta, timestamp, sufixo=""):
    RESULTS.mkdir(parents=True, exist_ok=True)
    base = f"ablation_{timestamp}{sufixo}"
    csv_path = RESULTS / f"{base}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(resultados)
    meta_path = RESULTS / f"{base}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return csv_path, meta_path


def _media_ponderada(linhas, coluna):
    pares = [(float(l[coluna]), l["duracao_s"]) for l in linhas
             if l[coluna] != ""]
    peso = sum(d for _, d in pares)
    return sum(v * d for v, d in pares) / peso if peso else float("nan")


def resumir(resultados, nomes, ref_camada):
    """
    Duas tabelas: a métrica normal (sobre a faixa toda) e o acerto no tempo
    rotulado (excluindo o que o sistema devolveu como N). A comparação entre
    as duas é o que separa "rotular mais tempo" de "rotular melhor".
    """
    tabela = {}
    for nome in nomes:
        linhas = [l for l in resultados if l["variante"] == nome]
        if not linhas:
            continue
        tabela[nome] = {
            **{c: _media_ponderada(linhas, c) for c in LEVELS},
            **{c: _media_ponderada(linhas, c) for c in LEVELS_ROTULADO},
            **{c: _media_ponderada(linhas, c) for c in
               ("frac_n_est", "frac_tonica_ok_qualidade_erro",
                "frac_tonica_erro")},
            **{c: _media_ponderada(linhas, c) for c in SEG_FIELDS},
            "seg_est": sum(l["n_segmentos_est"] for l in linhas) / len(linhas),
            "seg_ref": sum(l["n_segmentos_ref"] for l in linhas) / len(linhas),
        }

    print("\n" + "=" * 104)
    print(f"1. Média ponderada por duração, faixa TODA (%) — "
          f"referência chord[{ref_camada}]")
    print("=" * 104)
    cab = (f"{'variante':<9} | " + " | ".join(f"{n:>8}" for n in LEVELS)
           + f" | {'N est':>7} | {'ton.ok/qual.err':>15} | {'ton.err':>7}"
             f" | {'seg.est':>7} | {'seg.ref':>7}")
    print(cab)
    print("-" * len(cab))
    for nome, t in tabela.items():
        print(f"{nome:<9} | "
              + " | ".join(f"{t[n]*100:7.2f}%" for n in LEVELS)
              + f" | {t['frac_n_est']*100:6.2f}%"
              + f" | {t['frac_tonica_ok_qualidade_erro']*100:14.2f}%"
              + f" | {t['frac_tonica_erro']*100:6.2f}%"
              + f" | {t['seg_est']:7.1f} | {t['seg_ref']:7.1f}")

    print("\n" + "=" * 104)
    print("2. Acerto só no TEMPO ROTULADO (%) — exclui o tempo devolvido "
          "como N")
    print("=" * 104)
    cab2 = (f"{'variante':<9} | " + " | ".join(f"{n:>8}" for n in LEVELS)
            + f" | {'N est':>7} | {'Δ root':>8}")
    print(cab2)
    print("-" * len(cab2))
    for nome, t in tabela.items():
        delta = t["root_rotulado"] - t["root"]
        print(f"{nome:<9} | "
              + " | ".join(f"{t[f'{n}_rotulado']*100:7.2f}%" for n in LEVELS)
              + f" | {t['frac_n_est']*100:6.2f}%"
              + f" | {delta*100:+7.2f}")

    print("\n" + "=" * 62)
    print("3. Segmentação do mir_eval (1 = fronteiras perfeitas)")
    print("=" * 62)
    cab3 = (f"{'variante':<9} | {'overseg':>9} | {'underseg':>9} | {'seg':>9}"
            f" | {'seg.est':>7}")
    print(cab3)
    print("-" * len(cab3))
    for nome, t in tabela.items():
        print(f"{nome:<9} | {t['overseg']*100:8.2f}% | "
              f"{t['underseg']*100:8.2f}% | {t['seg']*100:8.2f}% | "
              f"{t['seg_est']:7.1f}")
    return tabela


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Roda a matriz de ablação sobre um manifest.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--splits", default="val",
                    help="lista separada por vírgula (default: val). "
                         "'test' precisa ser pedido explicitamente.")
    originais = [n for n in VARIANTES if n not in VARIANTES_POS_REVISAO]
    ap.add_argument("--variants", default=",".join(originais),
                    help=f"default: as pré-revisão ({','.join(originais)})")
    ap.add_argument("--ref-layer", type=int, default=REF_CAMADA,
                    choices=(0, 1),
                    help="camada de acorde do GuitarSet: 0 = lead sheet "
                         "instruído (default), 1 = performed/inferred")
    ap.add_argument("--post-review", action="store_true",
                    help="marca o meta.json com post_review=true (análises "
                         "da revisão do camera-ready)")
    args = ap.parse_args(argv)

    splits = {s.strip() for s in args.splits.split(",") if s.strip()}
    nomes = [n.strip() for n in args.variants.split(",") if n.strip()]

    desconhecidas = [n for n in nomes if n not in VARIANTES]
    if desconhecidas:
        raise SystemExit(f"variante desconhecida: {desconhecidas} "
                         f"(conhecidas: {list(VARIANTES)})")
    if any(n in VARIANTES_POS_REVISAO for n in nomes) and not args.post_review:
        raise SystemExit("variantes pós-revisão exigem --post-review")

    protegidos = splits & SPLITS_PROTEGIDOS
    if protegidos and "--splits" not in (argv if argv is not None else sys.argv):
        raise SystemExit(f"split protegido {sorted(protegidos)} exige --splits "
                         f"explícito")

    print(f"manifest {args.manifest} | splits {sorted(splits)} | "
          f"variantes {nomes} | referência chord[{args.ref_layer}]")
    if protegidos:
        print(f"  ATENÇÃO: rodando split(s) {sorted(protegidos)} -- "
              f"o conjunto de teste deve ser lido uma única vez.")

    t0 = time.perf_counter()
    resultados, falhas = rodar(args.manifest, splits, nomes, args.ref_layer)
    segundos = time.perf_counter() - t0

    resumir(resultados, nomes, args.ref_layer)
    meta = _meta(args.manifest, splits, nomes, args.ref_layer, len(resultados),
                 falhas, segundos)
    if args.post_review:
        meta["post_review"] = True
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path, meta_path = escrever(resultados, meta, timestamp,
                                   sufixo=f"_ref{args.ref_layer}")

    print(f"\nfalhas: {len(falhas)}")
    for onde, erro in falhas[:10]:
        print(f"  {onde}: {erro}")
    print(f"tempo total: {segundos:.0f}s")
    print(f"escrito {csv_path.relative_to(ROOT).as_posix()} "
          f"({len(resultados)} linhas)")
    print(f"escrito {meta_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
