// Attachment chip presentation: a short type badge (extension) + a color "kind"
// so a PDF / image / zip reads at a glance, and whether a file is a previewable
// image (for inline thumbnails). Shared by the reader + thread view.
const IMAGE = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp"]);
const KINDS = {
  pdf: ["pdf"],
  image: ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "heic", "tiff"],
  doc: ["doc", "docx", "odt", "rtf", "txt", "md", "pages"],
  sheet: ["xls", "xlsx", "csv", "ods", "numbers"],
  slide: ["ppt", "pptx", "odp", "key"],
  archive: ["zip", "rar", "7z", "tar", "gz", "bz2"],
  code: ["js", "ts", "py", "json", "xml", "html", "css", "sh", "c", "cpp", "java", "go", "rs"],
  audio: ["mp3", "wav", "flac", "ogg", "m4a"],
  video: ["mp4", "mov", "avi", "mkv", "webm"],
};

function ext(name) {
  const parts = (name || "").split(".");
  return parts.length > 1 ? (parts.pop() || "").toLowerCase() : "";
}
export function fileExt(name) {
  const e = ext(name);
  return e ? e.toUpperCase().slice(0, 4) : "FILE";
}
export function fileKind(name) {
  const e = ext(name);
  for (const [kind, exts] of Object.entries(KINDS)) if (exts.includes(e)) return kind;
  return "file";
}
export function isImageName(name) { return IMAGE.has(ext(name)); }
