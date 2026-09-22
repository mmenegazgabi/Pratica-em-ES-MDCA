# MDCA — telas de Gestão · E2

Todo o protótipo fica nesta pasta. Não há estrutura de aplicação ou backend.

Abra `index.html` para usar os arquivos separados ou `MDCA_Gestao_E2.html` para a versão portátil, que pode ser enviada sozinha. `MDCA Mapa de Telas.html` abre o mapa e deve ficar ao lado da versão portátil.

## Arquivos para editar

- `index.html`: entrada das telas.
- `style.css`: estilos Classical, fontes locais, layout e adaptação mobile.
- `app.js`: telas, navegação e interações com dados fictícios.
- `assets/`: fontes locais.
- `build.mjs`: gera o HTML portátil. Execute `node build.mjs` nesta pasta após editar os arquivos acima. Não exige instalação de pacotes.

Os arquivos antigos `classical.css`, `layout.css` e `fonts.css` foram preservados como referência; não são carregados pela versão atual. Edite `style.css` para alterar o visual.

## Uso e limites

Os botões de perfil no menu lateral permitem explorar os acessos simulados. O guia contém percursos de demonstração e a opção de reiniciar os dados de exemplo.

Os dados são fictícios e ficam no navegador. Login, permissões, auditoria e sincronização são simulações. Não há API, banco remoto, autenticação real ou infraestrutura implantada. Os anexos guardam apenas metadados; a importação CSV lê o arquivo local. A exportação PDF usa a impressão do navegador e a exportação XLSX gera uma planilha local.

O link Finanças abre o protótipo da pasta vizinha, sem compartilhar sessão ou dados. As funcionalidades próprias de Gestão foram preservadas, com navegação hierárquica e indicadores atualizados ao padrão visual financeiro.
