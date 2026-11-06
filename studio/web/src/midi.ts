/**
 * Web MIDI learn system for NoDAW Studio PRO.
 *
 * Supports mapping MIDI notes to pads and keys, and CCs to knobs.
 * Learning mode: click a control, then move the physical control.
 * Mappings persist in localStorage.
 */

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

type MidiListener = (msg: MIDIMessageEvent) => void

class MidiLearn {
  private access: MIDIAccess | null = null
  private mappings: MidiMapping[] = []
  private learning: MidiTarget | null = null
  private listeners = new Set<(mappings: MidiMapping[]) => void>()
  private onLearn: ((target: MidiTarget, mapping: MidiMapping) => void) | null = null
  private storageKey = 'nodaw-midi-mappings-v1'

  constructor() {
    this.load()
    this.requestAccess()
  }

  private async requestAccess() {
    if (!navigator.requestMIDIAccess) {
      console.warn('Web MIDI not supported in this browser')
      return
    }
    try {
      this.access = await navigator.requestMIDIAccess({ sysex: false })
      this.access.inputs.forEach((input) => {
        input.onmidimessage = (e) => this.handleMessage(e)
      })
      this.access.onstatechange = () => {
        this.access?.inputs.forEach((input) => {
          input.onmidimessage = (e) => this.handleMessage(e)
        })
      }
    } catch (err) {
      console.warn('MIDI access denied or failed', err)
    }
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
    for (const m of this.mappings) {
      if (m.type === (isNote ? 'note' : 'cc') && m.channel === channel && m.number === data1) {
        this.dispatch(m.target, value)
      }
    }
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
