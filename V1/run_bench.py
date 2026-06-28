"""
run_bench.py
============
Ponto de entrada. Roda o bench completo comparando:
  - CosineChordClassifier (proposta nova)
  - classificar_segmento_v4 (seu baseline preservado)

Gera no terminal: acurácia por condição e por tipo, top de confusões, teste de
pausa. Salva em ./out: matrizes de confusão, barras de acurácia e a curva de
varredura de harmônicos.

Rode:  python3 run_bench.py
"""

import os
import numpy as np

from V1.chord_templates import TRIADS, TETRADS, BASIC, build_templates
from V1.synth import synth_chord
from V1.classifier import CosineChordClassifier, chroma_vector, NO_CHORD
from V1.legacy_v4 import classificar_segmento_v4
import V1.bench as bench

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

SR = 22050

# QUICK=True roda rápido (4 raízes, sem detune ~ o gargalo do pitch_shift).
# QUICK=False roda completo (12 raízes, todas as condições) ~ 3-4 min.
QUICK = True
ROOTS = range(0, 12, 3) if QUICK else range(12)
if QUICK:
    from V1.noise import DEFAULT_CONDITIONS as _ALL
    CONDITIONS = [c for c in _ALL if not c[0].startswith('detune')]
else:
    from V1.noise import DEFAULT_CONDITIONS as CONDITIONS


# --------------------------------------------------------------------------
# Adaptadores: ambos os classificadores expostos como classify_fn(y, sr)->nome
# --------------------------------------------------------------------------
cos_clf = CosineChordClassifier(confidence_gate=0.72, rms_gate=0.02)

def classify_cosine(y, sr):
    return cos_clf.classify_audio(y, sr)

def classify_v4(y, sr):
    # gate de RMS para dar ao V4 a mesma chance de detectar pausa
    if np.sqrt(np.mean(y ** 2) + 1e-12) < 0.02:
        return NO_CHORD
    vec = chroma_vector(y, sr)          # mesmo chroma do cosseno (justo)
    nome = classificar_segmento_v4(vec)
    return nome if nome not in ("", "N/A") else NO_CHORD


def secao(titulo):
    print("\n" + "=" * 64)
    print(titulo)
    print("=" * 64)


def main():
    # ---------------------------------------------------------------
    # 1. Bench principal (tríades + tétrades x todas as condições)
    # ---------------------------------------------------------------
    secao("1. BENCH PRINCIPAL  (12 raízes x tríades+tétrades x ruídos)")

    print("\n[Cosseno]")
    rec_cos = bench.run_bench(classify_cosine, sr=SR, roots=ROOTS,
                              conditions=CONDITIONS, suffixes=TRIADS + TETRADS)
    print("\n[V4 baseline]")
    rec_v4 = bench.run_bench(classify_v4, sr=SR, roots=ROOTS,
                             conditions=CONDITIONS, suffixes=TRIADS + TETRADS)

    pc_cos, pt_cos = bench.accuracy_table(rec_cos)
    pc_v4, pt_v4 = bench.accuracy_table(rec_v4)

    print("\n--- Acurácia por CONDIÇÃO de ruído ---")
    print(f"{'condição':<14} | {'cosseno':>8} | {'V4':>8}")
    print("-" * 38)
    for k in pc_cos:
        print(f"{k:<14} | {pc_cos[k]*100:7.1f}% | {pc_v4.get(k,0)*100:7.1f}%")

    print("\n--- Acurácia por TIPO de acorde ---")
    print(f"{'tipo':<8} | {'cosseno':>8} | {'V4':>8}")
    print("-" * 30)
    for k in sorted(pt_cos):
        print(f"{k:<8} | {pt_cos[k]*100:7.1f}% | {pt_v4.get(k,0)*100:7.1f}%")

    print("\n--- Top confusões (cosseno) ---")
    for (t, p), n in bench.top_confusions(rec_cos, k=10):
        print(f"  {t:>6} -> {p:<6}  ({n}x)")

    # matrizes de confusão por tipo
    M_cos, lab_cos = bench.confusion_by_type(rec_cos)
    M_v4, lab_v4 = bench.confusion_by_type(rec_v4)
    bench.plot_confusion(M_cos, lab_cos,
                         "Confusão por tipo - Cosseno",
                         os.path.join(OUT, "confusao_cosseno.png"))
    bench.plot_confusion(M_v4, lab_v4,
                         "Confusão por tipo - V4",
                         os.path.join(OUT, "confusao_v4.png"))
    bench.plot_accuracy_bars(pc_cos, "Acurácia por condição - Cosseno",
                             os.path.join(OUT, "acuracia_cosseno.png"))

    # ---------------------------------------------------------------
    # 2. Teste de pausa (falso-positivo: ruído rotulado como acorde)
    # ---------------------------------------------------------------
    secao("2. TESTE DE PAUSA  (ideal: 0% rotulado como acorde)")
    print("\n[Cosseno]")
    bench.pause_test(classify_cosine, sr=SR)
    print("\n[V4 baseline]")
    bench.pause_test(classify_v4, sr=SR)

    # ---------------------------------------------------------------
    # 3. Varredura de harmônicos (onde cada um flipa)
    # ---------------------------------------------------------------
    secao("3. VARREDURA DE HARMÔNICOS  (maj/m/7/maj7, sem ruído)")
    print("\n[Cosseno]")
    sw_cos = bench.harmonic_sweep(classify_cosine, sr=SR, roots=ROOTS)
    print("\n[V4 baseline]")
    sw_v4 = bench.harmonic_sweep(classify_v4, sr=SR, roots=ROOTS)
    bench.plot_harmonic_sweep({'Cosseno': sw_cos, 'V4': sw_v4},
                              "Acurácia vs nº de harmônicos",
                              os.path.join(OUT, "varredura_harmonicos.png"))

    secao("ARQUIVOS GERADOS")
    for f in sorted(os.listdir(OUT)):
        print("  out/" + f)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
