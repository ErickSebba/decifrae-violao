"""
mascara_comum.py
================
Compara C e D sobre a MESMA porção de tempo, em vez de sobre a faixa toda.

O problema que motiva o script: C devolve `N` em ~43 % do tempo e D em ~23 %.
Comparar as duas na métrica usual soma dois efeitos — quem rotula melhor e quem
rotula mais tempo. As colunas de acerto no tempo rotulado separam parte disso,
mas cada variante tem o SEU tempo rotulado, então os dois números continuam
medidos em domínios diferentes.

Aqui as duas são pontuadas sobre a mesma máscara:

    M_C  : as células em que C não estimou `N`
           (o domínio de C; mede se D acerta mais onde C se arrisca)
    M_CD : as células em que NENHUM dos dois estimou `N`
           (a interseção; o único domínio em que as duas se comprometeram)

Em cada máscara, a acurácia é a média ponderada por duração das comparações do
mir_eval no nível `root`, restrita às células da máscara e às comparáveis
(`comparação >= 0`) — a mesma conta do `weighted_accuracy`, com o domínio
trocado. Δ = D − C, com bootstrap pareado por faixa (10 000 reamostragens,
semente 0, IC 95 %), idêntico ao de `stats.py`.

As saídas decodificam a partir do cache de `Features`: nenhuma extração de
chroma é refeita.

STATUS DA ANÁLISE. Na validação é exploratória. No conjunto de teste é
**pós-especificada (post hoc)**: não consta dos pares pré-registrados do §5 do
congelamento, foi concebida depois de ler o teste, e está marcada como tal no
CSV (coluna `status`) e no meta.json. Não substitui nem reinterpreta nenhuma
comparação pré-registrada.

Saída: data/results/mascara_comum_<timestamp>.csv + _meta.json

    python mascara_comum.py
"""

import argparse
import csv
import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import mir_eval  # noqa: E402

import cache  # noqa: E402
import dataset_io as ds  # noqa: E402
import runner  # noqa: E402
from evaluate import _to_arrays  # noqa: E402

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

NIVEL = "root"
REF_CAMADA = 0
VARIANTE_A, VARIANTE_B = "C", "D"
MASCARAS = ("M_C", "M_CD")

CSV_FIELDS = ["split", "status", "ref_camada", "nivel", "mascara",
              "variante_a", "variante_b", "n_faixas",
              "acerto_a", "acerto_b", "diferenca", "ic95_min", "ic95_max",
              "ic_cruza_zero", "p_bootstrap", "frac_tempo_na_mascara",
              "b_melhor", "b_pior", "empate"]


# ==========================================================================
# Uma faixa
# ==========================================================================
def _grade(est_a, est_b, ref):
    """
    Alinha as duas estimativas e a referência na MESMA grade temporal.

    Funde os três conjuntos de fronteiras de uma vez: primeiro ref+A, depois o
    resultado com B. Sem isso, as duas variantes seriam avaliadas em grades
    diferentes e as máscaras não seriam comparáveis célula a célula.
    """
    ref_int, ref_lab = _to_arrays(ref, translate=False)
    lo, hi = ref_int.min(), ref_int.max()

    def alinhar(est):
        i, l = _to_arrays(est)
        return mir_eval.util.adjust_intervals(
            i, l, lo, hi, mir_eval.chord.NO_CHORD, mir_eval.chord.NO_CHORD)

    a_int, a_lab = alinhar(est_a)
    b_int, b_lab = alinhar(est_b)

    inter, ref_l, a_l = mir_eval.util.merge_labeled_intervals(
        ref_int, ref_lab, a_int, a_lab)
    inter2, pares, b_l = mir_eval.util.merge_labeled_intervals(
        inter, list(zip(ref_l, a_l)), b_int, b_lab)
    ref_l = [p[0] for p in pares]
    a_l = [p[1] for p in pares]
    duracoes = mir_eval.util.intervals_to_durations(inter2)
    return duracoes, ref_l, a_l, b_l


def _e_n(labels):
    """Máscara de 'sem acorde', pela convenção do mir_eval."""
    roots, semis = mir_eval.chord.encode_many(labels, True)[:2]
    return (roots == -1) & ~semis.any(axis=1)


def medir_faixa(est_a, est_b, ref):
    """
    Devolve {mascara: (peso_a_certo, peso_b_certo, peso_total)} para a faixa.

    O peso é duração; 'certo' usa a comparação do mir_eval no nível, e só as
    células comparáveis (>= 0) entram no total.
    """
    duracoes, ref_l, a_l, b_l = _grade(est_a, est_b, ref)
    comp_a = np.asarray(getattr(mir_eval.chord, NIVEL)(ref_l, a_l), dtype=float)
    comp_b = np.asarray(getattr(mir_eval.chord, NIVEL)(ref_l, b_l), dtype=float)
    valido = (comp_a >= 0) & (comp_b >= 0)

    n_a, n_b = _e_n(a_l), _e_n(b_l)
    saida = {}
    for nome, mask in (("M_C", ~n_a), ("M_CD", ~n_a & ~n_b)):
        m = mask & valido
        peso = float(duracoes[m].sum())
        saida[nome] = (float((comp_a[m] * duracoes[m]).sum()),
                       float((comp_b[m] * duracoes[m]).sum()),
                       peso, float(duracoes[valido].sum()))
    return saida


# ==========================================================================
# Agregação
# ==========================================================================
def _bootstrap(d, w):
    lo, hi, p = None, None, None
    from stats import bootstrap
    return bootstrap(d, w)


def agregar(por_faixa, mascara):
    """
    Junta as faixas e devolve a linha do CSV para uma máscara.

    A acurácia de cada faixa é a razão dentro da máscara; o peso da faixa no
    bootstrap é o tempo que ela contribui PARA A MÁSCARA, não a duração total
    -- uma faixa em que C rotulou 5 % do tempo não deve pesar como uma em que
    rotulou 90 %.
    """
    acc_a, acc_b, pesos, fracoes = [], [], [], []
    for valores in por_faixa.values():
        soma_a, soma_b, peso, total = valores[mascara]
        if peso <= 0:
            continue
        acc_a.append(soma_a / peso)
        acc_b.append(soma_b / peso)
        pesos.append(peso)
        fracoes.append(peso / total if total > 0 else 0.0)

    a = np.array(acc_a); b = np.array(acc_b); w = np.array(pesos)
    d = b - a
    lo, hi, p = _bootstrap(d, w)
    tol = 1e-12
    return {
        "nivel": NIVEL,
        "mascara": mascara,
        "variante_a": VARIANTE_A,
        "variante_b": VARIANTE_B,
        "n_faixas": len(d),
        "acerto_a": round(float(np.sum(a * w) / np.sum(w)), 9),
        "acerto_b": round(float(np.sum(b * w) / np.sum(w)), 9),
        "diferenca": round(float(np.sum(d * w) / np.sum(w)), 9),
        "ic95_min": round(lo, 9),
        "ic95_max": round(hi, 9),
        "ic_cruza_zero": "sim" if lo <= 0 <= hi else "nao",
        "p_bootstrap": f"{p:.6g}",
        "frac_tempo_na_mascara": round(float(np.mean(fracoes)), 6),
        "b_melhor": int(np.sum(d > tol)),
        "b_pior": int(np.sum(d < -tol)),
        "empate": int(np.sum(np.abs(d) <= tol)),
    }


# ==========================================================================
# Execução
# ==========================================================================
def rodar(manifest, split, verbose=True):
    linhas_manifest = runner._linhas(manifest, {split})
    if not linhas_manifest:
        raise SystemExit(f"nenhuma faixa com split={split} em {manifest}")

    va, vb = runner.VARIANTES[VARIANTE_A], runner.VARIANTES[VARIANTE_B]
    por_faixa, falhas = {}, []
    for i, row in enumerate(linhas_manifest, start=1):
        tid = row["track_id"]
        try:
            ref = ds.load_guitarset(ROOT / row["annotation_path"],
                                    index=REF_CAMADA)
            audio = ROOT / row["audio_path"]
            # decodifica a partir do cache: nenhuma extração é refeita
            est_a = runner.estimar(va, cache.get_features(audio, va.pre))
            est_b = runner.estimar(vb, cache.get_features(audio, vb.pre))
            por_faixa[tid] = medir_faixa(est_a, est_b, ref)
        except Exception as exc:
            falhas.append((tid, f"{type(exc).__name__}: {exc}"))
        if verbose:
            sys.stdout.write(f"\r  {split}: {i}/{len(linhas_manifest)}")
            sys.stdout.flush()
    if verbose:
        print()
    return por_faixa, falhas


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="C vs D sobre a mesma máscara de tempo rotulado.")
    ap.add_argument("--manifest",
                    default="data/manifests/guitarset_comping.csv")
    ap.add_argument("--splits", default="val,test",
                    help="default: val,test (o teste é análise post hoc)")
    args = ap.parse_args(argv)

    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    manifest = ROOT / args.manifest

    t0 = time.perf_counter()
    linhas, todas_falhas = [], []
    for split in splits:
        status = "post_hoc" if split == "test" else "exploratoria"
        por_faixa, falhas = rodar(manifest, split)
        todas_falhas.extend((f"{split}/{t}", e) for t, e in falhas)
        for mascara in MASCARAS:
            linha = agregar(por_faixa, mascara)
            linha.update({"split": split, "status": status,
                          "ref_camada": f"chord[{REF_CAMADA}]"})
            linhas.append(linha)
    segundos = time.perf_counter() - t0

    print("\n" + "=" * 96)
    print(f"C vs D sobre a mesma máscara — nível {NIVEL}, "
          f"chord[{REF_CAMADA}]. Δ = D − C")
    print("=" * 96)
    cab = (f"{'split':<6} | {'status':<13} | {'máscara':<6} | {'C':>7} | "
           f"{'D':>7} | {'Δ':>6} | {'IC 95 %':>17} | {'tempo':>6} | "
           f"{'D+/D−/=':>10}")
    print(cab)
    print("-" * len(cab))
    for l in linhas:
        ic = f"[{l['ic95_min']*100:+.2f}, {l['ic95_max']*100:+.2f}]"
        print(f"{l['split']:<6} | {l['status']:<13} | {l['mascara']:<6} | "
              f"{l['acerto_a']*100:6.2f}% | {l['acerto_b']*100:6.2f}% | "
              f"{l['diferenca']*100:+5.2f} | {ic:>17} | "
              f"{l['frac_tempo_na_mascara']*100:5.1f}% | "
              f"{l['b_melhor']:>3}/{l['b_pior']:>3}/{l['empate']:>3}")
    print("-" * len(cab))
    print("'tempo' = fração média do tempo comparável da faixa que a máscara "
          "cobre.")
    print("O teste é PÓS-ESPECIFICADO: não consta dos pares pré-registrados "
          "do congelamento.")

    RESULTS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS / f"mascara_comum_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(linhas)

    import librosa
    import scipy
    from stats import N_BOOTSTRAP, SEED, ALFA
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "manifest": args.manifest,
        "splits": splits,
        "status": {"val": "exploratoria", "test": "post_hoc"},
        "aviso": "A análise sobre o split test é PÓS-ESPECIFICADA (post hoc): "
                 "não consta dos pares pré-registrados do §5 de "
                 "docs/CONGELAMENTO.md e foi concebida depois da leitura do "
                 "teste. Não substitui nem reinterpreta comparação "
                 "pré-registrada.",
        "ref_camada": f"chord[{REF_CAMADA}]",
        "nivel": NIVEL,
        "variantes": [VARIANTE_A, VARIANTE_B],
        "mascaras": {
            "M_C": "células em que C não estimou N",
            "M_CD": "células em que nenhum dos dois estimou N",
        },
        "peso_da_faixa": "tempo que a faixa contribui para a máscara",
        "n_bootstrap": N_BOOTSTRAP, "seed": SEED, "alfa": ALFA,
        "features": "decodificadas do cache; nenhuma extração de chroma refeita",
        "n_linhas": len(linhas),
        "falhas": [{"onde": o, "erro": e} for o, e in todas_falhas],
        "segundos": round(segundos, 1),
        "versoes": {"python": sys.version.split()[0], "numpy": np.__version__,
                    "scipy": scipy.__version__, "librosa": librosa.__version__,
                    "mir_eval": mir_eval.__version__},
        "projeto": runner._commit(),
    }
    meta_path = RESULTS / f"mascara_comum_{timestamp}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    print(f"\nfalhas: {len(todas_falhas)}")
    print(f"tempo: {segundos:.0f}s")
    print(f"escrito {csv_path.relative_to(ROOT).as_posix()}")
    print(f"escrito {meta_path.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
