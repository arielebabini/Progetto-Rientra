import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Disabilita la navigazione tramite tasto Tab per evitare il focus sui vari elementi
window.addEventListener('keydown', (e) => {
  if (e.key === 'Tab') {
    e.preventDefault();
  }
}, true);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
