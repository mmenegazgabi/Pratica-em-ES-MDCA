# Backend/Shared

Código de backend comum aos dois módulos (Financeiro e Gestão): utilitários,
modelos/clientes de dados compartilhados, autenticação, etc.

Dono: compartilhado entre os dois times — mudanças aqui afetam ambos os
domínios, então devem ser combinadas entre os times antes de alterar
contratos existentes.

## Relatórios em PDF e XLSX (`relatorios.py`, ARQ-06)

Componente de relatórios da plataforma (T-75). Um relatório é um `Documento`
(título, cabeçalho e seções com tabelas de texto). `gerar_pdf` e `gerar_xlsx`
desenham o mesmo documento, então os dois formatos têm sempre os mesmos dados.
O visual segue o relatório de prestação de contas do Financeiro.

- Quem monta o documento decide o conteúdo, inclusive o que sai por privacidade.
- No XLSX toda célula é texto: nada digitado vira fórmula.
- `ler_pdf` e `ler_xlsx` servem aos testes de paridade.

Hoje é usado pelo relatório técnico da Gestão (`Gestao/relatorio_tecnico.py`).
O relatório de prestação de contas do Financeiro (`Financeiro/relatorio_prestacao.py`)
continua com o gerador próprio e pode passar a usar este componente quando o time do
Financeiro quiser.
