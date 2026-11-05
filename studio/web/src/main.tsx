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

installAudioUnlock()
// Test and debugging hook: the automated audibility check reads the output node through this.
;(window as unknown as { __muser: unknown }).__muser = { audio }

applySkinAttr(initialSkin())

// Find out first whether a Studio server answers; if not, run the in-browser demo backend.
void initApi().then(() =>
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  ),
)
