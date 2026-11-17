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
