import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/api.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { lapTime, delta, date, api, ApiError } = await import(
  "data:text/javascript;base64," + Buffer.from(compiled).toString("base64")
);

test("lap time carries rounded seconds into the next minute", () => {
  assert.equal(lapTime(59.9999), "1:00.000");
  assert.equal(lapTime(90.27), "1:30.270");
  assert.equal(lapTime(null), "—");
});
test("delta does not display negative zero", () => {
  assert.equal(delta(-0.0000001), "0.000 s");
  assert.equal(delta(1.2345), "+1.235 s");
  assert.equal(delta(-1.2345), "-1.235 s");
  assert.equal(delta(-1.2), "-1.200 s");
});
test("dates use the Warsaw timezone", () => {
  assert.match(date(Date.UTC(2026, 9, 28, 12) / 1000), /13:00/);
});
test("API errors preserve status for expired-login handling", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async () =>
      new Response(JSON.stringify({ detail: "Zaloguj się" }), { status: 401 }),
  );
  await assert.rejects(
    api("/auth/me"),
    (error) =>
      error instanceof ApiError &&
      error.status === 401 &&
      error.message === "Zaloguj się",
  );
});
