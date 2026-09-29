import '@fontsource/marck-script/cyrillic-400.css';
import '@fontsource/marck-script/latin-400.css';
import '@arena/ui/styles.css';
import './app.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.js';
import { initTelegram } from './lib/telegram.js';
import { applyTheme } from './lib/settings.js';
import { unlockAudio } from './lib/sound.js';

initTelegram();
applyTheme();
// iOS lets sound start only from a touch: the first tap anywhere unlocks it and loads the effects.
window.addEventListener('pointerdown', unlockAudio, { once: true, capture: true });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
