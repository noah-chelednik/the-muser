import { useId } from 'react'

type Props = {
  label: string
  value: number
  min: number
  max: number
  step?: number
  log?: boolean
  format?: (v: number) => string
  onChange: (v: number) => void
  onEnd?: () => void
  testId?: string
}

/** Finger-sized labelled range control. `log` maps the track logarithmically (frequencies, Q). */
export function Slider({ label, value, min, max, step, log, format = (v) => v.toFixed(2), onChange, onEnd, testId }: Props) {
  const id = useId()
  const toPos = (v: number) => (log ? Math.log(v / min) / Math.log(max / min) : (v - min) / (max - min))
  const fromPos = (p: number) => {
    let v = log ? min * Math.pow(max / min, p) : min + p * (max - min)
    if (step) v = Math.round(v / step) * step
    return Math.min(max, Math.max(min, v))
  }
  return (
    <label className="nd-slider" htmlFor={id}>
      <span className="nd-slider-l">{label}</span>
      <input
        id={id}
        type="range"
        min={0}
        max={1000}
        step={1}
        value={Math.round(toPos(value) * 1000)}
        onChange={(e) => onChange(fromPos(+e.target.value / 1000))}
        onPointerUp={onEnd}
        onKeyUp={onEnd}
        onTouchEnd={onEnd}
        data-testid={testId}
        aria-valuetext={format(value)}
      />
      <span className="nd-slider-v">{format(value)}</span>
    </label>
  )
}
