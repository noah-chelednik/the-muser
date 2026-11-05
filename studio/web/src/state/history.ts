import { useCallback, useMemo, useRef, useState } from 'react'

/**
 * Undo/redo history for an immutable document.
 *
 * - `commit(label, updater)` applies a discrete edit and records it.
 * - `begin(label)` / `preview(updater)` / `end()` group a continuous gesture
 *   (e.g. dragging a knob) into ONE undo step.
 * - `reset(updater)` changes state without recording (e.g. loading a track).
 */
export type HistoryEntry<T> = { state: T; label: string }
type H<T> = { past: HistoryEntry<T>[]; present: T; future: HistoryEntry<T>[] }

export function useHistory<T>(initial: T, limit = 200) {
  const [h, setH] = useState<H<T>>({ past: [], present: initial, future: [] })
  const ref = useRef(h)
  const gesture = useRef<{ start: T; label: string } | null>(null)

  const apply = useCallback((next: H<T>) => {
    ref.current = next
    setH(next)
  }, [])

  const commit = useCallback(
    (label: string, updater: (s: T) => T) => {
      const cur = ref.current
      const next = updater(cur.present)
      if (next === cur.present) return
      apply({ past: [...cur.past.slice(-(limit - 1)), { state: cur.present, label }], present: next, future: [] })
    },
    [apply, limit],
  )

  const begin = useCallback((label: string) => {
    gesture.current = { start: ref.current.present, label }
  }, [])

  const preview = useCallback(
    (updater: (s: T) => T) => {
      const cur = ref.current
      apply({ ...cur, present: updater(cur.present) })
    },
    [apply],
  )

  const end = useCallback(() => {
    const g = gesture.current
    gesture.current = null
    const cur = ref.current
    if (g && g.start !== cur.present) {
      apply({
        past: [...cur.past.slice(-(limit - 1)), { state: g.start, label: g.label }],
        present: cur.present,
        future: [],
      })
    }
  }, [apply, limit])

  const undo = useCallback(() => {
    const cur = ref.current
    const last = cur.past[cur.past.length - 1]
    if (!last) return
    apply({
      past: cur.past.slice(0, -1),
      present: last.state,
      future: [{ state: cur.present, label: last.label }, ...cur.future],
    })
  }, [apply])

  const redo = useCallback(() => {
    const cur = ref.current
    const [next, ...rest] = cur.future
    if (!next) return
    apply({ past: [...cur.past, { state: cur.present, label: next.label }], present: next.state, future: rest })
  }, [apply])

  const reset = useCallback(
    (updater: (s: T) => T) => {
      const cur = ref.current
      apply({ ...cur, present: updater(cur.present) })
    },
    [apply],
  )

  return useMemo(
    () => ({
      state: h.present,
      commit,
      begin,
      preview,
      end,
      undo,
      redo,
      reset,
      canUndo: h.past.length > 0,
      canRedo: h.future.length > 0,
      undoLabel: h.past[h.past.length - 1]?.label ?? '',
      redoLabel: h.future[0]?.label ?? '',
      depth: h.past.length,
      entries: h.past.map((e) => e.label),
    }),
    [h, commit, begin, preview, end, undo, redo, reset],
  )
}

export type History<T> = ReturnType<typeof useHistory<T>>
