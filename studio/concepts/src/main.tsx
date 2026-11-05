import { StrictMode, Suspense, lazy, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { actions } from './shared/store'

const A = lazy(() => import('./a/A'))
const B = lazy(() => import('./b/B'))
const C = lazy(() => import('./c/C'))
const Landing = lazy(() => import('./Landing'))

function useRoute() {
  const [h, setH] = useState(location.hash || '#/')
  useEffect(() => { const f = () => setH(location.hash || '#/'); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f) }, [])
  return h.replace(/^#\/?/, '').split('?')[0]
}
let seeded = false
function App() {
  const route = useRoute()
  const [seg, sub] = route.split('/')
  useEffect(() => {
    const q = new URLSearchParams(location.search)
    if (!seeded && seg) {
      seeded = true
      const s = q.get('s')
      if (s) actions.demo(s)
    }
    if (sub === 'advanced') actions.setMode('advanced')
    else if (sub === 'easy') actions.setMode('easy')
  }, [seg, sub])
  return (
    <Suspense fallback={<div style={{ position: 'fixed', inset: 0, background: '#000' }} />}>
      {seg === 'a' ? <A /> : seg === 'b' ? <B /> : seg === 'c' ? <C /> : <Landing />}
    </Suspense>
  )
}
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
