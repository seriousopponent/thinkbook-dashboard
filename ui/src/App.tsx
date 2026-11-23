import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowUpRight, Battery, Check, ChevronDown, CircuitBoard, Copy, Cpu, Gauge, HardDrive, Info, Laptop, LayoutDashboard, LoaderCircle, MemoryStick, Moon, RefreshCw, RotateCcw, SlidersHorizontal, Sun, TriangleAlert, X } from 'lucide-react';
import { BounceSidebar } from '@/components/ui/bounce-sidebar';
import { AnimatedCounter } from '@/components/ui/animated-counter';
import { copyDiagnostics, request } from './bridge';
import type { Snapshot, Telemetry } from './types';
import { KeyboardLights } from './KeyboardLights';
import workstation from './assets/workstation-v1.webp';

const titles = ['Genel bakış', 'Güç ve pil', 'Grafik modları', 'Sistem'];
const modeNames: Record<string,string> = {hybrid:'Hibrit', integrated:'Yalnızca Intel', nvidia:'NVIDIA', compute:'Hesaplama', 'low-power':'Tasarruf', balanced:'Dengeli', performance:'Performans', quiet:'Sessiz', cool:'Serin', 'balanced-performance':'Dengeli performans'};
const graphicsModes = [
  {id:'hybrid', title:'Hibrit', description:'Intel + gerektiğinde NVIDIA', icon:Laptop},
  {id:'integrated', title:'Yalnızca Intel', description:'Daha düşük güç tüketimi', icon:Battery},
  {id:'nvidia', title:'NVIDIA', description:'Ayrık ekran kartı sürekli açık', icon:CircuitBoard},
];
const powerModes = [{id:'battery', title:'Tasarruf'}, {id:'balanced', title:'Dengeli'}, {id:'performance', title:'Performans'}];
const fmt = (value: number | null | undefined, unit = '', decimals = 0) => value == null ? '—' : `${value.toLocaleString('tr-TR', {maximumFractionDigits:decimals})}${unit}`;
const clock = (value?: string) => value ? new Date(value).toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'}) : '—';
const gpuLabel = (state?: string | null) => ({suspended:'Uykuda', active:'Aktif', suspending:'Uykuya geçiyor', resuming:'Uyanıyor'}[state || ''] || 'Bilinmiyor');
function Panel({title, children, extra, className=''}: {title:string; children:ReactNode; extra?:ReactNode; className?:string}) {
  return <section className={`panel ${className}`}><div className="section-heading"><h2>{title}</h2>{extra}</div>{children}</section>;
}
function Row({label, children}: {label:string; children:ReactNode}) {return <div className="detail-row"><dt>{label}</dt><dd>{children}</dd></div>;}
function Meter({value}: {value:number | null | undefined}) {return <div className="meter" aria-hidden="true"><span style={{width:`${Math.max(0,Math.min(100,value ?? 0))}%`}}/></div>;}
function Sparkline({values}: {values:number[]}) {
  if(values.length<2) return <div className="sparkline-empty">Ölçüm bekleniyor</div>;
  const points=values.map((value,index)=>`${index*300/(values.length-1)},${38-value*.34}`).join(' ');
  return <svg className="sparkline" viewBox="0 0 300 42" preserveAspectRatio="none" role="img" aria-label="İşlemci kullanım geçmişi"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke"/></svg>;
}
function RestartDialog({close, confirm, busy}: {close:()=>void; confirm:()=>void; busy:boolean}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{ref.current?.showModal();},[]);
  return <dialog ref={ref} className="restart-dialog" aria-labelledby="restart-title" onCancel={event=>{event.preventDefault();if(!busy)close();}}>
    <RotateCcw size={24}/><h2 id="restart-title">Yeniden başlatılsın mı?</h2>
    <p>Grafik modu uygulanacak. Devam etmeden önce açık çalışmalarını kaydet.</p>
    <div className="dialog-actions"><button className="button secondary" onClick={close} disabled={busy} autoFocus>Şimdi değil</button><button className="button primary" onClick={confirm} disabled={busy}>Yeniden başlat</button></div>
  </dialog>;
}
export default function App() {
  const [tab,setTab] = useState(0);
  const [data,setData] = useState<Snapshot | null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState('');
  const [refreshing,setRefreshing] = useState(false);
  const [toast,setToast] = useState<{message:string;ok:boolean} | null>(null);
  const [theme,setTheme] = useState(()=>localStorage.getItem('thinkbook-theme') || 'dark');
  const [history,setHistory] = useState<number[]>([]);
  const [selectedGraphics,setSelectedGraphics] = useState('hybrid');
  const [telemetry,setTelemetry] = useState<Telemetry | null>(null);
  const [restart,setRestart] = useState(false);
  const loading = useRef(false);
  const mutation = useRef(false);
  const mounted = useRef(true);
  const content = useRef<HTMLElement>(null);

  useEffect(()=>{document.documentElement.dataset.theme=theme; localStorage.setItem('thinkbook-theme',theme);},[theme]);
  const refresh = useCallback(async()=>{
    if (loading.current || mutation.current) return;
    loading.current=true; setRefreshing(true);
    try {const result=await request<Snapshot>('status'); if(!mounted.current) return; setData(result); setError(''); document.body.dataset.connected='true'; if(result.cpu.usage != null) setHistory(old=>[...old,result.cpu.usage!].slice(-40));}
    catch(e) {if(mounted.current) {setError(String(e instanceof Error ? e.message : e)); document.body.dataset.connected='false';}}
    finally {loading.current=false; if(mounted.current) setRefreshing(false);}
  },[]);
  useEffect(()=>{mounted.current=true; void refresh(); const interval=window.setInterval(()=>{if(!document.hidden && document.hasFocus()) void refresh();},4000); const visible=()=>{if(!document.hidden && document.hasFocus()) void refresh();}; document.addEventListener('visibilitychange',visible); window.addEventListener('focus',visible); return ()=>{mounted.current=false; clearInterval(interval); document.removeEventListener('visibilitychange',visible); window.removeEventListener('focus',visible);};},[refresh]);
  useEffect(()=>{if(data?.graphics.mode) setSelectedGraphics(data.graphics.mode);},[data?.graphics.mode]);
  useEffect(()=>{if(!toast) return; const timer=window.setTimeout(()=>setToast(null),toast.ok?6000:12000); return ()=>clearTimeout(timer);},[toast]);
  useEffect(()=>{content.current?.scrollTo({top:0});},[tab]);

  async function act(action:string, payload:object={}, label='İşlem uygulanıyor') {
    if(mutation.current) return;
    mutation.current=true; setBusy(label);
    try {const result=await request<{message:string}>(action,payload); setToast({message:result.message,ok:true});}
    catch(e) {setToast({message:e instanceof Error?e.message:String(e),ok:false});}
    finally {mutation.current=false;setBusy('');void refresh();}
  }
  async function measure() {
    if(mutation.current) return;
    mutation.current=true;setBusy('NVIDIA ölçümü alınıyor');
    try {setTelemetry(await request<Telemetry>('telemetry'));}
    catch(e) {setToast({message:e instanceof Error?e.message:String(e),ok:false});}
    finally {mutation.current=false;setBusy('');void refresh();}
  }
  async function copy() {try {await copyDiagnostics();setToast({message:'Tanılama bilgisi panoya kopyalandı.',ok:true});} catch(e) {setToast({message:String(e),ok:false});}}
  const disabled = !!busy || !data || !!error || !!data?.busy;
  const battery=data?.battery;
  const gpu=data?.gpu[0];
  const sleeping=gpu?.state==='suspended';
  const pendingRestart=data?.graphics.reboot_required===true;
  const powerError=data?.power.error;
  const keyboardControl = data && <KeyboardLights state={data.keyboard} disabled={disabled} onChange={brightness=>void act('keyboard',{brightness},'Aydınlatma ayarlanıyor')}/>;
  const powerChoices = <div className="segmented" role="group" aria-label="Güç profili">{powerModes.map(({id,title})=><button key={id} disabled={disabled||!!powerError||data?.power.mode===id} aria-pressed={data?.power.mode===id} className={data?.power.mode===id?'selected':''} onClick={()=>void act('power',{mode:id},'Güç profili uygulanıyor')}>{title}</button>)}</div>;
  const powerPanel = <Panel title="Güç profili" extra={<Gauge size={17}/>}><div className="control-body">{powerChoices}</div>{powerError&&<p className="inline-error">{powerError}</p>}</Panel>;
  const restartBanner = pendingRestart && <div className="restart-banner"><RotateCcw size={17}/><span>Grafik değişikliği yeniden başlatmayı bekliyor.</span><button className="text-button" disabled={disabled} onClick={()=>setRestart(true)}>Yeniden başlat<ArrowUpRight size={15}/></button></div>;
  const batteryStatus = !battery?.present?'Pil bulunamadı':battery.status==='Charging'?'Şarj oluyor':battery.status==='Discharging'?'Pil kullanılıyor':battery.online?'Prize bağlı':'Şarj dengede';
  const energyCard = <section className="energy-card" aria-label="Pil durumu">
    <div className="section-heading"><h2><Battery size={18}/>Pil</h2><span className="small-label">{batteryStatus}</span></div>
    <div className="battery-reading">{battery?.percent!=null?<AnimatedCounter value={battery.percent} duration={.25} suffix={<span className="number-unit">%</span>}/>:<span>—</span>}</div>
    <Meter value={battery?.percent}/><div className="battery-caption"><span>{battery?.conservation==='On'?'Şarj koruması açık':battery?.conservation==='Off'?'Şarj koruması kapalı':'Şarj koruması okunamıyor'}</span><span>{battery?.remaining_hours!=null?`~${fmt(battery.remaining_hours,' sa.',1)}`:battery?.status==='Discharging'?fmt(battery.watts,' W',1):''}</span></div>
  </section>;
  const gpuCard = <section className="gpu-card"><div className="section-heading"><h2><CircuitBoard size={18}/>Grafik</h2><span className={`state-label ${sleeping?'positive':''}`}><span className="status-dot"/>NVIDIA {gpuLabel(gpu?.state)}</span></div>
    <div className="gpu-mode">{modeNames[data?.graphics.mode||'']||'—'}</div><div className="gpu-card-bottom"><span>{sleeping?'Ayrık GPU güç tasarrufunda':gpu?.control==='on'?'Otomatik uyku kapalı':'Ayrık GPU kullanımda olabilir'}</span><button className="text-button" onClick={()=>setTab(2)}>Modu değiştir<ArrowUpRight size={15}/></button></div>
  </section>;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-stroke"/>ThinkBook<span className="brand-sub">Kontrol paneli</span></div>
      <nav aria-label="Ana menü"><BounceSidebar items={[{label:titles[0],icon:<LayoutDashboard size={18}/>},{label:titles[1],icon:<Battery size={18}/>},{label:titles[2],icon:<CircuitBoard size={18}/>},{label:titles[3],icon:<SlidersHorizontal size={18}/> }]} value={tab} onChange={setTab} dotColor="var(--accent)" className="app-nav"/></nav>
      <div className="sidebar-bottom"><Laptop size={17}/><span>{data?.model||'ThinkBook'}<small>Dashboard 2</small></span></div>
    </aside>
    <main className="main" ref={content}>
      <header className="topbar"><h1>{titles[tab]}</h1><div className="topbar-actions">
        <span className={`connection ${error?'offline':''}`}><span className="status-dot"/>{error?'Bağlantı yok':data?'Bağlı':'Bağlanıyor'}</span>
        <button className="icon-button" aria-label={theme==='dark'?'Açık temaya geç':'Koyu temaya geç'} title={theme==='dark'?'Açık tema':'Koyu tema'} onClick={()=>setTheme(theme==='dark'?'light':'dark')}>{theme==='dark'?<Sun size={17}/>:<Moon size={17}/>}</button>
        <button className="icon-button" aria-label="Durumu yenile" title="Yenile" disabled={!!busy||refreshing} onClick={()=>void refresh()}><RefreshCw size={16} className={refreshing?'spinning':''}/></button>
      </div></header>
      <div className="page-content">
        {error&&<div className="error-banner" role="alert"><TriangleAlert size={19}/><div><strong>{data?'Veriler güncel olmayabilir.':'Cihaza bağlanılamadı.'}</strong><p>{error}</p></div><button className="button secondary" onClick={()=>void refresh()}>Tekrar dene</button></div>}
        {!data?(!error&&<div className="loading-panel"><LoaderCircle className="spinning" size={22}/><span>Cihaz bilgileri okunuyor…</span></div>):<>
          {tab===0&&<>
            <div className="overview-heading"><span>{data.model}</span><span>{data.os}</span></div>
            <div className="hero-grid">{energyCard}{gpuCard}</div>
            {restartBanner}
            <section className="metrics-section" aria-label="Sistem kullanımı">
              <div className="metric"><div className="metric-title"><Cpu size={16}/>İşlemci</div><div className="metric-value">{fmt(data.cpu.usage)}<small>%</small></div><span className="metric-detail">{fmt(data.cpu.temperature,' °C')}</span><Sparkline values={history}/></div>
              <div className="metric"><div className="metric-title"><MemoryStick size={16}/>Bellek</div><div className="metric-value">{fmt(data.memory.used_gib,'',1)}<small>GB</small></div><span className="metric-detail">{fmt(data.memory.total_gib,' GB',1)} toplam</span><Meter value={data.memory.percent}/></div>
              <div className="metric"><div className="metric-title"><HardDrive size={16}/>Depolama</div><div className="metric-value">{fmt(data.disk.used_gib)}<small>GB</small></div><span className="metric-detail">{fmt(data.disk.total_gib-data.disk.used_gib,' GB')} boş</span><Meter value={data.disk.percent}/></div>
            </section>
            <div className="section-label">Hızlı ayarlar</div><div className="control-grid">{powerPanel}{keyboardControl}</div>
          </>}
          {tab===1&&<>
            <div className="control-grid">{powerPanel}{keyboardControl}</div>
            <Panel title="Pil" extra={<span className="small-label">{batteryStatus}</span>}><div className="power-battery-grid">{energyCard}<dl className="battery-details"><Row label="Kapasite oranı">{fmt(battery?.health,'%',1)}</Row><Row label="Şarj döngüsü">{fmt(battery?.cycles)}</Row><Row label="Tam dolu kapasite">{fmt(battery?.full_wh,' Wh',1)}</Row><Row label="Tasarım kapasitesi">{fmt(battery?.design_wh,' Wh',1)}</Row></dl></div></Panel>
            <Panel title="Termal profil" extra={<span className="shortcut"><kbd>Fn</kbd> + <kbd>Q</kbd></span>}>
              <div className="thermal-controls"><div className="segmented" role="group" aria-label="Termal profil">{data.firmware.choices.map(mode=><button key={mode} className={mode===data.firmware.mode?'selected':''} aria-pressed={mode===data.firmware.mode} disabled={disabled||mode===data.firmware.mode} onClick={()=>void act('firmware',{mode},'Termal profil uygulanıyor')}>{modeNames[mode]||mode}</button>)}</div><button className="text-button" disabled={disabled} onClick={()=>void act('preview',{},'Gösterge açılıyor')}>Göstergeyi dene<ArrowUpRight size={14}/></button></div>
              <p className="footnote">{data.firmware.choices.length?'Fan ve işlemci davranışı. Sistem parolası istenebilir.':'Firmware profil arayüzü kullanılamıyor.'}</p>
            </Panel>
          </>}
          {tab===2&&<>
            <div className="graphics-summary"><div><span className="small-label">Kayıtlı mod</span><h2>{modeNames[data.graphics.mode||'']||'Okunamıyor'}</h2></div><div className="graphics-runtime"><span className={`state-label ${sleeping?'positive':''}`}><span className="status-dot"/>NVIDIA {gpuLabel(gpu?.state)}</span><small>Otomatik uyku {gpu?.control==='auto'?'açık':gpu?.control==='on'?'kapalı':'bilinmiyor'}</small></div></div>
            {restartBanner}
            <Panel title="Grafik modu" extra={<span className="small-label">Yeniden başlatma gerekir</span>}>
              <div className="graphics-choices">{graphicsModes.map(({id,title,description,icon:Icon})=><button key={id} aria-label={title} aria-pressed={selectedGraphics===id} className={`graphics-choice ${selectedGraphics===id?'selected':''}`} disabled={disabled||!!data.graphics.error} onClick={()=>setSelectedGraphics(id)}><Icon size={21}/><span className="graphics-choice-copy"><strong>{title}</strong><small>{description}</small></span>{data.graphics.mode===id&&<span className="saved-label">Kayıtlı</span>}<span className="radio-dot">{selectedGraphics===id&&<span/>}</span></button>)}</div>
              <details className="advanced-graphics"><summary>Gelişmiş seçenek<ChevronDown size={14}/></summary><button aria-label="Hesaplama" className={`graphics-choice ${selectedGraphics==='compute'?'selected':''}`} aria-pressed={selectedGraphics==='compute'} disabled={disabled||!!data.graphics.error} onClick={()=>setSelectedGraphics('compute')}><Cpu size={21}/><span className="graphics-choice-copy"><strong>Hesaplama</strong><small>Intel görüntü · NVIDIA CUDA</small></span><span className="radio-dot">{selectedGraphics==='compute'&&<span/>}</span></button></details>
              {selectedGraphics==='integrated'&&<div className="inline-warning"><Info size={17}/><span>NVIDIA’ya bağlı HDMI ve diğer harici ekran çıkışları kullanılamayabilir.</span></div>}
              {data.graphics.error&&<p className="inline-error">{data.graphics.error}</p>}
              <div className="apply-bar"><span>{selectedGraphics===data.graphics.mode?'Kayıtlı mod seçili':`${modeNames[selectedGraphics]} seçildi`}</span><button className="button primary" disabled={disabled||!!data.graphics.error||selectedGraphics===data.graphics.mode} onClick={()=>void act('graphics',{mode:selectedGraphics},'Grafik modu hazırlanıyor')}>Modu uygula</button></div>
            </Panel>
            <Panel title="GPU ölçümü" extra={<button className="button secondary" disabled={disabled} onClick={()=>void measure()}>Bir kez ölç</button>}><p className="footnote">Ölçüm, uyuyan NVIDIA kartını uyandırabilir.</p>
              {telemetry&&<div className="telemetry"><span className="small-label">Son ölçüm {clock(telemetry.timestamp)} · CANLI DEĞİL</span>{telemetry.rows.map(([name,temp,load,used,total,driver],i)=><div key={i}><h3>{name}</h3><dl className="telemetry-values"><Row label="Sıcaklık">{temp} °C</Row><Row label="Kullanım">{load}%</Row><Row label="VRAM">{used} / {total} MiB</Row><Row label="Sürücü">{driver}</Row></dl></div>)}</div>}
            </Panel>
          </>}
          {tab===3&&<>
            <section className="device-hero"><div><span className="small-label">Cihaz</span><h2>{data.model}</h2><p>{data.os}</p></div><img src={workstation} alt="" aria-hidden="true" width="1254" height="1254"/></section>
            <div className="system-grid"><Panel title="Donanım"><dl><Row label="İşlemci">{data.cpu_name}</Row><Row label="Bellek">{fmt(data.memory.total_gib,' GB',1)}</Row><Row label="Disk bölümü">{fmt(data.disk.total_gib,' GB')}</Row><Row label="Pil">{fmt(battery?.design_wh,' Wh',1)}</Row><Row label="NVIDIA">{gpuLabel(gpu?.state)}</Row></dl></Panel><Panel title="Yazılım"><dl><Row label="İşletim sistemi">{data.os}</Row><Row label="Çekirdek">{data.kernel}</Row><Row label="Dashboard">2.0</Row></dl><button className="button secondary diagnostics-button" disabled={disabled} onClick={()=>void copy()}><Copy size={15}/>Tanılama bilgisini kopyala</button></Panel></div>
            <details className="activity-panel"><summary><span>İşlem geçmişi</span><span className="small-label">{data.events.length} işlem</span><ChevronDown size={15}/></summary><div className="activity-list">{data.events.length?[...data.events].reverse().map((event,i)=><div className="activity-row" key={i}>{event.ok?<Check size={15}/>:<TriangleAlert size={15}/>}<span>{event.title}</span><time>{clock(event.time)}</time></div>):<p className="footnote">Bu oturumda işlem yok.</p>}</div></details>
            <div className="credits"><a href="https://rareui.com" rel="noreferrer">Rare UI</a><span>·</span><a href="https://github.com/swamimalode07/rare-ui" rel="noreferrer">Swami Malode · Kaynak ve lisans</a></div>
          </>}
        </>}
      </div>
    </main>
    {busy&&<div className="operation-status" role="status"><LoaderCircle size={16} className="spinning"/>{busy}</div>}
    {toast&&<div className={`toast ${toast.ok?'success':'failure'}`} role={toast.ok?'status':'alert'}>{toast.ok?<Check size={17}/>:<TriangleAlert size={17}/>}<span>{toast.message}</span><button className="icon-button" aria-label="Bildirimi kapat" onClick={()=>setToast(null)}><X size={16}/></button></div>}
    {restart&&<RestartDialog busy={!!busy} close={()=>setRestart(false)} confirm={()=>{setRestart(false);void act('reboot',{confirmed:true},'Yeniden başlatılıyor');}}/>}
  </div>;
}
