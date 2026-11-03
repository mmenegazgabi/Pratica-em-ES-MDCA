// Acessos: regras sem DOM (testáveis no Node).

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Valida o convite/edição; devolve { campo: mensagem } (vazio = ok). */
export function validarPessoa({ nome, email, papel, projetos }, pessoas = [], editandoId = null) {
  const erros = {};
  if (!String(nome || "").trim()) erros.nome = "Informe o nome.";
  const e = String(email || "").trim().toLowerCase();
  if (!e) erros.email = "Informe o e-mail.";
  else if (!EMAIL.test(e)) erros.email = "E-mail inválido.";
  else if (pessoas.some((p) => p.id !== editandoId && p.email.toLowerCase() === e)) erros.email = "Já existe uma pessoa com esse e-mail.";
  if (!papel) erros.papel = "Escolha o papel.";
  if (!String(projetos || "").trim()) erros.projetos = "Informe os projetos (ou \"Todos\").";
  return erros;
}

/** Filtra o histórico por texto (quem, ação ou detalhe), sem diferenciar maiúsculas. */
export function filtrarAuditoria(registros, texto) {
  const busca = String(texto || "").trim().toLowerCase();
  if (!busca) return registros;
  return registros.filter((r) => [r.quem, r.acao, r.alvo].some((campo) => String(campo).toLowerCase().includes(busca)));
}
