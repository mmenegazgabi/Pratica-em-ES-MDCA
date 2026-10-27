// Rotas do computador: o hash da página vira {tela, parametros}.
import { itensDeMenu } from "./sessao.js";

/** "#/lancamentos?status=aprovado" → {tela: "lancamentos", parametros: {status: "aprovado"}}. */
export function lerRota(hash) {
  const [caminho, consulta = ""] = String(hash || "").replace(/^#\/?/, "").split("?");
  const [nome = "", id = ""] = caminho.split("/").filter(Boolean);
  const parametros = Object.fromEntries(new URLSearchParams(consulta));
  if (nome === "lancamentos") return { tela: "lancamentos", parametros };
  if (nome === "entrar") return { tela: "entrar", parametros: {} };
  if (nome === "projetos" && id) return { tela: "projeto", parametros: { id: decodeURIComponent(id) } };
  if (nome === "projetos") return { tela: "projetos", parametros };
  return { tela: "inicio", parametros: {} };
}

/** A tela está no menu do papel? O detalhe do projeto segue "projetos"; "entrar" é sempre livre. */
export function rotaPermitida(tela, papel) {
  if (tela === "entrar") return true;
  const item = tela === "projeto" ? "projetos" : tela;
  return itensDeMenu(papel).some((i) => i.id === item);
}
