// WASM analyzer loader.
//
// Loads the raw wasm32 sandbox module (base64-inlined, no toolchain needed at
// build time), feeds it the file bytes through linear memory, and wires the
// host import boundary so every finding / attempted action the payload contains
// is surfaced to the caller. The wasm can do NOTHING except call these imports.

import { WASM_B64 } from "./wasm-blob.js";

// Finding kinds (host_emit) — mirror src/lib.rs.
export const K_TYPE = 0;
export const K_EMBED = 4;
export const K_KEYWORD = 6;
export const K_PREVIEW = 7;
export const K_NOTE = 8;

// Intent kinds (host_intent) — the "what is it trying to do" feed.
export const I_NET = 1;
export const I_EXEC = 2;
export const I_SCRIPT = 3;
export const I_MACRO = 5;

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

let _modPromise = null;
function compiled() {
  if (!_modPromise) _modPromise = WebAssembly.compile(b64ToBytes(WASM_B64));
  return _modPromise;
}

/**
 * Analyze file bytes in the sealed wasm sandbox.
 * @param {Uint8Array} fileBytes
 * @param {{onFinding?: (f:{kind:number,text:string,num:number})=>void,
 *          onIntent?: (i:{kind:number,text:string})=>void}} cb
 * @returns {Promise<{score:number, truncated:boolean}>}
 */
export async function analyze(fileBytes, cb = {}) {
  const mod = await compiled();
  const dec = new TextDecoder("utf-8", { fatal: false });
  let inst;
  const read = (ptr, len) => {
    const mem = new Uint8Array(inst.exports.memory.buffer, ptr, len);
    return dec.decode(mem);
  };
  inst = await WebAssembly.instantiate(mod, {
    host: {
      host_emit: (kind, ptr, len, num) => {
        cb.onFinding && cb.onFinding({ kind, text: read(ptr, len), num });
      },
      host_intent: (kind, ptr, len) => {
        cb.onIntent && cb.onIntent({ kind, text: read(ptr, len) });
      },
    },
  });
  const ex = inst.exports;
  const cap = ex.capacity();
  const truncated = fileBytes.length > cap;
  const n = truncated ? cap : fileBytes.length;
  const ptr = ex.buffer();
  new Uint8Array(ex.memory.buffer, ptr, n).set(fileBytes.subarray(0, n));
  const score = ex.analyze(n);
  return { score, truncated };
}
