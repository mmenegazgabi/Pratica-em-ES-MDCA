// Câmera do comprovante (lancamento/camera.js): regras sem tela.
import { test } from "node:test";
import assert from "node:assert/strict";

import { MENSAGENS, mensagemDoErroDaCamera, nomeDaFoto, podeUsarWebcam, temCameraDoAparelho } from "../lancamento/camera.js";

test("tela de toque usa a câmera do aparelho; mouse, não", () => {
  const janela = (toque) => ({ matchMedia: (q) => ({ matches: toque && q === "(pointer: coarse)" }) });
  assert.equal(temCameraDoAparelho(janela(true)), true);
  assert.equal(temCameraDoAparelho(janela(false)), false);
  assert.equal(temCameraDoAparelho({}), false); // navegador sem matchMedia
  assert.equal(temCameraDoAparelho({ matchMedia: () => { throw new Error("x"); } }), false);
});

test("webcam só quando o navegador tem getUserMedia", () => {
  assert.equal(podeUsarWebcam({ navigator: { mediaDevices: { getUserMedia() {} } } }), true);
  assert.equal(podeUsarWebcam({ navigator: {} }), false);
  assert.equal(podeUsarWebcam({}), false);
});

test("cada erro da câmera tem o seu aviso", () => {
  assert.equal(mensagemDoErroDaCamera({ name: "NotAllowedError" }), MENSAGENS.semPermissao);
  assert.equal(mensagemDoErroDaCamera({ name: "SecurityError" }), MENSAGENS.semPermissao);
  assert.equal(mensagemDoErroDaCamera({ name: "NotFoundError" }), MENSAGENS.semCamera);
  assert.equal(mensagemDoErroDaCamera({ name: "OverconstrainedError" }), MENSAGENS.semCamera);
  assert.equal(mensagemDoErroDaCamera({ name: "NotReadableError" }), MENSAGENS.falhou); // câmera em uso por outro app
  assert.equal(mensagemDoErroDaCamera(undefined), MENSAGENS.falhou);
  for (const texto of Object.values(MENSAGENS)) assert.match(texto, /Escolha um arquivo/);
});

test("a foto da webcam leva data e hora no nome", () => {
  assert.equal(nomeDaFoto(new Date(2026, 10, 24, 18, 5, 1)), "comprovante-20261124-180501.jpg");
});
