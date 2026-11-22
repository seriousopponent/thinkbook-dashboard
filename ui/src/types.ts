export interface Snapshot {
  timestamp: string; session_started: string; model: string; os: string; kernel: string; cpu_name: string;
  cpu: {usage: number | null; temperature: number | null};
  memory: {total_gib: number | null; used_gib: number | null; percent: number | null};
  disk: {total_gib: number; used_gib: number; percent: number};
  battery: {present: boolean; online: boolean; percent?: number | null; status?: string; watts?: number | null; energy_wh?: number | null; full_wh?: number | null; design_wh?: number | null; health?: number | null; cycles?: number | null; remaining_hours?: number | null; conservation: string | null};
  power: {mode: string | null; label: string | null; error: string | null};
  graphics: {mode: string | null; reported: string | null; reboot_required: boolean | null; error: string | null};
  firmware: {mode: string | null; choices: string[]};
  gpu: {pci: string; state: string | null; control: string | null}[];
  events: {time: string; title: string; ok: boolean}[]; busy: boolean;
}
export interface Telemetry {rows: string[][]; timestamp: string}
