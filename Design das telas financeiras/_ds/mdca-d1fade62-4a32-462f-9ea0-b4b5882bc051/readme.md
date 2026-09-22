# MDCA design system

Identidade visual de mdca.org.br (Movimento pelos Direitos da Criança e do Adolescente), verificada direto no site ao vivo (estilos computados + o `logo.svg` do próprio site), não só em screenshots: verde como cor primária em pílulas e botões, neutros quentes (creme/bege) nos fundos, cinza neutro (não esverdeado) no texto, títulos em serifa (Bitter) sobre corpo em sem-serifa, cards brancos com sombra suave tingida de verde e raios generosos (pílula para ações, 24px para cards, 16px para campos e telas).

Este arquivo substitui o sistema "classical" nas telas do módulo financeiro, mantendo a mesma API de tokens e classes (`--color-*`, `--font-*`, `--space-*`, `--radius-*`, `--shadow-*`, `.btn`, `.card`, `.tag`, `.field`, `.input`, `.table`, `.seg`, `.plate`, `.hr`) — só os valores mudaram, então nenhuma tela precisou ter seu HTML ou lógica alterados (a única exceção deliberada: a função `tagFor()` e algumas linhas de dados nas telas passaram a apontar para as novas classes de status abaixo, porque isso é a cor que a interface mostra, não o dado em si).

## Como usar

- Link o único stylesheet — `<link rel="stylesheet" href="styles.css">` — e tire cor, fonte, espaçamento, raio e sombra sempre das variáveis. Nunca hex ou px soltos.
- Para editar o visual, mexa nos tokens no topo do `styles.css`.

## Cores

Rampa verde (`--green-950`…`--green-100`) é a cor de marca — `--green-400` (`#6aba60`) é a primária, amostrada direto do botão "Quero ser voluntário" do site. Fundos usam os tons quentes confirmados por amostragem de pixel: `--cream-50` `#fffdf1` (fundo de página) e `--beige-200` `#f3e5cb` (preenchimento de card). Texto usa cinza neutro de verdade, também confirmado por amostragem: títulos em preto puro (`#000000`), corpo em `#1e1e1e`, texto secundário em `#7a7a7a` — o site não tinge o texto de verde, só os fundos e os controles são coloridos.

### Cores do logo — agora usadas, não só reservadas

O logotipo MDCA (`M` vermelho, `D` verde, `C` azul, `A` amarelo) foi lido direto do `logo.svg` do site: `--logo-red` `#f02d34`, `--logo-green` `#009d53`, `--logo-blue` `#195bae`, `--logo-yellow` `#fde118`. No site institucional essas cores aparecem só na marca — mas o módulo financeiro precisa de um sistema de status com mais de uma cor (aprovado, pendente, rejeitado, conciliado, encerrado), e o site não define isso. Em vez de inventar cores fora da marca, este sistema usa as três cores do próprio logo que sobravam:

| Status | Token | Cor | Classe |
|---|---|---|---|
| Aprovado | `--status-approved` | verde (`--green-400`) | `.tag-accent` |
| Pendente | `--status-pending` | amarelo do logo | `.tag-warning` |
| Rejeitado | `--status-rejected` | vermelho do logo | `.tag-danger` |
| Conciliado | `--status-reconciled` | azul do logo | `.tag-info` |
| Encerrado | `--status-closed` | cinza neutro | `.tag-neutral` |

Vermelho/azul/amarelo ficam reservados a essas pílulas de status (e à marca) — nunca aparecem em botão, link ou fundo de tela, do mesmo jeito que o site nunca usa as cores do logo fora da marca.

### A marca em si

O logo real (SVG, colorido) agora aparece nas telas — barra lateral do protótipo e cabeçalho do mapa de telas — no lugar do texto "MDCA" que havia antes. É o mesmo arquivo vetorial do site, embutido inline.

## Fontes

Confirmado nos estilos computados do site: **Bitter** (serifada) para títulos e rótulos de botão — carregada do Google Fonts, é a fonte real, sem aproximação. O corpo do site usa **Neue Montreal**, uma fonte paga da fundição Pangram Pangram sem CDN gratuito legítimo; o substituto mais próximo é **General Sans** (Fontshare, gratuita, mesma linhagem de fundição e proporções). Troque a família em `--font-body` se a MDCA licenciar a fonte real depois.

## Espaçamento, raios e sombras

Escala de espaçamento em múltiplos de 4 (`--space-1` a `--space-8`, 4px a 56px). Raios: pílula (`--radius-pill`, 999px, confirmado pelo `border-radius: 90px` do botão real) para botões, badges e chips; 24px (`--radius-lg`) para cards; 16px (`--radius-md`) para campos, tiles e fotos inline. Sombras sempre suaves, para baixo e tingidas de verde, nunca cinza.

## Limitações conhecidas

- Neue Montreal é aproximada por General Sans (ver "Fontes" acima) — a única aproximação que resta; cores e a fonte de título já são exatas.
- O site não tem cores de status próprias — o mapeamento de status para vermelho/azul/amarelo do logo (ver tabela acima) é uma extensão deliberada deste sistema para o módulo financeiro, não algo copiado do site.
- Fundo do hero (gradiente escuro `#111111 → #2d4c2e → #436d43` com brilhos radiais) foi amostrado mas não é usado nestas telas de sistema, que ficam sobre `--color-bg` claro.

## Arquivos

- `styles.css` — tokens (`:root`) + camada de componentes. Link em toda página.
- `_ds_bundle.js` — namespace vazio do sistema (sem componentes exportados).
- `readme.md` — este guia.
