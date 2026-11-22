import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';

// Like a native app: iOS Safari ignores user-scalable=no, so its page pinch-zoom is stopped here (the charts keep their
// own pinch, which uses touch events, not these gesture events)
const stopZoom = (e: Event) => e.preventDefault();
['gesturestart', 'gesturechange', 'gestureend'].forEach(t => document.addEventListener(t, stopZoom, { passive: false }));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
