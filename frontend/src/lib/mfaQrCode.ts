/** Normalize GoTrue TOTP qr_code values for use as an <img src>. */
export function mfaQrImageSrc(qrCode: string | null | undefined): string | null {
  const value = (qrCode || "").trim();
  if (!value) return null;
  const lowered = value.toLowerCase();
  if (
    lowered.startsWith("data:") ||
    lowered.startsWith("http://") ||
    lowered.startsWith("https://") ||
    lowered.startsWith("blob:")
  ) {
    return value;
  }
  const markup = value.trimStart();
  if (markup.startsWith("<svg") || markup.startsWith("<?xml")) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(value)}`;
  }
  return `data:image/png;base64,${value}`;
}
