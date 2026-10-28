// The last recording stays on this phone (IndexedDB) until the server has all of it, so a dropped
// connection, a closed tab or a dead battery never loses a video. One recording is kept at a time.
const DB = "shelf-to-shop";
const STORE = "recordings";
const KEY = "pending";

export type Pending = { blob: Blob; savedAt: number; uploadId?: string };

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await open();
  try {
    return await new Promise<T>((resolve, reject) => {
      const req = work(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result as T);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

/** Best effort everywhere: private windows or full storage must never block recording. */
export async function keepRecording(blob: Blob): Promise<void> {
  try {
    await run("readwrite", (s) => s.put({ blob, savedAt: Date.now() } satisfies Pending, KEY));
  } catch {
    /* storage unavailable: the upload still works, it just cannot survive a closed tab */
  }
}

export async function rememberUpload(uploadId: string): Promise<void> {
  try {
    const pending = await pendingRecording();
    if (pending) await run("readwrite", (s) => s.put({ ...pending, uploadId }, KEY));
  } catch {
    /* see keepRecording */
  }
}

export async function pendingRecording(): Promise<Pending | null> {
  try {
    return (await run<Pending | undefined>("readonly", (s) => s.get(KEY))) ?? null;
  } catch {
    return null;
  }
}

export async function forgetRecording(): Promise<void> {
  try {
    await run("readwrite", (s) => s.delete(KEY));
  } catch {
    /* nothing to forget */
  }
}
