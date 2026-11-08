/**
 * Web MIDI for NoDAW Studio PRO.
 *
 * - Works without a learn step: notes that are not learned are sent out as `midi-note` events and the
 *   Deck routes them by the chosen layout (Auto: channel 10 or notes 36-51 to pads, everything else to
 *   keys; Pads: 36-51 to pads 1-16; Keys: every note to the keys).
 * - Learn: right-click (long-press) a pad, key or knob, then move the hardware control.
 *   Learned mappings win over the default layout and persist in localStorage.
 * - Web MIDI exists in Chrome, Edge and Opera on desktop and Android. Safari on iPhone and iPad has
 *   no Web MIDI at all, so phones use touch.
 */
export type MidiRouting = 'auto' | 'pads' | 'keys'
export type MidiStatus = 'unsupported' | 'idle' | 'pending' | 'ready' | 'denied'

/** Default layout. Auto: channel 10 drums or notes 36-51 while the pads are showing go to pads. */
export function routeNote(note: number, channel: number, routing: MidiRouting, view: 'pads' | 'keys' | 'other'): { kind: 'pad'; index: number } | { kind: 'key'; note: number } {
  const padRange = note >= 36 && note <= 51
  const toPads = routing === 'pads' ? padRange : routing === 'keys' ? false : padRange && (channel === 9 || view !== 'keys')
  return toPads ? { kind: 'pad', index: note - 36 } : { kind: 'key', note }
}

export type MidiTarget =
  | { kind: 'pad'; index: number }
  | { kind: 'key'; note: number }
  | { kind: 'knob'; id: string }

export type MidiMapping = {
  type: 'note' | 'cc'
  channel: number
  number: number
  target: MidiTarget
}


class MidiLearn {
  private access: MIDIAccess | null = null
  private mappings: MidiMapping[] = []
  private learning: MidiTarget | null = null
  private listeners = new Set<(mappings: MidiMapping[]) => void>()
  private onLearn: ((target: MidiTarget, mapping: MidiMapping) => void) | null = null
  private storageKey = 'nodaw-midi-mappings-v1'
  status: MidiStatus = typeof navigator !== 'undefined' && 'requestMIDIAccess' in navigator ? 'idle' : 'unsupported'
  routing: MidiRouting = (localStorage.getItem('nodaw-midi-routing') as MidiRouting) || 'auto'
  inputs: string[] = []
  lastNote = ''

  constructor() {
    this.load()
    // Only connect silently when permission was already granted; otherwise wait for the Connect button.
    try {
      void navigator.permissions?.query({ name: 'midi' as PermissionName }).then((p) => { if (p.state === 'granted') void this.connect() }).catch(() => undefined)
    } catch { /* no permissions API */ }
  }

  get supported() { return this.status !== 'unsupported' }

  setRouting(r: MidiRouting) {
    this.routing = r
    try { localStorage.setItem('nodaw-midi-routing', r) } catch { /* ignore */ }
    this.emit()
  }

  /** Ask for Web MIDI access (call from a click). */
  async connect(): Promise<MidiStatus> {
    if (!navigator.requestMIDIAccess) { this.status = 'unsupported'; this.emit(); return this.status }
    if (this.status === 'ready') return this.status
    this.status = 'pending'
    this.emit()
    try {
      this.access = await navigator.requestMIDIAccess({ sysex: false })
      const bind = () => {
        this.inputs = []
        this.access?.inputs.forEach((input) => {
          input.onmidimessage = (e) => this.handleMessage(e)
          this.inputs.push(input.name || 'MIDI input')
        })
        this.emit()
      }
      bind()
      this.access.onstatechange = bind
      this.status = 'ready'
    } catch {
      this.status = 'denied'
    }
    this.emit()
    return this.status
  }

  private handleMessage(e: MIDIMessageEvent) {
    if (!e.data || e.data.length < 2) return
    const [status, data1, data2 = 0] = e.data
    const type = status & 0xf0
    const channel = status & 0x0f
    const isNote = type === 0x90 || type === 0x80
    const isCC = type === 0xb0
    if (!isNote && !isCC) return

    if (this.learning) {
      const mapping: MidiMapping = {
        type: isNote ? 'note' : 'cc',
        channel,
        number: data1,
        target: this.learning,
      }
      this.mappings = this.mappings.filter(
        (m) => !(m.type === mapping.type && m.channel === mapping.channel && m.number === mapping.number)
      )
      this.mappings.push(mapping)
      this.save()
      this.emit()
      this.onLearn?.(this.learning, mapping)
      this.learning = null
      return
    }

    // Dispatch to mapped targets
    const value = isNote ? (type === 0x90 ? data2 / 127 : 0) : data2 / 127
    let mapped = false
    for (const m of this.mappings) {
      if (m.type === (isNote ? 'note' : 'cc') && m.channel === channel && m.number === data1) {
        this.dispatch(m.target, value)
        mapped = true
      }
    }
    if (!mapped && isNote) {
      // default layout, no learn step needed; the Deck routes it (see routeNote)
      if (value > 0) { this.lastNote = `ch ${channel + 1} note ${data1}`; this.emit() }
      window.dispatchEvent(new CustomEvent('midi-note', { detail: { note: data1, value, channel } }))
    }
  }

  /** Feed a raw message (tests and virtual keyboards). */
  inject(bytes: number[]) {
    this.handleMessage({ data: new Uint8Array(bytes) } as unknown as MIDIMessageEvent)
  }

  private dispatch(target: MidiTarget, value: number) {
    // Emit custom event so components can react without tight coupling
    window.dispatchEvent(new CustomEvent('midi-control', { detail: { target, value } }))
  }

  startLearn(target: MidiTarget, onDone?: (target: MidiTarget, mapping: MidiMapping) => void) {
    this.learning = target
    this.onLearn = onDone || null
  }

  cancelLearn() {
    this.learning = null
    this.onLearn = null
  }

  getMappings() {
    return [...this.mappings]
  }

  clearAll() {
    this.mappings = []
    this.save()
    this.emit()
  }

  subscribe(fn: (mappings: MidiMapping[]) => void) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private emit() {
    this.listeners.forEach((fn) => fn(this.mappings))
  }

  isLearning() { return this.learning !== null }

  private save() {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this.mappings))
    } catch {
      /* ignore */
    }
  }

  private load() {
    try {
      const raw = localStorage.getItem(this.storageKey)
      if (raw) this.mappings = JSON.parse(raw)
    } catch {
      this.mappings = []
    }
  }
}

export const midi = new MidiLearn()
