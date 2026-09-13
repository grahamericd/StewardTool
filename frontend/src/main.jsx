import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";

const USERS = { Steward: "steward@demo.gov", Approver: "approver@demo.gov", "Org Admin": "admin@demo.gov", "Enterprise Admin": "enterprise@demo.gov" };
const PRIMARY_NAV = ["Steward Home", "My Information", "Discover Information", "My Next Steps"];
const REVIEW_NAV = ["Review Queue", "Publishing History"];

function App() {
  const [page, setPage] = useState("Steward Home");
  const [userLabel, setUserLabel] = useState("Steward");
  const [me, setMe] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [assets, setAssets] = useState([]);
  const [systems, setSystems] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [assetTab, setAssetTab] = useState("Overview");
  const [selectedQualityIssueId, setSelectedQualityIssueId] = useState(null);
  const [guidedTask, setGuidedTask] = useState(null);
  const [message, setMessage] = useState("");
  const userEmail = USERS[userLabel];
  const canReview = ["APPROVER","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(me?.role);

  async function refresh() {
    const [meData, dash, assetData, systemData, taskData] = await Promise.all([
      api("/me", userEmail), api("/dashboard", userEmail), api("/assets", userEmail), api("/systems", userEmail), api("/tasks", userEmail)
    ]);
    setMe(meData); setDashboard(dash); setAssets(assetData); setSystems(systemData); setTasks(taskData);
    if (!selectedAssetId && assetData.length) setSelectedAssetId(assetData[0].asset.asset_id);
  }
  useEffect(() => { refresh().catch(e => setMessage(e.message)); }, [userEmail]);
  const selectedAsset = useMemo(() => assets.find(a => a.asset.asset_id === selectedAssetId), [assets, selectedAssetId]);

  async function doAction(fn, successMessage) {
    try { setMessage(""); await fn(); await refresh(); setMessage(successMessage); }
    catch (e) { setMessage(e.message); }
  }

  return <div className="app">
    <aside>
      <div className="brand">AI Data Steward</div>
      <div className="tagline">Guided stewardship, one step at a time.</div>

      <div className="nav-section">
        <div className="nav-label">Your stewardship</div>
        <nav>{PRIMARY_NAV.map(n => {
          const active = page===n || (page==="Information Details" && n==="My Information");
          return <button key={n} onClick={() => setPage(n)} className={active?"active":""}>{n}</button>;
        })}</nav>
      </div>

      {canReview&&<div className="nav-section reviewer-nav">
        <div className="nav-label">Review & publishing</div>
        <nav>{REVIEW_NAV.map(n => <button key={n} onClick={() => setPage(n)} className={page===n?"active":""}>{n}</button>)}</nav>
      </div>}

      <div className="aside-guidance">
        <b>Not sure where to start?</b>
        <p>Open My Next Steps. AI Data Steward will guide you to the work that needs attention.</p>
      </div>
    </aside>
    <main>
      <header>
        <div><div className="org">{me?.organization?.name || "Loading..."}</div><div className="role">{me?.role || ""}</div></div>
        <label className="role-switch demo-control"><span>Demo role</span><select value={userLabel} onChange={e=>setUserLabel(e.target.value)}>{Object.keys(USERS).map(u=><option key={u}>{u}</option>)}</select><small>Demo only</small></label>
      </header>
      {message && <div className="message">{message}</div>}
      {page === "Steward Home" && <StewardHome dashboard={dashboard} assets={assets} tasks={tasks} onTask={task=>{
        setSelectedAssetId(task.asset_id);
        if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
          setGuidedTask(null);
          setAssetTab("Can This Information Be Trusted?");
          setSelectedQualityIssueId(Number(task.source_reference));
        } else if(task.source_type==="PERIODIC_REVIEW"){
          setGuidedTask(task);
          setAssetTab("Review & Maintain");
          setSelectedQualityIssueId(null);
        } else {
          setGuidedTask(task);
          setAssetTab(task.governance_domain==="QUALITY"?"Can This Information Be Trusted?":"Governance");
          setSelectedQualityIssueId(null);
        }
        setPage("Information Details");
      }} onInventory={()=>setPage("My Information")} onDiscover={()=>setPage("Discover Information")} onAllTasks={()=>setPage("My Next Steps")} />}
      {page === "My Information" && <Dashboard dashboard={dashboard} assets={assets} onOpen={id=>{setSelectedAssetId(id);setPage("Information Details")}} />}
      {page === "Discover Information" && <Discover systems={systems} userEmail={userEmail} onDone={async id=>{await refresh();setSelectedAssetId(id);setPage("Information Details")}} />}
      {page === "My Next Steps" && <Inbox tasks={tasks} onGuide={task=>{
        setSelectedAssetId(task.asset_id);
        if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
          setGuidedTask(null);
          setAssetTab("Can This Information Be Trusted?");
          setSelectedQualityIssueId(Number(task.source_reference));
        } else if(task.source_type==="PERIODIC_REVIEW"){
          setGuidedTask(task);
          setAssetTab("Review & Maintain");
          setSelectedQualityIssueId(null);
        } else {
          setGuidedTask(task);
          setAssetTab(task.governance_domain==="QUALITY"?"Can This Information Be Trusted?":"Governance");
          setSelectedQualityIssueId(null);
        }
        setPage("Information Details");
      }} />}
      {page === "Information Details" && <Asset360 asset={selectedAsset} assets={assets} systems={systems} tasks={tasks} role={me?.role} userEmail={userEmail} selectedAssetId={selectedAssetId} setSelectedAssetId={id=>{setSelectedAssetId(id);setSelectedQualityIssueId(null);setGuidedTask(null);setAssetTab("Overview")}} doAction={doAction} tab={assetTab} setTab={setAssetTab} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} guidedTask={guidedTask} setGuidedTask={setGuidedTask} />}
      {page === "Review Queue" && <ReviewQueue assets={assets} role={me?.role} userEmail={userEmail} doAction={doAction} onOpen={id=>{setSelectedAssetId(id);setPage("Information Details")}} />}
      {page === "Publishing History" && <PublicationHistory assets={assets} selectedAssetId={selectedAssetId} setSelectedAssetId={setSelectedAssetId} userEmail={userEmail} />}
    </main>
  </div>;
}

function StewardHome({dashboard,assets,tasks,onTask,onInventory,onDiscover,onAllTasks}) {
  const [showIntro,setShowIntro]=useState(()=>localStorage.getItem("steward_intro_complete")!=="yes");
  const priorityOrder={HIGH:0,MEDIUM:1,LOW:2};
  const work=[...(tasks||[])].sort((a,b)=>(priorityOrder[a.priority]??9)-(priorityOrder[b.priority]??9));
  const now=work.filter(t=>(t.bucket||"NOW")==="NOW");
  const waiting=work.filter(t=>(t.bucket||"NOW")==="WAITING");
  const next=now[0];
  const assetCount=assets?.length||0;
  const qualityTasks=work.filter(t=>t.source_type==="QUALITY_ISSUE").length;
  const governanceTasks=work.filter(t=>t.source_type!=="QUALITY_ISSUE").length;

  const responsibilities=[
    ["Understand","Know what information exists, what it means, where it lives, and who is responsible."],
    ["Govern","Confirm ownership, classification, retention, and other stewardship decisions."],
    ["Trust","Review quality findings and make evidence-based decisions without guessing."],
    ["Maintain","Keep information current as systems, policies, quality, and business needs change."],
    ["Publish","Help information move to approval and publication when it is ready."]
  ];

  return <>
    {showIntro&&<section className="welcome-panel">
      <div className="eyebrow">New to data stewardship?</div>
      <h1>You do not need to be a governance expert.</h1>
      <p className="lead">Your role is to help make sure important information is understood, responsibly governed, and trustworthy. AI Data Steward will show you what needs attention, explain why it matters, and guide you through the decision.</p>
      <div className="responsibility-grid">{responsibilities.map(([title,text],idx)=><div className="responsibility-card" key={title}><span>{idx+1}</span><div><b>{title}</b><p>{text}</p></div></div>)}</div>
      <div className="callout"><b>What you are not expected to do</b><p>You do not need to know every governance rule, make legal or security decisions alone, or guess when you are unsure. Your job is to recognize what needs attention, bring the right context together, make the decisions you are qualified to make, and involve the right expert when needed.</p></div>
      <div className="button-row"><button className="primary" onClick={()=>{localStorage.setItem("steward_intro_complete","yes");setShowIntro(false)}}>Show me what needs my attention</button><button onClick={onDiscover}>Help me identify information</button></div>
    </section>}

    <div className="steward-home-head">
      <div><div className="eyebrow">Steward Home</div><h1>What needs your attention</h1><p className="lead">Work the highest-value item first. When you are unsure, choose “I’m not sure” rather than guessing.</p></div>
      <button onClick={()=>setShowIntro(true)}>What is my role?</button>
    </div>

    <div className="metrics four">
      <Metric label="Information assets" value={assetCount}/>
      <Metric label="Needs your attention" value={now.length}/>
      <Metric label="Waiting on others" value={waiting.length}/>
      <Metric label="Stewardship completeness" value={`${dashboard?.average_governance_readiness??0}%`}/>
    </div>

    {next?<section className="panel start-here">
      <div className="eyebrow">Start here</div>
      <h2>{next.title}</h2>
      <p><b>{next.asset_name}</b> · {responsibilityLabel(next)}</p>
      <div className="guided-task-grid">
        <div><b>Why this matters</b><p>{next.why_it_matters}</p></div>
        <div><b>What you should do</b><p>{next.recommended_action}</p></div>
        <div><b>What this responsibility means</b><p>{next.learn_text}</p></div>
      </div>
      <button className="primary" onClick={()=>onTask(next)}>{next.source_type==="QUALITY_ISSUE"?"Review findings":"Start guided task"}</button>
    </section>:<section className="panel success-panel"><h2>You are caught up.</h2><p>Nothing currently needs your attention. AI Data Steward will bring work back here when something changes.</p></section>}

    <div className="two-col steward-columns">
      <section className="panel">
        <div className="task-head"><div><div className="eyebrow">Your work</div><h2>Next up</h2></div><button onClick={onAllTasks}>View all</button></div>
        {now.slice(1,4).length===0&&<EmptyState title="No additional next steps." text="Your highest-priority work is shown above."/>}
        {now.slice(1,4).map(t=><div className="home-task" key={t.id}><div><span className="priority">{priorityLabel(t.priority)}</span><b>{t.title}</b><small>{t.asset_name} · {responsibilityLabel(t)}</small></div><button onClick={()=>onTask(t)}>Start</button></div>)}
      </section>
      <section className="panel">
        <div className="task-head"><div><div className="eyebrow">Coordination</div><h2>Waiting on others</h2></div></div>
        {waiting.length===0&&<EmptyState title="Nothing is waiting on someone else." text="Items that need another person or team will appear here."/>}
        {waiting.slice(0,4).map(t=><div className="home-task waiting-task" key={t.id}><div><b>{t.title}</b><small>{t.asset_name}</small></div><span>Waiting</span></div>)}
      </section>
    </div>

    <section className="panel stewardship-map">
      <div className="eyebrow">Your stewardship journey</div><h2>How the work fits together</h2>
      <div className="journey-steps">
        <div className={assetCount>0?"journey done":"journey current"}><span>1</span><b>Discover</b><small>Know what information exists</small></div>
        <div className={assetCount>0?"journey done":"journey"}><span>2</span><b>Understand</b><small>Describe purpose, owner, and source</small></div>
        <div className={governanceTasks===0?"journey done":"journey current"}><span>3</span><b>Govern</b><small>Classification, retention, accountability</small></div>
        <div className={qualityTasks===0?"journey done":"journey current"}><span>4</span><b>Trust</b><small>Review evidence and quality</small></div>
        <div className="journey"><span>5</span><b>Publish & maintain</b><small>Approve, publish, and keep current</small></div>
      </div>
      <div className="button-row"><button onClick={onInventory}>View my information</button><button onClick={onDiscover}>Add information</button></div>
    </section>
  </>;
}

function Dashboard({dashboard, assets, onOpen}) {
  if (!dashboard) return <p>Loading...</p>;
  return <>
    <h1>My Information</h1>
    <p className="lead">See the business information your organization has identified, what still needs attention, and whether it is ready to use and share.</p>
    <div className="metrics six">
      <Metric label="Systems we know about" value={dashboard.systems}/><Metric label="Information we know about" value={dashboard.assets}/><Metric label="Needs attention" value={dashboard.open_tasks}/><Metric label="Stewardship completeness" value={`${dashboard.average_governance_readiness}%`}/><Metric label="Average information quality" value={`${dashboard.average_quality_score}%`}/><Metric label="Document/content locations" value={dashboard.unstructured_resources}/>
    </div>
    <h2>Information</h2>
    <div className="grid">{assets.map(a=><div className="card" key={a.asset.asset_id}>
      <div className="eyebrow">{a.asset.business_domain || "Business information"}</div><h3>{a.asset.name}</h3><p>{a.asset.business_definition || "Definition needs review."}</p>
      <div className="status-line"><span>Stewardship completeness</span><b>{a.readiness.score}%</b></div><div className="progress"><div style={{width:`${a.readiness.score}%`}} /></div>
      <div className="status-line"><span>Information quality</span><b>{a.quality?.overall_score != null ? `${a.quality.overall_score}%` : "Not assessed"}</b></div>
      <div className="status-line"><span>Open tasks</span><b>{a.task_summary.open}</b></div>
      <div className="status-line"><span>Publication</span><Status value={a.publication.status}/></div>
      <button className="primary" onClick={()=>onOpen(a.asset.asset_id)}>View details</button>
    </div>)}</div>
  </>;
}

function Inbox({tasks, onGuide}) {
  const rank = {HIGH:0, MEDIUM:1, LOW:2};
  const sorted = [...tasks].sort((a,b)=>(rank[a.priority]??9)-(rank[b.priority]??9));
  return <>
    <h1>My Next Steps</h1><p className="lead">Start at the top. AI Data Steward will explain why each item matters and guide you to the right decision. If you are unsure, choose that option rather than guessing.</p>
    <div className="task-summary">{["HIGH","MEDIUM","LOW"].map(p=><Metric key={p} label={priorityLabel(p)} value={tasks.filter(t=>t.priority===p).length}/>)}</div>
    {sorted.length===0 && <EmptyState title="You’re caught up." text="AI Data Steward will bring work back here when something changes or needs review."/>}
    {sorted.map(t=>{const isQuality=t.source_type==="QUALITY_ISSUE";return <div className={`task task-${t.priority.toLowerCase()}`} key={t.id}>
      <div className="task-head"><div><div className="eyebrow">{responsibilityLabel(t)} · {t.asset_name}</div><h3>{t.title}</h3></div><span className="priority">{priorityLabel(t.priority)}</span></div>
      <div className="two-col compact"><div><b>Why this matters</b><p>{isQuality?"The quality check found patterns that need a steward's review. They are observations, not automatic errors.":t.why_it_matters}</p></div><div><b>Recommended next step</b><p>{isQuality?"Open the findings workbench, start with the first item marked Needs review, and work through the findings one at a time.":t.recommended_action}</p></div></div>
      <button className="primary" onClick={()=>onGuide(t)}>{isQuality?"Review findings":"Start guided task"}</button>
    </div>})}
  </>;
}

function Discover({systems, userEmail, onDone}) {
  const [step,setStep]=useState(1);
  const [systemName,setSystemName]=useState("");
  const [systemPurpose,setSystemPurpose]=useState("");
  const [touchpointType,setTouchpointType]=useState("SCREEN");
  const [touchpointName,setTouchpointName]=useState("");
  const [informationName,setInformationName]=useState("");
  const [customInformation,setCustomInformation]=useState("");
  const [businessUse,setBusinessUse]=useState("");
  const [createdAsset,setCreatedAsset]=useState(null);
  const [createdSystem,setCreatedSystem]=useState(null);
  const [resourceName,setResourceName]=useState("");
  const [resourceType,setResourceType]=useState("APPLICATION_SCREEN");
  const [structureType,setStructureType]=useState("STRUCTURED");
  const [locationReference,setLocationReference]=useState("");

  function words(text){
    return (text||"").toLowerCase();
  }

  function suggestedInformation(){
    const text=words(`${systemPurpose} ${touchpointName}`);
    const suggestions=[];
    const add=(name,why)=>{ if(!suggestions.some(x=>x.name===name)) suggestions.push({name,why}); };

    if(/corporat|business registration|sunbiz|filing/.test(text)){
      add("Corporate Filings","Records about business registrations, amendments, annual reports, and related corporate actions.");
      add("Registered Agent Information","Information identifying the person or organization designated to receive official notices.");
      add("Business Entity Information","Core information describing registered businesses and their status.");
    }
    if(/licen[cs]|permit|application/.test(text)){
      add("License Applications","Information submitted to request a license, permit, certification, or related agency action.");
      add("Licenses and Credentials","Information about issued licenses, status, dates, and credential details.");
    }
    if(/payment|fee|invoice|billing|transaction/.test(text)){
      add("Payments and Fees","Information about payments, fees, refunds, and related financial transactions.");
    }
    if(/disciplin|complaint|enforcement|violation/.test(text)){
      add("Disciplinary and Enforcement Records","Information about complaints, violations, investigations, and disciplinary actions.");
    }
    if(/employee|human resource|hr|personnel|payroll/.test(text)){
      add("Employee Records","Information used to manage employees, assignments, employment status, and personnel activity.");
      add("Payroll Information","Information used to calculate and administer employee compensation and payroll activity.");
    }
    if(/contract|procure|vendor|purchase/.test(text)){
      add("Vendor and Contract Information","Information about vendors, procurements, contracts, purchasing, and related activity.");
    }
    if(/case|client|customer|participant|citizen|resident/.test(text)){
      add("Case or Client Records","Information used to manage an individual case, client, participant, or service interaction.");
    }
    if(/document|pdf|scan|upload|form/.test(text)){
      add("Submitted Documents","Documents, forms, scans, or attachments submitted as part of the business process.");
    }
    if(/report|dashboard|analytics/.test(text)){
      add("Operational Reporting Information","Information assembled to monitor workload, outcomes, performance, or operational activity.");
    }

    if(suggestions.length===0){
      add("Business Records","The main business information created or maintained through this system or tool.");
      add("Transactions or Activities","Information recording the actions, events, or work performed through this system.");
      add("Supporting Documents","Files, forms, messages, or documents used to support the business process.");
    }
    return suggestions.slice(0,6);
  }

  function resourceDefaults(type){
    const map={
      SCREEN:["APPLICATION_SCREEN","STRUCTURED"],
      FILE:["FILE","SEMI_STRUCTURED"],
      FOLDER:["DOCUMENT_LIBRARY","UNSTRUCTURED"],
      EMAIL:["EMAIL_COLLECTION","UNSTRUCTURED"],
      DOCUMENT:["PDF_COLLECTION","UNSTRUCTURED"],
      REPORT:["REPORT","STRUCTURED"],
      DATABASE:["DATABASE_TABLE","STRUCTURED"],
      API:["API","STRUCTURED"],
    };
    return map[type]||["OTHER","SEMI_STRUCTURED"];
  }

  function chooseTouchpoint(v){
    setTouchpointType(v);
    const [rt,st]=resourceDefaults(v);
    setResourceType(rt);
    setStructureType(st);
  }

  async function ensureSystem(){
    const existing=systems.find(x=>x.name.trim().toLowerCase()===systemName.trim().toLowerCase());
    if(existing){
      setCreatedSystem(existing);
      return existing;
    }
    const created=await api("/systems",userEmail,{
      method:"POST",
      body:JSON.stringify({
        name:systemName.trim(),
        business_purpose:systemPurpose.trim()||businessUse.trim(),
        description:`System identified during guided discovery. ${systemPurpose.trim()}`.trim(),
        vendor:null,
        system_owner:null
      })
    });
    setCreatedSystem(created);
    return created;
  }

  async function createAsset(){
    const chosen=(customInformation.trim()||informationName.trim());
    if(!chosen) return;
    const system=await ensureSystem();
    const definition=businessUse.trim()
      ? `${chosen} is information used to ${businessUse.trim().replace(/\.$/,"")}.`
      : `${chosen} is business information managed through ${systemName}.`;
    const asset=await api("/assets",userEmail,{
      method:"POST",
      body:JSON.stringify({
        name:chosen,
        business_definition:definition,
        business_domain:null,
        business_owner:null,
        data_steward:null
      })
    });
    setCreatedAsset(asset);
    const suggestedResource=touchpointName.trim() || `${chosen} ${touchpointType.toLowerCase()}`;
    setResourceName(suggestedResource);
    setStep(5);
  }

  async function addResource(){
    const system=createdSystem || await ensureSystem();
    await api(`/assets/${createdAsset.asset.asset_id}/resources`,userEmail,{
      method:"POST",
      body:JSON.stringify({
        system_id:system?.id||null,
        name:resourceName.trim() || `${createdAsset.asset.name} source`,
        resource_type:resourceType,
        structure_type:structureType,
        description:`Location identified during guided discovery: ${touchpointType.toLowerCase()} used for ${createdAsset.asset.name}.`,
        location_reference:locationReference.trim()||null,
        relationship_type:"REPRESENTATION",
        is_authoritative:false
      })
    });
    onDone(createdAsset.asset.asset_id);
  }

  const candidates=suggestedInformation();
  const selectedInformation=customInformation.trim()||informationName.trim();

  return <><h1>Discover Your Information</h1>
    <p className="lead">You do not need to know data-governance terminology. Start with the system, screen, file, folder, email, document, or report you already use. We will help identify the business information inside it.</p>
    <div className="stepper">{[1,2,3,4,5].map(n=><div key={n} className={step>=n?"step on":"step"}>{n}</div>)}</div>

    {step===1&&<section className="panel discover-guide">
      <div className="eyebrow">Step 1 · Start with what you know</div>
      <h2>What system or tool does your team use?</h2>
      <p className="lead">This can be a software application, website, shared platform, database, or even a business tool your team has a special name for.</p>
      {systems?.length>0&&<div className="known-systems">
        <span>Already known:</span>
        {systems.map(s=><button type="button" key={s.id} className={systemName===s.name?"mini-choice selected":"mini-choice"} onClick={()=>{setSystemName(s.name);setSystemPurpose(s.business_purpose||"")}}>{s.name}</button>)}
      </div>}
      <label>System or tool name<input value={systemName} onChange={e=>setSystemName(e.target.value)} placeholder="e.g., Sunbiz, Licensing System, SharePoint"/></label>
      <label>What does your team use it to do?<textarea rows="4" value={systemPurpose} onChange={e=>setSystemPurpose(e.target.value)} placeholder="Describe the work in ordinary language. For example: Register businesses and maintain their filing history."/></label>
      <div className="button-row"><button className="primary" disabled={!systemName.trim()||!systemPurpose.trim()} onClick={()=>setStep(2)}>Continue</button></div>
    </section>}

    {step===2&&<section className="panel discover-guide">
      <div className="eyebrow">Step 2 · Identify something people actually use</div>
      <h2>What do you interact with in {systemName}?</h2>
      <p className="lead">Think about where you see, enter, receive, download, or work with information. This helps us move from “the system” to the actual information your organization manages.</p>
      <div className="touchpoint-grid">
        {[
          ["SCREEN","Screen or page","A screen where people view or enter information"],
          ["FILE","File or download","CSV, spreadsheet, fixed-width file, export, or other file"],
          ["FOLDER","Folder or library","Shared drive, SharePoint library, or collection of files"],
          ["EMAIL","Email or mailbox","Messages or an email collection used for business work"],
          ["DOCUMENT","Document or form","PDF, scanned form, application, image, or document"],
          ["REPORT","Report or dashboard","A report, dashboard, extract, or recurring output"],
          ["DATABASE","Database data","A table, view, or database source you know about"],
          ["API","API or interface","Information exchanged with another system"]
        ].map(([v,title,help])=><button type="button" key={v} className={touchpointType===v?"touchpoint selected":"touchpoint"} onClick={()=>chooseTouchpoint(v)}><b>{title}</b><span>{help}</span></button>)}
      </div>
      <label>What is it called?<input value={touchpointName} onChange={e=>setTouchpointName(e.target.value)} placeholder={touchpointType==="SCREEN"?"e.g., Corporate Filing Search screen":"Give it the name your team uses"}/></label>
      <div className="button-row"><button onClick={()=>setStep(1)}>Back</button><button className="primary" disabled={!touchpointName.trim()} onClick={()=>setStep(3)}>Help me identify the information</button></div>
    </section>}

    {step===3&&<section className="panel discover-guide">
      <div className="eyebrow">Step 3 · Identify the business information</div>
      <h2>What business information does “{touchpointName}” manage?</h2>
      <p className="lead">Based on what you told us, these are possibilities—not automatic answers. Choose the one that best matches how your organization thinks about the information, or enter your own.</p>
      <div className="candidate-list guided-candidates">
        {candidates.map(c=><button type="button" className={informationName===c.name&&!customInformation?"info-candidate selected":"info-candidate"} key={c.name} onClick={()=>{setInformationName(c.name);setCustomInformation("")}}><b>{c.name}</b><span>{c.why}</span></button>)}
      </div>
      <div className="or-divider"><span>or describe it yourself</span></div>
      <label>Business information name<input value={customInformation} onChange={e=>{setCustomInformation(e.target.value);if(e.target.value)setInformationName("")}} placeholder="Use the name business staff would recognize"/></label>
      <div className="education"><b>What are we doing?</b><p>We are separating the <b>system</b> from the <b>information</b>. A system can manage several kinds of business information, and the same information can exist in several places.</p></div>
      <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" disabled={!selectedInformation} onClick={()=>setStep(4)}>Continue</button></div>
    </section>}

    {step===4&&<section className="panel discover-guide">
      <div className="eyebrow">Step 4 · Describe why it exists</div>
      <h2>What does {selectedInformation} help your team do?</h2>
      <p className="lead">Describe the business purpose, not the technology. This becomes the starting description other employees will use to understand the information.</p>
      <textarea rows="5" value={businessUse} onChange={e=>setBusinessUse(e.target.value)} placeholder={`For example: Process business registrations, confirm filing status, and respond to public and agency questions about registered entities.`}/>
      <div className="discovery-summary">
        <div><span>System</span><b>{systemName}</b></div>
        <div><span>Where you encountered it</span><b>{touchpointName}</b></div>
        <div><span>Business information</span><b>{selectedInformation}</b></div>
      </div>
      <div className="button-row"><button onClick={()=>setStep(3)}>Back</button><button className="primary" disabled={!businessUse.trim()} onClick={createAsset}>This looks right</button></div>
    </section>}

    {step===5&&createdAsset&&<section className="panel discover-guide">
      <div className="eyebrow">Step 5 · Record where the information lives</div>
      <h2>Where did you find {createdAsset.asset.name}?</h2>
      <p className="lead">You have identified the business information. Now record the screen, file, folder, document, report, database, or interface that represents it.</p>
      <div className="education strong"><b>Important</b><p>This is not yet declaring the official or authoritative source. You are simply recording a known place where the information exists. We will guide that decision separately.</p></div>
      <label>Name for this location or representation<input value={resourceName} onChange={e=>setResourceName(e.target.value)}/></label>
      <label>Where is it located? <span className="muted">(optional)</span><input value={locationReference} onChange={e=>setLocationReference(e.target.value)} placeholder="URL, folder path, database/schema/table, report name, or other locator"/></label>
      <details className="advanced-details"><summary>Technical details</summary>
        <div className="form-grid">
          <label>Representation type<select value={resourceType} onChange={e=>setResourceType(e.target.value)}><option value="APPLICATION_SCREEN">Application screen</option><option value="FILE">File</option><option value="DOCUMENT_LIBRARY">Document library</option><option value="EMAIL_COLLECTION">Email collection</option><option value="PDF_COLLECTION">PDF/document collection</option><option value="REPORT">Report/dashboard</option><option value="SPREADSHEET">Spreadsheet</option><option value="DATABASE_TABLE">Database table</option><option value="API">API</option><option value="OTHER">Other</option></select></label>
          <label>Structure<select value={structureType} onChange={e=>setStructureType(e.target.value)}><option value="STRUCTURED">Structured</option><option value="SEMI_STRUCTURED">Semi-structured</option><option value="UNSTRUCTURED">Unstructured</option></select></label>
        </div>
      </details>
      <div className="button-row"><button className="primary" disabled={!resourceName.trim()} onClick={addResource}>Finish discovery</button></div>
    </section>}
  </>;
}

function Asset360({asset,assets,systems,tasks,role,userEmail,selectedAssetId,setSelectedAssetId,doAction,tab,setTab,selectedQualityIssueId,setSelectedQualityIssueId,guidedTask,setGuidedTask}) {
  const [quality,setQuality]=useState(null), [metaKey,setMetaKey]=useState("theme"), [metaValue,setMetaValue]=useState("Professional Licensing"), [gov,setGov]=useState({});
  useEffect(()=>{if(asset){setGov({business_owner:asset.asset.business_owner||"",data_steward:asset.asset.data_steward||"",classification:asset.asset.classification||"",retention_requirement:asset.asset.retention_requirement||"",retention_authority:asset.asset.retention_authority||""});api(`/assets/${asset.asset.asset_id}/quality`,userEmail).then(setQuality)}},[asset?.asset?.asset_id,userEmail]);
  if(!asset)return <p>No information has been identified yet.</p>; const a=asset.asset;
  return <><div className="title-row"><div><h1>Information Details</h1><p className="lead">This page brings together what the information means, where it lives, how it is governed, whether it can be trusted, and whether it is ready to share.</p></div><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select></div>
    <section className="asset-hero"><div><div className="eyebrow">{a.business_domain||"Business information"}</div><h2>{a.name}</h2><p>{a.business_definition}</p></div><div className="hero-scores"><div><span>Stewardship</span><strong>{asset.readiness.score}%</strong></div><div><span>Information quality</span><strong>{asset.quality?.overall_score != null ? `${asset.quality.overall_score}%` : "—"}</strong></div><Status value={asset.publication.status}/></div></section>
    <div className="tabs">{["Overview","Where It Lives","Help Others Understand It","Governance","Can This Information Be Trusted?","Review & Maintain","Share & Publish"].map(t=><button key={t} className={tab===t?"tab active":"tab"} onClick={()=>setTab(t)}>{t}</button>)}</div>
    {tab==="Overview"&&<InformationOverview asset={asset} tasks={tasks} setTab={setTab} setGuidedTask={setGuidedTask} setSelectedQualityIssueId={setSelectedQualityIssueId}/>}
    {tab==="Where It Lives"&&<WhereItLives asset={asset} userEmail={userEmail} doAction={doAction}/>}
    {tab==="Help Others Understand It"&&<UnderstandingGuide asset={asset} userEmail={userEmail} doAction={doAction} />}
    {tab==="Governance"&&<GovernanceGuide asset={asset} gov={gov} setGov={setGov} userEmail={userEmail} doAction={doAction} guidedTask={guidedTask} setGuidedTask={setGuidedTask}/>}
    {tab==="Can This Information Be Trusted?"&&<QualityPanel quality={quality} asset={asset} userEmail={userEmail} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} doAction={async(fn,msg)=>{await doAction(fn,msg);setQuality(await api(`/assets/${a.asset_id}/quality`,userEmail))}}/>}
    {tab==="Review & Maintain"&&<PeriodicReviewPanel asset={asset} userEmail={userEmail} doAction={doAction} guidedTask={guidedTask} setGuidedTask={setGuidedTask}/>}
    {tab==="Share & Publish"&&<PublicationPanel asset={asset} role={role} userEmail={userEmail} doAction={doAction}/>} 
  </>;
}

function InformationOverview({asset,tasks,setTab,setGuidedTask,setSelectedQualityIssueId}) {
  const a=asset.asset;
  const official=asset.resources?.find(r=>r.is_authoritative);
  const assetTasks=(tasks||[]).filter(t=>t.asset_id===a.asset_id);
  const rank={HIGH:0,MEDIUM:1,LOW:2};
  const actionable=assetTasks
    .filter(t=>(t.bucket||"NOW")==="NOW")
    .sort((x,y)=>(rank[x.priority]??9)-(rank[y.priority]??9));
  const waiting=assetTasks.filter(t=>(t.bucket||"NOW")==="WAITING");
  const next=actionable[0]||null;
  const checks=asset.readiness?.checks||[];

  const complete=(key)=>checks.find(c=>c.key===key)?.complete===true;
  const descriptionCurrent=complete("business_definition")&&complete("theme");
  const locationsCurrent=complete("has_resource");
  const officialCurrent=complete("authoritative_source") || Boolean(official);
  const ownershipCurrent=complete("business_owner");
  const classificationCurrent=complete("classification");
  const retentionCurrent=complete("retention");
  const qualityCurrent=complete("quality");
  const publishReady=asset.readiness?.ready_to_submit===true;

  const statusItems=[
    {
      key:"description",
      label:"Description",
      complete:descriptionCurrent,
      text:descriptionCurrent?"Business meaning and area are recorded.":"The business description or business area needs attention.",
      tab:"Help Others Understand It",
    },
    {
      key:"locations",
      label:"Where it lives",
      complete:locationsCurrent,
      text:locationsCurrent?`${asset.resources?.length||0} known location${asset.resources?.length===1?"":"s"} recorded.`:"No known location has been recorded yet.",
      tab:"Where It Lives",
    },
    {
      key:"official",
      label:"Official source",
      complete:officialCurrent,
      text:officialCurrent?`Confirmed${official?.name?`: ${official.name}`:"."}`:"The location the organization relies on as official still needs confirmation.",
      tab:"Where It Lives",
    },
    {
      key:"ownership",
      label:"Ownership",
      complete:ownershipCurrent,
      text:ownershipCurrent?`Business owner: ${a.business_owner}`:"The accountable business owner still needs to be identified.",
      tab:"Governance",
    },
    {
      key:"classification",
      label:"Handling & sensitivity",
      complete:classificationCurrent,
      text:classificationCurrent?`Current classification: ${a.classification}`:"How this information should be handled still needs review.",
      tab:"Governance",
    },
    {
      key:"retention",
      label:"Retention",
      complete:retentionCurrent,
      text:retentionCurrent?`Requirement recorded: ${a.retention_requirement}`:"Retention requirements have not been confirmed.",
      tab:"Governance",
    },
    {
      key:"quality",
      label:"Trust & quality",
      complete:qualityCurrent,
      text:qualityCurrent
        ? `Last quality score: ${asset.quality?.overall_score!=null?`${asset.quality.overall_score}%`:"assessed"}`
        : "Quality has not yet been assessed for this information.",
      tab:"Can This Information Be Trusted?",
    },
    {
      key:"publish",
      label:"Ready to share",
      complete:publishReady,
      text:publishReady?"Required stewardship checks are complete.":"Required stewardship work remains before submission.",
      tab:"Share & Publish",
    },
  ];

  function openTask(task){
    if(!task) return;
    if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
      setGuidedTask(null);
      setSelectedQualityIssueId(Number(task.source_reference));
      setTab("Can This Information Be Trusted?");
      return;
    }
    setSelectedQualityIssueId(null);
    setGuidedTask(task);
    if(task.source_type==="PERIODIC_REVIEW"){
      setTab("Review & Maintain");
    }else if(task.governance_domain==="QUALITY"){
      setTab("Can This Information Be Trusted?");
    }else if(["METADATA","DESCRIPTION"].includes(task.governance_domain) || ["business_definition","theme","keywords","update_frequency","contact"].includes(task.task_type)){
      setTab("Help Others Understand It");
    }else if(task.task_type==="has_resource" || task.task_type==="authoritative_source" || task.task_type==="review_change_locations" || task.task_type==="review_change_official_source"){
      setTab("Where It Lives");
    }else{
      setTab("Governance");
    }
  }

  return <>
    {next?<section className="panel overview-next-action">
      <div className="next-action-label">Recommended next action</div>
      <div className="next-action-content">
        <div>
          <span className={`priority priority-${(next.priority||"MEDIUM").toLowerCase()}`}>{priorityLabel(next.priority)}</span>
          <h2>{next.title}</h2>
          <p>{next.why_it_matters}</p>
          <small>{next.responsibility||"AI Data Steward will guide you through the decision."}</small>
        </div>
        <button className="primary next-action-button" onClick={()=>openTask(next)}>{next.source_type==="QUALITY_ISSUE"?"Review findings":"Start guided task"}</button>
      </div>
    </section>:<section className="panel overview-all-clear">
      <div className="completion-mark">✓</div>
      <div><div className="eyebrow">Current status</div><h2>No immediate stewardship work needs your attention.</h2><p>Use the status below to review the information or make updates when something changes.</p></div>
    </section>}

    <section className="panel">
      <div className="task-head">
        <div><div className="eyebrow">Stewardship status</div><h2>What is complete and what still needs attention</h2><p className="lead">You do not need to choose a governance module. Open any item for context, or follow the recommended next action above.</p></div>
        <div className="overview-completeness"><strong>{asset.readiness?.score??0}%</strong><span>complete</span></div>
      </div>

      <div className="stewardship-status-list">
        {statusItems.map(item=><button key={item.key} type="button" className={item.complete?"stewardship-status complete":"stewardship-status attention"} onClick={()=>setTab(item.tab)}>
          <span className="status-icon">{item.complete?"✓":"!"}</span>
          <div><b>{item.label}</b><small>{item.text}</small></div>
          <span className="status-open">{item.complete?"Review":"Needs attention"} →</span>
        </button>)}
      </div>
    </section>

    <div className="two-col overview-support">
      <section className="panel">
        <div className="eyebrow">At a glance</div>
        <h3>About this information</h3>
        <p>{a.business_definition||"A plain-language description still needs to be completed."}</p>
        <div className="mini-facts">
          <div><span>Business area</span><b>{a.business_domain||"Needs review"}</b></div>
          <div><span>Known locations</span><b>{asset.resources?.length||0}</b></div>
          <div><span>Official source</span><b>{official?.name||"Needs confirmation"}</b></div>
          <div><span>Publication</span><Status value={asset.publication.status}/></div>
        </div>
      </section>

      <section className="panel">
        <div className="eyebrow">Work queue</div>
        <h3>Other work for this information</h3>
        {actionable.slice(1,4).length===0&&waiting.length===0&&<div className="empty">No additional tasks for this information.</div>}
        {actionable.slice(1,4).map(t=><button className="overview-task-row" key={t.id} onClick={()=>openTask(t)}>
          <span className={`priority priority-${(t.priority||"MEDIUM").toLowerCase()}`}>{priorityLabel(t.priority)}</span>
          <div><b>{t.title}</b><small>{responsibilityLabel(t)}</small></div>
          <span>Open →</span>
        </button>)}
        {waiting.slice(0,2).map(t=><div className="overview-task-row waiting" key={t.id}>
          <span className="waiting-pill">Waiting</span>
          <div><b>{t.title}</b><small>{responsibilityLabel(t)}</small></div>
          <span>Pending</span>
        </div>)}
      </section>
    </div>
  </>;
}

function WhereItLives({asset,userEmail,doAction}) {
  const a=asset.asset;
  const locations=asset.resources||[];
  const currentOfficial=locations.find(r=>r.is_authoritative);
  const [mode,setMode]=useState("LIST");
  const [step,setStep]=useState(1);
  const [selectedId,setSelectedId]=useState(currentOfficial?.resource_id||"");
  const [originAnswer,setOriginAnswer]=useState("");
  const [conflictAnswer,setConflictAnswer]=useState("");
  const [copyAnswer,setCopyAnswer]=useState("");
  const [basis,setBasis]=useState("");

  function selected(){
    return locations.find(r=>r.resource_id===Number(selectedId));
  }

  function recommendationText(){
    const s=selected();
    if(!s) return "";
    const reasons=[];
    if(originAnswer==="yes") reasons.push("this is where the information is originally created or officially maintained");
    if(conflictAnswer==="yes") reasons.push("the organization would rely on this location if versions disagreed");
    if(copyAnswer==="no") reasons.push("it is not merely a copy, export, report, or working extract");
    return reasons.length
      ? `${s.name} appears to be the official source because ${reasons.join(", ")}.`
      : `${s.name} is the location you identified as the source the organization should rely on for official business decisions.`;
  }

  function reviewRecommendation(){
    setBasis(recommendationText());
    setStep(4);
  }

  async function confirmOfficial(){
    const s=selected();
    if(!s) return;
    await doAction(
      ()=>api(`/assets/${a.asset_id}/official-source`,userEmail,{
        method:"POST",
        body:JSON.stringify({
          resource_id:s.resource_id,
          decision_basis:basis.trim()||recommendationText()
        })
      }),
      `${s.name} is now recorded as the official source.`
    );
    setMode("LIST");
    setStep(1);
  }

  if(mode==="GUIDE"){
    return <section className="panel official-source-guide">
      <div className="wizard-head">
        <div><div className="eyebrow">Guided task · Official source</div><h2>Which location should people rely on as official?</h2><p className="lead">The same business information can exist in a database, download, report, spreadsheet, document library, or other location. We will help you identify which one should be trusted when those versions differ.</p></div>
        <span>Step {step} of 4</span>
      </div>

      {step===1&&<>
        <h3>Where is the information originally created or officially maintained?</h3>
        <p className="lead">Choose the place closest to the business process that creates or maintains the official record. Do not automatically choose the place that is easiest to access.</p>
        <div className="source-choice-list">
          {locations.map(r=><button type="button" key={r.resource_id} className={Number(selectedId)===r.resource_id?"source-choice selected":"source-choice"} onClick={()=>setSelectedId(r.resource_id)}>
            <div><b>{r.name}</b><span>{r.system||"No system recorded"} · {friendlyResourceType(r.resource_type)}</span></div>
            <small>{r.location_reference||r.description||"No location details recorded"}</small>
          </button>)}
        </div>
        {locations.length===0&&<div className="education strong"><b>No known locations yet.</b><p>Use Discover Information to record at least one place where this information exists before determining the official source.</p></div>}
        <div className="button-row"><button onClick={()=>setMode("LIST")}>Cancel</button><button className="primary" disabled={!selectedId} onClick={()=>setStep(2)}>Continue</button></div>
      </>}

      {step===2&&<>
        <h3>If two versions disagreed, would the organization rely on {selected()?.name}?</h3>
        <p className="lead">Imagine a report, spreadsheet, or download shows one value and this location shows another. Which one would staff treat as the official record for a business decision?</p>
        <Choice value={conflictAnswer} setValue={setConflictAnswer} options={[["yes","Yes — this is what we would rely on"],["no","No — another location would be considered official"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(1)}>Back</button>{conflictAnswer==="no"?<button className="primary" onClick={()=>{setSelectedId("");setConflictAnswer("");setStep(1)}}>Choose a different location</button>:<button className="primary" disabled={!conflictAnswer||conflictAnswer==="unsure"} onClick={()=>setStep(3)}>Continue</button>}</div>
        {conflictAnswer==="unsure"&&<div className="education strong"><b>Good choice—do not guess.</b><p>Confirm this with the business owner or the team responsible for the process before making an official-source decision.</p></div>}
      </>}

      {step===3&&<>
        <h3>Is {selected()?.name} mainly a copy, export, report, or working extract?</h3>
        <p className="lead">Copies can be useful and trustworthy, but they usually should not be labeled the official source if another location is where the record is actually maintained.</p>
        <Choice value={copyAnswer} setValue={setCopyAnswer} options={[["no","No — the official record is maintained here"],["yes","Yes — this is mainly a copy, export, report, or extract"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(2)}>Back</button>{copyAnswer==="yes"?<button className="primary" onClick={()=>{setSelectedId("");setCopyAnswer("");setStep(1)}}>Choose a different location</button>:<button className="primary" disabled={!copyAnswer||copyAnswer==="unsure"} onClick={reviewRecommendation}>Review recommendation</button>}</div>
        {copyAnswer==="unsure"&&<div className="education strong"><b>Good choice—verify it first.</b><p>Ask whether this location is where the official record is maintained or whether it is generated from another source.</p></div>}
      </>}

      {step===4&&<>
        <h3>Recommended official source</h3>
        <div className="recommendation-card">
          <span>AI Data Steward recommends</span>
          <strong>{selected()?.name}</strong>
          <p>{basis}</p>
        </div>
        <div className="education"><b>What this decision means</b><p>Other known locations can still be useful. This simply records which one people should rely on when they need the official business record.</p></div>
        <label>Why is this the official source?<textarea rows="4" value={basis} onChange={e=>setBasis(e.target.value)} /></label>
        <div className="button-row"><button onClick={()=>setStep(3)}>Back</button><button className="primary" onClick={confirmOfficial}>Confirm official source</button></div>
      </>}
    </section>;
  }

  return <section className="panel">
    <div className="task-head">
      <div><div className="eyebrow">Where it lives</div><h2>Known locations and representations</h2><p className="lead">The same information can exist in more than one place. Record those places here, then identify which one should be relied on as the official business source.</p></div>
      <button className="primary" disabled={locations.length===0} onClick={()=>{setMode("GUIDE");setStep(1);setSelectedId(currentOfficial?.resource_id||"")}}>{currentOfficial?"Review official source":"Determine official source"}</button>
    </div>

    {locations.length===0&&<div className="empty">No locations have been recorded yet. Use Discover Information to add the first place where this information exists.</div>}

    <div className="location-list">
      {locations.map(r=><div className={r.is_authoritative?"location-card official":"location-card"} key={r.resource_id}>
        <div className="location-main">
          <div><b>{r.name}</b>{r.is_authoritative&&<span className="official-badge">Official source</span>}</div>
          <span>{r.system||"No system recorded"} · {friendlyResourceType(r.resource_type)}</span>
          <small>{r.location_reference||r.description||"No location details recorded"}</small>
        </div>
        <div className="location-context">
          <span>{friendlyStructure(r.structure_type)}</span>
          <span>{r.relationship_type==="REPRESENTATION"?"Known representation":r.relationship_type}</span>
        </div>
      </div>)}
    </div>

    {currentOfficial?<div className="education strong"><b>Official source confirmed: {currentOfficial.name}</b><p>If this information also exists in reports, downloads, spreadsheets, APIs, or document collections, those can remain recorded without being treated as the official record.</p></div>:locations.length>0&&<div className="education strong"><b>The official source still needs to be confirmed.</b><p>Use the guided questions above. You do not need to know terms like “system of record” or “authoritative resource.”</p></div>}
  </section>;
}

function friendlyResourceType(value){
  const labels={
    APPLICATION_SCREEN:"Application screen",
    FILE:"File or download",
    DOCUMENT_LIBRARY:"Folder or document library",
    EMAIL_COLLECTION:"Email collection",
    PDF_COLLECTION:"Documents or PDFs",
    REPORT:"Report or dashboard",
    SPREADSHEET:"Spreadsheet",
    DATABASE_TABLE:"Database data",
    API:"API or system interface",
    OTHER:"Other location"
  };
  return labels[value]||String(value||"Location").replaceAll("_"," ").toLowerCase();
}

function friendlyStructure(value){
  const labels={STRUCTURED:"Organized fields/records",SEMI_STRUCTURED:"Partly structured",UNSTRUCTURED:"Documents/content"};
  return labels[value]||String(value||"").replaceAll("_"," ").toLowerCase();
}

function PeriodicReviewPanel({asset,userEmail,doAction,guidedTask,setGuidedTask}) {
  const a=asset.asset;
  const [reviewData,setReviewData]=useState(null);
  const [mode,setMode]=useState(guidedTask?.source_type==="PERIODIC_REVIEW"?"REVIEW":"SUMMARY");
  const [step,setStep]=useState(1);
  const [answers,setAnswers]=useState({});
  const [notes,setNotes]=useState("");
  const [result,setResult]=useState(null);

  useEffect(()=>{
    api(`/assets/${a.asset_id}/reviews`,userEmail).then(setReviewData).catch(()=>setReviewData(null));
  },[a.asset_id,userEmail]);

  useEffect(()=>{
    if(guidedTask?.source_type==="PERIODIC_REVIEW"){
      setMode("REVIEW");
      setStep(1);
    }
  },[guidedTask?.id]);

  const questions=[
    {
      key:"purpose",
      title:"Has the business purpose changed?",
      help:"Think about what this information helps the organization accomplish and how people use it.",
      yes:"No — it still serves the same purpose",
      changed:"Yes — how it is used or what it represents has changed"
    },
    {
      key:"ownership",
      title:"Has the business owner or steward changed?",
      help:"Think about who can make business decisions about the information and who coordinates stewardship day to day.",
      yes:"No — the same people or roles are still responsible",
      changed:"Yes — ownership or stewardship responsibility has changed"
    },
    {
      key:"locations",
      title:"Does the information still live in the same places?",
      help:"Consider systems, files, folders, reports, databases, document collections, APIs, or other known locations.",
      yes:"Yes — the known locations are still correct",
      changed:"No — a location was added, removed, replaced, or changed"
    },
    {
      key:"official_source",
      title:"Is the official source still the place the organization would rely on?",
      help:"Imagine two versions disagree. Would staff still rely on the currently recorded official source?",
      yes:"Yes — the official source is still correct",
      changed:"No — another location may now be the official source"
    },
    {
      key:"classification",
      title:"Has anything changed that could affect how this information should be handled?",
      help:"Think about sensitivity, personal information, public availability, legal restrictions, access, or sharing.",
      yes:"No — the handling/classification still appears appropriate",
      changed:"Yes — sensitivity, access, or sharing conditions may have changed"
    },
    {
      key:"retention",
      title:"Is the retention requirement still applicable?",
      help:"Consider whether the business process, records schedule, policy, or retention authority has changed.",
      yes:"Yes — the current retention requirement still applies",
      changed:"No — the requirement or authority may have changed"
    },
    {
      key:"quality",
      title:"Have there been meaningful new quality concerns?",
      help:"Think about recurring errors, missing information, unusual values, complaints, reconciliation problems, or changes to the source.",
      yes:"No — no meaningful new quality concerns",
      changed:"Yes — quality should be reassessed"
    },
    {
      key:"active_use",
      title:"Is this information still actively used?",
      help:"Consider whether the business still creates, updates, relies on, or needs this information.",
      yes:"Yes — it is still actively used",
      changed:"No — it may no longer be actively used"
    }
  ];

  const q=questions[step-1];
  const changedKeys=Object.entries(answers).filter(([k,v])=>{
    if(k==="active_use") return v==="no" || v==="unsure";
    return v==="changed" || v==="unsure";
  }).map(([k])=>k);

  function answer(value){
    setAnswers({...answers,[q.key]:value});
  }

  function next(){
    if(step<questions.length) setStep(step+1);
    else setStep(questions.length+1);
  }

  function back(){
    if(step>1) setStep(step-1);
  }

  async function submitReview(){
    const response=await api(`/assets/${a.asset_id}/reviews`,userEmail,{
      method:"POST",
      body:JSON.stringify({
        answers,
        change_summary:notes.trim()||null,
        review_interval_days:365
      })
    });
    setResult(response);
    setReviewData(await api(`/assets/${a.asset_id}/reviews`,userEmail));
    setMode("COMPLETE");
    setGuidedTask?.(null);
  }

  if(mode==="REVIEW"){
    return <section className="panel periodic-review-guide">
      <div className="wizard-head">
        <div>
          <div className="eyebrow">Guided task · Review what changed</div>
          <h2>Keep this stewardship information current</h2>
          <p className="lead">You do not need to redo the whole process. Answer a short set of questions, and AI Data Steward will reopen only the areas that need attention.</p>
        </div>
        <span>{step<=questions.length?`Step ${step} of ${questions.length}`:"Review"}</span>
      </div>

      {step<=questions.length&&q&&<>
        <h3>{q.title}</h3>
        <p className="lead">{q.help}</p>
        <div className="review-choice-grid">
          <button type="button" className={answers[q.key]==="same"?"review-choice selected":"review-choice"} onClick={()=>answer("same")}><b>{q.yes}</b><span>No follow-up will be created for this area.</span></button>
          <button type="button" className={answers[q.key]===("active_use"===q.key?"no":"changed")?"review-choice selected changed":"review-choice"} onClick={()=>answer(q.key==="active_use"?"no":"changed")}><b>{q.changed}</b><span>AI Data Steward will create a focused follow-up task.</span></button>
          <button type="button" className={answers[q.key]==="unsure"?"review-choice selected unsure":"review-choice"} onClick={()=>answer("unsure")}><b>I’m not sure</b><span>We will create a follow-up so you can verify this rather than guessing.</span></button>
        </div>
        <div className="button-row"><button disabled={step===1} onClick={back}>Back</button><button className="primary" disabled={!answers[q.key]} onClick={next}>{step===questions.length?"Review answers":"Continue"}</button></div>
      </>}

      {step===questions.length+1&&<>
        <h3>Review complete — here is what needs follow-up</h3>
        {changedKeys.length===0?<div className="education strong"><b>No changes identified.</b><p>Your existing stewardship decisions can remain in place. Completing this review will record that they were reconfirmed today.</p></div>:<>
          <p className="lead">You identified {changedKeys.length} area{changedKeys.length===1?"":"s"} that may need attention. You do not need to fix them inside this review; AI Data Steward will create focused next steps.</p>
          <div className="review-followup-list">
            {changedKeys.map(k=><div key={k}><span>Needs follow-up</span><b>{questions.find(x=>x.key===k)?.title}</b></div>)}
          </div>
        </>}
        <label>Anything else you want to record about this review? <span className="muted">(optional)</span><textarea rows="4" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Add context about what changed, what you verified, or what someone should know next."/></label>
        <div className="education"><b>What happens after you finish?</b><p>This review is recorded in history, the next review is scheduled for one year from now, and only the areas you marked as changed or uncertain become new tasks.</p></div>
        <div className="button-row"><button onClick={()=>setStep(questions.length)}>Back</button><button className="primary" onClick={submitReview}>Complete review</button></div>
      </>}
    </section>;
  }

  if(mode==="COMPLETE"){
    return <section className="panel">
      <div className="completion-state">
        <div className="completion-mark">✓</div>
        <div><h2>Complete — periodic review recorded</h2><p>{result?.message||"Your review was recorded."}</p></div>
      </div>
      {result?.follow_up_tasks?.length>0&&<div className="review-followup-list">
        {result.follow_up_tasks.map(t=><div key={t}><span>Added to My Next Steps</span><b>{t}</b></div>)}
      </div>}
      <div className="button-row"><button onClick={()=>setMode("SUMMARY")}>View review history</button></div>
    </section>;
  }

  const latest=reviewData?.latest;
  const due=reviewData?.next_review_due ? new Date(reviewData.next_review_due) : null;
  return <section className="panel">
    <div className="task-head">
      <div>
        <div className="eyebrow">Review & maintain</div>
        <h2>Keep this information current over time</h2>
        <p className="lead">Stewardship is not one-and-done. Periodic reviews confirm that the information, ownership, locations, rules, and quality context still reflect reality.</p>
      </div>
      <button className="primary" onClick={()=>{setAnswers({});setNotes("");setResult(null);setStep(1);setMode("REVIEW")}}>{latest?"Review what changed":"Complete first review"}</button>
    </div>

    <div className="review-status-grid">
      <div><span>Last reviewed</span><b>{latest?.reviewed_at?new Date(latest.reviewed_at).toLocaleDateString():"Not reviewed yet"}</b></div>
      <div><span>Next review</span><b>{due?due.toLocaleDateString():"Not scheduled"}</b></div>
      <div><span>Status</span><b>{reviewData?.is_due?"Review due":"Current"}</b></div>
    </div>

    {latest&&<div className="education strong"><b>Most recent review</b><p>{latest.change_summary||"The steward completed the review without additional notes."}</p></div>}

    <h3>Review history</h3>
    {(reviewData?.history||[]).length===0?<EmptyState title="No periodic reviews yet." text="Complete the first review when you want to establish a maintenance history."/>:<div className="review-history">
      {reviewData.history.map(r=>{
        const flagged=Object.entries(r.answers||{}).filter(([k,v])=>k==="active_use"?["no","unsure"].includes(v):["changed","unsure"].includes(v)).length;
        return <div key={r.id}><div><b>{new Date(r.reviewed_at).toLocaleDateString()}</b><span>{flagged===0?"No changes identified":`${flagged} area${flagged===1?"":"s"} needed follow-up`}</span></div><small>Next review: {new Date(r.next_review_due).toLocaleDateString()}</small></div>;
      })}
    </div>}
  </section>;
}

function UnderstandingGuide({asset,userEmail,doAction}) {
  const a=asset.asset;
  const existing=asset.metadata||{};
  const [step,setStep]=useState(1);
  const [businessArea,setBusinessArea]=useState(existing.theme||a.business_domain||"");
  const [audienceNeed,setAudienceNeed]=useState("");
  const [searchTerms,setSearchTerms]=useState(
    Array.isArray(existing.keyword) ? existing.keyword.join(", ") : (existing.keyword||"")
  );
  const [updatePattern,setUpdatePattern]=useState(existing.update_frequency||"");
  const [contactPoint,setContactPoint]=useState(existing.contact||"");
  const [businessPurpose,setBusinessPurpose]=useState(a.business_definition||"");
  const [suggestedTerms,setSuggestedTerms]=useState([]);

  function buildSuggestions(){
    const source=`${a.name||""} ${businessPurpose} ${businessArea} ${audienceNeed}`.toLowerCase();
    const terms=new Set();

    const add=(...xs)=>xs.forEach(x=>terms.add(x));
    if(/corporat|business registration|filing/.test(source)) add("corporations","business registration","corporate filings","registered agent");
    if(/licen[cs]|permit|credential/.test(source)) add("licenses","applications","credentials","permits");
    if(/payment|fee|invoice|billing/.test(source)) add("payments","fees","transactions");
    if(/employee|human resource|personnel|payroll/.test(source)) add("employees","human resources","personnel");
    if(/contract|vendor|procure/.test(source)) add("vendors","contracts","procurement");
    if(/complaint|disciplin|enforcement/.test(source)) add("complaints","disciplinary actions","enforcement");
    if(/case|client|participant/.test(source)) add("cases","clients","participants");
    if(/report|dashboard|performance/.test(source)) add("reports","performance","operations");

    for (const word of (a.name||"").split(/\s+/)) {
      const clean=word.replace(/[^A-Za-z0-9-]/g,"").toLowerCase();
      if(clean.length>3) terms.add(clean);
    }
    setSuggestedTerms([...terms].slice(0,8));
    setStep(4);
  }

  function toggleTerm(term){
    const current=searchTerms.split(",").map(x=>x.trim()).filter(Boolean);
    const lower=current.map(x=>x.toLowerCase());
    const next=lower.includes(term.toLowerCase())
      ? current.filter(x=>x.toLowerCase()!==term.toLowerCase())
      : [...current,term];
    setSearchTerms(next.join(", "));
  }

  async function save(){
    const payload={
      business_definition: businessPurpose.trim(),
      business_area: businessArea.trim(),
      search_terms: searchTerms.split(",").map(x=>x.trim()).filter(Boolean),
      update_frequency: updatePattern,
      contact_point: contactPoint.trim()
    };

    await doAction(
      ()=>api(`/assets/${a.asset_id}/understanding`,userEmail,{
        method:"PATCH",
        body:JSON.stringify(payload)
      }),
      "Information description saved."
    );
    setStep(6);
  }

  return <section className="panel understanding-guide">
    <div className="wizard-head">
      <div>
        <div className="eyebrow">Guided task · Help others understand it</div>
        <h2>Describe this information in business language</h2>
        <p className="lead">Explain this information the same way you would to a coworker who had never seen it before. AI Data Steward will organize your answers for you.</p>
      </div>
      <span>Step {step} of 6</span>
    </div>

    {step===1&&<>
      <h3>What part of the organization’s work is this information about?</h3>
      <p className="lead">Use the business area people would recognize—not the database, software vendor, or technical team.</p>
      <div className="choice-grid">
        {["Business registration","Professional licensing","Finance","Human resources","Public safety","Operations","Legal / compliance","Other"].map(v=><button key={v} type="button" className={businessArea===v?"choice selected":"choice"} onClick={()=>setBusinessArea(v)}>{v}</button>)}
      </div>
      <label>Or describe the business area<input value={businessArea} onChange={e=>setBusinessArea(e.target.value)} placeholder="e.g., Division of Corporations / Business Registration"/></label>
      <div className="button-row"><button className="primary" disabled={!businessArea.trim()} onClick={()=>setStep(2)}>Continue</button></div>
    </>}

    {step===2&&<>
      <h3>What would another employee need to know to understand this information?</h3>
      <p className="lead">Describe what it represents, what it is used for, and anything someone could easily misunderstand.</p>
      <textarea rows="5" value={businessPurpose} onChange={e=>setBusinessPurpose(e.target.value)} placeholder="For example: This information records corporation registrations, filing status, registered agents, and filing history used by agency staff and the public to verify business standing."/>
      <div className="education"><b>Why we ask this</b><p>This becomes the plain-language explanation people see when they discover the information later.</p></div>
      <div className="button-row"><button onClick={()=>setStep(1)}>Back</button><button className="primary" disabled={!businessPurpose.trim()} onClick={()=>setStep(3)}>Continue</button></div>
    </>}

    {step===3&&<>
      <h3>If someone needed this information, what would they probably search for?</h3>
      <p className="lead">Think like a coworker, not a catalog administrator. What words would they type because they know the business topic but not the exact system name?</p>
      <textarea rows="4" value={audienceNeed} onChange={e=>setAudienceNeed(e.target.value)} placeholder="e.g., corporation lookup, business registration, registered agent, filing status"/>
      <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" disabled={!audienceNeed.trim()} onClick={buildSuggestions}>Suggest search terms</button></div>
    </>}

    {step===4&&<>
      <h3>Suggested search terms</h3>
      <p className="lead">These are suggestions based on the business information you described. Keep the ones people would actually use and add any we missed.</p>
      <div className="suggested-term-grid">
        {suggestedTerms.map(t=><button type="button" key={t} className={searchTerms.toLowerCase().split(",").map(x=>x.trim()).includes(t.toLowerCase())?"term-chip selected":"term-chip"} onClick={()=>toggleTerm(t)}>{t}</button>)}
      </div>
      <label>Search terms<input value={searchTerms} onChange={e=>setSearchTerms(e.target.value)} placeholder="Comma-separated terms people would search for"/></label>
      <div className="button-row"><button onClick={()=>setStep(3)}>Back</button><button className="primary" disabled={!searchTerms.trim()} onClick={()=>setStep(5)}>Continue</button></div>
    </>}

    {step===5&&<>
      <h3>How does this information change, and who can answer questions about it?</h3>
      <p className="lead">These answers help people know whether the information is current and where to go when they need business context.</p>
      <label>How does it change?
        <select value={updatePattern} onChange={e=>setUpdatePattern(e.target.value)}>
          <option value="">Choose one</option>
          <option value="CONTINUOUS">Continuously as work occurs</option>
          <option value="DAILY">Daily</option>
          <option value="WEEKLY">Weekly</option>
          <option value="MONTHLY">Monthly</option>
          <option value="QUARTERLY">Quarterly</option>
          <option value="ANNUALLY">Annually</option>
          <option value="EVENT_DRIVEN">Only when a business event happens</option>
          <option value="UNKNOWN">I’m not sure</option>
        </select>
      </label>
      <label>If someone has a business question, who should they contact?<input value={contactPoint} onChange={e=>setContactPoint(e.target.value)} placeholder="Person, team, or business office"/></label>

      <div className="understanding-summary">
        <div><span>Business area</span><b>{businessArea}</b></div>
        <div><span>Search terms</span><b>{searchTerms||"Not entered"}</b></div>
        <div><span>How it changes</span><b>{updatePattern||"Not selected"}</b></div>
        <div><span>Contact</span><b>{contactPoint||"Not entered"}</b></div>
      </div>

      <div className="button-row"><button onClick={()=>setStep(4)}>Back</button><button className="primary" disabled={!updatePattern||!contactPoint.trim()} onClick={save}>Save this description</button></div>

      <details className="advanced-details">
        <summary>What information will AI Data Steward record?</summary>
        <p className="muted">AI Data Steward organizes these answers so the information can be understood and found across the organization. You do not need to manage the underlying fields yourself.</p>
      </details>
    </>}

    {step===6&&<>
      <div className="completion-state">
        <div className="completion-mark">✓</div>
        <div>
          <h3>Complete — others can understand and find this information more easily.</h3>
          <p>AI Data Steward recorded the business area, discovery terms, update pattern, and business contact so other people can understand and find this information.</p>
        </div>
      </div>
      <div className="button-row"><button onClick={()=>setStep(1)}>Review or update these answers</button></div>
    </>}
  </section>;
}

function GovernanceGuide({asset,gov,setGov,userEmail,doAction,guidedTask,setGuidedTask}) {
  const a=asset.asset;
  const [mode,setMode]=useState(guidedTask?.governance_domain||"");
  const [step,setStep]=useState(1);
  const [ownerDecision,setOwnerDecision]=useState(gov.business_owner||"");
  const [stewardDecision,setStewardDecision]=useState(gov.data_steward||"");
  const [publicIntent,setPublicIntent]=useState("");
  const [peopleInfo,setPeopleInfo]=useState("");
  const [restrictedRule,setRestrictedRule]=useState("");
  const [classificationRecommendation,setClassificationRecommendation]=useState("");
  const [businessActivity,setBusinessActivity]=useState("");
  const [retentionKnown,setRetentionKnown]=useState("");
  const [retentionPeriod,setRetentionPeriod]=useState(gov.retention_requirement||"");
  const [retentionAuthority,setRetentionAuthority]=useState(gov.retention_authority||"");

  useEffect(()=>{
    if(guidedTask){
      setMode(guidedTask.governance_domain||"");
      setStep(1);
    }
  },[guidedTask?.id]);

  function recommendClassification(){
    let rec="Needs Expert Review";
    if(restrictedRule==="yes" || peopleInfo==="sensitive") rec="Restricted";
    else if(peopleInfo==="basic") rec="Sensitive";
    else if(publicIntent==="yes" && peopleInfo==="none" && restrictedRule==="no") rec="Public";
    else if(publicIntent==="no" && peopleInfo==="none" && restrictedRule==="no") rec="Internal";
    setClassificationRecommendation(rec);
    setStep(4);
  }

  async function saveGovernance(patch,message){
    await doAction(
      ()=>api(`/assets/${a.asset_id}/governance`,userEmail,{method:"PATCH",body:JSON.stringify(patch)}),
      message
    );
    setGov({...gov,...patch});
    setGuidedTask(null);
    setMode("");
    setStep(1);
  }

  async function askExpert(label){
    if(!guidedTask?.id) return;
    await doAction(
      ()=>api(`/tasks/${guidedTask.id}/expert-review`,userEmail,{method:"POST"}),
      `${label} has been moved to Waiting on Others for expert review.`
    );
    setGuidedTask(null);
    setMode("");
    setStep(1);
  }

  const taskTitle=guidedTask?.title;

  if(mode==="OWNERSHIP"){
    return <section className="panel guide-panel governance-wizard">
      <div className="wizard-head"><div><div className="eyebrow">Guided task · Ownership</div><h2>{taskTitle||"Identify who is responsible"}</h2></div><span>Step {step} of 3</span></div>
      {step===1&&<>
        <h3>Who can make business decisions about this information?</h3>
        <p className="lead">Think about the business function—not necessarily the IT team—that can decide what this information means, how it should be used, and what “good” looks like.</p>
        <div className="example-box"><b>Examples</b><p>For licensing records, this might be the Licensing Division. For payroll information, it might be Human Resources or Finance.</p></div>
        <label>Business owner or business function</label>
        <input value={ownerDecision} onChange={e=>setOwnerDecision(e.target.value)} placeholder="e.g., Division of Corporations"/>
        <div className="button-row"><button className="primary" disabled={!ownerDecision.trim()} onClick={()=>setStep(2)}>Continue</button><button onClick={()=>askExpert("Ownership task")}>I’m not sure who owns this</button></div>
      </>}
      {step===2&&<>
        <h3>Who coordinates the day-to-day stewardship?</h3>
        <p className="lead">This is the person or role who keeps the information description, governance decisions, quality follow-up, and contacts current. They do not have to make every business decision themselves.</p>
        <label>Data steward</label>
        <input value={stewardDecision} onChange={e=>setStewardDecision(e.target.value)} placeholder="Person, team, or stewardship role"/>
        <div className="button-row"><button onClick={()=>setStep(1)}>Back</button><button className="primary" disabled={!stewardDecision.trim()} onClick={()=>setStep(3)}>Review recommendation</button><button onClick={()=>askExpert("Ownership task")}>I need help identifying the steward</button></div>
      </>}
      {step===3&&<>
        <h3>Here is what will be recorded</h3>
        <div className="decision-summary"><div><span>Business owner</span><b>{ownerDecision}</b></div><div><span>Data steward</span><b>{stewardDecision}</b></div></div>
        <div className="education strong"><b>Why this is enough</b><p>You supplied the business knowledge. AI Data Steward records it in the governance profile and closes the related readiness gaps.</p></div>
        <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" onClick={()=>saveGovernance({business_owner:ownerDecision,data_steward:stewardDecision},"Ownership responsibilities saved.")}>Confirm and save</button></div>
      </>}
    </section>;
  }

  if(mode==="CLASSIFICATION"){
    return <section className="panel guide-panel governance-wizard">
      <div className="wizard-head"><div><div className="eyebrow">Guided task · Classification</div><h2>{taskTitle||"Determine how this information should be handled"}</h2></div><span>Step {step} of 4</span></div>
      {step===1&&<>
        <h3>Is this information intended to be openly available to the public?</h3>
        <p className="lead">Answer based on the information itself, not whether someone could technically access the system.</p>
        <Choice value={publicIntent} setValue={setPublicIntent} options={[["yes","Yes, it is intended for public release"],["no","No, it is for internal or controlled use"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button className="primary" disabled={!publicIntent} onClick={()=>setStep(2)}>Continue</button></div>
      </>}
      {step===2&&<>
        <h3>Does it contain information about individual people?</h3>
        <p className="lead">Think about names, contact details, identifiers, financial details, health information, disciplinary information, credentials, or similar personal information.</p>
        <Choice value={peopleInfo} setValue={setPeopleInfo} options={[["none","No personal information"],["basic","Yes — ordinary identifying/contact information"],["sensitive","Yes — sensitive personal, financial, health, credential, or similarly high-risk information"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(1)}>Back</button><button className="primary" disabled={!peopleInfo} onClick={()=>setStep(3)}>Continue</button></div>
      </>}
      {step===3&&<>
        <h3>Do you know of a law, policy, contract, or security requirement that restricts access or sharing?</h3>
        <p className="lead">You do not need to know the citation. We only need to know whether you are aware of a restriction.</p>
        <Choice value={restrictedRule} setValue={setRestrictedRule} options={[["yes","Yes"],["no","No known restriction"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" disabled={!restrictedRule} onClick={recommendClassification}>Show recommendation</button></div>
      </>}
      {step===4&&<>
        <h3>Recommended classification</h3>
        <div className="recommendation-card"><span>AI Data Steward recommends</span><strong>{classificationRecommendation}</strong><p>This is a stewardship recommendation based on your answers, not a substitute for legal, privacy, records, or security review.</p></div>
        {classificationRecommendation==="Needs Expert Review"?<div className="education strong"><b>There is not enough certainty to classify this confidently.</b><p>Move the task to expert review rather than guessing. The steward can return to it when the appropriate expert responds.</p></div>:<label>Classification<select value={classificationRecommendation} onChange={e=>setClassificationRecommendation(e.target.value)}><option>Public</option><option>Internal</option><option>Sensitive</option><option>Restricted</option><option>Needs Expert Review</option></select></label>}
        <div className="button-row"><button onClick={()=>setStep(3)}>Back</button>{classificationRecommendation==="Needs Expert Review"?<button className="primary" onClick={()=>askExpert("Classification task")}>Ask for expert review</button>:<button className="primary" onClick={()=>saveGovernance({classification:classificationRecommendation},"Classification decision saved.")}>Accept and save</button>}</div>
      </>}
    </section>;
  }

  if(mode==="LIFECYCLE" || mode==="RETENTION"){
    return <section className="panel guide-panel governance-wizard">
      <div className="wizard-head"><div><div className="eyebrow">Guided task · Retention</div><h2>{taskTitle||"Determine how long this information must be kept"}</h2></div><span>Step {step} of 4</span></div>
      {step===1&&<>
        <h3>What business activity creates or uses this information?</h3>
        <p className="lead">Describe the activity in ordinary language. Records retention is usually tied to the business activity, not the database table or file format.</p>
        <textarea rows="4" value={businessActivity} onChange={e=>setBusinessActivity(e.target.value)} placeholder="e.g., Register corporations and maintain corporate filing history"/>
        <div className="button-row"><button className="primary" disabled={!businessActivity.trim()} onClick={()=>setStep(2)}>Continue</button></div>
      </>}
      {step===2&&<>
        <h3>Do you already know the approved retention requirement?</h3>
        <p className="lead">Choose the answer that best reflects what you know today. You should not invent a retention period.</p>
        <div className="choice-grid">
          <button type="button" className={retentionKnown==="yes"?"choice selected":"choice"} onClick={()=>{setRetentionKnown("yes");setStep(3)}}>Yes — I know the approved retention period and authority</button>
          <button type="button" className={retentionKnown==="no"?"choice selected":"choice"} onClick={()=>{setRetentionKnown("no");setStep(4)}}>No — I need Records Management to help determine it</button>
        </div>
        <div className="button-row"><button onClick={()=>setStep(1)}>Back</button></div>
      </>}
      {step===3&&<>
        <h3>Record the approved requirement</h3>
        <p className="lead">Use the wording from the approved records schedule or policy. Do not invent a retention period.</p>
        <label>Retention requirement<input value={retentionPeriod} onChange={e=>setRetentionPeriod(e.target.value)} placeholder="e.g., 5 years after closure"/></label>
        <label>Retention authority<input value={retentionAuthority} onChange={e=>setRetentionAuthority(e.target.value)} placeholder="Records schedule, item number, or policy source"/></label>
        <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" disabled={!retentionPeriod.trim()||!retentionAuthority.trim()} onClick={()=>saveGovernance({retention_requirement:retentionPeriod,retention_authority:retentionAuthority},"Retention requirement saved.")}>Confirm and save</button></div>
      </>}
      {step===4&&<>
        <h3>Records Management should help determine the retention requirement</h3>
        <p className="lead">That is a valid stewardship outcome. You should not guess at a retention period when the approved requirement is unknown.</p>
        <div className="referral-card">
          <div><span>Information asset</span><b>{a.name||"Current information asset"}</b></div>
          <div><span>Business activity</span><b>{businessActivity}</b></div>
          <div><span>Question for Records Management</span><b>What approved retention requirement and authority apply to this information?</b></div>
        </div>
        <div className="education strong"><b>What happens next?</b><p>The retention task will move to <b>Waiting on Others</b> for expert review. You can continue with other stewardship work while Records Management helps determine the answer.</p></div>
        <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" onClick={()=>askExpert("Retention task")}>Send to Records Management</button></div>
      </>}
    </section>;
  }

  return <section className="panel">
    <div className="eyebrow">Governance</div><h2>What do you need to work on?</h2>
    <p className="lead">Choose a guided task. AI Data Steward will ask plain-language questions and translate your answers into the governance profile.</p>
    <div className="guide-launch-grid">
      <button onClick={()=>{setMode("OWNERSHIP");setStep(1)}}><b>Ownership</b><span>Who makes business decisions and who maintains stewardship?</span></button>
      <button onClick={()=>{setMode("CLASSIFICATION");setStep(1)}}><b>Classification</b><span>How should this information be handled and protected?</span></button>
      <button onClick={()=>{setMode("LIFECYCLE");setStep(1)}}><b>Retention</b><span>How long should it be kept, and under what authority?</span></button>
    </div>
    <details className="advanced-details"><summary>Advanced governance details</summary><p className="muted">Experienced users can edit the profile directly. New stewards should normally use the guided tasks above.</p><div className="form-grid"><label>Business owner<input value={gov.business_owner||""} onChange={e=>setGov({...gov,business_owner:e.target.value})}/></label><label>Data steward<input value={gov.data_steward||""} onChange={e=>setGov({...gov,data_steward:e.target.value})}/></label><label>Classification<select value={gov.classification||""} onChange={e=>setGov({...gov,classification:e.target.value})}><option value="">Needs review</option><option>Public</option><option>Internal</option><option>Sensitive</option><option>Restricted</option><option>Needs Expert Review</option></select></label><label>Retention requirement<input value={gov.retention_requirement||""} onChange={e=>setGov({...gov,retention_requirement:e.target.value})}/></label><label className="wide">Retention authority<input value={gov.retention_authority||""} onChange={e=>setGov({...gov,retention_authority:e.target.value})}/></label></div><button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset_id}/governance`,userEmail,{method:"PATCH",body:JSON.stringify(gov)}),"Governance information saved.")}>Save advanced details</button></details>
  </section>;
}

function Choice({value,setValue,options}) {
  return <div className="choice-grid">{options.map(([v,label])=><button type="button" key={v} className={value===v?"choice selected":"choice"} onClick={()=>setValue(v)}>{label}</button>)}</div>;
}

function QualityPanel({quality,asset,userEmail,doAction,selectedQualityIssueId,setSelectedQualityIssueId}) {
  const q=quality?.profiles?.[0];
  const structured=asset.resources.filter(r=>r.structure_type==="STRUCTURED");
  const [resourceId,setResourceId]=useState(structured[0]?.resource_id||"");
  const [projectCode,setProjectCode]=useState("");
  const [tableGroupId,setTableGroupId]=useState("");
  const [testSuiteId,setTestSuiteId]=useState("");
  const [sourceConnectionName,setSourceConnectionName]=useState("");
  const [sourceDatabase,setSourceDatabase]=useState("");
  const [sourceSchema,setSourceSchema]=useState("");
  const [sourceTable,setSourceTable]=useState("");
  const [decisionIssue,setDecisionIssue]=useState(null);
  const [hygieneIssue,setHygieneIssue]=useState(null);
  const [selectedHygieneFinding,setSelectedHygieneFinding]=useState(null);
  const [notes,setNotes]=useState("");
  const [engineStatus,setEngineStatus]=useState(null);
  const link=quality?.links?.find(x=>x.resource_id===Number(resourceId));
  useEffect(()=>{api("/quality/engine/status",userEmail).then(setEngineStatus).catch(()=>setEngineStatus(null));},[userEmail]);

  useEffect(()=>{
    if(!resourceId) return;
    const selectedResource=structured.find(r=>r.resource_id===Number(resourceId));
    const current=quality?.links?.find(x=>x.resource_id===Number(resourceId));
    const source=current?.source_mapping||{};
    setProjectCode(current?.project_code||engineStatus?.project_code||"");
    setTableGroupId(current?.table_group_id||engineStatus?.table_group_id||"");
    setTestSuiteId(current?.test_suite_id||engineStatus?.test_suite_id||"");
    setSourceConnectionName(source.connection_name||"");
    setSourceDatabase(source.database||"");
    setSourceSchema(source.schema||"public");
    setSourceTable(source.table||current?.external_table_name?.split(".").pop()||selectedResource?.name||"");
  },[resourceId,quality?.links,engineStatus]);

  const openIssues=(quality?.issues||[]).filter(i=>i.status!=="RESOLVED");

  useEffect(()=>{
    if(!selectedQualityIssueId || !quality?.issues?.length) return;
    const issue=quality.issues.find(i=>i.id===Number(selectedQualityIssueId));
    if(!issue) return;

    setNotes("");
    if(issue.issue_type==="HYGIENE_FINDING"){
      setHygieneIssue(issue);
      setDecisionIssue(null);
      setSelectedHygieneFinding(null);
      window.setTimeout(()=>{
        document.getElementById("profiling-workbench")?.scrollIntoView({behavior:"smooth",block:"start"});
      },100);
    }else{
      setDecisionIssue(issue);
      setHygieneIssue(null);
      window.setTimeout(()=>{
        document.getElementById("guided-investigation")?.scrollIntoView({behavior:"smooth",block:"start"});
      },100);
    }
  },[selectedQualityIssueId,quality?.issues]);

  async function refreshAction(fn,msg){ await doAction(fn,msg); }

  return <>
    <section className="panel quality-trust-first">
      <div className="eyebrow">Trust & quality</div>
      <h2>Can this information be trusted for its intended use?</h2>
      <p className="lead">AI Data Steward checks the available evidence and turns technical findings into decisions a steward can work through. You do not need to understand the quality engine to use this page.</p>

      <div className="trust-summary-grid">
        <div>
          <span>Current quality</span>
          <strong>{q?.overall_score!=null?`${q.overall_score}%`:"Not assessed"}</strong>
          <small>{q?.profiled_at?`Last assessed ${new Date(q.profiled_at).toLocaleDateString()}`:"Run a check when you are ready."}</small>
        </div>
        <div>
          <span>Needs review</span>
          <strong>{openIssues.length}</strong>
          <small>{openIssues.length===0?"No unresolved findings.":"Open findings need a stewardship decision."}</small>
        </div>
        <div>
          <span>Source status</span>
          <strong>{link?.sync_status==="CONFIGURED"?"Ready":link?.sync_status||"Not configured"}</strong>
          <small>{link?.source_mapping?.qualified_name||link?.external_table_name||"A technical source can be connected when needed."}</small>
        </div>
      </div>

      <div className="button-row trust-actions">
        <button className="primary" disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/assess`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Information check completed. Review any findings that need a stewardship decision.")}>Check this information</button>
        <button disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/run`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Approved quality checks ran. Any findings that need attention were added to stewardship work.")}>Run approved checks</button>
      </div>

      {structured.length===0&&<div className="education strong"><b>Automated checking is not available for this type of information.</b><p>Documents and document libraries are still covered by description, classification, retention, ownership, and other stewardship work.</p></div>}

      {structured.length>1&&<details className="advanced-details">
        <summary>Choose which structured location to check</summary>
        <label>Location to check
          <select value={resourceId} onChange={e=>setResourceId(e.target.value)}>{structured.map(r=><option key={r.resource_id} value={r.resource_id}>{r.name} · {r.system||"No system"}</option>)}</select>
        </label>
      </details>}

      {quality?.engine_mode==="real"&&<details className="config-box technical-setup">
        <summary>Technical setup</summary>
        <p className="muted">This section is intended for technical or administrative users. It connects the governed information location to the quality engine. Stewards normally do not need to change these settings.</p>

        <div className="technical-status-line">
          <div><span>Quality engine</span><b>DataKitchen TestGen</b></div>
          <div><span>Connection</span><b>{engineStatus?.auth_mode||"Not loaded"}</b></div>
          <div><span>Mapping</span><b>{link?.sync_status||"Not linked"}</b></div>
        </div>

        {resourceId&&<div className="quality-context">
          <div><span>Information</span><b>{asset.asset.name}</b></div>
          <div><span>Location</span><b>{structured.find(r=>r.resource_id===Number(resourceId))?.name||"—"}</b></div>
          <div><span>Technical source</span><b>{link?.source_mapping?.qualified_name||link?.external_table_name||"Not mapped"}</b></div>
        </div>}

        <label>Structured location to configure</label>
        <select value={resourceId} onChange={e=>setResourceId(e.target.value)}>{structured.map(r=><option key={r.resource_id} value={r.resource_id}>{r.name} · {r.system||"No system"}</option>)}</select>

        <div className="mapping-section">
          <div className="eyebrow">Source identity</div>
          <div className="mapping-grid">
            <label>TestGen connection name<input value={sourceConnectionName} onChange={e=>setSourceConnectionName(e.target.value)} placeholder="e.g. Data_Lab"/></label>
            <label>Database<input value={sourceDatabase} onChange={e=>setSourceDatabase(e.target.value)} placeholder="e.g. corporate_registry"/></label>
            <label>Schema<input value={sourceSchema} onChange={e=>setSourceSchema(e.target.value)} placeholder="public"/></label>
            <label>Table<input value={sourceTable} onChange={e=>setSourceTable(e.target.value)} placeholder="corporate_data"/></label>
          </div>
        </div>

        <div className="mapping-section">
          <div className="eyebrow">TestGen execution mapping</div>
          <div className="mapping-grid">
            <label>Project code<input value={projectCode} onChange={e=>setProjectCode(e.target.value)} placeholder={engineStatus?.project_code||"DEFAULT"}/></label>
            <label>Table group ID<input value={tableGroupId} onChange={e=>setTableGroupId(e.target.value)} placeholder={engineStatus?.table_group_id||"TestGen table-group UUID"}/></label>
            <label>Test suite ID<input value={testSuiteId} onChange={e=>setTestSuiteId(e.target.value)} placeholder={engineStatus?.test_suite_id||"TestGen test-suite UUID"}/></label>
          </div>
          {(link?.source_mapping?.qualified_name||link?.external_table_name)&&<div className="source-summary"><b>Currently mapped source</b><span>{[link?.source_mapping?.connection_name,link?.source_mapping?.database,link?.source_mapping?.qualified_name||link?.external_table_name].filter(Boolean).join(" → ")}</span></div>}
        </div>

        <div className="button-row">
          <button onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/link`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId),project_code:projectCode||engineStatus?.project_code,table_group_id:tableGroupId||engineStatus?.table_group_id,test_suite_id:testSuiteId||engineStatus?.test_suite_id,source_connection_name:sourceConnectionName,source_database:sourceDatabase,source_schema:sourceSchema,source_table:sourceTable,external_table_name:sourceTable?`${sourceSchema?`${sourceSchema}.`:""}${sourceTable}`:structured.find(r=>r.resource_id===Number(resourceId))?.name})}),"Technical source mapping saved.")}>Save technical setup</button>
          <button onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/test-connection`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Quality engine connection succeeded.")}>Test connection</button>
        </div>
      </details>}

      {quality?.engine_mode!=="real"&&<details className="advanced-details">
        <summary>Technical setup</summary>
        <p className="muted">This demo is using the built-in quality simulator. Technical quality-engine configuration is not required.</p>
      </details>}
    </section>

    <section className="panel">
      <div className="eyebrow">Evidence summary</div><h2>What the latest check tells us</h2>
      {q?<><div className="quality-score"><strong>{q.overall_score}%</strong><span>Overall information quality</span></div><div className="quality-grid"><Metric label="Completeness" value={q.completeness_score!=null?`${q.completeness_score}%`:"—"}/><Metric label="Validity" value={q.validity_score!=null?`${q.validity_score}%`:"—"}/><Metric label="Uniqueness" value={q.uniqueness_score!=null?`${q.uniqueness_score}%`:"—"}/><Metric label="Consistency" value={q.consistency_score!=null?`${q.consistency_score}%`:"—"}/><Metric label="Timeliness" value={q.timeliness_score!=null?`${q.timeliness_score}%`:"—"}/></div></>:<p>No quality assessment has been recorded.</p>}
    </section>

    <section className="panel"><h2>What should this information reliably do?</h2><p className="muted">These expectations describe what the business needs to be true about the information. AI Data Steward turns failed checks into guided stewardship work rather than treating them as automatic errors.</p>{quality?.rules?.length?quality.rules.map(r=><div className="rule" key={r.id}><div><b>{r.plain_language_rule}</b><span>{friendlyType(r.rule_type)} · {r.status}</span>{r.latest_result&&<small>{r.latest_result.failed_count||0} failed in the latest run</small>}</div><div className="button-row mini">{r.status==="PROPOSED"&&<><button className="primary" onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"APPROVED"})}),"Quality expectation approved.")}>Approve</button><button onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"REJECTED"})}),"Quality expectation rejected.")}>Reject</button></>}</div></div>):<p>Check this information to identify suggested expectations.</p>}</section>

    <section className="panel"><h2>Findings that need a stewardship decision</h2><p className="muted">A finding means something is worth reviewing. It does not automatically mean the information is wrong. Use the evidence and business context to decide what it means.</p>{openIssues.length===0&&<EmptyState title="No findings need a decision." text="New findings will appear here after future checks when they need stewardship review."/>}{openIssues.map(i=>{const evidence=i.details?.evidence||{};const samples=evidence.sample_values?.length?evidence.sample_values:i.details?.sample_values;const isProfile=i.issue_type==="HYGIENE_FINDING";const summary=i.details?.finding_summary||{};return <div className={`quality-issue severity-${i.severity.toLowerCase()}`} key={i.id}><div className="task-head"><div><div className="eyebrow">{i.source} · {isProfile?"PROFILING FINDING":"QUALITY CHECK FAILURE"}</div><h3>{i.title}</h3></div><span className="priority">{i.severity}</span></div><p>{i.description}</p>{isProfile&&<><div className="finding-summary-grid"><Metric label="Needs review" value={summary.pending??i.details?.finding_count??0}/><Metric label="Reviewed" value={summary.resolved??0}/><Metric label="Expert review" value={summary.escalated??0}/><Metric label="Potential PII" value={i.details?.potential_pii_count||0}/></div><p className="muted">You do not need to understand the quality engine’s terminology. AI Data Steward translates each finding into what it means, why it matters, and what to do next.</p></>}{!isProfile&&<div className="evidence-grid">{evidence.status&&<Metric label="Result" value={evidence.status}/>} {evidence.test_type&&<Metric label="Check type" value={friendlyType(evidence.test_type)}/>} {evidence.evaluated_count!=null&&<Metric label="Records evaluated" value={Number(evidence.evaluated_count).toLocaleString()}/>} {i.failed_count!=null&&<Metric label="Records affected" value={i.failed_count.toLocaleString()}/>} {evidence.score!=null&&<Metric label="Check score" value={`${evidence.score}%`}/>}</div>}{evidence.columns?.length>0&&<p><b>Fields:</b> {evidence.columns.join(", ")}</p>}{samples?.length>0&&<div className="sample-values"><b>Example evidence</b><span>{samples.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<button className="primary" onClick={()=>{setSelectedQualityIssueId(i.id);setNotes("");if(isProfile){setHygieneIssue(i);setDecisionIssue(null);setSelectedHygieneFinding(null);window.setTimeout(()=>document.getElementById("profiling-workbench")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}else{setDecisionIssue(i);setHygieneIssue(null);window.setTimeout(()=>document.getElementById("guided-investigation")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}}}>{isProfile?"Review findings":"Guide Me"}</button></div>})}</section>

    {hygieneIssue&&<section id="profiling-workbench" className="panel guide-panel"><div className="eyebrow">Profiling findings workbench</div><h2>Review findings one at a time</h2><div className="next-step-callout"><b>What to do next</b><span>Start with the first item marked <strong>Needs review</strong>. Read what TestGen found, check why it matters, then choose the stewardship decision that best matches the business reality. Work through the list one finding at a time.</span></div><p className="muted">The quality check found patterns in the information. These are observations, not automatic errors.</p><div className="finding-progress"><b>{hygieneIssue.details?.finding_summary?.pending??0} need review</b><span>{hygieneIssue.details?.finding_summary?.resolved??0} reviewed · {hygieneIssue.details?.finding_summary?.escalated??0} sent for expert review</span></div><div className="finding-list">{(hygieneIssue.details?.steward_findings||[]).map(f=><div key={f.fingerprint} className={`steward-finding status-${(f.review_status||"PENDING").toLowerCase()}`}><div className="task-head"><div><div className="eyebrow">{f.column} · {friendlyType(f.category)}</div><h3>{f.title}</h3></div><span className="finding-status">{f.review_status==="RESOLVED"?"Reviewed":f.review_status==="ESCALATED"?"Expert review":"Needs review"}</span></div><p><b>Why it matters</b><br/>{f.why_it_matters}</p><p><b>Recommended next step</b><br/>{f.recommended_action}</p>{f.affected_count!=null&&<p><b>{Number(f.affected_count).toLocaleString()}</b> affected records</p>}{f.examples?.length>0&&<div className="sample-values"><b>Example evidence</b><span>{f.examples.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<details className="technical-detail"><summary>Technical finding details</summary><code>{f.testgen_finding}</code></details><button className={f.review_status==="PENDING"?"primary":""} onClick={()=>{setSelectedHygieneFinding(f);setNotes(f.notes||"");window.setTimeout(()=>document.getElementById("finding-decision")?.scrollIntoView({behavior:"smooth",block:"center"}),100)}}>{f.review_status==="PENDING"?"Review this finding":"Review decision"}</button></div>)}</div></section>}
    {hygieneIssue&&selectedHygieneFinding&&<section id="finding-decision" className="panel guide-panel finding-decision"><div className="eyebrow">Guided finding review</div><h2>{selectedHygieneFinding.title}</h2><div className="finding-decision-context"><div><span>Field</span><b>{selectedHygieneFinding.column||"—"}</b></div><div><span>Category</span><b>{friendlyType(selectedHygieneFinding.category||"PROFILE")}</b></div><div><span>Status</span><b>{selectedHygieneFinding.review_status==="RESOLVED"?"Reviewed":selectedHygieneFinding.review_status==="ESCALATED"?"Expert review":"Needs review"}</b></div>{selectedHygieneFinding.affected_count!=null&&<div><span>Affected records</span><b>{Number(selectedHygieneFinding.affected_count).toLocaleString()}</b></div>}{selectedHygieneFinding.confidence&&<div><span>TestGen confidence</span><b>{selectedHygieneFinding.confidence}</b></div>}</div><div className="finding-decision-detail"><div><b>What TestGen found</b><p>{selectedHygieneFinding.testgen_finding||"Profiling observation"}</p></div><div className="evidence-panel"><div className="evidence-panel-head"><div><b>Evidence available for this decision</b><p className="muted">Review the evidence before choosing a stewardship decision.</p></div><span className={`evidence-level evidence-${(selectedHygieneFinding.evidence?.sufficiency?.level||"LOW").toLowerCase()}`}>{selectedHygieneFinding.evidence?.sufficiency?.level||"LOW"} evidence</span></div>{selectedHygieneFinding.evidence?.testgen?.observed_values?.length>0&&<div className="evidence-block"><b>Observed value{selectedHygieneFinding.evidence.testgen.observed_values.length===1?"":"s"}</b><div className="evidence-values">{selectedHygieneFinding.evidence.testgen.observed_values.map((v,idx)=><code key={idx}>{v===null?"(missing)":String(v)}</code>)}</div></div>}{selectedHygieneFinding.evidence?.testgen?.detail&&<div className="evidence-block"><b>TestGen evidence</b><p>{selectedHygieneFinding.evidence.testgen.detail}</p>{selectedHygieneFinding.evidence.testgen.records_profiled!=null&&<p><b>{Number(selectedHygieneFinding.evidence.testgen.records_profiled).toLocaleString()}</b> records were profiled.</p>}</div>}{selectedHygieneFinding.evidence?.testgen?.affected_count!=null&&<div className="evidence-block"><b>Estimated impact</b><p><b>{Number(selectedHygieneFinding.evidence.testgen.affected_count).toLocaleString()}</b> records match this finding{selectedHygieneFinding.evidence.testgen.affected_percent!=null?` (${selectedHygieneFinding.evidence.testgen.affected_percent}%)`:""}.</p></div>}{selectedHygieneFinding.evidence?.testgen?.patterns?.length>0&&<div className="evidence-block"><b>Observed format distribution</b><div className="pattern-list">{selectedHygieneFinding.evidence.testgen.patterns.map((p,idx)=><span key={idx}><code>{p.pattern}</code><b>{Number(p.count).toLocaleString()}</b></span>)}</div></div>}{selectedHygieneFinding.evidence?.testgen?.semantic_type&&<div className="evidence-block"><b>Detected semantic type</b><p>{selectedHygieneFinding.evidence.testgen.semantic_type}</p></div>}{selectedHygieneFinding.evidence?.testgen?.minimum_value&&<div className="evidence-block"><b>Minimum observed value</b><p><code>{selectedHygieneFinding.evidence.testgen.minimum_value}</code></p></div>}{selectedHygieneFinding.evidence?.testgen?.affected_count!=null&&<div className="evidence-block"><b>How common is it?</b><p>{Number(selectedHygieneFinding.evidence.testgen.affected_count).toLocaleString()} affected record{Number(selectedHygieneFinding.evidence.testgen.affected_count)===1?"":"s"}{selectedHygieneFinding.evidence?.profile_context?.row_count?` out of ${Number(selectedHygieneFinding.evidence.profile_context.row_count).toLocaleString()} profiled records`:""}.</p></div>}{Object.keys(selectedHygieneFinding.evidence?.profile_context||{}).length>0&&<div className="evidence-block"><b>Profile context for {selectedHygieneFinding.column}</b><div className="profile-context-grid">{selectedHygieneFinding.evidence.profile_context.data_type&&<Metric label="Data type" value={selectedHygieneFinding.evidence.profile_context.data_type}/>} {selectedHygieneFinding.evidence.profile_context.semantic_type&&<Metric label="Detected meaning" value={selectedHygieneFinding.evidence.profile_context.semantic_type}/>} {selectedHygieneFinding.evidence.profile_context.row_count!=null&&<Metric label="Rows profiled" value={Number(selectedHygieneFinding.evidence.profile_context.row_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.distinct_count!=null&&<Metric label="Distinct values" value={Number(selectedHygieneFinding.evidence.profile_context.distinct_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.null_count!=null&&<Metric label="Missing values" value={Number(selectedHygieneFinding.evidence.profile_context.null_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.null_percent!=null&&<Metric label="Missing %" value={`${selectedHygieneFinding.evidence.profile_context.null_percent}%`}/>} {selectedHygieneFinding.evidence.profile_context.min_length!=null&&<Metric label="Shortest length" value={selectedHygieneFinding.evidence.profile_context.min_length}/>} {selectedHygieneFinding.evidence.profile_context.max_length!=null&&<Metric label="Longest length" value={selectedHygieneFinding.evidence.profile_context.max_length}/>} {selectedHygieneFinding.evidence.profile_context.avg_length!=null&&<Metric label="Typical length" value={selectedHygieneFinding.evidence.profile_context.avg_length}/>}</div>{selectedHygieneFinding.evidence.profile_context.typical_values?.length>0&&<div className="typical-values"><b>Typical / common values</b>{selectedHygieneFinding.evidence.profile_context.typical_values.map((item,idx)=><span key={idx}><code>{String(item.value)}</code>{item.count!=null&&` · ${Number(item.count).toLocaleString()} records`}</span>)}</div>}</div>}<div className="evidence-block source-evidence"><b>Source-record verification</b><p>{selectedHygieneFinding.evidence?.source_record_context?.message||"Open the source system or ask the data owner to verify the underlying record when the profile evidence is not enough."}</p></div><div className={`evidence-guidance evidence-${(selectedHygieneFinding.evidence?.sufficiency?.level||"LOW").toLowerCase()}`}><b>{selectedHygieneFinding.evidence?.sufficiency?.level==="LOW"?"More evidence is needed before making a confident decision":"Evidence guidance"}</b><p>{selectedHygieneFinding.evidence?.sufficiency?.guidance||"Verify the source record or consult a business expert before deciding."}</p>{selectedHygieneFinding.evidence?.sufficiency?.limitations?.length>0&&<ul>{selectedHygieneFinding.evidence.sufficiency.limitations.map((x,idx)=><li key={idx}>{x}</li>)}</ul>}</div></div><div><b>Why it matters</b><p>{selectedHygieneFinding.why_it_matters}</p></div><div><b>Recommended next step</b><p>{selectedHygieneFinding.recommended_action}</p></div></div><p><b>What should you decide?</b> Pick the option that best matches the business reality. If the evidence is limited, verify the source or use expert review rather than guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","This data needs correction"],["VALID_EXCEPTION","This is acceptable as-is"],["EXPECTATION_NEEDS_CHANGE","Create or adjust a quality expectation"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${hygieneIssue.id}/findings/${encodeURIComponent(selectedHygieneFinding.fingerprint)}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Finding decision recorded: ${label}.`).then(()=>{setSelectedHygieneFinding(null);setNotes("");})}>{label}</button>)}</div></section>}
    {decisionIssue&&<section id="guided-investigation" className="panel guide-panel"><div className="eyebrow">Guided investigation</div><h2>{decisionIssue.title}</h2><p><b>Step 1 — Understand what TestGen found.</b> {decisionIssue.issue_type==="HYGIENE_FINDING"?"A profiling finding highlights a characteristic or pattern that deserves review; it is not a failed rule by itself.":"A quality check did not pass. Review the affected records, fields, and evidence before deciding why."}</p><p><b>Step 2 — Make a stewardship decision.</b> Choose the explanation that best matches what you know. If you cannot determine it, escalate instead of guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","The data is incorrect"],["VALID_EXCEPTION","This is a valid exception"],["EXPECTATION_NEEDS_CHANGE","The quality expectation needs to change"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${decisionIssue.id}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Decision recorded: ${label}.`).then(()=>{setDecisionIssue(null);setSelectedQualityIssueId(null)})}>{label}</button>)}</div></section>}
  </>;
}

function PublicationPanel({asset,role,userEmail,doAction}) {
  const required=asset.readiness.checks.filter(c=>c.required);
  const missing=required.filter(c=>!c.complete);
  const ready=missing.length===0;
  const status=asset.publication.status;

  const canSubmit=["STEWARD","ORG_ADMIN"].includes(role);
  const canReview=["APPROVER","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const canPublish=["APPROVER","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);

  const roleName={
    STEWARD:"Steward",
    APPROVER:"Approver",
    ORG_ADMIN:"Organization administrator",
    ENTERPRISE_ADMIN:"Enterprise administrator",
    VIEWER:"Viewer"
  }[role]||"User";

  function roleGuidance(){
    if(status==="IN_REVIEW"){
      if(canReview) return "This information is waiting for your review. You can approve it or return it for changes.";
      return "Your submission is waiting for an approver. You can continue other stewardship work while the review is in progress.";
    }
    if(status==="APPROVED"){
      if(canPublish) return "The review is complete and an approved release exists. You can publish it when the organization is ready.";
      return "This information has been approved. Publishing is handled by an authorized reviewer or administrator.";
    }
    if(status==="PUBLISHED"){
      return "This information has been published. If stewardship information changes later, AI Data Steward will identify what needs to be reviewed again.";
    }
    if(status==="REJECTED"){
      if(canSubmit) return "The reviewer returned this information for changes. Address the requested work, then submit it again.";
      return "This information was returned for changes and is waiting for the steward to update it.";
    }
    if(status==="NEEDS_UPDATE"){
      if(canSubmit) return "Something changed after publication. Complete the required stewardship updates, then submit the revised information for review.";
      return "Published information has changed and needs steward updates before a new review.";
    }
    if(canSubmit){
      return ready
        ? "Your required stewardship work is complete. Your responsibility is to submit it for review—not to approve or publish it yourself."
        : "Finish the required stewardship work below. When it is complete, you will be able to submit it for review.";
    }
    if(canReview){
      return "There is nothing for you to approve yet. The steward must complete the required work and submit it first.";
    }
    return "You can view publication readiness, but you do not have an action to take at this stage.";
  }

  return <section className="panel role-aware-publication">
    <div className="task-head">
      <div>
        <div className="eyebrow">Share & publish</div>
        <h2>{ready?"Required stewardship checks are complete":"There are still things to finish before review"}</h2>
        <p className="lead">{roleGuidance()}</p>
      </div>
      <div className="role-responsibility"><span>Your role</span><b>{roleName}</b></div>
    </div>

    <div className={`publication-readiness ${ready?"ready":"not-ready"}`}>
      <strong>{required.length-missing.length} of {required.length}</strong>
      <span>required stewardship checks complete</span>
    </div>

    {required.map(c=><div className="readiness-row" key={c.key}>
      <span className={c.complete?"ok":"warn"}>{c.complete?"✓":"!"}</span>
      <div><b>{c.title}</b><small>{c.complete?"Complete":c.guidance}</small></div>
    </div>)}

    <div className="publication-role-path">
      <div className={["DRAFT","NEEDS_UPDATE","REJECTED"].includes(status)?"current":status!=="DRAFT"?"done":""}>
        <span>1</span><div><b>Prepare</b><small>Steward completes required work</small></div>
      </div>
      <div className={status==="IN_REVIEW"?"current":["APPROVED","PUBLISHED"].includes(status)?"done":""}>
        <span>2</span><div><b>Review</b><small>Approver reviews the submission</small></div>
      </div>
      <div className={status==="APPROVED"?"current":status==="PUBLISHED"?"done":""}>
        <span>3</span><div><b>Approved</b><small>Governed release is created</small></div>
      </div>
      <div className={status==="PUBLISHED"?"current":""}>
        <span>4</span><div><b>Published</b><small>Approved release is shared</small></div>
      </div>
    </div>

    <div className="role-action-card">
      {canSubmit&&["DRAFT","NEEDS_UPDATE","REJECTED"].includes(status)&&<>
        <div><b>Your next action</b><p>{ready?"Send this information to an approver. Submission does not publish it.":"Complete the required stewardship checks before sending this for review."}</p></div>
        <button className="primary" disabled={!ready} onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/submit`,userEmail,{method:"POST",body:JSON.stringify({comments:"Stewardship checks complete; ready for review."})}),"Submitted for review.")}>Submit for review</button>
      </>}

      {!canReview&&status==="IN_REVIEW"&&<div className="waiting-publication"><span className="waiting-pill">Waiting</span><div><b>Waiting for an approver</b><p>No publication action is required from you right now.</p></div></div>}

      {canReview&&status==="IN_REVIEW"&&<>
        <div><b>Your review decision</b><p>Confirm that the required stewardship information is suitable for an approved release, or return it to the steward with changes needed.</p></div>
        <div className="button-row">
          <button onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/reject`,userEmail,{method:"POST",body:JSON.stringify({comments:"Please address the requested stewardship changes and resubmit."})}),"Returned to the steward for changes.")}>Return for changes</button>
          <button className="primary" onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/approve`,userEmail,{method:"POST",body:JSON.stringify({comments:"Approved."})}),"Approved and governed release created.")}>Approve</button>
        </div>
      </>}

      {!canPublish&&status==="APPROVED"&&<div className="waiting-publication"><span className="waiting-pill">Approved</span><div><b>Review is complete</b><p>An authorized reviewer or administrator will handle publication.</p></div></div>}

      {canPublish&&status==="APPROVED"&&<>
        <div><b>Ready to publish</b><p>An approved governed release already exists. Publishing shares that approved release through the configured organization catalog connection.</p></div>
        <button className="primary" onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published.")}>Publish approved release</button>
      </>}

      {status==="PUBLISHED"&&<div className="waiting-publication published-state"><span className="completion-mark">✓</span><div><b>Published</b><p>This approved release is published. Stewardship continues if the information changes later.</p></div></div>}

      {!canSubmit&&!canReview&&!["IN_REVIEW","APPROVED","PUBLISHED"].includes(status)&&<div className="waiting-publication"><div><b>No action for your role</b><p>You can review the readiness status, but another role is responsible for the next publication step.</p></div></div>}
    </div>

    <details className="advanced-details publication-explainer">
      <summary>How the approval and publication process works</summary>
      <p><b>Submit for review</b> sends the current governed information to an approver. <b>Approve</b> creates an immutable governed release. <b>Publish</b> shares that approved release through the configured publication connection.</p>
    </details>
  </section>;
}

function ReviewQueue({assets,role,userEmail,doAction,onOpen}) {
  const canReview=["APPROVER","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const canPublish=["APPROVER","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const review=assets.filter(a=>["IN_REVIEW","APPROVED","NEEDS_UPDATE"].includes(a.publication.status));

  return <>
    <h1>Review Queue</h1>
    <p className="lead">Work submitted by stewards appears here for review. The actions shown are limited to what your current role is authorized to do.</p>

    {!canReview&&<div className="education strong"><b>This queue is read-only for your role.</b><p>An Approver or administrator is responsible for approval and publication decisions.</p></div>}
    {review.length===0&&<EmptyState title="Nothing is waiting for review or publication." text="Submitted or approved items will appear here when your role has work to do."/>}

    {review.map(a=><div className="review-row role-review-row" key={a.asset.asset_id}>
      <div>
        <b>{a.asset.name}</b>
        <span>{a.readiness.score}% stewardship completeness · {a.quality?.overall_score??"—"}% information quality</span>
      </div>
      <Status value={a.publication.status}/>
      <div className="button-row">
        <button onClick={()=>onOpen(a.asset.asset_id)}>View details</button>

        {canReview&&a.publication.status==="IN_REVIEW"&&<>
          <button onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/reject`,userEmail,{method:"POST",body:JSON.stringify({comments:"Please address the requested stewardship changes and resubmit."})}),"Returned to the steward for changes.")}>Return for changes</button>
          <button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/approve`,userEmail,{method:"POST",body:JSON.stringify({comments:"Approved."})}),"Approved and governed release created.")}>Approve</button>
        </>}

        {canPublish&&a.publication.status==="APPROVED"&&<button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published.")}>Publish approved release</button>}

        {a.publication.status==="NEEDS_UPDATE"&&<span className="review-state-note">Waiting for steward updates</span>}
      </div>
    </div>)}
  </>;
}

function PublicationHistory({assets,selectedAssetId,setSelectedAssetId,userEmail}) { const [history,setHistory]=useState(null); useEffect(()=>{if(selectedAssetId)api(`/assets/${selectedAssetId}/history`,userEmail).then(setHistory)},[selectedAssetId,userEmail]); return <><h1>Publishing History</h1><p className="lead">Review the approval and publication history for governed information. Technical release details remain available inside each release record.</p><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select><div className="two-col"><section className="panel"><h2>Audit timeline</h2>{history?.events?.length?history.events.map(e=><div className="timeline" key={e.id}><b>{e.event_type.replaceAll("_"," ")}</b><span>{e.from_status||"—"} → {e.to_status||"—"}</span><small>{e.created_at}</small></div>):<EmptyState title="No publication events yet." text="Submission, approval, return, and publishing activity will appear here."/>}</section><section className="panel"><h2>Immutable releases</h2>{history?.releases?.length?history.releases.map(r=><details key={r.id}><summary>Release v{r.version_number} {r.published_at?"· Published":"· Approved"}</summary><p><b>Snapshot hash:</b> {r.snapshot_hash}</p>{r.ckan_name&&<p><b>Catalog name:</b> {r.ckan_name}</p>}{r.publication_result?.dcat_payload&&<><p><b>Technical publication payload (DCAT JSON-LD)</b></p><pre>{JSON.stringify(r.publication_result.dcat_payload,null,2)}</pre></>}</details>):<EmptyState title="No approved releases yet." text="Approved release history will appear here after the first approval."/>}</section></div></> }

function Metric({label,value}) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }
function Status({value}) { return <span className={`status status-${(value||"").toLowerCase()}`}>{(value||"").replaceAll("_"," ")}</span> }
function friendlyType(value){return (value||"").replaceAll("_"," ").toLowerCase().replace(/\b\w/g,m=>m.toUpperCase())}
function priorityLabel(value){
  return {HIGH:"Do this soon",MEDIUM:"Needs attention",LOW:"When you can"}[value]||friendlyType(value);
}
function responsibilityLabel(task){
  if(task?.responsibility) return task.responsibility;
  const domain=(task?.governance_domain||"").toUpperCase();
  return {
    OWNERSHIP:"Know who is responsible",
    CLASSIFICATION:"Protect it appropriately",
    LIFECYCLE:"Keep it for the right amount of time",
    RETENTION:"Keep it for the right amount of time",
    QUALITY:"Make sure it can be trusted",
    METADATA:"Help others understand it",
    DESCRIPTION:"Help others understand it",
    CATALOG:"Know where it lives",
    GOVERNANCE:"Make the right stewardship decision",
    MAINTENANCE:"Keep it current"
  }[domain]||"Stewardship";
}
function EmptyState({title="Nothing needs attention right now.",text=null}){
  return <div className="empty empty-state"><b>{title}</b>{text&&<span>{text}</span>}</div>;
}

createRoot(document.getElementById("root")).render(<App/>);
