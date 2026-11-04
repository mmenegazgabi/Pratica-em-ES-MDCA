// Auditoria (coordenação e direção): só o histórico de ações, em leitura.
import { el, limpar } from "../base/dom.js";
import { blocoAuditoria } from "./acessos.js";

export async function mostrar(container) {
  limpar(container).append(el("h1", {}, "Auditoria"), el("p", { class: "sub" }, "Histórico de ações no módulo financeiro"), blocoAuditoria());
}
