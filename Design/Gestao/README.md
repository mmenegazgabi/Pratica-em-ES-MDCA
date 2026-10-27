# MDCA — telas de Gestão · E2

Todo o protótipo fica nesta pasta. Não há estrutura de aplicação ou backend.

Abra `index.html` para usar os arquivos separados ou `MDCA_Gestao_E2.html` para a versão portátil, que pode ser enviada sozinha. `MDCA Mapa de Telas.html` abre o mapa e deve ficar ao lado da versão portátil.

## Arquivos para editar

- `index.html`: entrada das telas.
- `style.css`: tokens e componentes do design system MDCA (os mesmos do Financeiro, em `../Financeiro/_ds/mdca-…/styles.css`), fontes locais, layout e adaptação mobile.
- `app.js`: telas, navegação e interações com dados fictícios.
- `assets/`: fontes locais (Bitter e General Sans, em woff2), embutidas no HTML portátil pelo `build.mjs`.
- `build.mjs`: gera o HTML portátil. Execute `node build.mjs` nesta pasta após editar os arquivos acima. Não exige instalação de pacotes.

Edite `style.css` para alterar o visual. Para manter Gestão e Finanças iguais, mudanças no design system devem ser feitas no `styles.css` do Financeiro e copiadas para o bloco MDCA no topo do `style.css`.

## Navegação

O menu lateral segue o padrão do Financeiro: grupos curtos, com um item por área de trabalho. Telas relacionadas ficam no mesmo item e são alternadas por abas:

| Grupo | Item | Telas reunidas |
|---|---|---|
| Programas e público | Visão geral | Painel inicial |
| | Programas e turmas | Programas · Turmas |
| | Pessoas e famílias | Cadastros e trajetória |
| Execução e atendimento | Atividades e frequência | Agenda, registro em campo e fila de sincronização |
| | Acompanhamento técnico | Alertas e busca ativa · Atendimentos · Rede de proteção |
| | Aprendizagem | Contratos e jornadas |
| Resultados | Indicadores e relatórios | Indicadores · Relatório técnico |
| | Visão integrada | Execução física e financeira por programa (coordenação e diretoria) |
| Auditoria e implantação | Trilha de auditoria | Eventos de acesso e alteração |
| | Importação e piloto | Carga de cadastros e piloto assistido |

Cada perfil vê apenas os itens e as abas que pode acessar. A coordenação vê a lista de atendimentos sem abrir o conteúdo e consulta a rede de proteção sem editar; registros com sigilo reforçado ficam restritos à equipe técnica. As notificações ficam no topo; a troca de perfil fica no menu do usuário; a saída fica no rodapé do menu lateral e também no menu do usuário; a troca de módulo fica no seletor Gestão/Finanças e no logo. Os endereços das telas não mudaram.

## Perfil Administrador

O perfil **Administrador** (Administração do sistema) acessa e edita todas as telas, inclusive atendimentos psicológicos e registros com sigilo reforçado. Ele não tem persona na E1. Mesmo com ele, a trilha de auditoria continua sem edição ou exclusão.

Só o Administrador vê a tela **Usuários e acessos** (grupo Auditoria e implantação), com contas, perfis, programas e situação. Os programas definidos ali controlam o acesso de Educadora, Assistente social e Psicólogo; um usuário inativo não consegue entrar pelo login. Criações, alterações e redefinições de senha são registradas na trilha de auditoria.

## Cobertura da E1

O protótipo simula os critérios de aceitação das 14 user stories da E1. Os pontos que dependem de regras automáticas funcionam assim:

| User story | Onde ver no protótipo |
|---|---|
| US-01 | Desligar um profissional na aba Equipe bloqueia o acesso dele ao programa; tentativas de acesso negado entram na trilha de auditoria. |
| US-02 | Plano de ação com período da ação dentro da vigência, resultado esperado e periodicidade. |
| US-03 | A revisão do cadastro alerta possível duplicidade por nome, nascimento e responsável e pede confirmação. |
| US-05 | Cada evidência guarda atividade, programa, autor e data. |
| US-06, 08 e 09 | Alertas criados a partir dos registros: faltas consecutivas acima do limite do programa, retorno da rede vencido e contrato a 60 dias do fim. Os dois primeiros ficam em Alertas e busca ativa; o aviso de contrato fica em Aprendizagem e nas notificações. |
| US-07 | Versões anteriores com autor e horário e lista de acessos ao registro. |
| US-10 | Indicadores com o mesmo cálculo do relatório e metas do ano por programa. |
| US-11 e 12 | Relatório com finalidade (externa ou interna), resultados, pessoas atendidas, evidências selecionadas, execução financeira opcional, PDF e XLSX com o mesmo conteúdo e histórico de emissões. |
| US-13 | Filtros por usuário, período e operação; tentativa de excluir um evento é negada e registrada. |
| US-14 | Registros incompletos entram com pendência; a carga mostra amostra conferida e divergências; o piloto registra data e responsável. |

O painel da coordenação também reúne os dados ausentes e as metas em risco antes do fechamento do período.

## Uso e limites

A troca de perfil no menu do usuário permite explorar os acessos simulados. O guia contém percursos de demonstração e a opção de reiniciar os dados de exemplo.

O link **Prévia para celular** no rodapé abre a plataforma em uma moldura de 390 × 844 px. Dentro dela, o menu ☰ no topo abre a barra lateral com as mesmas áreas do computador, conforme o perfil em uso. A prévia usa os dados fictícios do protótipo sem gravar alterações no armazenamento local.

Os dados são fictícios e ficam no navegador. Login, permissões, auditoria e sincronização são simulações. Não há API, banco remoto, autenticação real ou infraestrutura implantada. Os anexos guardam apenas metadados; a importação CSV lê o arquivo local. A exportação PDF usa a impressão do navegador e a exportação XLSX gera uma planilha local.

O link Finanças abre o protótipo da pasta vizinha, sem compartilhar sessão ou dados. As funcionalidades próprias de Gestão foram preservadas, com navegação hierárquica e indicadores atualizados ao padrão visual financeiro.
