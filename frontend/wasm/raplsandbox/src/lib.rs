//! RaplMail attachment sandbox analyzer.
//!
//! Compiled to a raw `wasm32-unknown-unknown` module (no wasm-bindgen, no_std).
//! The module has ZERO ability to touch the host: no filesystem, no network,
//! no syscalls. Its only channel to the outside world is a small set of
//! host-provided import functions (`host_emit`, `host_intent`). Everything the
//! analyzer "wants to do" therefore surfaces as a logged call across that
//! boundary, which the JS runtime records on a live dashboard and never acts
//! on. This is the "prisoner hands a letter to the guard" model: the file's own
//! content is parsed in a sealed box, and every dangerous construct it contains
//! becomes an intercepted intent instead of an action.

#![no_std]
#![no_main]

use core::ptr::addr_of_mut;

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    loop {}
}

// ---- Host import boundary -------------------------------------------------
// The only way out. `--allow-undefined` turns these into wasm imports.
#[link(wasm_import_module = "host")]
extern "C" {
    /// Report a finding. `kind` selects the category (see KIND_* below),
    /// `ptr`/`len` point at a UTF-8/bytes slice in linear memory, `num` is an
    /// auxiliary count/severity.
    fn host_emit(kind: u32, ptr: *const u8, len: usize, num: u32);
    /// Report an *attempted action* the payload tried to take (network, exec,
    /// script eval). The host logs it and returns a blocked/fake result — the
    /// action never happens. Kept separate so the UI can style intents as the
    /// live "what is it trying to do" feed.
    fn host_intent(kind: u32, ptr: *const u8, len: usize);
}

// Finding kinds (host_emit).
const K_TYPE: u32 = 0; // detected file type label
const K_EMBED: u32 = 4; // embedded file
const K_KEYWORD: u32 = 6; // suspicious keyword hit (num = count)
const K_PREVIEW: u32 = 7; // extracted printable text run
const K_NOTE: u32 = 8; // general note

// Intent kinds (host_intent) — the live activity feed.
const I_NET: u32 = 1; // wants to reach a URL
const I_EXEC: u32 = 2; // wants to launch/execute
const I_SCRIPT: u32 = 3; // carries embedded script/js
const I_MACRO: u32 = 5; // carries office macro

// 8 MiB analysis buffer. Lives in .bss, so it costs binary size nothing; the
// host caps input to this size before calling in.
const CAP: usize = 8 * 1024 * 1024;
static mut BUF: [u8; CAP] = [0; CAP];

#[no_mangle]
pub extern "C" fn buffer() -> *mut u8 {
    addr_of_mut!(BUF) as *mut u8
}

#[no_mangle]
pub extern "C" fn capacity() -> usize {
    CAP
}

// ---- helpers --------------------------------------------------------------

unsafe fn base() -> *const u8 {
    addr_of_mut!(BUF) as *const u8
}

unsafe fn at(i: usize) -> u8 {
    *base().add(i)
}

fn starts_with(n: usize, sig: &[u8]) -> bool {
    if sig.len() > n {
        return false;
    }
    let mut i = 0;
    while i < sig.len() {
        if unsafe { at(i) } != sig[i] {
            return false;
        }
        i += 1;
    }
    true
}

/// First index of `needle` in BUF[..n], or usize::MAX.
fn find(n: usize, start: usize, needle: &[u8]) -> usize {
    if needle.is_empty() || needle.len() > n {
        return usize::MAX;
    }
    let last = n - needle.len();
    let mut i = start;
    while i <= last {
        let mut k = 0;
        while k < needle.len() && unsafe { at(i + k) } == needle[k] {
            k += 1;
        }
        if k == needle.len() {
            return i;
        }
        i += 1;
    }
    usize::MAX
}

fn contains(n: usize, needle: &[u8]) -> bool {
    find(n, 0, needle) != usize::MAX
}

fn count(n: usize, needle: &[u8]) -> u32 {
    let mut c = 0u32;
    let mut i = 0usize;
    loop {
        let f = find(n, i, needle);
        if f == usize::MAX {
            break;
        }
        c += 1;
        if c >= 9999 {
            break;
        }
        i = f + needle.len();
    }
    c
}

fn is_print(b: u8) -> bool {
    b == 0x09 || (0x20..0x7f).contains(&b)
}

fn is_url_char(b: u8) -> bool {
    matches!(b,
        b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9')
        || matches!(
            b,
            b'-' | b'.' | b'_' | b'~' | b':' | b'/' | b'?' | b'#' | b'[' | b']'
                | b'@' | b'!' | b'$' | b'&' | b'\'' | b'(' | b')' | b'*' | b'+'
                | b',' | b';' | b'=' | b'%'
        )
}

fn emit(kind: u32, s: &[u8], num: u32) {
    unsafe { host_emit(kind, s.as_ptr(), s.len(), num) }
}

fn intent(kind: u32, ptr: usize, len: usize) {
    unsafe { host_intent(kind, base().add(ptr), len) }
}

fn intent_lbl(kind: u32, s: &[u8]) {
    unsafe { host_intent(kind, s.as_ptr(), s.len()) }
}

// ---- analysis -------------------------------------------------------------

/// Analyze the first `len` bytes already written into `buffer()`.
/// Returns a 0..=100 risk score.
#[no_mangle]
pub extern "C" fn analyze(len: usize) -> u32 {
    let n = if len > CAP { CAP } else { len };
    if n == 0 {
        emit(K_TYPE, b"Empty file", 0);
        return 0;
    }

    let mut score: u32 = 0;

    // ---- Magic-byte type detection ----
    let mut is_pdf = false;
    let mut is_zip = false;
    let mut is_ole = false;

    if starts_with(n, b"%PDF") {
        emit(K_TYPE, b"PDF document", 0);
        is_pdf = true;
    } else if starts_with(n, b"MZ") {
        emit(K_TYPE, b"Windows executable (PE/MZ)", 0);
        intent_lbl(I_EXEC, b"Contains native Windows executable code");
        score += 65;
    } else if starts_with(n, &[0x7f, b'E', b'L', b'F']) {
        emit(K_TYPE, b"Linux executable (ELF)", 0);
        intent_lbl(I_EXEC, b"Contains native Linux executable code");
        score += 65;
    } else if starts_with(n, &[0xCA, 0xFE, 0xBA, 0xBE]) {
        emit(K_TYPE, b"Java class / Mach-O binary", 0);
        intent_lbl(I_EXEC, b"Contains compiled bytecode / native code");
        score += 45;
    } else if starts_with(n, &[0xD0, 0xCF, 0x11, 0xE0]) {
        emit(K_TYPE, b"Legacy MS Office / OLE compound file", 0);
        is_ole = true;
    } else if starts_with(n, b"PK\x03\x04") {
        is_zip = true;
    } else if starts_with(n, b"{\\rtf") {
        emit(K_TYPE, b"Rich Text Format document", 0);
    } else if starts_with(n, b"#!") {
        emit(K_TYPE, b"Shell/interpreter script", 0);
        intent_lbl(I_SCRIPT, b"Executable script with interpreter shebang");
        score += 40;
    } else if starts_with(n, &[0x89, b'P', b'N', b'G']) {
        emit(K_TYPE, b"PNG image", 0);
    } else if starts_with(n, &[0xFF, 0xD8, 0xFF]) {
        emit(K_TYPE, b"JPEG image", 0);
    } else if starts_with(n, b"GIF8") {
        emit(K_TYPE, b"GIF image", 0);
    } else if starts_with(n, &[0x1F, 0x8B]) {
        emit(K_TYPE, b"GZIP archive", 0);
    } else if starts_with(n, b"Rar!") {
        emit(K_TYPE, b"RAR archive", 0);
    } else if starts_with(n, &[b'7', b'z', 0xBC, 0xAF, 0x27, 0x1C]) {
        emit(K_TYPE, b"7-Zip archive", 0);
    } else if starts_with(n, b"<?xml") || starts_with(n, b"<html") || starts_with(n, b"<!DOC") {
        emit(K_TYPE, b"Markup / HTML document", 0);
    } else {
        emit(K_TYPE, b"Unknown / binary data", 0);
    }

    // ---- ZIP container: Office macros, jars, nested archives ----
    if is_zip {
        let office = contains(n, b"word/") || contains(n, b"xl/") || contains(n, b"ppt/");
        if office {
            emit(K_TYPE, b"OpenXML Office document (docx/xlsx/pptx)", 0);
        } else if contains(n, b"AndroidManifest.xml") {
            emit(K_TYPE, b"Android package (APK)", 0);
            score += 20;
        } else if contains(n, b"META-INF/MANIFEST.MF") {
            emit(K_TYPE, b"Java archive (JAR)", 0);
            intent_lbl(I_EXEC, b"Runnable Java archive");
            score += 30;
        } else {
            emit(K_TYPE, b"ZIP archive", 0);
        }
        if contains(n, b"vbaProject.bin") || contains(n, b"macroEnabled") {
            emit(K_EMBED, b"Embedded VBA macro project", 0);
            intent_lbl(I_MACRO, b"Document carries executable VBA macros");
            score += 45;
        }
    }

    // ---- OLE (legacy Office): macro streams ----
    if is_ole && (contains(n, b"VBA") || contains(n, b"Macros") || contains(n, b"_VBA_PROJECT")) {
        intent_lbl(I_MACRO, b"Legacy document carries VBA macro streams");
        score += 45;
    }

    // ---- PDF active-content scan ----
    if is_pdf {
        score += pdf_scan(n);
    }

    // ---- Embedded URL extraction (any file) ----
    score += scan_urls(n);

    // ---- Suspicious keyword sweep (generic, works on scripts/HTML/macros) ----
    score += keyword_sweep(n);

    // ---- Safe printable-string preview ----
    preview(n);

    if score > 100 {
        score = 100;
    }
    score
}

/// Scan a PDF for the constructs that make PDFs dangerous. Returns added score.
fn pdf_scan(n: usize) -> u32 {
    let mut s = 0u32;

    if contains(n, b"/Launch") {
        intent_lbl(I_EXEC, b"/Launch action: tries to run an external program");
        s += 60;
    }
    let js = contains(n, b"/JavaScript") || contains(n, b"/JS");
    if js {
        emit(K_KEYWORD, b"/JavaScript", count(n, b"/JavaScript") + count(n, b"/JS"));
        intent_lbl(I_SCRIPT, b"Embedded JavaScript that runs on open/view");
        s += 30;
    }
    if contains(n, b"/OpenAction") {
        intent_lbl(I_SCRIPT, b"/OpenAction: auto-runs code when the file is opened");
        s += 20;
    }
    if contains(n, b"/AA") {
        emit(K_NOTE, b"/AA additional-actions (event-triggered code)", 0);
        s += 10;
    }
    if contains(n, b"/EmbeddedFile") || contains(n, b"/Filespec") {
        emit(K_EMBED, b"Embedded file payload inside the PDF", count(n, b"/EmbeddedFile"));
        s += 20;
    }
    if contains(n, b"/RichMedia") {
        emit(K_EMBED, b"/RichMedia (embedded Flash/media object)", 0);
        s += 15;
    }
    if contains(n, b"/SubmitForm") {
        intent_lbl(I_NET, b"/SubmitForm: posts form data to a remote server");
        s += 15;
    }
    if contains(n, b"/GoToR") || contains(n, b"/URI") {
        emit(K_NOTE, b"Remote / URI navigation actions present", 0);
    }
    if contains(n, b"/XFA") {
        emit(K_NOTE, b"/XFA dynamic form (extra scripting surface)", 0);
        s += 5;
    }
    s
}

/// Extract embedded http(s) URLs and report each as a blocked network intent.
fn scan_urls(n: usize) -> u32 {
    let mut s = 0u32;
    let mut found = 0u32;
    let schemes: [&[u8]; 2] = [b"http://", b"https://"];
    for scheme in schemes {
        let mut i = 0usize;
        loop {
            let f = find(n, i, scheme);
            if f == usize::MAX {
                break;
            }
            // Extend across valid URL characters.
            let mut end = f + scheme.len();
            while end < n && is_url_char(unsafe { at(end) }) && end - f < 512 {
                end += 1;
            }
            intent(I_NET, f, end - f);
            found += 1;
            if found >= 40 {
                return s + 20;
            }
            i = end;
        }
    }
    if found > 0 {
        s += if found > 6 { 12 } else { 4 };
    }
    s
}

fn keyword_sweep(n: usize) -> u32 {
    let mut s = 0u32;
    let kws: [(&[u8], u32); 10] = [
        (b"powershell", 15),
        (b"cmd.exe", 15),
        (b"WScript.Shell", 20),
        (b"eval(", 8),
        (b"CreateObject", 12),
        (b"FromBase64String", 12),
        (b"Invoke-Expression", 20),
        (b"document.write", 6),
        (b"ActiveXObject", 12),
        (b"URLDownloadToFile", 20),
    ];
    for (kw, weight) in kws {
        let c = count(n, kw);
        if c > 0 {
            emit(K_KEYWORD, kw, c);
            s += weight;
        }
    }
    s
}

/// Emit runs of printable text so the host can show a safe read-only preview
/// without ever handing bytes to the OS. Budgeted so huge files stay snappy.
fn preview(n: usize) {
    let mut i = 0usize;
    let mut runs = 0u32;
    let mut budget: usize = 8192; // total bytes of preview to surface
    while i < n && runs < 120 && budget > 0 {
        if is_print(unsafe { at(i) }) {
            let start = i;
            while i < n && is_print(unsafe { at(i) }) {
                i += 1;
            }
            let mut len = i - start;
            if len >= 5 {
                if len > budget {
                    len = budget;
                }
                intent_preview(start, len);
                budget -= len;
                runs += 1;
            }
        } else {
            i += 1;
        }
    }
}

fn intent_preview(ptr: usize, len: usize) {
    unsafe { host_emit(K_PREVIEW, base().add(ptr), len, 0) }
}
