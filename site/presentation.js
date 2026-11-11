/* Policy list navigation by priority, status, and legal source. */
(function (global) {
  "use strict";
  const MODES=Object.freeze(["all","new","repealed","impact"]);
  function category(event) {
    if(event.kind==="new")return "신규 제정";
    if(event.kind==="repealed")return "폐지";
    return "개정";
  }
  function hasInstitutionalReview(event) {
    return Array.isArray(event.institutional_reviews) &&
      event.institutional_reviews.length>0;
  }
  function highImpactScope(event) {
    return event.impact_level==="high";
  }
  function filterEvents(events,{mode="all",query="",category:topic="",source="",sort="impact",verification=""}={}) {
    if(!MODES.includes(mode))throw Error("Unsupported event filter");
    const term=String(query).trim().toLocaleLowerCase("ko-KR");
    return [...events].filter(event=>{
      if(topic&&event.topic!==topic)return false;
      if(source&&event.source!==source)return false;
      if(mode==="impact"&&!highImpactScope(event))return false;
      if(verification==="changed"&&event.comparison_status!=="changed")return false;
      if(verification==="partial"&&event.comparison_status!=="partial_unverified")return false;
      if(verification==="pending"&&
         !["original_saved_comparison_pending","no_text_change"].includes(event.comparison_status))return false;
      if(!["all","impact"].includes(mode)&&event.kind!==mode)return false;
      const searchable=[
        event.title,event.headline,event.ministry,event.topic,
        ...(event.priority_reasons||[]),...(event.agency_names||[]),
        ...(event.members||[]).flatMap(x=>[x.title,x.kind]),
        ...(event.changes||[]).flatMap(x=>[
          x.document_title,x.article,x.meaning?.label||x.category||"",
        ]),
        ...(event.institutional_reviews||[]).flatMap(x=>[
          x.institution,x.program,x.task
        ]),
        ...(event.public_service_leads||[]).flatMap(x=>[
          x.agency,x.service_name,
          ...(x.review_targets||[]).map(y=>y.field)
        ])
      ].join(" ").toLocaleLowerCase("ko-KR");
      return searchable.includes(term);
    }).sort((a,b)=>{
      const byDate=String(b.published_at||"").localeCompare(String(a.published_at||""));
      if(sort==="impact"){
        const tier=event=>({high:0,pending:1,normal:2})[event.impact_assessment?.classification||event.impact_level]??1;
        return tier(a)-tier(b)||
          (tier(a)===1 ? Number(b.impact_assessment?.possible_high||false)-Number(a.impact_assessment?.possible_high||false) : 0)||
          (Number(b.impact_assessment?.score_min??0)-Number(a.impact_assessment?.score_min??0))||
          byDate||String(a.id||"").localeCompare(String(b.id||""));
      }
      return String(b[sort==="effective"?"effective_date":"published_at"]||"").localeCompare(
        String(a[sort==="effective"?"effective_date":"published_at"]||""))||
        byDate||String(a.id||"").localeCompare(String(b.id||""));
    });
  }
  function impactGroups(event) {
    // A single institution selector for independently verified changed-clause
    // reviews and official public-service review leads. These evidence tiers
    // must never be merged into "confirmed institutional actions".
    const grouped=new Map();
    function item(agency) {
      agency=String(agency||"").trim();
      if(!agency)return null;
      if(!grouped.has(agency))grouped.set(agency,{
        agency,reviews:[],services:[],
      });
      return grouped.get(agency);
    }
    for(const review of event.institutional_reviews||[]) {
      const target=item(review.institution);
      if(target)target.reviews.push(review);
    }
    for(const service of event.public_service_leads||[]) {
      if(service.verification!=="candidate_not_confirmed")continue;
      const target=item(service.agency);
      if(target)target.services.push(service);
    }
    return [...grouped.values()].sort((a,b)=>
      a.agency.localeCompare(b.agency,"ko-KR"));
  }
  function overview(events,progress={}) {
    const agencies=new Set(events.flatMap(e=>
      (e.agency_names||(e.institutional_reviews||[]).map(x=>x.institution)).filter(Boolean)));
    return {
      events:events.length,institutions:agencies.size,
      actions:events.reduce((sum,e)=>sum+(e.review_count??(e.institutional_reviews||[]).length),0),
      sources:Number(progress.indexed_documents||0),
      comparedDocuments:Number(progress.verified_document_changes||0)
    };
  }
  global.PolicyDominoView=Object.freeze({
    MODES,category,hasInstitutionalReview,highImpactScope,
    filterEvents,impactGroups,overview
  });
})(window);

