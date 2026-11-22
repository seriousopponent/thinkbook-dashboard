import energy from './assets/energy-capsule-v1.webp';
import compute from './assets/compute-core-v1.webp';
import memory from './assets/memory-module-v1.webp';
import storage from './assets/storage-drive-v1.webp';
import workstation from './assets/workstation-v1.webp';

const artwork = {
  energy: {src: energy, width: 1254, height: 1254},
  compute: {src: compute, width: 1254, height: 1254},
  memory: {src: memory, width: 1448, height: 1086},
  storage: {src: storage, width: 1254, height: 1254},
  workstation: {src: workstation, width: 1254, height: 1254},
};

/** Decorative product concepts; actual hardware readings stay in adjacent text. */
export function HardwareArtwork({kind, className = ''}: {kind: keyof typeof artwork; className?: string}) {
  return <div className={`hardware-artwork ${className}`} data-artwork={kind} aria-hidden="true">
    <img {...artwork[kind]} alt="" loading="lazy" decoding="async" draggable={false}/>
  </div>;
}
