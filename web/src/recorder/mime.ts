// Formats in preference order: iOS Safari records MP4, Android Chrome records WebM.
export const CANDIDATE_TYPES = [
  "video/mp4;codecs=avc1.42E01E,mp4a.40.2",
  "video/mp4",
  "video/webm;codecs=vp8,opus",
  "video/webm;codecs=vp9,opus",
  "video/webm",
];

export function pickMimeType(isSupported: (type: string) => boolean): string | undefined {
  return CANDIDATE_TYPES.find((type) => {
    try {
      return isSupported(type);
    } catch {
      return false;
    }
  });
}

export type CameraProblem = "denied" | "nocamera" | "insecure";

export function cameraProblem(err: unknown, secure: boolean, hasMedia: boolean): CameraProblem {
  if (!secure) return "insecure";
  if (!hasMedia) return "nocamera";
  const name = err instanceof DOMException || err instanceof Error ? err.name : "";
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "NotReadableError") {
    return "nocamera";
  }
  return "denied";
}
