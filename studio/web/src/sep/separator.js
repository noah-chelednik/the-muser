/**
 * Backend-agnostic chunking / overlap-add driver.
 *
 *   separateTrack({ adapter, run, left, right, overlap, onChunk, isCancelled })
 *
 * `run(feeds)` executes one model forward pass and resolves to
 * { outputName: Float32Array }. Everything else (STFT, masking, iSTFT,
 * cross-fading, normalising) happens here so it can be unit-tested in Node
 * with onnxruntime and shipped unchanged in a Web Worker.
 */

import { MemorySink } from './sinks.js';

export class CancelledError extends Error {
  constructor() { super('Separation cancelled'); this.name = 'CancelledError'; }
}

/** Start offsets of every chunk (the last one is end-aligned so it holds real audio). */
export function planChunks(totalSamples, chunkSamples, overlapSamples) {
  const step = chunkSamples - overlapSamples;
  const starts = [0];
  let s = 0;
  while (s + chunkSamples < totalSamples) {
    s = Math.min(s + step, totalSamples - chunkSamples);
    starts.push(s);
  }
  return starts;
}

function rms(a, n) {
  let e = 0;
  for (let i = 0; i < n; i++) e += a[i] * a[i];
  return Math.sqrt(e / Math.max(1, n));
}

/**
 * Streaming overlap-add. Only a two-chunk window of accumulators lives in RAM:
 * once chunk i is done, everything before chunk i+1's start can no longer
 * change, so it is normalised and flushed to `sink` and the window slides.
 * (Memory is O(chunk), not O(track x stems).)
 *
 * @param {{write: Function}} [sink] defaults to an in-memory sink
 */
export async function separateTrack({
  adapter, run, left, right, overlap = 0.25, onChunk, isCancelled, sanityCheck, sink,
}) {
  const N = left.length;
  const C = adapter.chunkSamples;
  const ov = Math.min(Math.floor(C * overlap), C - 1);
  const starts = planChunks(N, C, ov);
  const total = starts.length;
  sink = sink || new MemorySink(N);

  const win = {}; // name -> [Float32Array(C), Float32Array(C)]  (window origin = start of current chunk)
  const wwin = new Float32Array(C);
  const bufL = new Float32Array(C);
  const bufR = new Float32Array(C);
  let sanityDone = false;
  const t0 = Date.now();

  for (let i = 0; i < total; i++) {
    if (isCancelled?.()) throw new CancelledError();
    const start = starts[i];
    const len = Math.min(C, N - start);
    bufL.fill(0); bufR.fill(0);
    bufL.set(left.subarray(start, start + len));
    bufR.set(right.subarray(start, start + len));

    const { feeds, ctx } = adapter.prepare(bufL.slice(), bufR.slice());
    const outputs = await run(feeds);
    const stems = adapter.finish(outputs, ctx);

    if (!sanityDone && sanityCheck && rms(bufL, len) > 1e-3) {
      sanityDone = true;
      sanityCheck({ input: [bufL, bufR], stems, len });
    }

    // Weights: linear cross-fades, no fade on the outer edges of the track.
    const fadeIn = i > 0 ? ov : 0;
    const fadeOut = i < total - 1 ? ov : 0;
    const w = (j) => {
      let v = 1;
      if (j < fadeIn) v = (j + 1) / (fadeIn + 1);
      const k = C - 1 - j; // distance from the end of the chunk
      if (k < fadeOut) v = Math.min(v, (k + 1) / (fadeOut + 1));
      return v;
    };
    for (const [name, [sl, sr]] of Object.entries(stems)) {
      if (!win[name]) win[name] = [new Float32Array(C), new Float32Array(C)];
      const [al, ar] = win[name];
      for (let j = 0; j < len; j++) {
        const wj = w(j);
        al[j] += sl[j] * wj;
        ar[j] += sr[j] * wj;
      }
    }
    for (let j = 0; j < len; j++) wwin[j] += w(j);

    // Flush the finished region [start, nextStart) and slide the window.
    const nextStart = i < total - 1 ? starts[i + 1] : N;
    const fin = Math.min(nextStart - start, len);
    for (const [name, [al, ar]] of Object.entries(win)) {
      const outL = new Float32Array(fin);
      const outR = new Float32Array(fin);
      for (let j = 0; j < fin; j++) {
        const inv = wwin[j] > 0 ? 1 / wwin[j] : 0;
        outL[j] = al[j] * inv; outR[j] = ar[j] * inv;
      }
      await sink.write(name, 0, start, outL);
      await sink.write(name, 1, start, outR);
      al.copyWithin(0, fin); ar.copyWithin(0, fin);
      al.fill(0, C - fin); ar.fill(0, C - fin);
    }
    wwin.copyWithin(0, fin); wwin.fill(0, C - fin);

    const done = i + 1;
    const elapsed = Date.now() - t0;
    onChunk?.({ done, total, elapsedMs: elapsed, etaMs: (elapsed / done) * (total - done) });
    // Let the event loop breathe (progress messages, cancel).
    await new Promise((r) => setTimeout(r, 0));
  }

  return { sink, stems: sink.data || null, chunks: total };
}
