"""
tests/test_curvas.py
====================
Testes das curvas de acerto × cobertura, da figura e do congelamento.

O risco aqui é a figura do artigo mostrar uma curva que não existe no CSV, ou
o congelamento divergir do código depois de commitado. Os dois são silenciosos:
o PDF sai bonito de qualquer forma, e o documento não reclama.

Usam áudio sintético e CSVs minúsculos; não dependem de `data/extracted/`.

    pytest tests/test_curvas.py
"""

import csv
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import congelar  # noqa: E402
import curvas  # noqa: E402
import figura_curvas as fig  # noqa: E402
import runner  # noqa: E402


# ==========================================================================
# A varredura
# ==========================================================================
def test_pontos_cobrem_o_que_foi_pedido():
    pontos = curvas._pontos()
    por_curva = {}
    for curva, param, valor, _ in pontos:
        por_curva.setdefault(curva, []).append((param, valor))

    assert [v for p, v in por_curva["C"]] == [0.00, 0.50, 0.55, 0.60, 0.65,
                                              0.70, 0.75, 0.80, 0.85, 0.90]
    assert all(p == "confidence_gate" for p, _ in por_curva["C"])
    esperado_lp = [-1.0, -1.5, -2.0, -2.5, -3.0, -4.0, -5.0, -6.0, -8.0, -1e9]
    for curva in ("D", "F"):
        assert [v for p, v in por_curva[curva]] == esperado_lp
        assert all(p == "n_logprob" for p, _ in por_curva[curva])
    assert len(por_curva["V4"]) == 1


def test_cada_ponto_muda_so_o_parametro_da_curva():
    """Uma curva que variasse dois campos não seria uma curva."""
    base = {"C": runner.VARIANTES["C"], "D": runner.VARIANTES["D"],
            "F": runner.VARIANTES["F"]}
    for curva, param, valor, variante in curvas._pontos():
        if curva == "V4":
            continue
        b = base[curva]
        assert variante.vocab == b.vocab
        assert variante.pre == b.pre
        diferentes = [f for f in type(b.post).__dataclass_fields__
                      if getattr(b.post, f) != getattr(variante.post, f)]
        assert diferentes in ([], [param]), (
            f"{curva} valor={valor} mudou {diferentes}")


def test_curva_C_usa_o_gate_e_D_usa_o_viterbi():
    """Guarda contra trocar os eixos: C sem Viterbi, D e F com."""
    for curva, _, _, v in curvas._pontos():
        if curva == "C":
            assert v.post.use_viterbi is False
        elif curva in ("D", "F"):
            assert v.post.use_viterbi is True


# ==========================================================================
# A agregação da figura
# ==========================================================================
@pytest.fixture
def csv_minimo(tmp_path):
    """Duas faixas de durações diferentes, para checar a ponderação."""
    caminho = tmp_path / "curvas_teste.csv"
    with caminho.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=curvas.CSV_FIELDS)
        w.writeheader()
        base = {k: "" for k in curvas.CSV_FIELDS}
        # ponto de cobertura 1.0: faixa de 10 s com 0.9 e faixa de 30 s com 0.5
        for tid, dur, acerto in [("a", 10.0, 0.9), ("b", 30.0, 0.5)]:
            w.writerow({**base, "curva": "C", "valor": "0.0", "track_id": tid,
                        "duracao_s": dur, "cobertura": 1.0,
                        "acerto_rotulado_root": acerto,
                        "acerto_rotulado_majmin": acerto,
                        "acerto_total_root": acerto,
                        "acerto_total_majmin": acerto})
    return caminho


def test_agregacao_e_ponderada_pela_duracao(csv_minimo):
    """(0.9*10 + 0.5*30)/40 = 0.60, não a média simples 0.70."""
    curvas_agregadas = fig.agregar(csv_minimo)
    ponto = curvas_agregadas["C"][0]
    assert ponto["rotulado"]["root"] == pytest.approx(0.60)
    assert ponto["cobertura"] == pytest.approx(1.0)


def test_figura_sai_em_pdf_vetorial(csv_minimo, tmp_path):
    destino = tmp_path / "fig.pdf"
    fig.desenhar(fig.agregar(csv_minimo), destino)

    dados = destino.read_bytes()
    assert dados[:5] == b"%PDF-", "não saiu PDF"
    # sem imagem raster: um gráfico de linhas rasterizado perderia a escala
    assert b"/Subtype /Image" not in dados and b"/Subtype/Image" not in dados
    assert b"/DCTDecode" not in dados


def test_figura_respeita_o_formato_pedido():
    assert fig.LARGURA_POL == 3.5, "largura de uma coluna IEEE"
    assert fig.FONTE >= 8, "fonte mínima de 8 pt"
    assert fig.NIVEIS == ["root", "majmin"]


def test_celula_vazia_nao_entra_na_media(tmp_path):
    """
    Quando a cobertura é 0, o acerto no tempo rotulado vem vazio (não zero).
    Entrar como zero puxaria a curva para baixo com um valor inventado.
    """
    caminho = tmp_path / "curvas_vazio.csv"
    with caminho.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=curvas.CSV_FIELDS)
        w.writeheader()
        base = {k: "" for k in curvas.CSV_FIELDS}
        w.writerow({**base, "curva": "C", "valor": "0.9", "track_id": "a",
                    "duracao_s": 10.0, "cobertura": 0.0,
                    "acerto_rotulado_root": "", "acerto_rotulado_majmin": "",
                    "acerto_total_root": 0.0, "acerto_total_majmin": 0.0})
        w.writerow({**base, "curva": "C", "valor": "0.9", "track_id": "b",
                    "duracao_s": 10.0, "cobertura": 0.5,
                    "acerto_rotulado_root": 0.8, "acerto_rotulado_majmin": 0.8,
                    "acerto_total_root": 0.4, "acerto_total_majmin": 0.4})
    ponto = fig.agregar(caminho)["C"][0]
    assert ponto["rotulado"]["root"] == pytest.approx(0.8)


# ==========================================================================
# O congelamento
# ==========================================================================
def test_congelamento_lista_as_seis_configuracoes():
    assert congelar.CONGELADAS == ["V4", "C", "D", "E", "F0rg", "D0rg"]
    for nome in congelar.CONGELADAS:
        assert nome in runner.VARIANTES
        assert nome in congelar.JUSTIFICATIVA


def test_congelamento_traz_todos_os_campos_de_config():
    texto = congelar.gerar()
    from config import PreChromaConfig, PostChromaConfig
    for campo in list(PreChromaConfig.__dataclass_fields__) + \
            list(PostChromaConfig.__dataclass_fields__):
        assert f"`{campo}`" in texto, f"campo {campo} ausente do congelamento"
    for nome in congelar.CONGELADAS:
        assert f"`{nome}`" in texto
    assert "commit" in texto.lower()


def test_congelamento_no_disco_bate_com_o_codigo():
    """
    Se este teste falhar, uma configuração mudou depois de congelada. O
    conserto é entender a mudança, não rodar `python congelar.py` por reflexo.

    A comparação ignora as linhas de proveniência (data e commit): elas mudam
    a cada execução e a cada commit, e comparar o hash faria o teste falhar
    para sempre depois do primeiro commit do documento.
    """
    assert congelar.main(["--check"]) == 0, (
        "docs/CONGELAMENTO.md divergiu das variantes em runner.py")


def test_check_ignora_proveniencia_mas_nao_configuracao():
    """
    O `--check` tem de ser cego à data e ao commit, e sensível a qualquer
    mudança nas tabelas de configuração.
    """
    doc = congelar.gerar()

    trocado = doc.replace("- Gerado em: ", "- Gerado em: 1999-01-01 ")
    trocado = trocado.replace("Commit que define estas configurações: `",
                              "Commit que define estas configurações: `outro")
    assert congelar._so_conteudo(trocado) == congelar._so_conteudo(doc)

    # já uma mudança de valor de campo tem de aparecer
    alterado = doc.replace("| `min_dur` |", "| `min_dur_trocado` |")
    assert congelar._so_conteudo(alterado) != congelar._so_conteudo(doc)


def test_congelamento_nao_promete_split_test_rodado():
    texto = congelar.gerar()
    assert "não foi lido" in texto
    assert "uma única vez" in texto
