const AS='/fishing-assets/';
const locations=[
{id:'quiet',name:'Тихая заводь',img:'backgrounds/quiet.svg',weather:'🌤 Ясно',time:'🌅 Рассвет',fish:['pike','perch','crucian','roach','carp'],bonus:'Крупный карп'},
{id:'forest',name:'Лесное озеро',img:'backgrounds/forest.svg',weather:'🌤 Прохладно',time:'☀️ День',fish:['pike','perch','carp','tench','bream'],bonus:'Эпический карп'},
{id:'river',name:'Большая река',img:'backgrounds/river.svg',weather:'☁️ Облачно',time:'🌇 Вечер',fish:['zander','asp','catfish','bream','chub'],bonus:'Судак-хищник'},
{id:'mountain',name:'Горное озеро',img:'backgrounds/mountain.svg',weather:'🌫 Туман',time:'☀️ День',fish:['trout','taimen','perch'],bonus:'Горная форель'},
{id:'deep',name:'Глубокая вода',img:'backgrounds/deep.svg',weather:'🌙 Ночь',time:'🌙 Ночь',fish:['catfish','taimen','beluga','burbo'],bonus:'Легендарный сом'}];
const fish={
pike:{name:'Щука',img:'fish_clean/pike.jpg?v=4',trophy:'fish_clean/pike.jpg?v=4',rarity:'Редкая',min:.8,max:8.8,power:78,value:320,xp:55},perch:{name:'Окунь',img:'fish_clean/perch.jpg?v=4',rarity:'Обычная',min:.15,max:2.1,power:35,value:90,xp:24},crucian:{name:'Карась',img:'fish_clean/crucian.jpg?v=4',rarity:'Обычная',min:.12,max:1.8,power:28,value:70,xp:22},roach:{name:'Плотва',img:'fish_clean/roach.jpg?v=4',rarity:'Обычная',min:.08,max:1.3,power:22,value:55,xp:18},carp:{name:'Карп',img:'fish_clean/carp.jpg?v=4',trophy:'fish_clean/carp.jpg?v=4',rarity:'Эпическая',min:1.5,max:12,power:82,value:620,xp:95},tench:{name:'Линь',img:'fish_clean/tench.jpg?v=4',rarity:'Необычная',min:.3,max:3.4,power:48,value:180,xp:42},bream:{name:'Лещ',img:'fish_clean/bream.jpg?v=4',rarity:'Необычная',min:.4,max:4.8,power:55,value:210,xp:46},zander:{name:'Судак',img:'fish_clean/zander.jpg?v=4',rarity:'Редкая',min:.7,max:6.2,power:68,value:390,xp:62},asp:{name:'Жерех',img:'fish_clean/asp.jpg?v=4',rarity:'Редкая',min:.8,max:5.6,power:64,value:360,xp:58},catfish:{name:'Сом',img:'fish_clean/catfish.jpg?v=4',trophy:'fish_clean/catfish.jpg?v=4',rarity:'Легендарная',min:3,max:25,power:96,value:1250,xp:170},chub:{name:'Голавль',img:'fish_clean/chub.jpg?v=4',rarity:'Необычная',min:.4,max:3.5,power:51,value:200,xp:44},burbo:{name:'Налим',img:'fish_clean/burbo.jpg?v=4',rarity:'Редкая',min:.6,max:5.8,power:62,value:410,xp:68},trout:{name:'Форель',img:'fish_clean/trout.jpg?v=4',trophy:'fish_clean/trout.jpg?v=4',rarity:'Эпическая',min:.5,max:6,power:73,value:700,xp:105},taimen:{name:'Таймень',img:'fish_clean/taimen.jpg?v=4',trophy:'fish_clean/taimen.jpg?v=4',rarity:'Легендарная',min:2,max:18,power:91,value:1600,xp:220},beluga:{name:'Белуга',img:'fish_clean/beluga.jpg?v=4',rarity:'Мифическая',min:8,max:35,power:100,value:3000,xp:350}};
const gear=[
{id:'starter',img:'gear/rod_starter.png',name:'Простая удочка',price:0,control:8,power:0,level:0},
{id:'float',img:'gear/rod_float.png',name:'Поплавочная',price:250,control:16,power:5,level:2},
{id:'spin',img:'gear/rod_spinning.png',name:'Спиннинг',price:600,control:12,power:20,level:3},
{id:'feeder',img:'gear/rod_feeder.png',name:'Фидер',price:950,control:24,power:14,level:4},
{id:'carp',img:'gear/rod_carp.png',name:'Карповик',price:1500,control:18,power:35,level:6},
{id:'premium',img:'gear/rod_premium.png',name:'Таймень Pro',price:3000,control:28,power:48,level:9}];
const baits=[['worm.png','Червь',0],['maggots.png','Опарыш',50],['corn.png','Кукуруза',70],['bread.png','Хлеб',40],['livebait.png','Живец',160],['fly.png','Мушка',180],['wobbler.png','Воблер',240],['spinner.png','Блесна',220],['softbait.png','Силикон',200]];
const achievements=[
{id:'first',icon:'🐟',name:'Первая рыба',desc:'Поймать первую рыбу',ok:s=>s.caught>=1,reward:100},
{id:'ten',icon:'🎣',name:'Рыбак',desc:'Поймать 10 рыб',ok:s=>s.caught>=10,reward:250},
{id:'collector',icon:'🗃️',name:'Коллекционер',desc:'Открыть 10 видов',ok:s=>Object.keys(s.inventory).length>=10,reward:500},
{id:'big',icon:'⚖️',name:'Тяжеловес',desc:'Поймать рыбу 10+ кг',ok:s=>s.best>=10,reward:700},
{id:'legend',icon:'👑',name:'Легенда',desc:'Поймать легендарную рыбу',ok:s=>s.legendary>=1,reward:1000},
{id:'night',icon:'🌙',name:'Ночной охотник',desc:'Поймать рыбу ночью',ok:s=>s.nightCatches>=1,reward:400}];
const events=[
{name:'🌅 Золотой рассвет',desc:'Редкая рыба активнее',bonus:1.18},
{name:'🌧 Тёплый дождь',desc:'Поклёвка происходит быстрее',bonus:1.12},
{name:'🌫 Таинственный туман',desc:'Шанс на редкий улов повышен',bonus:1.25},
{name:'🌙 Ночная охота',desc:'Открываются глубоководные трофеи',bonus:1.35}];
const defaults={loc:0,diamonds:1250,xp:0,level:1,phase:'idle',fish:null,fishPower:0,line:36,rod:'starter',rodLevels:{starter:1},bait:0,caught:0,best:0,inventory:{},owned:['starter'],lastCatch:null,weatherIndex:0,legendary:0,nightCatches:0,unlockedAchievements:[],event:null,eventUntil:0};
let state={...defaults};
const $=id=>document.getElementById(id);const scene=$('scene');
function save(){localStorage.setItem('maruskaFishingV3',JSON.stringify(state));}
function load(){try{const s=JSON.parse(localStorage.getItem('maruskaFishingV3'));if(s)state={...defaults,...s,rodLevels:{...defaults.rodLevels,...(s.rodLevels||{})}}}catch{}}
function toast(t){const e=$('toast');e.textContent=t;e.classList.add('show');clearTimeout(window.__toast);window.__toast=setTimeout(()=>e.classList.remove('show'),2100)}
function levelNeed(l){return 120+(l-1)*85}
function levelProgress(){let n=levelNeed(state.level);return Math.min(100,Math.round(state.xp/n*100))}
function addXP(amount){state.xp+=amount;let leveled=false;while(state.xp>=levelNeed(state.level)){state.xp-=levelNeed(state.level);state.level++;leveled=true}if(leveled){toast('✨ Новый уровень: '+state.level);checkAchievements()}}
function currentEvent(){if(state.event && Date.now()<state.eventUntil)return state.event;return null}
function rollEvent(){const e=events[Math.floor(Math.random()*events.length)];state.event=e;state.eventUntil=Date.now()+90000;toast(e.name+' • '+e.desc);render()}
function render(){const l=locations[state.loc];scene.style.backgroundImage=`url('${AS+l.img}')`;scene.classList.toggle('is-casting',state.phase==='waiting'||state.phase==='bite');scene.classList.toggle('is-fighting',state.phase==='fight');scene.classList.toggle('is-broken',state.phase==='idle'&&$('statusPill').textContent.includes('порвалась'));const rv=$('rodVisual');if(rv){rv.src=AS+getRod().img;}$('locationName').textContent=l.name;$('weather').textContent=l.weather;$('time').textContent=l.time;$('diamonds').textContent=state.diamonds.toLocaleString('ru-RU');$('locationDots').innerHTML=locations.map((_,i)=>`<i class="${i===state.loc?'active':''}"></i>`).join('');$('rain').classList.toggle('on',l.weather.includes('Дожд'));document.body.dataset.time=l.time;let badge=document.getElementById('levelBadge');if(!badge){badge=document.createElement('button');badge.id='levelBadge';badge.className='level-badge';$('statusPill').after(badge);badge.onclick=()=>showProgress()}badge.innerHTML=`⭐ Ур. ${state.level} <span>${levelProgress()}%</span>`;let ev=currentEvent();let ec=document.getElementById('eventChip');if(!ec){ec=document.createElement('button');ec.id='eventChip';ec.className='event-chip';$('weatherBtn').after(ec);ec.onclick=()=>rollEvent()}ec.textContent=ev?ev.name:'✨ Событие';ec.classList.toggle('active',!!ev)}
function setLocation(i){if(state.phase!=='idle'){toast('Сначала закончи текущую рыбалку');return}if(state.level<locations[i].level){toast('🔒 Нужен уровень '+locations[i].level);return}state.loc=(i+locations.length)%locations.length;render();save()}
locations[0].level=1;locations[1].level=2;locations[2].level=4;locations[3].level=6;locations[4].level=9;
function chooseFish(){const l=locations[state.loc];let pool=[...l.fish];const night=state.loc===4||l.time.includes('Ночь');const ev=currentEvent();if(night&&Math.random()<.08)pool=['beluga'];if(Math.random()<.1&&pool.includes('carp'))pool.push('carp');if(ev&&ev.name.includes('Таинственный')&&Math.random()<.18)pool=pool.filter(k=>fish[k].rarity!=='Обычная').length?pool.filter(k=>fish[k].rarity!=='Обычная'):pool;if(night&&Math.random()<.25)state.nightCatches++;return pool[Math.floor(Math.random()*pool.length)]}
function getRod(){const g=gear.find(g=>g.id===state.rod)||gear[0];const lv=state.rodLevels[state.rod]||1;return {...g,control:g.control+(lv-1)*3,power:g.power+(lv-1)*4,upgrade:lv}}
function continueCast(){if(state.phase!=='catch')return;state.phase='idle';state.fish=null;$('catchCard').classList.add('hidden');$('fightCard').classList.add('hidden');$('biteCard').classList.add('hidden');FX.reset();$('castBtn').classList.remove('hidden');$('statusPill').textContent='Готов к забросу';scene.classList.remove('is-casting','is-fighting','is-broken');render();v4save?.();save();try{window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')}catch{}}
function cast(){if(state.phase!=='idle')return;if(state.level>=2&&Math.random()<.13)rollEvent();state.phase='waiting';$('castBtn').classList.add('hidden');$('statusPill').textContent='🎣 Заброс...';scene.classList.add('is-casting');
  FX.cast().then(()=>{if(state.phase==='waiting')$('statusPill').textContent='👀 Ждём поклёвку...'});
  const ev=currentEvent();const delay=1000+(ev&&ev.name.includes('дождь')?700:1200)+Math.random()*2600;
  setTimeout(()=>{if(state.phase!=='waiting')return;state.phase='bite';$('statusPill').textContent='⚡ ПОКЛЁВКА!';$('biteCard').classList.remove('hidden');FX.bite();try{window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('heavy')}catch{}},delay)}
function hook(){if(state.phase!=='bite')return;scene.classList.remove('is-casting');scene.classList.add('is-fighting');const key=chooseFish();state.fish=key;state.fishPower=fish[key].power;state.line=30;state.phase='fight';$('biteCard').classList.add('hidden');$('fightCard').classList.remove('hidden');FX.hook();$('fightFishImage').src=AS+fish[key].img;$('fishName').textContent=fish[key].name;$('rarity').textContent=fish[key].rarity;$('statusPill').textContent='🐟 Вываживай!';updateFight()}
function updateFight(){const p=Math.round(state.fishPower),l=Math.round(state.line);$('fishPower').style.width=p+'%';$('fishPowerText').textContent=p+'%';$('linePower').style.width=l+'%';$('lineText').textContent=l+'%';$('fightCard').style.setProperty('--strain',l+'%');FX.tension(l)}
function fight(type){if(state.phase!=='fight')return;const rod=getRod();let damage=0,line=0;if(type==='pull'){damage=9+Math.random()*8+rod.power*.08;line=8+Math.random()*11-rod.control*.12}else if(type==='relax'){damage=1+Math.random()*3;line=-(12+Math.random()*15+rod.control*.16)}else{damage=5+Math.random()*7+rod.power*.05;line=3+Math.random()*7-rod.control*.1}const surge=Math.random()<(0.22+(state.fishPower>75?.08:0))?8+Math.random()*20:0;state.fishPower=Math.max(0,state.fishPower-damage+surge);state.line=Math.min(100,Math.max(0,state.line+line));if(type==='pull')FX.jerk();if(surge){state.line=Math.min(100,state.line+surge*.25);FX.jerk();toast('🐟 Резкий рывок!')}updateFight();if(state.line>=100)return fail();if(state.fishPower<=0)return catchFish();clearTimeout(window.__fightTick);window.__fightTick=setTimeout(()=>{if(state.phase!=='fight')return;state.line=Math.min(100,state.line+Math.random()*4.5);if(Math.random()<.15)state.fishPower=Math.min(100,state.fishPower+4);updateFight();if(state.line>=100)fail()},260)}
function fail(){scene.classList.remove('is-casting','is-fighting');scene.classList.add('is-broken');state.phase='idle';$('fightCard').classList.add('hidden');FX.snap();$('castBtn').classList.remove('hidden');$('statusPill').textContent='💥 Леска порвалась';toast('Рыба ушла...');setTimeout(()=>$('statusPill').textContent='Готов к забросу',1500);save()}
function catchFish(){scene.classList.remove('is-casting','is-fighting');const key=state.fish,f=fish[key];let w=f.min+Math.random()*(f.max-f.min);const ev=currentEvent();const trophy=Math.random()<(0.07*(ev?ev.bonus:1))&&f.trophy;if(trophy)w=Math.min(f.max,w*1.2);w=+w.toFixed(2);const len=Math.round(22+w*8+Math.random()*14);const reward=Math.round(f.value*(trophy?2.4:1)*(1+state.loc*.08)*(ev?ev.bonus:1));state.caught++;state.inventory[key]=(state.inventory[key]||0)+1;state.diamonds+=reward;state.best=Math.max(state.best,w);if(f.rarity==='Легендарная'||f.rarity==='Мифическая')state.legendary++;state.lastCatch={key,w,len,reward,trophy};addXP(f.xp+(trophy?Math.round(f.xp*.7):0));checkAchievements();state.phase='catch';$('fightCard').classList.add('hidden');FX.reset();$('catchImage').src=AS+(trophy?f.trophy:f.img);$('catchName').textContent=f.name;$('catchRarity').textContent=trophy?'👑 ТРОФЕЙНЫЙ • '+f.rarity:f.rarity;$('catchWeight').textContent=w.toFixed(2)+' кг';$('catchLength').textContent=len+' см';$('catchReward').textContent='+'+reward;$('catchCard').classList.remove('hidden');$('catchCard').classList.toggle('trophy',!!trophy);$('statusPill').textContent=trophy?'👑 ТРОФЕЙНЫЙ УЛОВ!':'🎉 Рыба поймана!';$('fishJump').style.backgroundImage=`url('${AS+f.img}')`;$('fishJump').style.display='block';$('fishJump').animate([{transform:'translate(-50%,0) scale(.6)',opacity:0},{transform:'translate(-50%,-100px) rotate(-12deg) scale(1)',opacity:1},{transform:'translate(-50%,20px) rotate(14deg) scale(.75)',opacity:0}],{duration:900,easing:'cubic-bezier(.2,.8,.2,1)'}).finished.then(()=>{$('fishJump').style.display='none'});render();save();
  if(window.FishingSecure){ const requestId=(crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random()); window.FishingSecure.catch({fish_key:key,weight:w,request_id:requestId}).catch(()=>{}); }
  FishingBackend.save().catch(()=>{});
}
function checkAchievements(){achievements.forEach(a=>{if(!state.unlockedAchievements.includes(a.id)&&a.ok(state)){state.unlockedAchievements.push(a.id);state.diamonds+=a.reward;toast(a.icon+' Достижение: '+a.name+'  +'+a.reward+' 💎')}});save()}
function showProgress(){const m=$('modal'),c=$('modalContent');c.innerHTML=`<div class="level-hero"><span>⭐ УРОВЕНЬ</span><b>${state.level}</b><div class="track"><i style="width:${levelProgress()}%"></i></div><small>${state.xp} / ${levelNeed(state.level)} XP</small></div><h2>Прогресс</h2><p class="muted">Новые водоёмы и снасти открываются по уровню.</p><button class="primary full" id="achBtn">🏆 Достижения</button>`;m.classList.remove('hidden');$('achBtn').onclick=()=>{m.classList.add('hidden');openPanel('collection')}}
function openPanel(tab){const title=$('panelTitle'),content=$('panelContent');if(tab==='gear'){title.textContent='🎒 Снасти и магазин';content.innerHTML=`<div class="balance">⭐ Ур. ${state.level} • 💎 ${state.diamonds.toLocaleString('ru-RU')}</div><div class="section-title">Удочки</div><div class="grid">${gear.map(g=>{const lv=state.rodLevels[g.id]||1;const locked=state.level<g.level;return `<button class="item ${state.rod===g.id?'selected':''}" data-rod="${g.id}" data-gear="1"><img src="${AS+g.img}"><h3>${g.name}</h3><p>Контроль +${g.control+(lv-1)*3} • Сила +${g.power+(lv-1)*4}</p><b>${locked?'🔒 Ур. '+g.level:state.owned.includes(g.id)?(state.rod===g.id?'ЭКИПИРОВАНО':'ЭКИПИРОВАТЬ'):(g.price?g.price.toLocaleString('ru-RU')+' 💎':'БЕСПЛАТНО')}</b></button>`}).join('')}</div><div class="section-title">Прокачка экипированной</div><div class="upgrade-card"><b>${getRod().name} • ур. ${getRod().upgrade}</b><span>+3 контроль / +4 сила за уровень</span><button class="primary small" id="upgradeRod">Прокачать · ${Math.round(180*getRod().upgrade)} 💎</button></div><div class="section-title">Наживка</div><div class="bait-row">${baits.map((b,i)=>`<button class="bait ${state.bait===i?'selected':''}" data-bait="${i}"><img src="${AS+'baits/'+b[0]}"><span>${b[1]}</span></button>`).join('')}</div>`;content.querySelectorAll('[data-rod]').forEach(b=>b.onclick=()=>buyRod(b.dataset.rod));content.querySelectorAll('[data-bait]').forEach(b=>b.onclick=()=>{state.bait=+b.dataset.bait;save();openPanel('gear')});$('upgradeRod').onclick=upgradeRod}
else if(tab==='collection'){title.textContent='🐟 Улов и достижения';const unlocked=state.unlockedAchievements.length;content.innerHTML=`<div class="stats-row"><div><b>${state.caught}</b><span>рыб</span></div><div><b>${Object.keys(state.inventory).length}/15</b><span>видов</span></div><div><b>${state.best.toFixed(2)} кг</b><span>рекорд</span></div></div><div class="section-title">Коллекция рыб</div><div class="grid">${Object.entries(fish).map(([k,f])=>{const caught=state.inventory[k]||0;return `<div class="item" data-rarity="${f.rarity}"><img src="${AS+f.img}"><h3>${f.name}</h3><p>${caught} поймано</p><span class="tag tag-${f.rarity}">${f.rarity}</span>${caught>0?`<span class="fish-catch-count">×${caught}</span>`:''}</div>`}).join('')}</div><div class="section-title">🏆 Достижения ${unlocked}/${achievements.length}</div><div class="achievements">${achievements.map(a=>`<div class="achievement ${state.unlockedAchievements.includes(a.id)?'done':''}"><span>${a.icon}</span><div><b>${a.name}</b><small>${a.desc}</small></div><strong>${state.unlockedAchievements.includes(a.id)?'✓':'+'+a.reward+' 💎'}</strong></div>`).join('')}</div>`}
else if(tab==='spots'){title.textContent='🌊 Водоёмы';content.innerHTML=`<div class="grid">${locations.map((l,i)=>`<button class="item spot ${i===state.loc?'selected':''}" data-location="${i}"><img src="${AS+l.img}"><h3>${l.name}</h3><p>${l.weather} • ${l.time}</p><span class="tag">${state.level>=l.level?'🎁 '+l.bonus:'🔒 Ур. '+l.level}</span></button>`).join('')}</div>`;content.querySelectorAll('[data-location]').forEach(b=>b.onclick=()=>{setLocation(+b.dataset.location);if(state.level>=locations[+b.dataset.location].level)$('panel').classList.add('hidden')})}
else{title.textContent='🎣 Рыбалка';content.innerHTML=`<div class="hero-stat"><span>Уровень</span><b>${state.level}</b><small>${state.xp}/${levelNeed(state.level)} XP</small></div><div class="menu-card">${state.lastCatch?`Последний трофей: <b>${fish[state.lastCatch.key].name}</b><span>${state.lastCatch.w} кг • +${state.lastCatch.reward} 💎</span>`:'Забрось удочку и поймай первую рыбу'}</div><div class="menu-card" id="eventOpen">✨ Событие <span>${currentEvent()?.name||'нет активного'}</span></div>`;content.querySelector('#eventOpen').onclick=rollEvent}$('panel').classList.remove('hidden')}
function buyRod(id){const g=gear.find(x=>x.id===id);if(!g)return;if(state.level<g.level){toast('🔒 Нужен уровень '+g.level);return}if(state.owned.includes(id)){state.rod=id;toast('🎣 '+g.name+' экипирована');save();openPanel('gear');return}if(state.diamonds<g.price){toast('💎 Недостаточно алмазов');return}state.diamonds-=g.price;state.owned.push(id);state.rod=id;render();save();toast('🎣 Новая удочка получена');openPanel('gear')}
function upgradeRod(){const r=getRod(),cost=Math.round(180*r.upgrade);if(r.upgrade>=8){toast('🏆 Максимальный уровень');return}if(state.diamonds<cost){toast('💎 Недостаточно алмазов');return}state.diamonds-=cost;state.rodLevels[state.rod]=r.upgrade+1;save();render();openPanel('gear');toast('⬆️ Удочка улучшена до ур. '+(r.upgrade+1))}
function showWallet(){const m=$('modal'),c=$('modalContent');c.innerHTML=`<div class="wallet-big">💎<b>${state.diamonds.toLocaleString('ru-RU')}</b></div><h2>Кошелёк</h2><p class="muted">Standalone: локальная игровая экономика. В Telegram Mini App баланс будет синхронизирован с Маруськой.</p><button class="primary full" id="demoReward">+100 💎 за тест</button>`;m.classList.remove('hidden');$('demoReward').onclick=()=>{state.diamonds+=100;render();save();toast('+100 💎');m.classList.add('hidden')}}
function cycleWeather(){if(state.phase!=='idle')return;const variants=[['🌤 Ясно','☀️ День'],['🌧 Дождь','🌧 Дождь'],['🌫 Туман','🌫 Туман'],['🌙 Ночь','🌙 Ночь']];state.weatherIndex=(state.weatherIndex+1)%variants.length;const v=variants[state.weatherIndex];$('weather').textContent=v[0];$('time').textContent=v[1];$('rain').classList.toggle('on',v[0].includes('Дождь'));toast(v[0]+' • '+v[1]);}
const api={async getProfile(){return {...state}},async saveProfile(patch){state={...state,...patch};save();return {...state}},async recordCatch(c){return c}};window.FishingAPI=api;
function telegramBridge(){try{const w=window.Telegram?.WebApp;if(!w)return;w.ready();w.expand();w.setHeaderColor?.('#06131b');w.setBackgroundColor?.('#06131b');w.setBottomBarColor?.('#06131b');w.disableVerticalSwipes?.();w.HapticFeedback?.impactOccurred?.('light')}catch{}}
function init(){load();render();checkAchievements();$('castBtn').onclick=cast;$('hookBtn').onclick=hook;$('continueBtn').onclick=continueCast;$('pullBtn').onclick=()=>fight('pull');$('relaxBtn').onclick=()=>fight('relax');$('reelBtn').onclick=()=>fight('reel');$('walletBtn').onclick=showWallet;$('weatherBtn').onclick=cycleWeather;document.querySelectorAll('.nav-item').forEach(b=>{const go=e=>{if(e.type==='touchend')e.preventDefault();e.stopPropagation();document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));b.classList.add('active');openPanel(b.dataset.tab)};b.onclick=go});$('panelClose').onclick=()=>$('panel').classList.add('hidden');$('modalClose').onclick=()=>$('modal').classList.add('hidden');scene.addEventListener('click',e=>{if(e.target.closest('button,.bite-card,.fight-card,.catch-card,.topbar'))return;if(state.phase==='idle')cast()});telegramBridge()}
init();


/* =========================
   FISHING v4 — progression layer
   Boats • bait inventory • daily quests • streaks • chests • backend bridge
   ========================= */
const V4_KEY='maruskaFishingV4';
const boats=[
  {id:'shore',name:'Береговая ловля',icon:'🥾',price:0,control:0,reward:0,level:1,desc:'Надёжный старт с берега.'},
  {id:'boat',name:'Лодка «Ветер»',icon:'🛶',price:1200,control:8,reward:.08,level:4,desc:'Выходи на глубину и получай больше добычи.'},
  {id:'speedboat',name:'Катер «Шторм»',icon:'🚤',price:3500,control:15,reward:.16,level:7,desc:'Для сильной рыбы и дальних забросов.'},
  {id:'legend',name:'Лодка «Таймень»',icon:'🚤',price:7000,control:24,reward:.28,level:10,desc:'Премиальная лодка для трофейной рыбалки.'}
];
const questTemplates=[
  {id:'q_catch',title:'Первый улов',desc:'Поймай 5 рыб',target:5,reward:180,type:'catch'},
  {id:'q_weight',title:'Тяжёлый трофей',desc:'Поймай рыбу тяжелее 4 кг',target:1,reward:260,type:'weight'},
  {id:'q_night',title:'Ночная охота',desc:'Поймай 2 рыбы ночью',target:2,reward:320,type:'night'},
  {id:'q_river',title:'Речная экспедиция',desc:'Поймай 3 рыбы на Большой реке',target:3,reward:300,type:'river'},
  {id:'q_rare',title:'Редкая добыча',desc:'Поймай редкую или более редкую рыбу',target:2,reward:420,type:'rare'}
];
const v4defaults={
  baitStock:{worm:12,maggots:5,corn:5,bread:5,livebait:3,fly:3,wobbler:2,spinner:2,softbait:2},
  boat:'shore',ownedBoats:['shore'],
  streak:0,lastFishDay:'',
  questsDay:'',quests:[],
  chests:0,openedChests:0,
  lifetimeWeight:0,
  backendUrl:''
};
function dayKey(){return new Date().toISOString().slice(0,10)}
function v4load(){
  try{
    const s=JSON.parse(localStorage.getItem(V4_KEY));
    if(s) Object.assign(state,v4defaults,s,{baitStock:{...v4defaults.baitStock,...(s.baitStock||{})}});
  }catch{}
  if(!state.baitStock)state.baitStock={...v4defaults.baitStock};
  if(!state.ownedBoats)state.ownedBoats=['shore'];
  if(!state.boat)state.boat='shore';
  ensureDailyQuests();
}
function v4save(){localStorage.setItem(V4_KEY,JSON.stringify({
  baitStock:state.baitStock,boat:state.boat,ownedBoats:state.ownedBoats,
  streak:state.streak,lastFishDay:state.lastFishDay,questsDay:state.questsDay,
  quests:state.quests,chests:state.chests,openedChests:state.openedChests,
  lifetimeWeight:state.lifetimeWeight,backendUrl:state.backendUrl||''
}))}
function ensureDailyQuests(){
  const d=dayKey();
  if(state.questsDay===d && Array.isArray(state.quests)&&state.quests.length)return;
  const shuffled=[...questTemplates].sort(()=>Math.random()-.5);
  state.quests=shuffled.slice(0,3).map(q=>({...q,progress:0,done:false}));
  state.questsDay=d; v4save();
}
function boat(){return boats.find(b=>b.id===state.boat)||boats[0]}
function baitId(){return ['worm','maggots','corn','bread','livebait','fly','wobbler','spinner','softbait'][state.bait]||'worm'}
function baitLabel(id){return (baits.find((b,i)=>['worm','maggots','corn','bread','livebait','fly','wobbler','spinner','softbait'][i]===id)||baits[0])[1]}
function consumeBait(){
  const id=baitId();
  if((state.baitStock[id]||0)<=0){toast('🪱 Наживка закончилась — пополни запас');openPanel('gear');return false}
  state.baitStock[id]--; return true;
}
function grantBait(id,n){state.baitStock[id]=(state.baitStock[id]||0)+n}
function updateQuests(c){
  ensureDailyQuests();
  state.quests.forEach(q=>{
    if(q.done)return;
    if(q.type==='catch')q.progress++;
    if(q.type==='weight'&&c.w>=4)q.progress=1;
    if(q.type==='night'&&c.night)q.progress++;
    if(q.type==='river'&&state.loc===2)q.progress++;
    if(q.type==='rare'&&['Редкая','Эпическая','Легендарная','Мифическая'].includes(c.rarity))q.progress++;
    q.progress=Math.min(q.target,q.progress);
    if(q.progress>=q.target){q.done=true;state.diamonds+=q.reward;toast('📜 Задание выполнено • +'+q.reward+' 💎')}
  });
}
function updateStreak(){
  const today=dayKey(), prev=new Date(Date.now()-86400000).toISOString().slice(0,10);
  if(state.lastFishDay===today)return;
  state.streak=state.lastFishDay===prev?(state.streak||0)+1:1;
  state.lastFishDay=today;
  const bonus=Math.min(500,50*state.streak);
  state.diamonds+=bonus;
  toast('🔥 Серия '+state.streak+' дней • +'+bonus+' 💎');
}
function maybeChest(){
  if(Math.random()<.12){state.chests++;toast('🎁 Ты нашёл сундук рыбака!');}
}
function openChest(){
  if(!state.chests){toast('🎁 Сундуков пока нет');return}
  state.chests--;
  const rewards=[
    ()=>{const n=200+Math.floor(Math.random()*601);state.diamonds+=n;return '+'+n+' 💎'},
    ()=>{const id=['worm','maggots','corn','bread','livebait'][Math.floor(Math.random()*5)];const n=2+Math.floor(Math.random()*5);grantBait(id,n);return '+'+n+' '+baitLabel(id)},
    ()=>{addXP(80+Math.floor(Math.random()*121));return '+XP'}
  ];
  const reward=rewards[Math.floor(Math.random()*rewards.length)]();
  state.openedChests++;v4save();save();render();toast('🎁 Сундук открыт: '+reward);
}
function showQuests(){
  ensureDailyQuests();
  const m=$('modal'),c=$('modalContent');
  c.innerHTML=`<div class="v4-modal-title">📜 Ежедневные задания</div>
  <p class="muted">Обновляются каждый день. Выполненные задания отмечаются автоматически.</p>
  <div class="v4-list">${state.quests.map(q=>`<div class="v4-quest ${q.done?'done':''}">
  <div class="v4-q-icon">${q.done?'✅':'📜'}</div><div><b>${q.title}</b><small>${q.desc}</small>
  <div class="v4-progress"><i style="width:${Math.round(q.progress/q.target*100)}%"></i></div>
  <span>${q.progress}/${q.target} • +${q.reward} 💎</span></div></div>`).join('')}</div>`;
  m.classList.remove('hidden');
}
function showBoats(){
  const m=$('modal'),c=$('modalContent');
  c.innerHTML=`<div class="v4-modal-title">🛶 Флот</div><p class="muted">Лодка влияет на контроль лески и награду за улов.</p>
  <div class="v4-boat-grid">${boats.map(b=>`<button class="v4-boat ${state.boat===b.id?'selected':''}" data-boat="${b.id}">
  <span class="v4-boat-icon">${b.icon}</span><b>${b.name}</b><small>${b.desc}</small>
  <span>Контроль +${b.control} • награда +${Math.round(b.reward*100)}%</span>
  <strong>${state.ownedBoats.includes(b.id)?(state.boat===b.id?'ЭКИПИРОВАНО':'ЭКИПИРОВАТЬ'):(state.level<b.level?'🔒 Ур. '+b.level:b.price.toLocaleString('ru-RU')+' 💎')}</strong></button>`).join('')}</div>`;
  m.classList.remove('hidden');
  c.querySelectorAll('[data-boat]').forEach(x=>x.onclick=()=>buyBoat(x.dataset.boat));
}
function buyBoat(id){
  const b=boats.find(x=>x.id===id);if(!b)return;
  if(state.level<b.level){toast('🔒 Нужен уровень '+b.level);return}
  if(state.ownedBoats.includes(id)){state.boat=id;v4save();render();showBoats();toast('🛶 '+b.name+' экипирована');return}
  if(state.diamonds<b.price){toast('💎 Недостаточно алмазов');return}
  state.diamonds-=b.price;state.ownedBoats.push(id);state.boat=id;v4save();save();render();showBoats();toast('🛶 Лодка куплена');
}
function buyBait(id){
  const prices={worm:10,maggots:18,corn:14,bread:10,livebait:45,fly:50,wobbler:65,spinner:60,softbait:55};
  const n=5,cost=(prices[id]||20)*n;
  if(state.diamonds<cost){toast('💎 Недостаточно алмазов');return}
  state.diamonds-=cost;grantBait(id,n);v4save();save();openPanel('gear');toast('🪱 +'+n+' '+baitLabel(id));
}
function showV4Stats(){
  const m=$('modal'),c=$('modalContent'),b=boat();
  c.innerHTML=`<div class="v4-modal-title">📊 Статистика</div>
  <div class="v4-stat-grid"><div><b>${state.caught}</b><span>улов</span></div><div><b>${state.best.toFixed(2)} кг</b><span>рекорд</span></div>
  <div><b>${state.streak} 🔥</b><span>серия дней</span></div><div><b>${state.openedChests}</b><span>сундуков</span></div></div>
  <div class="menu-card">🛶 ${b.name}<span>Контроль +${b.control} • награда +${Math.round(b.reward*100)}%</span></div>
  <div class="menu-card">🎯 Завершено заданий: <span>${state.quests.filter(q=>q.done).length}</span></div>`;
  m.classList.remove('hidden');
}
async function backendSync(){
  const url=state.backendUrl||localStorage.getItem('maruskaFishingBackend')||window.MARUSKA_FISHING_BACKEND||window.location.origin;
  if(!url)return {offline:true};
  try{
    const res=await fetch(url.replace(/\/$/,'')+'/api/fishing/profile',{headers:{'Content-Type':'application/json'}});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const remote=await res.json(); state={...state,...remote};v4save();save();render();return remote;
  }catch(e){return {offline:true,error:String(e)}}
}
const FishingBackend={
  configure(url){state.backendUrl=url;localStorage.setItem('maruskaFishingBackend',url);v4save();toast('🔌 Backend сохранён')},
  async sync(){return backendSync()},
  async save(){const url=state.backendUrl||localStorage.getItem('maruskaFishingBackend')||window.MARUSKA_FISHING_BACKEND||window.location.origin;if(!url)return {offline:true};try{
    const r=await fetch(url.replace(/\/$/,'')+'/api/fishing/profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(state)});return await r.json();
  }catch(e){return {offline:true,error:String(e)}}}
};
window.FishingBackend=FishingBackend;

// Preserve v3 handlers and add v4 gameplay hooks.
v4load();
const __v3Cast=cast;
cast=function(){
  if(!consumeBait())return;
  updateStreak();v4save();save();
  __v3Cast();
};
const __v3Fight=fight;
fight=function(type){
  const before=state.phase;
  __v3Fight(type);
  if(before==='fight'&&state.phase==='catch'){
    const c=state.lastCatch;
    if(c){
      c.night=(locations[state.loc].time||'').includes('Ночь')||state.loc===4;
      c.rarity=fish[c.key].rarity;
      updateQuests(c);maybeChest();
      const b=boat();
      const boatBonus=Math.round(c.reward*b.reward);
      if(boatBonus){state.diamonds+=boatBonus;c.reward+=boatBonus}
      state.lifetimeWeight+=c.w;
      v4save();save();
    }
  }
};

// Upgrade render of gear panel by wrapping original.
const __v3OpenPanel=openPanel;
openPanel=function(tab){
  __v3OpenPanel(tab);
  if(tab==='gear'){
    const host=$('panelContent');
    const oldBait=host.querySelector('.bait-row');
    if(oldBait){
      host.insertAdjacentHTML('afterend',`<div class="section-title">🪱 Запас наживки</div>
      <div class="v4-bait-stock">${Object.keys(v4defaults.baitStock).map(id=>{
        const idx=['worm','maggots','corn','bread','livebait','fly','wobbler','spinner','softbait'].indexOf(id);
        return `<button class="v4-stock" data-buybait="${id}"><img src="${AS+'baits/'+baits[idx][0]}"><b>${baits[idx][1]}</b><span>×${state.baitStock[id]||0}</span><small>Купить +5</small></button>`
      }).join('')}</div><div class="v4-mini-note">Каждый заброс расходует 1 выбранную наживку.</div>`);
      host.querySelectorAll('[data-buybait]').forEach(x=>x.onclick=()=>buyBait(x.dataset.buybait));
    }
  }
  if(tab==='spots'){
    const host=$('panelContent');
    host.insertAdjacentHTML('afterbegin',`<button class="v4-wide-btn" id="boatsBtn">🛶 ${boat().name} · Флот</button>`);
    $('boatsBtn').onclick=showBoats;
  }
};

// Add extra quick controls to UI.
function installV4UI(){
  if(document.getElementById('v4Tools'))return;
  const tools=document.createElement('div');tools.id='v4Tools';tools.className='v4-tools';
  tools.innerHTML=`<button id="questsBtn">📜</button><button id="chestBtn">🎁<em id="chestCount">${state.chests||0}</em></button><button id="statsBtn">📊</button>`;
  $('statusPill').after(tools);
  $('questsBtn').onclick=showQuests;$('statsBtn').onclick=showV4Stats;
  $('chestBtn').onclick=openChest;
  if(state.chests)toast('🎁 У тебя есть сундук!');
}
function v4RenderHook(){
  render();
  const cc=$('chestCount');if(cc)cc.textContent=state.chests||0;
  document.body.dataset.boat=state.boat;
}
const __oldRender=render;
render=function(){__oldRender();const cc=document.getElementById('chestCount');if(cc)cc.textContent=state.chests||0;};
installV4UI();
v4RenderHook();

// Replace old cast onclick installed by init.
$('castBtn').onclick=cast;
$('hookBtn').onclick=hook;
$('continueBtn').onclick=continueCast;
$('pullBtn').onclick=()=>fight('pull');
$('relaxBtn').onclick=()=>fight('relax');
$('reelBtn').onclick=()=>fight('reel');
v4save();






/* ===== v6 Telegram-authorized backend bridge ===== */
function fishingInitData(){
  return window.Telegram?.WebApp?.initData || '';
}
async function secureFetch(path, options={}){
  const url=(state.backendUrl||localStorage.getItem('maruskaFishingBackend')||window.MARUSKA_FISHING_BACKEND||window.location.origin||'').replace(/\/$/,'');
  if(!url)return null;
  const headers={...(options.headers||{}),'X-Telegram-Init-Data':fishingInitData()};
  const r=await fetch(url+path,{...options,headers});
  if(!r.ok)throw Error('Fishing API HTTP '+r.status);
  return r.json();
}
window.FishingSecure={
  profile:()=>secureFetch('/api/fishing/profile'),
  save:(profile)=>secureFetch('/api/fishing/profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(profile)}),
  catch:(c)=>secureFetch('/api/fishing/catch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)})
};


setTimeout(async()=>{ try { if(window.Telegram?.WebApp?.initData && window.FishingSecure){ const p=await window.FishingSecure.profile(); if(p&&typeof p==='object'){ state={...state,...p}; v4save(); save(); render(); } } } catch(e) {} }, 300);
/* ===== FX: rod, line and bobber drawn in SVG ===== */
const FX=(()=>{
  const NS='http://www.w3.org/2000/svg';
  const sc=document.getElementById('scene');
  const svg=document.createElementNS(NS,'svg');
  svg.id='fxLayer';
  svg.innerHTML=
    '<g id="fxRings"></g>'+
    '<path id="fxLine" fill="none" stroke="rgba(232,246,250,.9)" stroke-width="1.3" stroke-linecap="round"/>'+
    '<g id="fxBob"><ellipse id="fxBobShadow" cx="0" cy="1" rx="9" ry="2.6" fill="rgba(0,0,0,.28)"/>'+
      '<g id="fxBobBody"><line x1="0" y1="-19" x2="0" y2="-9" stroke="#ffd23f" stroke-width="2.2" stroke-linecap="round"/>'+
      '<ellipse cx="0" cy="-3" rx="5.6" ry="7.6" fill="#f3f6f6"/><path d="M-5.6 -3 A5.6 7.6 0 0 1 5.6 -3 Z" fill="#ff3434"/>'+
      '<ellipse cx="-1.8" cy="-6" rx="1.4" ry="2.4" fill="rgba(255,255,255,.55)"/></g></g>'+
    '<g id="fxDrops"></g>'+
    '<g id="fxRod"><path id="fxBlank" fill="none" stroke-linecap="round"/><path id="fxBlankHi" fill="none" stroke-linecap="round" stroke="rgba(255,255,255,.22)" stroke-width="1"/>'+
      '<g id="fxGuides"></g><path id="fxGrip" fill="none" stroke-linecap="round" stroke-width="10"/>'+
      '<circle id="fxReel" r="9" fill="#1b2327" stroke="#9fb3ba" stroke-width="2"/><circle id="fxReelHub" r="3" fill="#cfd8dc"/></g>';
  sc.appendChild(svg);
  const q=id=>svg.querySelector('#'+id);
  const E={line:q('fxLine'),bob:q('fxBob'),body:q('fxBobBody'),shadow:q('fxBobShadow'),rings:q('fxRings'),drops:q('fxDrops'),
    blank:q('fxBlank'),hi:q('fxBlankHi'),grip:q('fxGrip'),reel:q('fxReel'),hub:q('fxReelHub'),guides:q('fxGuides')};
  for(let i=0;i<4;i++){const c=document.createElementNS(NS,'circle');c.setAttribute('r','1.8');c.setAttribute('fill','none');c.setAttribute('stroke','#c9d6da');c.setAttribute('stroke-width','1');E.guides.appendChild(c)}
  const COLORS={starter:'#7a5230',float:'#2f7a58',spinning:'#28476e',feeder:'#23252b',carp:'#35603a',premium:'#c99a2e'};
  const S={mode:'idle',ang:50,bend:0,tension:0,fly:0,sub:0,biting:false,scale:1,tx:.62,ty:.5,jerk:0,lineOn:true};
  let tweens=[],drops=[],rings=[],nextRing=0,nibbleUntil=0,t0=performance.now();
  const ease=t=>1-Math.pow(1-t,3);
  function tween(key,to,dur,fn){tweens=tweens.filter(w=>w.key!==key);tweens.push({key,from:S[key],to,t:performance.now(),dur,fn})}
  function wait(ms){return new Promise(r=>setTimeout(r,ms))}
  function geo(){
    const W=sc.clientWidth,H=sc.clientHeight,L=Math.min(W*.64,270);
    const bx=W*.03,by=H-100,a=S.ang*Math.PI/180;
    const dx=Math.cos(a),dy=-Math.sin(a),nx=-dy,ny=dx;
    const tip={x:bx+dx*L,y:by+dy*L};
    // bend pulls the tip toward the line (forward/down)
    const b=S.bend+S.jerk;
    tip.x+=dx*-b*.15+b*.55;tip.y+=b*.9;
    const mid={x:bx+dx*L*.5+nx*b*.35,y:by+dy*L*.5+ny*b*.35};
    return {W,H,L,bx,by,dx,dy,tip,mid,target:{x:W*S.tx,y:H*S.ty}};
  }
  function ring(x,y,big){const e=document.createElementNS(NS,'ellipse');e.setAttribute('fill','none');e.setAttribute('stroke','rgba(210,245,252,.7)');e.setAttribute('stroke-width',big?'1.6':'1.1');E.rings.appendChild(e);rings.push({e,x,y,t:performance.now(),dur:big?1100:1500,max:big?34:20})}
  function splash(x,y){ring(x,y,true);setTimeout(()=>ring(x,y,true),140);for(let i=0;i<9;i++){const c=document.createElementNS(NS,'circle');c.setAttribute('r',String(1+Math.random()*1.6));c.setAttribute('fill','rgba(225,250,255,.9)');E.drops.appendChild(c);drops.push({c,x,y,vx:(Math.random()-.5)*110,vy:-60-Math.random()*90,t:performance.now()})}}
  function frame(now){
    const time=(now-t0)/1000;
    tweens=tweens.filter(w=>{const p=Math.min(1,(now-w.t)/w.dur);S[w.key]=w.from+(w.to-w.from)*(w.fn||ease)(p);return p<1});
    S.jerk*=.88;
    const g=geo(),tip=g.tip,T=g.target;
    let bx,by,sag=0,showBob=true;
    if(S.mode==='idle'){
      const sw=Math.sin(time*1.6)*3;bx=tip.x+4+sw;by=tip.y+30;S.scale=1;
    }else if(S.mode==='fly'){
      const p=S.fly,sx=S.fx0,sy=S.fy0;bx=sx+(T.x-sx)*p;by=sy+(T.y-sy)*p-Math.sin(p*Math.PI)*Math.max(90,(sy-T.y)*.9);S.scale=1-.22*p;sag=-10*Math.sin(p*Math.PI);
    }else if(S.mode==='water'){
      bx=T.x;by=T.y+Math.sin(time*2.1)*1.4;S.scale=.78;sag=16;
      if(S.biting){const d=Math.abs(Math.sin(time*9));by+=d*9;S.sub=.25+d*.55;sag=6;S.bend=4+d*10;if(now>nextRing){ring(T.x,T.y,false);nextRing=now+260}}
      else{S.sub=0;if(now<nibbleUntil)by+=5;else if(Math.random()<.004)nibbleUntil=now+170;if(now>nextRing){ring(T.x,T.y,false);nextRing=now+1700}}
    }else{ // fight: fish pulls the line; keep it above the fight card so it stays visible
      const card=document.getElementById('fightCard'),top=card&&!card.classList.contains('hidden')?card.getBoundingClientRect().top-sc.getBoundingClientRect().top-30:T.y;
      const fy=Math.min(T.y,top),k=.5+S.tension/140;bx=T.x+Math.sin(time*1.7)*38*k+Math.sin(time*4.3)*6;by=fy+Math.cos(time*1.1)*6;showBob=false;sag=0;
      S.bend=10+S.tension*.42+Math.sin(time*11)*S.tension*.04;
      if(now>nextRing){ring(bx,by-6,false);nextRing=now+420-S.tension*2}
    }
    // rod
    const col=COLORS[(typeof getRod==='function'&&getRod().id)||'starter']||COLORS.starter;
    const gx=g.bx+g.dx*g.L*.3,gy=g.by+g.dy*g.L*.3;
    E.blank.setAttribute('d',`M${g.bx},${g.by} Q${g.mid.x},${g.mid.y} ${tip.x},${tip.y}`);E.blank.setAttribute('stroke',col);E.blank.setAttribute('stroke-width','4.2');
    E.hi.setAttribute('d',`M${gx},${gy} Q${g.mid.x},${g.mid.y} ${tip.x},${tip.y}`);
    E.grip.setAttribute('d',`M${g.bx},${g.by} L${gx},${gy}`);E.grip.setAttribute('stroke','#a8733f');
    const rx=g.bx+g.dx*g.L*.2+g.dy*-11,ry=g.by+g.dy*g.L*.2+g.dx*11;
    E.reel.setAttribute('cx',rx);E.reel.setAttribute('cy',ry);E.hub.setAttribute('cx',rx);E.hub.setAttribute('cy',ry);
    [...E.guides.children].forEach((c,i)=>{const u=.45+i*.17,v=1-u;c.setAttribute('cx',v*v*g.bx+2*v*u*g.mid.x+u*u*tip.x);c.setAttribute('cy',v*v*g.by+2*v*u*g.mid.y+u*u*tip.y)});
    // line
    const mx=(tip.x+bx)/2,my=(tip.y+by)/2+sag;
    E.line.setAttribute('d',`M${tip.x},${tip.y} Q${mx},${my} ${bx},${by}`);
    E.line.style.opacity=S.lineOn?1:0;
    // bobber
    E.bob.style.display=showBob&&S.lineOn?'':'none';
    E.bob.setAttribute('transform',`translate(${bx},${by}) scale(${S.scale})`);
    E.body.setAttribute('transform',`translate(0,${S.sub*9})`);
    E.body.style.opacity=1-S.sub*.55;
    E.shadow.style.display=S.mode==='water'?'':'none';
    // rings & drops
    rings=rings.filter(r=>{const p=(now-r.t)/r.dur;if(p>=1){r.e.remove();return false}r.e.setAttribute('cx',r.x);r.e.setAttribute('cy',r.y+2);r.e.setAttribute('rx',4+r.max*p);r.e.setAttribute('ry',(4+r.max*p)*.32);r.e.style.opacity=1-p;return true});
    drops=drops.filter(d=>{const s=(now-d.t)/1000;if(s>.7){d.c.remove();return false}d.c.setAttribute('cx',d.x+d.vx*s);d.c.setAttribute('cy',d.y+d.vy*s+260*s*s);d.c.style.opacity=1-s/.7;return true});
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  return {
    async cast(){
      S.mode='idle';S.biting=false;S.sub=0;S.lineOn=true;S.tension=0;
      S.tx=.5+Math.random()*.24;S.ty=.47+Math.random()*.06;
      tween('bend',0,150);tween('ang',80,240);await wait(240);
      tween('ang',34,170);tween('bend',26,170);await wait(120);
      const g=geo();S.fx0=g.tip.x;S.fy0=g.tip.y;S.fly=0;S.mode='fly';
      tween('fly',1,720,t=>t);tween('bend',0,420);setTimeout(()=>tween('ang',46,500),170);
      await wait(720);
      S.mode='water';const T=geo().target;splash(T.x,T.y);nextRing=performance.now()+500;
    },
    bite(){S.biting=true;S.mode='water'},
    hook(){S.biting=false;S.mode='fight';S.jerk=18;tween('ang',66,220);const T=geo().target;splash(T.x,T.y)},
    tension(v){S.tension=v},
    jerk(){S.jerk=14},
    reset(){S.mode='idle';S.biting=false;S.sub=0;S.tension=0;S.lineOn=true;tween('ang',50,450);tween('bend',0,450)},
    snap(){S.lineOn=false;S.mode='idle';S.biting=false;S.tension=0;S.jerk=0;tween('ang',30,160);tween('bend',0,300);setTimeout(()=>{tween('ang',50,600);S.lineOn=true},900)}
  };
})();
window.FX=FX;
