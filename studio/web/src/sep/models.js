/**
 * In-browser separation models. Weights are NOT in git and NOT on Vercel: they are fetched at runtime
 * from the Hugging Face CDN (CORS enabled), pinned to an exact commit, verified against SHA-256 and
 * kept in the browser (OPFS, Cache Storage fallback), so they download once.
 *
 * Runtime: onnxruntime-web 1.30.0 (MIT), copied to /ort by scripts/copy-ort.mjs. WebGPU when the GPU
 * has shader-f16, otherwise WASM (SIMD, and threads when the page is cross-origin isolated).
 *
 * Licences are summarised in THIRD_PARTY_LICENSES.md at the repo root. Read the notes: the MIT tag on
 * the Demucs ONNX export does not settle the licence of the trained weights.
 */
export const ORT_VERSION = '1.30.0';
const origin = typeof self !== 'undefined' && self.location ? self.location.origin : '';
export const ORT_LOCAL_BASE = `${origin}/ort/`;
export const ORT_MODULE_URL = `${ORT_LOCAL_BASE}ort.webgpu.min.mjs`;
export const ORT_WASM_BASE = ORT_LOCAL_BASE;
export const ORT_CDN_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;
export const ORT_CDN_MODULE_URL = `${ORT_CDN_BASE}ort.webgpu.min.mjs`;

export const MODEL_CACHE_NAME = 'muser-sep-models-v1';
export const MODEL_OPFS_DIR = 'muser-sep-models-v1';

const hf = (repo, revision, path) => `https://huggingface.co/${repo}/resolve/${revision}/${path}`;
const MB = 1000 * 1000;

export const MODELS = {
  htdemucs: {
    id: 'htdemucs',
    adapter: 'htdemucs',
    label: 'Demucs, 4 stems',
    short: 'drums, bass, vocals, other',
    description: 'HTDemucs (Meta) exported to ONNX (demucs-web build, STFT done in the worker). The classic four-stem split. Best all-round quality of the three.',
    stems: ['drums', 'bass', 'other', 'vocals'],
    sampleRate: 44100,
    chunkSamples: 343980, // 7.8 s, fixed by the export
    overlap: 0.25,
    sizeBytes: 180534758,
    minMemoryGB: 4,
    ramHint: 'Needs roughly 1 to 1.5 GB of free RAM while it runs.',
    speedHint: 'WebGPU: about real time or faster. WASM: several times slower than real time.',
    warning: 'Large download (181 MB, once).',
    files: [
      {
        role: 'model',
        name: 'htdemucs_embedded.onnx',
        url: hf('timcsy/demucs-web-onnx', '92e33df61cfc9eb820272aaa62d2ef6dcf4d950d', 'htdemucs_embedded.onnx'),
        bytes: 180534758,
        sha256: 'e5e425c17683f163a472462eb5f5a4ffcd11c31858d57fbd0833b012d8b88077',
      },
    ],
    license: {
      spdx: 'MIT (export) / weights: see note',
      name: 'HTDemucs ONNX (timcsy demucs-web) from Demucs (facebookresearch)',
      url: 'https://huggingface.co/timcsy/demucs-web-onnx',
      note: 'The Demucs code is MIT. The ONNX repo is tagged MIT, but the pretrained weights were trained on MUSDB18-HQ plus licensed data and their terms are not stated in that repo. Treat as personal and research use unless you have cleared it.',
      caveat: 'weights licence unresolved, personal use',
    },
  },

  mini: {
    id: 'mini',
    adapter: 'mini',
    label: 'Light preview (Mini-RoFormer)',
    short: '4 stems, Mini-BS-RoFormer',
    description: 'Quick draft split into vocals, drums, bass and other. Smallest download, fastest - good for auditioning a track or checking a split before committing to the big model.',
    stems: ['vocals', 'drums', 'bass', 'other'],
    sampleRate: 44100,
    chunkSamples: 352800, // 8 s, fixed by the model card / ONNX example
    overlap: 0.25,
    sizeBytes: 96538997,
    ramHint: 'About 1.5 GB of free RAM.',
    speedHint: 'Roughly 1–3× real-time on a mid-range GPU; 5–15× slower than real-time on CPU.',
    warning: null,
    files: [
      {
        role: 'model',
        name: 'freq_weights.onnx',
        url: hf('HiDolen/Mini-BS-RoFormer-V2.5-46.2M', '38dafc78834607aec57d8c0cb3568523f9ea5563', 'onnx/freq_weights.onnx'),
        bytes: 96538997,
        sha256: 'c019650a7fb9e6a208353fead62471ed6ffdf20a3069ddadd8278edeb411d556',
      },
    ],
    license: {
      spdx: 'MIT',
      name: 'Mini-BS-RoFormer-V2.5-46.2M (HiDolen)',
      url: 'https://huggingface.co/HiDolen/Mini-BS-RoFormer-V2.5-46.2M',
    },
  },

  duality: {
    id: 'duality',
    adapter: 'duality',
    label: 'Clean vocals',
    short: '2 stems · Mel-Band RoFormer Duality',
    description: 'Vocals and instrumental. A distilled Mel-Band RoFormer tuned for clean lead-vocal / acapella extraction.',
    stems: ['vocals', 'instrumental'],
    sampleRate: 44100,
    chunkSamples: 484659, // 441 * 1099 -> exactly 1100 STFT frames, ~11 s
    overlap: 0.25,
    sizeBytes: 5539495 + 213244940,
    ramHint: 'About 2 GB of free RAM.',
    speedHint: 'Needs a GPU for comfortable speed; CPU fallback is very slow (many minutes per song).',
    warning: 'Works best on a desktop GPU (WebGPU). CPU/WASM works but is noticeably slower.',
    // ORT session options merged into the WebGPU execution-provider entry.
    webgpuOptions: { storageBufferCacheMode: 'simple' },
    files: [
      {
        role: 'model',
        name: 'duality_student_core_t1100.onnx',
        url: hf('musetric/mel-band-roformer-duality-student-onnx', '0e04989195c31669276cdf05f5f840f8cf2f7e6f', 'duality_student_core_t1100.onnx'),
        bytes: 5539495,
        sha256: '0198c50e408bf040522aa1b12042628e3218c61c958f06fdc9bb1aad9465a594',
      },
      {
        // External-data sidecar. `name` MUST match the `location` recorded
        // inside the .onnx file (checked with `onnx` during development).
        role: 'data',
        name: 'duality_student_core_t1100.onnx.data',
        url: hf('musetric/mel-band-roformer-duality-student-onnx', '0e04989195c31669276cdf05f5f840f8cf2f7e6f', 'duality_student_core_t1100.onnx.data'),
        bytes: 213244940,
        sha256: 'd7bea7fae93748cbc210208b8b9728dc274e1cc9e0bdad852ad08294ee1c335b',
      },
    ],
    license: {
      spdx: 'Apache-2.0',
      name: 'Mel-Band RoFormer Duality student ONNX (musetric)',
      url: 'https://huggingface.co/musetric/mel-band-roformer-duality-student-onnx',
    },
  },
};

/** Display order in the picker. */
export const MODEL_ORDER = ['htdemucs', 'mini', 'duality'];

export function formatBytes(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + ' GB';
  if (n >= MB) return Math.round(n / MB) + ' MB';
  return Math.round(n / 1000) + ' KB';
}
