'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const state = {mode:'live', business:'plan', config:null, data:null, selected:null, payload:null, request:0, timer:null, manualSelection:false, map:null, chart:null, routeLayer:null, tile:null, citiesLayer:null};
const colors = ['#72a98a','#65a6d8','#e9b450','#eb9253','#dc625b'];
const labels = ['无阈值命中','蓝色','黄色','橙色','红色'];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge = (type, title='') => `<b class="badge ${{'真实':'real','推断':'inferred','模拟':'simulated','用户输入':'input','用户提供':'input'}[type] || 'inferred'}" title="${esc(title)}">${esc(type)}</b>`;
const fmt = (v,n=1) => Number(v).toFixed(n);
const localTime = value => { const d=new Date(value); return Number.isNaN(d.getTime()) ? '时间无效' : new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d); };
const isoLocal = d => { const pad=n=>String(n).padStart(2,'0'); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const defaultTime = mode => mode==='offline' ? new Date('2025-01-01T08:00:00Z') : new Date(Date.now()+4*3600*1000);
const routeSource = route => (route?.provenance || []).map(p => `${p.source} · ${p.retrieved_at_utc}`).join('；');

function showError(message){ $('#error').textContent=message; $('#error').classList.toggle('hidden',!message); }
function setLoading(on){ $('#loading').classList.toggle('hidden',!on); $('#analyzeBtn').disabled=on; $('#analyzeBtn').textContent=on?'正在分析…':'分析运输路线 ↗'; }
function setBanner(){
  const banner=$('#banner');
  const scenario=state.data?.scenario;
  if(state.mode==='offline'){
    let text='离线演示：路线为已保存的真实路由，天气为 2025 年历史预报，不是当前预报。发车与参考时刻均用于模拟。';
    if(scenario) text+=` 当前为场景演示：已注入 ${scenario.inject.length} 个模拟事件。`;
    banner.innerHTML=esc(text)+` ${badge('真实','历史天气预报及其时间来自 Open-Meteo 快照')}${scenario ? ' '+badge('模拟','场景事件为模拟') : ''}`; banner.className='mode-banner';
  }else if(state.mode==='scenario'){
    banner.innerHTML=esc(scenario?`当前为场景演示：${scenario.name}，已注入 ${scenario.inject.length} 个模拟事件。所有事件均非现实路况。`:'场景演示：所选事件均为模拟，分析后显示注入数量。')+' '+badge('模拟','场景事件均为模拟'); banner.className='mode-banner scene';
  }else{ banner.className='mode-banner hidden'; banner.textContent=''; }
  $('#scenarioField').classList.toggle('hidden',state.mode==='live');
  const status=$('#connection');
  status.classList.toggle('off',state.mode==='offline'||!navigator.onLine);
  status.innerHTML=state.mode==='offline'?'<i></i>历史快照 · 离线演示':navigator.onLine?'<i></i>设备在线 · 接口待分析':'<i></i>设备离线';
}
function clearResults(){ state.data=null;state.payload=null;state.selected=null;state.manualSelection=false; $('#decision').classList.add('hidden');$('#placeResolution').classList.add('hidden'); $('#results').className='results-empty';$('#results').innerHTML='<div class="empty-route">⌁</div><strong>还没有路线方案</strong><span>分析完成后，方案会按推荐指数排序。</span>';$('#resultCount').textContent='等待分析';$('#decisionBtn').disabled=true;$('#exportBtn').disabled=true;$('#mapEmpty').classList.remove('hidden');$('#chartEmpty').classList.remove('hidden'); if(state.routeLayer)state.routeLayer.clearLayers();if(state.chart)state.chart.clear();setBanner(); }
function switchMode(mode){
  state.request++;clearTimeout(state.timer);setLoading(false);state.mode=mode; $$('.mode').forEach(el=>el.classList.toggle('active',el.dataset.mode===mode));
  $('#departure').value=isoLocal(defaultTime(mode));
  $('#scenario').value=mode==='scenario'?'closure':'none';
  if(state.tile){state.map.removeLayer(state.tile);state.tile=null;}
  if(mode!=='offline' && navigator.onLine){ state.tile=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:''}).addTo(state.map);state.tile.bringToBack(); }
  clearResults();showError('');
}
function switchBusiness(kind){state.request++;clearTimeout(state.timer);setLoading(false);state.business=kind;$$('.business').forEach(x=>x.classList.toggle('active',x.dataset.business===kind));$('#planFields').classList.toggle('hidden',kind!=='plan');$('#inspectFields').classList.toggle('hidden',kind!=='inspect');clearResults();showError('');}
function payload(){
  const departure=new Date($('#departure').value); if(Number.isNaN(departure.getTime()))throw new Error('请输入有效的计划发车时间。');
  const promised=Number($('#promised').value); if(!(promised>0))throw new Error('承诺时效必须大于零。');
  return {mode:state.mode,business_mode:state.business,origin:$('#origin').value.trim(),destination:$('#destination').value.trim(),route_text:$('#routeText').value.trim(),departure_utc:departure.toISOString(),cargo:$('#cargo').value,promised_hours:promised,time_preference:Number($('#timePref').value),money_preference:Number($('#moneyPref').value),scenario:state.mode==='live'?'none':$('#scenario').value};
}
async function requestAnalysis(){
  let body;try{body=payload()}catch(e){showError(e.message);return;}
  const number=++state.request; setLoading(true);showError('');$('#exportBtn').disabled=true;
  try{
    const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json(); if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'输入有误，请检查后重试。');
    if(number!==state.request)return;
    state.data=data;state.payload=body;
    if(!state.manualSelection || !data.result.ranked_routes.some(x=>x.route_id===state.selected))state.selected=data.result.decision?.route_id || data.routes[0]?.id || null;
    renderResults();renderMap(true);renderChart();setBanner();
    const fixture=data.result.decision?.samples?.some(s=>s.weather_source.mode==='fixture');
    const routeFixture=data.routes.some(r=>r.provenance.some(p=>p.mode==='fixture'));
    if(state.mode!=='offline' && (fixture||routeFixture)){$('#connection').innerHTML='<i></i>'+(fixture&&routeFixture?'路线和天气已回落快照':fixture?'天气已回落历史快照':'路线已回落离线快照');$('#connection').classList.add('off');}
    else if(state.mode!=='offline' && data.result.decision){const retrieved=data.result.decision.samples[0].weather_source.retrieved_at_utc;$('#connection').innerHTML=`<i></i>天气获取 ${esc(localTime(retrieved))} ${badge('真实','Open-Meteo 响应获取时间：'+retrieved)}`;}
    $('#exportBtn').disabled=!data.result.decision;$('#decisionBtn').disabled=!data.result.decision;
  }catch(error){if(number===state.request){clearResults();showError(error.message || '分析失败，请稍后重试。');}}
  finally{if(number===state.request)setLoading(false);}
}
function invalidate(){const hadResult=!!state.data || $('#analyzeBtn').disabled;state.request++;clearTimeout(state.timer);setLoading(false);if(hadResult){clearResults();showError('输入已更改，请重新分析路线。');}}
function rerank(){ $('#timeValue').textContent=$('#timePref').value;$('#moneyValue').textContent=$('#moneyPref').value;const shouldRun=!!state.data || $('#analyzeBtn').disabled;if(shouldRun){state.request++;clearTimeout(state.timer);setLoading(false);state.timer=setTimeout(requestAnalysis,220);} }
function renderResults(){
  const result=state.data.result, rows=result.ranked_routes;const locations=state.data.resolved_places||[];const placeEl=$('#placeResolution');placeEl.classList.toggle('hidden',!locations.length);placeEl.innerHTML=locations.length?'地点解析：'+locations.map(p=>`${esc(p.label)} ${badge(p.source_type, p.source+(p.retrieved_at_utc?' · 获取：'+p.retrieved_at_utc:' · 未记录获取时间'))}`).join(' → '):'';
  $('#resultCount').innerHTML=rows.length?`路由返回 ${state.data.routes.length} 条 ${badge('真实',routeSource(state.data.routes[0]))} · 可评估 ${rows.length} 条 ${badge('推断','排除已过时、封路或缺少天气的方案')}`:'暂无可行方案';
  const container=$('#results');
  if(!rows.length){const reasons=[...new Set(result.candidates.map(x=>x.reason).filter(Boolean))];container.className='results-empty';container.innerHTML=`<strong>当前没有可行方案</strong><span>${esc(reasons.join('；') || '请调整发车时间或路线。')}</span>`;$('#decision').classList.add('hidden');if(state.data.routes.length)$('#mapEmpty').classList.add('hidden');return;}
  container.className='route-list';
  const minDistance=Math.min(...rows.map(x=>x.distance_km)), minRisk=Math.min(...rows.map(x=>x.highest_risk));
  container.innerHTML=rows.map((r,i)=>{
    const geometry=state.data.routes.find(x=>x.id===r.route_id), source=routeSource(geometry), weather=r.samples[0].weather_source;
    const city=(geometry.nearby_cities||[]).join(' · ') || '未匹配内置城市';
    const riskIndex=r.samples.findIndex(s=>s.risk.level===r.highest_risk), point=r.samples[riskIndex];
    const plus=[rows.length>1 && r.distance_km===minDistance?'本次候选中里程较短':'已按真实路网规划',rows.length>1 && r.highest_risk===minRisk?'本次候选中最高天气风险较低':'已按经过时间匹配天气'];
    const minus=[r.highest_risk>=2?'部分路段需关注天气':'沿途天气仍需动态复核',r.misses_promise?`预计超过承诺时效 ${fmt(r.late_hours)} 小时`:r.shift_hours<0?'需要提前发车':'需按计划时间发车'];
    return `<article class="route-card ${r.route_id===state.selected?'selected':''}" tabindex="0" role="button" data-route="${esc(r.route_id)}" aria-label="选择路线 ${esc(r.route_id)}"><div class="route-title"><strong>路线 ${esc(r.route_id)} ${i===0?'<span class="recommended-label">推荐</span>':''}</strong><span class="route-score">${fmt(r.score,1)} <small>推荐指数</small> ${badge('推断','100 × (1 − 当前预期成本 / 最差可行方案成本)')}</span></div><div class="route-meta"><span>${fmt(r.distance_km)} km ${badge('真实',source)}</span><span>${fmt(r.duration_h)} 小时 ${badge('推断','路由时长及模拟场景推算')}</span><span>${labels[r.highest_risk]} ${badge('推断','天气阈值计算')}</span></div><div class="route-city">附近城市：${esc(city)} ${badge('推断','根据路线与内置城市坐标距离估计，不代表途经市区')}</div><div class="route-detail-list">优点：${esc(plus.join('；'))} ${badge('推断')}<br>注意：${esc(minus.join('；'))} ${badge('推断')}</div><div class="route-reason">最高风险点：${fmt(point.distance_m/1000)} km ${badge('推断')} · ${esc(localTime(point.passage_utc))} ${badge('推断')} · 天气 ${badge('真实',`${weather.source}；获取：${weather.retrieved_at_utc}`)}</div><div class="route-trigger">${esc(r.trigger)}</div></article>`;
  }).join('');
  $$('.route-card').forEach(el=>{const select=()=>{state.selected=el.dataset.route;state.manualSelection=true;renderResults();renderMap(false);renderChart();};el.addEventListener('click',select);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});});
  $('#mapEmpty').classList.add('hidden');$('#decision').classList.add('hidden');
}
function renderDecision(){
  const r=state.data?.result.decision;if(!r)return;state.selected=r.route_id;state.manualSelection=false;renderResults();renderMap(false);renderChart();
  const overdue=r.misses_promise?`<p class="overdue">预计超过承诺时效 ${fmt(r.late_hours)} 小时 ${badge('推断','按预计到达与承诺期限比较')}</p>`:'';
  const assumptions=state.data.scenario?`<p>已考虑模拟场景；模拟已确认封路仅用于场景演示。 ${badge('模拟')}</p>`:'';
  $('#decision').innerHTML=`<strong>✦ 建议路线 ${esc(r.route_id)}</strong> ${badge('推断')}<p>建议发车：${esc(localTime(r.departure_utc))} ${badge('推断')}<br>预计到达：${esc(localTime(r.arrival_utc))} ${badge('推断')}<br>剩余最高风险：${labels[r.highest_risk]} ${badge('推断')}</p><ol>${r.reasons.map(x=>`<li>${esc(x)} ${badge('推断','基于模拟参数和天气计算')}</li>`).join('')}</ol>${overdue}<p>${esc(r.trigger)}</p>${assumptions}`;$('#decision').classList.remove('hidden');
}
function geoDistance(a,b){const rad=Math.PI/180,dy=(b[1]-a[1])*rad,dx=(b[0]-a[0])*rad,x=Math.sin(dy/2)**2+Math.cos(a[1]*rad)*Math.cos(b[1]*rad)*Math.sin(dx/2)**2;return 12742000*Math.asin(Math.min(1,Math.sqrt(x)));}
function clipGeometry(segment,offset,start,end){
  const coords=segment.geometry.coordinates,lens=[0];for(let i=1;i<coords.length;i++)lens.push(lens[i-1]+geoDistance(coords[i-1],coords[i]));const total=lens.at(-1);if(!total)return [];
  const a=Math.max(0,(start-offset)/segment.distance)*total,b=Math.min(1,(end-offset)/segment.distance)*total;if(a>=b)return [];
  const result=[]; for(let i=1;i<coords.length;i++){const l=lens[i-1],r=lens[i];if(r<a||l>b||r===l)continue;const interpolate=t=>{const v=(t-l)/(r-l);return [coords[i-1][1]+v*(coords[i][1]-coords[i-1][1]),coords[i-1][0]+v*(coords[i][0]-coords[i-1][0])];};if(!result.length)result.push(interpolate(Math.max(a,l)));result.push(interpolate(Math.min(b,r)));if(r>=b)break;}return result;
}
function renderMap(fit){
  const map=state.map, layer=state.routeLayer; layer.clearLayers(); if(!state.data)return;
  const routes=state.data.routes, ranked=state.data.result.ranked_routes;
  for(const r of routes){for(const seg of r.segments){const line=L.polyline(seg.geometry.coordinates.map(c=>[c[1],c[0]]),{color:r.id===state.selected?'#b7cac0':'#aebcb5',weight:r.id===state.selected?7:4,opacity:.8}).addTo(layer);line.on('click',()=>{if(ranked.some(x=>x.route_id===r.id)){state.selected=r.id;state.manualSelection=true;renderResults();renderMap(false);renderChart();}});}}
  const route=routes.find(x=>x.id===state.selected),selected=ranked.find(x=>x.route_id===state.selected)||state.data.result.candidates.find(x=>x.route_id===state.selected&&x.shift_hours===0);if(!route)return;
  const samples=selected?.samples||route.preview_samples;
  for(let i=0;selected?.samples && i<selected.samples.length-1;i++){
    const a=selected.samples[i],b=selected.samples[i+1];let offset=0;
    for(const seg of route.segments){const clipped=clipGeometry(seg,offset,a.distance_m,b.distance_m);if(clipped.length>1)L.polyline(clipped,{color:colors[a.risk.level],weight:5,opacity:1}).bindTooltip(`${labels[a.risk.level]}风险 · 推断`).addTo(layer);offset+=seg.distance;}
  }
  const first=samples[0],last=samples.at(-1);for(const [sample,name] of [[first,'起'],[last,'终']])L.circleMarker([sample.position[1],sample.position[0]],{radius:7,color:'#fff',weight:3,fillColor:'#255b46',fillOpacity:1}).bindTooltip(name).addTo(layer);
  if(state.data.scenario){for(const event of state.data.scenario.inject){if(event.route_id && event.route_id!==route.id)continue;const i=Number(event.edge.slice(1))-1,s=samples[i];if(!s)continue;const active=(selected?.events||[]).some(e=>e.edge===event.edge&&e.kind===event.kind);const title=`模拟${event.kind==='closed'?(event.confirmed?'已确认封路':'预报封路'):'减速'} · ${active?'当前方案生效':'当前方案未生效'}`;L.marker([s.position[1],s.position[0]],{icon:L.divIcon({className:'',html:`<span class="event-icon">注入${active?'':'·未生效'}</span>`})}).bindTooltip(title).addTo(layer);}}
  if(fit){const lines=route.segments.flatMap(seg=>seg.geometry.coordinates.map(c=>[c[1],c[0]]));if(lines.length)map.fitBounds(L.latLngBounds(lines),{padding:[28,28],maxZoom:9});}
}
function renderChart(){
  const selected=state.data?.result.ranked_routes.find(x=>x.route_id===state.selected);if(!selected){state.chart.clear();$('#chartEmpty').classList.remove('hidden');return;}
  $('#chartEmpty').classList.add('hidden');const rows=selected.samples;
  const series=(key,scale=1)=>rows.map(r=>[r.distance_m/1000,key==='visibility'?r.risk.visibility_m==null?null:r.risk.visibility_m/scale:r.weather[key]==null?null:r.weather[key]/scale]);
  const bands=rows.slice(0,-1).map((r,i)=>[{xAxis:r.distance_m/1000,itemStyle:{color:['rgba(119,172,138,.09)','rgba(97,166,218,.12)','rgba(237,188,74,.14)','rgba(239,148,81,.16)','rgba(222,91,79,.16)'][r.risk.level]}},{xAxis:rows[i+1].distance_m/1000}]);
  const worst=rows.reduce((a,b)=>a.risk.level>=b.risk.level?a:b);
  const markers=[{xAxis:rows[0].distance_m/1000,name:'起点'},{xAxis:rows.at(-1).distance_m/1000,name:'终点'}];if(state.data.scenario){for(const event of state.data.scenario.inject){if(event.route_id&&event.route_id!==selected.route_id)continue;const i=Number(event.edge.slice(1))-1;if(rows[i])markers.push({xAxis:rows[i].distance_m/1000,name:'模拟注入',lineStyle:{color:'#a66a9c',type:'dashed'}});}}for(const city of state.data.routes.find(x=>x.id===state.selected).nearby_cities){const p=state.config.cities[city];let near=rows[0];for(const r of rows)if(geoDistance(r.position,[p[1],p[0]])<geoDistance(near.position,[p[1],p[0]]))near=r;if(near!==rows[0]&&near!==rows.at(-1))markers.push({xAxis:near.distance_m/1000,name:city+'附近'});}
  state.chart.setOption({animation:false,grid:{left:50,right:55,top:46,bottom:65},legend:{top:0,right:8,textStyle:{fontSize:10,color:'#81958a'},data:['降水 mm/h','风速 m/s','能见度 km']},tooltip:{trigger:'axis',confine:true,formatter:params=>{const i=params[0]?.dataIndex,r=rows[i];if(!r)return '';const w=r.weather,src=r.weather_source;return `<b>${fmt(r.distance_m/1000)} km · 推断</b><br>预计经过：${esc(localTime(r.passage_utc))} · 推断<br>预报整点：${esc(localTime(w.forecast_time_utc))} · 推断<br>降水：${w.precipitation==null?'缺失':fmt(w.precipitation)} mm/h · 真实<br>风速：${w.wind_speed_10m==null?'缺失':fmt(w.wind_speed_10m)} m/s · 真实<br>能见度：${r.risk.visibility_m==null?'缺失':fmt(r.risk.visibility_m/1000)} km · ${esc(r.risk.visibility_source)}<br>风险：${labels[r.risk.level]} · 推断<br>分级依据：${esc(Object.entries(r.risk.factors).map(([k,v])=>`${k} ${v==null?'缺失':labels[v]}`).join('；'))}<br>天气来源：${esc(src.source)}<br>获取：${esc(src.retrieved_at_utc)}`;}},xAxis:{type:'value',name:'里程 km · 推断',nameLocation:'middle',nameGap:30,axisLine:{lineStyle:{color:'#c9d5cc'}},axisLabel:{color:'#8a9c90',fontSize:10}},yAxis:[{type:'value',name:'降水 mm/h · 真实',min:0,splitLine:{lineStyle:{color:'#edf2ee'}},axisLabel:{color:'#91a397',fontSize:10}},{type:'value',name:'风 m/s / 能见度 km',min:0,splitLine:{show:false},axisLabel:{color:'#91a397',fontSize:10}}],dataZoom:[{type:'inside'},{type:'slider',height:13,bottom:4,borderColor:'transparent',backgroundColor:'#f1f5f0',fillerColor:'#bcd9c8',handleSize:9,textStyle:{fontSize:9}}],series:[{name:'降水 mm/h',type:'line',showSymbol:false,data:series('precipitation'),itemStyle:{color:'#8dbccf'},lineStyle:{color:'#8dbccf',width:1},areaStyle:{color:'rgba(148,195,213,.35)'},markArea:{silent:true,data:bands},markLine:{silent:true,symbol:'none',lineStyle:{type:'dotted',color:'#b8c8bc'},label:{fontSize:9,formatter:'{b}',position:'insideEndTop'},data:markers}},{name:'风速 m/s',type:'line',showSymbol:false,yAxisIndex:1,data:series('wind_speed_10m'),itemStyle:{color:'#d79d57'},lineStyle:{color:'#d79d57',width:2}},{name:'能见度 km',type:'line',showSymbol:false,yAxisIndex:1,data:series('visibility',1000),itemStyle:{color:'#4c9279'},lineStyle:{color:'#4c9279',width:2,type:'dashed'},markPoint:{symbolSize:28,data:[{coord:[worst.distance_m/1000,(worst.risk.visibility_m||0)/1000],value:'风险',itemStyle:{color:colors[worst.risk.level]}}]}}]},true);
}
async function exportReport(){if(!state.payload)return;$('#exportBtn').disabled=true;try{const r=await fetch('/api/report/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.payload)});const data=await r.json();if(!r.ok)throw Error(data.detail||'报告生成失败');$('#reportNotice').innerHTML=`报告已保存到项目目录：${esc(data.relative_path)} <a href="${esc(data.url)}" target="_blank" rel="noopener">打开报告 ↗</a>`;$('#reportNotice').classList.remove('hidden');}catch(e){showError(e.message);}finally{$('#exportBtn').disabled=false;}}

const assumptionNames={sampling_interval_km:'采样间距（km）',freight_yuan_per_km:'运价（元/km）',time_cost_yuan_per_hour:'时间成本（元/小时）',late_penalty_yuan:'延误赔付（元）',warehouse_yuan_per_hour:'仓储费（元/小时）',promised_hours_default:'默认承诺时效（小时）',delay_probability_by_level:'各风险等级延误概率',risk_penalty_yuan_by_level:'各风险等级惩罚（元）',cargo_risk_multiplier:'货类风险系数',unconfirmed_closure_probability:'预报封路延误概率下限',unconfirmed_closure_penalty_yuan:'预报封路惩罚（元）',preference_weight_floor:'偏好权重底数',preference_default:'默认偏好',storage_hours_default:'默认仓储时长（小时）',nearby_city_radius_km:'附近城市范围（km）'};
const placeTimers={};
function suggestPlaces(id){const value=$('#'+id).value.trim(), target=$('#'+id+'Places');clearTimeout(placeTimers[id]);if(state.mode==='offline'||value.length<2||value.includes('（')||value.includes(','))return;placeTimers[id]=setTimeout(async()=>{try{const response=await fetch('/api/places?query='+encodeURIComponent(value));if(!response.ok)return;const body=await response.json();if($('#'+id).value.trim()!==value)return;const options=[...new Set([...Object.keys(state.config.cities),...body.places.map(p=>p.label)])];target.innerHTML=options.map(n=>`<option value="${esc(n)}"></option>`).join('');}catch(e){/* 主分析会给出可读的地点查询错误。 */}},400);}
function initMap(){state.map=L.map('map',{zoomControl:true,attributionControl:true,preferCanvas:true}).setView([28.8,112.8],6);state.map.attributionControl.addAttribution('&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · <a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a>');for(let lat=23;lat<=32;lat++)L.polyline([[lat,110],[lat,117]],{color:'#91a992',weight:.5,opacity:.24,interactive:false}).addTo(state.map);for(let lon=110;lon<=117;lon++)L.polyline([[23,lon],[32,lon]],{color:'#91a992',weight:.5,opacity:.24,interactive:false}).addTo(state.map);state.routeLayer=L.layerGroup().addTo(state.map);state.citiesLayer=L.layerGroup().addTo(state.map);fetch('/static/map/provinces.geojson').then(r=>r.json()).then(g=>{const layer=L.geoJSON(g,{style:{color:'#b8cbb9',weight:1,fillColor:'#e5f0e2',fillOpacity:.6,interactive:false}}).addTo(state.map);layer.bringToBack();});}
async function init(){
  initMap();state.chart=echarts.init($('#chart'));window.addEventListener('resize',()=>state.chart.resize());
  $('#departure').value=isoLocal(defaultTime('live'));setBanner();
  try{const r=await fetch('/api/config');if(!r.ok)throw Error('配置加载失败');state.config=await r.json();for(const id of ['originPlaces','destinationPlaces'])$('#'+id).innerHTML=Object.keys(state.config.cities).map(n=>`<option value="${esc(n)}"></option>`).join('');
    for(const [name,p] of Object.entries(state.config.cities)){L.circleMarker(p,{radius:3,color:'#829b87',weight:1,fillColor:'#fff',fillOpacity:1}).addTo(state.citiesLayer);L.marker(p,{interactive:false,icon:L.divIcon({className:'city-label',html:esc(name),iconSize:[60,18],iconAnchor:[-5,8]})}).addTo(state.citiesLayer);}
    $('#assumptionsList').innerHTML=Object.entries(state.config.assumptions).map(([k,v])=>`<div class="assumption-row"><strong>${esc(assumptionNames[k]||k)}</strong><span>${esc(typeof v.value==='object'?JSON.stringify(v.value):v.value)} ${badge('模拟',v.reason)}</span><span>${esc(v.reason)}</span></div>`).join('');
  }catch(e){showError('配置加载失败：'+e.message);}
  switchMode('live');
  $$('.mode').forEach(b=>b.addEventListener('click',()=>switchMode(b.dataset.mode)));$$('.business').forEach(b=>b.addEventListener('click',()=>switchBusiness(b.dataset.business)));
  $('#analyzeBtn').addEventListener('click',requestAnalysis);$('#decisionBtn').addEventListener('click',renderDecision);$('#exportBtn').addEventListener('click',exportReport);$('#timePref').addEventListener('input',rerank);$('#moneyPref').addEventListener('input',rerank);
  for(const id of ['origin','destination','routeText','departure','cargo','promised','scenario'])$('#'+id).addEventListener('input',invalidate);for(const id of ['origin','destination'])$('#'+id).addEventListener('input',()=>suggestPlaces(id));for(const id of ['cargo','scenario'])$('#'+id).addEventListener('change',invalidate);
  $('#assumptionsBtn').addEventListener('click',()=>$('#assumptionsDialog').showModal());$('#closeDialog').addEventListener('click',()=>$('#assumptionsDialog').close());
  window.addEventListener('online',setBanner);window.addEventListener('offline',setBanner);
}
document.addEventListener('DOMContentLoaded',init);
