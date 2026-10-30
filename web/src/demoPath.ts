// The demo path on Home: shown to visitors who opened a copy of the sample shop (hackathon demo only).
// Kept in this browser; nothing about it is sent to the server.

const SAMPLE = "sts_path_sample";
const HIDDEN = "sts_path_hidden";
const READ = "sts_path_read";

function get(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function set(key: string, on: boolean): void {
  try {
    if (on) localStorage.setItem(key, "1");
    else localStorage.removeItem(key);
  } catch {
    /* storage blocked: the path simply does not show */
  }
}

/** A demo sign-in just opened the sample shop (true) or a new empty shop (false). */
export function startedFromSample(sample: boolean): void {
  set(SAMPLE, sample);
  set(HIDDEN, false);
  set(READ, false);
}

export const showPath = (): boolean => get(SAMPLE) && !get(HIDDEN);
export const hidePath = (): void => set(HIDDEN, true);
export const sawVideoDetails = (): void => set(READ, true);
export const hasSeenVideoDetails = (): boolean => get(READ);
