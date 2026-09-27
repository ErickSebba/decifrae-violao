"""
stats.py
========
Comparações pareadas entre variantes, sobre as notas POR FAIXA do split de
validação.

Até aqui a ablação comparava médias ponderadas. Uma diferença de 1,6 ponto
entre D e E pode ser real ou pode ser ruído de 120 faixas -- a média sozinha
não distingue. Este script responde três perguntas por par:

  1. Qual é a diferença média ponderada por duração? (o efeito)
  2. Qual é o intervalo de 95 % dessa diferença? (bootstrap pareado, 10 000
     reamostragens de FAIXAS -- reamostrar faixas, e não segmentos, porque a
     faixa é a unidade independente: dois segmentos da mesma execução do
     mesmo músico não são observações independentes)
  3. A diferença é consistente faixa a faixa? (Wilcoxon pareado, que só olha
     o sinal e a ordem das diferenças -- não a magnitude)

As três respondem coisas diferentes e podem discordar. Um efeito médio grande
com IC cruzando zero significa "poucas faixas dominam o resultado". Um efeito
médio pequeno com Wilcoxon muito significativo significa "quase toda faixa
melhora, mas pouco". Ambos os casos aparecem nos pares abaixo.

Os pares são PRÉ-REGISTRADOS em `docs/CONGELAMENTO.md`: cada um existe para
isolar uma etapa, e as métricas de cada um foram escolhidas antes de olhar os
p-valores. Rodar aqui, na validação, é o ensaio; o teste roda os mesmos pares
uma única vez.

Entrada: o CSV de ablação mais recente do chord[0] (uma linha por variante e
faixa). Saída: data/results/stats_val_<timestamp>.csv + _meta.json

    python stats.py
    python stats.py --csv data/results/ablation_<ts>_ref0.csv
"""

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy import stats as sps

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"

N_BOOTSTRAP = 10_000
SEED = 0
ALFA = 0.05

# (variante_a, variante_b, [métricas], o que o par isola)
# A diferença reportada é sempre b - a: positivo = b melhor.
PARES = [
    ("C", "D", ["root", "root_rotulado"],
     "o Viterbi na métrica usual"),
    ("C0rg", "D0rg", ["root", "majmin"],
     "o Viterbi com cobertura igualada (nenhuma fonte de N)"),
    ("D", "E", ["root", "seg", "overseg"],
     "o trade-off do min_dur: acurácia contra segmentação"),
    ("V4b", "V4", ["root", "overseg"],
     "a inércia temporal do baseline"),
    ("V4", "F0rg", ["root", "majmin", "seg"],
     "baseline contra a melhor variante"),
    ("D0rg", "F0rg", ["root", "majmin", "sevenths"],
     "o vocabulário (MEDIUM vs BASIC) com cobertura igualada"),
]

CSV_FIELDS = ["par", "variante_a", "variante_b", "metrica", "isola",
              "n_faixas", "n_descartadas",
              "media_a", "media_b", "diferenca", "ic95_min", "ic95_max",
              "ic_cruza_zero", "wilcoxon_estatistica", "wilcoxon_p",
              "b_melhor", "b_pior", "empate", "mediana_diferenca"]


# ==========================================================================
# Leitura
# ==========================================================================
def _csv_mais_recente():
    candidatos = sorted(RESULTS.glob("ablation_*_ref0.csv"))
    if not candidatos:
        raise SystemExit("nenhum ablation_*_ref0.csv em data/results/ -- "
                         "rode `python runner.py --manifest ... --ref-layer 0`")
    return candidatos[-1]


def carregar(csv_path):
    """{variante: {track_id: linha}} e a duração de cada faixa."""
    with Path(csv_path).open(encoding="utf-8", newline="") as fp:
        linhas = list(csv.DictReader(fp))
    por_variante = defaultdict(dict)
    duracoes = {}
    for l in linhas:
        por_variante[l["variante"]][l["track_id"]] = l
        duracoes[l["track_id"]] = float(l["duracao_s"])
    return por_variante, duracoes


def _pares_alinhados(por_variante, duracoes, a, b, metrica):
    """
    Arrays alinhados por faixa: (valores_a, valores_b, pesos, n_descartadas).

    Descarta a faixa quando a métrica está vazia em qualquer dos dois lados --
    é o que acontece com `*_rotulado` quando a cobertura é zero. Devolver zero
    no lugar inventaria um dado.
    """
    faltando = [v for v in (a, b) if v not in por_variante]
    if faltando:
        raise KeyError(f"variante(s) ausente(s) no CSV: {faltando}")

    comuns = sorted(set(por_variante[a]) & set(por_variante[b]))
    va, vb, w = [], [], []
    descartadas = 0
    for tid in comuns:
        xa = por_variante[a][tid][metrica]
        xb = por_variante[b][tid][metrica]
        if xa == "" or xb == "":
            descartadas += 1
            continue
        va.append(float(xa))
        vb.append(float(xb))
        w.append(duracoes[tid])
    return (np.array(va), np.array(vb), np.array(w), descartadas)


# ==========================================================================
# Estatística
# ==========================================================================
def _media_ponderada(x, w):
    return float(np.sum(x * w) / np.sum(w)) if np.sum(w) > 0 else float("nan")


def bootstrap_ic(d, w, n=N_BOOTSTRAP, seed=SEED, alfa=ALFA):
    """
    IC da diferença média ponderada, por reamostragem PAREADA de faixas.

    Cada reamostragem sorteia faixas com reposição e recalcula a média
    ponderada das diferenças -- o par (d_i, w_i) viaja junto, que é o que
    torna o teste pareado. Semente própria por comparação, para que rodar um
    par isolado dê o mesmo número.
    """
    if len(d) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    pesos = w[idx]
    medias = np.sum(d[idx] * pesos, axis=1) / np.sum(pesos, axis=1)
    lo, hi = np.percentile(medias, [100 * alfa / 2, 100 * (1 - alfa / 2)])
    return float(lo), float(hi)


def wilcoxon(d):
    """
    Wilcoxon pareado sobre as diferenças por faixa. Não é ponderado: o teste
    é de ranks, e ponderar rank por duração não tem interpretação.

    Devolve (estatística, p) ou (nan, nan) quando não há diferença nenhuma --
    caso em que o scipy levanta, e reportar p=1 seria inventar.
    """
    if len(d) == 0 or np.allclose(d, 0):
        return float("nan"), float("nan")
    try:
        res = sps.wilcoxon(d, zero_method="wilcox", alternative="two-sided")
        return float(res.statistic), float(res.pvalue)
    except ValueError:
        return float("nan"), float("nan")


def comparar(por_variante, duracoes, a, b, metrica, isola):
    va, vb, w, descartadas = _pares_alinhados(por_variante, duracoes, a, b,
                                              metrica)
    d = vb - va
    media_a = _media_ponderada(va, w)
    media_b = _media_ponderada(vb, w)
    diferenca = _media_ponderada(d, w)
    lo, hi = bootstrap_ic(d, w)
    est, p = wilcoxon(d)
    tol = 1e-12
    return {
        "par": f"{a} vs {b}",
        "variante_a": a,
        "variante_b": b,
        "metrica": metrica,
        "isola": isola,
        "n_faixas": len(d),
        "n_descartadas": descartadas,
        "media_a": round(media_a, 9),
        "media_b": round(media_b, 9),
        "diferenca": round(diferenca, 9),
        "ic95_min": round(lo, 9),
        "ic95_max": round(hi, 9),
        "ic_cruza_zero": "sim" if (lo <= 0 <= hi) else "nao",
        "wilcoxon_estatistica": round(est, 6) if est == est else "",
        "wilcoxon_p": f"{p:.6g}" if p == p else "",
        "b_melhor": int(np.sum(d > tol)),
        "b_pior": int(np.sum(d < -tol)),
        "empate": int(np.sum(np.abs(d) <= tol)),
        "mediana_diferenca": round(float(np.median(d)), 9) if len(d) else "",
    }


def rodar(csv_path):
    por_variante, duracoes = carregar(csv_path)
    linhas, avisos = [], []
    for a, b, metricas, isola in PARES:
        for metrica in metricas:
            try:
                linhas.append(comparar(por_variante, duracoes, a, b, metrica,
                                       isola))
            except KeyError as exc:
                avisos.append(f"{a} vs {b} / {metrica}: {exc}")
    return linhas, avisos


# ==========================================================================
# Saída
# ==========================================================================
def imprimir(linhas):
    print("=" * 118)
    print("Comparações pareadas — split val, chord[0]. Diferença = b − a "
          "(positivo: b melhor)")
    print("=" * 118)
    cab = (f"{'par':<14} | {'métrica':<14} | {'a':>7} | {'b':>7} | "
           f"{'dif':>7} | {'IC 95 %':>16} | {'p (Wilc.)':>10} | "
           f"{'b+/b−/=':>12}")
    print(cab)
    print("-" * len(cab))
    par_anterior = None
    for l in linhas:
        if par_anterior is not None and l["par"] != par_anterior:
            print("-" * len(cab))
        par_anterior = l["par"]
        ic = f"[{l['ic95_min']*100:+.2f}, {l['ic95_max']*100:+.2f}]"
        marca = " " if l["ic_cruza_zero"] == "nao" else "*"
        print(f"{l['par']:<14} | {l['metrica']:<14} | "
              f"{l['media_a']*100:6.2f}% | {l['media_b']*100:6.2f}% | "
              f"{l['diferenca']*100:+6.2f} | {ic:>15}{marca} | "
              f"{str(l['wilcoxon_p']):>10} | "
              f"{l['b_melhor']:>3}/{l['b_pior']:>3}/{l['empate']:>3}")
    print("-" * len(cab))
    print("* IC 95 % cruza zero: a diferença não é distinguível de ruído "
          "com 120 faixas.")


def escrever(linhas, meta, timestamp):
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / f"stats_val_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(linhas)
    meta_path = RESULTS / f"stats_val_{timestamp}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    return csv_path, meta_path


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Comparações pareadas entre variantes no split val.")
    ap.add_argument("--csv", default=None,
                    help="default: o ablation_*_ref0.csv mais recente")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv) if args.csv else _csv_mais_recente()
    print(f"lendo {csv_path.relative_to(ROOT).as_posix()}")

    t0 = time.perf_counter()
    linhas, avisos = rodar(csv_path)
    segundos = time.perf_counter() - t0

    imprimir(linhas)
    for aviso in avisos:
        print(f"AVISO: {aviso}")

    import runner
    import scipy
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "entrada": csv_path.name,
        "split": "val",
        "ref_camada": "chord[0]",
        "n_bootstrap": N_BOOTSTRAP,
        "seed": SEED,
        "alfa": ALFA,
        "unidade_de_reamostragem": "faixa",
        "wilcoxon": "scipy.stats.wilcoxon, two-sided, zero_method=wilcox",
        "pares": [{"a": a, "b": b, "metricas": m, "isola": i}
                  for a, b, m, i in PARES],
        "n_comparacoes": len(linhas),
        "avisos": avisos,
        "segundos": round(segundos, 1),
        "versoes": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "projeto": runner._commit(),
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_out, meta_out = escrever(linhas, meta, timestamp)
    print(f"\ntempo: {segundos:.1f}s")
    print(f"escrito {csv_out.relative_to(ROOT).as_posix()} "
          f"({len(linhas)} comparações)")
    print(f"escrito {meta_out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
