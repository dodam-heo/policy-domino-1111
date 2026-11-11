(() => {
  "use strict";
  const $ = name => document.getElementById(name);
  const view = window.PolicyDominoView;
  const model = window.PolicyDominoModel;
  let requestId=0;
  const state = {
    data: null, events: [], selected: null, mode: "impact", category:"",source:"",sort:"impact",
    query: "", visible: 60, institutionFilter: "all"
  };
  const mobile = () => window.matchMedia("(max-width:850px)").matches;
  const num = n => Number(n || 0).toLocaleString("ko-KR");
  const compact = (value, limit = 130) => {
    const str = String(value || "").replace(/\s+/g, " ").trim();
    return str.length > limit ? str.slice(0, limit) + "…" : str;
  };
  const create = (tag, className = "", value) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = String(value);
    return el;
  };
  const append = (parent,...children) => children.forEach(c => {
    if (c) parent.appendChild(c);
  });
  function link(url, label) {
    try {
      const valid = new URL(url);
      // Official ministries and institutions use many independent domains.
      // Keep the protocol safe without dropping evidence links outside the
      // central government's small historical host allow-list.
      if (valid.protocol !== "https:" || valid.username || valid.password ||
          !valid.hostname.includes(".")) return null;
      const a = create("a","official-link",label);
      a.href = valid.href;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      return a;
    } catch { return null; }
  }
  const pill = (text, modifier = "") =>
    create("span","pill "+modifier,text);
  function heading(text, description = "") {
    const s = create("section","detail-section");
    append(s,create("h3","section-heading",text));
    if (description) append(s,create("p","section-help",description));
    return s;
  }
  function eventHash() {
    const match = location.hash.match(/^#(?:event=)?(.+)$/);
    if (!match) return null;
    try { return decodeURIComponent(match[1]); }
    catch { return null; }
  }
  function scrollTop() {
    try { window.scrollTo({top:0,behavior:"instant"}); }
    catch { window.scrollTo(0,0); }
  }
  function back(updateUrl=true) {
    $("layout").classList.remove("detail-open");
    document.body.classList.remove("detail-active");
    if (updateUrl) {
      try { history.replaceState(null,"",location.pathname+location.search); }
      catch {}
    }
    if (mobile()) scrollTop();
  }
  async function select(id, updateUrl=true) {
    if (!state.events.some(e => e.id === id)) return;
    if (state.selected !== id) state.institutionFilter = "all";
    state.selected = id;
    renderList();
    renderDetail();
    if (updateUrl) {
      try { history.pushState({policyEvent:id},"","#event="+encodeURIComponent(id)); }
      catch {}
    }
    if (mobile()) {
      $("layout").classList.add("detail-open");
      document.body.classList.add("detail-active");
      scrollTop();
    }
    const ticket=++requestId;
    const event=state.events.find(e=>e.id===id);
    if(!event.loaded){
      try {
        const payload=await model.loadEventDetail(event);
        const index=state.events.findIndex(e=>e.id===id);
        state.events[index]=model.eventView({...event.raw,...payload});
        if(ticket===requestId&&state.selected===id){renderList();renderDetail();}
      }catch(error){
        if(ticket===requestId&&state.selected===id)
          $("detail").replaceChildren(create("p","no-impacts","상세 로딩 실패: "+error.message));
      }
    }
  }
  function renderFilters() {
    for (const mode of view.MODES) {
      const button=$("mode-"+mode);
      const active=state.mode===mode;
      if(active)button.classList.add("active");
      else button.classList.remove("active");
      button.setAttribute("aria-pressed",String(active));
    }
  }
  function filtered() {
    return view.filterEvents(state.events,state);
  }
  function renderList() {
    renderFilters();
    const events=filtered();
    const root=$("items");root.replaceChildren();
    $("list-count").textContent="조건 일치 "+num(events.length)+"건 / 전체 "+num(state.events.length)+"건"
      +(events.length>state.visible?" · "+num(state.visible)+"건 먼저 표시":"");
    if (!events.length) {
      append(root,create("p","empty",
        "조건에 맞는 자료가 없습니다. 필터 초기화로 수집된 전체 정책을 확인하세요."));
    }
    for (const event of events.slice(0,state.visible)) {
      const item=create("button","item"+(event.id===state.selected?" selected":""));
      item.type="button";
      item.dataset.eventId=event.id;
      const header=create("div","item-top");
      const categories=[...new Set((event.members||[])
        .map(x=>x.kind).filter(Boolean))];
      append(header,pill(view.category(event),"type "+event.kind),
        categories.length===1&&categories[0]!=="법령"?
          pill(categories[0]):null,
        create("span","item-date",event.published_at||"날짜 미확인"));
      const tags=create("div","item-tags");
      const impact=event.impact_assessment;
      if (impact) {
        const status=impact.classification==="high"?"영향도 큼":
          impact.classification==="pending"?"평가 중":"일반";
        const points=impact.score_min+(impact.score_complete?"점":"점 이상");
        append(tags,pill(status+" · "+points,impact.classification==="high"?"priority":"impact-score"));
      }
      if (event.source_count>1) append(tags,pill("동시 개정 "+num(event.source_count)+"건"));
      if (event.institution_count) append(tags,pill("검토 기관 "+num(event.institution_count)+"곳","impact"));
      if (event.review_count) append(tags,pill("업무 검토 "+num(event.review_count)+"건"));
      if (event.public_service_lead_count)
        append(tags,pill("공공서비스 기준 "+num(event.public_service_lead_count)+"건"));
      if (event.ai_count) append(tags,pill("AI 보조검토","ai"));
      const highlighted=(event.highlights||[])[0];
      const important=highlighted && (event.changes||[]).find(ch=>
        ch.document_id===highlighted.document_id && ch.article===highlighted.article);
      const brief=important?.brief||event.changes?.[0]?.brief;
      append(item,header,create("h3","",event.title),
        create("p","item-brief",compact(brief||event.headline,170)),tags);
      item.onclick=()=>select(event.id);
      append(root,item);
    }

    $("more").hidden=events.length<=state.visible;
  }
  function sourceDiffPreview(change, beforeLabel="변경 전", afterLabel="변경 후", visible=Infinity, start=0) {
    const meaning=change.meaning||{};
    const allFocus=Array.isArray(meaning.focus)?meaning.focus:[];
    const focus=allFocus.slice(start,start+visible);
    const wrapper=create("div","source-diff-preview");
    if(!focus.length) {
      const pair=create("div","highlight-comparison");
      const a=create("div","highlight-old"),b=create("div","highlight-new");
      append(a,create("small","",beforeLabel),
        create("p","",compact(change.before||"종전 원문 미확보",300)));
      append(b,create("small","",afterLabel),
        create("p","",compact(change.after||"현행 원문 미확보",300)));
      append(pair,a,b);
      append(wrapper,pair);
      return wrapper;
    }
    if(meaning.diff_window_count>allFocus.length)
      append(wrapper,create("p","section-help","일부 변경 내용은 조문 전문에서 확인할 수 있습니다."));
    for(const [index,part] of focus.entries()){
      const pair=create("div","highlight-comparison");
      if(allFocus.length>1)
        append(wrapper,create("p","diff-window-label",
          "변경 위치 "+num(start+index+1)+" / "+num(allFocus.length)));
      for(const [side,label,className] of [
        ["before",beforeLabel,"highlight-old"],
        ["after",afterLabel,"highlight-new"]
      ]) {
        const block=create("div",className);
        append(block,create("small","",label));
        const p=create("p","diff-preview-text");
        const snippet=part[side]||{};
        if(snippet.prefix)append(p,create("span","diff-context",snippet.prefix));
        if(snippet.changed)append(p,create("mark","diff-changed",snippet.changed));
        else append(p,create("span","diff-absent",
          side==="before"?"[추가된 부분]":"[삭제된 부분]"));
        if(snippet.suffix)append(p,create("span","diff-context",snippet.suffix));
        if(snippet.truncated)append(block,create("p","section-help","긴 변경 구간은 일부만 표시했습니다. 전체 원문을 펼쳐 확인하세요."));
        append(block,p);
        append(pair,block);
      }
      append(wrapper,pair);
    }
    return wrapper;
  }

  function sourcePair(change) {
    const wrap=create("div","clause");
    const label=change.meaning?.label||"조문 내용 변경";
    append(wrap,create("div","clause-name",
      change.document_title+" · "+change.article+" · "+label));
    if(change.brief)append(wrap,create("p","clause-description",change.brief));
    append(wrap,sourceDiffPreview(change,"변경 전","변경 후"));
    const full=create("details","original-clause");
    append(full,create("summary","","변경 전·후 조문 전체 보기"));
    const complete=create("div","pair");
    const oldBox=create("div","before");
    const newBox=create("div","after");
    append(oldBox,create("small","value-label","종전 조문 전문"),
      create("p","full-clause-text",change.before||"미확인"));
    append(newBox,create("small","value-label","현행 조문 전문"),
      create("p","full-clause-text",change.after||"미확인"));
    append(complete,oldBox,newBox);
    append(full,complete);
    append(wrap,full,link(change.source_url,"공식 법령 원문"));
    return wrap;
  }
  function renderCore(event) {
    const section=heading("이번 개정에서 달라진 내용");
    section.className="detail-section core";
    const summary=create("div","core-summary");
    append(summary,create("strong","",compact(event.headline,220)));
    if(event.headline.length>170){const more=create("details","highlight-detail");append(more,create("summary","","정책 요약 전체 보기"),create("p","",event.headline));append(summary,more);}
    append(section,summary);
    if (event.changes?.length) {
      const highlights=create("div","highlights");
      // Highlight only source-verified, substantive edits. Historical renaming,
      // citation formatting and revision-date changes remain in the full diff.
      const indices=event.impact_assessment?.featured_change_indices||[];
      const shown=indices.map(i=>event.changes[i]).filter(Boolean).slice(0,3);
      const moreChanges=shown.length>1?create("details","core-more"):null;
      if(moreChanges)
        append(moreChanges,create("summary","","추가 주요 조문 "+num(shown.length-1)+"건 펼쳐보기"));
      for (const change of shown) {
        const meaning=change.meaning||{};
        const row=create("div","highlight");
        if(meaning.source_check_required)row.className+=" highlight-caution";
        const lead=create("div","highlight-lead");
        append(lead,create("span","highlight-cat",
            meaning.label||"변경 조문"),
          create("span","highlight-doc",
            change.document_title+" · "+change.article));
        append(row,lead);
        const focus=meaning.focus?.[0]||{};
        const oldText=compact(focus.before?.changed||"",70);
        const newText=compact(focus.after?.changed||"",70);
        const factual=oldText||newText?"변경 전 ‘"+(oldText||"없음")+"’ → 변경 후 ‘"+(newText||"없음")+"’":"";
        const description=change.brief||factual||meaning.description||"원문 내용 확인 필요";
        append(row,create("strong","highlight-description",compact(description,160)));
        if(description.length>160){
          const more=create("details","highlight-detail");
          append(more,create("summary","","변경 설명 전체 보기"),
            create("p","",description));
          append(row,more);
        }
        if(change.before || change.after || meaning.focus?.length) {
          const first=shown.indexOf(change)===0;
          if(first) {
            append(row,sourceDiffPreview(change,"변경 전","변경 후",1));
            const windows=Array.isArray(meaning.focus)?meaning.focus:[];
            if(windows.length>1) {
              const rest=create("details","core-more");
              append(rest,create("summary","","나머지 변경 위치 "+num(windows.length-1)+"곳 펼쳐보기"),
                sourceDiffPreview(change,"변경 전","변경 후",Infinity,1));
              append(row,rest);
            }
          } else {
            const toggle=create("details","highlight-detail");
            append(toggle,create("summary","","변경 전·후 내용 펼치기"));
            append(toggle,sourceDiffPreview(change,"변경 전","변경 후"));
            append(row,toggle);
          }
        }
        append(shown.indexOf(change)===0?highlights:moreChanges,row);
      }
      if(moreChanges)append(highlights,moreChanges);
      if(shown.length)append(section,highlights);
    }
    const stats=create("div","impact-numbers");
    if(event.institution_count>0)
      append(stats,create("span","","관련 기관 "+num(event.institution_count)+"곳"));
    if(event.review_count>0)
      append(stats,create("span","","후속조치 "+num(event.review_count)+"건"));
    if (event.public_service_lead_count)
      append(stats,create("span","","공공서비스 검토 후보 "+
        num(event.public_service_lead_count)+"건"));
    if (event.dependent_rules?.length)
      append(stats,create("span","","연관 규정 "+num(event.dependent_rules.length)+"건"));
    if(stats.children.length)append(section,stats);
    const agencies=[...new Set((event.institutional_reviews||[]).map(x=>x.institution))];
    if(agencies.length)append(section,create("p","core-agencies","영향 검토 기관 · "+agencies.join(" · ")));
    return section;
  }
  function reviewCard(review) {
    const card=create("div","review-card");
    const type={
      direct_regulated_institution:"직접 규율기관",
      explicit_changed_clause:"변경 조문에 명시",
      verified_official_rule_citation:"관련 공식 규정 인용",
      historical_citation_review_candidate:"이전 수집 자료 인용 · 원문 대조 전",
      verified_program_citation:"공식 사업 인용",
      partial_source_review:"추가 대조 필요 · 변경 원문 일부 미확인",
       explicit_official_standard_criterion:"공식 사업에 명시된 기준 · 연계 검토"
    }[review.basis_tier]||"공식 근거";
    append(card,create("div","review-meta",
      type+" · "+(review.program||review.document_title)+" · "+review.article));
    append(card,pill(review.evidence_status==="review_of_verified_citation" && review.basis_tier!=="partial_source_review" ?
      "근거 확인" : "추가 확인할 연결","review-status"));
    append(card,create("p","review-task",review.task));
    if(review.effective_date)append(card,create("p","review-effective","적용 시점 "+review.effective_date));
    const short=(review.linked_changes||[]).filter(model.isShort);
    if(short.length)append(card,deltaTable(short,6));
    if(review.linked_changes?.length){
      const delta=create("details","proof");append(delta,create("summary","","연결된 변경 근거 "+review.linked_changes.length+"개"));
      for(const change of review.linked_changes)append(delta,sourcePair(model.changeView(change,review.event)));
      append(card,delta);
    }
    if (review.program && review.change)
      append(card,create("div","review-change",compact(review.change,150)));
    if (review.ai?.work_impact || review.ai?.question) {
      const suggestion=create("details","ai-inline");
      append(suggestion,create("summary","","AI가 분석한 업무 변경 설명과 인용 근거"));
      if (review.ai.work_impact)
        append(suggestion,create("p","",review.ai.work_impact));
      if (review.ai.question)
        append(suggestion,create("p","",review.ai.question));
      if (review.ai.old_quote && review.ai.new_quote)
        append(suggestion,create("p","ai-evidence","종전 원문: "+review.ai.old_quote+" / 변경 원문: "+review.ai.new_quote));
      if (review.ai.program_quote)
        append(suggestion,create("p","ai-evidence","공식 사업자료 인용: "+review.ai.program_quote));
      append(card,suggestion);
    }
    const proof=create("details","proof");
    append(proof,create("summary","","변경 근거 확인"),
      create("p","",review.basis_quote),
      link(review.source_url,"변경 조문"),
      link(review.related_rule_url,"관련 공식 규정"),
      link(review.program_url,"공식 사업자료"));
    for(const edge of review.dependency_path||[]) {
      append(proof,create("p","",edge.title+" "+edge.article+" → "+edge.reference_quote),link(edge.url,"중간 규정 원문"));
    }
    append(card,proof);
    return card;
  }
  function renderInstitutions(event) {
    const section=heading("기관·사업별 후속조치");
    let relatedRules=null;
    if(event.dependent_rules?.length){
      const rules=create("details","proof");
      append(rules,create("summary","","관련 규정 "+num(event.dependent_rules.length)+"건"));
      for(const edge of event.dependent_rules){
        const item=create("div","review-card");
        append(item,create("p","review-task",edge.title+" · "+edge.article),create("p","",event.title+" "+edge.changed_article+" 인용"),create("p","",edge.reference_quote),link(edge.url,"관련 규정 원문"));
        append(rules,item);
      }
      relatedRules=rules;
    }
    const groups=view.impactGroups(event);
    if (!groups.length) {
      if(relatedRules)append(section,relatedRules);
      return relatedRules?section:null;
    }
    // Names come solely from this event's verified institutional reviews.
    // Switching policy events resets the selection in select(), never carrying
    // an agency from another policy into an unrelated event.
    if (state.institutionFilter!=="all" &&
        !groups.some(g=>g.agency===state.institutionFilter)) {
      state.institutionFilter="all";
    }

    const layout=create("div","institution-layout");
    const sidebar=create("aside","agency-filter-panel");
    append(sidebar,create("div","agency-filter-title","기관명 필터"));
    const search=create("input","agency-filter-search");
    search.type="search";
    search.placeholder="기관명 검색";
    search.setAttribute("aria-label","검토 대상 기관명 검색");
    const buttons=create("div","agency-filter-buttons");
    append(sidebar,search,buttons);

    const main=create("div","agency-filter-results");
    const compactLabel=create("label","agency-select-label","기관 선택");
    const compactSelect=create("select","agency-select");
    compactSelect.id="institution-select-"+event.id;
    compactLabel.setAttribute("for",compactSelect.id);
    compactSelect.setAttribute("aria-label","기관별 변경 검토사항 기관 선택");
    const all=create("option","","전체 기관 ("+num(groups.length)+")");
    all.value="all";
    append(compactSelect,all);
    for(const entry of groups) {
      const opt=create("option","",entry.agency+" ("+num(entry.reviews.length+entry.services.length)+")");
      opt.value=entry.agency;
      append(compactSelect,opt);
    }
    compactSelect.value=state.institutionFilter;
    const compactControl=create("div","agency-mobile-filter");
    append(compactControl,compactLabel,compactSelect);
    const counter=create("div","section-counter");
    counter.setAttribute("aria-live","polite");
    const results=create("div","agency-group-results");
    append(main,compactControl,counter,results);
    append(layout,sidebar,main);
    append(section,layout);

    function drawResults(){
      const shown=state.institutionFilter==="all" ? groups :
        groups.filter(g=>g.agency===state.institutionFilter);
      const reviewCount=shown.reduce((total,g)=>total+g.reviews.length,0);
      const serviceCount=shown.reduce((total,g)=>total+g.services.length,0);
      const verified=shown.reduce((n,g)=>n+g.reviews.filter(r=>
        r.evidence_status==="review_of_verified_citation" && event.comparison_status==="changed").length,0);
      counter.textContent=num(shown.length)+"개 기관 · 근거 확인 "+num(verified)+"건 · 추가 확인 "+num(reviewCount-verified)+"건";
      compactSelect.value=state.institutionFilter;
      results.replaceChildren();
      for(let i=0;i<shown.length;i++){
        const entry=shown[i];
        const group=create("details","agency-group");
        group.open=state.institutionFilter!=="all" ||
          shown.length<=3 || i===0;
        const top=create("summary","agency-heading");
        append(top,create("strong","",entry.agency),
          create("span","",num(entry.reviews.length+entry.services.length)+"건"));
        append(group,top);
        for(const review of entry.reviews){
          append(group,reviewCard(review));
        }
        append(results,group);
      }
    }
    function drawFilterButtons(){
      const term=search.value.trim().toLocaleLowerCase("ko-KR");
      buttons.replaceChildren();
      const allButton=create("button",
        "agency-filter-button"+(state.institutionFilter==="all"?" active":""),
        "전체 기관");
      allButton.type="button";
      allButton.setAttribute("aria-pressed",
        String(state.institutionFilter==="all"));
      append(allButton,create("span","agency-filter-count",num(groups.length)));
      allButton.onclick=()=>choose("all");
      append(buttons,allButton);
      let matched=0;
      const buckets=new Map();
      for(const entry of groups){
        if(!entry.agency.toLocaleLowerCase("ko-KR").includes(term))continue;
        matched++;
        const selected=state.institutionFilter===entry.agency;
        const button=create("button",
          "agency-filter-button"+(selected?" active":""));
        button.type="button";
        button.setAttribute("aria-pressed",String(selected));
        button.dataset.institution=entry.agency;
        append(button,create("span","agency-filter-name",entry.agency),
          create("span","agency-filter-count",num(entry.reviews.length+entry.services.length)));
        button.onclick=()=>choose(entry.agency);
        const type=entry.reviews[0]?.agency_type||"";
        const name=/교육청|교육지원청/.test(entry.agency)?"교육청":/시군구|광역시도|지방자치/.test(type)?"지방자치단체":"중앙부처·공공기관";
        if(!buckets.has(name))buckets.set(name,[]);buckets.get(name).push(button);
      }
      for(const [name,items]of buckets){const group=create("details");group.open=name==="중앙부처·공공기관"||!!term||items.some(b=>b.dataset.institution===state.institutionFilter);append(group,create("summary","",name+" · "+items.length));for(const item of items)append(group,item);append(buttons,group);}
      if(!matched && term)
        append(buttons,create("p","agency-no-match","검색된 기관이 없습니다."));
    }
    function choose(name){
      state.institutionFilter=name;
      drawFilterButtons();
      drawResults();
    }
    search.oninput=()=>drawFilterButtons();
    compactSelect.onchange=()=>choose(compactSelect.value);
    drawFilterButtons();
    drawResults();
    if(relatedRules)append(section,relatedRules);
    return section;
  }
  function renderEvidence(event) {
    // The entire evidence section, including official source links, begins
    // collapsed. Expanding it reveals the first five excerpts and a separate
    // disclosure for additional excerpts; all original text stays accessible.
    const section=create("details","detail-section evidence-panel evidence-section");
    append(section,create("summary","section-heading","공식 신구대비와 근거 원문"));
    const body=create("div","evidence-content");
    append(body,link(event.url,"현행 공식 판본"),link(event.prior_url,"종전 공식 판본"));
    for (const [i,ch] of (event.changes||[]).entries()) {
      if (i===5) {
        const more=create("details","more-clauses");
        append(more,create("summary","",
          "추가 변경 조문 "+num(event.changes.length-5)+"건"));
        for (const other of event.changes.slice(5))
          append(more,sourcePair(other));
        append(body,more);
        break;
      }
      append(body,sourcePair(ch));
    }
    if(event.source_count>1) {
      const documents=create("details","more-clauses");
      append(documents,create("summary","","함께 개정된 법령 "+num(event.source_count)+"건"));
      for (const member of event.members||[]) {
        const row=create("div","member-row");
        append(row,create("span","",member.title),
          link(member.url,"공식 원문"));
        append(documents,row);
      }
      append(body,documents);
    }
    if(event.dependent_rules?.length) {
      const refs=create("details","more-clauses");
      append(refs,create("summary","","관련 규정 "+num(event.dependent_rules.length)+"건"));
      for(const ref of event.dependent_rules) {
        const row=create("div","member-row");
        append(row,create("span","",ref.title+" · "+ref.article),
          link(ref.url,"규정 원문"));
        append(refs,row);
      }
      append(body,refs);
    }
    append(section,body);
    return section;
  }
  function renderAI(event) {
    if (!event.ai_summaries?.length) return null;
    const section=heading("AI 분석 근거");
    const drawer=create("details","evidence-panel");
    append(drawer,create("summary","",
      "AI 분석 근거 "+num(event.ai_summaries.length)+"건 펼치기"));
    for (const item of event.ai_summaries) {
      const card=create("div","ai-review");
      append(card,create("strong","",item.summary),
        item.question?create("p","",item.question):null,
        create("small","",item.article+" · 공식 원문 인용: "+
          item.before_quote+" → "+item.after_quote));
      append(drawer,card);
    }
    append(section,drawer);
    return section;
  }
  function renderDetail() {
    const root=$("detail");root.replaceChildren();
    const event=state.events.find(e=>e.id===state.selected);
    if (!event) {
      append(root,create("p","empty","정책 변경 사건을 선택하세요."));
      return;
    }
    const head=create("header","detail-head");
    const meta=create("div","detail-meta");
    append(meta,pill(view.category(event),"type "+event.kind),
      create("span","",event.published_at||""));
    append(head,meta,create("h2","",event.title),
      event.effective_date ?
        create("p","effective","시행일 "+event.effective_date):null);
    append(root,head);
    if(!event.loaded){
      append(root,create("p","loading-detail","정책 상세를 불러오는 중입니다."));
      return;
    }
    const core=renderCore(event);
    const institutions=renderInstitutions(event);
    const ai=renderAI(event);
    const evidence=renderEvidence(event);
    core.id="policy-core";
    if(institutions)institutions.id="policy-institutions";
    if(ai)ai.id="policy-ai";
    evidence.id="policy-evidence";
    const links=[
      ["변경 핵심","policy-core"],
      ...(institutions?[["기관별 후속조치","policy-institutions"]]:[]),
      ...(ai?[["AI 분석 근거","policy-ai"]]:[]),
      ["신구대비·근거","policy-evidence"]
    ];
    const nav=create("nav","detail-nav");
    for(const [text,id] of links) {
      const button=create("button","",text);
      button.type="button";
      button.onclick=()=>{
        const target=$(id);
        if(!target)return;
        if(target.tagName==="DETAILS")target.open=true;
        target.scrollIntoView({behavior:"smooth",block:"start"});
      };
      append(nav,button);
    }
    append(head,link(event.url,"공식 정책 원문"),nav);
    // Sections follow the reader's actual work: what changed, what to do,
    // AI explanation, then optional source archive. No score/debug panels.
    append(root,core,institutions,ai,evidence);
  }
  function show(data) {
    if(data.schema!=="policy-domino-unified-ui-v1"||!Array.isArray(data.events))throw Error("정책 데이터 규격이 일치하지 않습니다.");
    const raw=data;
    state.data=data;state.events=data.events.map(model.eventView);state.mode="impact";state.sort="impact";state.institutionFilter="all";
    const stats=view.overview(state.events);
    $("stat-events").textContent=num(raw.total_source_versions_saved||stats.events);
    $("stat-agencies").textContent=num(stats.institutions);
    $("stat-actions").textContent=num(raw.reconciliation?.verified_institutional_review_tasks??stats.actions);
    const rc=raw.reconciliation||{};
    $("analysis-coverage").textContent="공식 원문 확보 "+num(rc.official_complete_originals)+"건 · 검증된 신구 변경 "+num(rc.comparisons_by_status?.changed)+"건 · 부분 대조 "+num(rc.comparisons_by_status?.partial_unverified)+"건 · 분석 현황 펼치기";
    $("ai-review-progress").textContent="AI 정책 변경 설명 "+num(raw.analysis?.policy_ai_summaries)+"건 · 추가 분석 대상 "+num(raw.analysis?.policy_summaries_pending)+"건";
    const c=raw.coverage||{};
    const latestGov=c.gov24_refresh||{};
    const govStatus=latestGov.errors?.length?"최근 정부24 갱신 오류":latestGov.listed_pages||latestGov.detail_pages?
      "최근 정부24 갱신: 목록 "+num(latestGov.listed_pages)+"쪽, 상세 "+num(latestGov.detail_pages)+"쪽":"정부24 최신 갱신 대기";
    $("institution-link-progress").textContent="정부24 공식 사업 "+num(c.gov24_programs)+"건, 운영기관 "+num(c.gov24_agencies)+"곳 · "+govStatus+" · 색인 "+num(rc.indexed_unique_versions)+"건 중 원문 미확보 "+num(rc.indexed_without_saved_original)+"건, 과거 추출본 재검증 "+num(rc.legacy_extracted_versions_requiring_source_revalidation)+"건. 알리오플러스 기관 명부 "+num(c.alio_public_institutions)+"곳. 기관 명부만으로 정책 영향을 추정하지 않습니다.";
    $("updated").textContent=raw.generated_at?" · 자료 갱신 "+new Date(raw.generated_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"})+" KST":"";
    for(const topic of [...new Set(state.events.map(e=>e.topic).filter(Boolean))].sort()){
      const option=create("option","",topic);option.value=topic;append($("category"),option);
    }
    setupRegistry();
    const linked=eventHash();
    state.selected=state.events.some(e=>e.id===linked) ?
      linked:(filtered()[0]?.id||null);
    renderList();renderDetail();
    if(state.selected)select(state.selected,false);
    if (linked && mobile()) select(linked,false);
    else if (mobile()) back(false);
  }
  function refresh(){
    state.visible=60;renderList();const shown=filtered();
    if(!mobile()){
      if(!shown.length){state.selected=null;requestId++;renderDetail();}
      else if(!shown.some(e=>e.id===state.selected))select(shown[0].id,false);
    }
  }
  for(const id of ["category","source","sort"])$(id).onchange=()=>{state[id]=$(id).value;refresh();};
  $("reset").onclick=()=>{state.mode="impact";state.query="";state.category="";state.source="";state.sort="impact";$("search").value="";$("category").value="";$("source").value="";$("sort").value="impact";refresh();};
  function goHome(event){
    if(event)event.preventDefault();
    // Cancel in-flight detail responses so a previous policy cannot reopen.
    requestId++;
    Object.assign(state,{mode:"impact",query:"",category:"",source:"",
      sort:"impact",visible:60,institutionFilter:"all",selected:null});
    $("search").value="";
    $("category").value="";
    $("source").value="";
    $("sort").value="impact";
    if($("registry-dialog").open)$("registry-dialog").close();
    document.querySelector(".coverage-status-inner").open=false;
    try{history.replaceState(null,"",location.pathname+location.search);}catch{}
    back(false);
    renderList();
    const first=filtered()[0];
    if(first)select(first.id,false);
    else renderDetail();
    // The mobile home view is the list, not an automatically opened detail.
    if(mobile())back(false);
    $("items").scrollTop=0;
    scrollTop();
  }
  document.querySelectorAll("[data-home]").forEach(banner=>banner.addEventListener("click",goHome));
  function deltaTable(changes,limit){
    const wrap=create("div","delta-wrap"),table=create("table","delta-table"),head=create("thead"),row=create("tr");
    for(const label of ["변경 항목","이전","변경"])append(row,create("th","",label));append(head,row);append(table,head);
    const body=create("tbody");for(const change of changes.slice(0,limit)){const row=create("tr");for(const text of [change.article,change.before,change.after])append(row,create("td","",text));append(body,row);}append(table,body);append(wrap,table);return wrap;
  }
  function setupRegistry(){
    let records=[];
    const draw=()=>{const q=$("registry-search").value.trim().toLocaleLowerCase("ko-KR"),rows=records.filter(x=>x.name.toLocaleLowerCase("ko-KR").includes(q));$("registry-caption").textContent="알리오플러스 공식 기관 명부 · "+records.length+"곳 중 "+rows.length+"곳 표시";$("registry-results").replaceChildren();for(const entry of rows){const row=create("div","registry-row");append(row,create("span","",entry.name),link(entry.url,"공식 기관정보 ↗"));append($("registry-results"),row);}};
    $("registry-open").onclick=async()=>{try{if(!records.length){const res=await fetch("institutions.json");if(!res.ok)throw Error("명부 응답 오류");records=(await res.json()).records||[];}draw();$("registry-dialog").showModal();}catch(error){$("institution-link-progress").textContent=error.message;}};
    $("registry-close").onclick=()=>$("registry-dialog").close();$("registry-search").oninput=draw;
  }
  for (const mode of view.MODES) {
    $("mode-"+mode).onclick=()=>{
      state.mode=mode;
      state.visible=60;
      renderList();
      if(!mobile()){
        const shown=filtered();
        if(shown.length&&!shown.some(event=>event.id===state.selected)){
          select(shown[0].id,false);
        } else if(!shown.length) {
          state.selected=null;
          renderDetail();
        }
      }
    };
  }
  $("search").oninput=ev=>{
    state.query=String(ev.target.value||"").trim();
    refresh();
  };
  $("more").onclick=()=>{state.visible+=60;renderList();};
  $("backToList").onclick=()=>back();
  window.addEventListener("popstate",()=>{
    const id=eventHash();
    if (id && state.events.some(e=>e.id===id)) select(id,false);
    else back(false);
  });
  window.addEventListener("resize",()=>{
    if (!mobile()) {
      $("layout").classList.remove("detail-open");
      document.body.classList.remove("detail-active");
    } else if (!eventHash()) back(false);
  });
  fetch("./data.json",{cache:"no-store"})
    .then(res=>{
      if(!res.ok)throw Error("공식 정책 데이터 응답 오류");
      return res.json();
    }).then(show).catch(err=>{
      $("items").replaceChildren(create("p","empty",
        "공식 정책 변경 데이터를 불러오지 못했습니다."));
      $("detail").replaceChildren(create("p","no-impacts",String(err)));
      $("list-count").textContent="불러오기 실패";
    });
})();
