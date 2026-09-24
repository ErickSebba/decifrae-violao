"""
cache.py
========
Persistência em disco da etapa cara do pipeline (`pipeline.extract_features`).

Sete dos oito parâmetros do espaço de busca são pós-chroma (CLAUDE.md,
"Hiperparâmetros: pré-chroma e pós-chroma"). Isso quer dizer que uma varredura
inteira pode reusar o mesmo chroma: HPSS + beat track + CQT rodam uma vez por
(áudio, PreChromaConfig) e ficam aqui.

Layout: `data/cache/<nome_do_audio>__<hash8>.npz`, onde `hash8` são os 8
primeiros hex de um sha256 sobre o caminho do áudio e TODOS os campos de
PreChromaConfig. Os campos são lidos com `dataclasses.fields`, então um campo
novo na dataclass entra no hash sozinho e invalida os caches antigos -- é
proposital: cache que sobrevive a uma mudança de configuração é cache errado.

O hash identifica, mas não prova. Por isso todo `.npz` guarda o caminho e os
campos como metadados e o load os confere um a um; divergência levanta
`CacheMismatchError` com os campos que não bateram. Nada é devolvido em
silêncio.

Os arrays vão com os mesmos nomes que `Features.save` usa, então um arquivo
daqui também abre com `pipeline.Features.load` (que simplesmente ignora os
metadados).

CLI:

    python cache.py --manifest data/manifests/guitarset_comping.csv
    python cache.py --manifest ... --limit 5        # só as 5 primeiras
    python cache.py --manifest ... --force          # recalcula tudo
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import fields
from pathlib import Path

import numpy as np

from config import PRE_CHROMA, PreChromaConfig
from pipeline import Features, extract_features

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"

# Chave do metadado dentro do .npz. Os outros nomes (chroma, beat_times,
# seg_rms) são os de Features.save.
_META_KEY = "meta"


class CacheMismatchError(Exception):
    """O .npz não corresponde ao que foi pedido. Nunca é engolido."""


# ==========================================================================
# Identidade do cache
# ==========================================================================
def _rel(path):
    """Caminho relativo à raiz do projeto quando possível; senão, absoluto."""
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _pre_items(pre):
    """
    [(nome, valor), ...] de TODOS os campos de PreChromaConfig, na ordem de
    declaração. Programático de propósito: campo novo entra sem edição aqui.
    """
    return [(f.name, getattr(pre, f.name)) for f in fields(pre)]


def _canonical(audio_path, pre):
    """Serialização canônica de (áudio, configuração) -> str estável."""
    payload = {"audio": _rel(audio_path), "pre": _pre_items(pre)}
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def cache_path(audio_path, pre=PRE_CHROMA):
    """Caminho do .npz correspondente a (áudio, configuração pré-chroma)."""
    digest = hashlib.sha256(_canonical(audio_path, pre).encode("utf-8"))
    hash8 = digest.hexdigest()[:8]
    return CACHE_DIR / f"{Path(audio_path).stem}__{hash8}.npz"


# ==========================================================================
# Leitura e escrita
# ==========================================================================
def _save(path, features, audio_path, pre):
    """Escreve o .npz de forma atômica (tmp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"audio": _rel(audio_path), "pre": dict(_pre_items(pre))}
    tmp = path.parent / (path.name + ".tmp")
    with tmp.open("wb") as fp:
        np.savez(fp, chroma=features.chroma, beat_times=features.beat_times,
                 seg_rms=features.seg_rms,
                 **{_META_KEY: np.array(json.dumps(meta, ensure_ascii=True))})
    os.replace(tmp, path)
    return path


def _check_meta(path, meta, audio_path, pre):
    """Confere o metadado campo a campo. Levanta com a lista de divergências."""
    divergencias = []

    esperado_audio = _rel(audio_path)
    if meta.get("audio") != esperado_audio:
        divergencias.append(
            f"audio: cache={meta.get('audio')!r} pedido={esperado_audio!r}")

    guardado = meta.get("pre", {})
    for nome, valor in _pre_items(pre):
        if nome not in guardado:
            divergencias.append(f"{nome}: ausente no cache, pedido={valor!r}")
        elif guardado[nome] != valor:
            divergencias.append(
                f"{nome}: cache={guardado[nome]!r} pedido={valor!r}")

    sobrando = set(guardado) - {n for n, _ in _pre_items(pre)}
    for nome in sorted(sobrando):
        divergencias.append(f"{nome}: no cache ({guardado[nome]!r}) mas não "
                            f"existe mais em PreChromaConfig")

    if divergencias:
        raise CacheMismatchError(
            f"{path.name} não corresponde ao pedido:\n  "
            + "\n  ".join(divergencias)
        )


def load_cached(path, audio_path, pre):
    """Lê um .npz validando os metadados. Levanta CacheMismatchError se não bate."""
    path = Path(path)
    with np.load(path, allow_pickle=False) as data:
        if _META_KEY not in data:
            raise CacheMismatchError(
                f"{path.name} não tem metadados (arquivo de uma versão "
                f"anterior do cache); regenere com force=True")
        meta = json.loads(str(data[_META_KEY].item()))
        _check_meta(path, meta, audio_path, pre)
        return Features(chroma=data["chroma"], beat_times=data["beat_times"],
                        seg_rms=data["seg_rms"])


def get_features(audio_path, pre=PRE_CHROMA, force=False):
    """
    Features de uma faixa, do cache quando possível.

    force=True ignora o que houver em disco, recalcula e sobrescreve. É também
    a saída para um .npz corrompido (ex.: escrita interrompida antes do
    `os.replace`), que de outra forma propaga o erro de leitura em vez de ser
    remendado em silêncio.
    """
    import librosa                      # import tardio: o CLI abre mais rápido

    audio_path = Path(audio_path)
    destino = cache_path(audio_path, pre)

    if not force and destino.exists():
        return load_cached(destino, audio_path, pre)

    y, sr = librosa.load(audio_path, sr=pre.sr, mono=True)
    features = extract_features(y, sr, pre)
    _save(destino, features, audio_path, pre)
    return features


# ==========================================================================
# CLI
# ==========================================================================
def _linhas_do_manifest(manifest):
    """Linhas não excluídas, na ordem do CSV."""
    with Path(manifest).open(encoding="utf-8", newline="") as fp:
        return [row for row in csv.DictReader(fp)
                if (row.get("excluded") or "false").strip().lower() != "true"]


def _progresso(i, total, largura=32):
    cheio = int(largura * i / total) if total else largura
    barra = "#" * cheio + "-" * (largura - cheio)
    sys.stdout.write(f"\r  [{barra}] {i}/{total}")
    sys.stdout.flush()


def preencher(manifest, pre=PRE_CHROMA, limite=None, force=False):
    """
    Preenche o cache das faixas do manifest. Uma falha não aborta o lote.

    Devolve (gerados, reaproveitados, falhas), onde falhas é uma lista de
    (track_id, mensagem).
    """
    linhas = _linhas_do_manifest(manifest)
    if limite is not None:
        linhas = linhas[:limite]

    gerados = reaproveitados = 0
    falhas = []
    total = len(linhas)
    t0 = time.perf_counter()

    for i, row in enumerate(linhas, start=1):
        track_id = row.get("track_id") or row.get("audio_path", "?")
        audio = ROOT / row["audio_path"]
        try:
            ja_tinha = (not force) and cache_path(audio, pre).exists()
            get_features(audio, pre, force=force)
            if ja_tinha:
                reaproveitados += 1
            else:
                gerados += 1
        except Exception as exc:                      # segue o lote
            falhas.append((track_id, f"{type(exc).__name__}: {exc}"))
        _progresso(i, total)

    print()
    dt = time.perf_counter() - t0
    print(f"  gerados        : {gerados}")
    print(f"  reaproveitados : {reaproveitados}")
    print(f"  falhas         : {len(falhas)}")
    for track_id, msg in falhas:
        print(f"    {track_id}: {msg}")
    print(f"  tempo          : {dt:.1f}s"
          + (f" ({dt/total:.1f}s por faixa)" if total else ""))
    return gerados, reaproveitados, falhas


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Preenche o cache de Features das faixas de um manifest.")
    ap.add_argument("--manifest", required=True,
                    help="CSV em data/manifests/ (linhas excluded=true são puladas)")
    ap.add_argument("--limit", type=int, default=None,
                    help="processa só as N primeiras faixas")
    ap.add_argument("--force", action="store_true",
                    help="recalcula mesmo que o cache exista")
    args = ap.parse_args(argv)

    print(f"cache em {_rel(CACHE_DIR)}/  |  manifest {args.manifest}")
    preencher(args.manifest, PRE_CHROMA, limite=args.limit, force=args.force)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
