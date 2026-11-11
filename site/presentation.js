/* One policy list, five evidence-based navigation choices. */
(function (global) {
  "use strict";
  const MODES=Object.freeze(["all","new","amended","repealed","impact"]);
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
  function filterEvents(events,{mode="all",query="",category:topic="",source="",sort="published"}={}) {
    if(!MODES.includes(mode))throw Error("Unsupported event filter");
    const term=String(query).trim().toLocaleLowerCase("ko-KR");
    return [...events].filter(event=>{
      if(topic&&event.topic!==topic)return false;
      if(source&&event.source!==source)return false;
      if(mode==="impact"&&!highImpactScope(event))return false;
      if(mode!=="all"&&mode!=="impact"&&event.kind!==mode)return false;
      const searchable=[
        event.title,event.headline,event.ministry,event.topic,...(event.agency_names||[]),
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
    }).sort((a,b)=>
      (sort==="impact"? (b.review_count||0)-(a.review_count||0):String(b[sort==="effective"?"effective_date":"published_at"]||"").localeCompare(String(a[sort==="effective"?"effective_date":"published_at"]||"")))||
      (b.institution_count||0)-(a.institution_count||0)||
      String(a.id||"").localeCompare(String(b.id||"")));
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

