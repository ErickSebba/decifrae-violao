"""
tests/test_dataset_io.py
========================
Testes dos adaptadores de anotação externa e dos manifests.

O que importa aqui é a forma da saída: o runner vai varrer estas listas
assumindo que são ordenadas, contíguas e que cobrem a faixa inteira. Uma
lacuna silenciosa viraria tempo não pontuado, e o erro apareceria como uma
métrica levemente otimista, difícil de rastrear depois.

Depende dos dados extraídos em `data/extracted/` (não versionados); os testes
fazem skip quando eles não estão no disco.

Como rodar (de dentro de `Decifra-Violão/`):

    pytest tests/test_dataset_io.py
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import dataset_io as ds  # noqa: E402
from evaluate import score_segments  # noqa: E402

# Três JAMS de músicos diferentes + o único .lab de guitar/.
JAMS_AMOSTRA = [
    "00_BN1-129-Eb_comp.jams",
    "03_Rock1-130-A_comp.jams",
    "05_SS1-100-C#_comp.jams",
]
LAB = ds.IDMT_ROOT / "guitar" / "guitar_annotation.lab"

# Folga usada nas comparações de borda, a mesma do adaptador.
EPS = ds.EPS


def _carrega_jams(nome):
    caminho = ds.GUITARSET_ANNOT / nome
    if not caminho.exists():
        pytest.skip(f"anotação ausente: {caminho}")
    return ds.load_guitarset(caminho)


def _duracao_jams(nome):
    import json
    with (ds.GUITARSET_ANNOT / nome).open(encoding="utf-8") as fp:
        return json.load(fp)["file_metadata"]["duration"]


def _verifica_forma(segs, duracao_esperada):
    assert segs, "lista de segmentos vazia"
    assert segs[0][0] == pytest.approx(0.0, abs=EPS), "não começa em 0"
    for i, (start, end, label) in enumerate(segs):
        assert end > start, f"segmento {i} não tem duração positiva"
        assert isinstance(label, str) and label, f"segmento {i} sem rótulo"
    for i in range(len(segs) - 1):
        assert segs[i][1] == pytest.approx(segs[i + 1][0], abs=EPS), (
            f"descontinuidade entre os segmentos {i} e {i+1}: "
            f"{segs[i][1]} != {segs[i+1][0]}"
        )
    assert segs[-1][1] == pytest.approx(duracao_esperada, abs=1e-6), (
        f"cobertura termina em {segs[-1][1]}, esperado {duracao_esperada}"
    )


# ==========================================================================
# Forma da saída
# ==========================================================================
@pytest.mark.parametrize("nome", JAMS_AMOSTRA)
def test_guitarset_contiguo_ordenado_e_completo(nome):
    segs = _carrega_jams(nome)
    _verifica_forma(segs, _duracao_jams(nome))


def test_idmt_contiguo_ordenado_e_completo():
    if not LAB.exists():
        pytest.skip(f"anotação ausente: {LAB}")
    segs = ds.load_idmt_lab(LAB)
    # O .lab não declara duração; a referência é o áudio que ele anota.
    wav = ds.IDMT_ROOT / "guitar" / "ableton_live_guitar_Campfire.wav"
    if not wav.exists():
        pytest.skip(f"áudio ausente: {wav}")
    import soundfile as sf
    _verifica_forma(segs, sf.info(str(wav)).duration)


def test_rotulos_saem_em_harte_sem_traducao():
    """
    Os rótulos têm de chegar como estão no arquivo. Se alguém plugar a
    tradução do projeto no caminho, estes dois padrões somem.
    """
    segs = _carrega_jams(JAMS_AMOSTRA[0])
    labels = [lab for _, _, lab in segs]
    assert any(':' in lab for lab in labels), "nenhum rótulo em notação Harte"
    assert any('/' in lab for lab in labels), "as inversões foram perdidas"


# ==========================================================================
# A ponte com o evaluate
# ==========================================================================
def test_score_segments_precisa_de_ref_is_harte():
    """
    Com a referência em Harte, `ref_is_harte=True` pontua; o default traduz a
    referência, vira 'X' e o mir_eval ignora tudo. Este teste existe para que
    esquecer o parâmetro no runner apareça como falha, não como número bonito.
    """
    ref = [(0.0, 2.0, 'C:maj/1'), (2.0, 4.0, 'A:min7')]
    est = [(0.0, 2.0, 'C'), (2.0, 4.0, 'Am7')]

    com = score_segments(est, ref, levels=['root'], ref_is_harte=True)
    sem = score_segments(est, ref, levels=['root'])

    assert com['root'] == pytest.approx(1.0)
    assert sem['root'] == pytest.approx(0.0)


def test_default_do_score_segments_nao_mudou():
    """O GT do projeto continua sendo traduzido como sempre."""
    gt = [(0.0, 2.0, 'C'), (2.0, 4.0, 'Am'), (4.0, 6.0, 'E7'), (6.0, 8.0, 'N')]
    assert score_segments(gt, gt)['sevenths'] == pytest.approx(1.0)


# ==========================================================================
# Manifests
# ==========================================================================
def test_manifests_tem_as_colunas_e_os_splits_certos():
    if not ds.GUITARSET_AUDIO.exists():
        pytest.skip("GuitarSet não extraído")
    linhas = ds.guitarset_rows()

    assert len(linhas) == 180
    assert all(list(l) == ds.MANIFEST_FIELDS for l in linhas)
    for l in linhas:
        esperado = "val" if l["player_id"] in {"00", "01", "02", "03"} else "test"
        assert l["split"] == esperado
        assert not os.path.isabs(l["audio_path"])
        assert not os.path.isabs(l["annotation_path"])

    excluidas = {l["track_id"] for l in linhas if l["excluded"] == "true"}
    assert excluidas == set(ds.GUITARSET_EXCLUDED)
    for l in linhas:
        if l["excluded"] == "true":
            assert l["exclude_reason"], f"{l['track_id']} sem motivo"


def test_manifest_idmt_e_eval():
    if not ds.IDMT_ROOT.exists():
        pytest.skip("IDMT não extraído")
    linhas = ds.idmt_rows()
    assert len(linhas) == 6
    assert {l["split"] for l in linhas} == {"eval"}
    assert all(l["excluded"] == "false" for l in linhas)
