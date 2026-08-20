import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const ZSTD_MAGIC = [0x28, 0xb5, 0x2f, 0xfd];

/** Resolve either a session directory or a session.jsonl.zstd file. */
export function resolveSessionFile(input) {
  if (!input) throw new Error('session path is required');
  const absolute = path.resolve(input);
  if (!fs.existsSync(absolute)) throw new Error(`session path does not exist: ${absolute}`);
  return fs.statSync(absolute).isDirectory()
    ? path.join(absolute, 'session.jsonl.zstd')
    : absolute;
}

/** Load every JSON event from a concatenated multi-frame zstd session. */
export function loadSessionEvents(input) {
  const file = resolveSessionFile(input);
  if (!fs.existsSync(file)) throw new Error(`session file does not exist: ${file}`);
  const buffer = fs.readFileSync(file);
  const starts = [];
  for (let i = 0; i + 4 <= buffer.length; i++) {
    if (ZSTD_MAGIC.every((byte, offset) => buffer[i + offset] === byte)) starts.push(i);
  }
  const events = [];
  const frameErrors = [];
  for (let i = 0; i < starts.length; i++) {
    const end = i + 1 < starts.length ? starts[i + 1] : buffer.length;
    try {
      const output = zlib.zstdDecompressSync(buffer.subarray(starts[i], end));
      for (const line of output.toString('utf8').split('\n')) {
        const text = line.trim();
        if (!text) continue;
        try { events.push(JSON.parse(text)); } catch {}
      }
    } catch (error) {
      frameErrors.push({ frame: i, offset: starts[i], error: String(error) });
    }
  }
  return { file, events, frames: starts.length, frameErrors };
}

export function sessionIdFromFile(file) {
  return path.basename(path.dirname(resolveSessionFile(file))).replace(/^session-/, '');
}
