# Metodologia

Este documento descreve os dados, a referência de anotação, o pipeline, as
variantes ablacionadas, as métricas, o protocolo estatístico e as condições de
reprodutibilidade do estudo. Nenhum resultado é reportado aqui: valores de
configuração, contagens do conjunto de dados e estatísticas descritivas das
anotações aparecem porque definem o experimento; as medidas de desempenho estão
em `RESULTADOS.md`. As decisões registradas abaixo foram fixadas antes da
leitura do conjunto de teste, conforme `docs/CONGELAMENTO.md`.

---

## 1. Dados

### 1.1 Corpus e sinal

Os experimentos usam o GuitarSet (Zenodo, registro 3371780). O corpus contém,
para cada um dos seis músicos, 30 excertos gravados em duas versões: uma de
acompanhamento (*comping*) e uma de improviso (*solo*). Este estudo usa
**exclusivamente os 180 excertos de comping** — os 180 excertos de solo nunca
entram, em nenhum split e em nenhuma etapa, porque um improviso monofônico não
tem a estrutura harmônica vertical que o sistema se propõe a estimar. Os
arquivos de áudio de comping usam o sufixo `_comp_mic.wav` e as anotações
correspondentes, `_comp.jams`; o manifest é montado por varredura desse padrão
em `dataset_io.guitarset_rows`, que falha explicitamente se não encontrar
exatamente 180 excertos.

Os 30 excertos de cada músico são o produto de 5 estilos (Bossa Nova, Funk,
Jazz, Rock e *Singer-Songwriter*) × 3 progressões por estilo × 2 andamentos, o
que dá 30 combinações distintas, cada uma gravada pelos 6 músicos.

O GuitarSet publica várias condições de captação simultâneas (microfone,
*hexaphonic pickup*, versões com e sem separação por corda). Adotou-se o sinal
`audio_mono-mic`, isto é, a captação monofônica por microfone, **por ser a
condição mais próxima do caso de uso do sistema**: áudio gravado pelo microfone
de um telefone celular, sem captador, sem trilha por corda e sem acesso ao
sinal direto do instrumento. Usar o *pickup* hexafônico tornaria o benchmark
mais fácil do que a aplicação real e inflaria artificialmente as métricas. O
áudio é carregado com `librosa.load(sr=22050, mono=True)`.

### 1.2 Faixas excluídas

Duas anotações do GuitarSet têm deslocamento temporal conhecido em relação ao
áudio, documentado na página do dataset e na *issue* #5 do repositório oficial.
São as únicas exclusões do estudo:

| `track_id` | Motivo | Fonte |
|---|---|---|
| `04_BN3-154-E_comp` | anotação adiantada em +0,409 s em relação ao áudio | *issue* #5 do repositório do GuitarSet |
| `04_Jazz1-200-B_comp` | anotação adiantada em +0,309 s em relação ao áudio | *issue* #5 do repositório do GuitarSet |

A exclusão é declarada, não silenciosa: as duas faixas permanecem no manifest
`data/manifests/guitarset_comping.csv` com `excluded=true` e a `exclude_reason`
literal acima, e são filtradas na leitura (`runner._linhas`, `cache._linhas_do_manifest`).
Assim o manifest continua a ser o inventário completo dos 180 excertos e a
auditoria da exclusão não depende de memória institucional. Como ambas pertencem
ao músico 04, as duas caem inteiramente no split de teste.

### 1.3 Divisão por músico

O split é **por músico**, não por faixa nem aleatório. O critério é evitar que
o mesmo executante apareça nos dois lados: excertos do mesmo músico compartilham
timbre, instrumento, ataque, afinação e idiossincrasias de execução, e um split
aleatório permitiria que a busca de configuração se ajustasse a características
de um executante que reaparecem no teste.

| Split | Músicos | Excertos de comping | Excertos pontuados |
|---|---|---:|---:|
| `val` | 00, 01, 02, 03 | 120 | 120 |
| `test` | 04, 05 | 60 | 58 |
| Total | 00–05 | 180 | 178 |

O split de teste tem 60 excertos, dos quais **58 são pontuados**: as duas faixas
da §1.2 saem por `excluded=true`. Toda a exploração — matriz de ablação, curvas
de parâmetro, escolha das configurações e ensaio do protocolo estatístico —
roda apenas em `val`. O split `test` é lido uma única vez, no fim, e o próprio
`runner.py` o protege: `test` está em `SPLITS_PROTEGIDOS` e exige `--splits`
explícito na linha de comando, nunca entrando por omissão.

### 1.4 Licença

O GuitarSet é distribuído sob **Creative Commons Attribution 4.0**; a citação da
fonte é obrigatória e consta das referências do artigo. Nenhum áudio e nenhum
JAMS é redistribuído ou alterado por este trabalho: os arquivos originais ficam
fora do controle de versão, e apenas os manifests, os scripts e as métricas
agregadas são versionados, o que basta para reproduzir o experimento a partir
do download original (verificado por MD5, registrado em `docs/DATASETS.md` §2).

---

## 2. Referência de anotação

### 2.1 As duas camadas do JAMS

Cada arquivo JAMS do GuitarSet contém **duas anotações no namespace `chord`**,
e a escolha entre elas não é neutra:

- `chord[0]` — o **lead sheet instruído**: a cifra que foi dada ao músico para
  executar. É um vocabulário pequeno e estável, com segmentação regular.
- `chord[1]` — a camada **performed/inferred**: derivada das transcrições das
  notas efetivamente tocadas, com segmentação e raiz herdadas do lead sheet.
  Descreve o que soa, incluindo omissões, substituições e extensões que o
  executante acrescentou.

Conforme `docs/CONGELAMENTO.md` §6.2, a **camada principal é `chord[1]`** e a
**camada secundária é `chord[0]`**; as duas são medidas e reportadas em toda
execução, e a camada usada viaja com o número, na coluna `ref_camada` do CSV e
no `meta.json` correspondente, de modo que nenhum valor fica órfão de sua
referência. Os rótulos são lidos e entregues ao `mir_eval` **em notação Harte,
exatamente como estão no arquivo** (`dataset_io.load_guitarset`), sem passar
pelo dicionário de tradução do vocabulário interno — que converteria rótulos
como `D#:sus2(7)/1` em `X` e os faria desaparecer da ponderação. Lacunas entre
observações, inclusive uma lacuna inicial, são preenchidas com `N`, de forma que
a referência de cada faixa seja uma partição contígua do seu eixo temporal.

### 2.2 Cobertura por nível do mir_eval

A escolha da camada tem uma consequência quantitativa que a métrica, sozinha,
esconde. O `mir_eval` **não penaliza** um trecho cuja referência está fora do
vocabulário do nível avaliado: ele o **descarta** da ponderação, marcando a
comparação com −1. Um `sevenths` alto medido sobre dois terços do tempo anotado
não é a mesma afirmação que o mesmo valor medido sobre a quase totalidade dele,
e a diferença não aparece em lugar nenhum da acurácia.

Chama-se aqui **cobertura da referência** a fração do tempo anotado que o
`mir_eval` de fato pondera naquele nível. Ela é medida por
`coverage_report.py`, que não roda pipeline nenhum: chama a própria função do
nível (`mir_eval.chord.root`/`majmin`/`sevenths`/`mirex`) com a referência
contra ela mesma e conta o tempo cuja comparação não é −1 — o descarte depende
só do rótulo de referência, então o estimado é irrelevante para esta pergunta.
Os valores abaixo vêm de `data/results/coverage.csv`, sobre as 178 faixas não
excluídas (5 444,886 s de anotação no total):

| Nível | `chord[0]` ponderado | `chord[0]` descartado | `chord[1]` ponderado | `chord[1]` descartado |
|---|---:|---:|---:|---:|
| `root` | 100,00 % | 0,00 % | 100,00 % | 0,00 % |
| `majmin` | 95,49 % | 4,51 % | 66,69 % | 33,31 % |
| `sevenths` | 95,49 % | 4,51 % | 64,32 % | 35,68 % |
| `mirex` | 100,00 % | 0,00 % | 89,47 % | 10,54 % |

Fonte: `data/results/coverage.csv` (linhas `guitarset,chord[0],*` e
`guitarset,chord[1],*`), gerado por `coverage_report.py`.

A assimetria é a expressão direta da diferença entre as duas camadas. O lead
sheet usa quatro qualidades apenas (`maj`, `min`, `7`, `hdim7`), todas dentro do
escopo dos níveis do `mir_eval`. A camada performed/inferred distribui o mesmo
tempo por dezenas de qualidades, várias delas fora do vocabulário de `majmin` e
de `sevenths` — díades `(1,5)`, acordes com quinta omitida (`7(*5)`, `9(*5)`),
tensões (`maj(#11)`, `maj(2)`), `sus2`, nonas. É por isso que um terço do tempo
some da ponderação de `majmin` em `chord[1]`, e é por isso que as duas camadas
são reportadas lado a lado em vez de uma substituir a outra: `chord[1]` é a
referência mais fiel ao que soa, e `chord[0]` é a referência com cobertura
quase integral. Nenhuma das duas responde à pergunta sozinha.

Um terceiro fato desta tabela governa a interpretação de todo o estudo: nas duas
camadas, **a fração do tempo de referência rotulada como `N` é exatamente zero**
(colunas `n_frac` e `n_s`). O GuitarSet não tem silêncio anotado. Portanto todo
`N` que o sistema estima é erro puro, e qualquer variante que se abstenha de
rotular paga por isso na métrica — o que motiva as variantes e as métricas das
seções 4 e 5.

---

## 3. Pipeline

### 3.1 Etapas, na ordem

O sistema avaliado é o módulo de reconhecimento de acordes do Decifraê. Ele
recebe áudio mono a 22 050 Hz e devolve uma sequência de segmentos
`{start, end, label}`, onde `label` é um nome de acorde do vocabulário ativo ou
`N`. As etapas, na ordem de execução (`pipeline.extract_features` seguido de
`pipeline.decode`):

1. **HPSS** — `librosa.effects.hpss` separa o áudio em componente harmônico e
   componente percussivo. Um único HPSS por faixa alimenta as duas etapas
   seguintes.
2. **Rastreamento de batida** — `librosa.beat.beat_track` sobre o componente
   **percussivo** define as fronteiras dos segmentos. A segmentação é, portanto,
   métrica: o sistema não propõe fronteiras de acorde independentes da batida.
3. **CQT** — `librosa.feature.chroma_cqt` sobre o componente **harmônico**
   produz o chroma de 12 dimensões com resolução de 1/3 de semitom.
4. **Filtro de mediana temporal** — mediana ao longo do tempo com janela fixa,
   para suprimir o tremulação quadro a quadro do chroma.
5. **Sincronização por batida** — `librosa.util.sync` com agregação pela
   **mediana** reduz o chroma a um vetor por batida. O chroma é extraído uma só
   vez na faixa inteira e só então agregado, e não recalculado por fatia curta.
6. **RMS por segmento** — o RMS de cada segmento é medido no áudio **original**,
   não no componente harmônico.
7. **Gate relativo de silêncio** — o limiar é
   `gate = max(abs_floor, rel_gate · mediana(RMS dos segmentos acima do piso))`,
   e todo segmento com RMS abaixo dele é marcado para `N`. O gate é **relativo
   ao nível da própria gravação**, de modo que uma faixa gravada baixa não seja
   integralmente classificada como silêncio; `abs_floor` é o piso absoluto que
   pega silêncio digital.
8. **Emissão por cosseno** — `classifier.CosineChordClassifier.emission` calcula
   o cosseno do chroma do segmento contra todos os templates binários do
   vocabulário, previamente normalizados em L2. O cosseno é auto-normalizado
   pela norma do template (√3 para tríades, √4 para tétrades), então uma tétrade
   só vence se houver energia real nas quatro posições. Sobre isso atua um viés
   pró-tríade **adaptativo**: a tétrade sofre o desconto
   `complexity_penalty · max(0, 1 − ext_sharpness · e_ext)`, onde `e_ext` é a
   energia normalizada da sua nota de extensão (6ª ou 7ª) no chroma — a
   penalidade é cheia quando a extensão está ausente e desaparece quando ela está
   presente.
9. **Viterbi** — `viterbi.decode` decodifica em log-espaço a sequência mais
   provável sobre `n + 1` estados, os `n` acordes do vocabulário mais o estado
   `N`. As emissões viram distribuição por *softmax* com temperatura `temp`; o
   estado `N` recebe a log-probabilidade base `n_logprob`; manter o estado custa
   0 e trocar custa `−change_penalty`, um valor **fixo, não dividido pelo número
   de estados**, o que mantém o mesmo grau de suavização com 24 ou com 60
   templates. Segmentos marcados pelo gate têm as emissões de acorde levadas a
   −50 e `N` a 0,0, de modo que o gate **sobrepõe** as outras fontes de `N`.
10. **Fusão de vizinhos** — `pipeline._merge` funde segmentos consecutivos com o
    mesmo rótulo e descarta intervalos degenerados.
11. **Absorção de curtos** — `pipeline._absorb_short` faz cada segmento com
    duração inferior a `min_dur` herdar o rótulo do **vizinho mais longo**,
    iterando até estabilizar, o que remove os *blips* de transição sem mexer nos
    acordes sustentados.

### 3.2 Parâmetros de produção

Os valores abaixo são os de `config.py`, que é a fonte única dos
hiperparâmetros do pipeline real e o ponto de partida de toda variante (as
variantes são construídas por `dataclasses.replace` sobre estas instâncias). A
tabela completa, com o efeito de cada parâmetro e a faixa sugerida pelo código,
está em `docs/HIPERPARAMETROS.md`.

| Grupo | Parâmetro | Valor | Papel |
|---|---|---:|---|
| pré-chroma | `sr` | 22 050 Hz | taxa de amostragem do carregamento |
| pré-chroma | `method` | `cqt` | *feature* de chroma |
| pré-chroma | `smooth` | 21 | janela (quadros) do filtro de mediana temporal |
| pré-chroma | `hpss_margin` | 3.0 | margem do HPSS |
| pré-chroma | `bins_per_octave` | 36 | resolução do CQT (1/3 de semitom) |
| pós-chroma | `complexity_penalty` | 0.06 | desconto máximo do viés pró-tríade |
| pós-chroma | `ext_sharpness` | 4.0 | sensibilidade do viés à energia da extensão |
| pós-chroma | `confidence_gate` | 0.72 | cosseno mínimo no modo *argmax* (inerte com Viterbi) |
| pós-chroma | `use_viterbi` | `True` | suavização temporal por HMM |
| pós-chroma | `change_penalty` | 2.0 | custo (log) de trocar de acorde entre batidas |
| pós-chroma | `temp` | 0.1 | temperatura do *softmax* das emissões |
| pós-chroma | `n_logprob` | −2.5 | log-probabilidade base do estado `N` |
| pós-chroma | `rel_gate` | 0.2 | fração da mediana do RMS que define silêncio |
| pós-chroma | `abs_floor` | 5 × 10⁻⁴ | piso absoluto de RMS (silêncio digital) |
| pós-chroma | `min_dur` | 0.8 s | duração abaixo da qual o segmento é absorvido |

O vocabulário padrão é `MEDIUM`: os sufixos maior, menor, `7`, `maj7` e `m7`
sobre as 12 tônicas, isto é, 60 templates, mais o estado `N` acrescentado pelo
decodificador (61 estados). O vocabulário `BASIC`, usado por algumas variantes e
pelo baseline, é maior e menor sobre as 12 tônicas (24 templates). Os nomes são
escritos apenas com sustenidos, e a ordem de construção dos templates é a ordem
das colunas da matriz de emissão.

### 3.3 A fronteira pré-chroma / pós-chroma

O pipeline é deliberadamente partido em duas funções, e a fronteira é a
existência do chroma sincronizado por batida:

- **`extract_features` (etapa cara)** — passos 1 a 6. Depende apenas de
  `(áudio, PreChromaConfig)` e produz um objeto `Features` com o chroma
  sincronizado, as bordas temporais e o RMS por segmento. Depois deste ponto,
  nem a forma de onda nem a taxa de amostragem são consultadas.
- **`decode` (etapa barata)** — passos 7 a 11. Depende apenas de
  `(Features, classificador, PostChromaConfig)`.

A fronteira existe por uma razão experimental e não estética: **dos oito
parâmetros do espaço de busca, sete são pós-chroma**. Uma varredura que
recalculasse HPSS, rastreamento de batida e CQT a cada configuração gastaria
quase todo o tempo recomputando algo que não mudou. Com a separação, a etapa
cara roda uma vez por `(áudio, configuração pré-chroma)`, é serializada em disco
por `cache.py`, e a busca varre apenas a etapa barata sobre o mesmo `Features`.
Três parâmetros pós-chroma — `complexity_penalty`, `ext_sharpness` e
`confidence_gate` — configuram o **classificador**, não o `decode`, que os
ignora de propósito; variar um deles exige construir outro classificador, o que
`runner.classificador_de` faz, memoizando por
`(complexity_penalty, ext_sharpness, confidence_gate, vocabulário)`. Uma
varredura que os passasse no `post` esperando efeito estaria medindo dois
parâmetros inertes.

---

## 4. Variantes

A matriz de ablação vive em `runner.py` e é montada por diferença sobre os
defaults de `config.py`. As variantes **A–E são incrementais**: cada uma
acrescenta exatamente uma etapa à anterior, para que a diferença entre duas
linhas vizinhas seja atribuível a uma única mudança. `F`, os dois baselines e as
famílias `0`/`0rg` saem dessa cadeia para isolar outras coisas.

| Variante | Motor | Vocab. | O que muda em relação à anterior |
|---|---|---|---|
| `V4` | v4 | BASIC | baseline do projeto (`legacy_v4.py`, intocado): classificador por soma de energia com *bias* fixo, mais dois termos temporais gulosos (bônus no acorde repetido, penalidade de nome mais longo). Não usa `PreChromaConfig`: tem margem e resolução literais no próprio módulo. |
| `V4b` | v4b | BASIC | o **mesmo** classificador de energia **sem** os dois termos temporais. Separa o que vem do classificador do que vem do modelo temporal guloso. É uma cópia em `runner.py`, porque `legacy_v4.py` não é editado. |
| `A` | cosseno | MEDIUM | ponto de partida do pipeline novo: `smooth=0` (sem filtro de mediana), `complexity_penalty=0` (cosseno puro), `use_viterbi=False` (*argmax* por segmento, com `confidence_gate`), `min_dur=0` (sem absorção). |
| `B` | cosseno | MEDIUM | acrescenta o filtro de mediana temporal: `smooth=21`. É a única variante em que muda um parâmetro **pré-chroma** — `A` e `B` usam extrações diferentes. |
| `C` | cosseno | MEDIUM | acrescenta o viés pró-tríade adaptativo: `complexity_penalty=0.06`. |
| `D` | cosseno | MEDIUM | acrescenta a suavização temporal: `use_viterbi=True`. |
| `E` | cosseno | MEDIUM | acrescenta a absorção de segmentos curtos: `min_dur=0.8`. É a configuração do sistema em produção. |
| `F` | cosseno | BASIC | igual a `D`, trocando o vocabulário de `MEDIUM` (60 templates) para `BASIC` (24). |
| `C0` | cosseno | MEDIUM | `C` com `confidence_gate=0`: o *argmax* passa a rotular sempre. |
| `D0` | cosseno | MEDIUM | `D` com `n_logprob=−1e9`: o estado `N` nunca vence no Viterbi. |
| `E0` | cosseno | MEDIUM | `E` com `n_logprob=−1e9`. |
| `F0` | cosseno | BASIC | `F` com `n_logprob=−1e9`. |
| `C0rg` | cosseno | MEDIUM | `C0` e também `rel_gate=0`. |
| `D0rg` | cosseno | MEDIUM | `D0` e também `rel_gate=0`. |
| `E0rg` | cosseno | MEDIUM | `E0` e também `rel_gate=0`. |
| `F0rg` | cosseno | BASIC | `F0` e também `rel_gate=0`. |

Não existe variante `G`: "`E` com `min_dur=0`" é `D`, campo por campo, e o
conjunto de testes fixa essa equivalência para que ninguém a recrie acreditando
medir outra coisa.

**As três fontes de `N`.** Como a referência do GuitarSet não tem nenhum `N`
(§2.2), a quantidade de tempo que uma variante se recusa a rotular domina a
comparação entre variantes, e isso confunde "rotular mais tempo" com "rotular
melhor". As famílias `0` e `0rg` existem para separar os dois. Há exatamente
três fontes de `N`, e elas são camadas, não alternativas:

1. `confidence_gate`, em `classify_vector` — atua **só** nas variantes sem
   Viterbi. Desligado por `C0`.
2. `n_logprob`, o estado `N` do Viterbi — atua **só** nas variantes com
   Viterbi. Desligado por `D0`, `E0`, `F0`.
3. `force_n`, o gate de RMS — **sobrepõe** as outras duas, porque zera as
   emissões de acorde e fixa `N` em 0,0 no decodificador, de modo que nem
   `n_logprob=−1e9` a vence. É a fonte que resta em `C0`/`D0`/`E0`/`F0`, e é o
   que as versões `rg` desligam: com `rel_gate=0` sobra apenas o piso absoluto
   `abs_floor`, isto é, silêncio digital de verdade — responsável pelo resíduo
   de `N` que subsiste nessas variantes.

**Do conjunto acima, apenas seis vão ao teste**, e foram fixadas antes de o
teste ser lido: `V4`, `C`, `D`, `E`, `F0rg` e `D0rg` (`docs/CONGELAMENTO.md`
§1). As dez restantes são instrumentos de ablação e permanecem restritas ao
split de validação. Os critérios de entrada de cada uma das seis — baseline do
projeto, configuração de produção, e as que se destacaram na validação sob cada
métrica — estão registrados no documento de congelamento, junto com o commit que
define as configurações e a tabela campo a campo de todas elas.

---

## 5. Métricas

Todas as métricas são calculadas por `mir_eval.chord` a partir dos segmentos
estimados e da referência em notação Harte. O `mir_eval` reamostra estimativa e
referência numa grade comum: os intervalos estimados são ajustados ao intervalo
da referência e as duas partições são fundidas, produzindo células
$i = 1 \dots M$ de duração $d_i$, cada uma com um rótulo de referência e um
rótulo estimado. O diagnóstico e as métricas derivadas são medidos na **mesma**
grade, para que não meçam outra coisa que a acurácia.

### 5.1 Os quatro níveis de acerto

Para um nível $\ell$, o `mir_eval` produz por célula uma comparação
$c_i^{\ell} \in \{0, 1\}$, ou $c_i^{\ell} = -1$ quando o rótulo de referência
está fora do vocabulário daquele nível. A acurácia ponderada por tempo é

$$
\mathrm{acc}_{\ell} \;=\;
\frac{\sum_{i \,:\, c_i^{\ell} \ge 0} c_i^{\ell}\, d_i}
     {\sum_{i \,:\, c_i^{\ell} \ge 0} d_i}
$$

isto é, a média das comparações válidas ponderada pela duração. O denominador
exclui as células descartadas — é exatamente a cobertura da §2.2. Os quatro
níveis exigem:

| Nível | Exige |
|---|---|
| `root` | só a tônica; ignora qualidade, sétima e extensões. |
| `majmin` | tônica **e** a distinção maior/menor; ignora a sétima e as extensões. Referência fora de {maior, menor} é descartada. |
| `sevenths` | tônica, qualidade **e** a sétima: aqui a sétima passa a contar. Referência fora do conjunto de qualidades com sétima é descartada. |
| `mirex` | critério MIREX: pelo menos 3 classes de altura em comum entre referência e estimativa. |

### 5.2 `N est` e cobertura da estimativa

`N est` é a fração do tempo que o **sistema** devolveu como "sem acorde",
medida na grade comum. Sendo $\mathcal{N}$ o conjunto de células cuja
estimativa é `N` (na convenção do `mir_eval`, raiz −1 e nenhum semitom):

$$
\texttt{frac\_n\_est} \;=\;
\frac{\sum_{i \in \mathcal{N}} d_i}{\sum_{i} d_i}
\qquad\qquad
\text{cobertura da estimativa} \;=\; 1 - \texttt{frac\_n\_est}
$$

Como a referência não tem `N` (§2.2), `N est` é integralmente tempo perdido, e a
cobertura da estimativa é a fração da faixa sobre a qual o sistema se
arriscou a dar uma resposta. Note que esta cobertura é a da **estimativa** e não
se confunde com a cobertura da **referência** da §2.2, que depende só da
anotação e do nível.

### 5.3 Acerto no tempo rotulado

A acurácia sobre a faixa toda mistura dois erros distintos: rotular errado e
não rotular. A métrica `<nível>_rotulado` isola o primeiro, restringindo a mesma
média ponderada às células em que o sistema **não** devolveu `N`:

$$
\mathrm{acc}^{\text{rot}}_{\ell} \;=\;
\frac{\sum_{i \,\in\, V_{\ell}} c_i^{\ell}\, d_i}{\sum_{i \,\in\, V_{\ell}} d_i},
\qquad
V_{\ell} \;=\; \{\, i \;:\; c_i^{\ell} \ge 0 \;\wedge\; i \notin \mathcal{N} \,\}
$$

Ela responde "quando se arrisca, acerta?", e a distância entre ela e
$\mathrm{acc}_{\ell}$ é o custo do silêncio auto-imposto.

**Ressalva sobre o denominador.** $\sum_{i \in V_{\ell}} d_i$ **não** é o "tempo
total menos o tempo em `N`" literal: ele exclui também as células que o
`mir_eval` descarta naquele nível, isto é, aquelas cuja referência está fora do
vocabulário do nível. A alternativa — contar essas células como erro — tornaria
a coluna incomparável entre níveis e entre camadas: como a §2.2 mostra, em
`chord[1]` o nível `majmin` pondera cerca de dois terços do tempo, e somar o
resto ao denominador misturaria "errou" com "o `mir_eval` não sabe julgar". A
definição está implementada em `runner.acerto_no_tempo_rotulado`. Quando a
cobertura de uma faixa é zero num nível, a célula sai vazia no CSV e a faixa é
descartada daquela comparação, em vez de receber um zero inventado.

### 5.4 Segmentação

O `mir_eval.chord.evaluate` devolve, junto dos níveis, três medidas de
segmentação que dependem **apenas das fronteiras**, não dos rótulos — e que,
por isso, são idênticas nas duas camadas do GuitarSet, que compartilham a
segmentação. Sendo $\mathrm{DHD}(A \Vert B)$ a distância de Hamming direcional
normalizada, que para cada segmento de $A$ desconta a duração do segmento de $B$
que mais se sobrepõe a ele,

$$
\mathrm{DHD}(A \Vert B) \;=\;
\frac{1}{T}\sum_{a \in A}\Big(|a| - \max_{b \in B} |a \cap b|\Big),
$$

as três medidas são

$$
\texttt{overseg} = 1 - \mathrm{DHD}(\text{ref} \Vert \text{est}),
\qquad
\texttt{underseg} = 1 - \mathrm{DHD}(\text{est} \Vert \text{ref}),
\qquad
\texttt{seg} = \min(\texttt{overseg}, \texttt{underseg}).
$$

`overseg` penaliza fronteiras a mais (supersegmentação: a estimativa parte um
acorde da referência em vários); `underseg` penaliza fronteiras de menos
(subsegmentação: a estimativa cola acordes distintos num só); `seg` é o pior dos
dois, o `MeanSeg` do MIREX. O valor 1 significa fronteiras perfeitas. Como
complemento descritivo, cada linha do CSV traz também a contagem absoluta de
segmentos estimados e de referência.

### 5.5 Colunas de diagnóstico

Além das métricas acima, cada linha registra onde o erro está, nas mesmas
frações de tempo da mesma grade: `frac_n_est` (§5.2),
`frac_tonica_ok_qualidade_erro` (tônica certa e qualidade errada) e
`frac_tonica_erro` (tônica errada, o que inclui estimar `N` onde há acorde,
porque `N` não tem tônica). Elas não substituem os níveis; servem para atribuir
uma diferença de acurácia a um tipo de erro.

---

## 6. Protocolo estatístico

O protocolo está implementado em `stats.py` e foi declarado em
`docs/CONGELAMENTO.md` §5 **antes** da leitura do teste, precisamente para que a
leitura não possa escolher o critério que favorece a conclusão. Roda-se o
protocolo na validação como ensaio; o teste roda os mesmos pares, uma única vez.

### 6.1 A unidade de reamostragem é a faixa

O efeito de interesse é a diferença, entre duas variantes, da média ponderada
por duração de uma métrica. Para quantificar a incerteza dessa diferença usa-se
**bootstrap pareado com a faixa como unidade de reamostragem**: cada
reamostragem sorteia faixas com reposição, e o par (diferença da faixa, duração
da faixa) viaja junto — é isso que torna o teste pareado, porque as duas
variantes são avaliadas exatamente nas mesmas faixas.

A escolha da faixa, e **não do segmento**, é a decisão metodológica central
desta seção. Segmentos da mesma execução do mesmo músico não são observações
independentes: compartilham o instrumento, a captação, o nível de gravação, o
andamento, a progressão e a mão do executante. Um erro sistemático — uma corda
mal afinada, um ataque abafado, um beat tracking que travou naquele andamento —
contamina todos os segmentos daquela faixa de forma correlacionada. Reamostrar
segmentos trataria centenas de observações dependentes como independentes,
encolheria artificialmente os intervalos de confiança e produziria significância
onde há apenas volume de dados correlacionados. A faixa é o nível em que a
independência é defensável, e é ela que é reamostrada.

São **10 000 reamostragens** com **semente 0**, fixada por comparação, de modo
que rodar um par isolado reproduza exatamente o mesmo número que rodá-lo dentro
da bateria completa. O intervalo de 95 % é o intervalo percentil da
distribuição bootstrap.

### 6.2 O p do bootstrap

O p-valor do bootstrap é reportado como **nível de significância atingido**
(ASL) da distribuição bootstrap em relação a zero: duas vezes a menor das duas
caudas, com piso em $1/B$. Sendo $\hat\theta^{*(1)}, \dots, \hat\theta^{*(B)}$
as médias ponderadas das diferenças nas $B = 10\,000$ reamostragens,

$$
p \;=\; \min\!\left\{1,\;
\max\!\left(
\frac{1}{B},\;
2 \cdot \min\!\left(
\frac{\#\{b : \hat\theta^{*(b)} \le 0\}}{B},\;
\frac{\#\{b : \hat\theta^{*(b)} \ge 0\}}{B}
\right)\right)\right\}
$$

O piso existe porque não faz sentido reportar $p = 0$ a partir de 10 000
reamostragens. Este **não** é um teste de permutação: é a probabilidade de a
reamostragem cair do outro lado de zero.

### 6.3 Wilcoxon como critério secundário

O **critério principal de decisão é o IC 95 % do bootstrap pareado sobre a
média ponderada por duração.** O Wilcoxon pareado (bilateral, `zero_method`
`wilcox`) sobre as diferenças por faixa é **secundário** e nunca decide sozinho.
A razão é que os dois medem coisas diferentes, e é esperado que às vezes
discordem: a média ponderada por duração é dominada pelas faixas longas, ao
passo que o teste de postos conta faixas, olhando apenas o sinal e a ordem das
diferenças, não a magnitude. Um efeito médio grande com IC cruzando zero
significa "poucas faixas dominam o resultado"; um efeito médio pequeno com
Wilcoxon muito significativo significa "quase toda faixa melhora, mas pouco". As
duas leituras são informativas, e por isso **ambos são reportados sempre**, em
particular quando discordam. O Wilcoxon não é ponderado, porque ponderar postos
por duração não tem interpretação. Quando as diferenças são todas nulas, não há
estatística e a célula sai vazia, em vez de receber um $p = 1$ inventado.

### 6.4 Correção de múltiplas comparações

Os seis pares pré-registrados, com suas métricas, produzem **15 comparações**.
Os p-valores são corrigidos por **Holm-Bonferroni com $\alpha = 0{,}05$**, em
**duas famílias separadas** — uma para os p do bootstrap e uma para os do
Wilcoxon — porque misturar dois testes de naturezas distintas numa família só
não tem justificativa. Ordenando os p brutos de forma crescente,

$$
p^{\text{Holm}}_{(k)} \;=\; \min\!\Big(1,\;
\max_{j \le k}\,(n - j + 1)\, p_{(j)} \Big),
$$

com a monotonicidade imposta explicitamente e teto em 1. Holm foi escolhido em
lugar de Bonferroni simples por ser uniformemente mais poderoso sem supor
independência entre as comparações — o que importa aqui, já que as 15
comparações reusam as mesmas faixas e vários pares compartilham uma variante.
Comparações sem p (por exemplo, Wilcoxon de diferença nula) saem sem p ajustado
e **não** entram na contagem $n$ da família: incluí-las inflaria $n$ e tornaria
a correção mais conservadora do que o declarado.

### 6.5 Regra de decisão

A classificação de cada efeito é calculada por `stats.classificar`, não
atribuída à mão:

| Classe | Condição |
|---|---|
| `confirmado` | o IC 95 % do bootstrap **exclui** zero **e** o p de Holm do bootstrap é < 0,05 |
| `empate` | o IC 95 % **cruza** zero — não há efeito distinguível de ruído |
| `fragil` | o IC 95 % exclui zero **mas** Holm não rejeita |

Um efeito `empate` **não** é descrito como ganho em nenhum texto do artigo. Um
efeito `fragil` é reportado sempre com a ressalva explícita. Cada comparação
traz ainda a mediana das diferenças e a contagem de faixas em que a segunda
variante ganha, perde ou empata, para que a leitura do efeito médio possa ser
confrontada com a sua consistência faixa a faixa.

### 6.6 Os seis pares pré-registrados

A diferença reportada é sempre $b - a$, positiva quando $b$ é a melhor das duas.
A lista canônica vive em `stats.PARES` e é **importada** pelo script que gera o
documento de congelamento, para que documento e código não possam divergir.

| # | Par ($a$ vs $b$) | Métricas | O que o par isola |
|---|---|---|---|
| 1 | `C` vs `D` | `root`, `root_rotulado` | o Viterbi na métrica usual |
| 2 | `C0rg` vs `D0rg` | `root`, `majmin` | o Viterbi com a cobertura igualada (nenhuma fonte de `N` ativa nos dois lados) |
| 3 | `D` vs `E` | `root`, `seg`, `overseg` | o compromisso do `min_dur`: acurácia contra segmentação |
| 4 | `V4b` vs `V4` | `root`, `overseg` | a inércia temporal do baseline |
| 5 | `V4` vs `F0rg` | `root`, `majmin`, `seg` | o baseline contra a variante selecionada no congelamento |
| 6 | `D0rg` vs `F0rg` | `root`, `majmin`, `sevenths` | o vocabulário (`MEDIUM` contra `BASIC`) com a cobertura igualada |

Os pares 2 e 6 usam variantes `0rg` justamente para responder a uma pergunta de
cada vez: com todas as fontes de `N` desligadas nos dois lados, a diferença não
pode ser atribuída a uma das variantes se abster mais que a outra, e o que sobra
é o efeito do Viterbi (par 2) ou do tamanho do vocabulário (par 6). **Nenhum par
novo entra depois de o teste ser lido**; um par acrescentado depois é análise
exploratória e é reportado como tal.

As 15 comparações foram avaliadas em **duas execuções** sobre o conjunto de
teste. A §1 do congelamento listou seis configurações, mas os pares 2 e 4 exigem
`C0rg` e `V4b`, que ficaram fora dessa lista por erro de transcrição entre as
duas seções do mesmo documento. A primeira execução cobriu, por isso, 11 das 15;
a omissão e a sua correção estão registradas em `docs/ADENDO_CONGELAMENTO.md`,
commitado **antes** da segunda execução, e as duas variantes foram medidas com as
configurações inalteradas desde o commit que as define, verificadas linha a linha
contra o código daquele commit. Nenhum parâmetro foi escolhido, ajustado ou
revisto depois da leitura do teste: a segunda execução completa uma matriz
pré-especificada e não acrescenta comparação nova.

### 6.7 Uma análise pós-especificada: a máscara comum

Além dos seis pares, uma análise complementar compara `C` e `D` sobre a **mesma**
porção de tempo, para separar o que a métrica usual soma — quem rotula melhor de
quem rotula mais tempo. Duas máscaras, no nível `root`:

$$
M_C = \{\text{células em que } C \text{ não estimou } N\}, \qquad
M_{CD} = \{\text{células em que nem } C \text{ nem } D \text{ estimaram } N\}
$$

Em cada máscara, a acurácia é a mesma média ponderada do
`mir_eval.weighted_accuracy`, restrita às células da máscara e às comparáveis, e
$\Delta = D - C$ recebe o mesmo bootstrap pareado por faixa (10 000
reamostragens, semente 0). O peso de cada faixa no bootstrap é o tempo que ela
contribui **para a máscara**, não a sua duração total: uma faixa em que `C`
rotulou 5 % do tempo não pode pesar como uma em que rotulou 90 %. As três
estimativas são decodificadas a partir do cache de `Features`, sem refazer
extração de chroma.

Esta análise **não** consta dos pares pré-registrados. Na validação é
exploratória; **no conjunto de teste é pós-especificada (post hoc)**, porque foi
concebida depois da leitura do teste. Ela está marcada como tal na coluna
`status` do CSV e no `meta.json`, e não substitui nem reinterpreta nenhuma
comparação pré-registrada.

---

## 7. Reprodutibilidade

**Determinismo.** O pipeline não tem componente estocástico: HPSS,
rastreamento de batida, CQT, filtro de mediana, cosseno e Viterbi são todos
determinísticos, e não há semente aleatória em nenhuma etapa. A mesma entrada e
a mesma configuração devolvem os mesmos segmentos, bit a bit. Os únicos
processos estocásticos do estudo são as reamostragens do bootstrap, cuja semente
é fixada em 0 e registrada no `meta.json`.

**Oráculo de regressão.** O arquivo `out/musicas_bench/metrics.json` está
versionado e funciona como oráculo: enquanto o comportamento do pipeline não
muda de propósito, ele tem de sair idêntico. Qualquer refatoração desta fase é
neutra em comportamento, e a verificação é um `git diff --exit-code` sobre esse
arquivo após reexecutar o benchmark. Um diff não vazio é tratado como erro da
mudança, não como arredondamento: reverte-se e investiga-se, e o oráculo só é
regenerado quando uma alteração de hiperparâmetro ou de algoritmo é intencional,
no mesmo commit que a introduz. O oráculo já foi verificado numa reexecução em
ambiente idêntico, com saída byte a byte igual à original.

**Procedência de cada número.** Cada execução escreve um CSV em
`data/results/`, nunca sobrescrito, com uma linha por faixa e por variante e
com as colunas de configuração repetidas na própria linha. Ao lado de cada CSV
vai um `<nome>_meta.json` com: o instante de geração; o manifest, os splits, as
variantes e a camada de referência usados; o número de linhas e a lista de
falhas; o tempo de execução; as versões de Python, NumPy, librosa, mir_eval e
SciPy; o commit do projeto e se a árvore estava suja; e a configuração base
completa. Nenhum número do artigo é digitado à mão: tabelas e figuras saem de
script lendo esses CSVs, e a origem é indicada.

**Congelamento anterior à leitura do teste.** `docs/CONGELAMENTO.md` é gerado
por script, não editado à mão, e registra o commit que define as configurações,
as configurações que vão ao teste com todos os seus campos, os parâmetros que
**não** foram ablacionados, os pares pré-registrados e o critério de decisão. Foi
gerado antes de qualquer leitura do split de teste, e a anterioridade é auditável
pela ordem dos commits. As duas faixas problemáticas seguem excluídas pelo
manifest, e as duas camadas de referência são reportadas. Nada é ajustado depois:
se o resultado do teste sugerir outra configuração, isso é trabalho para outro
conjunto de dados, não uma revisão deste número.

O congelamento **não é editado depois da leitura do teste** — editá-lo destruiria
a anterioridade que lhe dá valor. Correções ao seu registro vão para
`docs/ADENDO_CONGELAMENTO.md`, datado e commitado antes da execução que autoriza.
O adendo corrige três coisas: a omissão de `C0rg` e `V4b` da lista da §1 (§6.6
acima), o fato de a árvore estar suja na geração do documento — era o próprio
código que o gerou, commitado 82 s depois e mais de quatro minutos antes da
primeira leitura do teste — e a atribuição errada do `N` residual ao `abs_floor`,
que na verdade vem do `rel_gate`.

**Cache validado por metadados.** A etapa cara é persistida em
`data/cache/<nome_do_audio>__<hash8>.npz`, onde `hash8` são os oito primeiros
dígitos hexadecimais de um SHA-256 sobre o caminho do áudio e **todos** os
campos de `PreChromaConfig`, lidos programaticamente — um campo novo na
configuração entra no hash sozinho e invalida os caches antigos, o que é
proposital. O hash identifica mas não prova: cada `.npz` guarda o caminho e os
campos como metadados, e a leitura os confere um a um, levantando
`CacheMismatchError` com a lista de divergências. Nada é devolvido em silêncio,
e a escrita é atômica (arquivo temporário e `os.replace`), de modo que uma
execução interrompida não deixa um cache parcial que passe por válido.

---

## 8. Limitações

**`change_penalty` fixo e nunca ablacionado.** O custo de troca de acorde do
Viterbi permanece em 2.0 em todas as variantes e em todas as execuções: nenhuma
rodada da matriz de ablação e nenhuma curva de parâmetro usou outro valor. O
valor vem de calibração manual em duas gravações comerciais do acervo do
projeto, e entra no teste como **constante, não como escolha justificada por
dado**. Isso é registrado como decisão declarada e não como omissão. Como o
parâmetro governa diretamente a suavidade da linha do tempo, e portanto tanto a
acurácia quanto as medidas de segmentação da §5.4, é plausível que parte do
efeito atribuído ao Viterbi no par 1 dependa desse valor específico. O mesmo se
aplica, em menor grau, a `temp` (0.1), `ext_sharpness` (4.0), `abs_floor`
(5 × 10⁻⁴), `bins_per_octave` (36) e `hpss_margin` (3.0), todos fixos e nunca
variados; a lista completa está em `docs/CONGELAMENTO.md` §4. Ablacionar
`change_penalty` é o primeiro trabalho que este estudo deixa em aberto.

**IDMT-SMT-Chords fora desta análise.** O segundo benchmark previsto para o
projeto — IDMT-SMT-Chords, do qual só os seis arquivos de guitarra entrariam
como conjunto principal — **não** faz parte desta análise. O adaptador de
anotação, o manifest e a medida de cobertura da sua camada de referência já
existem, mas nenhuma variante foi avaliada sobre ele aqui. Em particular, o
dataset é publicado sob licença `CC BY-NC-ND 4.0`, mais restritiva que a do
GuitarSet. Consequentemente, todas as conclusões deste estudo são conclusões
**sobre o GuitarSet**, e a generalização para outro corpus permanece não
verificada.

**Escopo do GuitarSet.** O corpus é estreito em quatro direções que importam
para a leitura dos resultados:

1. **Apenas 3 progressões por estilo.** As 30 combinações por músico cobrem 5
   estilos × 3 progressões × 2 andamentos. O vocabulário harmônico efetivamente
   exercitado é o dessas progressões, e não uma amostra do repertório de violão
   em geral; a distribuição de qualidades da §2.2 é a distribuição dessas
   progressões.
2. **Violão desacompanhado.** Não há baixo, bateria, voz nem outros
   instrumentos. O sistema nunca é exposto ao problema de estimar acordes em
   mistura densa, que é a condição em que a maior parte das gravações reais
   chega ao Decifraê.
3. **Gravação de estúdio.** Sala tratada, microfone fixo, sem ruído ambiente,
   sem reverberação de ambiente doméstico, sem compressão perceptual e sem os
   artefatos de um microfone de telefone celular. A escolha do sinal
   `audio_mono-mic` em lugar do captador hexafônico (§1.1) aproxima o benchmark
   do caso de uso, mas não o reproduz.
4. **Um só instrumento.** Violão de aço, com o mesmo conjunto de instrumentos
   ao longo do corpus. Nada aqui informa o comportamento do sistema em violão de
   nylon, guitarra elétrica, cavaquinho ou instrumentos com afinação alternativa.

Somadas, as quatro restrições significam que os números deste estudo devem ser
lidos como desempenho num cenário limpo, controlado e harmonicamente restrito —
um limite superior otimista para o comportamento em áudio de usuário — e que a
validade externa das comparações entre variantes depende de a ordem entre elas
se preservar fora dessas condições, o que este experimento não testa.

## 7. Análises pós-revisão

Análises pedidas pelos revisores do ACDSA 2027 para o camera-ready. Todas são
**pós-especificadas**: nenhuma estava em `docs/CONGELAMENTO.md`, e todo CSV
desta seção leva `post_review: true` no meta.json. As configurações novas e o
critério de escolha de cada valor estão em `docs/ADENDO_REVISAO.md`, commitado
(`996aabe`) antes de qualquer execução delas no teste. O teste foi executado
uma vez por camada (`b5065ef` chord[0], `8ca8b2e` chord[1]). Bootstrap
pareado por faixa, 10 000 reamostragens, seed 0, peso = duração
(`stats.bootstrap`).

**Variantes novas** (`runner.py`, exigem `--post-review`):
`Crg`/`Drg` = C/D com `rel_gate = 0`; `Cmatch` = C com `confidence_gate =
0,65`; `Dmatch` = D com `n_logprob = −2,25`; `D0rg_cal` = D0rg com
`change_penalty = 1,5`; `F0rg_cal` = F0rg com `change_penalty = 1,0`. Os quatro
valores saíram de `calibracao_revisao.py`, só na validação.

**R2.1 — executantes.** Para os 15 contrastes de `stats.PARES`, Δ = b − a
médio ponderado por duração dentro de cada executante (00–03 =
desenvolvimento/val, 04–05 = teste; 28–30 faixas cada). Reporta-se o número
de executantes cujo Δ tem o sinal do Δ agregado dos seis e a amplitude
min–max. IC 95 % por executante: bootstrap pareado reamostrando as faixas
**dentro** do executante (10 000, seed 0, peso = duração). Script:
`analise_executantes.py`.

**R2.3 — fatorial 2×2×2.** Fatores: decodificador (argmax C / Viterbi D),
abstenção própria (`confidence_gate` ou `n_logprob` ligado / desligado) e gate
relativo de RMS (`rel_gate` 0,2 / 0). Células: C, C0, Crg, C0rg, D, D0, Drg,
D0rg. Efeito principal = média das quatro diferenças pareadas do fator;
interação X×Y = diferença de diferenças (quanto muda o efeito de X quando Y é
ligado); idem para a de 3ª ordem. Métricas: `root` na faixa toda, cobertura
(1 − `frac_n_est`) e `root_rotulado`. Script: `analise_fatorial.py`.

**R2.3 — cobertura igualada.** `Cmatch` vs D e C vs `Dmatch`; o casamento de
cobertura foi feito na validação e **não é garantido no teste**. Por isso há
também uma comparação feita no próprio teste, sem escolher valor nenhum
(protocolo em `docs/ADENDO_REVISAO.md` §5, commitado antes da execução): as
curvas de C (`confidence_gate` ∈ {0} ∪ {0,50…0,90}, passo 0,01) e de D
(`n_logprob` ∈ {−1…−8}, passo 0,25, ∪ {−1e9}) são medidas no teste; cada
curva é interpolada linearmente (métrica agregada × cobertura agregada) nos
alvos 60, 70, 77 e 90 %, e Δ = D − C. IC por bootstrap pareado por faixa, com
as duas curvas reagregadas e reinterpoladas a cada reamostragem. Script:
`curvas_teste_revisao.py`.

**R2.4 — decomposição e viés de seleção.** Na grade comum do mir_eval, cada
célula de cada faixa é classificada em rotulada por C e D, só por D, só por C
ou por nenhum. A parcela de cada região é Σ(dur·(acerto_D − acerto_C)) / Σ dur,
de modo que as quatro somam exatamente o Δ `root` agregado (conferido contra
os CSVs de ablação, resíduo < 1e-10). Viés de seleção: `root` de D0rg, que
rotula tudo, dentro e fora da máscara comum de C e D. Script:
`analise_decomposicao.py` (re-decodifica C, D e D0rg do cache). A fração do
tempo em cada região é **agregada por duração** (Σ tempo da região / Σ tempo
comparável, sobre todas as faixas). `mascara_comum.py` (setembro) reportava
outra estatística para a mesma região, a **média simples por faixa** da
fração (`np.mean` das frações, cada faixa com peso 1); mesmas células, mesmo
denominador por faixa, agregação diferente.

**R2.5 — representabilidade.** Fração do tempo de referência cuja qualidade
(bitmap de `mir_eval.chord.encode`, sem reduzir extensões) é exatamente
maj/min (vocabulário 24) ou maj/min/7/maj7/min7 (vocabulário 60). O baixo é
ignorado (inversão conta como posição fundamental); N/X ficam no denominador.

**R2.6 — sétimas e transição.** Precisão de sétimas = tempo estimado como
7/maj7/min7 com mesma tônica e qualidade da referência / tempo estimado como
sétima; revocação análoga sobre o tempo de referência com sétima; soma de
tempo sobre as faixas, com IC 95 % por bootstrap reamostrando faixas
(numerador e denominador da faixa juntos; 10 000, seed 0). Sensibilidade à transição: curva `root` ×
`change_penalty` ∈ {0,5…6} na validação, e no teste D0rg/F0rg (cp 2,0) contra
as versões `_cal`. Script: `analise_vocabulario.py`.
