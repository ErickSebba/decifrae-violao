"""
tests/test_idmt_guitar.py
=========================
Adaptador do IDMT-SMT-Guitar V2 (subconjunto 4) e despachante de referência.

Os testes de parser usam CSVs sintéticos em tmp_path; os de varredura leem
todos os arquivos não excluídos das duas bases externas (IDMT-SMT-Guitar e
IDMT-SMT-Chords) e fazem skip se os dados não estiverem extraídos. Nenhum
teste abre o split `test` do GuitarSet.

    pytest tests/test_idmt_guitar.py
"""

import csv
import os
import sys
import warnings

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

warnings.filterwarnings("ignore")
import mir_eval  # noqa: E402

import dataset_io as ds  # noqa: E402

EPS = ds.EPS


# --------------------------------------------------------------------------
# Tradução de rótulos
# --------------------------------------------------------------------------
@pytest.mark.parametrize("sufixo,qualidade", sorted(ds.IDMT_GUITAR_QUALITY.items()))
def test_cada_sufixo(sufixo, qualidade):
    harte = ds.idmt_guitar_to_harte(f"C{sufixo}")
    assert harte == f"C:{qualidade}"
    mir_eval.chord.encode(harte)          # levanta se inválido


@pytest.mark.parametrize("idmt,harte", [
    ("NC", "N"),
    ("G", "G:maj"),
    ("Gbmin", "Gb:min"),
    ("D7/C", "D:7/b7"),
    ("D7/Gb", "D:7/3"),
    ("Gbmin75b/C", "Gb:hdim7/b5"),
    ("Dbmin/E", "Db:min/b3"),
    ("A/Db", "A:maj/3"),
    ("G5/A", "G:5/2"),
    ("E13/Db", "E:maj(13)/6"),
    ("B79b/Eb", "B:7(b9)/3"),
    ("Bb7913/Ab", "Bb:7(9,13)/b7"),
    ("Amin75b", "A:hdim7"),
    ("B75b", "B:7(*5,b5)"),
])
def test_rotulos_e_inversoes(idmt, harte):
    assert ds.idmt_guitar_to_harte(idmt) == harte


@pytest.mark.parametrize("idmt", ["GB5", "D/7Gb", "Hmin", "Cxyz", "C/H", ""])
def test_intraduziveis_viram_x(idmt):
    assert ds.idmt_guitar_to_harte(idmt) == "X"


# --------------------------------------------------------------------------
# Parser de arquivo
# --------------------------------------------------------------------------
def _csv(tmp_path, linhas):
    p = tmp_path / "x.csv"
    p.write_bytes(("\r\n".join(linhas) + "\r\n").encode("utf-8"))
    return p


def test_parser_rodape_ignorado_e_fim(tmp_path):
    p = _csv(tmp_path, [
        "10.0,1.1:G", "11.0,1.2", "12.0,1.3:D7/C", "13.0,1.4",
        "14.0,2.1:NC", "15.0,2.2",
        "1,1", "8,4", "4,4",
    ])
    batidas, rotulos, rodape = ds._parse_idmt_guitar(p)
    assert len(batidas) == 6
    assert rodape == ["1,1", "8,4", "4,4"]
    assert ds.load_idmt_guitar(p) == [
        (10.0, 12.0, "G:maj"),
        (12.0, 14.0, "D:7/b7"),
        (14.0, 16.0, "N"),               # 15 + intervalo mediano (1 s)
    ]


def test_parser_batida_truncada_conta(tmp_path):
    # linhas reais de acoustic_pickup: número da batida truncado ou sujo
    p = _csv(tmp_path, [
        "1.0,1.1:C", "2.0,1.", "3.0,1.3d", "4.0,1.:Amin", "5.0,1.4",
        "1,1", "4,4", "4,4",
    ])
    assert ds.load_idmt_guitar(p) == [(1.0, 4.0, "C:maj"),
                                      (4.0, 6.0, "A:min")]


def test_parser_primeira_batida_sem_rotulo_vira_n(tmp_path):
    p = _csv(tmp_path, ["1.0,1.1", "2.0,1.2:C", "3.0,1.3", "1,1", "4,4", "4,4"])
    assert ds.load_idmt_guitar(p) == [(1.0, 2.0, "N"), (2.0, 4.0, "C:maj")]


def test_parser_batida_depois_do_rodape_falha(tmp_path):
    p = _csv(tmp_path, ["1.0,1.1:C", "2.0,1.2", "1,1", "3.0,1.3"])
    with pytest.raises(ValueError):
        ds.load_idmt_guitar(p)


# --------------------------------------------------------------------------
# Varredura das duas bases externas
# --------------------------------------------------------------------------
def _linhas_externas():
    linhas = []
    if ds.IDMT_GUITAR_ROOT.exists():
        linhas += [r for r in ds.idmt_guitar_rows() if r["excluded"] != "true"]
    man = ds.MANIFESTS / "idmt_smt_chords.csv"
    if man.exists() and ds.IDMT_ROOT.exists():
        with man.open(encoding="utf-8", newline="") as fp:
            linhas += [r for r in csv.DictReader(fp) if r["excluded"] != "true"]
    return linhas


LINHAS = _linhas_externas()


@pytest.mark.skipif(not LINHAS, reason="bases externas não extraídas")
def test_manifest_idmt_guitar():
    rows = ds.idmt_guitar_rows()
    assert len(rows) == 507
    excl = [r for r in rows if r["excluded"] == "true"]
    assert [r["track_id"] for r in excl] == ["career-sg_fast_rock_1_120BPM"]
    assert excl[0]["exclude_reason"]
    assert {r["split"] for r in rows} == {"external"}
    assert {r["guitarra"] for r in rows} == {
        "Career SG", "Ibanez 2820", "acoustic_mic", "acoustic_pickup"}


@pytest.mark.skipif(not LINHAS, reason="bases externas não extraídas")
def test_contiguas_e_rotulos_validos_em_todas():
    problemas = []
    for row in LINHAS:
        segs = ds.load_reference(row)
        if not segs:
            problemas.append((row["track_id"], "vazio"))
            continue
        for s, e, lab in segs:
            if e - s <= EPS:
                problemas.append((row["track_id"], "segmento degenerado"))
            if lab != "X":
                try:
                    mir_eval.chord.encode(lab)
                except Exception as exc:  # noqa: BLE001
                    problemas.append((row["track_id"], f"{lab}: {exc}"))
        for (s0, e0, _), (s1, e1, _) in zip(segs, segs[1:]):
            if abs(e0 - s1) > EPS:
                problemas.append((row["track_id"], f"buraco/sobreposição em {e0}"))
            if not (s1 > s0 and e1 > e0):
                problemas.append((row["track_id"], "não monótono"))
    assert not problemas, problemas[:10]


@pytest.mark.skipif(not LINHAS, reason="bases externas não extraídas")
def test_despachante_igual_ao_loader_direto():
    for row in LINHAS:
        caminho = ds.ROOT / row["annotation_path"]
        direto = (ds.load_idmt_guitar(caminho)
                  if row["dataset"] == "idmt-smt-guitar"
                  else ds.load_idmt_lab(caminho))
        assert ds.load_reference(row) == direto


def test_despachante_guitarset_val():
    """Só o split val: o teste do GuitarSet não é aberto aqui."""
    man = ds.MANIFESTS / "guitarset_comping.csv"
    if not (man.exists() and ds.GUITARSET_ANNOT.exists()):
        pytest.skip("GuitarSet não extraído")
    with man.open(encoding="utf-8", newline="") as fp:
        rows = [r for r in csv.DictReader(fp)
                if r["split"] == "val" and r["excluded"] != "true"][:5]
    for row in rows:
        for index in (0, 1):
            assert ds.load_reference(row, index=index) == ds.load_guitarset(
                ds.ROOT / row["annotation_path"], index=index)


def test_despachante_dataset_desconhecido():
    with pytest.raises(ValueError):
        ds.load_reference({"dataset": "outro", "annotation_path": "x"})
