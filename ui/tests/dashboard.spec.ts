import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
const snapshot = JSON.parse(readFileSync(new URL('./snapshot.json', import.meta.url), 'utf8'));

async function setup(page:Page, failPower=false, keyboardMode='available') {
  // Mimic only the Qt transport; production has no demo data or HTTP API.
  await page.route('qrc:**', route=>route.fulfill({body:'',contentType:'application/javascript'}));
  await page.addInitScript(({snapshot, failPower, keyboardMode})=>{
    const state=structuredClone(snapshot); state.cpu.usage=8;
    if(keyboardMode==='missing') state.keyboard={available:false,brightness:null,maximum:null,error:'Klavye aydınlatma servisine ulaşılamadı.'};
    if(keyboardMode==='continuous') state.keyboard={available:true,brightness:100,maximum:255,error:null};
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
          else if(action==='keyboard') {if(keyboardMode==='failure'){setTimeout(()=>reply(id,JSON.stringify({ok:false,error:'Aydınlatma seviyesi doğrulanamadı.'})),40);return;}state.keyboard.brightness=payload.brightness;data={message:'Klavye aydınlatması ayarlandı.'};}
          else if(action==='diagnostics') data={text:JSON.stringify(state)};
          else if(action==='telemetry') data={timestamp:state.timestamp,rows:[['NVIDIA GeForce RTX 5060','44','0','2','8151','595.84']]};
          else data={message:'İşlem tamamlandı.'};
          setTimeout(()=>reply(id,JSON.stringify({ok:true,data})),40);
        }};
        ready({objects:{dashboard:bridge}});
      }
    };
  },{snapshot,failPower,keyboardMode});
  await page.goto('/');
  await expect(page.locator('body')).toHaveAttribute('data-connected','true');
}

test('overview is live, power change is verified, telemetry is opt-in',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await setup(page);
  await expect(page.getByRole('heading',{name:'Genel bakış'})).toBeVisible();
  await expect(page.locator('[data-slot="animated-counter"]')).toHaveCount(1);
  await page.locator('.page-content img').evaluateAll(async images=>{
    for(const image of images as HTMLImageElement[]) await image.decode();
  });
  await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'/tmp/thinkbook-overview-docs.png'});
  await page.getByRole('button',{name:'Tasarruf'}).click();
  await expect(page.getByRole('button',{name:'Tasarruf'})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('status')).toContainText('Güç profili uygulandı');
  expect(await page.evaluate(()=>(window as any).__calls.filter((x:any)=>x.action==='telemetry').length)).toBe(0);
  await page.screenshot({path:'/tmp/thinkbook-overview.png',fullPage:true});
});

test('all graphics modes, pending reboot, and safe cancellation',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Grafik modları',exact:true}).click();
  await expect(page.getByRole('button',{name:'Modu uygula'})).toBeDisabled();
  await page.getByRole('button',{name:'Yalnızca Intel',exact:true}).click();
  await expect(page.getByText(/HDMI ve diğer harici ekran/)).toBeVisible();
  await page.getByRole('button',{name:'Modu uygula'}).click();
  await expect(page.locator('.graphics-summary h2')).toHaveText('Yalnızca Intel');
  await expect(page.getByRole('button',{name:'Modu uygula'})).toBeDisabled();
  await page.getByText('Gelişmiş seçenek',{exact:true}).click();
  await page.getByRole('button',{name:'Hesaplama',exact:true}).click();
  await page.getByRole('button',{name:'Modu uygula'}).click();
  await expect(page.locator('.graphics-summary h2')).toHaveText('Hesaplama');
  await page.getByRole('button',{name:'NVIDIA',exact:true}).click();
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
  await page.getByRole('button',{name:'Performans'}).click();
  await expect(page.getByRole('alert')).toContainText('Güç servisine ulaşılamadı.');
  await expect(page.getByRole('button',{name:'Dengeli'})).toHaveAttribute('aria-pressed','true');
});

test('narrow window, light theme, reduced motion, and diagnostic copy',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:800,height:650});
  await setup(page);
  await page.getByRole('button',{name:'Açık temaya geç'}).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await page.locator('[data-slot="bounce-sidebar-item"]').nth(3).click();
  await expect(page.getByRole('heading',{name:'Sistem'})).toBeVisible();
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

test('keyboard levels apply real steps and follow refreshed hardware readings',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Güç ve pil',exact:true}).click();
  const panel=page.getByRole('region',{name:'Klavye aydınlatması',exact:true});
  await expect(panel.getByRole('button',{name:'Düşük',exact:true})).toHaveAttribute('aria-pressed','true');
  for(const [label,level] of [['Yüksek',2],['Kapalı',0],['Düşük',1]] as const){
    await panel.getByRole('button',{name:label,exact:true}).click();
    await expect(panel.getByRole('button',{name:label,exact:true})).toHaveAttribute('aria-pressed','true');
    expect(await page.evaluate(()=>(window as any).__calls.filter((x:any)=>x.action==='keyboard').at(-1).payload)).toEqual({brightness:level});
  }
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/thinkbook-keyboard-controls.png'});
});

test('keyboard service failure and unsupported hardware never fake success',async({page})=>{
  await setup(page,false,'failure');
  await page.getByRole('button',{name:'Güç ve pil',exact:true}).click();
  const panel=page.getByRole('region',{name:'Klavye aydınlatması',exact:true});
  await panel.getByRole('button',{name:'Yüksek',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('doğrulanamadı');
  await expect(panel.getByRole('button',{name:'Düşük',exact:true})).toHaveAttribute('aria-pressed','true');
});

test('missing keyboard service disables control without hiding other settings',async({page})=>{
  await setup(page,false,'missing');
  await page.getByRole('button',{name:'Güç ve pil',exact:true}).click();
  const panel=page.getByRole('region',{name:'Klavye aydınlatması',exact:true});
  await expect(panel).toContainText('servisine ulaşılamadı');
  await expect(panel.getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Güç profili',exact:true})).toBeVisible();
});

test('higher-resolution keyboard backlights use integer slider values',async({page})=>{
  await setup(page,false,'continuous');
  await page.getByRole('button',{name:'Güç ve pil',exact:true}).click();
  await page.getByRole('slider',{name:'Parlaklık: 100 / 255'}).fill('160');
  await page.getByRole('button',{name:'Aydınlatmayı uygula',exact:true}).click();
  await expect(page.getByLabel('Geçerli aydınlatma seviyesi')).toHaveText('Seviye 160');
});

test('all redesigned pages remain usable in both themes at desktop minimum width',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});
  await setup(page);
  const tabs=['Genel bakış','Güç ve pil','Grafik modları','Sistem'];
  for(const [width,height] of [[1180,850],[760,650]]){
    await page.setViewportSize({width,height});
    for(const theme of ['dark','light']){
      if(await page.locator('html').getAttribute('data-theme')!==theme){
        await page.getByRole('button',{name:theme==='light'?'Açık temaya geç':'Koyu temaya geç'}).click();
      }
      for(let tab=0;tab<tabs.length;tab++){
        await page.getByRole('button',{name:tabs[tab],exact:true}).click();
        await expect(page.getByRole('heading',{name:tabs[tab],level:1,exact:true})).toBeVisible();
        await page.evaluate(()=>document.fonts.ready);
        await page.locator('.page-content img').evaluateAll(async images=>{for(const img of images as HTMLImageElement[])await img.decode();});
        expect(await page.locator('main').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
        const panel=page.getByRole('region',{name:'Klavye aydınlatması',exact:true});
        if(tab<2) await expect(panel.getByRole('button',{name:'Yüksek',exact:true})).toBeInViewport({ratio:1});
        await page.screenshot({path:`/tmp/thinkbook-redesign-${width}-${theme}-${tab}.png`});
      }
    }
  }
});
