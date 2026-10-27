// Ícones Lucide (traço fino). Os caminhos são fixos aqui, nunca vêm do usuário.

const NS = "http://www.w3.org/2000/svg";

const CAMINHOS = {
  inicio: ["M3 10.5 12 3l9 7.5", "M5 9.5V21h14V9.5", "M10 21v-6h4v6"],
  lancamentos: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5", "M9 13h6", "M9 17h6"],
  projetos: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  relatorios: ["M3 3v18h18", "M8 17v-5", "M13 17V8", "M18 17v-9"],
  auditoria: ["M12 3 4 6v6c0 4.5 3.2 8.2 8 9 4.8-.8 8-4.5 8-9V6z", "m9 12 2 2 4-4"],
  camera: ["M14.5 4h-5L8 6H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3z", "M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"],
  galeria: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M9 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z", "m21 15-5-5L5 21"],
  fechar: ["M18 6 6 18", "m6 6 12 12"],
  voltar: ["m15 18-6-6 6-6"],
  seta: ["M5 12h14", "m12 5 7 7-7 7"],
  mais: ["M12 5v14", "M5 12h14"],
  sino: ["M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9", "M10.3 21a1.9 1.9 0 0 0 3.4 0"],
  perfil: ["M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"],
  calendario: ["M8 2v4", "M16 2v4", "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M3 10h18"],
  envio: ["m22 2-7 20-4-9-9-4z", "M22 2 11 13"],
};

export function icone(nome) {
  const caminhos = CAMINHOS[nome];
  if (!caminhos) throw new Error(`Ícone desconhecido: ${nome}`);
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icone");
  svg.setAttribute("aria-hidden", "true");
  for (const d of caminhos) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}
