# Adendo da revisão (camera-ready)

> Registro das configurações novas pedidas pelos revisores do ACDSA 2027.
> Não altera `docs/CONGELAMENTO.md` nem `docs/ADENDO_CONGELAMENTO.md`. Todos os
> valores abaixo foram escolhidos **só no split de validação** e este arquivo é
> commitado **antes** de qualquer execução das variantes novas no teste.
> Todas as análises desta fase são **pós-especificadas** (`post_review=true`
> no meta.json de cada CSV).

- Escrito em: 2026-11-16
- Branch: `revisao-camera-ready`
- Fonte de todos os números: `data/results/calibracao_revisao_20261116_231220.csv`
  (+ `_meta.json`), gerado por `calibracao_revisao.py`, split `val` (120 faixas,
  executantes 00–03), médias ponderadas pela duração da referência.
- Desempate fixado antes de rodar: menor |valor − default de `config.py`|,
  depois o menor valor. Não foi necessário em nenhuma das quatro escolhas.

## 1. Variantes fatoriais (sem escolha de valor)

Completam o fatorial 2×2×2 decodificador × abstenção própria × gate relativo.

| variante | definição em `runner.py` |
|---|---|
| `Crg` | C com `rel_gate = 0` (mantém `confidence_gate = 0,72`) |
| `Drg` | D com `rel_gate = 0` (mantém `n_logprob = −2,5`) |

As outras seis células (`C`, `C0`, `C0rg`, `D`, `D0`, `D0rg`) já existiam.

## 2. Cobertura igualada

Cobertura = 1 − fração do tempo estimada como `N` (independe da camada).
Na validação: cobertura de **C = 60,46 %**, de **D = 87,87 %**.

| variante | parâmetro varrido | grade | critério | valor escolhido | cobertura obtida | alvo |
|---|---|---|---|---|---|---|
| `Cmatch` | `confidence_gate` de C | 0,50…0,90, passo 0,01 | argmin \|cob(C,θ) − cob(D)\| | **θ\* = 0,65** | 88,45 % | 87,87 % |
| `Dmatch` | `n_logprob` de D | −1…−8, passo 0,25 | argmin \|cob(D,β) − cob(C)\| | **β\* = −2,25** | 66,42 % | 60,46 % |

Limitação registrada: a cobertura de D cai de forma íngreme entre β = −2,5
(87,87 %) e β = −2,0 (41,34 %); na grade pedida, o ponto mais próximo
(−2,25) fica 5,96 pontos acima do alvo. O casamento de C (0,58 ponto) é bem
mais fino que o de D. A grade **não** foi refinada depois de ver isso.

## 3. Penalidade de transição calibrada

`change_penalty` ∈ {0,5; 1; 1,5; 2; 2,5; 3; 4; 6}, critério: maior `root` na
faixa toda, camada chord[0] (a curva em chord[1] é idêntica no nível `root`
e escolheria o mesmo valor).

| cp | 0,5 | 1,0 | 1,5 | 2,0 | 2,5 | 3,0 | 4,0 | 6,0 |
|---|---|---|---|---|---|---|---|---|
| `D0rg` (60) root % | 66,39 | 66,59 | **66,78** | 65,80 | 64,69 | 63,43 | 60,66 | 53,93 |
| `F0rg` (24) root % | 70,47 | **70,52** | 70,25 | 69,15 | 68,27 | 67,02 | 63,98 | 56,75 |

| variante | definição | valor escolhido |
|---|---|---|
| `D0rg_cal` | D0rg com `change_penalty` calibrado | **1,5** |
| `F0rg_cal` | F0rg com `change_penalty` calibrado | **1,0** |

O default congelado (2,0) não era o ótimo em nenhum dos dois vocabulários; o
ganho na validação é de +0,98 (D0rg) e +1,37 (F0rg) ponto, e é ganho **dentro
da amostra** de calibração — só o teste o mede.

## 4. Execução prevista no teste (uma vez)

`runner.py --splits test --post-review` com `Crg, Drg, C0, D0, Cmatch, Dmatch,
D0rg_cal, F0rg_cal`, nas camadas chord[0] e chord[1], um commit entre as duas.
As mesmas seis variantes novas rodam também no val, nas duas camadas, antes do
teste. Nenhum valor deste adendo é revisto depois da leitura do teste.

## 5. Curvas de acerto × cobertura no teste (protocolo, 2026-11-17)

Registrado e commitado **antes** de rodar. Análise pós-especificada
(`post_review=true`), sem escolha de nenhum valor: não há calibração no teste.

- Script: `curvas_teste_revisao.py`; split `test` (58 faixas), camada chord[0],
  nível `root`.
- Curva C: variante C com `confidence_gate` ∈ {0} ∪ {0,50; 0,51; …; 0,90}.
- Curva D: variante D com `n_logprob` ∈ {−1; −1,25; …; −8} ∪ {−1e9}.
- Demais campos como em `runner.VARIANTES["C"]`/`["D"]` (inclusive
  `rel_gate = 0,2`).
- Por ponto e faixa: cobertura (1 − `frac_n_est`), `root_rotulado` e `root`
  na faixa toda. Agregação por ponto: média ponderada pela duração da faixa
  (`root_rotulado` exclui as faixas em que a cobertura é zero).
- Comparação na mesma cobertura: para cada curva, interpolação linear da
  métrica agregada em função da cobertura agregada (pontos ordenados por
  cobertura), nos alvos **60 %, 70 %, 77 % e 90 %**. Δ = D − C.
- IC 95 %: bootstrap pareado por faixa (10 000 reamostragens, seed 0); em
  cada reamostragem as duas curvas são reagregadas com os mesmos pesos e
  reinterpoladas. Alvo fora do intervalo de cobertura de uma curva numa
  reamostragem → reamostragem descartada para aquele alvo, e o número de
  reamostragens válidas é reportado.
- Saídas: `data/results/curvas_teste_<ts>.csv` (uma linha por curva, ponto e
  faixa), `data/results/cobertura_igualada_teste_<ts>.csv` (resumo),
  `artigo-ACDSA/tabelas/tab_cobertura_igualada.tex`,
  `artigo-ACDSA/figuras/fig_cobertura_teste.pdf/.png` (3,5 pol, fonte 8 pt).

## 6. Procedência das ablações de teste `20261116_231650` e `_231706` (2026-11-17)

As duas execuções únicas do teste pós-revisão gravaram `arvore_suja: true`.
Verificado depois, a partir do Git:

- `_231650_ref0` registra o commit `a380774`; `_231706_ref1`, o `b5065ef`. Entre
  os dois commits a única diferença é o próprio CSV/meta do chord[0]
  (`git diff --stat a380774 b5065ef`).
- Nenhum arquivo `.py` rastreado diferia do commit gravado: entre `a380774` e
  `bc001a8` os únicos `.py` que mudam são os quatro `analise_*.py`, **criados**
  depois das execuções e não importados por `runner.py`.
- O que sujava a árvore: (i) arquivos **não rastreados** do usuário
  (`artigo-ACDSA/slides-ACDSA/`, `artigo-ACDSA/slides-ACDSA.zip` e zips em
  `data/`), e (ii) uma alteração **rastreada e não commitada** do usuário em
  `artigo-ACDSA/RESULTADOS.md` (legendas de figuras), commitada só em
  `bc001a8`. Nenhum dos dois é lido pelo pipeline.

Conclusão: o código que produziu as duas ablações é exatamente o dos commits
gravados no meta. Os CSVs não foram regenerados, porque isso seria uma segunda
leitura do teste.

## 7. Refinamento da curva D no teste (protocolo, 2026-11-17)

Registrado e commitado antes de rodar. Na execução do §5, a curva D tinha só
três pontos entre 58 % e 89 % de cobertura (`n_logprob` −2,25 → 58,32 %,
−2,5 → 77,12 %, −2,75 → 89,26 %). Acrescentam-se os pontos
`n_logprob` ∈ {−2,30; −2,35; …; −2,70} (passo 0,05; 8 pontos novos, porque −2,50 já existia) entre
−2,25 e −2,75. A grade passa a ter 38 pontos em D; C, alvos (60, 70, 77 e 90 %),
interpolação, bootstrap (10 000, seed 0) e saídas são os do §5. O CSV antigo
não é sobrescrito; `tab_cobertura_igualada.tex` e `fig_cobertura_teste` são
regenerados a partir do CSV novo. Nenhum valor é escolhido.

## 8. Bases externas e baselines (protocolo, 2026-11-17)

Registrado e commitado **antes** de qualquer execução nas bases externas.
Análise pós-especificada (`post_review=true` em todo CSV).

**Regra: nenhuma configuração é ajustada fora do GuitarSet.** Rodam só as
variantes já congeladas, com os valores de `runner.VARIANTES` no commit deste
protocolo: `V4`, `V4b`, `C`, `D`, `E`, `C0rg`, `D0rg`, `F0rg` (as oito que os
15 contrastes de `stats.PARES` exigem). Nenhum hiperparâmetro, limiar,
vocabulário ou grade é escolhido ou revisto a partir dessas bases.

**Bases.**
- IDMT-SMT-Guitar V2, subconjunto 4 (`data/manifests/idmt_smt_guitar.csv`,
  `split=external`): todas as faixas com áudio e anotação de acordes
  pareados; o par cujo nome não casa (`Career SG/fast/rock_blues`,
  áudio `rock_1_120BPM` × anotação `rock_1_100BPM`) fica excluído no manifest.
  Rótulos traduzidos para Harte pelo adaptador `dataset_io.load_idmt_guitar`;
  as convenções (fim do último acorde, rótulos não traduzíveis → `X`) estão
  no docstring dele.
- IDMT-SMT-Chords, só `guitar/` (`data/manifests/idmt_smt_chords.csv`,
  `split=eval`, 6 faixas).
- Nas bases externas há uma referência só; os CSVs levam o sufixo `_ref0`
  apenas por convenção de nome do `runner.py`.

**Baselines de terceiros**, sem nenhum ajuste:
- Chordino (NNLS Chroma, Vamp) via Sonic Annotator 1.7, transform
  `vamp:nnls-chroma:chordino:simplechord` com os parâmetros default
  congelados em `baselines/chordino_simplechord.n3`; rótulos traduzidos para
  Harte por `baselines_externos.parse_chordino`.
- madmom CNN + CRF de acordes maior/menor (Korzeniowski & Widmer 2016), modelo
  pré-treinado do pacote (madmom 0.17.dev0, commit `27f032e`), em ambiente
  separado (Python 3.10); script `baselines/madmom_acordes.py`.
- Rodam em: GuitarSet `val` e `test` (camadas chord[0] e chord[1]) e nas duas
  bases externas.

**Métricas e estatística.** As mesmas colunas de `runner.CSV_FIELDS`. Por base,
os 15 contrastes de `stats.PARES` com bootstrap pareado por faixa (10 000,
seed 0) e Holm sobre a família de 15 (`stats.py --post-review`). No
IDMT-SMT-Guitar, também Δ por guitarra (as quatro gravações) com IC por
bootstrap dentro da guitarra. Transferência: para cada contraste, se o sinal
de Δ no GuitarSet teste (chord[0]) se mantém em cada base externa. O
IDMT-SMT-Chords tem só 6 faixas; os IC dele são lidos como descritivos.

**Detalhes fixados antes de rodar** (adaptadores escritos e testados, sem
olhar resultado de nenhuma variante nas bases externas):
- IDMT-SMT-Guitar: 507 faixas no manifest, 1 excluída (a do nome que não casa),
  506 avaliáveis, 11 761,3 s anotados. Referência do primeiro tempo de batida
  ao último + 1 intervalo mediano (o dataset não anota o compasso de silêncio
  e os dois de sinal de controle iniciais). Footer (3 linhas inteiras: início
  e fim da sequência repetida e fórmula de compasso) ignorado.
- Sufixos do IDMT → Harte: `13` → `maj(13)` (notação aditiva; distingue `13`
  de `713`), `79` → `7(9)`, `min75b` → `hdim7`, `75b` → `7(*5,b5)`, `sus9` →
  `sus2`, demais no docstring de `dataset_io.IDMT_GUITAR_QUALITY`. `GB5` e
  `D/7Gb` (prováveis erros de digitação) viram `X` e o mir_eval os ignora; não
  são corrigidos. Sensibilidade registrada no meta da cobertura: com `13` →
  `maj6`, a cobertura de `sevenths` cairia de 0,856 para 0,817.
- Cobertura da referência por nível (origem:
  `data/results/coverage_externo_20261117_102831.csv`): IDMT-SMT-Guitar root
  0,998, majmin 0,870, sevenths 0,856, mirex 0,918 (N = 11,9 % do tempo);
  IDMT-SMT-Chords guitar root 1,000, majmin 0,714, sevenths 0,714, mirex 0,857.
- O beat tracking do pipeline tende a 90–120 BPM: em 3 faixas de conferência
  dobrou a de 60 BPM e dividiu por dois a de 180 BPM. **Não é corrigido**
  (seria ajuste fora do GuitarSet); fica como limitação.
- Avaliação dos baselines: os rótulos já em Harte passam direto pelo
  `evaluate._to_arrays` dentro de `baselines_externos._estimado_em_harte()`
  (o meta registra `est_is_harte: true`); `evaluate.py` e `runner.py` não
  mudam. Chordino: plugin versão 5, step 2048, block 16384, parâmetros default
  (boostn 0,1, rollon 0, s 0,7, tuningmode global, useNNLS 1, whitening 1).
- `runner.rodar` passa a carregar a referência por `dataset_io.load_reference`
  (despacho pelo campo `dataset`); no GuitarSet a chamada é idêntica à
  anterior (verificado em val, chord[0] e chord[1]; oráculo sem diff).

**Desvio registrado durante a execução (2026-11-17).** Na primeira avaliação
do madmom no IDMT-SMT-Guitar (`baseline_madmom_20261117_122212_ref0.csv`,
505 linhas), a faixa `acoustic_pickup_slow_folk_2_75BPM` falhou: a referência
começa em 9,600 s e o madmom tem uma fronteira exatamente em 9,600 s; o
`adjust_intervals` do mir_eval deixa um segmento de duração zero e o
`underseg` levanta `ValueError`. Correção em
`baselines_externos.fora_da_referencia`: descartar os segmentos estimados
inteiramente fora de [início, fim] da referência (o mir_eval já os corta).
Verificado neutro: reavaliados os 12 CSVs de baseline já commitados, zero
diferenças em root, majmin, sevenths, mirex, root_rotulado e segmentação; a
única mudança é a faixa recuperada. O CSV de 505 linhas fica (não se
sobrescreve) e é substituído pelo seguinte, de 506 linhas. Não afeta as
variantes do pipeline (nenhuma falha nas 8 × 506).

## 9. Diagnósticos de camera-ready (2026-11-17)

Nada é ajustado; só diagnóstico e formatação. Fixado antes de rodar.

### 9.1 O rótulo `13` do IDMT-SMT-Guitar

Pergunta: `13` é acorde dominante (então `7(9,13)`) ou não?

- **Fonte oficial:** `SMT_GUITAR_dataset_description.pdf` (§2.2.2, p. 10–11,
  na distribuição do dataset) só define o formato
  `chord_name/bass_note` e **não define os sufixos**. Não há outro documento
  na distribuição.
- **Evidência interna da notação:** o dataset usa `713` e `7913` como
  rótulos distintos de `13`, e em 3 das 8 formas com baixo o baixo é a 6ª
  (`E13/Db`, `A13/Gb`, `B13/Ab`).
- **Evidência acústica** (chroma do cache, média por trecho anotado,
  rotacionada para a tônica, normalizada): energia na 7ª menor nos trechos
  `13` = 0,034 (807 trechos), contra 0,026 no maior simples, 0,144 em `7` e
  0,188 em `713`; na 6ª/13ª, 0,245.
- **Decisão:** `13` **não** é dominante. O mapeamento `13` → `maj(13)` fica
  como está e **a base não é repontuada**. Peso: 5,00 % do tempo anotado
  (588,1 s em 63 faixas); `GB5` 0,05 % (3 faixas), `D/7Gb` 0,12 % (8 faixas).

### 9.2 Diagnóstico do estado N

Script `diagnostico_n.py`. Por base (GuitarSet teste, IDMT-SMT-Guitar,
IDMT-SMT-Chords guitar) e célula de batida i:
ℓ_i(k) = log softmax(e_i / temp)_k, exatamente como em `viterbi.decode`
(temp 0,1), com e_i = `classifier.emission` do classificador da variante.
Estatística: max_k ℓ_i(k) — mediana, IQR e fração de células abaixo de
β = −2,5 (o `n_logprob` da D). Contagem por célula (não ponderada por
duração). Variantes: D (60 templates; células forçadas a N pelo gate de RMS
ficam fora e são contadas à parte), D0rg com 60 (MEDIUM) e com 24 (BASIC,
que é o classificador da F0rg). D e D0rg-60 usam o mesmo classificador; só
o gate difere. Figura `fig_diagnostico_n` (3,5 pol): histogramas de D por
base, sobrepostos, com linha em β.

### 9.3 Beat tracking contra o andamento nominal (IDMT-SMT-Guitar)

Andamento estimado = 60 / mediana dos intervalos entre batidas do cache.
Razão r = estimado / nominal (do nome do arquivo). Classes: ~1 se
|r − 1| ≤ 0,08; ~2 se |r/2 − 1| ≤ 0,08; ~0,5 se |2r − 1| ≤ 0,08; senão
"outro". "Erro de oitava" = ~2 ∪ ~0,5.

**Os 6 contrastes principais** (um por par de `stats.PARES`, a métrica que
o par isola): C→D `root`; C0rg→D0rg `majmin`; D→E `overseg`; V4b→V4
`overseg`; V4→F0rg `majmin`; D0rg→F0rg `sevenths`. Para cada grupo (razão ~1
e erro de oitava): Δ médio ponderado por duração e IC 95 % do bootstrap
pareado por faixa (10 000, seed 0), **descritivo, sem Holm**; não muda
nenhuma classe.

### 9.4 Tabelas de uma coluna

`tab_principal.tex`: GuitarSet teste `chord[0]`, 8 variantes + Chordino +
madmom (root, root rotulado, cobertura e overseg são idênticos nas duas
camadas — verificado nas 464 linhas de ablação do teste; majmin e sevenths
são de `chord[0]`). `tab_transferencia_curta.tex`: os 6 contrastes
principais × 3 corpora, Δ e classe (✓ confirmado, = empate, ~ frágil), das
mesmas fontes da `tab_transferencia`.
