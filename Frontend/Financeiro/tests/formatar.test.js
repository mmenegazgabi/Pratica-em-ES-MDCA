import { test } from "node:test";
import assert from "node:assert/strict";
import {
  diasDesde,
  formatarData,
  formatarDataCurta,
  formatarMoeda,
  somarReais,
  tempoRelativo,
} from "../base/formatar.js";

test("somarReais evita erro de ponto flutuante", () => assert.equal(somarReais([0.1, 0.2]), 0.3));
test("somarReais de lista vazia é zero", () => assert.equal(somarReais([]), 0));
test("formatarMoeda", () => assert.equal(formatarMoeda(1234.5).replace(/\s/g, " "), "R$ 1.234,50"));
test("formatarData e formatarDataCurta", () => {
  assert.equal(formatarData("2026-10-26"), "26/10/2026");
  assert.equal(formatarDataCurta("2026-10-26"), "26/10");
});

const AGORA = new Date("2026-10-27T09:00:00Z");

test("diasDesde conta dias inteiros", () => {
  assert.equal(diasDesde("2026-10-20T10:00:00Z", AGORA), 6);
  assert.equal(diasDesde("2026-10-27T08:00:00Z", AGORA), 0);
  assert.equal(diasDesde("2026-11-01T08:00:00Z", AGORA), 0);
});

test("tempoRelativo", () => {
  assert.equal(tempoRelativo("2026-10-27T01:00:00Z", AGORA), "hoje");
  assert.equal(tempoRelativo("2026-10-26T08:00:00Z", AGORA), "há 1 dia");
  assert.equal(tempoRelativo("2026-10-24T08:00:00Z", AGORA), "há 3 dias");
});
