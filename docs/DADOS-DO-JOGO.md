# Dados extraídos do CS2 — o que já está aqui e o que mais dá para pedir

Documento de passagem entre agentes. Quem escreveu isto tem acesso a um servidor
CS2 dedicado com plugin próprio (`~/Projects/cs2-solver`) rodando no `proxyfarm`,
e extrai dados direto dos arquivos do jogo. Todo número abaixo vem **desta build**
(`1.41.7.2/14172`), não de tabela de terceiros.

---

## 1. Já entregue

### Sprites das armas — `docs/sprites/*.png`

34 PNGs, 512×384 RGBA com fundo transparente, extraídos de
`panorama/images/econ/weapons/base_weapons/weapon_<nome>_png.vtex_c`.

Nomes de arquivo = **nome de engine** (`ak47.png`, `usp_silencer.png`,
`m4a1_silencer.png`), então casam por chave com `weapons.csv` e com o JSON abaixo
sem tabela de tradução.

Rifles, SMGs, shotguns, pistolas, LMGs e snipers. Faltam facas, granadas e
equipamento — dá para extrair se o livro precisar (caminho diferente no VPK).

### Parâmetros de arma — `data/weapons_cs2_vdata.json`

46 armas, de `scripts/weapons.vdata`. Chaves com o nome cru do schema, para a
procedência de cada número ser rastreável. Campos por arma:

| campo | o que é |
| --- | --- |
| `m_flCycleTime` | intervalo entre tiros em segundos (AK: 0.1 = 600 RPM) |
| `m_flRecoilMagnitude` / `Variance` | módulo do chute por tiro, e sua variância |
| `m_flRecoilAngle` / `Variance` | direção do chute (0 = cima) e sua variância |
| `m_nRecoilSeed` | **a semente que torna o padrão repetível** |
| `m_flSpread` | dispersão de base da bala |
| `m_flInaccuracy{Stand,Crouch,Move,Jump,Land,Ladder,Fire}` | imprecisão por estado; `Fire` acumula por tiro |
| `m_flRecoveryTime{Stand,Crouch}` | constante de decaimento da imprecisão |
| `m_nDamage`, `m_flArmorRatio`, `m_flPenetration`, `m_flRange`, `m_flRangeModifier` | dano e balística |
| `m_iMaxClip1`, `m_nPrice`, `m_nNumBullets` | pente, preço, balins por tiro |
| `_base` | prefab de origem, para auditar de onde o valor herdou |

**Pares assimétricos:** alguns campos são `[normal, modo alternativo]` —
AUG/AWP com luneta, FAMAS em rajada, pistolas. Ex.: AUG
`m_flRecoilMagnitude = [24.0, 16.0]`. Quando os dois são iguais, o JSON guarda um
número só. Não trate lista como dado faltando.

---

## 2. Achado que afeta `docs/treino/index.html`

A função `pattern(key)` gera o padrão assim:

```js
var w = DATA[key], r = rng(seedOf(key));      // <-- semente = hash de "ak"
var m = w.rMag + (r() * 2 - 1) * w.mv;
var ang = (90 + (r() * 2 - 1) * w.av / 2) * Math.PI / 180;
```

**A fórmula está estruturalmente correta** — é a mesma do engine: módulo ±
variância, ângulo em torno de "cima" ± variância. Duas coisas não são as do jogo:

1. **A semente.** `seedOf("ak")` é o hash da string. A real é
   `m_nRecoilSeed = 223`, e o engine semeia por `seed + índice do tiro`.
2. **O gerador.** É um mulberry32 de JS, não o PRNG da Valve.

Consequência: o padrão tem a *forma* certa e a *sequência* errada. Para o livro
isso importa porque o capítulo 8 afirma que o spray "é uma tabela fixa" — é
verdade, mas a tabela mostrada no app não é a do jogo. Quem treinar nela aprende
uma curva que não transfere.

Valores reais para a AK (`m_nRecoilSeed` incluído):

```
m_flCycleTime                0.1
m_flRecoilMagnitude         30.0
m_flRecoilMagnitudeVariance  0.0     <-- zero
m_flRecoilAngle              0.0
m_flRecoilAngleVariance     70.0
m_nRecoilSeed                223
m_flSpread                   0.0006
m_flInaccuracyStand          0.00641
m_flInaccuracyFire           0.0078  <-- acumula por tiro
m_flRecoveryTimeStand        0.368
```

O capítulo 8 **já** trata `magVar = 0` na AK e o contraste Set Pattern vs Random,
pela planilha do SlothSquadron — a extração só confirma isso na build atual, não é
achado novo. O que a planilha **não** tem e o jogo tem:

- **`m_nRecoilSeed` por arma** (AK 223, M4A1 38965, Galil 51191, MP9 50729, P90
  6213, UMP45 59299, M249 50310, AUG 24204, AWP 4100, Deagle 1454, FAMAS 39623,
  SG556 43500, Glock 4484, USP 5426). É a peça que faltava: com magnitude
  constante e ângulo semeado, a semente é o que fixa *qual* sequência sai. Sem
  ela dá para dizer que o padrão é determinístico; com ela dá para reproduzi-lo.
- `m_nSpreadSeed`, `m_flRecoveryTime{Stand,Crouch}` e a família
  `m_flInaccuracy*` completa, direto da fonte e nesta build.

---

## 3. O que ainda NÃO existe (e o limite honesto)

**Parâmetro não é padrão.** Ter magnitude, ângulo, variâncias e semente não dá a
curva; a curva é o resultado de passar isso pelo PRNG da Valve com a matemática de
acúmulo e decaimento do *punch*. Reimplementar é factível — e a AK é o caso mais
fácil, porque magnitude é constante — mas uma reimplementação **não validada** não
deve ser apresentada como medida.

Tentei medir o padrão no engine com bot e bati num limite estrutural, que vale
registrar para ninguém repetir:

- **Cravar a mira do bot apaga o recuo.** Em CS2 o recuo desloca a própria mira,
  então impor ângulos a cada tick destrói o que se quer medir. Resultado: 240
  tiros de ruído puro, mediana zero.
- **Não cravar entrega a mira para a IA.** O bot girou de yaw 16° para 110°
  durante um spray, com assinatura de aproximação exponencial.
- No projeto de granada isso era contornável porque o projétil pode ser corrigido
  *depois* do lançamento. Bala não — o trace é instantâneo.

Dois caminhos para fechar, e eles se complementam:

1. **Reimplementar o PRNG e validar** contra impactos reais. Para *validar* não
   preciso de mira parada, só para *medir do zero* — o registro já grava, por
   tiro, a origem, os ângulos de visão e o ponto de impacto.
2. **Medir com um humano** segurando o mouse parado. Já está pronto e ligado:
   `css_recoil_capture on` no servidor grava todo tiro de qualquer jogador,
   separando rajadas por intervalo. Três ou quatro sprays bastam para a mediana
   por índice de tiro e o desvio-padrão por índice.

---

## 4. Pedidos que eu atendo

Diga o que falta e em que formato. O que a infraestrutura já alcança:

- **Qualquer arquivo dos VPKs do jogo** — texturas (→ PNG), modelos, `.vdata`,
  `items_game.txt`, sons, mapas. Comando:
  ```
  steam-run Source2Viewer-CLI -i pak01_dir.vpk --vpk_filepath <caminho> -o <saida> -d
  ```
  (roda em `/srv/cs2/server/game/csgo`; `--vpk_list` lista as 132.585 entradas)
- **Sprites que faltam** — facas, granadas, equipamento, ícones de HUD, imagens de
  mapa.
- **Medição in-engine de qualquer coisa balística** — o servidor tem plugin com
  bot dirigível, `host_timescale` até 16 sem alterar a física, e registro por tick
  de trajetória e impacto. Foi assim que saíram as constantes de granada
  (gravidade do projétil 320.0, velocidade de lançamento 675.00, restituição de
  quique 0.439).
- **`items_game.txt`** já extraído em `/srv/cs2/extract/scripts/items/` (8 MB) —
  contém nomes localizados, raridade, coleções, pinturas.

Ferramentas que geraram o que está aqui, todas em `~/Projects/cs2-solver/tools/`:
`weapon_data.py` (parâmetros), `weapon_sprites.py` (sprites),
`recoil_measure.py` + `recoil_pattern.py` (medição in-engine).
