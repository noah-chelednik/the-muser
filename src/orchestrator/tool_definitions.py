"""Tool schemas for The Muser orchestration.

Tool definitions stored in Anthropic format (with input_schema) for backward
compatibility. The `get_all_tools_openai()` function converts them to
OpenAI format for use with LiteLLM, Ollama, Groq, and other providers.
"""

GENERATION_TOOLS = [
    {
        "name": "create_composition_plan",
        "description": (
            "Create a structured composition plan for a new piece. "
            "Establishes form, key, tempo, instrumentation, and section layout. "
            "Must be called before generating any notation or audio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the composition",
                },
                "genre": {
                    "type": "string",
                    "description": "Musical genre (classical, pop, rock, jazz, electronic, etc.)",
                },
                "form": {
                    "type": "string",
                    "description": "Musical form (sonata, ABA, verse-chorus, through-composed, etc.)",
                },
                "key": {
                    "type": "string",
                    "description": "Key signature (e.g., 'C major', 'A minor', 'Bb major')",
                },
                "tempo": {
                    "type": "integer",
                    "description": "Tempo in BPM",
                },
                "time_signature": {
                    "type": "string",
                    "description": "Time signature (e.g., '4/4', '3/4', '6/8')",
                },
                "instrumentation": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of instruments/voices",
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "measures": {"type": "integer"},
                            "description": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                    "description": "Planned sections of the composition",
                },
                "mood": {
                    "type": "string",
                    "description": "Emotional character or mood of the piece",
                },
                "duration_estimate_s": {
                    "type": "integer",
                    "description": "Estimated duration in seconds",
                },
            },
            "required": ["title", "genre", "instrumentation"],
        },
    },
    {
        "name": "update_composition_plan",
        "description": (
            "Modify an existing composition plan. "
            "Use to adjust form, add/remove sections, change instrumentation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "object",
                    "description": "Key-value pairs to update in the composition plan",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the update",
                },
            },
            "required": ["updates", "reason"],
        },
    },
    {
        "name": "generate_notation_claude",
        "description": (
            "Generate MusicXML notation directly using Claude's music knowledge. "
            "Best for short passages (1-8 bars), specific harmonic progressions, "
            "or when precise control over every note is needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_name": {
                    "type": "string",
                    "description": "Name of the section being composed",
                },
                "instructions": {
                    "type": "string",
                    "description": "Detailed musical instructions for the passage",
                },
                "key": {"type": "string", "description": "Key signature"},
                "time_signature": {"type": "string", "description": "Time signature"},
                "tempo": {"type": "integer", "description": "Tempo in BPM"},
                "instruments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Instruments to write for",
                },
                "measures": {
                    "type": "integer",
                    "description": "Number of measures to generate",
                },
            },
            "required": ["section_name", "instructions", "instruments"],
        },
    },
    {
        "name": "generate_notation_notagen",
        "description": (
            "Generate symbolic music notation using NotaGen AI model. "
            "Produces complete musical passages in ABC notation, then converted to MusicXML. "
            "Best for classical/romantic period styles and longer passages. "
            "Requires GPU; will unload other models from VRAM."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": [
                        "Medieval", "Renaissance", "Baroque", "Classical",
                        "Romantic", "Modern",
                    ],
                    "description": "Musical period style",
                },
                "composer": {
                    "type": "string",
                    "description": "Composer style to emulate (e.g., 'Chopin', 'Bach', 'Mozart')",
                },
                "instrumentation": {
                    "type": "string",
                    "description": "Instrumentation description (e.g., 'Piano', 'String Quartet')",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum generation length in tokens (default: 1024)",
                },
                "section_name": {
                    "type": "string",
                    "description": "Section to assign the output to",
                },
            },
            "required": ["period", "composer", "instrumentation"],
        },
    },
    {
        "name": "generate_audio_acestep",
        "description": (
            "Generate audio using ACE-Step text-to-music model. "
            "Produces 48 kHz WAV audio from text tags and optional lyrics. "
            "Best for modern genres (pop, rock, electronic, jazz). "
            "Use infer_step=27 for fast drafts, infer_step=50 for final quality. "
            "Tags should be descriptive paragraphs (50-150 words) covering genre, instruments, mood, and production style. "
            "Use '[instrumental]' as lyrics for instrumental tracks. "
            "Requires GPU; will unload other models from VRAM."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "string",
                    "description": (
                        "Descriptive paragraph (50-150 words) covering genre, instruments, "
                        "mood, vocal style, and production notes "
                        "(e.g., 'A bright upbeat synth pop track with female vocals...')"
                    ),
                },
                "lyrics": {
                    "type": "string",
                    "description": (
                        "Song lyrics with structure markers like [verse], [chorus], [bridge]. "
                        "Use '[instrumental]' for instrumental tracks (required if no lyrics)."
                    ),
                },
                "duration_s": {
                    "type": "integer",
                    "description": "Target duration in seconds (default: 120, max: 300)",
                },
                "num_candidates": {
                    "type": "integer",
                    "description": "Number of candidate generations (default: 1, max: 4)",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility",
                },
                "infer_step": {
                    "type": "integer",
                    "description": (
                        "Diffusion inference steps. 27=fast draft (~30s), "
                        "50=quality (~90s). Default: 50."
                    ),
                },
                "guidance_scale": {
                    "type": "number",
                    "description": (
                        "Classifier-free guidance scale. "
                        "Range: 1.0-10.0. Default: 4.0. Values above 6.0 degrade quality."
                    ),
                },
            },
            "required": ["tags"],
        },
    },
    {
        "name": "generate_audio_acestep_lora",
        "description": (
            "Generate audio using ACE-Step with a custom voice LoRA. "
            "Same as generate_audio_acestep but applies a trained LoRA "
            "for a specific voice character."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tags": {"type": "string", "description": "Style/genre tags"},
                "lyrics": {"type": "string", "description": "Song lyrics"},
                "lora_path": {
                    "type": "string",
                    "description": "Path to the LoRA weights file",
                },
                "duration_s": {"type": "integer", "description": "Target duration"},
                "seed": {"type": "integer", "description": "Random seed"},
                "infer_step": {
                    "type": "integer",
                    "description": "Diffusion inference steps (27=fast, 60=quality)",
                },
                "guidance_scale": {
                    "type": "number",
                    "description": "CFG guidance scale (1.0-10.0, default: 4.0)",
                },
            },
            "required": ["tags", "lora_path"],
        },
    },
]

V15_TOOLS = [
    {
        "name": "generate_audio_acestep_v15",
        "description": (
            "Generate audio using ACE-Step v1.5 with LLM pre-planning, "
            "native batch generation, and metadata-aware conditioning. "
            "Supports BPM, key, and time signature parameters. "
            "Use inference_steps=8 for turbo drafts, 50 for final quality. "
            "Tags should be descriptive paragraphs (50-150 words). "
            "Requires GPU; will unload other models from VRAM."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "string",
                    "description": (
                        "Descriptive paragraph (50-150 words) covering genre, "
                        "instruments, mood, vocal style, and production notes"
                    ),
                },
                "lyrics": {
                    "type": "string",
                    "description": (
                        "Song lyrics with structure markers. "
                        "Use '[instrumental]' for instrumental tracks."
                    ),
                },
                "duration_s": {
                    "type": "integer",
                    "description": "Target duration in seconds (default: 120, max: 600)",
                },
                "num_candidates": {
                    "type": "integer",
                    "description": "Number of candidates to generate in batch (default: 1, max: 8)",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility (-1 for random)",
                },
                "infer_step": {
                    "type": "integer",
                    "description": "Inference steps. 8=turbo draft, 50=quality. Default: 8.",
                },
                "guidance_scale": {
                    "type": "number",
                    "description": "CFG guidance scale (default: 7.0)",
                },
                "bpm": {
                    "type": "integer",
                    "description": "Target BPM (30-300, auto-detected if omitted)",
                },
                "key_scale": {
                    "type": "string",
                    "description": "Target key (e.g., 'C major', 'A minor')",
                },
                "time_signature": {
                    "type": "string",
                    "description": "Time signature numerator (e.g., '4' for 4/4, '3' for 3/4)",
                },
            },
            "required": ["tags"],
        },
    },
    {
        "name": "repaint_audio_acestep",
        "description": (
            "Regenerate a specific time interval of existing audio using ACE-Step v1.5. "
            "Keeps audio outside the interval unchanged. "
            "Useful for fixing sections or regenerating parts you don't like."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "src_audio": {
                    "type": "string",
                    "description": "Path to the source audio file",
                },
                "tags": {
                    "type": "string",
                    "description": "Descriptive paragraph for the repainted region",
                },
                "start_s": {
                    "type": "number",
                    "description": "Start of repaint region in seconds",
                },
                "end_s": {
                    "type": "number",
                    "description": "End of repaint region in seconds",
                },
                "lyrics": {
                    "type": "string",
                    "description": "Lyrics for the repainted region (optional)",
                },
                "seed": {"type": "integer", "description": "Random seed"},
            },
            "required": ["src_audio", "tags", "start_s", "end_s"],
        },
    },
    {
        "name": "cover_audio_acestep",
        "description": (
            "Apply style transfer to existing audio using ACE-Step v1.5. "
            "Preserves melody and structure while changing instrumentation, genre, or mood. "
            "cover_strength controls how much the style changes (0.0=identical, 1.0=fully new)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "src_audio": {
                    "type": "string",
                    "description": "Path to the source audio file",
                },
                "tags": {
                    "type": "string",
                    "description": "Descriptive paragraph for the new style",
                },
                "cover_strength": {
                    "type": "number",
                    "description": "Style transfer strength (0.0-1.0, default: 0.5)",
                },
                "lyrics": {
                    "type": "string",
                    "description": "New lyrics (optional, keeps original if omitted)",
                },
                "seed": {"type": "integer", "description": "Random seed"},
            },
            "required": ["src_audio", "tags"],
        },
    },
    {
        "name": "extend_audio_acestep",
        "description": (
            "Extend existing audio by appending new AI-generated content. "
            "Uses ACE-Step v1.5 auto-completion to seamlessly continue the audio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "src_audio": {
                    "type": "string",
                    "description": "Path to the source audio file to extend",
                },
                "tags": {
                    "type": "string",
                    "description": "Descriptive paragraph for the extension",
                },
                "extend_s": {
                    "type": "number",
                    "description": "Duration of content to add in seconds (default: 30)",
                },
                "lyrics": {
                    "type": "string",
                    "description": "Lyrics for the extension (optional)",
                },
                "seed": {"type": "integer", "description": "Random seed"},
            },
            "required": ["src_audio", "tags"],
        },
    },
]

VOICE_TOOLS = [
    {
        "name": "render_vocals_diffsinger",
        "description": (
            "Synthesize singing vocals from a MusicXML score using DiffSinger. "
            "Score-driven synthesis: pitch and timing from the score, phonemes from lyrics. "
            "Supports expressive controls for breathiness, tension, voicing, and gender."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "musicxml_path": {
                    "type": "string",
                    "description": "Path to MusicXML file with vocal line, or .ds project file",
                },
                "lyrics": {
                    "type": "string",
                    "description": "Lyrics text aligned to the vocal part",
                },
                "model_name": {
                    "type": "string",
                    "description": "DiffSinger voice model name (from registry) or directory path",
                },
                "pitch_expressiveness": {
                    "type": "number",
                    "description": "Pitch variation scale (0.0=flat, 1.0=natural, >1.0=exaggerated)",
                },
                "breathiness": {
                    "type": "number",
                    "description": "Breathiness level (0.0=clean, 1.0=very breathy)",
                },
                "voicing": {
                    "type": "number",
                    "description": "Voicing strength (0.0=whispered, 1.0=fully voiced)",
                },
                "tension": {
                    "type": "number",
                    "description": "Vocal tension (0.0=relaxed, 1.0=very tense)",
                },
                "energy": {
                    "type": "number",
                    "description": "Energy/volume scale (0.5=soft, 1.0=normal, 1.5=loud)",
                },
                "gender": {
                    "type": "number",
                    "description": "Gender shift (-1.0=feminize, 0.0=neutral, 1.0=masculinize)",
                },
            },
            "required": ["musicxml_path", "lyrics"],
        },
    },
    {
        "name": "convert_voice_rvc",
        "description": (
            "Convert audio vocals to a different voice using RVC/Applio. "
            "Takes existing vocal audio and transforms it to match a target voice model."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "input_audio": {
                    "type": "string",
                    "description": "Path to input vocal audio file",
                },
                "voice_id": {
                    "type": "string",
                    "description": "Voice model ID from the registry",
                },
                "transpose": {
                    "type": "integer",
                    "description": "Pitch shift in semitones (positive=up, negative=down)",
                },
                "f0_method": {
                    "type": "string",
                    "enum": ["rmvpe", "crepe", "pm", "harvest"],
                    "description": "Pitch extraction method (default: rmvpe)",
                },
            },
            "required": ["input_audio", "voice_id"],
        },
    },
    {
        "name": "select_voice",
        "description": "Select a voice from the voice model registry for use in composition.",
        "input_schema": {
            "type": "object",
            "properties": {
                "voice_id": {
                    "type": "string",
                    "description": "Voice model ID to select",
                },
            },
            "required": ["voice_id"],
        },
    },
    {
        "name": "separate_stems_demucs",
        "description": (
            "Separate audio into stems (vocals, drums, bass, other) using Demucs. "
            "Useful for isolating vocals before voice conversion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "input_audio": {
                    "type": "string",
                    "description": "Path to input audio file",
                },
                "two_stems": {
                    "type": "boolean",
                    "description": "If true, only separate vocals/accompaniment (default: true)",
                },
            },
            "required": ["input_audio"],
        },
    },
    {
        "name": "feminize_audio",
        "description": (
            "Apply multi-stage feminization to audio. Converts male vocals to "
            "convincing female voice using layered formant shifting and voice conversion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "input_audio": {
                    "type": "string",
                    "description": "Path to input audio file",
                },
                "preset": {
                    "type": "string",
                    "enum": [
                        "powerful_mezzo",
                        "soft_feminine",
                        "androgynous",
                    ],
                    "description": "Feminization preset",
                },
                "voice_id": {
                    "type": "string",
                    "description": "RVC voice model ID from registry",
                },
            },
            "required": ["input_audio", "preset", "voice_id"],
        },
    },
    {
        "name": "train_voice_lora",
        "description": (
            "Start ACE-Step LoRA voice training as a background process. "
            "Takes a directory of training audio files with sidecar metadata "
            "and trains a LoRA adapter for voice cloning. Returns immediately "
            "with a process ID — training runs in the background."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "voice_name": {
                    "type": "string",
                    "description": "Name for the voice model (e.g., 'noah', 'noah-fem')",
                },
                "training_data_dir": {
                    "type": "string",
                    "description": "Directory containing training audio files with _prompt.txt and _lyrics.txt sidecars",
                },
                "epochs": {
                    "type": "integer",
                    "description": "Number of training epochs (default: 500)",
                },
                "lora_rank": {
                    "type": "integer",
                    "description": "LoRA rank — lower=faster/less expressive, higher=slower/more expressive (default: 32)",
                },
                "learning_rate": {
                    "type": "number",
                    "description": "Learning rate (default: 0.0001)",
                },
            },
            "required": ["voice_name", "training_data_dir"],
        },
    },
]

VALIDATION_TOOLS = [
    {
        "name": "validate_notation",
        "description": (
            "Run music theory validation checks on a MusicXML score. "
            "Checks instrument ranges, rhythm consistency, parallel motion, "
            "repetitiveness, and empty sections. Always validate before rendering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "musicxml_path": {
                    "type": "string",
                    "description": "Path to MusicXML file to validate",
                },
            },
            "required": ["musicxml_path"],
        },
    },
    {
        "name": "validate_audio",
        "description": (
            "Validate an audio file for common issues: silence, clipping, "
            "unexpected duration. Run after any audio generation or rendering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {
                    "type": "string",
                    "description": "Path to WAV file to validate",
                },
                "expected_duration_s": {
                    "type": "number",
                    "description": "Expected duration in seconds (optional)",
                },
            },
            "required": ["wav_path"],
        },
    },
]

RENDERING_TOOLS = [
    {
        "name": "render_preview",
        "description": (
            "Quickly render a MusicXML score to audio using FluidSynth. "
            "Fast preview quality — use for iterative feedback loops."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "musicxml_path": {
                    "type": "string",
                    "description": "Path to MusicXML file",
                },
                "soundfont": {
                    "type": "string",
                    "enum": ["preview", "draft"],
                    "description": "Soundfont quality level (default: preview)",
                },
            },
            "required": ["musicxml_path"],
        },
    },
    {
        "name": "render_score_pdf",
        "description": (
            "Render a publication-quality PDF score from MusicXML using LilyPond. "
            "For final output — slower but produces professional engraving."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "musicxml_path": {
                    "type": "string",
                    "description": "Path to MusicXML file",
                },
                "renderer": {
                    "type": "string",
                    "enum": ["lilypond", "musescore"],
                    "description": "Rendering engine (default: lilypond)",
                },
            },
            "required": ["musicxml_path"],
        },
    },
    {
        "name": "render_quality_audio",
        "description": (
            "Render high-quality audio from MIDI using sfizz with orchestral samples. "
            "Slower but significantly better than FluidSynth preview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "midi_path": {
                    "type": "string",
                    "description": "Path to MIDI file",
                },
                "sfz_instrument": {
                    "type": "string",
                    "description": "SFZ instrument to use (default: auto from MIDI)",
                },
            },
            "required": ["midi_path"],
        },
    },
]

STATE_TOOLS = [
    {
        "name": "update_memory_document",
        "description": (
            "Update a section of the Musical Memory Document. "
            "For generic updates to project, form_plan, orchestration_state, or voice_plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": [
                        "project", "form_plan", "theme_catalog",
                        "harmonic_plan", "orchestration_state",
                        "voice_plan", "revision_notes",
                    ],
                    "description": "Which section of the memory document to update",
                },
                "data": {
                    "type": "object",
                    "description": "Data to merge into the specified section",
                },
            },
            "required": ["section", "data"],
        },
    },
    {
        "name": "add_theme",
        "description": (
            "Add a musical theme to the composition's theme catalog. "
            "Themes are named motifs or melodic ideas that recur throughout the piece."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "theme_id": {
                    "type": "string",
                    "description": "Unique identifier for the theme (e.g., 'main_theme', 'bridge_motif')",
                },
                "abc_snippet": {
                    "type": "string",
                    "description": "ABC notation snippet of the theme (e.g., 'CDEF GABc')",
                },
                "character": {
                    "type": "string",
                    "description": "Character description of the theme (e.g., 'Lyrical, ascending, hopeful')",
                },
            },
            "required": ["theme_id", "character"],
        },
    },
    {
        "name": "record_theme_appearance",
        "description": "Record where a theme appears in the composition.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme_id": {
                    "type": "string",
                    "description": "Theme ID from the catalog",
                },
                "location": {
                    "type": "string",
                    "description": "Where the theme appears (e.g., 'mvt1:m45', 'chorus:m1-4')",
                },
                "description": {
                    "type": "string",
                    "description": "How the theme is used here (e.g., 'Inverted in the bass')",
                },
            },
            "required": ["theme_id", "location"],
        },
    },
    {
        "name": "update_harmonic_plan",
        "description": (
            "Update the harmonic plan: add key centers or modulation points. "
            "Tracks the tonal structure of the composition."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add_key_center", "add_modulation"],
                    "description": "Type of harmonic plan update",
                },
                "measure": {
                    "type": "integer",
                    "description": "Measure number",
                },
                "key": {
                    "type": "string",
                    "description": "Key for add_key_center (e.g., 'G major')",
                },
                "from_key": {
                    "type": "string",
                    "description": "Source key for add_modulation",
                },
                "to_key": {
                    "type": "string",
                    "description": "Target key for add_modulation",
                },
            },
            "required": ["operation", "measure"],
        },
    },
    {
        "name": "add_revision_note",
        "description": "Add a revision note to the composition. Only the 5 most recent notes are kept.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The revision note text",
                },
            },
            "required": ["note"],
        },
    },
    {
        "name": "update_section_status",
        "description": "Update the status of a composition section.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section_name": {
                    "type": "string",
                    "description": "Name of the section",
                },
                "status": {
                    "type": "string",
                    "enum": ["planned", "in_progress", "complete"],
                    "description": "New status for the section",
                },
            },
            "required": ["section_name", "status"],
        },
    },
    {
        "name": "save_checkpoint",
        "description": "Save current composition state as a git commit for version control.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message describing what changed",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "list_sections",
        "description": "List all completed sections of the current composition.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_section",
        "description": "Retrieve a specific section's MusicXML content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section_name": {
                    "type": "string",
                    "description": "Name of the section to retrieve",
                },
            },
            "required": ["section_name"],
        },
    },
    {
        "name": "plan_piece",
        "description": (
            "Create a hierarchical Level 1 piece plan with sections and measure ranges. "
            "Establishes the top-level form structure that can be progressively refined "
            "with zoom_in. Each section gets a name, measure range, key, tempo, and description."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "form": {
                    "type": "string",
                    "description": "Musical form (e.g., 'sonata', 'ABA', 'verse-chorus', 'rondo')",
                },
                "total_measures": {
                    "type": "integer",
                    "description": "Total number of measures in the piece",
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Section name"},
                            "start_measure": {"type": "integer", "description": "Starting measure number"},
                            "end_measure": {"type": "integer", "description": "Ending measure number"},
                            "key": {"type": "string", "description": "Key signature for this section"},
                            "tempo": {"type": "integer", "description": "Tempo in BPM"},
                            "description": {"type": "string", "description": "Musical description of the section"},
                        },
                        "required": ["name", "start_measure", "end_measure"],
                    },
                    "description": "Sections of the piece with measure ranges",
                },
            },
            "required": ["form", "total_measures", "sections"],
        },
    },
    {
        "name": "zoom_in",
        "description": (
            "Zoom into a section to see phrase-level detail (Level 2), note-level detail (Level 3), "
            "or arrangement detail (Level 4). Call repeatedly to drill deeper. "
            "Use after plan_piece to refine individual sections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Name of the section to zoom into",
                },
            },
            "required": ["section"],
        },
    },
    {
        "name": "zoom_out",
        "description": (
            "Zoom out to see the overview at the next higher level of the hierarchical plan. "
            "Moves from arrangement (L4) -> note (L3) -> phrase (L2) -> full piece (L1)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

POSTPRODUCTION_TOOLS = [
    {
        "name": "apply_postproduction",
        "description": (
            "Apply automated mixing and mastering to an audio file. "
            "Includes loudness normalization, EQ, compression based on genre preset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {
                    "type": "string",
                    "description": "Path to input WAV file",
                },
                "genre": {
                    "type": "string",
                    "enum": ["default", "classical", "pop", "rock", "electronic"],
                    "description": "Genre preset for mastering (default: default)",
                },
            },
            "required": ["wav_path"],
        },
    },
    {
        "name": "export_final",
        "description": (
            "Export the final composition to distributable formats (WAV, MP3, FLAC). "
            "Applies loudness normalization and format conversion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {
                    "type": "string",
                    "description": "Path to the mastered WAV file",
                },
                "formats": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["wav", "mp3", "flac"],
                    },
                    "description": "Output formats (default: all)",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for exported files",
                },
            },
            "required": ["wav_path"],
        },
    },
    {
        "name": "remix_track",
        "description": (
            "Mix processed vocals with an instrumental backing track. "
            "Applies a 5-stage vocal processing chain (de-essing, compression, "
            "saturation, early reflections, reverb) before mixing. "
            "Handles sample rate matching, vocal level, and stereo panning. "
            "Run BEFORE genre mastering (apply_postproduction)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vocal_path": {
                    "type": "string",
                    "description": "Path to the vocal WAV file",
                },
                "instrumental_path": {
                    "type": "string",
                    "description": "Path to the instrumental backing WAV file",
                },
                "vocal_level_db": {
                    "type": "number",
                    "description": (
                        "Vocal gain adjustment in dB (positive=louder, "
                        "negative=quieter, default: 0.0)"
                    ),
                },
                "vocal_pan": {
                    "type": "number",
                    "description": (
                        "Stereo panning for vocals (-1.0=hard left, "
                        "0.0=center, 1.0=hard right, default: 0.0)"
                    ),
                },
                "apply_vocal_processing": {
                    "type": "boolean",
                    "description": (
                        "Whether to apply the vocal processing chain before "
                        "mixing (default: true)"
                    ),
                },
                "vocal_style": {
                    "type": "string",
                    "enum": ["default", "intimate", "powerful", "ethereal"],
                    "description": (
                        "Vocal processing style preset (default: 'default'). "
                        "'intimate'=short room, 'powerful'=medium hall, "
                        "'ethereal'=long hall with high diffusion."
                    ),
                },
            },
            "required": ["vocal_path", "instrumental_path"],
        },
    },
]


PLAYBACK_TOOLS = [
    {
        "name": "play_audio",
        "description": "Play an audio file through system speakers so the user can hear it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Path to audio file to play"},
                "start_s": {"type": "number", "description": "Start playback at this offset in seconds (default: 0)"},
                "duration_s": {"type": "number", "description": "Play for this many seconds (0 = full file)"},
            },
            "required": ["wav_path"],
        },
    },
]

EFFECTS_TOOLS = [
    {
        "name": "apply_eq",
        "description": "Apply parametric EQ to an audio file. Boost or cut a specific frequency band.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Input audio file path"},
                "frequency_hz": {"type": "integer", "description": "Center frequency in Hz (20-20000)"},
                "gain_db": {"type": "number", "description": "Gain in dB (-24 to +24)"},
                "q": {"type": "number", "description": "Q factor / bandwidth (0.1-10, default: 1.0)"},
                "output_path": {"type": "string", "description": "Output path (auto-generated if omitted)"},
            },
            "required": ["wav_path", "frequency_hz", "gain_db"],
        },
    },
    {
        "name": "apply_reverb",
        "description": "Apply reverb to an audio file. Simulates room reflections.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Input audio file path"},
                "room_size": {"type": "number", "description": "Room size (0.0=small, 1.0=large hall, default: 0.5)"},
                "decay": {"type": "number", "description": "Decay amount (0.0-1.0, default: 0.4)"},
                "mix": {"type": "number", "description": "Wet/dry mix (0.0=dry, 1.0=fully wet, default: 0.3)"},
                "output_path": {"type": "string", "description": "Output path (auto-generated if omitted)"},
            },
            "required": ["wav_path"],
        },
    },
    {
        "name": "apply_compression",
        "description": "Apply dynamic range compression to an audio file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Input audio file path"},
                "threshold_db": {"type": "number", "description": "Threshold in dB (-60 to 0, default: -20)"},
                "ratio": {"type": "number", "description": "Compression ratio (1-20, default: 4)"},
                "attack_ms": {"type": "number", "description": "Attack time in ms (0.1-200, default: 10)"},
                "release_ms": {"type": "number", "description": "Release time in ms (10-2000, default: 200)"},
                "output_path": {"type": "string", "description": "Output path (auto-generated if omitted)"},
            },
            "required": ["wav_path"],
        },
    },
    {
        "name": "adjust_volume",
        "description": "Adjust the volume of an audio file by a dB amount.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Input audio file path"},
                "gain_db": {"type": "number", "description": "Volume adjustment in dB (-60 to +24)"},
                "output_path": {"type": "string", "description": "Output path (auto-generated if omitted)"},
            },
            "required": ["wav_path", "gain_db"],
        },
    },
]

BRIDGE_TOOLS = [
    {
        "name": "extract_midi_from_audio",
        "description": (
            "Extract MIDI note data (pitch + rhythm) from an audio file. "
            "Bridges audio generation (ACE-Step) to the notation world (MusicXML). "
            "Enables getting sheet music from AI-generated audio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to input audio file"},
                "output_path": {"type": "string", "description": "Output MIDI path (auto-generated if omitted)"},
                "onset_threshold": {"type": "number", "description": "Onset sensitivity 0-1 (default: 0.5)"},
                "min_frequency_hz": {"type": "number", "description": "Minimum frequency to detect (default: 30)"},
                "max_frequency_hz": {"type": "number", "description": "Maximum frequency to detect (default: 4000)"},
            },
            "required": ["audio_path"],
        },
    },
]

CURATION_TOOLS = [
    {
        "name": "score_audio_quality",
        "description": (
            "Run detailed audio quality analysis with 9 metrics, returning a "
            "composite score (0-1) and letter grade (A-F). Use after generation "
            "to evaluate and compare audio candidates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Path to audio file to analyze"},
                "tags": {"type": "string", "description": "Tags used during generation (for future alignment scoring)"},
                "lyrics": {"type": "string", "description": "Lyrics used during generation (for future alignment scoring)"},
            },
            "required": ["wav_path"],
        },
    },
    {
        "name": "analyze_audio_dimensions",
        "description": (
            "Run the full 12-dimension quality analysis (6 hard gates + 6 soft scores). "
            "More detailed than score_audio_quality — includes silence detection, clipping, "
            "loudness, phase, structure, rhythm, harmony, frequency balance, evolution, and stereo mix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string", "description": "Path to audio file"},
                "genre": {"type": "string", "description": "Genre for weight tuning (default: pop)"},
            },
            "required": ["wav_path"],
        },
    },
]

MIXER_TOOLS = [
    {
        "name": "mix_tracks",
        "description": (
            "Mix multiple audio tracks into a single output file. "
            "Supports per-track volume, stereo panning, and delay. "
            "Use to combine separately generated parts (vocals, instruments, drums)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tracks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Audio file path"},
                            "volume_db": {"type": "number", "description": "Gain in dB (default: 0)"},
                            "pan": {"type": "number", "description": "Stereo pan -1 to 1 (default: 0)"},
                            "delay_ms": {"type": "number", "description": "Delay in ms (default: 0)"},
                        },
                        "required": ["path"],
                    },
                    "description": "List of tracks to mix (minimum 2)",
                },
                "output_path": {"type": "string", "description": "Output file path (auto-generated if omitted)"},
                "normalize": {"type": "boolean", "description": "Apply loudness normalization (default: true)"},
            },
            "required": ["tracks"],
        },
    },
    {
        "name": "check_training_status",
        "description": (
            "Check the status of a voice LoRA training job started with train_voice_lora. "
            "Returns whether it's running, completed, or failed, plus the last lines of the training log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "Process ID of the training job (0 to list all jobs)"},
                "voice_name": {"type": "string", "description": "Filter by voice name"},
            },
            "required": [],
        },
    },
]


def get_all_tools() -> list[dict]:
    """Return all tool definitions in Anthropic format (with input_schema)."""
    return (
        GENERATION_TOOLS
        + V15_TOOLS
        + VOICE_TOOLS
        + VALIDATION_TOOLS
        + RENDERING_TOOLS
        + STATE_TOOLS
        + POSTPRODUCTION_TOOLS
        + PLAYBACK_TOOLS
        + EFFECTS_TOOLS
        + BRIDGE_TOOLS
        + CURATION_TOOLS
        + MIXER_TOOLS
    )


def anthropic_to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI format for LiteLLM/Ollama."""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool.get("input_schema", tool.get("parameters", {})),
            }
        })
    return openai_tools


def get_all_tools_openai() -> list[dict]:
    """Return all tool definitions in OpenAI format (for LiteLLM/Ollama/Groq)."""
    return anthropic_to_openai_tools(get_all_tools())


def get_tool_names() -> list[str]:
    """Return all tool names."""
    return [t["name"] for t in get_all_tools()]
