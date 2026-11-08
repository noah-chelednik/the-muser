import { Composer } from '../../components/Composer'
import { Deck } from '../../components/Deck'
import { Library } from '../../components/Library'
import { SampleLibrary } from '../../components/SampleLibrary'
import '../../components/SampleLibrary.css'
import { useStudio } from '../../studio/StudioContext'
import { isBrowserDemo } from '../../api'
import { SoundBrowser } from '../../components/deck/SoundBrowser'
import { useState } from 'react'
import { audio } from '../../audio/engine'
import { PADS } from '../../audio/instruments'

export function ComposerPane() {
  const { status, loadTrack, onGenerate, generating } = useStudio()
  return <Composer status={status} onTrack={(t) => loadTrack(t)} onGenerate={onGenerate} generating={generating} />
}

export function LibraryPane() {
  const { tracks, current, loadTrack, deleteTrack, uploadFile } = useStudio()
  return (
    <div className="library-stack">
      <Library tracks={tracks} currentId={current?.id ?? null} onSelect={loadTrack} onDelete={deleteTrack} onUpload={uploadFile} />
      <LibrarySounds />
      {!isBrowserDemo() && <SampleLibrary />}
    </div>
  )
}

export function DeckPane() {
  const { history } = useStudio()
  return <Deck history={history} />
}

/** CC0 drum library and uploads, loading onto pads (works on the hosted demo and on phones). */
function LibrarySounds() {
  const [pad, setPad] = useState(0)
  const { history } = useStudio()
  return (
    <section className="panel deck nd" data-testid="library-sounds">
      <SoundBrowser pad={pad} setPad={setPad} onAssigned={(i) => { audio.unlock(); PADS[i].play(audio.ensure().currentTime + 0.01, history.state.pads) }} onKeys={() => undefined} />
    </section>
  )
}
