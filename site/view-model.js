/* Unified data boundary for NEXT's master-detail presentation. */
(function(global){
  'use strict';
  const detailCache=new Map();
  const stages={changed:'신구 변경 확인',no_text_change:'본문 변경 없음',partial_unverified:'원문·첨부 추가 확인 필요',original_saved_comparison_pending:'신구 대조 대기'};
  const stageLabel=status=>stages[status]||'신구 대조 대기';
  const isShort=c=>String(c.before||'').length<100&&String(c.after||'').length<100;
  function focus(a,b){
    a=String(a||'');b=String(b||'');let p=0,z=0;
    while(p<Math.min(a.length,b.length)&&a[p]===b[p])p++;
    while(z<Math.min(a.length,b.length)-p&&a[a.length-z-1]===b[b.length-z-1])z++;
    const side=t=>({prefix:(p>45?'…':'')+t.slice(Math.max(0,p-45),p),changed:t.slice(p,Math.min(t.length-z,p+300))+(t.length-z-p>300?'…':''),truncated:t.length-z-p>300,suffix:t.slice(t.length-z,t.length-z+45)+(z>45?'…':'')});
    return [{before:side(a),after:side(b)}];
  }
  function changeView(c,e){return {...c,document_id:e.id,document_title:e.title,source_url:e.url,meaning:{label:c.article?.startsWith('표 ')?'기준표 변경':'조문 변경',description:(c.article||'본문')+'의 변경 전·후 공식 원문을 대조했습니다.',focus:c.focus?.length?c.focus:focus(c.before,c.after),diff_window_count:c.diff_window_count||0}};}
  function eventView(raw){
    const changes=(raw.changes||[]).map(c=>changeView(c,raw)),analysis=raw.policy_analysis?.verified?raw.policy_analysis:null;
    return {...raw,raw,loaded:Array.isArray(raw.changes),topic:raw.category,
      kind:/폐지/.test(raw.revision||'')?'repealed':/제정|신규|신설/.test(raw.revision||'')?'new':'amended',
      headline:analysis?.explanation||(raw.change_count||changes.length?`공식 판본에서 ${raw.change_count||changes.length}개 항목의 문구 차이를 확인했습니다.`:stageLabel(raw.comparison_status)),
      verification:raw.comparison_status==='changed'?'verified':'partial',changes,
      source_documents:[raw.id],source_count:1,members:[{id:raw.id,title:raw.title,kind:raw.kind,url:raw.url}],
      institution_count:raw.agency_names?.length??new Set((raw.institutions||[]).map(x=>x.agency)).size,
      review_count:raw.action_count??raw.institutions?.length??0,
      ai_count:analysis?1:0,ai_summaries:analysis?[{document_id:raw.id,article:"정책 변경 요약",summary:analysis.explanation,before_quote:analysis.old_quote,after_quote:analysis.new_quote,question:""}]:[],public_service_leads:[],dependent_rules:[],
      institutional_reviews:(raw.institutions||[]).map(x=>({institution:x.agency,agency_type:x.agency_type,program:x.service,article:x.changed_clause,
        task:x.ai_analysis?.verified?x.ai_analysis.explanation:x.required_change,basis_tier:'verified_program_citation',
        basis_quote:[x.evidence?.service_field,x.evidence?.service_quote,x.evidence?.reference_quote,x.evidence?.delegation_quote].filter(Boolean).join('\n'),
        source_url:x.policy_url,program_url:x.service_url,effective_date:raw.effective_date,
        linked_changes:x.linked_changes||[{article:x.changed_clause,before:x.before,after:x.after}],event:{id:raw.id,title:raw.title,url:raw.url}}))};
  }
  async function loadEventDetail(event,fetcher=global.fetch.bind(global)){
    const id=event.id;if(detailCache.has(id))return detailCache.get(id);
    const response=await fetcher(event.detail_url);if(!response.ok)throw Error('HTTP '+response.status);
    const payload=await response.json();if(payload.id!==id)throw Error('선택한 정책과 상세 자료가 일치하지 않습니다.');
    detailCache.set(id,payload);return payload;
  }
  global.PolicyDominoModel=Object.freeze({eventView,changeView,stageLabel,isShort,loadEventDetail,detailCache});
})(window);
