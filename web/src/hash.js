// CloudFront Origin Access Control signs requests to the API Lambda URL, and Lambda rejects a signed request whose
// body hash is unknown. So every request with a body carries `x-amz-content-sha256` = hex SHA-256 of the exact body.
export async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
