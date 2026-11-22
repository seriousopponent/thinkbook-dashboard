import { useEffect, useState } from 'react';
import { Check, Keyboard, Sun } from 'lucide-react';
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
    <div className="panel-heading"><h2 id="keyboard-title"><Keyboard size={19}/>Klavye aydınlatması</h2>
      {available && <span className="badge green" aria-label="Geçerli aydınlatma seviyesi">{label(state.brightness!)}</span>}
    </div>
    <p className="panel-description">Tuşların ışığını bulunduğun ortama göre ayarla. Değişiklik anında uygulanır.</p>
    {available ? <>
      {maximum <= 4 ? <div className="keyboard-levels" role="group" aria-label="Klavye aydınlatma seviyesi">
        {Array.from({length: maximum + 1}, (_, level) => <button key={level}
          className={`keyboard-level ${state.brightness === level ? 'selected' : ''}`}
          disabled={disabled || state.brightness === level} aria-pressed={state.brightness === level}
          onClick={() => onChange(level)}>
          <Sun size={18}/><span>{label(level)}</span>{state.brightness === level && <Check size={16}/>}
        </button>)}
      </div> : <div className="keyboard-slider">
        <label htmlFor="keyboard-brightness">Parlaklık: {draft} / {maximum}</label>
        <input id="keyboard-brightness" type="range" min="0" max={maximum} step="1"
          value={draft} disabled={disabled} onChange={event => setDraft(Number(event.target.value))}/>
        <button className="button primary" disabled={disabled || draft === state.brightness} onClick={() => onChange(draft)}>Aydınlatmayı uygula</button>
      </div>}
      <p className="keyboard-hint"><kbd>Fn</kbd> + <kbd>Space</kbd><span>ThinkBook’ta klavyeden de değiştirebilirsin.</span></p>
    </> : <p className="inline-error">{state?.error || 'Klavye aydınlatma bilgisi okunamıyor.'}</p>}
  </section>;
}
