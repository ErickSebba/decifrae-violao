"""
coverage_report.py
==================
Quanto de cada dataset é COMPARÁVEL em cada nível do mir_eval.

NOME DO ARQUIVO: não renomear para `coverage.py`. Os módulos deste projeto são
planos na raiz e a raiz entra no sys.path, então um `coverage.py` aqui
sequestra o pacote `coverage` que o numba importa
(`numba/misc/coverage_support.py`), e com ele quebram numba, librosa e a suíte
inteira.

Nenhum pipeline roda aqui. O script só olha as anotações de referência e
responde: se pontuarmos neste nível, que fração do tempo anotado o mir_eval de
fato pondera, e que fração ele joga fora?

Isso importa porque o mir_eval não erra alto quando a referência sai do
vocabulário do nível: ele DESCARTA aquele trecho da ponderação. Um `majmin`
de 0,90 sobre 40 % do tempo não é a mesma afirmação que 0,90 sobre 95 %, e a
diferença não aparece na métrica -- só aqui.

A decisão de comparabilidade não é uma lista escrita à mão: é a própria função
do mir_eval que `evaluate.score_segments` usa em cada nível
(`mir_eval.chord.root/majmin/sevenths/mirex`), chamada com a referência contra
ela mesma. Essas funções marcam com -1 o que será ignorado, e o -1 depende só
do rótulo de referência -- então o estimado pode ser qualquer um.

Camadas medidas:
  guitarset/chord[0]  lead sheet instruído
  guitarset/chord[1]  performed/inferred (a referência do benchmark)
  idmt/lab            guitar_annotation.lab

Saída: data/results/coverage.csv (uma linha por dataset × camada × nível) e um
resumo no terminal.

    python coverage_report.py
"""

import csv
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import mir_eval  # noqa: E402

import dataset_io as ds  # noqa: E402

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "data" / "results"
OUT_CSV = RESULTS / "coverage.csv"

LEVELS = ['root', 'majmin', 'sevenths', 'mirex']
TOP_N = 15

# (rótulo da camada, manifest, loader)
CAMADAS = [
    ("guitarset", "chord[0]", "data/manifests/guitarset_comping.csv",
     lambda p: ds.load_guitarset(p, index=0)),
    ("guitarset", "chord[1]", "data/manifests/guitarset_comping.csv",
     lambda p: ds.load_guitarset(p, index=1)),
    ("idmt-smt-chords", "lab", "data/manifests/idmt_smt_chords.csv",
     ds.load_idmt_lab),
]

CSV_FIELDS = ["dataset", "camada", "split", "nivel", "n_faixas",
              "duracao_total_s", "comparavel_frac", "comparavel_s",
              "descartado_frac", "n_frac", "n_s", "top_qualidades"]


# ==========================================================================
# Medida
# ==========================================================================
def _comparavel(labels, nivel):
    """
    Máscara booleana: True onde o mir_eval PONDERA o rótulo naquele nível.

    Usa a função do próprio nível, comparando a referência com ela mesma. O
    -1 ('fora do escopo do nível') depende só da referência, então o estimado
    é irrelevante para esta pergunta.
    """
    if not labels:
        return np.zeros(0, dtype=bool)
    scores = getattr(mir_eval.chord, nivel)(labels, labels)
    return np.asarray(scores) != -1


def _qualidade(label):
    """
    A qualidade do rótulo, pela própria decomposição do mir_eval: sem tônica e
    sem baixo, com as extensões entre parênteses como no arquivo.
    'D#:sus2(7)/1' -> 'sus2(7)'; 'C:maj' -> 'maj'; 'N' -> 'N'.
    """
    if label in ds.NO_CHORD or label == 'N':
        return 'N'
    try:
        _, quality, extensoes, _ = mir_eval.chord.split(
            label, reduce_extended_chords=False)
    except Exception:
        return '<ilegível>'
    if extensoes:
        return f"{quality}({','.join(sorted(extensoes))})"
    return quality or 'maj'


def medir_camada(dataset, camada, manifest, loader, split=None):
    """
    Agrega as faixas não excluídas do manifest e devolve uma linha por nível,
    mais a tabela de qualidades (que não depende do nível).

    `split=None` agrega tudo; um valor (`'val'`, `'test'`, `'eval'`) restringe.
    O recorte existe porque a distribuição de qualidades NÃO é a mesma nos dois
    splits -- o tempo de `7` em chord[0] é 9,02 % no conjunto todo e 9,15 % só
    no teste. Quem usar a fração agregada para normalizar um resultado do teste
    erra na terceira casa, e erra a favor da própria conclusão.
    """
    linhas_manifest = _linhas(manifest)
    if split is not None:
        linhas_manifest = [r for r in linhas_manifest
                           if (r.get("split") or "") == split]
    labels, duracoes = [], []
    anotacoes_lidas = 0

    for row in linhas_manifest:
        segmentos = loader(ROOT / row["annotation_path"])
        anotacoes_lidas += 1
        for start, end, label in segmentos:
            labels.append(label)
            duracoes.append(end - start)

    duracoes = np.asarray(duracoes, dtype=float)
    total = float(duracoes.sum())

    # 'N' pela mesma decomposição usada nas qualidades
    qualidades = [_qualidade(l) for l in labels]
    tempo_n = float(duracoes[np.array([q == 'N' for q in qualidades])].sum())

    por_qualidade = Counter()
    for q, d in zip(qualidades, duracoes):
        por_qualidade[q] += float(d)
    top = [(q, t / total if total else 0.0)
           for q, t in por_qualidade.most_common(TOP_N)]

    linhas = []
    for nivel in LEVELS:
        mask = _comparavel(labels, nivel)
        comparavel = float(duracoes[mask].sum())
        linhas.append({
            "dataset": dataset,
            "camada": camada,
            "split": split if split is not None else "todos",
            "nivel": nivel,
            "n_faixas": anotacoes_lidas,
            "duracao_total_s": round(total, 3),
            "comparavel_frac": round(comparavel / total, 6) if total else 0.0,
            "comparavel_s": round(comparavel, 3),
            "descartado_frac": round(1 - comparavel / total, 6) if total else 0.0,
            "n_frac": round(tempo_n / total, 6) if total else 0.0,
            "n_s": round(tempo_n, 3),
            # 6 casas, não 4: a fração de '7' é usada para normalizar um
            # resultado do teste, e 4 casas mudariam a terceira casa do
            # número publicado.
            "top_qualidades": "|".join(f"{q}:{f:.6f}" for q, f in top),
        })
    return linhas, top


def _linhas(manifest):
    caminho = ROOT / manifest if not Path(manifest).is_absolute() else Path(manifest)
    with Path(caminho).open(encoding="utf-8", newline="") as fp:
        return [r for r in csv.DictReader(fp)
                if (r.get("excluded") or "false").strip().lower() != "true"]


def _splits_do_manifest(manifest):
    """Os splits presentes no manifest, na ordem em que aparecem."""
    vistos = []
    for r in _linhas(manifest):
        s = r.get("split") or ""
        if s and s not in vistos:
            vistos.append(s)
    return vistos


def medir_tudo():
    """
    Devolve (linhas_do_csv, {(dataset, camada): top_qualidades}).

    Emite o agregado (`split=todos`) e um recorte por split, para que um
    resultado medido num split possa ser normalizado pela distribuição daquele
    mesmo split e não pela do dataset inteiro.
    """
    linhas, tops = [], {}
    for dataset, camada, manifest, loader in CAMADAS:
        if not (ROOT / manifest).exists():
            print(f"  (manifest ausente: {manifest} -- pulando {dataset}/{camada})")
            continue
        parciais, top = medir_camada(dataset, camada, manifest, loader)
        linhas.extend(parciais)
        tops[(dataset, camada)] = top
        for split in _splits_do_manifest(manifest):
            parciais_split, _ = medir_camada(dataset, camada, manifest, loader,
                                             split=split)
            linhas.extend(parciais_split)
    return linhas, tops


def escrever_csv(linhas, destino=OUT_CSV):
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(linhas)
    return destino


# ==========================================================================
# Resumo no terminal
# ==========================================================================
def _por_chave(linhas):
    saida = {}
    for l in linhas:
        saida.setdefault((l["dataset"], l["camada"]), {})[l["nivel"]] = l
    return saida


def imprimir_resumo(linhas, tops):
    tabela = _por_chave(linhas)
    gs0 = tabela.get(("guitarset", "chord[0]"))
    gs1 = tabela.get(("guitarset", "chord[1]"))

    if gs0 and gs1:
        print("=" * 72)
        print("GuitarSet — as duas camadas lado a lado (fração do tempo ponderada)")
        print("=" * 72)
        qualquer = next(iter(gs1.values()))
        print(f"{qualquer['n_faixas']} faixas não excluídas, "
              f"{qualquer['duracao_total_s']/60:.1f} min de anotação")
        print(f"\n{'nível':<10} | {'chord[0] lead sheet':>20} | "
              f"{'chord[1] performed':>20} | {'Δ':>7}")
        print("-" * 68)
        for nivel in LEVELS:
            a = gs0[nivel]["comparavel_frac"]
            b = gs1[nivel]["comparavel_frac"]
            print(f"{nivel:<10} | {a*100:19.1f}% | {b*100:19.1f}% | "
                  f"{(b-a)*100:+6.1f}")
        print(f"\n{'tempo N':<10} | {gs0['root']['n_frac']*100:19.1f}% | "
              f"{gs1['root']['n_frac']*100:19.1f}% |")

    for (dataset, camada), niveis in tabela.items():
        if dataset == "guitarset":
            continue
        print("\n" + "=" * 72)
        print(f"{dataset} / {camada}")
        print("=" * 72)
        qualquer = next(iter(niveis.values()))
        print(f"{qualquer['n_faixas']} faixas, "
              f"{qualquer['duracao_total_s']/60:.1f} min de anotação")
        print(f"\n{'nível':<10} | {'comparável':>12} | {'descartado':>12}")
        print("-" * 40)
        for nivel in LEVELS:
            l = niveis[nivel]
            print(f"{nivel:<10} | {l['comparavel_frac']*100:11.1f}% | "
                  f"{l['descartado_frac']*100:11.1f}%")

    print("\n" + "=" * 72)
    print(f"Top {TOP_N} qualidades por tempo (não depende do nível)")
    print("=" * 72)
    for (dataset, camada), top in tops.items():
        print(f"\n{dataset} / {camada}:")
        for q, f in top:
            print(f"  {q:<18} {f*100:6.2f}%")


def main():
    linhas, tops = medir_tudo()
    if not linhas:
        print("Nada a medir: gere os manifests com `python dataset_io.py`.")
        return
    imprimir_resumo(linhas, tops)
    destino = escrever_csv(linhas)
    print(f"\nescrito {destino.relative_to(ROOT).as_posix()} "
          f"({len(linhas)} linhas)")


if __name__ == "__main__":
    main()
