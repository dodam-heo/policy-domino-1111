const $ = (id) => document.getElementById(id);
let dataset = [], shown = [], active = null;
let agencyFilter = '', globalAgency = '', pageSize = 60, requestId = 0;
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
    stat('기관·사업 연결',raw.summary.agency_action_count.toLocaleString()+'건'),
    stat('AI 변경 요약',(raw.analysis?.policy_ai_summaries||0).toLocaleString()+'건')
  );
}
function filtered(){
  const q=$('search').value.trim().toLowerCase(), cat=$('category').value, src=$('source').value;
  shown=dataset.filter(e=>(!q||[e.title,e.ministry,...(e.agency_names||[])].join(' ').toLowerCase().includes(q))
    &&(!cat||e.category===cat)&&(!src||e.source===src)&&(!$('high').checked||e.impact_level==='high')
    &&(!globalAgency||(e.agency_names||[]).includes(globalAgency)));
  const sort=$('sort').value;
  shown.sort((a,b)=>sort==='impact'?actionCount(b)-actionCount(a):String(sort==='effective'?b.effective_date:b.published_at).localeCompare(String(sort==='effective'?a.effective_date:a.published_at)));
  $('count').textContent=shown.length.toLocaleString()+'건';
  if(!active||!shown.some(e=>e.id===active.id))active=shown[0]||null;
  renderList(); renderDetail();
}
function renderAgencies(){
  const root=$('agencies');root.replaceChildren();
  const counts=new Map(); dataset.forEach(e=>(e.agency_names||[]).forEach(n=>counts.set(n,(counts.get(n)||0)+1)));
  const button=(name,count)=>{const b=node('button',globalAgency===name?'selected':'', (name||'전체 기관')+' '+count);b.type='button';b.onclick=()=>{globalAgency=name;pageSize=60;renderAgencies();filtered();};return b;};
  root.appendChild(button('',dataset.length));
  const groups={'중앙부처·공공기관':[],'지방자치단체':[],'교육청':[]};
  [...counts].sort((a,b)=>a[0].localeCompare(b[0],'ko')).forEach(([n,c])=>groups[/교육청|교육지원청/.test(n)?'교육청':/특별시|광역시|특별자치|도 |시청|군청|구청|시 |군 |구$/.test(n)?'지방자치단체':'중앙부처·공공기관'].push([n,c]));
  Object.entries(groups).forEach(([group,items])=>{if(!items.length)return;const d=node('details');d.open=group==='중앙부처·공공기관';add(d,node('summary','',group+' '+items.length));items.forEach(([n,c])=>d.appendChild(button(n,c)));root.appendChild(d);});
  if(!counts.size)root.appendChild(node('p','secondary','공식 사업 근거와 연결된 기관이 여기에 표시됩니다.'));
}
function renderList(){
  const list=$('events');list.replaceChildren();
  if(!shown.length){add(list,node('div','empty',$('high').checked?'현재 영향도 큼 조건에 해당하는 자료가 없습니다. 필터 초기화로 수집된 전체 정책을 확인하세요.':'해당 조건에 맞는 공식 자료가 없습니다.'));return;}
  shown.slice(0,pageSize).forEach(e=>{
    const b=node('button','event'+(e.id===active?.id?' active':''));b.type='button';
    add(b,chip(e.category),changeCount(e)?chip('변경 '+changeCount(e)+'개','blue'):chip(stage[e.comparison_status]||'대조 대기','orange'));
    if(actionCount(e))b.appendChild(chip('기관·사업 '+actionCount(e),'blue'));
    add(b,node('h3','',e.title),node('div','meta',(e.published_at||'발령일 미확인')+' · '+(e.ministry||names[e.source])));
    b.addEventListener('click',()=>{active=e;agencyFilter='';renderList();renderDetail();});
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
function workItems(action){
  const rows=action.linked_changes||[],text=rows.map(c=>c.article+' '+c.after).join(' ');
  const field=action.evidence.service_field;
  if(/가구|소득|선정|지원대상/.test(text+' '+field))return [
    '신청 안내의 가구 규모별 선정기준과 소득기준표 갱신',
    '대상자 심사에 사용하는 기준값·계산식과 적용연도 확인',
    '시행일 이후 신청·재심사 건에 적용할 기준 구분'];
  if(/금액|원|지원내용|비용/.test(text+' '+field))return [
    '사업 안내와 지급기준표의 해당 금액 갱신',
    '지급액 산식·상한액 및 업무 시스템 기준값 대조',
    '시행일 기준 지급 대상과 적용 시점 확인'];
  return ['공식 운영기준의 해당 조문·항목 대조','업무 안내·심사 절차·관련 서식의 수정 항목 확인'];
}

async function renderDetail(){
  const ticket=++requestId;
  if(active?.detail_url && !detailCache.has(active.id)){
    $('detail').replaceChildren(node('div','empty','정책 상세를 불러오는 중입니다.'));
    try{const response=await fetch(active.detail_url);if(!response.ok)throw new Error('HTTP '+response.status);detailCache.set(active.id,await response.json());}
    catch(error){if(ticket===requestId)$('detail').replaceChildren(node('div','warning','상세 로딩 실패: '+error.message));return;}
  }
  if(ticket!==requestId)return;
  const root=$('detail');root.replaceChildren();
  if(!active){add(root,node('div','empty','검색 조건에 맞는 정책이 없습니다.'));return;}
  const e=detailCache.get(active.id)||active;
  history.replaceState(null,"","#"+encodeURIComponent(e.id));
  add(root,chip(e.category,'blue'),node('h2','',e.title));
  add(root,node('div','sub',[e.ministry,e.published_at&&('발령 '+e.published_at),e.effective_date&&('시행 '+e.effective_date)].filter(Boolean).join(' · ')));
  add(root,external('국가법령정보센터 공식 문서 보기',e.url));
  const overview=node('section','section');
  add(overview,node('h3','','정책 변경 핵심'));
  const note=e.changes?.length
    ? '공식 종전·개정 판본에서 '+e.changes.length+'개 항목의 문구 차이를 확인했습니다.'
    : e.comparison_status==='no_text_change'
      ? '확보한 판본의 조문 텍스트에서는 변경을 확인하지 못했습니다.'
      : '공식 문서 판본은 확보됐지만 종전·개정 원문 대조가 완료되지 않았습니다.';
  add(overview,node('p','lead',e.policy_analysis?.verified?e.policy_analysis.explanation:note));
  const tableChanges=shortChanges(e.changes||[]);
  if(tableChanges.length)overview.appendChild(deltaTable(tableChanges,7));
  (e.changes||[]).filter(c=>!shortChanges([c]).length&&!/[─━┼│┬┴┌┐└┘]/.test(c.before+c.after)).slice(0,1).forEach(c=>{
    const card=node('div','key-change');add(card,node('b','',c.article||'본문 변경'));
    const [before,after]=compactDiff(c.before,c.after);
    add(card,node('p','','이전 · '+before),node('p','','변경 · '+after));overview.appendChild(card);
  });
  add(overview,node('div','secondary','검증 상태 · '+(stage[e.comparison_status]||e.comparison_status)));
  root.appendChild(overview);
  const agency=node('section','section');
  const actions=e.institutions||[];
  const head=node('div','section-head');
  add(head,node('h3','','영향받는 공공기관·사업'),chip(actions.length+'건','blue'));agency.appendChild(head);
  if(!actions.length){
    add(agency,node('p','warning','현재 확보한 공식 운영근거에서 이 변경과 연결된 기관·사업을 확인하지 못했습니다.'));
  }else{
    const unique=[...new Set(actions.map(x=>x.agency))].sort();
    const filters=node('div','agency-filters');
    ['',...unique].forEach(name=>{
      const b=node('button',agencyFilter===name?'active':'',name||'전체 기관');
      b.addEventListener('click',()=>{agencyFilter=name;renderDetail();});
      filters.appendChild(b);
    });
    agency.appendChild(filters);
    actions.filter(x=>!agencyFilter||x.agency===agencyFilter).forEach(x=>{
      const item=node('article','agency-item');
      add(item,node('strong','',x.agency),node('div','secondary','공공서비스 · '+x.service));
      add(item,node('p','action-text',x.required_change));
      if(e.effective_date)add(item,chip('적용 시점 '+e.effective_date,'blue'));
      const todos=node('ul','work-items');workItems(x).forEach(t=>todos.appendChild(node('li','',t)));item.appendChild(todos);
      const linked=x.linked_changes||[{article:x.changed_clause,before:x.before,after:x.after}];
      const compact=shortChanges(linked);
      if(compact.length)item.appendChild(deltaTable(compact,6));
      const delta=node('details');add(delta,node('summary','','연결된 변경 근거 '+linked.length+'개 펼치기'));
      linked.forEach(c=>delta.appendChild(changeCard(c)));item.appendChild(delta);
      if(x.ai_analysis?.verified){
        const ai=node('details','');
        add(ai,node('summary','','검증된 AI 설명'),node('p','proof',x.ai_analysis.explanation));
        item.appendChild(ai);
      }
      add(item,node('div','proof','적용 항목 · '+x.evidence.service_field));
      const more=node('details','');
      add(more,node('summary','','공식 운영기준·연결 근거'),node('p','proof',x.evidence.service_quote),node('p','proof',x.evidence.reference_quote+(x.evidence.delegation_quote?'\n상위법 위임 근거 · '+x.evidence.delegation_quote:'')));
      add(item,more,external('사업 근거 자료',x.service_url));
      agency.appendChild(item);
    });
  }
  root.appendChild(agency);
  const compare=node('section','section');
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
    renderSummary(data);active=dataset[0]||null;
    for(const id of ['search','category','source','high','sort'])$(id).addEventListener(id==='search'?'input':'change',filtered);
    const wanted=decodeURIComponent(location.hash.slice(1));active=dataset.find(e=>e.id===wanted)||active;
    if(wanted)$('high').checked=false;
    $('more').onclick=()=>{pageSize+=60;renderList();};
    $('reset').onclick=()=>{$('search').value='';$('category').value='';$('source').value='';$('high').checked=false;globalAgency='';renderAgencies();filtered();};
    $('freshness').textContent='자료 생성 '+new Date(data.generated_at).toLocaleString('ko-KR')+' · 공식 판본 '+data.total_source_versions_saved.toLocaleString()+'건';
    renderAgencies();filtered();
  }catch(e){
    $('summary').replaceChildren(node('span','secondary','공식 자료를 읽지 못했습니다.'));
    $('detail').replaceChildren(node('div','warning','데이터 로딩 실패: '+e.message));
  }
}
main();