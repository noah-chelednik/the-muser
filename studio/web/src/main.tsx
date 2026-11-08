import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './skins/tokens.css'
import './styles/base.css'
import './styles/pro3.css'
import { applySkinAttr } from './skins/SkinProvider'
import { initialSkin } from './skins/registry'
import App from './App'
import { initApi } from './api'
import { audio, installAudioUnlock } from './audio/engine'
import { restoreSession } from './audio/samples'
import { midi } from './midi'
import * as upload from './audio/upload'
import * as library from './audio/library'
import { padBank } from './audio/samples'

installAudioUnlock()
// Test and debugging hook: the automated audibility check reads the output node through this.
;(window as unknown as { __muser: unknown }).__muser = { audio, midi, upload, library, padBank }
void restoreSession()

applySkinAttr(initialSkin())

// Find out first whether a Studio server answers; if not, run the in-browser demo backend.
void initApi().then(() =>
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  ),
)
