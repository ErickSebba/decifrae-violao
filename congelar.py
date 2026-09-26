"""
congelar.py
===========
Gera `docs/CONGELAMENTO.md`: as configurações que irão ao split de teste, com
todos os campos e o commit que as define.

Existe como script, e não como documento escrito à mão, por dois motivos:
nenhum número do artigo é digitado (CLAUDE.md), e um congelamento que divirja
do código não congela nada. Rodar de novo e obter um diff significa que uma
configuração mudou depois de congelada.

    python congelar.py            # escreve docs/CONGELAMENTO.md
    python congelar.py --check    # só confere se o arquivo está atualizado
"""

import argparse
import subprocess
import sys
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

import runner
from config import PreChromaConfig, PostChromaConfig

ROOT = Path(__file__).resolve().parent
DESTINO = ROOT / "docs" / "CONGELAMENTO.md"

# As configurações que vão ao teste, na ordem em que aparecerão na tabela.
CONGELADAS = ["V4", "C", "D", "E", "F0rg", "D0rg"]

JUSTIFICATIVA = {
    "V4": "baseline do projeto, intocado (`legacy_v4.py`).",
    "C": "melhor acerto no tempo rotulado (74,7 % em root), ao custo de "
         "abster-se em 39,5 % do tempo.",
    "D": "o pipeline com Viterbi sem absorção de segmentos curtos; melhor que "
         "E em todos os níveis na validação.",
    "E": "a configuração atual do sistema em produção. Entra para que o artigo "
         "reporte o que o Decifraê faz hoje, não só o melhor achado.",
    "F0rg": "melhor acerto sobre a faixa toda em root e sevenths "
            "(vocabulário BASIC, sem nenhuma fonte de N).",
    "D0rg": "melhor acerto sobre a faixa toda em majmin e mirex na camada "
            "chord[1] (vocabulário MEDIUM, sem nenhuma fonte de N).",
}


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, timeout=30).stdout.strip()


def _commit():
    return {"commit": _git("rev-parse", "HEAD"),
            "curto": _git("rev-parse", "--short", "HEAD"),
            "suja": bool(_git("status", "--porcelain"))}


def _valor(v):
    if v == "" or v is None:
        return "—"
    if isinstance(v, float) and v <= -1e8:
        return "−1e9"
    return str(v)


def gerar():
    info = _commit()
    pre_campos = [f.name for f in fields(PreChromaConfig)]
    post_campos = [f.name for f in fields(PostChromaConfig)]

    linhas = []
    add = linhas.append
    add("# Congelamento das configurações para o conjunto de teste")
    add("")
    add("> **Gerado por `python congelar.py`. Não editar à mão.** Rodar o")
    add("> script de novo e obter um diff significa que uma configuração mudou")
    add("> depois de congelada — nesse caso o congelamento é que está errado,")
    add("> não o script.")
    add("")
    add(f"- Gerado em: {datetime.now().isoformat(timespec='seconds')}")
    add(f"- Commit que define estas configurações: `{info['commit']}`")
    add(f"- Árvore suja na geração: **{'sim' if info['suja'] else 'não'}**")
    add("")
    add("O conjunto de teste (60 excertos dos músicos 04 e 05) **não foi lido**")
    add("até este ponto. Toda a busca e todo o ajuste rodaram no split `val`")
    add("(120 excertos, músicos 00–03), como manda o `CLAUDE.md`. Este")
    add("documento existe para fixar o que vai ser medido **antes** de medir:")
    add("sem ele, qualquer escolha feita depois de ver o teste é ajuste")
    add("disfarçado de resultado.")
    add("")
    add("## 1. As configurações")
    add("")
    add("| Configuração | Motor | Vocabulário | Por que entra |")
    add("|---|---|---|---|")
    for nome in CONGELADAS:
        v = runner.VARIANTES[nome]
        add(f"| `{nome}` | {v.motor} | {v.vocab} | {JUSTIFICATIVA[nome]} |")
    add("")
    add("## 2. Campos pré-chroma")
    add("")
    add("Etapa cara (HPSS, beat track, CQT). O `V4` não usa esta configuração:")
    add("tem o caminho próprio dele, com `margin=3.0` e `bins_per_octave=36`")
    add("literais dentro de `legacy_v4.run_beat_tracking`.")
    add("")
    add("| Campo | " + " | ".join(f"`{n}`" for n in CONGELADAS) + " |")
    add("|---" * (len(CONGELADAS) + 1) + "|")
    for campo in pre_campos:
        celulas = []
        for nome in CONGELADAS:
            v = runner.VARIANTES[nome]
            celulas.append(_valor(asdict(v.pre)[campo] if v.pre else ""))
        add(f"| `{campo}` | " + " | ".join(celulas) + " |")
    add("")
    add("## 3. Campos pós-chroma")
    add("")
    add("Etapa barata (gate de silêncio, emissão, Viterbi, merge, absorção).")
    add("Três destes campos configuram o **classificador**, não o `decode`:")
    add("`complexity_penalty`, `ext_sharpness` e `confidence_gate`.")
    add("")
    add("| Campo | " + " | ".join(f"`{n}`" for n in CONGELADAS) + " |")
    add("|---" * (len(CONGELADAS) + 1) + "|")
    for campo in post_campos:
        celulas = []
        for nome in CONGELADAS:
            v = runner.VARIANTES[nome]
            celulas.append(_valor(asdict(v.post)[campo] if v.post else ""))
        add(f"| `{campo}` | " + " | ".join(celulas) + " |")
    add("")
    add("## 4. Protocolo do teste")
    add("")
    add("1. O split `test` é lido **uma única vez**, com")
    add("   `python runner.py --manifest data/manifests/guitarset_comping.csv`")
    add("   `--splits test --variants " + ",".join(CONGELADAS) + "`.")
    add("2. As duas camadas de anotação (`--ref-layer 0` e `--ref-layer 1`) são")
    add("   reportadas. A camada principal é a `chord[1]`, conforme")
    add("   `docs/DATASETS.md` §2.")
    add("3. As duas faixas com timing incorreto seguem excluídas pelo manifest")
    add("   (`excluded=true`), então o teste tem 58 excertos pontuados de 60.")
    add("4. Nada é ajustado depois. Se o resultado do teste sugerir outra")
    add("   configuração, isso é trabalho para outro conjunto de dados, não")
    add("   uma revisão deste número.")
    add("")
    return "\n".join(linhas) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gera docs/CONGELAMENTO.md.")
    ap.add_argument("--check", action="store_true",
                    help="não escreve; sai com código 1 se estiver desatualizado")
    args = ap.parse_args(argv)

    novo = gerar()
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        # a linha "Gerado em" muda a cada execução: ignorada na comparação
        def sem_data(t):
            return "\n".join(l for l in t.splitlines()
                             if not l.startswith("- Gerado em:"))
        if sem_data(novo) != sem_data(atual):
            print("docs/CONGELAMENTO.md está DESATUALIZADO em relação ao código")
            return 1
        print("docs/CONGELAMENTO.md está atualizado")
        return 0

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(novo, encoding="utf-8")
    print(f"escrito {DESTINO.relative_to(ROOT).as_posix()} "
          f"({len(CONGELADAS)} configurações)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
