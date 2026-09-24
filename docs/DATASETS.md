# Datasets de avaliação

Este documento define a organização local e as decisões do benchmark externo.
Os arquivos de áudio e os ZIPs não entram no Git; o documento, os manifests e
os resultados resumidos entram para permitir a reprodução do experimento.

## 1. Organização local

Criar esta árvore na raiz de `Decifra-Violão/`:

```text
data/
  raw/
    guitarset/
      annotation.zip
      audio_mono-mic.zip
    idmt-smt-chords/
      IDMT-SMT-CHORDS.zip
  extracted/
    guitarset/
      annotation/
      audio_mono-mic/
    idmt-smt-chords/
  manifests/
    guitarset_comping.csv
    idmt_smt_chords.csv
  results/
    guitarset/
    idmt_smt_chords/
```

`raw/` preserva os downloads originais. `extracted/` contém somente o que foi
descompactado. `manifests/` é a entrada do runner e deve registrar uma faixa
por linha, com pelo menos `dataset`, `track_id`, `audio_path`,
`annotation_path`, `split` e `excluded`. `results/` contém métricas e logs
gerados, nunca arquivos de áudio ou anotações copiadas.

Os caminhos nos CSVs devem ser relativos à raiz de `Decifra-Violão/`. Assim o
benchmark não depende da letra do disco ou do diretório pessoal de quem o
executa.

## 2. GuitarSet

- Página: <https://zenodo.org/records/3371780>
- Arquivos necessários: `annotation.zip` e `audio_mono-mic.zip`.
- MD5 de `annotation.zip`: `b39b78e63d3446f2e54ddb7a54df9b10`.
- MD5 de `audio_mono-mic.zip`: `275966d6610ac34999b58426beb119c3`.
- Sinal usado: `audio_mono-mic`, por ser a condição mais próxima de uma
  gravação de celular usada pelo Decifraê.
- Subconjunto confirmado localmente: 180 excertos de acompanhamento
  (*comping*), nunca os 180 excertos de solo. O áudio usa o sufixo
  `_comp_mic.wav` e as anotações correspondentes usam `_comp.jams`.
- Licença: Creative Commons Attribution 4.0. A citação da fonte deve aparecer
  no artigo.

### Anotação de acordes

Cada JAMS contém duas anotações no namespace `chord`. A escolha é a segunda
anotação, isto é, `chord[1]` (a anotação inferida/performed). Ela é baseada nas
transcrições das notas tocadas, com segmentação e raiz derivadas do lead sheet.
A primeira, `chord[0]`, é o lead sheet instruído e não será usada como
referência principal do áudio.

```text
namespace escolhido: chord[1]
camada: performed/inferred
motivo: representa a execução inferida a partir das notas tocadas; chord[0] é o lead sheet instruído
```

Não assumir esse valor sem inspeção dos JAMS. O runner deve converter os
intervalos para o formato interno `(start, end, label)` antes de pontuar.

### Exclusões

As duas anotações com tempos incorretos descritas na página do GuitarSet e na
issue #5 serão excluídas do manifest:

```text
faixas excluídas por timing:
  04_BN3-154-E_comp (+0,409 s)
  04_Jazz1-200-B_comp (+0,309 s)
fonte: issue #5 do repositório do GuitarSet
```

Não excluir faixas silenciosamente: cada exclusão deve permanecer no CSV com
`excluded=true` e uma `exclude_reason`.

## 3. IDMT-SMT-Chords

- Página: <https://zenodo.org/records/7544213>
- Arquivo: `IDMT-SMT-CHORDS.zip`.
- MD5: `af2239fcc468ce653c9d9350ceaa3eb5`.
- Estrutura confirmada após a extração: `IDMT-SMT-CHORDS/guitar/` contém 6
  WAVs e `guitar_annotation.lab`; `non_guitar/` contém 10 WAVs e
  `non_guitar_annotation.lab`.
- Benchmark principal: somente os 6 arquivos de `guitar/`, porque o projeto
  reconhece acordes de violão. Os 10 arquivos de `non_guitar/` ficam separados
  para um teste opcional de generalização e não entram na métrica principal.
- Anotação principal: `guitar_annotation.lab`, com intervalos em segundos e
  rótulos no formato `raiz:qualidade`, opcionalmente com inversão, por exemplo
  `C:maj`, `C:min7` e `C:maj/3`.
- Conteúdo publicado: 273 classes de acordes de guitarra e 576 classes
  não-guitarra; segmentos de 2 s, áudio mono a 44,1 kHz.
- Licença confirmada na página do Zenodo: Creative Commons Attribution
  Non-Commercial No-Derivatives 4.0 International (`CC BY-NC-ND 4.0`).
  Registrar a citação no artigo e não redistribuir nem alterar os arquivos do
  dataset.
- Referência: Nadar, Abeßer e Grollmisch, *Towards CNN-based acoustic modeling
  of seventh chords for automatic chord recognition*, SMC 2019.

## 4. Regras do teste

1. Os dados externos ficam separados de `Musicas/`, que continua sendo o
   conjunto de exemplos manuais do projeto.
2. Nenhum áudio ou JAMS é alterado. Normalizações e conversões produzem
   arquivos derivados em `data/extracted/` ou `data/results/`.
3. O split e a seleção de faixas são definidos no manifest, não no código do
   classificador.
4. O mesmo pipeline e os mesmos hiperparâmetros devem ser usados nos dois
   datasets; diferenças de formato ficam restritas ao adaptador de anotação.
5. Para cada execução, salvar versões de Python, librosa, mir_eval e o commit
   do projeto junto das métricas.

## 5. Checklist antes do primeiro benchmark

- [x] MD5 dos três ZIPs confere com os valores acima.
- [x] Os 180 arquivos de comping do GuitarSet foram identificados.
- [x] O namespace de acorde escolhido foi confirmado em todos os JAMS: `chord[1]`.
- [x] As duas faixas com timing incorreto foram identificadas e marcadas.
- [x] A licença do IDMT-SMT-Chords foi lida e registrada: `CC BY-NC-ND 4.0`.
- [x] Os manifests foram gerados com caminhos relativos; as duas faixas
  problemáticas estão marcadas como excluídas.
