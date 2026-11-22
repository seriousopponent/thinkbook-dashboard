type Reply = {ok: boolean; data?: unknown; error?: string};
type Native = {request: (id: string, action: string, payload: string) => void; reply: {connect: (fn: (id: string, value: string) => void) => void}; copyText: (text: string) => void};
declare global { interface Window { qt?: {webChannelTransport: unknown}; QWebChannel?: new (transport: unknown, callback: (channel: {objects: {dashboard: Native}}) => void) => unknown } }
let bridge: Native | null = null;
let counter = 0;
let connecting: Promise<Native> | null = null;
const pending = new Map<string, {resolve: (data: unknown) => void; reject: (error: Error) => void; timer: number}>();
function connect(): Promise<Native> {
  if (bridge) return Promise.resolve(bridge);
  if (connecting) return connecting;
  connecting = new Promise<Native>((resolve, reject) => {
    if (!window.qt || !window.QWebChannel) { reject(new Error('Yerel bağlantı bulunamadı. Uygulamayı masaüstündeki ThinkBook Dashboard simgesinden aç.')); return; }
    const timeout = window.setTimeout(() => reject(new Error('Cihaz bağlantısı zaman aşımına uğradı.')), 10000);
    new window.QWebChannel(window.qt.webChannelTransport, channel => {
      clearTimeout(timeout); bridge = channel.objects.dashboard;
      bridge.reply.connect((id, value) => {
        const call = pending.get(id); if (!call) return;
        pending.delete(id); clearTimeout(call.timer);
        try { const result: Reply = JSON.parse(value); result.ok ? call.resolve(result.data) : call.reject(new Error(result.error || 'İşlem tamamlanamadı.')); }
        catch (error) { call.reject(error instanceof Error ? error : new Error(String(error))); }
      });
      resolve(bridge);
    });
  }).catch(error => { connecting = null; throw error; });
  return connecting;
}
export async function request<T>(action: string, payload: object = {}): Promise<T> {
  const native = await connect(); const id = String(++counter);
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => { pending.delete(id); reject(new Error('İşlem zaman aşımına uğradı. Ayarı yeniden denemeden önce durumu yenile.')); }, action === 'status' ? 15000 : 200000);
    pending.set(id, {resolve: value => resolve(value as T), reject, timer});
    native.request(id, action, JSON.stringify(payload));
  });
}
export async function copyDiagnostics() {const result = await request<{text: string}>('diagnostics'); (await connect()).copyText(result.text);}
