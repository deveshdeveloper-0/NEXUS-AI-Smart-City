const $ = (s) => document.querySelector(s);
async function getJSON(url){const r=await fetch(url);if(!r.ok)throw new Error(`API error ${r.status}`);return r.json()}
function metricCard(label,value,unit){return `<div class="metric"><label>${label}</label><strong>${value}</strong><small>${unit}</small></div>`}
function drawTrend(a,b){
  const c=$("#trend"),ctx=c.getContext("2d"),w=c.width,h=c.height,p=35;
  ctx.clearRect(0,0,w,h);ctx.strokeStyle="#26384b";ctx.lineWidth=1;
  for(let i=0;i<5;i++){let y=p+i*(h-2*p)/4;ctx.beginPath();ctx.moveTo(p,y);ctx.lineTo(w-p,y);ctx.stroke()}
  function line(vals,color,max){ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();vals.forEach((v,i)=>{let x=p+i*(w-2*p)/(vals.length-1),y=h-p-(v/max)*(h-2*p);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}
  line(a,"#20d7df",100);line(b.map(x=>x/1.6),"#a78bfa",100);
}
async function loadDashboard(){
  try{const d=await getJSON("/api/dashboard");$("#metrics").innerHTML=d.indicators.map(x=>metricCard(x.name,x.value,x.unit)).join("");drawTrend(d.traffic_history,d.aqi_history)}
  catch(e){$("#metrics").innerHTML=`<p class="muted">Could not load backend: ${e.message}. Check that the server is running.</p>`}
}
$("#analyze").addEventListener("click",async()=>{
  const out=$("#analysis");out.innerHTML='<p class="muted">Analyzing demo indicators…</p>';
  try{const d=await getJSON("/api/analyze");out.innerHTML=`<p class="muted">${d.summary} <br><small>Method: ${d.method}</small></p><div class="agent-list">${d.agents.map(a=>`<article class="agent"><span class="status ${a.status}">${a.status.toUpperCase()}</span><h3>${a.agent}</h3><p>${a.finding}</p><p><b>Recommendation:</b> ${a.recommendation}</p></article>`).join("")}</div><p class="muted small">${d.limitations.join(" · ")}</p>`}
  catch(e){out.innerHTML=`<p class="muted">Analysis failed: ${e.message}</p>`}
});
loadDashboard();
