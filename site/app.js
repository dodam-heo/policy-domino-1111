const $ = (id) => document.getElementById(id);
let dataset = [], shown = [], active = null;
let agencyFilter = '', revisionFilter = 'all', pageSize = 60, requestId = 0, detailActions = [];
let listScroll = 0;
const detailCache = new Map();
const changeCount = e => e.change_count ?? e.changes?.length ?? 0;
const actionCount = e => e.action_count ?? e.institutions?.length ?? 0;
const names = {law:'법령',admrul:'행정규칙',ordin:'자치법규'};
const stage = {
  changed:'신구 변경 확인',no_text_change:'본문 변경 없음',
  partial_unverified:'원문·첨부 추가 확인 필요',
  original_saved_comparison_pending:'신구 대조 대기'
};
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = String(text);
  return el;
}
function add(parent,...children){children.forEach(child=>parent.appendChild(child));return parent;}
function external(text,url){
  if (!url || !url.startsWith('https://')) return node('span','secondary','공식 원문 링크 확인 필요');
  const a=node('a','source-link',text);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function chip(text,css=''){return node('span','chip '+css,text);}
function stat(label,value){const el=node('div','stat');add(el,node('b','',value),node('span','',label));return el;}
function renderSummary(raw){
  $('summary').replaceChildren(
    stat('확보된 공식 판본',raw.total_source_versions_saved.toLocaleString()+'건'),
    stat('확인된 신구 변경',raw.summary.with_verified_changes.toLocaleString()+'건'),
    stat('연결된 기관',new Set(raw.events.flatMap(e=>e.agency_names||[])).size.toLocaleString()+'곳'),
    stat('기관별 검토항목',raw.summary.agency_action_count.toLocaleString()+'건')
  );
}
function renderCoverage(data){
  const c=data.coverage||{};
  $('coverage-summary').textContent='수집 범위 · 공공기관 명부 '+(c.alio_public_institutions||0)+'곳 · 정부24 사업 '+(c.gov24_programs||0).toLocaleString()+'건';
  $('coverage-details').replaceChildren(node('p','','알리오플러스 기관 명부 '+(c.alio_public_institutions||0)+'곳 / 공식 명부 '+(c.alio_reported||'미확인')+'곳'),node('p','','정부24 보관 사업 '+(c.gov24_programs||0).toLocaleString()+'건 · 운영기관 '+(c.gov24_agencies||0)+'곳'),node('p','secondary','기관 명부의 수집과 정책별 영향 확인은 별도입니다. 정부24의 최신 전체 갱신 여부는 아직 확인되지 않았습니다.'),node('p','secondary','AI 정책 요약 '+(data.analysis?.policy_ai_summaries||0)+'건 · 남은 요약 '+(data.analysis?.policy_summaries_pending||0)+'건'));
  let records=[];
  const draw=()=>{const q=$('registry-search').value.trim().toLowerCase();const rows=records.filter(x=>x.name.toLowerCase().includes(q));$('registry-caption').textContent='알리오플러스 공식 기관 명부 · '+records.length+'곳 중 '+rows.length+'곳 표시';$('registry-results').replaceChildren(...rows.map(x=>{const row=node('div','registry-row');add(row,node('span','',x.name),external('공식 기관정보 ↗',x.url));return row;}));};
  $('registry-open').onclick=async()=>{if(!records.length){try{const r=await fetch('institutions.json');if(!r.ok)throw new Error('명부 로딩 실패');records=(await r.json()).records||[];}catch(e){$('registry-caption').textContent=e.message;}}draw();$('registry-dialog').showModal();};
  $('registry-close').onclick=()=>$('registry-dialog').close();$('registry-search').oninput=draw;
}

function filtered(){
  const q=$('search').value.trim().toLowerCase(), cat=$('category').value, src=$('source').value;
  shown=dataset.filter(e=>(!q||[e.title,e.ministry,...(e.agency_names||[])].join(' ').toLowerCase().includes(q))
    &&(!cat||e.category===cat)&&(!src||e.source===src)&&(!$('high').checked||e.impact_level==='high')
    &&(revisionFilter==='all'||(revisionFilter==='new'&&/제정|신규|신설/.test(e.revision||''))||(revisionFilter==='amended'&&/개정/.test(e.revision||''))||(revisionFilter==='repealed'&&/폐지/.test(e.revision||''))));
  const sort=$('sort').value;
  shown.sort((a,b)=>sort==='impact'?actionCount(b)-actionCount(a):String(sort==='effective'?b.effective_date:b.published_at).localeCompare(String(sort==='effective'?a.effective_date:a.published_at)));
  $('count').textContent=shown.length.toLocaleString()+'건';
  if(!active||!shown.some(e=>e.id===active.id))active=shown[0]||null;
  renderList(); if(document.body.classList.contains('mode-detail'))renderDetail();
}
function scopedAgencyCounts(actions){
  const counts=new Map();
  actions.forEach(a=>counts.set(a.agency,(counts.get(a.agency)||0)+1));
  return counts;
}
async function loadEventDetail(event, fetcher=fetch){
  if(detailCache.has(event.id))return detailCache.get(event.id);
  const response=await fetcher(event.detail_url);
  if(!response.ok)throw new Error('HTTP '+response.status);
  const payload=await response.json();
  if(payload.id!==event.id)throw new Error('선택한 정책과 상세 자료가 일치하지 않습니다.');
  detailCache.set(event.id,payload);
  return payload;
}

function renderAgencies(actions=detailActions){
  const root=$('agencies');root.replaceChildren();
  const counts=scopedAgencyCounts(actions), types=new Map(actions.map(a=>[a.agency,a.agency_type||'']));
  if(agencyFilter&&!counts.has(agencyFilter))agencyFilter='';
  const button=(name,count)=>{const b=node('button',agencyFilter===name?'selected':'',name?name+' · '+count:'전체 기관 · '+counts.size);b.type='button';b.setAttribute('aria-pressed',String(agencyFilter===name));b.onclick=()=>{agencyFilter=name;renderDetail();};return b;};
  root.appendChild(button('',counts.size));
  const term=$('agency-search').value.trim().toLocaleLowerCase('ko-KR');
  const groups={'중앙부처·공공기관':[],'지방자치단체':[],'교육청':[]};
  [...counts].sort((a,b)=>a[0].localeCompare(b[0],'ko')).forEach(([n,c])=>{
    if(term&&!n.toLocaleLowerCase('ko-KR').includes(term))return;
    const t=types.get(n);const group=/교육청|교육지원청/.test(n)?'교육청':/시군구|광역|지방자치/.test(t)||/특별시|광역시|특별자치|도 |시청|군청|구청|시 |군 |구$/.test(n)?'지방자치단체':'중앙부처·공공기관';groups[group].push([n,c]);
  });
  Object.entries(groups).forEach(([group,items])=>{if(!items.length)return;const d=node('details');d.open=group==='중앙부처·공공기관'||items.some(([n])=>n===agencyFilter);add(d,node('summary','',group+' '+items.length));items.forEach(([n,c])=>d.appendChild(button(n,c)));root.appendChild(d);});
  if(!counts.size)root.appendChild(node('p','secondary','이 정책과 근거가 연결된 기관이 아직 없습니다.'));
  else if(!Object.values(groups).some(rows=>rows.length))root.appendChild(node('p','secondary','검색된 기관이 없습니다.'));
}
function selectPolicy(e, push=true){
  if(!e)return;
  if(document.body.classList.contains('mode-list'))listScroll=window.scrollY;
  active=e;agencyFilter='';$('agency-search').value='';
  document.body.classList.replace('mode-list','mode-detail');
  if(push)history.pushState({view:'detail'},'', '#'+encodeURIComponent(e.id));
  renderList();renderDetail();window.scrollTo({top:0,behavior:'smooth'});
}
function renderPolicySwitcher(){
  const pool=shown.length?shown:dataset;
  $('policy-switcher').replaceChildren(...pool.map(e=>{const o=node('option','',e.title);o.value=e.id;o.selected=e.id===active?.id;return o;}));
  const index=pool.findIndex(e=>e.id===active?.id);
  $('previous-policy').disabled=index<=0;
  $('next-policy').disabled=index<0||index===pool.length-1;
  $('previous-policy').onclick=()=>selectPolicy(pool[index-1]);
  $('next-policy').onclick=()=>selectPolicy(pool[index+1]);
}

function renderList(){
  const list=$('events');list.replaceChildren();
  if(!shown.length){add(list,node('div','empty',$('high').checked?'현재 영향도 큼 조건에 해당하는 자료가 없습니다. 필터 초기화로 수집된 전체 정책을 확인하세요.':'해당 조건에 맞는 공식 자료가 없습니다.'));return;}
  shown.slice(0,pageSize).forEach(e=>{
    const b=node('button','event'+(e.id===active?.id?' active':''));b.type='button';
    add(b,chip(e.category),changeCount(e)?chip('변경 '+changeCount(e)+'개','blue'):chip(stage[e.comparison_status]||'대조 대기','orange'));
    if(actionCount(e))b.appendChild(chip('기관·사업 '+actionCount(e),'blue'));
    add(b,node('h3','',e.title),node('div','meta',(e.ministry||names[e.source])+' · '+(e.published_at||'발령일 미확인')));
    if(e.policy_analysis?.verified)b.appendChild(node('p','event-summary',e.policy_analysis.explanation));
    const foot=node('div','event-foot');add(foot,node('span','',e.effective_date?'시행 '+e.effective_date:'시행일 확인 중'),node('span','event-arrow','영향 확인 ↗'));b.appendChild(foot);
    b.addEventListener('click',()=>selectPolicy(e));
    list.appendChild(b);
  });
  $('more').hidden=shown.length<=pageSize;
}
function diffFragments(a,b){
  // Highlight changed text without interpreting any source HTML.
  a=String(a||'');b=String(b||'');
  let prefix=0;while(prefix<Math.min(a.length,b.length)&&a[prefix]===b[prefix])prefix++;
  let suffix=0;while(suffix<Math.min(a.length,b.length)-prefix&&a[a.length-1-suffix]===b[b.length-1-suffix])suffix++;
  const left=node('div','text'),right=node('div','text');
  const mark=(parent,part)=>{if(part)parent.appendChild(node('mark','',part));};
  add(left,document.createTextNode(a.slice(0,prefix)));mark(left,a.slice(prefix,a.length-suffix));left.appendChild(document.createTextNode(suffix?a.slice(a.length-suffix):''));
  add(right,document.createTextNode(b.slice(0,prefix)));mark(right,b.slice(prefix,b.length-suffix));right.appendChild(document.createTextNode(suffix?b.slice(b.length-suffix):''));
  return [left,right];
}
function compactDiff(a,b){
  a=String(a||'');b=String(b||'');let p=0,z=0;
  while(p<Math.min(a.length,b.length)&&a[p]===b[p])p++;
  while(z<Math.min(a.length,b.length)-p&&a[a.length-z-1]===b[b.length-z-1])z++;
  const excerpt=t=>(p>45?'…':'')+t.slice(Math.max(0,p-45),Math.min(t.length-z+45,p+320))+(t.length-z+45<t.length?'…':'');
  return [excerpt(a),excerpt(b)];
}
function changeCard(c){
  const wrapper=node('div',''),heading=node('h3','',c.article||'개정 조문');
  const grid=node('div','two'),before=node('div','comparison'),after=node('div','comparison after');
  const [oldText,newText]=diffFragments(c.before,c.after);
  add(before,node('div','head','개정 전'),oldText);
  add(after,node('div','head','개정 후'),newText);
  add(grid,before,after);add(wrapper,heading,grid);
  return wrapper;
}
function deltaTable(changes, limit=12){
  const wrap=node('div','delta-wrap'),table=node('table','delta-table');
  const head=node('tr');['변경 항목','이전','변경'].forEach(t=>head.appendChild(node('th','',t)));
  const thead=node('thead');thead.appendChild(head);table.appendChild(thead);
  const body=node('tbody');
  changes.slice(0,limit).forEach(c=>{const row=node('tr');
    add(row,node('td','',c.article||c.clause||'본문'),node('td','',c.before),node('td','',c.after));body.appendChild(row);});
  table.appendChild(body);wrap.appendChild(table);return wrap;
}
function shortChanges(changes){return changes.filter(c=>String(c.before).length<100&&String(c.after).length<100);}

async function renderDetail(){
  const ticket=++requestId;
  const selected=active;
  if(selected?.detail_url && !detailCache.has(selected.id)){
    detailActions=[];renderAgencies();
    $('detail').replaceChildren(node('div','empty','정책 상세를 불러오는 중입니다.'));
    try{await loadEventDetail(selected);}
    catch(error){if(ticket===requestId)$('detail').replaceChildren(node('div','warning','상세 로딩 실패: '+error.message));return;}
  }
  if(ticket!==requestId||active?.id!==selected?.id)return;
  const root=$('detail');root.replaceChildren();
  if(!active){add(root,node('div','empty','검색 조건에 맞는 정책이 없습니다.'));return;}
  const e=detailCache.get(active.id)||active;
  detailActions=e.institutions||[];renderAgencies();renderPolicySwitcher();
  history.replaceState(null,"","#"+encodeURIComponent(e.id));
  add(root,node('p','eyebrow','POLICY IMPACT REPORT'),chip(e.category,'blue'),node('h2','',e.title));
  add(root,node('div','sub',[e.ministry,e.published_at&&('발령 '+e.published_at),e.effective_date&&('시행 '+e.effective_date)].filter(Boolean).join(' · ')));
  add(root,external('국가법령정보센터 공식 문서 보기',e.url));
  const nav=node('nav','detail-tabs');[['변경 핵심','policy-overview'],['기관·사업 영향','policy-agencies'],['신구 비교·근거','policy-comparison']].forEach(([label,id])=>{const a=node('a','',label);a.href='#'+id;a.onclick=ev=>{ev.preventDefault();document.getElementById(id)?.scrollIntoView({behavior:'smooth'});};nav.appendChild(a);});root.appendChild(nav);
  const overview=node('section','section');overview.id='policy-overview';
  add(overview,node('h3','','정책 변경 핵심'));
  const note=e.changes?.length
    ? '공식 종전·개정 판본에서 '+e.changes.length+'개 항목의 문구 차이를 확인했습니다.'
    : e.comparison_status==='no_text_change'
      ? '확보한 판본의 조문 텍스트에서는 변경을 확인하지 못했습니다.'
      : '공식 문서 판본은 확보됐지만 종전·개정 원문 대조가 완료되지 않았습니다.';
  add(overview,node('p','lead',e.policy_analysis?.verified?e.policy_analysis.explanation:note));
  const tableChanges=shortChanges(e.changes||[]);
  if(tableChanges.length)overview.appendChild(deltaTable(tableChanges,4));
  (e.changes||[]).filter(c=>!shortChanges([c]).length&&!/[─━┼│┬┴┌┐└┘]/.test(c.before+c.after)).slice(0,1).forEach(c=>{
    const card=node('details','key-change');add(card,node('summary','',c.article||'본문 변경'));
    const [before,after]=compactDiff(c.before,c.after);
    add(card,node('p','','이전 · '+before),node('p','','변경 · '+after));overview.appendChild(card);
  });
  add(overview,node('div','secondary','검증 상태 · '+(stage[e.comparison_status]||e.comparison_status)));
  root.appendChild(overview);
  const agency=node('section','section');agency.id='policy-agencies';
  const actions=e.institutions||[];
  const head=node('div','section-head');
  add(head,node('h3','','영향받는 공공기관·사업'),chip(new Set(actions.map(x=>x.agency)).size+'곳 · '+actions.length+'개 검토항목','blue'));agency.appendChild(head);
  if(!actions.length){
    add(agency,node('p','warning','현재 확보한 공식 운영근거에서 이 변경과 연결된 기관·사업을 확인하지 못했습니다.'));
  }else{
    const unique=[...new Set(actions.map(x=>x.agency))].sort();
    actions.filter(x=>!agencyFilter||x.agency===agencyFilter).forEach(x=>{
      const item=node('article','agency-item');
      add(item,node('strong','',x.agency),node('div','secondary','공공서비스 · '+x.service));
      add(item,node('p','action-text',x.ai_analysis?.verified?x.ai_analysis.explanation:x.required_change));
      if(e.effective_date)add(item,chip('적용 시점 '+e.effective_date,'blue'));
      const linked=x.linked_changes||[{article:x.changed_clause,before:x.before,after:x.after}];
      const compact=shortChanges(linked);
      if(compact.length)item.appendChild(deltaTable(compact,6));
      const delta=node('details');add(delta,node('summary','','연결된 변경 근거 '+linked.length+'개 펼치기'));
      linked.forEach(c=>delta.appendChild(changeCard(c)));item.appendChild(delta);
      add(item,node('div','proof','적용 항목 · '+x.evidence.service_field));
      const more=node('details','');
      add(more,node('summary','','공식 운영기준·연결 근거'),node('p','proof',x.evidence.service_quote),node('p','proof',x.evidence.reference_quote+(x.evidence.delegation_quote?'\n상위법 위임 근거 · '+x.evidence.delegation_quote:'')));
      add(item,more,external('사업 근거 자료',x.service_url));
      agency.appendChild(item);
    });
  }
  root.appendChild(agency);
  const compare=node('section','section');compare.id='policy-comparison';
  const title=node('div','section-head');
  add(title,node('h3','','실제 변경사항 · 신구 비교'),chip((e.changes||[]).length+'개','blue'));
  compare.appendChild(title);
  if(e.changes?.length){
    const details=node('details','');
    details.open=false;
    add(details,node('summary','','개정 전·후 조문 펼치기'));
    e.changes.forEach(c=>details.appendChild(changeCard(c)));
    compare.appendChild(details);
  } else add(compare,node('div','warning','비교할 수 있는 종전·개정 본문을 더 확보해야 합니다.'));
  if(e.unresolved?.length){
    add(compare,node('p','secondary','별표·첨부 또는 대응본 미확보: '+e.unresolved.length+'개 항목. 미확인 사항은 변경이라고 단정하지 않습니다.'));
  }
  if(e.prior_url)compare.appendChild(external('종전 공식 판본 보기',e.prior_url));
  root.appendChild(compare);
}
async function main(){
  try{
    const response=await fetch('data.json',{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const data=await response.json();
    if(data.schema!=='policy-domino-unified-ui-v1')throw new Error('데이터 규격 불일치');
    dataset=data.events||[];
    renderSummary(data);renderCoverage(data);active=dataset[0]||null;
    for(const id of ['search','category','source','high','sort'])$(id).addEventListener(id==='search'?'input':'change',filtered);
    const wanted=decodeURIComponent(location.hash.slice(1));active=dataset.find(e=>e.id===wanted)||active;
    if(wanted){$('high').checked=false;document.body.classList.replace('mode-list','mode-detail');}
    $('back').onclick=()=>{document.body.classList.replace('mode-detail','mode-list');history.replaceState(null,'',location.pathname);window.scrollTo({top:listScroll});};
    $('policy-switcher').onchange=()=>selectPolicy(dataset.find(e=>e.id===$('policy-switcher').value));
    $('agency-search').oninput=()=>renderAgencies();
    window.addEventListener('popstate',()=>{const id=decodeURIComponent(location.hash.slice(1));const e=dataset.find(x=>x.id===id);if(e)selectPolicy(e,false);else{document.body.classList.replace('mode-detail','mode-list');window.scrollTo({top:listScroll});}});
    document.querySelectorAll('[data-revision]').forEach(b=>b.onclick=()=>{revisionFilter=b.dataset.revision;document.querySelectorAll('[data-revision]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});pageSize=60;filtered();});
    ['list','cards'].forEach(view=>$('view-'+view).onclick=()=>{document.body.classList.toggle('view-list',view==='list');['list','cards'].forEach(v=>{$('view-'+v).classList.toggle('active',v===view);$('view-'+v).setAttribute('aria-pressed',String(v===view));});});
    $('more').onclick=()=>{pageSize+=60;renderList();};
    $('reset').onclick=()=>{$('search').value='';$('category').value='';$('source').value='';$('high').checked=false;revisionFilter='all';document.querySelectorAll('[data-revision]').forEach(x=>{x.classList.toggle('active',x.dataset.revision==='all');x.setAttribute('aria-pressed',String(x.dataset.revision==='all'));});renderAgencies();filtered();};
    $('freshness').textContent='자료 생성 '+new Date(data.generated_at).toLocaleString('ko-KR')+' · 공식 판본 '+data.total_source_versions_saved.toLocaleString()+'건';
    renderAgencies();filtered();
  }catch(e){
    $('summary').replaceChildren(node('span','secondary','공식 자료를 읽지 못했습니다.'));
    $('detail').replaceChildren(node('div','warning','데이터 로딩 실패: '+e.message));
  }
}
main();