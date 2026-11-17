"""Baseline externo: reconhecedor de acordes CNN + CRF do madmom.

Modelo pré-treinado de Korzeniowski & Widmer (2016), "A Fully Convolutional
Deep Auditory Model for Musical Chord Recognition" (vocabulário maior/menor
+ N, 25 classes). Os pesos vêm junto do pacote madmom
(`madmom/models/chords/2016/`).

IMPORTANTE: este script roda com o Python do ambiente separado do madmom
(ex.: C:\\Users\\erick\\.venvs\\madmom310), NÃO com o `.venv` do projeto.
Não importa nenhum módulo do projeto; só lê o manifest.

Uso (de dentro da raiz do repositório):

    C:\\Users\\erick\\.venvs\\madmom310\\Scripts\\python.exe baselines/madmom_acordes.py \\
        --manifest data/manifests/guitarset_comping.csv --splits val --limite 2

Saída: data/cache/baselines/madmom/<dataset>/<track_id>.lab
(início\\tfim\\trótulo, rótulos Harte como o madmom emite: `C:maj`, `A:min`,
`N`). Faixas cujo .lab já existe são puladas. Grava também
data/cache/baselines/madmom/versoes.json.

O split `test` é recusado a menos que `--splits test` seja pedido
explicitamente (e sozinho).
"""
import argparse
import csv
import json
import os
import platform
import sys
import time

import numpy as np
import scipy

import madmom
from madmom.audio.signal import Signal
from madmom.features.chords import (CNNChordFeatureProcessor,
                                    CRFChordRecognitionProcessor)
from madmom.models import CHORDS_CFCRF, CHORDS_CNN_FEAT

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, 'data', 'cache', 'baselines', 'madmom')
SR_MODELO = 44100  # taxa usada pelo CNNChordFeatureProcessor


def _origem_madmom():
    """URL e commit de onde o madmom foi instalado (PEP 610), se houver."""
    try:
        from importlib.metadata import distribution
        txt = distribution('madmom').read_text('direct_url.json')
        return json.loads(txt) if txt else None
    except Exception:
        return None


def versoes():
    return {
        'python': sys.version.split()[0],
        'plataforma': platform.platform(),
        'madmom': madmom.__version__,
        'madmom_origem': _origem_madmom(),
        'numpy': np.__version__,
        'scipy': scipy.__version__,
        'modelo_features': [os.path.relpath(f, os.path.dirname(madmom.__file__))
                            for f in CHORDS_CNN_FEAT],
        'modelo_crf': [os.path.relpath(f, os.path.dirname(madmom.__file__))
                       for f in CHORDS_CFCRF],
        'processadores': 'CNNChordFeatureProcessor + CRFChordRecognitionProcessor',
        'referencia': 'Korzeniowski & Widmer (2016), CNN + CRF, maj/min + N',
    }


def carregar_sinal(caminho):
    """Devolve o que o processador do madmom deve receber.

    WAV a 44,1 kHz vai pelo caminho nativo do madmom (passa o arquivo; é
    exatamente o que o modelo viu no treino). Outras taxas são lidas com
    scipy, mixadas para mono e reamostradas para 44,1 kHz mantendo a escala
    int16, para não depender de ffmpeg.
    """
    from scipy.io import wavfile
    sr, dados = wavfile.read(caminho, mmap=True)
    if sr == SR_MODELO:
        return caminho, sr
    from math import gcd
    from scipy.signal import resample_poly
    x = np.asarray(dados, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if dados.dtype.kind == 'f':  # float em [-1, 1] -> escala int16
        x = x * 32767.0
    g = gcd(SR_MODELO, sr)
    x = resample_poly(x, SR_MODELO // g, sr // g)
    x = np.clip(np.round(x), -32768, 32767).astype(np.int16)
    return Signal(x, sample_rate=SR_MODELO, num_channels=1), sr


def ler_manifest(caminho, splits, limite):
    with open(caminho, newline='', encoding='utf-8') as f:
        linhas = list(csv.DictReader(f))
    sel = []
    for ln in linhas:
        if ln.get('excluded', '').strip().lower() == 'true':
            continue
        if ln['split'] not in splits:
            continue
        sel.append(ln)
    if limite is not None:
        sel = sel[:limite]
    return sel


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--splits', required=True,
                    help='lista separada por vírgula, ex.: val ou train,val')
    ap.add_argument('--limite', type=int, default=None)
    args = ap.parse_args()

    splits = [s.strip() for s in args.splits.split(',') if s.strip()]
    if 'test' in splits and splits != ['test']:
        sys.exit("ERRO: o split 'test' só é aceito com '--splits test' "
                 "explícito e sozinho.")

    faixas = ler_manifest(args.manifest, set(splits), args.limite)
    print(f'{len(faixas)} faixa(s) selecionada(s) em {splits}')

    os.makedirs(SAIDA, exist_ok=True)
    with open(os.path.join(SAIDA, 'versoes.json'), 'w', encoding='utf-8') as f:
        json.dump(versoes(), f, indent=2, ensure_ascii=False)

    feat = CNNChordFeatureProcessor()
    crf = CRFChordRecognitionProcessor()

    for ln in faixas:
        destino = os.path.join(SAIDA, ln['dataset'], ln['track_id'] + '.lab')
        if os.path.exists(destino):
            print(f'[pula] {ln["track_id"]} (já existe)')
            continue
        audio = ln['audio_path']
        if not os.path.isabs(audio):
            audio = os.path.join(RAIZ, audio)
        t0 = time.perf_counter()
        entrada, sr = carregar_sinal(audio)
        segs = crf(feat(entrada))
        dt = time.perf_counter() - t0
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        tmp = destino + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            for ini, fim, rot in segs:
                f.write(f'{float(ini):.6f}\t{float(fim):.6f}\t{rot}\n')
        os.replace(tmp, destino)
        print(f'[ok] {ln["dataset"]}/{ln["track_id"]}: {len(segs)} segmentos, '
              f'sr_orig={sr}, {dt:.2f} s')


if __name__ == '__main__':
    main()
