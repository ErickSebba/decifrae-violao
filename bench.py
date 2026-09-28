"""
bench.py
========
Motor do bench sintético.

Agnóstico ao classificador: recebe uma função classify_fn(y, sr) -> nome.
Assim a MESMA bateria roda no classificador por cosseno e no V4 (baseline),
e você compara as matrizes de confusão lado a lado.

Produz:
  - run_bench        : roda (acordes x condições de ruído), devolve registros
  - accuracy_table   : acurácia por condição e por tipo de acorde
  - top_confusions   : os erros mais frequentes (verdadeiro -> predito)
  - confusion_by_type: matriz de confusão colapsada por TIPO de acorde
  - pause_test       : taxa de falso-positivo em pausas (ruído rotulado como acorde)
  - harmonic_sweep   : acurácia vs nº de harmônicos (acha onde o algoritmo flipa)
  - plot_*           : heatmaps e curvas (salvos em arquivo)
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # backend sem display (salva em arquivo)
import matplotlib.pyplot as plt

from chord_templates import (NOTE_NAMES, TRIADS, TETRADS, BASIC,
                             build_templates, NO_CHORD)
from synth import synth_chord, synth_pause
from noise import apply_condition, DEFAULT_CONDITIONS


# --------------------------------------------------------------------------
# Execução da bateria
# --------------------------------------------------------------------------
def run_bench(classify_fn, sr=22050, dur=1.5,
              roots=range(12), suffixes=None,
              conditions=None, n_harmonics=6, decay=0.6,
              base_octave=3, seed=0, verbose=True):
    """
    Roda (acordes x condições). Devolve uma lista de registros:
        {'true', 'true_type', 'cond', 'pred', 'correct'}

    classify_fn : callable(y, sr) -> str   (nome do acorde ou 'N')
    suffixes    : lista de tipos; None = TRIADS + TETRADS
    conditions  : lista (rotulo, nome, kwargs); None = DEFAULT_CONDITIONS
    """
    if suffixes is None:
        suffixes = TRIADS + TETRADS
    if conditions is None:
        conditions = DEFAULT_CONDITIONS

    records = []
    total = len(list(roots)) * len(suffixes) * len(conditions)
    done = 0

    for root in roots:
        for suffix in suffixes:
            true_name = f"{NOTE_NAMES[root]}{suffix}"
            y_clean = synth_chord(root, suffix, sr=sr, dur=dur,
                                  base_octave=base_octave,
                                  n_harmonics=n_harmonics, decay=decay)
            for label, cname, kw in conditions:
                y = apply_condition(y_clean, sr, cname, **kw)
                pred = classify_fn(y, sr)
                records.append({
                    'true': true_name,
                    'true_type': suffix if suffix else 'maj',
                    'cond': label,
                    'pred': pred,
                    'correct': pred == true_name,
                })
                done += 1
        if verbose:
            print(f"  ... {done}/{total} casos", end="\r")
    if verbose:
        print(f"  {total} casos concluídos.            ")
    return records


# --------------------------------------------------------------------------
# Métricas
# --------------------------------------------------------------------------
def accuracy_table(records):
    """
    Retorna dois dicionários:
      por_condicao : {condição: acurácia}
      por_tipo     : {tipo_de_acorde: acurácia}
    """
    conds = {}
    types = {}
    for r in records:
        conds.setdefault(r['cond'], []).append(r['correct'])
        types.setdefault(r['true_type'], []).append(r['correct'])
    por_condicao = {k: float(np.mean(v)) for k, v in conds.items()}
    por_tipo = {k: float(np.mean(v)) for k, v in types.items()}
    return por_condicao, por_tipo


def top_confusions(records, k=15, only_wrong=True):
    """Lista os pares (verdadeiro -> predito) mais frequentes."""
    from collections import Counter
    c = Counter()
    for r in records:
        if only_wrong and r['correct']:
            continue
        c[(r['true'], r['pred'])] += 1
    return c.most_common(k)


def _type_of(name):
    """Extrai o tipo (sufixo) de um nome de acorde. 'C#m7' -> 'm7'."""
    if name == NO_CHORD or name == "" or name == "N/A":
        return NO_CHORD
    # remove a raiz (1 ou 2 chars: letra + '#')
    if len(name) >= 2 and name[1] == '#':
        suffix = name[2:]
    else:
        suffix = name[1:]
    return suffix if suffix else 'maj'


def confusion_by_type(records):
    """
    Matriz de confusão colapsada por TIPO de acorde (ignora a raiz).
    Mostra padrões como maj->7 ou m->m7, que é o que interessa.
    Retorna (matriz, rotulos).
    """
    true_types = sorted(set(r['true_type'] for r in records))
    pred_types = sorted(set(_type_of(r['pred']) for r in records))
    labels = sorted(set(true_types) | set(pred_types),
                    key=lambda s: (s == NO_CHORD, s))
    idx = {l: i for i, l in enumerate(labels)}
    M = np.zeros((len(labels), len(labels)), dtype=int)
    for r in records:
        M[idx[r['true_type']], idx[_type_of(r['pred'])]] += 1
    return M, labels


# --------------------------------------------------------------------------
# Teste de pausa (falso-positivo)
# --------------------------------------------------------------------------
def pause_test(classify_fn, sr=22050, dur=1.0, n_trials=30,
               noise_levels=(0.005, 0.01, 0.02, 0.05), verbose=True):
    """
    Gera pausas com ruído leve crescente e mede quantas são (erroneamente)
    rotuladas como acorde. O ideal é 0% (tudo 'N').

    Retorna {noise_level: taxa_de_falso_positivo}.
    """
    out = {}
    for lvl in noise_levels:
        fp = 0
        for t in range(n_trials):
            p = synth_pause(sr=sr, dur=dur, noise_level=lvl, seed=1000 + t)
            pred = classify_fn(p, sr)
            if pred not in (NO_CHORD, "", "N/A"):
                fp += 1
        rate = fp / n_trials
        out[lvl] = rate
        if verbose:
            print(f"  ruído {lvl:.3f}: {rate*100:5.1f}% rotulado como acorde "
                  f"({fp}/{n_trials})")
    return out


# --------------------------------------------------------------------------
# Varredura de harmônicos (onde o algoritmo flipa)
# --------------------------------------------------------------------------
def harmonic_sweep(classify_fn, sr=22050, dur=1.5,
                   roots=range(12), suffixes=None,
                   harmonics_range=range(1, 13), decay=0.6, verbose=True):
    """
    Para cada nº de harmônicos, mede a acurácia (sem ruído).
    Revela o ponto onde os harmônicos começam a confundir o classificador
    (ex.: maj virando 7 por causa do 7º harmônico).

    Retorna {n_harmonics: acuracia}.
    """
    if suffixes is None:
        suffixes = ['', 'm', '7', 'maj7']
    out = {}
    for nh in harmonics_range:
        hits = 0
        total = 0
        for root in roots:
            for suffix in suffixes:
                true_name = f"{NOTE_NAMES[root]}{suffix}"
                y = synth_chord(root, suffix, sr=sr, dur=dur,
                                n_harmonics=nh, decay=decay)
                pred = classify_fn(y, sr)
                hits += (pred == true_name)
                total += 1
        out[nh] = hits / total
        if verbose:
            print(f"  harmônicos={nh:2d}: acurácia {out[nh]*100:5.1f}%")
    return out


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------
def plot_confusion(M, labels, title, path):
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(M, cmap='viridis')
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_yticklabels(labels)
    ax.set_xlabel("Predito")
    ax.set_ylabel("Verdadeiro")
    ax.set_title(title)
    thr = M.max() / 2 if M.max() > 0 else 1
    for i in range(len(labels)):
        for j in range(len(labels)):
            if M[i, j] > 0:
                ax.text(j, i, str(M[i, j]), ha='center', va='center',
                        color='white' if M[i, j] < thr else 'black', fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_accuracy_bars(por_condicao, title, path):
    fig, ax = plt.subplots(figsize=(10, 4))
    ks = list(por_condicao.keys())
    vs = [por_condicao[k] * 100 for k in ks]
    cores = ['#2a9d8f' if v >= 80 else '#e9c46a' if v >= 50 else '#e76f51'
             for v in vs]
    ax.bar(ks, vs, color=cores)
    ax.set_ylabel("Acurácia (%)")
    ax.set_ylim(0, 100)
    ax.set_title(title)
    ax.axhline(80, ls='--', color='gray', alpha=0.5)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_harmonic_sweep(sweeps, title, path):
    """sweeps : {label: {n_harm: acc}} -> compara curvas (ex.: cosseno vs V4)."""
    fig, ax = plt.subplots(figsize=(9, 5))
    for label, data in sweeps.items():
        xs = list(data.keys())
        ys = [data[x] * 100 for x in xs]
        ax.plot(xs, ys, marker='o', label=label)
    ax.set_xlabel("Nº de harmônicos por nota")
    ax.set_ylabel("Acurácia (%)")
    ax.set_ylim(0, 105)
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close(fig)
    return path


if __name__ == "__main__":
    from classifier import CosineChordClassifier
    clf = CosineChordClassifier()
    fn = lambda y, sr: clf.classify_audio(y, sr)
    recs = run_bench(fn, suffixes=BASIC, conditions=DEFAULT_CONDITIONS[:3],
                     roots=range(3))
    pc, pt = accuracy_table(recs)
    print("por condição:", {k: round(v, 2) for k, v in pc.items()})
    print("por tipo:", {k: round(v, 2) for k, v in pt.items()})
