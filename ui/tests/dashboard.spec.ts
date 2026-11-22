import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
const snapshot = JSON.parse(readFileSync(new URL('./snapshot.json', import.meta.url), 'utf8'));

async function setup(page:Page, failPower=false) {
  // Mimic only the Qt transport; production has no demo data or HTTP API.
  await page.route('qrc:**', route=>route.fulfill({body:'',contentType:'application/javascript'}));
  await page.addInitScript(({snapshot, failPower})=>{
    const state=structuredClone(snapshot); state.cpu.usage=8;
    const calls:{action:string;payload:Record<string,unknown>}[]=[];
    (window as any).__calls=calls;
    (window as any).qt={webChannelTransport:{}};
    (window as any).QWebChannel=class {
      constructor(_transport:unknown, ready:Function) {
        let reply:Function;
        const bridge={reply:{connect:(fn:Function)=>{reply=fn;}},copyText:(text:string)=>{(window as any).__clipboard=text;},request:(id:string,action:string,raw:string)=>{
          const payload=JSON.parse(raw);calls.push({action,payload});
          let data:any;
          if(action==='status') data=structuredClone(state);
          else if(action==='graphics') {state.graphics.mode=payload.mode;state.graphics.reported=payload.mode==='integrated'?'compute':payload.mode;state.graphics.reboot_required=true;data={message:'Grafik modu kaydedildi. Yeniden başlattığında tamamen uygulanacak.'};}
          else if(action==='power') {if(failPower){setTimeout(()=>reply(id,JSON.stringify({ok:false,error:'Güç servisine ulaşılamadı.'})),40);return;}state.power.mode=payload.mode;data={message:'Güç profili uygulandı.'};}
          else if(action==='diagnostics') data={text:JSON.stringify(state)};
          else if(action==='telemetry') data={timestamp:state.timestamp,rows:[['NVIDIA GeForce RTX 5060','44','0','2','8151','595.84']]};
          else data={message:'İşlem tamamlandı.'};
          setTimeout(()=>reply(id,JSON.stringify({ok:true,data})),40);
        }};
        ready({objects:{dashboard:bridge}});
      }
    };
  },{snapshot,failPower});
  await page.goto('/');
  await expect(page.locator('body')).toHaveAttribute('data-connected','true');
}

test('overview is live, power change is verified, telemetry is opt-in',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await setup(page);
  await expect(page.getByRole('heading',{name:'Genel bakış.'})).toBeVisible();
  await expect(page.locator('[data-slot="animated-counter"]')).toHaveCount(1);
  await page.locator('.page-content img').evaluateAll(async images=>{
    for(const image of images as HTMLImageElement[]) await image.decode();
  });
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'/tmp/thinkbook-overview-docs.png'});
  await page.getByRole('button',{name:'Tasarruf Daha uzun pil süresi'}).click();
  await expect(page.getByRole('button',{name:'Tasarruf Daha uzun pil süresi'})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('status')).toContainText('Güç profili uygulandı');
  expect(await page.evaluate(()=>(window as any).__calls.filter((x:any)=>x.action==='telemetry').length)).toBe(0);
  await page.screenshot({path:'/tmp/thinkbook-overview.png',fullPage:true});
});

test('all graphics modes, pending reboot, and safe cancellation',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Grafik modları',exact:true}).click();
  await expect(page.getByRole('button',{name:'Modu uygula'})).toBeDisabled();
  await page.getByRole('button',{name:/DAHA UZUN PİL Yalnızca Intel/}).click();
  await expect(page.getByText(/HDMI ve diğer harici ekran/)).toBeVisible();
  await page.getByRole('button',{name:'Modu uygula'}).click();
  await expect(page.locator('.graphics-summary h2')).toHaveText('Yalnızca Intel');
  await expect(page.getByRole('button',{name:'Modu uygula'})).toBeDisabled();
  await page.getByText('Gelişmiş seçenek',{exact:true}).click();
  await page.getByRole('button',{name:/Hesaplama · Intel/}).click();
  await page.getByRole('button',{name:'Modu uygula'}).click();
  await expect(page.locator('.graphics-summary h2')).toHaveText('Hesaplama');
  await page.getByRole('button',{name:/TAM PERFORMANS NVIDIA/}).click();
  await page.getByRole('button',{name:'Modu uygula'}).click();
  await expect(page.locator('.graphics-summary h2')).toHaveText('NVIDIA');
  await page.getByRole('button',{name:/Yeniden başlat/}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'Şimdi değil'}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  expect(await page.evaluate(()=>(window as any).__calls.some((x:any)=>x.action==='reboot'))).toBe(false);
  await page.getByRole('button',{name:'Bir kez ölç'}).click();
  await expect(page.getByRole('heading',{name:'NVIDIA GeForce RTX 5060'})).toBeVisible();
  await expect(page.getByText(/CANLI DEĞİL/)).toBeVisible();
  await page.screenshot({path:'/tmp/thinkbook-graphics.png',fullPage:true});
});

test('backend failure leaves the old profile selected and shows the reason',async({page})=>{
  await setup(page,true);
  await page.getByRole('button',{name:'Performans İhtiyaç duyduğun tüm güç'}).click();
  await expect(page.getByRole('alert')).toContainText('Güç servisine ulaşılamadı.');
  await expect(page.getByRole('button',{name:'Dengeli Güç ve performans dengesi'})).toHaveAttribute('aria-pressed','true');
});

test('narrow window, light theme, reduced motion, and diagnostic copy',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:800,height:650});
  await setup(page);
  await page.getByRole('button',{name:'Açık temaya geç'}).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.locator('[data-slot="bounce-sidebar-item"]').nth(3).click();
  await expect(page.getByRole('heading',{name:'Sistem.'})).toBeVisible();
  await page.getByRole('button',{name:'Tanılama bilgisini kopyala'}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__clipboard)).toContain('ThinkBook');
  expect(await page.evaluate(()=>document.querySelector('main')!.scrollWidth<=document.querySelector('main')!.clientWidth)).toBe(true);
  await page.screenshot({path:'/tmp/thinkbook-narrow-light.png',fullPage:true});
});

test('missing native connection is honest and never displays fictional metrics',async({page})=>{
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Cihaza bağlanılamadı.');
  await expect(page.locator('.energy-card')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Tekrar dene'})).toBeEnabled();
});
