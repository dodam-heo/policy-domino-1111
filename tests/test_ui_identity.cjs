const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const window={fetch:()=>{throw Error('unexpected fetch')}};
const context=vm.createContext({window});
for(const file of ['site/view-model.js','site/presentation.js'])vm.runInContext(fs.readFileSync(file,'utf8'),context);
const {loadEventDetail,detailCache,eventView}=window.PolicyDominoModel;
const view=window.PolicyDominoView;
const scopedAgencyCounts=actions=>new Map(actions.map(a=>[a.agency,1]));
(async()=>{
  const education=eventView({id:'education',title:'교육급여',revision:'개정',category:'급여·지원기준',source:'admrul',impact_level:'high',changes:[],institutions:[{agency:'교육부'},{agency:'경기도 수원시'}]});
  const housing=eventView({id:'housing',title:'주거급여',changes:[],institutions:[{agency:'서울특별시 동대문구'}]});
  assert.equal(view.impactGroups(education).some(x=>x.agency.includes('동대문')),false);
  assert.equal(view.impactGroups(housing).length,1);
  assert.equal(view.filterEvents([education,housing],{mode:'impact'}).length,1);
  assert.equal(view.filterEvents([education,housing],{category:'급여·지원기준',source:'admrul',query:'수원시'}).length,1);
  assert.equal(view.filterEvents([education,housing],{mode:'all'}).length,2);
  const filterHtml=fs.readFileSync('site/index.html','utf8');
  const requiredModes=['all','new','repealed','impact'];
  assert.deepEqual(Array.from(view.MODES),requiredModes);
  const positions=requiredModes.map(id=>filterHtml.indexOf('id="mode-'+id+'"'));
  assert.ok(positions.every(position=>position>=0));
  assert.ok(positions.every((position,i)=>i===0||position>positions[i-1]));
  assert.ok(!filterHtml.includes('id="mode-amended"'));
  assert.ok(filterHtml.includes('>영향도 큼</button>'));
  assert.ok(!filterHtml.includes('영향도 큼만 보기'));
  assert.equal(view.filterEvents([education,housing],{mode:'all',verification:'changed'}).length,0);
  assert.equal(view.filterEvents([education,housing],{mode:'all',verification:'partial'}).length,0);
  const change=eventView({id:'annual',title:'지원기준 고시',category:'급여·지원기준',
    comparison_status:'changed',impact_level:'high',
    priority_reasons:['급여·지원금·소득 기준 변경'],
    primary_change_summary:'표 1 · 100원 → 120원',
    institutions:[{agency:'공식 기관',service:'지원사업',required_change:'심사금액 정비',
      status:'review_of_verified_citation',evidence:{reference_quote:'법 제1조'},
      ai_analysis:{verified:true,explanation:'심사금액 100원에서 120원으로 변경 검토',old_quote:'100원',
        new_quote:'120원',program_quote:'100원'}}]});
  assert.ok(change.headline.includes('100원 → 120원'));
  assert.equal(change.institutional_reviews[0].task,'심사금액 정비');
  assert.ok(change.institutional_reviews[0].ai.work_impact.includes('120원'));
  assert.equal(view.filterEvents([education,housing,change],{mode:'impact'}).length,2);
  assert.equal(view.filterEvents([education,housing,change],{mode:'all',verification:'changed'}).length,1);
  assert.throws(()=>view.filterEvents([education,housing,change],{mode:'linked'}),/Unsupported event filter/);
  // Default ranking: confirmed high first, high-potential pending second,
  // general last; all ties break by newest promulgation date.
  const ranked=[
    {id:'normal',title:'경미한 내부 정비',impact_level:'normal',published_at:'2026-11-11',
      impact_assessment:{classification:'normal',score_min:40}},
    {id:'pending',title:'확인 중인 전국 기준',impact_level:'pending',published_at:'2026-11-10',
      impact_assessment:{classification:'pending',score_min:60,possible_high:true}},
    {id:'high-older',title:'전국 급여 기준',impact_level:'high',published_at:'2026-01-01',
      impact_assessment:{classification:'high',score_min:75}},
    {id:'high-newer',title:'새로운 공공서비스 기준',impact_level:'high',published_at:'2026-10-01',
      impact_assessment:{classification:'high',score_min:75}}
  ];
  assert.deepEqual(Array.from(view.filterEvents(ranked,{sort:'impact'}).map(e=>e.id)),
    ['high-newer','high-older','pending','normal']);
  assert.deepEqual(Array.from(view.filterEvents(ranked,{sort:'impact',mode:'impact'}).map(e=>e.id)),
    ['high-newer','high-older']);
  assert.deepEqual(Array.from(view.filterEvents(ranked,{sort:'published'}).map(e=>e.id)),
    ['normal','pending','high-newer','high-older']);
  assert.deepEqual(Array.from(scopedAgencyCounts([{agency:'교육부'},{agency:'경기도 수원시'}]).keys()),['교육부','경기도 수원시']);
  const pending={};
  const fetcher=url=>new Promise(resolve=>pending[url]=resolve);
  const a=loadEventDetail({id:'education',detail_url:'education.json'},fetcher);
  const b=loadEventDetail({id:'housing',detail_url:'housing.json'},fetcher);
  pending['housing.json']({ok:true,json:async()=>({id:'housing',title:'주거급여'})});
  await b;
  pending['education.json']({ok:true,json:async()=>({id:'education',title:'교육급여'})});
  await a;
  assert.equal(detailCache.get('education').title,'교육급여');
  assert.equal(detailCache.get('housing').title,'주거급여');
  await assert.rejects(loadEventDetail({id:'other',detail_url:'other.json'},async()=>({ok:true,json:async()=>({id:'housing'})})),/일치하지/);
  assert.equal(detailCache.has('other'),false);
  console.log('UI_IDENTITY_PASS: selected-policy agencies, reversed responses, mismatched payload rejection');
})().catch(e=>{console.error(e);process.exit(1)});
