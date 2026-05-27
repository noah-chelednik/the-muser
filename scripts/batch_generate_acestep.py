#!/usr/bin/env python3
"""Batch audio generation using ACE-Step for The Muser.

Generates audio tracks across multiple genres using a curated prompt
library.  Supports best-of-N selection via audio quality scoring.

Usage::

    python scripts/batch_generate_acestep.py \\
        --device cuda \\
        --num-per-genre 8 \\
        --best-of 3 \\
        --infer-step 60

The prompt library contains 64 prompts across 8 genres, each carefully
crafted with specific tags for ACE-Step's conditioning system.
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator.config import (
    ACESTEP_INFER_STEP,
    ACESTEP_GUIDANCE_SCALE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("muser.batch")


# ---------------------------------------------------------------------------
# Audio quality scoring
# ---------------------------------------------------------------------------


def get_audio_quality_score(wav_path: str) -> float:
    """Score audio quality using expanded metrics from audio_validator.

    Returns a composite score in [0, 1] where higher is better.
    Falls back to simple 3-metric scoring if evaluate_quality is unavailable.
    """
    try:
        from src.audio.audio_validator import evaluate_quality

        report = evaluate_quality(wav_path)
        return report.composite_score

    except Exception:
        # Fallback: simple 3-metric scoring (backwards compatible)
        try:
            import librosa
            import numpy as np

            y, sr = librosa.load(wav_path, sr=None, mono=True)

            if y is None or len(y) == 0:
                return 0.0

            rms = librosa.feature.rms(y=y)[0]
            rms_mean = float(rms.mean())
            if rms_mean < 1e-6:
                return 0.0
            rms_score = min(rms_mean / 0.1, 1.0)

            rms_db = 20 * np.log10(rms + 1e-10)
            dynamic_range = float(rms_db.std())
            dr_score = min(dynamic_range / 15.0, 1.0)

            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            centroid_var = float(centroid.std() / (centroid.mean() + 1e-10))
            sc_score = min(centroid_var / 0.5, 1.0)

            score = 0.4 * rms_score + 0.3 * dr_score + 0.3 * sc_score
            return round(score, 4)

        except Exception as exc:
            logger.warning("Quality scoring failed for %s: %s", wav_path, exc)
            return 0.0


# ---------------------------------------------------------------------------
# Prompt library
# ---------------------------------------------------------------------------


@dataclass
class TrackPrompt:
    """A single generation prompt with metadata."""

    genre: str
    title: str
    tags: str
    lyrics: str = "[instrumental]"
    duration_s: int = 60
    guidance_scale: float = 4.0


PROMPT_LIBRARY: dict[str, list[TrackPrompt]] = {
    "pop": [
        TrackPrompt(
            "pop",
            "Sunrise Boulevard",
            "A bright and upbeat synth pop track with polished radio-ready production. "
            "Female vocals carry a soaring catchy melody over shimmering synthesizer pads, "
            "punchy electronic drums, and a warm sub bass that anchors the dance-pop groove. "
            "The mood is euphoric and sun-drenched, building from a gentle verse into an "
            "anthemic chorus with layered vocal harmonies. Crisp hi-hats and sidechain "
            "compression give it a modern radio pop feel with commercial appeal.",
        ),
        TrackPrompt(
            "pop",
            "Midnight Glow",
            "A mid-tempo emotional pop ballad driven by expressive male vocals and a "
            "grand piano melody. Lush orchestral strings swell beneath the chorus while "
            "soft programmed drums maintain a gentle heartbeat pulse. The atmosphere is "
            "warm yet melancholic, like city lights reflected in rain. Reverb-drenched "
            "vocal layers create an intimate, confessional quality. The production is "
            "polished but restrained, letting the vocal performance breathe.",
        ),
        TrackPrompt(
            "pop",
            "Electric Hearts",
            "An energetic electronic pop anthem with driving female vocals and a pulsing "
            "synth bass foundation. Aggressive drum machines punch through layers of "
            "arpeggiated synthesizers and filtered pad textures. The track builds relentlessly "
            "toward an explosive drop-style chorus with soaring vocal ad-libs. Club-ready "
            "production with sidechain pumping, crisp snares, and a euphoric major-key "
            "progression that demands movement.",
        ),
        TrackPrompt(
            "pop",
            "Paper Planes",
            "A breezy indie pop track with male vocals floating over fingerpicked acoustic "
            "guitar and light brushed drums. The carefree summer atmosphere is enhanced by "
            "subtle glockenspiel accents and warm bass guitar lines. A whistled melodic hook "
            "appears between verses, giving it an easygoing, walking-in-the-park quality. "
            "The production is intentionally lo-fi and organic, with room ambience and "
            "minimal processing on the vocals for an intimate coffeehouse feel.",
        ),
        TrackPrompt(
            "pop",
            "Velvet Sky",
            "A dreamy ethereal pop track with female vocals drenched in shimmering reverb "
            "and cascading delay effects. Lush pad synthesizers create a vast atmospheric "
            "soundscape while a gentle pulse of electronic percussion provides subtle forward "
            "motion. The melody is hypnotic and circular, drawing the listener into a "
            "trance-like state. Dream pop production with shoegaze-influenced guitar textures, "
            "ambient washes, and a luminous quality that feels weightless and celestial.",
        ),
        TrackPrompt(
            "pop",
            "City Lights Instrumental",
            "An instrumental synth pop piece with a bright grand piano lead melody over "
            "polished electronic production. Upbeat electronic drums with crisp rimshots "
            "and programmed hi-hat patterns drive the groove forward. Layered synthesizer "
            "textures shift between warm analog pads and sparkling digital arpeggios. "
            "Commercial and accessible, with a memorable melodic hook suitable for media "
            "placement. Clean and modern mixing with spatial stereo effects.",
        ),
        TrackPrompt(
            "pop",
            "Golden Hour",
            "A warm nostalgic indie pop track with intimate female vocals and golden-toned "
            "acoustic guitar as the harmonic foundation. Soft brushed drums and a mellow "
            "bass guitar provide a gentle rhythmic bed. The production captures the magic "
            "of fading afternoon light with tape-saturated warmth and subtle analog "
            "compression. Vocal harmonies bloom in the chorus, creating a lush but "
            "understated emotional peak. Intimate and personal in character.",
        ),
        TrackPrompt(
            "pop",
            "Neon Nights",
            "A moody dark pop track with male vocals processed through subtle pitch "
            "correction over deep synth bass and trap-influenced drum patterns. The "
            "atmosphere is sleek and urban, with minor-key chord progressions creating "
            "tension beneath a seductive vocal delivery. Sparse production leaves space "
            "for dramatic effect, with occasional stuttered vocal chops and filtered "
            "risers building suspense. Modern, nocturnal, and coolly detached in tone.",
        ),
    ],
    "rock": [
        TrackPrompt(
            "rock",
            "Thunder Road",
            "A powerful arena rock anthem with soaring male vocals and crunching electric "
            "guitars playing aggressive power chord progressions. Driving drums with a "
            "relentless four-on-the-floor kick pattern propel the track forward at high "
            "energy. The bass guitar locks tightly with the kick drum for a massive low-end "
            "foundation. Multiple guitar layers create a wall of distortion that opens up "
            "in the verse and crashes back for the anthemic sing-along chorus. Stadium-sized "
            "reverb on the vocals and gang vocal shouts in the hook.",
        ),
        TrackPrompt(
            "rock",
            "Broken Glass",
            "A raw and emotionally intense alternative rock track with female vocals that "
            "shift between vulnerable verses and explosive, screamed choruses. Heavy bass "
            "guitar with overdrive cuts through aggressive drum patterns with tom-heavy "
            "fills. The grunge-influenced production is deliberately rough-edged, with "
            "analog distortion on nearly every element. Dynamic contrast between quiet "
            "introspective passages and full-band fury captures the emotional turbulence "
            "of the performance.",
        ),
        TrackPrompt(
            "rock",
            "Desert Highway",
            "An instrumental blues rock piece with warm slide guitar melodies weaving over "
            "a Hammond organ's sustained chords and a steady hypnotic groove. The rhythm "
            "section locks into a deep pocket with a swinging feel, evoking long drives "
            "through arid landscapes. Southern rock warmth infuses every element, from the "
            "overdriven guitar tone to the slightly behind-the-beat drum feel. Subtle "
            "wah-wah pedal effects and natural tube amplifier saturation give the guitars "
            "an organic, lived-in character.",
        ),
        TrackPrompt(
            "rock",
            "Rebel Heart",
            "A fast and aggressive punk rock track with shouted male vocals delivering "
            "rapid-fire lyrics over thrashing power chords and pummeling drums. The bass "
            "guitar drives a relentless eighth-note pulse that never lets up. Minimal "
            "production keeps the sound raw and garage-like, with bleed between instruments "
            "adding to the chaotic energy. Short and explosive, the track wastes no time "
            "on intros or outros, launching immediately into the assault and ending abruptly "
            "after a final feedback squeal.",
        ),
        TrackPrompt(
            "rock",
            "Midnight Drive",
            "An atmospheric instrumental post-rock piece that builds from whispered guitar "
            "harmonics and ambient delay textures into a massive wall of sound. Layers of "
            "tremolo-picked electric guitar accumulate gradually over patient, minimal "
            "drumming. The crescendo is slow and inevitable, with each new guitar layer "
            "adding harmonic richness until the climax washes over the listener in a wave "
            "of shimmering distortion. Cinematic and deeply emotional, with a sense of "
            "vast open spaces and quiet determination.",
        ),
        TrackPrompt(
            "rock",
            "Iron Will",
            "A hard rock track with powerful male vocals and heavy guitar riffs built on "
            "palm-muted chugging patterns and aggressive double kick drum passages. The "
            "bass guitar adds metallic growl with a distorted tone that rumbles beneath "
            "the guitar wall. Production is tight and modern, with precise drum editing "
            "and layered guitar tracking for maximum heaviness. The chorus opens up with "
            "a half-time feel and melodic vocal hook before crashing back into the "
            "relentless verse riff.",
        ),
        TrackPrompt(
            "rock",
            "Autumn Leaves Fall",
            "A wistful indie rock track with female vocals and jangly clean-tone electric "
            "guitars playing arpeggiated chord patterns reminiscent of late-80s college "
            "rock. Light distortion on the chorus guitars adds warmth without aggression. "
            "The drumming is tasteful with jazzy ghost notes on the snare and a brushed "
            "hi-hat keeping time. Bass guitar provides melodic counterpoint to the vocals. "
            "The overall mood is breezy and nostalgic, like looking through old photographs "
            "on a cool autumn afternoon.",
        ),
        TrackPrompt(
            "rock",
            "Volcano",
            "An instrumental progressive rock piece with complex guitar work alternating "
            "between odd meter passages and soaring melodic themes. Technical drumming "
            "navigates shifting time signatures with precision while the bass guitar "
            "provides both rhythmic anchor and melodic countermelody. The arrangement is "
            "dynamic and evolving, moving through multiple distinct sections that contrast "
            "heavy distorted riffing with clean atmospheric interludes. Epic in scope "
            "and ambitious in its harmonic and rhythmic complexity.",
        ),
    ],
    "jazz": [
        TrackPrompt(
            "jazz",
            "Blue Moon Café",
            "A lively bebop piano trio performance with a grand piano playing fleet "
            "improvised lines over sophisticated chord changes. Walking upright bass "
            "provides harmonic foundation and rhythmic propulsion while brush drums "
            "create an intricate swing texture on the ride cymbal. The piano comping "
            "between solo choruses is angular and harmonically adventurous. The recording "
            "has an intimate live-in-the-club quality with room ambience and natural "
            "dynamic variation, capturing the spontaneous interplay of master musicians.",
        ),
        TrackPrompt(
            "jazz",
            "Smoky Lounge",
            "A cool jazz track centered on a breathy tenor saxophone playing languid "
            "melodic lines over a walking bass and gentle ride cymbal. The mood is late-night "
            "and intimate, with the saxophone tone warm and slightly husky. Piano comping "
            "is sparse and tasteful, offering subtle harmonic colors beneath the horn. "
            "The tempo is relaxed and unhurried, with the rhythm section laying back "
            "behind the beat. Recorded with vintage warmth and minimal reverb for a "
            "close, personal listening experience.",
        ),
        TrackPrompt(
            "jazz",
            "Sunday Morning",
            "A bossa nova jazz piece with warm female vocals singing a lilting melody "
            "over nylon-string guitar playing classic Brazilian rhythmic patterns. Soft "
            "brushed drums and a gentle bass provide rhythmic support without overwhelming "
            "the delicate vocal performance. The harmony is rich with extended chord voicings "
            "and chromatic passing tones. The atmosphere is warm and relaxed, like "
            "sunlight streaming through café windows on a lazy weekend morning. Elegant "
            "and effortlessly sophisticated.",
        ),
        TrackPrompt(
            "jazz",
            "Harlem Nights",
            "An energetic big band swing piece with a muted trumpet taking the lead over "
            "a full brass section arranged in tight block harmonies. The rhythm section "
            "drives a propulsive swing feel with the drummer working the hi-hat and ride "
            "cymbal while the bassist walks confidently through the changes. Brass shouts "
            "punctuate the arrangement between solo passages. The energy is festive and "
            "celebratory, evoking the golden age of swing clubs and dance halls.",
        ),
        TrackPrompt(
            "jazz",
            "Rainy Day Blues",
            "A solo piano jazz ballad of exquisite melancholy and emotional depth. The "
            "pianist plays with rubato freedom, stretching and compressing time to serve "
            "the emotional narrative. Sparse left-hand voicings support a right-hand melody "
            "that sings with vocal-like phrasing. Dynamic control ranges from barely audible "
            "whispers to passionate forte outbursts. The mood is deeply introspective and "
            "contemplative, with minor-key harmonies that resolve in unexpected directions. "
            "Delicate and profoundly moving.",
        ),
        TrackPrompt(
            "jazz",
            "Fusion Drive",
            "A jazz fusion track with a Fender Rhodes electric piano playing funky "
            "comping patterns over a slapped bass guitar groove and complex polyrhythmic "
            "drumming. The energy is high and technically demanding, with rapid-fire "
            "unison lines between keyboard and bass. Guitar adds wah-wah inflected "
            "fills and rhythmic scratching. The harmonic language blends jazz sophistication "
            "with funk grit, creating an irresistible head-nodding groove punctuated by "
            "virtuosic improvisational passages.",
        ),
        TrackPrompt(
            "jazz",
            "Autumn in Paris",
            "A gypsy jazz piece with acoustic guitar playing rapid arpeggiated runs in "
            "the style of Django Reinhardt alongside a singing accordion melody. A violin "
            "adds soaring countermelody lines while the rhythm guitar provides the "
            "characteristic pompe rhythm. The swing feel is lighter and faster than "
            "American jazz, with a distinctly European romantic character. The atmosphere "
            "is playful and nostalgic, evoking Parisian café culture and the manouche "
            "tradition of virtuosic string improvisation.",
        ),
        TrackPrompt(
            "jazz",
            "Modal Exploration",
            "A meditative modal jazz piece with soprano saxophone playing long sustained "
            "tones and searching melodic fragments over a piano providing shimmering "
            "quartal voicings. The bass moves in slow pedal tones while the drums create "
            "atmospheric textures with mallets on cymbals and sparse bass drum accents. "
            "The harmonic language is deliberately static, exploring the colors within "
            "a single mode rather than progressing through changes. Spiritual and "
            "contemplative in the tradition of late Coltrane explorations.",
        ),
    ],
    "electronic": [
        TrackPrompt(
            "electronic",
            "Neon Pulse",
            "A driving synthwave track built on lush analog-style synthesizer pads and "
            "a pulsing arpeggiated bass sequence that evokes 1980s sci-fi soundtracks. "
            "Punchy drum machine patterns with gated reverb on the snare and tight "
            "electronic kick drums provide propulsive rhythmic energy. Layered "
            "synthesizer leads soar over the arrangement with nostalgic warmth. The "
            "production captures vintage analog character with modern clarity, creating "
            "a retro-futuristic atmosphere of neon-lit highways and chrome reflections.",
        ),
        TrackPrompt(
            "electronic",
            "Deep Dive",
            "A deep house track with a four-on-the-floor kick drum pattern driving a "
            "hypnotic groove built on filtered pad chords and a warm sub bass that "
            "pulses with sidechain compression. Subtle hi-hat patterns evolve gradually "
            "while filtered vocal samples drift through the stereo field. The arrangement "
            "develops slowly through careful addition and subtraction of elements, "
            "creating a mesmerizing late-night dance floor experience. Warm analog "
            "character with deep low-end presence and spacious mixing.",
        ),
        TrackPrompt(
            "electronic",
            "Binary Stars",
            "An ambient electronic piece constructed from ethereal atmospheric pads, "
            "granular synthesis textures, and vast reverberant spaces that suggest "
            "infinite cosmic distances. Gentle melodic fragments emerge and dissolve "
            "within the texture like distant stars appearing through clouds. The tempo "
            "is slow and breathing, with barely perceptible rhythmic pulses providing "
            "subtle forward motion. Contemplative and expansive, the soundscape invites "
            "deep listening and meditation on vastness and solitude.",
        ),
        TrackPrompt(
            "electronic",
            "Circuit Break",
            "An intense drum and bass track with chopped breakbeat patterns rolling at "
            "high speed over a massive rolling bassline that shifts between sub-frequency "
            "rumbles and mid-range growls. Sharp synth stabs cut through the mix like "
            "laser fire while filtered pad risers build tension before each drop. The "
            "production is futuristic and aggressive, with precise surgical editing on "
            "the drum breaks and heavy compression creating a wall-of-sound intensity "
            "designed for high-energy dance floors.",
        ),
        TrackPrompt(
            "electronic",
            "Crystal Caves",
            "A downtempo trip hop track with mellow beat programming, vinyl crackle "
            "warmth, and mysterious atmospheric textures suggesting underground spaces "
            "and hidden depths. A slow hip-hop-influenced drum pattern with heavy swing "
            "provides the rhythmic foundation while processed piano samples and ethereal "
            "vocal fragments drift through layers of reverb and delay. The mood is "
            "nocturnal and contemplative, with a slightly psychedelic quality to the "
            "swirling effects and spatial processing.",
        ),
        TrackPrompt(
            "electronic",
            "Quantum Leap",
            "A dark minimal techno track with a relentless driving kick drum and "
            "industrial-tinged acid synthesizer lines that squelch and morph through "
            "filter sweeps. The arrangement is stripped to essential elements: kick, "
            "hi-hat, acid bass, and sparse percussive accents. Tension builds through "
            "subtle parameter automation and gradual textural layering rather than "
            "structural changes. Mechanical and hypnotic, designed for extended DJ sets "
            "in dark warehouse spaces with powerful sound systems.",
        ),
        TrackPrompt(
            "electronic",
            "Aurora Waves",
            "A hazy chillwave track with lo-fi synthesizer melodies processed through "
            "tape saturation and gentle chorus effects. Dreamy processed vocals are "
            "buried in the mix like a half-remembered memory. Soft drum machine patterns "
            "with heavy reverb and a warm bass synth create a pillowy rhythmic bed. "
            "The production deliberately embraces lo-fi aesthetics with degraded samples, "
            "pitch wobble, and washed-out frequency response. Nostalgic and sun-bleached, "
            "evoking endless summer afternoons.",
        ),
        TrackPrompt(
            "electronic",
            "Data Stream",
            "An experimental IDM track with glitchy granular percussion patterns, "
            "micro-edited drum hits, and complex polyrhythmic structures that shift "
            "unpredictably. Digital synthesis textures range from crystalline bell tones "
            "to harsh noise bursts, all precisely arranged in intricate counterpoint. "
            "The harmonic content is atonal but carefully controlled, with moments of "
            "unexpected beauty emerging from the complexity. Cerebral and challenging, "
            "rewarding close attention with layers of hidden detail and structural logic.",
        ),
    ],
    "classical": [
        TrackPrompt(
            "classical",
            "Morning Prelude",
            "A romantic-period piano solo with expressive rubato phrasing and singing "
            "melodic lines that evoke the lyrical style of Chopin's character pieces. "
            "The right hand spins long cantabile melodies over the left hand's arpeggiated "
            "accompaniment patterns. Dynamic shaping ranges from tender pianissimo "
            "passages to passionate climactic moments. The harmonic language is richly "
            "chromatic with unexpected modulations that heighten emotional expression. "
            "Elegant and deeply personal, performed with the freedom and spontaneity "
            "of true romantic pianism.",
        ),
        TrackPrompt(
            "classical",
            "String Serenade",
            "A baroque-inspired string quartet with intricate contrapuntal writing where "
            "four independent voices weave together in elaborate polyphonic textures. "
            "First violin and cello engage in imitative dialogue while viola and second "
            "violin provide harmonic and rhythmic support. The writing references Bach's "
            "fugal techniques with subject entries, episodes, and stretto passages. "
            "Performed in a crisp, articulate style with minimal vibrato and precise "
            "intonation. Intellectually satisfying and architecturally refined.",
        ),
        TrackPrompt(
            "classical",
            "Nocturne in Blue",
            "A contemplative piano nocturne with a hauntingly beautiful melody played "
            "with delicate touch and intimate dynamic control. The left hand provides "
            "a gently rocking accompaniment figure while the right hand sings a long-breathed "
            "melody that rises and falls like quiet breathing. Soft pedaling creates a "
            "veiled, mysterious quality. The harmonic palette favors rich minor-key "
            "sonorities with chromatic voice leading that creates an atmosphere of "
            "bittersweet beauty and quiet nighttime contemplation.",
        ),
        TrackPrompt(
            "classical",
            "Symphony Fragment",
            "A dramatic orchestral passage for full symphony orchestra with sweeping string "
            "lines, powerful brass fanfares, colorful woodwind countermelodies, and thundering "
            "timpani rolls. The writing channels the heroic intensity of Beethoven's middle "
            "period with bold dynamic contrasts and driving rhythmic energy. The orchestration "
            "is rich and full, exploiting the timbral palette of each section. Tension builds "
            "through developing variation and sequential harmonic motion toward a triumphant "
            "climactic statement of the main theme.",
        ),
        TrackPrompt(
            "classical",
            "Minuet in G",
            "An elegant classical-period minuet for harpsichord with ornamental grace notes, "
            "trills, and mordents decorating a graceful dance melody. The form follows the "
            "traditional binary structure with clear phrase symmetry and elegant cadential "
            "gestures. The style references Mozart's galant aesthetic with its emphasis "
            "on balanced proportions, light textures, and conversational melodic exchanges "
            "between treble and bass registers. Courtly and refined, with the sparkle "
            "of harpsichord registration adding period-appropriate brightness.",
        ),
        TrackPrompt(
            "classical",
            "Elegy for Strings",
            "A profoundly sorrowful adagio for string orchestra with rich sustained "
            "harmonies and achingly beautiful melodic lines that seem to weep. The writing "
            "recalls Samuel Barber's emotional directness with its long vocal-like phrases "
            "and expressive chromaticism. The dynamic range extends from hushed, barely "
            "audible passages where individual voices emerge from the texture to "
            "overwhelming fortissimo climaxes of collective grief. Deeply emotional "
            "and cathartic, with a sense of profound loss gradually transforming "
            "into acceptance.",
        ),
        TrackPrompt(
            "classical",
            "Scherzo Brillante",
            "A virtuosic piano scherzo sparkling with rapid passagework, playful "
            "staccato articulations, and mercurial shifts between humor and intensity. "
            "The writing references Mendelssohn's fairy-like lightness with its fleet "
            "finger patterns and transparent textures. Quick dynamic contrasts create "
            "a sense of mischievous energy and whimsical surprise. The technical demands "
            "include rapid scale passages, wide leaps, and delicate pianissimo filigree "
            "that shimmers like sunlight on water.",
        ),
        TrackPrompt(
            "classical",
            "Pastoral Scene",
            "An impressionistic orchestral miniature for flute, oboe, and strings "
            "evoking gentle nature scenes with flowing melodic lines and luminous "
            "harmonic colors. The flute plays a singing pastoral theme while the oboe "
            "offers a lyrical countermelody. Strings provide shimmering harmonic support "
            "with tremolo and sul ponticello effects suggesting dappled sunlight and "
            "gentle breezes. The influence of Debussy is felt in the use of whole-tone "
            "scales, parallel chord motion, and a preference for color over functional "
            "harmonic progression.",
        ),
    ],
    "r&b": [
        TrackPrompt(
            "r&b",
            "Silk Sheets",
            "A smooth neo-soul track with sultry female vocals gliding over warm Rhodes "
            "electric piano chords and a deep, round bass guitar groove. The drums are "
            "programmed with organic feel, featuring soft kick patterns and crisp snare "
            "ghost notes with a brushed hi-hat. Subtle string pad layers add warmth "
            "beneath the intimate vocal performance. The production is lush but "
            "restrained, with analog warmth from tape saturation and gentle compression. "
            "The mood is sensual and late-night, perfect for quiet moments.",
        ),
        TrackPrompt(
            "r&b",
            "Midnight Confession",
            "A modern R&B slow jam with vulnerable male vocals floating over atmospheric "
            "pad synthesizers and a deep 808 sub bass that vibrates with subsonic weight. "
            "Sparse programmed drums with trap-influenced hi-hat patterns create space "
            "for the vocal performance to breathe. The production is cavernous and dark, "
            "with heavy reverb and delay creating a sense of isolation and emotional "
            "exposure. The harmonic palette favors suspended and diminished sonorities "
            "that never fully resolve, maintaining tension throughout.",
        ),
        TrackPrompt(
            "r&b",
            "Golden Touch",
            "An upbeat retro-soul track with joyful female vocals over a funky slap bass "
            "line, clavinet riffs, and punchy brass hits that recall the Motown era. "
            "Live-feeling drums with a tight pocket groove and syncopated hi-hat patterns "
            "drive the danceable rhythm. Backing vocal harmonies stack in thick gospel-inspired "
            "arrangements during the chorus. The production balances vintage warmth with "
            "modern clarity, capturing the effervescent energy of classic soul music "
            "while sounding contemporary and fresh.",
        ),
        TrackPrompt(
            "r&b",
            "Velvet Rain",
            "An emotionally exposed R&B ballad with male vocals reaching into a tender "
            "falsetto register over minimal drum programming and lush orchestral strings. "
            "The sparse arrangement leaves the voice vulnerable and center-stage, with "
            "each vocal inflection carrying dramatic weight. Cinematic string swells "
            "underscore the most emotional moments while the rhythm barely whispers "
            "beneath. The mood is haunting and vulnerable, like a confession whispered "
            "in the dark. Restrained production serves the raw emotional performance.",
        ),
        TrackPrompt(
            "r&b",
            "After Hours",
            "An instrumental lo-fi R&B track with warm Rhodes piano melodies floating "
            "over soft vinyl-crackle-infused drum patterns and a mellow bass line. The "
            "late-night atmosphere is enhanced by gentle tape saturation, subtle wow and "
            "flutter effects, and spacious reverb that creates a sense of solitary "
            "contemplation. Occasional guitar arpeggios add color between piano phrases. "
            "The mood is chill and meditative, perfect for late-night listening with "
            "its warm analog character and unhurried groove.",
        ),
        TrackPrompt(
            "r&b",
            "Crown Royal",
            "A dark contemporary trap-soul track with moody male vocals processed "
            "through tasteful auto-tune over deep 808 sub bass and intricate hi-hat "
            "programming with rapid rolls and syncopated patterns. Dark pad synthesizers "
            "create a brooding atmospheric backdrop while sparse piano chords add "
            "melancholic color. The vocal performance shifts between melodic singing "
            "and rhythmic half-rapped passages. Production is modern and minimalist, "
            "with heavy low-end presence and spacious, dark-toned mixing.",
        ),
        TrackPrompt(
            "r&b",
            "Summer Wine",
            "A breezy organic R&B track with warm female vocals harmonizing over "
            "fingerpicked acoustic guitar and gentle hand percussion including shaker "
            "and tambourine. The bass guitar plays a melodic supportive line that "
            "weaves around the vocal melody. Backing harmonies are rich and closely "
            "voiced, creating a warm choir-like effect. The mood is romantic and "
            "sun-kissed, with a natural, unprocessed quality to the recording that "
            "emphasizes the beauty of the acoustic instruments and vocal blend.",
        ),
        TrackPrompt(
            "r&b",
            "Neon Soul",
            "A futuristic instrumental electronic soul track blending organic warmth "
            "with digital experimentation. Synth bass provides a deep groove foundation "
            "while glitchy beat programming incorporates stuttered samples, bit-crushed "
            "textures, and spacious gaps that create rhythmic surprise. Atmospheric "
            "synthesizer pads shift through unexpected harmonic territories while "
            "processed vocal samples appear and vanish like digital ghosts. The "
            "production is adventurous and boundary-pushing, finding soulfulness "
            "within electronic abstraction.",
        ),
    ],
    "hiphop": [
        TrackPrompt(
            "hiphop",
            "Block Party",
            "A classic boom bap hip hop beat with dusty sampled drums chopped from vinyl "
            "records, authentic DJ scratch turntablism, and a warm upright bass providing "
            "the melodic bass line. The drum pattern swings with a golden-era hip hop feel, "
            "featuring a punchy kick with analog warmth and a snappy snare with vinyl "
            "texture. Subtle filtered soul samples add nostalgic color. The groove is "
            "head-nodding and street-level authentic, capturing the spirit of outdoor "
            "block parties and b-boy cyphers.",
        ),
        TrackPrompt(
            "hiphop",
            "Concrete Jungle",
            "An aggressive trap beat with a massive 808 bass that distorts and rumbles "
            "beneath rapid hi-hat rolls and hard-hitting snare patterns. Dark atmospheric "
            "pad synthesizers create a menacing, urban soundscape. The production is "
            "maximalist and intense, with layered percussion creating a dense rhythmic "
            "texture. Reversed cymbal crashes and riser effects build tension between "
            "sections. The overall mood is dark, confrontational, and street-hardened, "
            "with the 808 sub bass designed to overwhelm car sound systems.",
        ),
        TrackPrompt(
            "hiphop",
            "Cloud Nine",
            "A mellow lo-fi hip hop beat with jazzy sampled chords, dusty vintage drum "
            "machine patterns, and a warm detuned bass synth. The groove is relaxed and "
            "unhurried with gentle swing feel. Vinyl crackle and tape hiss add nostalgic "
            "analog warmth while a filtered jazz piano sample loops hypnotically. "
            "Occasional field recordings of rain or ambient sounds enhance the cozy "
            "atmosphere. Perfect for studying or relaxed listening, with a dreamy "
            "quality that softens all edges.",
        ),
        TrackPrompt(
            "hiphop",
            "Empire State",
            "A cinematic orchestral hip hop beat with dramatic string arrangements, "
            "grand piano chords, and epic orchestral drum patterns layered with "
            "programmed hip hop drums. The orchestration sweeps through dynamic "
            "crescendos and dramatic pauses that create space for storytelling. "
            "French horn and cello provide majestic low-end warmth while high strings "
            "add tension and urgency. The production bridges symphonic grandeur "
            "with street-level hip hop grit, creating a soundtrack for urban epics.",
        ),
        TrackPrompt(
            "hiphop",
            "Southside Groove",
            "A bouncy southern trap beat with sliding 808 bass lines that pitch between "
            "notes, rapid snare rolls, and an energetic club-ready groove. The hi-hat "
            "programming is intricate with triplet patterns and dynamic accents. "
            "Bright synthesizer stabs and vocal chant samples add party energy. The "
            "mix is bass-heavy with the 808 occupying massive low-frequency space "
            "while crisp percussion cuts through the top end. Designed for maximum "
            "physical impact on dance floors and car audio systems.",
        ),
        TrackPrompt(
            "hiphop",
            "Zen Garden",
            "An atmospheric instrumental hip hop beat blending East Asian musical "
            "elements with meditative production. A bamboo flute plays a pentatonic "
            "melody over soft programmed drums with gentle swing and spacious reverb. "
            "Filtered koto and guzheng samples add crystalline textural detail while "
            "a warm sub bass provides grounding low-end presence. The mood is peaceful "
            "and contemplative, creating a tranquil sonic landscape that bridges "
            "traditional Asian aesthetics with contemporary beat production.",
        ),
        TrackPrompt(
            "hiphop",
            "Midnight Cypher",
            "A gritty underground hip hop beat with raw, unquantized drum patterns "
            "featuring distorted kicks and aggressive snare hits. The bass is overdriven "
            "and menacing, sitting heavy in the mix with analog saturation. Dark "
            "atmospheric samples and industrial noise textures create an oppressive, "
            "claustrophobic atmosphere. The production rejects polish in favor of "
            "authentic rawness and street credibility. Hardcore and uncompromising, "
            "with a lo-fi aesthetic that emphasizes attitude over technical perfection.",
        ),
        TrackPrompt(
            "hiphop",
            "Golden Era",
            "A smooth jazzy hip hop beat with a warm saxophone sample looping over "
            "classic boom bap drum patterns and a round, melodic bass line. The groove "
            "is soulful and nostalgic, evoking the mid-90s golden age of hip hop "
            "production. Warm Rhodes piano chords add harmonic sophistication while "
            "subtle vinyl noise and tape warmth enhance the vintage character. The "
            "overall mood is smooth and sophisticated, bridging jazz artistry with "
            "hip hop rhythm for a timeless, head-nodding listening experience.",
        ),
    ],
    "country": [
        TrackPrompt(
            "country",
            "Dusty Trail",
            "A traditional country song with heartfelt male vocals telling a story over "
            "fingerpicked acoustic guitar, weeping pedal steel guitar, and a fiddle "
            "providing melodic fills between vocal phrases. The rhythm section is "
            "understated with a gentle two-step groove from brushed drums and an "
            "acoustic bass guitar. The production is warm and organic, capturing "
            "the sound of a small Nashville studio with natural room ambience. "
            "The mood is sincere and storytelling, in the tradition of classic "
            "country balladeers.",
        ),
        TrackPrompt(
            "country",
            "Honky Tonk Saturday",
            "An upbeat honky tonk country track with energetic female vocals over "
            "driving banjo rolls, sawing fiddle, and a barrelhouse piano providing "
            "percussive chord accompaniment. The drums play a driving shuffle pattern "
            "while the bass guitar walks through the chord changes with country swagger. "
            "The energy is danceable and fun, evoking Saturday night celebrations in "
            "roadside dance halls. The production is bright and lively with the "
            "instruments panned for a wide, immersive stage sound.",
        ),
        TrackPrompt(
            "country",
            "River Bend",
            "A peaceful instrumental folk country piece with an intricate fingerpicking "
            "guitar pattern as the primary melodic voice, accompanied by a plaintive "
            "harmonica playing sustained melodic phrases. The arrangement is minimal "
            "and spacious, letting the natural resonance of the acoustic guitar fill "
            "the sonic space. Gentle outdoor ambience suggests creek-side tranquility. "
            "The mood is pastoral and meditative, evoking quiet mornings by flowing "
            "water in the rural countryside. Clean, natural acoustic recording.",
        ),
        TrackPrompt(
            "country",
            "Broken Boots",
            "A country rock track with rugged male vocals over electric guitar riffs "
            "that blend Nashville twang with rock and roll attitude. Driving drums with "
            "a heavy kick pattern and energetic fills propel the outlaw country groove. "
            "Pedal steel guitar adds country authenticity while the distorted electric "
            "guitar brings rebellious edge. The bass guitar plays aggressive root-fifth "
            "patterns that lock with the kick drum. The attitude is defiant and rugged, "
            "channeling the spirit of outlaw country legends.",
        ),
        TrackPrompt(
            "country",
            "Wildflower",
            "A bright modern country pop track with polished female vocals and a blend "
            "of acoustic guitar strumming, subtle electric guitar fills, and pop-influenced "
            "programmed drums. The production bridges Nashville tradition with contemporary "
            "pop accessibility, featuring layered vocal harmonies and a radio-friendly hook. "
            "The mood is optimistic and romantic, with a major-key progression that lifts "
            "through the chorus. Clean, commercially polished production with modern "
            "compression and bright EQ character.",
        ),
        TrackPrompt(
            "country",
            "Porch Swing Blues",
            "A country blues track with weathered male vocals singing over slide guitar "
            "and a resonator dobro providing gritty metallic tones. The rhythm is loose "
            "and behind-the-beat, with minimal drums allowing the guitar interplay to "
            "take center stage. The mood is melancholic and authentic, telling stories "
            "of hard times with quiet dignity. The production is deliberately raw and "
            "unpolished, capturing the sound of a front porch performance recorded "
            "with a single microphone on a warm evening.",
        ),
        TrackPrompt(
            "country",
            "Harvest Moon Dance",
            "A fast instrumental bluegrass piece featuring virtuosic mandolin picking, "
            "rapid banjo rolls, and a driving upright bass providing the rhythmic "
            "foundation. The instruments trade melodic breaks with increasing speed and "
            "complexity, showcasing technical mastery and joyful musical conversation. "
            "The energy is exhilarating and celebratory, evoking barn dances and "
            "harvest festivals. The acoustic recording captures the natural brilliance "
            "and attack of each stringed instrument with clarity and presence.",
        ),
        TrackPrompt(
            "country",
            "Tennessee Waltz",
            "A gentle country waltz with tender female vocals over flowing acoustic "
            "guitar arpeggios and sustained string accompaniment. The waltz rhythm "
            "creates an elegant, swaying quality with the bass guitar emphasizing the "
            "downbeat of each measure. The mood is bittersweet and timeless, with "
            "a melody that lingers in memory like a half-forgotten dance. The production "
            "is warm and intimate, with subtle reverb adding a sense of nostalgic "
            "distance to the vocal performance.",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def generate_batch(
    genres: list[str] | None,
    num_per_genre: int,
    best_of: int,
    infer_step: int,
    guidance_scale: float,
    output_dir: Path,
    base_seed: int,
    batch_size: int = 1,
    bpm: int | None = None,
    key_scale: str = "",
) -> list[dict]:
    """Generate a batch of audio tracks across genres.

    When batch_size > 1, generates multiple candidates in one call
    (v1.5 native batching) instead of sequential calls.

    Returns a list of manifest entry dicts.
    """
    from src.generation.acestep_wrapper import generate_audio

    if genres is None:
        genres = list(PROMPT_LIBRARY.keys())

    manifest_entries: list[dict] = []
    total_prompts = sum(min(num_per_genre, len(PROMPT_LIBRARY.get(g, []))) for g in genres)
    completed = 0
    start_time = time.time()

    for genre in genres:
        prompts = PROMPT_LIBRARY.get(genre, [])
        if not prompts:
            logger.warning("No prompts for genre '%s', skipping.", genre)
            continue

        genre_dir = output_dir / genre
        genre_dir.mkdir(parents=True, exist_ok=True)

        for i, prompt in enumerate(prompts[:num_per_genre]):
            completed += 1
            elapsed = time.time() - start_time
            eta = (elapsed / completed) * (total_prompts - completed) if completed > 0 else 0

            logger.info(
                "[%d/%d] Generating: %s / %s (ETA: %.0fs)",
                completed,
                total_prompts,
                genre,
                prompt.title,
                eta,
            )

            best_path = None
            best_score = -1.0
            candidate_scores: list[dict] = []

            # v1.5 native batch: generate all candidates in one call
            effective_best_of = best_of
            effective_batch = min(batch_size, best_of) if batch_size > 1 else 1

            num_rounds = (effective_best_of + effective_batch - 1) // effective_batch

            for round_idx in range(num_rounds):
                candidates_this_round = min(
                    effective_batch,
                    effective_best_of - len(candidate_scores),
                )
                seed = base_seed + (i * best_of) + (round_idx * effective_batch)
                gen_start = time.time()

                try:
                    paths = generate_audio(
                        tags=prompt.tags,
                        lyrics=prompt.lyrics,
                        duration_s=prompt.duration_s,
                        num_candidates=candidates_this_round,
                        seed=seed,
                        infer_step=infer_step,
                        guidance_scale=prompt.guidance_scale,
                        bpm=bpm,
                        key_scale=key_scale,
                    )
                except Exception as exc:
                    logger.error(
                        "Generation failed for %s/%s (seed=%d): %s",
                        genre,
                        prompt.title,
                        seed,
                        exc,
                    )
                    continue

                gen_time = time.time() - gen_start

                if not paths:
                    logger.warning(
                        "No output for %s/%s (seed=%d)",
                        genre,
                        prompt.title,
                        seed,
                    )
                    continue

                for j, wav_path in enumerate(paths):
                    score = get_audio_quality_score(wav_path)
                    candidate_scores.append(
                        {
                            "seed": seed + j,
                            "path": wav_path,
                            "audio_quality_score": score,
                            "generation_time_s": round(gen_time / len(paths), 2),
                        }
                    )

                    logger.info(
                        "  Candidate %d/%d: score=%.4f, seed=%d, time=%.1fs",
                        len(candidate_scores),
                        effective_best_of,
                        score,
                        seed + j,
                        gen_time / len(paths),
                    )

                    if score > best_score:
                        best_score = score
                        best_path = wav_path

            if best_path is None:
                logger.error("All candidates failed for %s / %s", genre, prompt.title)
                manifest_entries.append(
                    {
                        "genre": genre,
                        "title": prompt.title,
                        "tags": prompt.tags[:100],
                        "status": "failed",
                    }
                )
                continue

            # Copy best candidate to genre output dir
            import shutil

            safe_title = prompt.title.lower().replace(" ", "_").replace("'", "")
            # Detect format from best_path extension
            ext = Path(best_path).suffix or ".wav"
            final_name = f"{safe_title}{ext}"
            final_path = genre_dir / final_name
            shutil.copy2(best_path, str(final_path))

            logger.info(
                "  Best: score=%.4f -> %s",
                best_score,
                final_path,
            )

            manifest_entries.append(
                {
                    "genre": genre,
                    "title": prompt.title,
                    "tags": prompt.tags[:200],
                    "lyrics": prompt.lyrics,
                    "duration_s": prompt.duration_s,
                    "output_path": str(final_path),
                    "best_audio_quality_score": best_score,
                    "candidates": candidate_scores,
                    "infer_step": infer_step,
                    "guidance_scale": prompt.guidance_scale,
                    "status": "success",
                }
            )

    return manifest_entries


def main():
    parser = argparse.ArgumentParser(description="Batch audio generation using ACE-Step")
    parser.add_argument(
        "--device",
        default="cuda",
        help="Device to use (cuda or cpu, default: cuda)",
    )
    parser.add_argument(
        "--num-per-genre",
        type=int,
        default=8,
        help="Number of tracks per genre (default: 8)",
    )
    parser.add_argument(
        "--best-of",
        type=int,
        default=3,
        help="Generate N candidates and keep the best (default: 3)",
    )
    parser.add_argument(
        "--infer-step",
        type=int,
        default=ACESTEP_INFER_STEP,
        help=f"Diffusion inference steps. v1.0: 27=fast/50=quality. v1.5: 8=turbo/50=quality. (default: {ACESTEP_INFER_STEP})",
    )
    parser.add_argument(
        "--guidance-scale",
        type=float,
        default=ACESTEP_GUIDANCE_SCALE,
        help=f"CFG guidance scale (default: {ACESTEP_GUIDANCE_SCALE})",
    )
    parser.add_argument(
        "--genres",
        nargs="+",
        default=None,
        help="Specific genres to generate (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: output/batch_YYYYMMDD_HHMM)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base random seed (default: 42)",
    )
    # v1.5-specific flags
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="v1.5 native batch size (default: 1, max: 8). Generates N candidates per call.",
    )
    parser.add_argument(
        "--bpm",
        type=int,
        default=None,
        help="Target BPM for all tracks (v1.5 only, auto-detected if omitted)",
    )
    parser.add_argument(
        "--key",
        default="",
        help="Target key for all tracks (v1.5 only, e.g., 'C major')",
    )

    args = parser.parse_args()

    # Set CUDA visibility if CPU requested
    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = PROJECT_ROOT / "output" / f"batch_{timestamp}"

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("ACE-Step Batch Generation")
    logger.info("=" * 60)
    logger.info("Output: %s", output_dir)
    logger.info("Genres: %s", args.genres or "all")
    logger.info("Per genre: %d tracks, best-of-%d", args.num_per_genre, args.best_of)
    logger.info("Infer steps: %d, guidance: %.1f", args.infer_step, args.guidance_scale)
    logger.info("Batch size: %d", args.batch_size)
    if args.bpm:
        logger.info("BPM: %d", args.bpm)
    if args.key:
        logger.info("Key: %s", args.key)
    logger.info("Base seed: %d", args.seed)
    logger.info("=" * 60)

    start = time.time()
    entries = generate_batch(
        genres=args.genres,
        num_per_genre=args.num_per_genre,
        best_of=args.best_of,
        infer_step=args.infer_step,
        guidance_scale=args.guidance_scale,
        output_dir=output_dir,
        base_seed=args.seed,
        batch_size=args.batch_size,
        bpm=args.bpm,
        key_scale=args.key,
    )
    total_time = time.time() - start

    # Write manifest
    manifest_path = output_dir / "generation_manifest.json"
    success_count = sum(1 for e in entries if e.get("status") == "success")
    manifest = {
        "total_tracks": len(entries),
        "successful": success_count,
        "failed": len(entries) - success_count,
        "infer_step": args.infer_step,
        "guidance_scale": args.guidance_scale,
        "best_of": args.best_of,
        "batch_size": args.batch_size,
        "bpm": args.bpm,
        "key_scale": args.key,
        "base_seed": args.seed,
        "total_time_s": round(total_time, 1),
        "tracks": entries,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("=" * 60)
    logger.info("Batch generation complete!")
    logger.info("  Successful: %d / %d", success_count, len(entries))
    logger.info("  Total time: %.1f minutes", total_time / 60)
    logger.info("  Manifest: %s", manifest_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
