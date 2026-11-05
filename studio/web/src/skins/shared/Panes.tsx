import { Composer } from '../../components/Composer'
import { Deck } from '../../components/Deck'
import { Library } from '../../components/Library'
import { SampleLibrary } from '../../components/SampleLibrary'
import '../../components/SampleLibrary.css'
import { useStudio } from '../../studio/StudioContext'

export function ComposerPane() {
  const { status, loadTrack, onGenerate, generating } = useStudio()
  return <Composer status={status} onTrack={(t) => loadTrack(t)} onGenerate={onGenerate} generating={generating} />
}

export function LibraryPane() {
  const { tracks, current, loadTrack, deleteTrack, uploadFile } = useStudio()
  return (
    <div className="library-stack">
      <Library tracks={tracks} currentId={current?.id ?? null} onSelect={loadTrack} onDelete={deleteTrack} onUpload={uploadFile} />
      <SampleLibrary />
    </div>
  )
}

export function DeckPane() {
  const { history } = useStudio()
  return <Deck history={history} />
}
