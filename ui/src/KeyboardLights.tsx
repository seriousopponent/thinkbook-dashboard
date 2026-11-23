import { useEffect, useState } from 'react';
import { Keyboard } from 'lucide-react';
import type { Snapshot } from './types';

export function KeyboardLights({state, disabled, onChange}: {
  state?: Snapshot['keyboard']; disabled: boolean; onChange: (brightness: number) => void;
}) {
  const [draft, setDraft] = useState(state?.brightness ?? 0);
  useEffect(() => { setDraft(state?.brightness ?? 0); }, [state?.brightness]);
  const available = state?.available && state.brightness != null && state.maximum != null;
  const maximum = state?.maximum ?? 0;
  const label = (value: number) => value === 0 ? 'Kapalı' : maximum === 1 ? 'Açık' :
    maximum === 2 ? (value === 1 ? 'Düşük' : 'Yüksek') : `Seviye ${value}`;

  return <section className="panel keyboard-panel" aria-labelledby="keyboard-title">
    <div className="section-heading"><h2 id="keyboard-title"><Keyboard size={19}/>Klavye aydınlatması</h2>
      <span className="shortcut"><kbd>Fn</kbd> + <kbd>Space</kbd></span>
    </div>
    {available ? <>
      {maximum <= 4 ? <div className="segmented control-body" role="group" aria-label="Klavye aydınlatma seviyesi">
        {Array.from({length: maximum + 1}, (_, level) => <button key={level}
          className={state.brightness === level ? 'selected' : ''}
          disabled={disabled || state.brightness === level} aria-pressed={state.brightness === level}
          onClick={() => onChange(level)}>
          {label(level)}
        </button>)}
      </div> : <div className="keyboard-slider">
        <label htmlFor="keyboard-brightness">Parlaklık: {draft} / {maximum}</label>
        <input id="keyboard-brightness" type="range" min="0" max={maximum} step="1"
          value={draft} disabled={disabled} onChange={event => setDraft(Number(event.target.value))}/>
        <button className="button primary" disabled={disabled || draft === state.brightness} onClick={() => onChange(draft)}>Aydınlatmayı uygula</button>
      </div>}
      <span className="sr-only" aria-label="Geçerli aydınlatma seviyesi">{label(state.brightness!)}</span>
    </> : <p className="inline-error">{state?.error || 'Klavye aydınlatma bilgisi okunamıyor.'}</p>}
  </section>;
}
