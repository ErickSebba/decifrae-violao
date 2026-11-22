# Conferência dos números pós-revisão

- Data: 2026-11-16, branch `revisao-camera-ready`
- Escopo: `RESULTADOS.md` §7, `METODOLOGIA.md` §7, `docs/ADENDO_REVISAO.md`,
  `tabelas/tab_executantes.tex`, `tab_fatorial.tex`, `tab_decomposicao.tex`,
  `tab_vocabulario.tex` e o `post_review: true` dos 13 `_meta.json` novos.
- Método: um sub-agente que não escreveu nenhum desses arquivos recalculou cada
  número a partir do CSV de origem, numa passada única (≈ 790 números).

## Discrepâncias encontradas e corrigidas

| # | onde | escrito | correto (CSV) | origem |
|---|---|---|---|---|
| 1 | `RESULTADOS.md` R2.3 | "o gate relativo muda menos de 1 p.p. em qualquer célula" | D → Drg no teste: 49,39 → 50,42 (+1,03) | `fatorial_20261116_232328.csv` |
| 2 | `RESULTADOS.md` R2.1 | ganho de 24 "vem de dois executantes (01 e 02)" | três positivos: 01 +11,1, 02 +8,8, 05 +0,7 | `por_executante_20261116_232016.csv` |
| 3 | `ADENDO_REVISAO.md` §3 | D0rg cp 0,5 = 66,40 | 66,395 → 66,39 | `calibracao_revisao_20261116_231220.csv` |

As três foram corrigidas no texto. Não houve segunda conferência.

## Pendências registradas (não corrigidas)

- Os `_meta.json` das análises dos sub-agentes registram `arvore_suja: true`
  (commit `8ca8b2e`): rodaram com scripts ainda não commitados, que entram
  no commit desta revisão sem alteração.
- `Cmatch` não manteve a cobertura igualada no teste (+8,9 p.p. sobre D) e
  `Dmatch` ficou +5,96 p.p. acima do alvo já na validação (grade de 0,25).
- Precisão e revocação de sétimas e o Δ por executante são descritivos, sem IC.
- A tabela de cobertura igualada não tem `.tex`; está só em `RESULTADOS.md`.
- `fig_transicao` tem 3,37 pol de largura (corte "tight"), dentro da coluna de 3,5.

## Revisão das seções "Bases externas e baselines" (2026-11-17)

Uma passada por sub-agente novo, conferindo cada número contra
`externo_resumo_`, `transferencia_` e `transferencia_guitarra_20261117_122651.csv`,
as ablações, os `stats_` e os baselines. Tabelas `tab_externo` e
`tab_transferencia` bateram integralmente. Cinco correções no texto:

1. RESULTADOS §8.1: madmom sobre a melhor variante no IDMT-SMT-Guitar é
   +13,6 p.p. (76,73 − 63,18), não +13,5 (diferença de arredondados).
2. RESULTADOS §8.1: o IDMT-SMT-Chords tem 273 segmentos por faixa, mas 84
   rótulos distintos (não "273 acordes distintos").
3. RESULTADOS §8.4: "nenhuma variante alcança os baselines" restrito a `root`
   no GuitarSet e no IDMT-SMT-Guitar; no IDMT-SMT-Chords C0rg supera ambos em
   `majmin` e, no GuitarSet teste, F0rg e V4 superam o Chordino em `sevenths`.
4. METODOLOGIA §9.1: 261,3 min são os 507 WAV; as 506 avaliáveis somam
   260,9 min.
5. RESULTADOS §8.4: C0rg→D0rg `majmin` no IDMT-SMT-Guitar é frágil (IC
   [+0,30; +2,22]), não "indistinguível de zero".

Não conferido por falta de fonte em CSV: "Vamp Plugin Pack 2.0" e os BPM da
conferência de beat tracking (registrados no adendo §8, vindos da instalação
e do relatório do adaptador).

## Revisão dos números de camera-ready (2026-11-17)

Uma passada por sub-agente novo sobre RESULTADOS §8.5–8.7, adendo §9.1,
`tab_principal`, `tab_transferencia_curta` e BASELINES §9. Tabelas e números
do diagnóstico do N, do beat tracking e do rótulo `13` bateram. Correções:

1. Adendo §9.1: o `13` aparece em 13 formas, das quais 8 têm baixo; a 6ª é o
   baixo em 3 das **8** (não "3 das 13 formas com baixo").
2. RESULTADOS §8.7: a classe "outro" foi descrita por completo (30 entre
   1,25 e 1,40; 18 entre 0,70 e 0,85; 15 entre 0,55 e 0,70; 7 perto de 1,5;
   5 acima de 2), em vez de "sobretudo ~0,75 e ~1,25–1,33".
3. BASELINES §9: "Vamp Plugin Pack 2.0" não é verificável pelos arquivos de
   resultado; o texto passa a citar o caminho da instalação e o SHA-256 da
   DLL registrado nos metas.

## Revisão do pacote camera-ready (2026-11-21)

Uma passada por sub-agente novo sobre `camera-ready/CAMERA_READY.md` e
`RESPOSTA_REVISORES.md`: números contra CSV/md, afirmações proibidas, modelo
de seção e caminhos. Corrigido:

1. Holm de C→D `root` citado como 0,0011 (família de 11); na família de 15 é
   0,0015.
2. Primeira avaliação externa: `ac894a9` (11:08), não `1939cd6` (que é o
   Chordino no GuitarSet).
3. "Segmentação mantém sinal e classe" no IDMT-SMT-Guitar: o sinal se mantém
   em 15/15, mas os dois contrastes `seg` mudam de empate para confirmado;
   só os `overseg` mantêm a classe. Texto ajustado (resumo executivo, G5, G6,
   resumo do artigo, resposta aos revisores).
4. "Accuracy effects shrink or reverse": vale para os efeitos de
   decodificação e vocabulário; C→D `root_rotulado`, D→E `root` e
   D0rg→F0rg `root`/`majmin` continuam ou passam a confirmados no
   IDMT-SMT-Guitar. Texto restrito aos efeitos principais.
5. Duas frases limítrofes de equivalência reescritas: "appears only when…"
   (R2.3) e "segmentation contrasts are similar in both groups" (R4, G4).
6. Caminhos: três CSVs `stats_*` faltavam em `dados/`; `splits/` passou a
   `detalhes/splits/`.

Antes da montagem, também foram corrigidas fontes do repositório:
RESULTADOS R2.3 passou a usar a curva D refinada
(`cobertura_igualada_teste_20261117_011711.csv`), e METODOLOGIA §8 passou a
remeter à §9 sobre o IDMT-SMT-Chords.
