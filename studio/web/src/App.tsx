import { EasyProvider } from './studio/EasyContext'
import { RackProvider } from './studio/RackContext'
import { StudioProvider } from './studio/StudioContext'
import { Chrome } from './skins/Chrome'
import { SkinHost } from './skins/SkinHost'
import { SkinProvider } from './skins/SkinProvider'
import { DemoRibbon } from './skins/DemoRibbon'
import { AudioGate } from './components/AudioGate'

/** Providers sit above the lazy skin host, so a skin swap never loses session state. */
export default function App() {
  return (
    <StudioProvider>
      <EasyProvider>
        <RackProvider>
          <SkinProvider>
            <SkinHost />
            <Chrome />
            <DemoRibbon />
            <AudioGate />
          </SkinProvider>
        </RackProvider>
      </EasyProvider>
    </StudioProvider>
  )
}
