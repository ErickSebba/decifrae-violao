"""
tests/test_regression.py
========================
Teste de regressão do oráculo: `out/musicas_bench/metrics.json` é a saída
commitada de `benchmark_musicas.py` e, enquanto o comportamento do pipeline não
muda de propósito, tem de sair idêntico (CLAUDE.md, "Regra de ouro").

Este teste automatiza o procedimento manual descrito em `docs/BENCHMARK.md` §1
("Uso como teste de regressão"): carrega o JSON commitado, roda as duas faixas
com ground truth pelos runners do próprio `benchmark_musicas.py` (`run_atual` e
`run_v4`, cujos hiperparâmetros vêm de `config.py`), pontua com
`evaluate.score_segments` nos 4 níveis mir_eval e compara com tolerância
absoluta de 1e-9 por nível.

Nada é escrito em disco: o oráculo só é lido.

Como rodar (de dentro de `Decifra-Violão/`):

    pytest tests/test_regression.py
"""

import json
import os
import sys

import pytest

# Os módulos do projeto vivem na raiz, em layout plano e sem `__init__.py`;
# o pytest só põe `tests/` no sys.path, então a raiz entra aqui.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import librosa  # noqa: E402

import benchmark_musicas as bm  # noqa: E402
from evaluate import score_segments  # noqa: E402

ORACLE = os.path.join(ROOT, "out", "musicas_bench", "metrics.json")

# Tolerância por nível. O pipeline é determinístico, então a comparação é
# essencialmente exata; 1e-9 só absorve ruído de serialização do JSON.
TOL = 1e-9


# ==========================================================================
# Carga do oráculo e das faixas
# ==========================================================================
def _load_oracle():
    if not os.path.exists(ORACLE):
        pytest.skip(f"oráculo ausente: {ORACLE} (rode python benchmark_musicas.py)")
    with open(ORACLE, encoding="utf-8") as fp:
        return json.load(fp)


ORACLE_DATA = _load_oracle()

# Só faz sentido testar as faixas que estão no oráculo E têm ground truth.
TRACKS = [name for name in bm.GROUND_TRUTH if name in ORACLE_DATA]

# Cache por faixa: áudio e pontuações são caros (~1 min a faixa) e os testes
# são parametrizados por nível.
_audio_cache = {}
_scores_cache = {}


def _audio(name):
    """(y, sr) da faixa, carregado uma única vez por sessão."""
    if name not in _audio_cache:
        path = os.path.join(bm.MUS, bm.AUDIO_FILES.get(name, name + ".mp3"))
        if not os.path.exists(path):
            pytest.skip(f"áudio ausente: {path}")
        _audio_cache[name] = librosa.load(path, sr=bm.SR, mono=True)
    return _audio_cache[name]


def _scores(name, runner):
    """Pontuação nos 4 níveis para (faixa, runner), calculada uma única vez."""
    key = (name, runner)
    if key not in _scores_cache:
        y, sr = _audio(name)
        # Chama os runners do próprio benchmark em vez de replicar a chamada:
        # replicar deixaria o teste passar enquanto o caminho real quebrasse.
        # Os hiperparâmetros vêm de config.py, via benchmark_musicas.
        est = bm.run_atual(y, sr) if runner == "atual" else bm.run_v4(y, sr)
        _scores_cache[key] = score_segments(est, bm.GROUND_TRUTH[name],
                                            levels=bm.LEVELS)
    return _scores_cache[key]


# ==========================================================================
# Testes
# ==========================================================================
@pytest.mark.parametrize("name", TRACKS)
@pytest.mark.parametrize("runner", ["atual", "v4"])
@pytest.mark.parametrize("level", bm.LEVELS)
def test_metrica_bate_com_o_oraculo(name, runner, level):
    """Cada nível mir_eval reproduz o valor commitado em metrics.json."""
    esperado = ORACLE_DATA[name][runner][level]
    obtido = _scores(name, runner)[level]
    assert obtido == pytest.approx(esperado, abs=TOL), (
        f"regressão em {name}/{runner}/{level}: "
        f"esperado {esperado!r}, obtido {obtido!r} "
        f"(Δ={obtido - esperado:+.3e})"
    )


def test_oraculo_cobre_as_duas_faixas():
    """Guarda contra um oráculo truncado silenciosamente."""
    assert sorted(ORACLE_DATA) == sorted(bm.GROUND_TRUTH)
    for name in bm.GROUND_TRUTH:
        assert sorted(ORACLE_DATA[name]) == ["atual", "v4"]
        for runner in ("atual", "v4"):
            assert sorted(ORACLE_DATA[name][runner]) == sorted(bm.LEVELS)
