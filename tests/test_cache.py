"""
tests/test_cache.py
===================
Testes do cache de Features.

O risco que estes testes cobrem não é o cache falhar -- é o cache ACERTAR
quando não devia: devolver um chroma calculado com outra configuração e a
busca de hiperparâmetros inteira sair de um número errado, sem nenhum sintoma.
Por isso as asserções são sobre identidade (o caminho muda quando a
configuração muda) e sobre validação (metadado adulterado levanta).

Usam áudio sintético e um diretório de cache temporário (`CACHE_DIR` é
redirecionado por fixture), então não tocam em `data/cache/` do projeto.

Como rodar (de dentro de `Decifra-Violão/`):

    pytest tests/test_cache.py
"""

import json
import os
import sys
from dataclasses import replace

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cache  # noqa: E402
import pipeline as P  # noqa: E402
from config import PRE_CHROMA  # noqa: E402
from synth import synth_chord  # noqa: E402

SR = 22050


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Redireciona o cache para um diretório temporário."""
    destino = tmp_path / "cache"
    monkeypatch.setattr(cache, "CACHE_DIR", destino)
    return destino


@pytest.fixture
def audio(tmp_path):
    """Um WAV curto de verdade: C(2s) + G(2s), para o librosa.load abrir."""
    import soundfile as sf
    y = np.concatenate([
        synth_chord(0, '', sr=SR, dur=2.0, n_harmonics=6),
        synth_chord(7, '', sr=SR, dur=2.0, n_harmonics=6),
    ])
    caminho = tmp_path / "faixa_teste.wav"
    sf.write(caminho, y, SR)
    return caminho


# ==========================================================================
# Identidade do cache
# ==========================================================================
def test_caminho_muda_quando_um_campo_de_pre_muda(cache_dir, audio):
    base = cache.cache_path(audio, PRE_CHROMA)
    for campo, valor in [("sr", 11025), ("method", "stft"), ("smooth", 0),
                         ("hpss_margin", 1.0), ("bins_per_octave", 12)]:
        outro = cache.cache_path(audio, replace(PRE_CHROMA, **{campo: valor}))
        assert outro != base, f"mudar {campo} não mudou o caminho do cache"
    # mesma configuração -> mesmo caminho (o hash é estável entre chamadas)
    assert cache.cache_path(audio, PRE_CHROMA) == base
    assert base.suffix == ".npz" and audio.stem in base.name


def test_hash_cobre_campos_novos_automaticamente():
    """
    O hash é montado com dataclasses.fields, não com uma lista escrita à mão:
    todo campo da dataclass aparece na serialização canônica.
    """
    from dataclasses import fields
    canonico = cache._canonical("x.wav", PRE_CHROMA)
    for f in fields(PRE_CHROMA):
        assert f.name in canonico, f"campo {f.name} ficou fora do hash"


# ==========================================================================
# Reuso
# ==========================================================================
def test_segunda_chamada_nao_recalcula(cache_dir, audio, monkeypatch):
    """get_features duas vezes: extract_features roda uma só."""
    chamadas = []
    original = cache.extract_features

    def contando(y, sr, pre):
        chamadas.append(pre)
        return original(y, sr, pre)

    monkeypatch.setattr(cache, "extract_features", contando)

    primeira = cache.get_features(audio, PRE_CHROMA)
    assert len(chamadas) == 1
    assert cache.cache_path(audio, PRE_CHROMA).exists()

    segunda = cache.get_features(audio, PRE_CHROMA)
    assert len(chamadas) == 1, "a segunda chamada recalculou o chroma"

    for campo in ("chroma", "beat_times", "seg_rms"):
        a, b = getattr(primeira, campo), getattr(segunda, campo)
        assert b.dtype == a.dtype
        assert np.array_equal(a, b), f"{campo} voltou diferente do cache"


def test_force_recalcula(cache_dir, audio, monkeypatch):
    chamadas = []
    original = cache.extract_features
    monkeypatch.setattr(cache, "extract_features",
                        lambda y, sr, pre: (chamadas.append(pre),
                                            original(y, sr, pre))[1])

    cache.get_features(audio, PRE_CHROMA)
    cache.get_features(audio, PRE_CHROMA, force=True)
    assert len(chamadas) == 2


def test_cache_abre_com_features_load(cache_dir, audio):
    """O .npz do cache continua legível pelo loader de pipeline.Features."""
    esperado = cache.get_features(audio, PRE_CHROMA)
    lido = P.Features.load(cache.cache_path(audio, PRE_CHROMA))
    assert np.array_equal(lido.chroma, esperado.chroma)


# ==========================================================================
# Validação
# ==========================================================================
def _reescreve_meta(path, meta):
    """Regrava o .npz trocando só o metadado."""
    with np.load(path, allow_pickle=False) as data:
        arrays = {k: data[k] for k in data.files}
    arrays[cache._META_KEY] = np.array(json.dumps(meta))
    np.savez(path, **arrays)


@pytest.mark.parametrize("campo,valor", [
    ("sr", 11025),
    ("method", "stft"),
    ("smooth", 0),
    ("hpss_margin", 1.0),
    ("bins_per_octave", 12),
])
def test_metadado_adulterado_levanta(cache_dir, audio, campo, valor):
    """Um campo de pre divergente no .npz nunca passa em silêncio."""
    destino = cache.cache_path(audio, PRE_CHROMA)
    cache.get_features(audio, PRE_CHROMA)

    meta = {"audio": cache._rel(audio),
            "pre": dict(cache._pre_items(replace(PRE_CHROMA, **{campo: valor})))}
    _reescreve_meta(destino, meta)

    with pytest.raises(cache.CacheMismatchError) as exc:
        cache.get_features(audio, PRE_CHROMA)
    assert campo in str(exc.value)


def test_audio_adulterado_levanta(cache_dir, audio):
    destino = cache.cache_path(audio, PRE_CHROMA)
    cache.get_features(audio, PRE_CHROMA)

    meta = {"audio": "outro/caminho.wav",
            "pre": dict(cache._pre_items(PRE_CHROMA))}
    _reescreve_meta(destino, meta)

    with pytest.raises(cache.CacheMismatchError) as exc:
        cache.get_features(audio, PRE_CHROMA)
    assert "audio" in str(exc.value)


def test_npz_sem_metadado_levanta(cache_dir, audio):
    """Arquivo escrito por Features.save (sem meta) não é aceito como cache."""
    destino = cache.cache_path(audio, PRE_CHROMA)
    destino.parent.mkdir(parents=True, exist_ok=True)
    features = P.extract_features(
        np.concatenate([synth_chord(0, '', sr=SR, dur=2.0, n_harmonics=6)]),
        SR, PRE_CHROMA)
    features.save(destino)

    with pytest.raises(cache.CacheMismatchError):
        cache.get_features(audio, PRE_CHROMA)


# ==========================================================================
# CLI / lote
# ==========================================================================
def test_lote_nao_aborta_em_falha(cache_dir, audio, tmp_path, capsys):
    """Uma faixa quebrada é registrada e o lote segue."""
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "dataset,track_id,audio_path,excluded\n"
        f"t,boa,{cache._rel(audio)},false\n"
        "t,inexistente,data/extracted/nao_existe.wav,false\n"
        f"t,pulada,{cache._rel(audio)},true\n",
        encoding="utf-8")

    gerados, reaproveitados, falhas = cache.preencher(manifest, PRE_CHROMA)

    assert gerados == 1
    assert reaproveitados == 0
    assert [t for t, _ in falhas] == ["inexistente"]
    assert "pulada" not in capsys.readouterr().out
