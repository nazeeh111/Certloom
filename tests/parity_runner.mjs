import { verifyText } from "../web/verify.mjs";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const results = JSON.parse(input).map((text) => {
  try { return { ok: true, result: verifyText(text) }; }
  catch { return { ok: false }; }
});
process.stdout.write(JSON.stringify(results));
