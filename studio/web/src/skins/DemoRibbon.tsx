import { useEffect } from 'react'
import { isBrowserDemo } from '../api'

export const REPO_URL = 'https://github.com/myaiplug/the-muser'

/** Always-visible label for the static, serverless build. Skin independent. */
export function DemoRibbon() {
  const on = isBrowserDemo()
  useEffect(() => {
    document.body.classList.toggle('browser-demo', on)
    return () => document.body.classList.remove('browser-demo')
  }, [on])
  if (!on) return null
  return (
    <div className="demo-ribbon" role="note" data-testid="demo-ribbon">
      <b>BROWSER DEMO</b>
      <span>Generated sound comes from a built-in synthesizer, not AI. Split on uploaded audio runs a real separation model in this tab. Everything stays in your browser.</span>
      <a href={REPO_URL} target="_blank" rel="noreferrer">Real AI needs the local install</a>
    </div>
  )
}
