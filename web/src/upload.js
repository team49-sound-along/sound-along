// Upload a recording to the `upload` target returned by POST /api/recordings.
//
// Hash decision: CloudFront-signed API calls must carry x-amz-content-sha256 (see hash.js), but only for requests that
// go through the API origin. When `upload.url` is same-origin /api/... (the local server, or the API behind CloudFront)
// we send the header; a 25 MB SHA-256 with crypto.subtle takes well under a second, so correctness wins. A presigned
// S3 URL is absolute and already signed, and adding unsigned headers would break the signature, so we send only the
// headers the API told us to. XMLHttpRequest is used because fetch cannot report upload progress.
const toHex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

export const isApiUrl = (url) => /^\/api\//.test(url);

/** Headers to send: those the API gave us, plus the body hash for same-origin /api URLs. */
export async function uploadHeaders(file, upload) {
  const headers = { ...(upload.headers ?? {}) };
  if (isApiUrl(upload.url) && !Object.keys(headers).some((h) => h.toLowerCase() === "x-amz-content-sha256")) {
    headers["x-amz-content-sha256"] = toHex(await globalThis.crypto.subtle.digest("SHA-256", await file.arrayBuffer()));
  }
  return headers;
}

export async function uploadRecording(file, upload, onProgress = () => {}) {
  const headers = await uploadHeaders(file, upload);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(upload.method || "PUT", upload.url);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(Object.assign(new Error("Cannot reach the server to upload the recording. Check your connection and try again."), { status: 0 }));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve();
      let message = `The recording upload failed (HTTP ${xhr.status}).`;
      try {
        message = JSON.parse(xhr.responseText).error || message;
      } catch {
        /* S3 returns XML: keep the generic message */
      }
      reject(Object.assign(new Error(message), { status: xhr.status }));
    };
    xhr.send(file);
  });
}
