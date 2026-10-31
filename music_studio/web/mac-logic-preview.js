/* Appearance prototype only. Illustrative session data; no recording,
   separation, chord-analysis, export or file-system operations are performed. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id), root=$('logic-preview');
 const paths={library:'M3 4h5v16H3Zm8 0h4v16h-4Zm7 0 3 1-2 15-3-1Z',inspector:'M3 4h18v16H3Zm6 0v16m4-12h5m-5 4h5',help:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm-2 6a2 2 0 1 1 3 2c-1 1-1 1-1 3m0 3h.01',download:'M4 4h16v16H4Zm8 2v10m-4-4 4 4 4-4',knob:'M5 9a8 8 0 1 0 14 0M12 2v10',sliders:'M5 3v18m7-18v18m7-18v18M2 8h6m1 8h6m1-10h6',pencil:'m4 17 1 4 4-1L21 8l-5-5Zm11-12 4 4',rewind:'m11 5-9 7 9 7Zm11 0-9 7 9 7Z',forward:'m2 5 9 7-9 7Zm11 0 9 7-9 7Z',stop:'M6 6h12v12H6Z',play:'m7 4 14 8L7 20Z',pause:'M6 4h4v16H6Zm8 0h4v16h-4Z',punch:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',flashback:'M4 4h16v16H4ZM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',record:'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16Z',cycle:'m5 5 3-3M5 5l3 3M5 5h10a5 5 0 0 1 5 5m-1 9-3 3m3-3-3-3m3 3H9a5 5 0 0 1-5-5',metronome:'m8 3-5 18h18L16 3ZM8 16l9-9M7 3h10',list:'M8 5h13M8 12h13M8 19h13M3 5h.1M3 12h.1M3 19h.1',note:'M4 3h16v18H4Zm4 5h8m-8 4h8m-8 4h5',loops:'M17 18h3V8a8 8 0 0 0-16 0v10h3V9m10 0v9m-5 3h5',browser:'M3 4h7l2 3h9v13H3Z',grid:'M3 4h18v16H3Zm6 0v16m6-16v16M3 10h18m-18 5h18',tracks:'M3 5h5v4H3Zm8 0h10v4H11ZM3 15h5v4H3Zm8 0h10v4H11Z',automation:'M2 17h5l7-10h8M6 15v4m7-14v4',wave:'M2 12h3l3-7 4 14 4-14 3 7h3',flex:'m3 3 4 9-4 9m18-18-4 9 4 9M9 12h6',pointer:'m5 3 3 17 4-6 7-2Z',marquee:'M12 3v18M3 12h18',scissors:'M6 13a4 4 0 1 0 0 8 4 4 0 1 0 0-8Zm12 0a4 4 0 1 0 0 8 4 4 0 1 0 0-8ZM4 2l14 14M20 2 6 16',vocal:'M9 4a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0Zm-3 6v1a6 6 0 0 0 12 0v-1m-6 7v5m-4 0h8',drums:'M3 9c0-4 18-4 18 0s-18 4-18 0Zm0 0v8c0 4 18 4 18 0V9M4 3l8 4m8-4-8 4',bass:'m14 8 6-6 2 2-6 6m-2-2-2 2C5 7 1 17 6 21s12-1 9-8l2-3M8 14l3 3',piano:'M3 12h18v4H3Zm2 4v6m14-6v6M6 12V7L18 2l2 1v9M6 7h14',guitar:'m14 8 6-6 2 2-6 6m-2-2-2 2C5 7 1 17 6 21s12-1 9-8l2-3M8 14l3 3',strings:'m15 3-9 15m14-15L10 21m2-16c-6 0-9 10-5 13s10-3 8-7l-3-6Z',brass:'m3 14 14-7 4-5v17l-4-5-14 4Zm5-3V6h3v4m1-3V3h3v4',synth:'M2 5h20v14H2Zm4 0v14m4-14v14m4-14v14m4-14v14M8 5v8m4-8v8m4-8v8'};
 // Top-bar glyphs use a separate catalogue: updating toolbar artwork must not
 // change instrument drawings or editor tools. Independently authored SVGs.
 const controlIcons={
  library:'<path d="M5 17H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v2"/><rect class="icon-fill" x="7" y="8" width="14" height="13" rx="1.5"/><path class="icon-cutout" d="M13 17v-5l5-1v5m-5-2 5-1"/><ellipse class="icon-cutout icon-fill" cx="11.5" cy="17.5" rx="2" ry="1.5"/><ellipse class="icon-cutout icon-fill" cx="16.5" cy="16.5" rx="2" ry="1.5"/>',
  inspector:'<rect x="3.5" y="4" width="17" height="6" rx="3"/><rect x="3.5" y="14" width="17" height="6" rx="3"/><circle class="icon-fill" cx="7" cy="7" r="2"/><circle class="icon-fill" cx="17" cy="17" r="2"/>',
  help:'<circle cx="12" cy="12" r="8.5"/><path d="M9.5 8.8a2.5 2.5 0 0 1 5 .2c0 2-2.5 2-2.5 4.2"/><circle class="icon-fill" cx="12" cy="16.6" r=".9"/>',
  download:'<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 8h18m-9 2v7m-3-3 3 3 3-3"/>',
  dial:'<circle cx="12" cy="13" r="5.5"/><path d="M12 7.5V13M12 2v2M4 5l1.5 1.5M2 13h2m16 0h2M20 5l-1.5 1.5M5 21l1-1m13 1-1-1"/>',
  mixer:'<path d="M5 3v4m0 5v9M12 3v10m0 5v3M19 3v2m0 5v11"/><rect x="3" y="7" width="4" height="5" rx=".8"/><rect x="10" y="13" width="4" height="5" rx=".8"/><rect x="17" y="5" width="4" height="5" rx=".8"/>',
  pencil:'<path class="icon-fill" d="m5 16 11-11 3 3L8 19l-4 1 1-4Zm12-12 1-1c.6-.6 1.4-.6 2 0l1 1c.6.6.6 1.4 0 2l-1 1-3-3Z"/>',
  punch:'<circle class="icon-fill" cx="12" cy="12" r="4"/><path d="M5.3 7.2a8.3 8.3 0 0 1 4.3-3.1m4.8 0a8.3 8.3 0 0 1 4.3 3.1m1.5 4.6a8.3 8.3 0 0 1-1.7 5.1m-3.8 2.8a8.3 8.3 0 0 1-5.4 0m-3.8-2.8a8.3 8.3 0 0 1-1.7-5.1"/>',
  capture:'<rect x="5" y="3" width="14" height="18" rx="1"/><circle class="icon-fill" cx="12" cy="12" r="3"/>',
  cycle:'<path d="M4 10V9a3 3 0 0 1 3-3h12m-3-3 3 3-3 3M20 14v1a3 3 0 0 1-3 3H5m3-3-3 3 3 3"/>',
  tuner:'<g transform="rotate(38 12 12)"><path d="M8 3v6a4 4 0 0 0 8 0V3m-4 10v8"/></g>',
  metronome:'<path d="m9 3-5 17h16L15 3ZM5 17h14m-9-2L18 5"/><path d="m15.5 5.5 2 2"/>',
  list:'<path d="M8 6h13M8 12h13M8 18h13"/><circle class="icon-fill" cx="3.5" cy="6" r="1"/><circle class="icon-fill" cx="3.5" cy="12" r="1"/><circle class="icon-fill" cx="3.5" cy="18" r="1"/>',
  notes:'<rect x="4" y="3.5" width="16" height="17" rx="1"/><path d="M7 7.5h10M7 11h10M7 14.5h10M7 18h6"/>',
  loops:'<path d="M8 19H3m13 0h5M7 19C3 16 3 8 7 5c3-2 7-2 10 0 4 3 4 11 0 14"/>',
  media:'<path d="M13 7V3H3v13h3M3 7h10"/><rect x="7" y="9" width="9" height="11" rx="1"/><path class="icon-fill" d="m10 12 4 2.5-4 2.5Z"/><path d="M20 19V9l3 1v7"/><ellipse class="icon-fill" cx="18.5" cy="19.5" rx="2" ry="1.5"/><ellipse class="icon-fill" cx="21.5" cy="17.5" rx="2" ry="1.5"/>'
 };
 const svg=name=>{
  const control=name.startsWith('control-')?controlIcons[name.slice(8)]:null;
  return '<svg viewBox="0 0 24 24" aria-hidden="true"'+(control?' class="control-symbol symbol-'+name.slice(8)+'"':'')+'>'+(control||'<path d="'+(paths[name]||paths.wave)+'"/>')+'</svg>';
 };
 const button=(icon,label,cls='')=>{const b=document.createElement('button');b.type='button';b.title=label;b.setAttribute('aria-label',label);b.className=cls;b.innerHTML=svg(icon);return b;};
 function group(id,items){for(const [icon,label,cls]of items)$(id).append(button(icon,label,cls||''));}
 group('navigation-tools',[['control-library','Library'],['control-inspector','Inspector'],['control-help','Quick help'],['control-download','Sound library']]);
 group('workspace-tools',[['control-dial','Smart controls'],['control-mixer','Mixer'],['control-pencil','Editors']]);
 $('workspace-tools').lastChild.setAttribute('aria-pressed','true');
 group('transport',[['stop','Stop'],['play','Play','play'],['record','Record appearance','record'],['control-punch','Punch recording appearance','record-outline'],['control-capture','Capture appearance','capture'],['control-cycle','Cycle']]);
 group('monitoring-tools',[['control-tuner','Tuner']]);
 const solo=document.createElement('button');solo.type='button';solo.innerHTML='<span class="solo-symbol" aria-hidden="true">S</span>';solo.title='Solo appearance';solo.setAttribute('aria-label',solo.title);$('monitoring-tools').append(solo);
 const count=document.createElement('button');count.type='button';count.className='count-in';count.textContent='1234';count.title='Count-in appearance';count.setAttribute('aria-label',count.title);$('tempo-tools').append(count);
 group('tempo-tools',[['control-metronome','Metronome appearance','purple']]);
 group('browser-tools',[['control-list','List editors'],['control-notes','Notes'],['control-loops','Loops'],['control-media','Browsers']]);
 group('view-tools',[['grid','Live Loops appearance'],['tracks','Tracks appearance'],['automation','Automation appearance'],['wave','Flex appearance'],['flex','Track alternatives appearance']]);$('view-tools').children[1].setAttribute('aria-pressed','true');
 group('display-tools',[['wave','Waveform display appearance'],['flex','Vertical auto zoom appearance'],['grid','Horizontal auto zoom appearance']]);
 group('pointer-tools',[['pointer','Pointer tool'],['marquee','Secondary tool']]);group('editor-tools',[['automation','Editor automation appearance'],['wave','Flex editor appearance'],['flex','Editor view appearance']]);group('editor-heading-tools',[['pointer','Editor pointer tool'],['pencil','Editor pencil tool']]);
 // The production host supplies real session data before sample data exists.
 if(window.BlazeLogicHost){window.BlazeLogicLiveMount({root,svg,button});return;}
 const tracks=[
 {name:'Lead Vocal',icon:'vocal',color:'#2daec0',region:'#218b9c',seed:1,clips:[[0,8],[8,8],[16,8],[24,8]]},
 {name:'Drum Kit',icon:'drums',color:'#4b9dd8',region:'#287ea9',seed:2,clips:[[0,8],[8,8],[16,8],[24,8]]},
 {name:'Bass',icon:'bass',color:'#7f7edb',region:'#534ea6',seed:3,clips:[[0,8],[8,8],[16,8],[24,8]]},
 {name:'Piano',icon:'piano',color:'#ba94e0',region:'#7353ad',seed:4,clips:[[0,8],[8,8],[16,8],[24,8]]},
 {name:'Acoustic Guitar',icon:'guitar',color:'#60bfd4',region:'#2a8da5',seed:5,clips:[[0,12],[16,8],[24,8]]},
 {name:'Strings',icon:'strings',color:'#58c6b3',region:'#258e83',seed:6,clips:[[4,12],[20,12]]},
 {name:'Brass',icon:'brass',color:'#91a5e0',region:'#536da9',seed:7,clips:[[8,8],[24,8]]},
 {name:'Synth Pad',icon:'synth',color:'#8f80dc',region:'#6650a3',seed:8,clips:[[0,16],[16,16]]},
 {name:'Ambience',icon:'wave',color:'#84a1b8',region:'#4e708d',seed:9,clips:[[0,32]]}
 ];
 let selected=3,playhead=.25,playing=false,frame=0,last=0;
 function ruler(id,start,count,step=1){const r=$(id);for(let n=0;n<count;n+=step){const s=document.createElement('span');s.style.left=(n/count*100)+'%';s.textContent=String(start+n);r.append(s);}}
 ruler('project-ruler',1,32,2);ruler('editor-ruler',5,16,2);
 for(const name of ['C','Am7(11)','Fsus2','Gadd11','C','Am7(11)','Fsus2','Gadd11']){const s=document.createElement('span');s.textContent=name;$('chord-lane').append(s);}
 function select(index){selected=index;for(const [n,h]of [...$('track-headers').children].entries()){h.classList.toggle('selected',n===index);h.setAttribute('aria-selected',String(n===index));}for(const clip of $('regions').querySelectorAll('.clip'))clip.classList.toggle('selected',Number(clip.dataset.track)===index);$('editor-track').textContent=tracks[index].name;$('editor-caption').textContent=tracks[index].name;drawAll();}
 tracks.forEach((track,index)=>{
  const header=document.createElement('div');header.className='track-header';header.tabIndex=0;header.setAttribute('role','option');header.setAttribute('aria-label',track.name);header.style.setProperty('--track-color',track.color);
  header.innerHTML='<span class="track-number">'+(index+1)+'</span><span class="instrument">'+svg(track.icon)+'</span><div class="track-info"><span class="track-name">'+track.name+'</span><div class="track-controls"><button aria-label="Mute '+track.name+'" aria-pressed="false">M</button><button aria-label="Solo '+track.name+'" aria-pressed="false">S</button><button class="arm" aria-label="Record-enable appearance for '+track.name+'">R</button><button class="monitor" aria-label="Input-monitoring appearance for '+track.name+'">I</button><span class="track-level" style="--level:'+(index%3?42:63)+'%"><i></i></span><span class="pan"></span></div></div>';
  header.onclick=()=>select(index);header.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(index);}};
  for(const b of header.querySelectorAll('button'))b.onclick=e=>{e.stopPropagation();b.setAttribute('aria-pressed',String(b.getAttribute('aria-pressed')!=='true'));};$('track-headers').append(header);
  const row=document.createElement('div');row.className='region-row';row.style.setProperty('--region-color',track.region);
  for(const [start,length]of track.clips){const clip=document.createElement('div');clip.className='clip';clip.dataset.track=String(index);clip.style.left=(start/32*100)+'%';clip.style.width=(length/32*100)+'%';clip.innerHTML='<div class="clip-name"></div><canvas aria-label="Illustrative waveform for '+track.name+'"></canvas>';clip.firstChild.textContent=track.name;clip.onclick=()=>select(index);clip.querySelector('canvas').dataset.seed=String(track.seed);row.append(clip);}$('regions').append(row);
 });
 $('track-headers').setAttribute('role','listbox');
 function draw(canvas,seed,stereo=false){const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;const d=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(rect.width*d);canvas.height=Math.round(rect.height*d);const g=canvas.getContext('2d');g.scale(d,d);const w=rect.width,h=rect.height,channels=stereo?2:1;g.strokeStyle='#ffffff12';g.lineWidth=1;
  for(let n=0;n<=16;n++){const x=n*w/16;g.beginPath();g.moveTo(x,0);g.lineTo(x,h);g.stroke();}
  for(let c=0;c<channels;c++){const center=h/channels*(c+.5),amp=h/channels*.47;g.strokeStyle='#bddcf044';g.beginPath();g.moveTo(0,center);g.lineTo(w,center);g.stroke();g.fillStyle=stereo?'#c0def5':'#bce2f8';g.beginPath();
   function peak(x){const t=x/w,phrase=.13+.65*Math.pow(Math.max(0,Math.sin(t*23.4+seed)),2),beat=Math.exp(-((t*14+seed*.12)%1)*8),grain=.55+.45*Math.abs(Math.sin(x*1.17+seed)*Math.cos(x*.51+c));return Math.min(1,Math.max(.005,(.12+phrase*.85+beat*.65)*grain))*amp;}
   for(let x=0;x<=w;x++)g.lineTo(x,center-peak(x));for(let x=w;x>=0;x--)g.lineTo(x,center+peak(x)*(.75+.2*Math.sin(x*.03+seed)));g.closePath();g.fill();
  }
 }
 function drawAll(){for(const c of $('regions').querySelectorAll('canvas'))draw(c,Number(c.dataset.seed));draw($('editor-wave'),tracks[selected].seed,true);}
 function paint(){ $('project-playhead').style.left=(playhead*100)+'%';$('editor-playhead').style.left=(playhead*100)+'%';const bar=Math.floor(playhead*32)+1;$('position-bar').textContent=String(bar);$('position-padding').textContent=bar<10?'00':'0';const time=playhead*64;$('visual-time').textContent=String(Math.floor(time/60)).padStart(2,'0')+':'+String(Math.floor(time%60)).padStart(2,'0')+'.'+String(Math.floor(time%1*1000)).padStart(3,'0'); }
 function tick(now){if(!playing)return;if(last)playhead=(playhead+(now-last)/64000)%1;last=now;paint();frame=requestAnimationFrame(tick);}
 const play=$('transport').querySelector('.play');play.onclick=()=>{playing=!playing;play.innerHTML=svg(playing?'pause':'play');play.setAttribute('aria-label',playing?'Pause':'Play');last=0;cancelAnimationFrame(frame);if(playing)frame=requestAnimationFrame(tick);};
 $('transport').children[0].onclick=()=>{playing=false;cancelAnimationFrame(frame);playhead=0;play.innerHTML=svg('play');paint();};
 for(const i of [2,3,4])$('transport').children[i].disabled=true;
 for(const b of [$('transport').lastChild,...$('timing-tools').querySelectorAll('button')])b.onclick=()=>b.setAttribute('aria-pressed',String(b.getAttribute('aria-pressed')!=='true'));
 $('show-editor').onclick=()=>{const hide=root.classList.toggle('editor-hidden');for(const node of [$('show-editor'),$('workspace-tools').lastChild])node.setAttribute('aria-pressed',String(!hide));requestAnimationFrame(drawAll);};
 $('workspace-tools').lastChild.onclick=()=>$('show-editor').click();
 $('project-ruler').onclick=e=>{const r=e.currentTarget.getBoundingClientRect();playhead=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));paint();};
 document.querySelector('[aria-label="Track visual height"]').oninput=e=>{root.style.setProperty('--row-height',e.target.value+'px');drawAll();};
 const menus={edit:['Undo','Redo','Cut','Copy','Paste','Delete'],functions:['Region settings','Track settings','Project settings'],view:['Show Library','Show Inspector','Show Editors','Show Mixer']};
 for(const b of document.querySelectorAll('[data-menu]'))b.onclick=()=>{const menu=$('appearance-menu'),r=b.getBoundingClientRect();menu.replaceChildren();for(const label of menus[b.dataset.menu.replace('editor-','')]){const item=document.createElement('button');item.textContent=label;item.onclick=()=>{menu.hidden=true;};menu.append(item);}menu.style.left=r.left+'px';menu.style.top=r.bottom+4+'px';menu.hidden=false;};
 document.addEventListener('keydown',e=>{if(e.key==='Escape')$('appearance-menu').hidden=true;});document.addEventListener('pointerdown',e=>{if(!e.target.closest('[data-menu],#appearance-menu'))$('appearance-menu').hidden=true;});
 const observer=new ResizeObserver(drawAll);observer.observe(root);window.addEventListener('pagehide',()=>{observer.disconnect();cancelAnimationFrame(frame);},{once:true});select(3);paint();
 window.BlazeLogicVisual={scope:'visual-only',versionReference:'Logic Pro 12.4 current App Store screenshots',redraw:drawAll};
})();
