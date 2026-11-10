// Ajuda dos testes: grava uma sessão da plataforma (`mdca.sessao`) no localStorage atual
// e, se pedido, o papel escolhido no Financeiro (`mdca.financeiro.papel`).

const NOMES = {
  coordenacao: "Coordenação",
  direcao: "Diretoria",
  voluntario_financeiro: "Voluntário financeiro",
  educador: "Educador",
  administracao: "Administração",
};

export function sessaoDeTeste({
  papeis = ["coordenacao"],
  papel,
  nome = "Luana Ferraz",
  id = "u-luana",
  email = "luana@mdca.org.br",
  token = "token-de-teste",
  armazem = globalThis.localStorage,
} = {}) {
  const sessao = {
    token,
    expira_em: new Date(Date.now() + 86400000).toISOString(),
    usuario: { id, nome, email, papeis: papeis.map((p) => ({ id: p, nome: NOMES[p] || p })) },
  };
  armazem.setItem("mdca.sessao", JSON.stringify(sessao));
  if (papel) armazem.setItem("mdca.financeiro.papel", papel);
  else armazem.removeItem("mdca.financeiro.papel");
  return sessao;
}
