# CS2 Buy Optimizer (Otimizador de Compra)

Modelo de análise de dados + otimização de compra de armas no CS2, construído
sobre a planilha de armas da comunidade do SlothSquadron (stats extraídos da
engine, última atualização de armas em 2026-03-18,
`data/source/weapon_spreadsheet.xlsx`).

## O que ele faz

Tabelas clássicas de TTK assumem que toda bala acerta, o que faz armas de
carregador grande parecerem absurdas. Este modelo estima o **tempo-até-matar
esperado sob spread real** e otimiza em cima disso:

1. **Parse** (`cs2opt/parse.py`) — organiza a planilha em `data/*.csv`:
   stats de engine por arma, curvas de imprecisão por bala do spray
   (em pé/agachado, normal/com scope), tempos de reload e parâmetros
   ajustados de recuperação de imprecisão.
2. **Modelo de engajamento** (`cs2opt/model.py`) — TTK via Monte Carlo: o
   desvio de cada tiro é sorteado do jeito que a engine faz (disco uniforme
   de imprecisão compartilhado por cartucho + disco uniforme de spread por
   projétil), escalado pela distância (`raio_m = imprecisão/1000 ×
   distância_m`, validado contra as colunas de Accurate Range da própria
   planilha). Abate = N acertos de peito com `N = ceil(100 / dano(d))`,
   `dano(d) = Dano × ArmorPen × RangeModifier^(unidades/500)` (reproduz
   exatamente as tabelas de dano da planilha). Inclui ciclos de
   carregador/reload e 0,3 s de scope-in em tiros com mira.
3. **Otimização de cadência de tiro** — para cada arma × distância o modelo
   testa cadências de spray / burst / tap (a imprecisão se recupera entre
   tiros via o decay ajustado por arma) e fica com a melhor. Ele redescobre a
   técnica real: spray ≤15 m, bursts de ~200 ms a 20 m, taps de ~300 ms a
   30 m+, e spray total na Negev (a imprecisão dela *cai* durante fogo
   contínuo).
4. **Camada de otimização** (`cs2opt/optimize.py`) —
   - TTK esperado por arma × distância × estado de colete,
   - probabilidade de vencer duelo contra um jogador de AK-47 com colete
     (ambos atiram em t=0, cadência ótima; seu colete muda a velocidade com
     que a AK mata você),
   - perfis de engajamento (CQC 2,5–10 m, MID 10–20 m, LONG 20–40 m),
   - fronteira de Pareto em (preço, TTK esperado),
   - **compras por orçamento**: melhor loadout arma+colete por orçamento,
     maximizando a probabilidade de vitória no duelo no perfil MID,
   - varredura de referência mirando na cabeça (armas de one-tap vs capacete).

## Rodar

```bash
.venv/bin/python run_analysis.py   # ~2 min, escreve results/*.csv + summary.json
```

Relatório visual (artefato): `report/build_report.py` → `report/index.html`.

## Resultados principais (v1)

- As compras por orçamento reproduzem a meta real sem ajuste manual: force de
  MP9+colete ($1.900), FAMAS+colete ($2.600), M4A1-S+colete ($3.550),
  AWP+colete ($5.400); AWP pelada nunca é escolhida — M4A1-S+colete domina
  ela em $4.750.
- Fronteira de Pareto no MID: USP-S → Dual Berettas → Tec-9 → MP9 → FAMAS →
  AK-47 → M4A1-S → AWP. P90, AUG, M4A4 e as duas auto-snipers são dominadas
  em preço.
- CZ75-Auto é a melhor pistola anti-colete abaixo de $800 no dano de peito;
  a Desert Eagle só brilha na tabela de headshot (one-tap no capacete a 20 m
  com 94% de acerto no primeiro tiro, batendo com seu fatal-headshot range).
- SG 553 (com scope, 100% de penetração de colete) é o melhor rifle além de
  25 m; M4A1-S ganha da M4A4 em todo lugar que importa.

## Premissas & limitações

- Mira centrada no peito (ou na cabeça, na varredura de headshot); recuo
  assumido totalmente compensado — sobram só imprecisão da engine e spread.
  Os erros são portanto *limites inferiores*; armas de headshot de alta
  skill (Deagle, SSG 08) ficam subestimadas no score de peito.
- Duelos começam simultâneos com os dois jogadores parados e pré-mirados;
  movimento, vantagem do peeker, flicks e spraydown em vários oponentes não
  são modelados. Os 100% da AWP no duelo se leem como "vence a corrida do
  primeiro tiro pré-mirado", não "compre AWP sempre".
- Todos os acertos são de peito (sem mistura de estômago/perna), colete nunca
  quebra, tagging/flinch ignorados.
- Modos burst da FAMAS/Glock e o alt-fire da R8 não são modelados; as curvas
  de spray de Negev/M249 além da bala 30 seguram o último valor da planilha.
- Utilitárias, economia entre rounds e jogo de equipe estão fora do escopo (v1).

## Fonte dos dados & licença

`data/source/weapon_spreadsheet.xlsx` é a planilha de armas de CS2 do
SlothSquadron (ver a aba License). Todos os números derivados remontam a ela;
constantes do jogo além da planilha: colete $650, 100 HP, 0,3 s de scope-in,
raios dos alvos peito/cabeça (0,17 m / 0,10 m).
