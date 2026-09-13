import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";

const USERS = { Steward: "steward@demo.gov", Approver: "approver@demo.gov", "Org Admin": "admin@demo.gov", "Enterprise Admin": "enterprise@demo.gov" };
const NAV = ["Steward Home", "My Information", "Discover Data", "My Next Steps", "Data Asset 360", "Review Queue", "Publication History"];

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
      <div className="tagline">Discover → Describe → Govern → Measure → Resolve → Publish</div>
      <nav>{NAV.map(n => <button key={n} onClick={() => setPage(n)} className={page===n?"active":""}>{n}</button>)}</nav>
      <div className="aside-note"><b>Hidden standards</b><p>Users answer ordinary business questions. AI Data Steward produces standards-based metadata behind the scenes.</p></div>
    </aside>
    <main>
      <header>
        <div><div className="org">{me?.organization?.name || "Loading..."}</div><div className="role">{me?.role || ""}</div></div>
        <label className="role-switch">Demo as<select value={userLabel} onChange={e=>setUserLabel(e.target.value)}>{Object.keys(USERS).map(u=><option key={u}>{u}</option>)}</select></label>
      </header>
      {message && <div className="message">{message}</div>}
      {page === "Steward Home" && <StewardHome dashboard={dashboard} assets={assets} tasks={tasks} onTask={task=>{
        setSelectedAssetId(task.asset_id);
        if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
          setGuidedTask(null);
          setAssetTab("Data Quality");
          setSelectedQualityIssueId(Number(task.source_reference));
        } else {
          setGuidedTask(task);
          setAssetTab(task.governance_domain==="QUALITY"?"Data Quality":"Governance");
          setSelectedQualityIssueId(null);
        }
        setPage("Data Asset 360");
      }} onInventory={()=>setPage("My Information")} onDiscover={()=>setPage("Discover Data")} onAllTasks={()=>setPage("My Next Steps")} />}
      {page === "My Information" && <Dashboard dashboard={dashboard} assets={assets} onOpen={id=>{setSelectedAssetId(id);setPage("Data Asset 360")}} />}
      {page === "Discover Data" && <Discover systems={systems} userEmail={userEmail} onDone={async id=>{await refresh();setSelectedAssetId(id);setPage("Data Asset 360")}} />}
      {page === "My Next Steps" && <Inbox tasks={tasks} onGuide={task=>{
        setSelectedAssetId(task.asset_id);
        if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
          setGuidedTask(null);
          setAssetTab("Data Quality");
          setSelectedQualityIssueId(Number(task.source_reference));
        } else {
          setGuidedTask(task);
          setAssetTab(task.governance_domain==="QUALITY"?"Data Quality":"Governance");
          setSelectedQualityIssueId(null);
        }
        setPage("Data Asset 360");
      }} />}
      {page === "Data Asset 360" && <Asset360 asset={selectedAsset} assets={assets} systems={systems} userEmail={userEmail} selectedAssetId={selectedAssetId} setSelectedAssetId={id=>{setSelectedAssetId(id);setSelectedQualityIssueId(null);setGuidedTask(null);setAssetTab("Overview")}} doAction={doAction} tab={assetTab} setTab={setAssetTab} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} guidedTask={guidedTask} setGuidedTask={setGuidedTask} />}
      {page === "Review Queue" && <ReviewQueue assets={assets} userEmail={userEmail} doAction={doAction} onOpen={id=>{setSelectedAssetId(id);setPage("Data Asset 360")}} />}
      {page === "Publication History" && <PublicationHistory assets={assets} selectedAssetId={selectedAssetId} setSelectedAssetId={setSelectedAssetId} userEmail={userEmail} />}
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
      <div><div className="eyebrow">Steward Home</div><h1>What needs your attention</h1><p className="lead">Work the highest-value item first. You can always ask for help or expert review rather than guessing.</p></div>
      <button onClick={()=>setShowIntro(true)}>What is my role?</button>
    </div>

    <div className="metrics four">
      <Metric label="Information assets" value={assetCount}/>
      <Metric label="Needs your attention" value={now.length}/>
      <Metric label="Waiting on others" value={waiting.length}/>
      <Metric label="Governance readiness" value={`${dashboard?.average_governance_readiness??0}%`}/>
    </div>

    {next?<section className="panel start-here">
      <div className="eyebrow">Start here</div>
      <h2>{next.title}</h2>
      <p><b>{next.asset_name}</b> · {next.responsibility||next.governance_domain}</p>
      <div className="guided-task-grid">
        <div><b>Why this matters</b><p>{next.why_it_matters}</p></div>
        <div><b>What you should do</b><p>{next.recommended_action}</p></div>
        <div><b>What this responsibility means</b><p>{next.learn_text}</p></div>
      </div>
      <button className="primary" onClick={()=>onTask(next)}>{next.source_type==="QUALITY_ISSUE"?"Review findings":"Guide me through this"}</button>
    </section>:<section className="panel success-panel"><h2>You are caught up.</h2><p>Nothing currently needs your attention. AI Data Steward will bring work back here when something changes.</p></section>}

    <div className="two-col steward-columns">
      <section className="panel">
        <div className="task-head"><div><div className="eyebrow">Your work</div><h2>Next up</h2></div><button onClick={onAllTasks}>View all</button></div>
        {now.slice(1,4).length===0&&<div className="empty">No additional tasks right now.</div>}
        {now.slice(1,4).map(t=><div className="home-task" key={t.id}><div><span className="priority">{t.priority}</span><b>{t.title}</b><small>{t.asset_name} · {t.responsibility||t.governance_domain}</small></div><button onClick={()=>onTask(t)}>Open</button></div>)}
      </section>
      <section className="panel">
        <div className="task-head"><div><div className="eyebrow">Coordination</div><h2>Waiting on others</h2></div></div>
        {waiting.length===0&&<div className="empty">Nothing is waiting on someone else.</div>}
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
    <h1>My Information Inventory</h1>
    <p className="lead">Your organization’s governed information landscape — systems, data assets, metadata, stewardship work, quality, and publication status.</p>
    <div className="metrics six">
      <Metric label="Known Systems" value={dashboard.systems}/><Metric label="Data Assets" value={dashboard.assets}/><Metric label="Open Stewardship Tasks" value={dashboard.open_tasks}/><Metric label="Governance Readiness" value={`${dashboard.average_governance_readiness}%`}/><Metric label="Average Quality" value={`${dashboard.average_quality_score}%`}/><Metric label="Unstructured Resources" value={dashboard.unstructured_resources}/>
    </div>
    <h2>Data assets</h2>
    <div className="grid">{assets.map(a=><div className="card" key={a.asset.asset_id}>
      <div className="eyebrow">{a.asset.business_domain || "Business information"}</div><h3>{a.asset.name}</h3><p>{a.asset.business_definition || "Definition needs review."}</p>
      <div className="status-line"><span>Governance readiness</span><b>{a.readiness.score}%</b></div><div className="progress"><div style={{width:`${a.readiness.score}%`}} /></div>
      <div className="status-line"><span>Data quality</span><b>{a.quality?.overall_score != null ? `${a.quality.overall_score}%` : "Not assessed"}</b></div>
      <div className="status-line"><span>Open tasks</span><b>{a.task_summary.open}</b></div>
      <div className="status-line"><span>Publication</span><Status value={a.publication.status}/></div>
      <button className="primary" onClick={()=>onOpen(a.asset.asset_id)}>Open asset</button>
    </div>)}</div>
  </>;
}

function Inbox({tasks, onGuide}) {
  const rank = {HIGH:0, MEDIUM:1, LOW:2};
  const sorted = [...tasks].sort((a,b)=>(rank[a.priority]??9)-(rank[b.priority]??9));
  return <>
    <h1>My Next Steps</h1><p className="lead">Start at the top and use the guided workflow. You do not need to know which governance module to visit, and you should escalate rather than guess when you are unsure.</p>
    <div className="task-summary">{["HIGH","MEDIUM","LOW"].map(p=><Metric key={p} label={`${p} priority`} value={tasks.filter(t=>t.priority===p).length}/>)}</div>
    {sorted.length===0 && <div className="empty">Nothing needs attention right now.</div>}
    {sorted.map(t=>{const isQuality=t.source_type==="QUALITY_ISSUE";return <div className={`task task-${t.priority.toLowerCase()}`} key={t.id}>
      <div className="task-head"><div><div className="eyebrow">{t.governance_domain} · {t.asset_name}</div><h3>{t.title}</h3></div><span className="priority">{t.priority}</span></div>
      <div className="two-col compact"><div><b>Why this matters</b><p>{isQuality?"TestGen found patterns in this data that need a steward's review. They are observations, not automatic errors.":t.why_it_matters}</p></div><div><b>Recommended next step</b><p>{isQuality?"Open the findings workbench, start with the first item marked Needs review, and work through the findings one at a time.":t.recommended_action}</p></div></div>
      <button className="primary" onClick={()=>onGuide(t)}>{isQuality?"Review findings":"Guide me"}</button>
    </div>})}
  </>;
}

function Discover({systems, userEmail, onDone}) {
  const [step,setStep]=useState(1), [systemName,setSystemName]=useState("Business Licensing System"), [purpose,setPurpose]=useState("Manages licenses, applications, payments, disciplinary actions, and uploaded PDF applications."), [assetName,setAssetName]=useState("Application"), [definition,setDefinition]=useState("Information submitted by an individual or organization requesting a professional license or related agency action."), [createdAsset,setCreatedAsset]=useState(null), [resourceName,setResourceName]=useState("Submitted License Applications"), [resourceType,setResourceType]=useState("PDF_COLLECTION"), [structureType,setStructureType]=useState("UNSTRUCTURED");
  const candidates=["License","Application","Payment","Disciplinary Action"];
  async function createAsset(){const a=await api("/assets",userEmail,{method:"POST",body:JSON.stringify({name:assetName,business_definition:definition,business_domain:"Professional Licensing",business_owner:"Licensing Division"})});setCreatedAsset(a);setStep(4)}
  async function addResource(){const s=systems.find(x=>x.name===systemName)||systems[0];await api(`/assets/${createdAsset.asset.asset_id}/resources`,userEmail,{method:"POST",body:JSON.stringify({system_id:s?.id||null,name:resourceName,resource_type:resourceType,structure_type:structureType,description:"Resource identified during guided discovery.",relationship_type:"REPRESENTATION",is_authoritative:false})});onDone(createdAsset.asset.asset_id)}
  return <><h1>Discover Your Data</h1><p className="lead">Start with a system you know. We will guide you from software usage to a real inventory of the information your organization manages.</p><div className="stepper">{[1,2,3,4].map(n=><div key={n} className={step>=n?"step on":"step"}>{n}</div>)}</div>
    {step===1&&<section className="panel"><div className="eyebrow">Step 1</div><h2>What system or tool does your team use?</h2><input value={systemName} onChange={e=>setSystemName(e.target.value)}/><button className="primary" onClick={()=>setStep(2)}>Continue</button></section>}
    {step===2&&<section className="panel"><div className="eyebrow">Step 2</div><h2>What does this system help your team do?</h2><textarea rows="5" value={purpose} onChange={e=>setPurpose(e.target.value)}/><button className="primary" onClick={()=>setStep(3)}>Identify information</button></section>}
    {step===3&&<section className="panel"><div className="eyebrow">Step 3</div><h2>I found these potential data assets</h2><div className="candidate-list">{candidates.map(c=><label className="check-card" key={c}><input type="radio" checked={assetName===c} onChange={()=>setAssetName(c)}/><span>{c}</span></label>)}</div><div className="education"><b>You are building a catalog without filling out a catalog form.</b><p>A data asset is meaningful business information. The system is only one place where that information may live.</p></div><label>Describe {assetName} in plain language</label><textarea rows="4" value={definition} onChange={e=>setDefinition(e.target.value)}/><button className="primary" onClick={createAsset}>Add to my information inventory</button></section>}
    {step===4&&<section className="panel"><div className="eyebrow">Step 4</div><h2>Where else does this information exist?</h2><div className="education strong"><b>Think beyond databases.</b><p>PDFs, scanned forms, spreadsheets, emails, images, shared drives, and SharePoint libraries contain information that also needs governance.</p></div><label>Resource name</label><input value={resourceName} onChange={e=>setResourceName(e.target.value)}/><label>Type</label><select value={resourceType} onChange={e=>{const v=e.target.value;setResourceType(v);setStructureType(["PDF_COLLECTION","DOCUMENT_LIBRARY","EMAIL_COLLECTION","IMAGE_COLLECTION"].includes(v)?"UNSTRUCTURED":"STRUCTURED")}}><option value="PDF_COLLECTION">PDF document collection</option><option value="DOCUMENT_LIBRARY">Document library</option><option value="SPREADSHEET">Spreadsheet</option><option value="DATABASE_TABLE">Database table</option><option value="API">API</option></select><label>Structure</label><input value={structureType} readOnly/><button className="primary" onClick={addResource}>Add resource and continue to governance</button></section>}
  </>;
}

function Asset360({asset,assets,systems,userEmail,selectedAssetId,setSelectedAssetId,doAction,tab,setTab,selectedQualityIssueId,setSelectedQualityIssueId,guidedTask,setGuidedTask}) {
  const [quality,setQuality]=useState(null), [metaKey,setMetaKey]=useState("theme"), [metaValue,setMetaValue]=useState("Professional Licensing"), [gov,setGov]=useState({});
  useEffect(()=>{if(asset){setGov({business_owner:asset.asset.business_owner||"",data_steward:asset.asset.data_steward||"",classification:asset.asset.classification||"",retention_requirement:asset.asset.retention_requirement||"",retention_authority:asset.asset.retention_authority||""});api(`/assets/${asset.asset.asset_id}/quality`,userEmail).then(setQuality)}},[asset?.asset?.asset_id,userEmail]);
  if(!asset)return <p>No data assets yet.</p>; const a=asset.asset;
  return <><div className="title-row"><div><h1>Information Details</h1><p className="lead">One place to understand what this information means, where it lives, how it is governed, and whether it can be trusted.</p></div><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select></div>
    <section className="asset-hero"><div><div className="eyebrow">{a.business_domain||"Business information"}</div><h2>{a.name}</h2><p>{a.business_definition}</p></div><div className="hero-scores"><div><span>Governance</span><strong>{asset.readiness.score}%</strong></div><div><span>Quality</span><strong>{asset.quality?.overall_score != null ? `${asset.quality.overall_score}%` : "—"}</strong></div><Status value={asset.publication.status}/></div></section>
    <div className="tabs">{["Overview","Metadata & Tags","Governance","Data Quality","Publication"].map(t=><button key={t} className={tab===t?"tab active":"tab"} onClick={()=>setTab(t)}>{t}</button>)}</div>
    {tab==="Overview"&&<div className="two-col"><section className="panel"><h2>Governance readiness</h2>{asset.readiness.checks.map(c=><div className="readiness-row" key={c.key}><span className={c.complete?"ok":"warn"}>{c.complete?"✓":"!"}</span><div><b>{c.title}</b><small>{c.complete?"Complete":c.guidance}</small></div></div>)}</section><section className="panel"><h2>Where this information lives</h2>{asset.resources.map(r=><div className="resource" key={r.resource_id}><b>{r.name}</b><span>{friendlyType(r.resource_type)} · {r.structure_type}</span><span>{r.system||"No system"}{r.is_authoritative?" · Authoritative source":""}</span></div>)}</section></div>}
    {tab==="Metadata & Tags"&&<section className="panel"><div className="eyebrow">Plain language → standards behind the scenes</div><h2>Help people understand and find this information</h2><p className="muted">The user never sees DCAT field names. These answers are mapped to standards when published.</p><label>{metaKey==="theme"?"What business area does this information relate to?":metaKey==="keyword"?"What words would someone search for?":metaKey==="update_frequency"?"How often is this information updated?":"Who can answer questions about this information?"}</label><select value={metaKey} onChange={e=>setMetaKey(e.target.value)}><option value="theme">Business area</option><option value="keyword">Search terms</option><option value="update_frequency">Update frequency</option><option value="contact">Contact point</option></select><input value={metaValue} onChange={e=>setMetaValue(e.target.value)}/><button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset_id}/metadata`,userEmail,{method:"PUT",body:JSON.stringify({metadata_key:metaKey,metadata_value:metaKey==="keyword"?metaValue.split(",").map(x=>x.trim()).filter(Boolean):metaKey==="contact"?{name:metaValue,email:"contact@example.gov"}:metaValue})}),"Metadata saved and readiness recalculated.")}>Save metadata</button></section>}
    {tab==="Governance"&&<GovernanceGuide asset={asset} gov={gov} setGov={setGov} userEmail={userEmail} doAction={doAction} guidedTask={guidedTask} setGuidedTask={setGuidedTask}/>}
    {tab==="Data Quality"&&<QualityPanel quality={quality} asset={asset} userEmail={userEmail} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} doAction={async(fn,msg)=>{await doAction(fn,msg);setQuality(await api(`/assets/${a.asset_id}/quality`,userEmail))}}/>}
    {tab==="Publication"&&<PublicationPanel asset={asset} userEmail={userEmail} doAction={doAction}/>} 
  </>;
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
    <section className="panel">
      <div className="eyebrow">Quality engine · DataKitchen TestGen</div>
      <h2>Assess Data Quality</h2>
      <p className="muted">AI Data Steward remains the steward experience. TestGen performs profiling and test execution underneath it.</p>
      <div className="engine-banner"><div><b>{quality?.engine_mode==="real"?"Real TestGen integration":"Demo integration mode"}</b><span>{quality?.engine_mode==="real"?`${engineStatus?.base_url||"TestGen API"} · ${engineStatus?.auth_mode||"authentication not loaded"}`:"Uses a deterministic TestGen-shaped simulator so you can validate the full workflow before connecting TestGen."}</span></div><Status value={link?.sync_status||"NOT LINKED"}/></div>
      {resourceId&&<div className="quality-context"><div><span>Business asset</span><b>{asset.asset.name}</b></div><div><span>Cataloged resource</span><b>{structured.find(r=>r.resource_id===Number(resourceId))?.name||"—"}</b></div><div><span>Governed source</span><b>{link?.source_mapping?.qualified_name||link?.external_table_name||"Not mapped"}</b></div></div>}
      <label>Structured resource to assess</label>
      <select value={resourceId} onChange={e=>setResourceId(e.target.value)}>{structured.map(r=><option key={r.resource_id} value={r.resource_id}>{r.name} · {r.system||"No system"}</option>)}</select>
      {structured.length===0&&<div className="education strong"><b>No structured resource is available.</b><p>Quality profiling applies to structured resources. Unstructured PDFs and document libraries remain governed through metadata, classification, retention, and other stewardship workflows.</p></div>}
      {quality?.engine_mode==="real"&&<details className="config-box" open><summary>Governed source & TestGen mapping</summary><p className="muted">Connect this cataloged resource to the real technical source TestGen assesses. Database credentials stay in TestGen; AI Data Steward stores only the governed source identity and TestGen object IDs.</p><div className="mapping-section"><div className="eyebrow">Real governed source</div><div className="mapping-grid"><label>TestGen connection name<input value={sourceConnectionName} onChange={e=>setSourceConnectionName(e.target.value)} placeholder="e.g. Data_Lab"/></label><label>Database<input value={sourceDatabase} onChange={e=>setSourceDatabase(e.target.value)} placeholder="e.g. corporate_registry"/></label><label>Schema<input value={sourceSchema} onChange={e=>setSourceSchema(e.target.value)} placeholder="public"/></label><label>Table<input value={sourceTable} onChange={e=>setSourceTable(e.target.value)} placeholder="corporate_data"/></label></div></div><div className="mapping-section"><div className="eyebrow">TestGen execution mapping</div><div className="mapping-grid"><label>Project code<input value={projectCode} onChange={e=>setProjectCode(e.target.value)} placeholder={engineStatus?.project_code||"DEFAULT"}/></label><label>Table group ID<input value={tableGroupId} onChange={e=>setTableGroupId(e.target.value)} placeholder={engineStatus?.table_group_id||"TestGen table-group UUID"}/></label><label>Test suite ID<input value={testSuiteId} onChange={e=>setTestSuiteId(e.target.value)} placeholder={engineStatus?.test_suite_id||"TestGen test-suite UUID"}/></label></div>{(link?.source_mapping?.qualified_name||link?.external_table_name)&&<div className="source-summary"><b>Currently mapped source</b><span>{[link?.source_mapping?.connection_name,link?.source_mapping?.database,link?.source_mapping?.qualified_name||link?.external_table_name].filter(Boolean).join(" → ")}</span></div>}</div><div className="button-row"><button onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/link`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId),project_code:projectCode||engineStatus?.project_code,table_group_id:tableGroupId||engineStatus?.table_group_id,test_suite_id:testSuiteId||engineStatus?.test_suite_id,source_connection_name:sourceConnectionName,source_database:sourceDatabase,source_schema:sourceSchema,source_table:sourceTable,external_table_name:sourceTable?`${sourceSchema?`${sourceSchema}.`:""}${sourceTable}`:structured.find(r=>r.resource_id===Number(resourceId))?.name})}),"Governed source and TestGen mapping saved.")}>Save source mapping</button><button className="primary" onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/test-connection`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Authenticated TestGen connection succeeded.")}>Test connection</button></div></details>}
      <div className="button-row"><button className="primary" disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/assess`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Data quality assessment completed. Review the profiling findings below.")}>Assess Data Quality</button><button disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/run`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),quality?.engine_mode==="real"?"TestGen quality checks ran. Current failures were synchronized into stewardship work.":"Approved quality checks ran. Any failures were converted into stewardship work.")}>{quality?.engine_mode==="real"?"Run Quality Checks":"Run Approved Checks"}</button></div>
    </section>

    <section className="panel">
      <div className="eyebrow">Can we trust it?</div><h2>Quality Health</h2>
      {q?<><div className="quality-score"><strong>{q.overall_score}%</strong><span>Overall quality · {q.source}</span></div><div className="quality-grid"><Metric label="Completeness" value={q.completeness_score!=null?`${q.completeness_score}%`:"—"}/><Metric label="Validity" value={q.validity_score!=null?`${q.validity_score}%`:"—"}/><Metric label="Uniqueness" value={q.uniqueness_score!=null?`${q.uniqueness_score}%`:"—"}/><Metric label="Consistency" value={q.consistency_score!=null?`${q.consistency_score}%`:"—"}/><Metric label="Timeliness" value={q.timeliness_score!=null?`${q.timeliness_score}%`:"—"}/></div></>:<p>No quality assessment has been recorded.</p>}
    </section>

    <section className="panel"><h2>Quality expectations</h2><p className="muted">{quality?.engine_mode==="real"?"The mapped TestGen test suite is the execution source. AI Data Steward converts failures into guided stewardship work.":"TestGen discovers patterns and candidate checks. The steward decides which expectations should become governed rules."}</p>{quality?.rules?.length?quality.rules.map(r=><div className="rule" key={r.id}><div><b>{r.plain_language_rule}</b><span>{friendlyType(r.rule_type)} · {r.status}</span>{r.latest_result&&<small>{r.latest_result.failed_count||0} failed in the latest run</small>}</div><div className="button-row mini">{r.status==="PROPOSED"&&<><button className="primary" onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"APPROVED"})}),"Quality expectation approved.")}>Approve</button><button onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"REJECTED"})}),"Quality expectation rejected.")}>Reject</button></>}</div></div>):<p>Run an assessment to generate suggested expectations.</p>}</section>

    <section className="panel"><h2>Quality issues requiring a stewardship decision</h2><p className="muted">Profiling findings describe characteristics worth reviewing. Test failures show where an expected quality check did not pass. Neither automatically means the data is wrong.</p>{openIssues.length===0&&<div className="empty">No unresolved quality issues.</div>}{openIssues.map(i=>{const evidence=i.details?.evidence||{};const samples=evidence.sample_values?.length?evidence.sample_values:i.details?.sample_values;const isProfile=i.issue_type==="HYGIENE_FINDING";const summary=i.details?.finding_summary||{};return <div className={`quality-issue severity-${i.severity.toLowerCase()}`} key={i.id}><div className="task-head"><div><div className="eyebrow">{i.source} · {isProfile?"PROFILING FINDING":"QUALITY CHECK FAILURE"}</div><h3>{i.title}</h3></div><span className="priority">{i.severity}</span></div><p>{i.description}</p>{isProfile&&<><div className="finding-summary-grid"><Metric label="Needs review" value={summary.pending??i.details?.finding_count??0}/><Metric label="Reviewed" value={summary.resolved??0}/><Metric label="Expert review" value={summary.escalated??0}/><Metric label="Potential PII" value={i.details?.potential_pii_count||0}/></div><p className="muted">You do not need to understand TestGen terminology. AI Data Steward translates each finding into what it means, why it matters, and what to do next.</p></>}{!isProfile&&<div className="evidence-grid">{evidence.status&&<Metric label="Result" value={evidence.status}/>} {evidence.test_type&&<Metric label="Check type" value={friendlyType(evidence.test_type)}/>} {evidence.evaluated_count!=null&&<Metric label="Records evaluated" value={Number(evidence.evaluated_count).toLocaleString()}/>} {i.failed_count!=null&&<Metric label="Records affected" value={i.failed_count.toLocaleString()}/>} {evidence.score!=null&&<Metric label="Check score" value={`${evidence.score}%`}/>}</div>}{evidence.columns?.length>0&&<p><b>Fields:</b> {evidence.columns.join(", ")}</p>}{samples?.length>0&&<div className="sample-values"><b>Example evidence</b><span>{samples.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<button className="primary" onClick={()=>{setSelectedQualityIssueId(i.id);setNotes("");if(isProfile){setHygieneIssue(i);setDecisionIssue(null);setSelectedHygieneFinding(null);window.setTimeout(()=>document.getElementById("profiling-workbench")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}else{setDecisionIssue(i);setHygieneIssue(null);window.setTimeout(()=>document.getElementById("guided-investigation")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}}}>{isProfile?"Review findings":"Guide Me"}</button></div>})}</section>

    {hygieneIssue&&<section id="profiling-workbench" className="panel guide-panel"><div className="eyebrow">Profiling findings workbench</div><h2>Review findings one at a time</h2><div className="next-step-callout"><b>What to do next</b><span>Start with the first item marked <strong>Needs review</strong>. Read what TestGen found, check why it matters, then choose the stewardship decision that best matches the business reality. Work through the list one finding at a time.</span></div><p className="muted">TestGen found patterns in the data. These are observations, not automatic errors.</p><div className="finding-progress"><b>{hygieneIssue.details?.finding_summary?.pending??0} need review</b><span>{hygieneIssue.details?.finding_summary?.resolved??0} reviewed · {hygieneIssue.details?.finding_summary?.escalated??0} sent for expert review</span></div><div className="finding-list">{(hygieneIssue.details?.steward_findings||[]).map(f=><div key={f.fingerprint} className={`steward-finding status-${(f.review_status||"PENDING").toLowerCase()}`}><div className="task-head"><div><div className="eyebrow">{f.column} · {friendlyType(f.category)}</div><h3>{f.title}</h3></div><span className="finding-status">{f.review_status==="RESOLVED"?"Reviewed":f.review_status==="ESCALATED"?"Expert review":"Needs review"}</span></div><p><b>Why it matters</b><br/>{f.why_it_matters}</p><p><b>Recommended next step</b><br/>{f.recommended_action}</p>{f.affected_count!=null&&<p><b>{Number(f.affected_count).toLocaleString()}</b> affected records</p>}{f.examples?.length>0&&<div className="sample-values"><b>Example evidence</b><span>{f.examples.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<details className="technical-detail"><summary>What TestGen called this</summary><code>{f.testgen_finding}</code></details><button className={f.review_status==="PENDING"?"primary":""} onClick={()=>{setSelectedHygieneFinding(f);setNotes(f.notes||"");window.setTimeout(()=>document.getElementById("finding-decision")?.scrollIntoView({behavior:"smooth",block:"center"}),100)}}>{f.review_status==="PENDING"?"Review this finding":"Review decision"}</button></div>)}</div></section>}
    {hygieneIssue&&selectedHygieneFinding&&<section id="finding-decision" className="panel guide-panel finding-decision"><div className="eyebrow">Guided finding review</div><h2>{selectedHygieneFinding.title}</h2><div className="finding-decision-context"><div><span>Field</span><b>{selectedHygieneFinding.column||"—"}</b></div><div><span>Category</span><b>{friendlyType(selectedHygieneFinding.category||"PROFILE")}</b></div><div><span>Status</span><b>{selectedHygieneFinding.review_status==="RESOLVED"?"Reviewed":selectedHygieneFinding.review_status==="ESCALATED"?"Expert review":"Needs review"}</b></div>{selectedHygieneFinding.affected_count!=null&&<div><span>Affected records</span><b>{Number(selectedHygieneFinding.affected_count).toLocaleString()}</b></div>}{selectedHygieneFinding.confidence&&<div><span>TestGen confidence</span><b>{selectedHygieneFinding.confidence}</b></div>}</div><div className="finding-decision-detail"><div><b>What TestGen found</b><p>{selectedHygieneFinding.testgen_finding||"Profiling observation"}</p></div><div className="evidence-panel"><div className="evidence-panel-head"><div><b>Evidence available for this decision</b><p className="muted">Review the evidence before choosing a stewardship decision.</p></div><span className={`evidence-level evidence-${(selectedHygieneFinding.evidence?.sufficiency?.level||"LOW").toLowerCase()}`}>{selectedHygieneFinding.evidence?.sufficiency?.level||"LOW"} evidence</span></div>{selectedHygieneFinding.evidence?.testgen?.observed_values?.length>0&&<div className="evidence-block"><b>Observed value{selectedHygieneFinding.evidence.testgen.observed_values.length===1?"":"s"}</b><div className="evidence-values">{selectedHygieneFinding.evidence.testgen.observed_values.map((v,idx)=><code key={idx}>{v===null?"(missing)":String(v)}</code>)}</div></div>}{selectedHygieneFinding.evidence?.testgen?.detail&&<div className="evidence-block"><b>TestGen evidence</b><p>{selectedHygieneFinding.evidence.testgen.detail}</p>{selectedHygieneFinding.evidence.testgen.records_profiled!=null&&<p><b>{Number(selectedHygieneFinding.evidence.testgen.records_profiled).toLocaleString()}</b> records were profiled.</p>}</div>}{selectedHygieneFinding.evidence?.testgen?.affected_count!=null&&<div className="evidence-block"><b>Estimated impact</b><p><b>{Number(selectedHygieneFinding.evidence.testgen.affected_count).toLocaleString()}</b> records match this finding{selectedHygieneFinding.evidence.testgen.affected_percent!=null?` (${selectedHygieneFinding.evidence.testgen.affected_percent}%)`:""}.</p></div>}{selectedHygieneFinding.evidence?.testgen?.patterns?.length>0&&<div className="evidence-block"><b>Observed format distribution</b><div className="pattern-list">{selectedHygieneFinding.evidence.testgen.patterns.map((p,idx)=><span key={idx}><code>{p.pattern}</code><b>{Number(p.count).toLocaleString()}</b></span>)}</div></div>}{selectedHygieneFinding.evidence?.testgen?.semantic_type&&<div className="evidence-block"><b>Detected semantic type</b><p>{selectedHygieneFinding.evidence.testgen.semantic_type}</p></div>}{selectedHygieneFinding.evidence?.testgen?.minimum_value&&<div className="evidence-block"><b>Minimum observed value</b><p><code>{selectedHygieneFinding.evidence.testgen.minimum_value}</code></p></div>}{selectedHygieneFinding.evidence?.testgen?.affected_count!=null&&<div className="evidence-block"><b>How common is it?</b><p>{Number(selectedHygieneFinding.evidence.testgen.affected_count).toLocaleString()} affected record{Number(selectedHygieneFinding.evidence.testgen.affected_count)===1?"":"s"}{selectedHygieneFinding.evidence?.profile_context?.row_count?` out of ${Number(selectedHygieneFinding.evidence.profile_context.row_count).toLocaleString()} profiled records`:""}.</p></div>}{Object.keys(selectedHygieneFinding.evidence?.profile_context||{}).length>0&&<div className="evidence-block"><b>Profile context for {selectedHygieneFinding.column}</b><div className="profile-context-grid">{selectedHygieneFinding.evidence.profile_context.data_type&&<Metric label="Data type" value={selectedHygieneFinding.evidence.profile_context.data_type}/>} {selectedHygieneFinding.evidence.profile_context.semantic_type&&<Metric label="Detected meaning" value={selectedHygieneFinding.evidence.profile_context.semantic_type}/>} {selectedHygieneFinding.evidence.profile_context.row_count!=null&&<Metric label="Rows profiled" value={Number(selectedHygieneFinding.evidence.profile_context.row_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.distinct_count!=null&&<Metric label="Distinct values" value={Number(selectedHygieneFinding.evidence.profile_context.distinct_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.null_count!=null&&<Metric label="Missing values" value={Number(selectedHygieneFinding.evidence.profile_context.null_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.null_percent!=null&&<Metric label="Missing %" value={`${selectedHygieneFinding.evidence.profile_context.null_percent}%`}/>} {selectedHygieneFinding.evidence.profile_context.min_length!=null&&<Metric label="Shortest length" value={selectedHygieneFinding.evidence.profile_context.min_length}/>} {selectedHygieneFinding.evidence.profile_context.max_length!=null&&<Metric label="Longest length" value={selectedHygieneFinding.evidence.profile_context.max_length}/>} {selectedHygieneFinding.evidence.profile_context.avg_length!=null&&<Metric label="Typical length" value={selectedHygieneFinding.evidence.profile_context.avg_length}/>}</div>{selectedHygieneFinding.evidence.profile_context.typical_values?.length>0&&<div className="typical-values"><b>Typical / common values</b>{selectedHygieneFinding.evidence.profile_context.typical_values.map((item,idx)=><span key={idx}><code>{String(item.value)}</code>{item.count!=null&&` · ${Number(item.count).toLocaleString()} records`}</span>)}</div>}</div>}<div className="evidence-block source-evidence"><b>Source-record verification</b><p>{selectedHygieneFinding.evidence?.source_record_context?.message||"Open the source system or ask the data owner to verify the underlying record when the profile evidence is not enough."}</p></div><div className={`evidence-guidance evidence-${(selectedHygieneFinding.evidence?.sufficiency?.level||"LOW").toLowerCase()}`}><b>{selectedHygieneFinding.evidence?.sufficiency?.level==="LOW"?"More evidence is needed before making a confident decision":"Evidence guidance"}</b><p>{selectedHygieneFinding.evidence?.sufficiency?.guidance||"Verify the source record or consult a business expert before deciding."}</p>{selectedHygieneFinding.evidence?.sufficiency?.limitations?.length>0&&<ul>{selectedHygieneFinding.evidence.sufficiency.limitations.map((x,idx)=><li key={idx}>{x}</li>)}</ul>}</div></div><div><b>Why it matters</b><p>{selectedHygieneFinding.why_it_matters}</p></div><div><b>Recommended next step</b><p>{selectedHygieneFinding.recommended_action}</p></div></div><p><b>What should you decide?</b> Pick the option that best matches the business reality. If the evidence is limited, verify the source or use expert review rather than guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","This data needs correction"],["VALID_EXCEPTION","This is acceptable as-is"],["EXPECTATION_NEEDS_CHANGE","Create or adjust a quality expectation"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${hygieneIssue.id}/findings/${encodeURIComponent(selectedHygieneFinding.fingerprint)}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Finding decision recorded: ${label}.`).then(()=>{setSelectedHygieneFinding(null);setNotes("");})}>{label}</button>)}</div></section>}
    {decisionIssue&&<section id="guided-investigation" className="panel guide-panel"><div className="eyebrow">Guided investigation</div><h2>{decisionIssue.title}</h2><p><b>Step 1 — Understand what TestGen found.</b> {decisionIssue.issue_type==="HYGIENE_FINDING"?"A profiling finding highlights a characteristic or pattern that deserves review; it is not a failed rule by itself.":"A quality check did not pass. Review the affected records, fields, and evidence before deciding why."}</p><p><b>Step 2 — Make a stewardship decision.</b> Choose the explanation that best matches what you know. If you cannot determine it, escalate instead of guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","The data is incorrect"],["VALID_EXCEPTION","This is a valid exception"],["EXPECTATION_NEEDS_CHANGE","The quality expectation needs to change"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${decisionIssue.id}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Decision recorded: ${label}.`).then(()=>{setDecisionIssue(null);setSelectedQualityIssueId(null)})}>{label}</button>)}</div></section>}
  </>;
}

function PublicationPanel({asset,userEmail,doAction}) {
  const required=asset.readiness.checks.filter(c=>c.required);
  const missing=required.filter(c=>!c.complete);
  const ready=missing.length===0;
  const status=asset.publication.status;
  return <section className="panel">
    <div className="eyebrow">Guided publication readiness</div>
    <h2>{ready?"This information is ready for the next review step":"There are still things to finish before review"}</h2>
    <p className="lead">{ready?"You have completed the required stewardship information. Submitting does not publish the information—it sends the governed snapshot to an approver for review.":"AI Data Steward has checked the required stewardship information. Finish the items below before submitting rather than trying to understand catalog standards yourself."}</p>
    <div className={`publication-readiness ${ready?"ready":"not-ready"}`}><strong>{required.length-missing.length} of {required.length}</strong><span>required stewardship checks complete</span></div>
    {required.map(c=><div className="readiness-row" key={c.key}><span className={c.complete?"ok":"warn"}>{c.complete?"✓":"!"}</span><div><b>{c.title}</b><small>{c.complete?"Complete":c.guidance}</small></div></div>)}
    <div className="education"><b>What happens next?</b><p><b>Submit for review</b> sends the asset to an approver. <b>Approval</b> creates an immutable governed release. <b>Publish</b> makes the approved release available through the configured enterprise catalog adapter.</p></div>
    <div className="lifecycle">{["DRAFT","IN_REVIEW","APPROVED","PUBLISHED"].map(s=><div key={s} className={status===s?"life current":"life"}>{s.replace("_"," ")}</div>)}</div>
    <div className="button-row">
      <button className="primary" disabled={!ready||!["DRAFT","NEEDS_UPDATE","REJECTED"].includes(status)} onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/submit`,userEmail,{method:"POST",body:JSON.stringify({comments:"Stewardship checks complete; ready for review."})}),"Submitted for review.")}>Submit for review</button>
      <button disabled={status!=="IN_REVIEW"} onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/approve`,userEmail,{method:"POST",body:JSON.stringify({comments:"Approved."})}),"Approved and immutable release created.")}>Approve</button>
      <button disabled={status!=="APPROVED"} onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published to the configured catalog adapter.")}>Publish</button>
    </div>
    {!ready&&<p className="muted">The submit button stays unavailable until required stewardship checks are complete.</p>}
  </section>;
}

function ReviewQueue({assets,userEmail,doAction,onOpen}) { const review=assets.filter(a=>["IN_REVIEW","APPROVED","NEEDS_UPDATE"].includes(a.publication.status)); return <><h1>Review Queue</h1><p className="lead">Assets waiting for governance approval or enterprise publication.</p>{review.length===0&&<div className="empty">Nothing is waiting for review.</div>}{review.map(a=><div className="review-row" key={a.asset.asset_id}><div><b>{a.asset.name}</b><span>{a.readiness.score}% governance readiness · {a.quality?.overall_score??"—"}% quality</span></div><Status value={a.publication.status}/><div className="button-row"><button onClick={()=>onOpen(a.asset.asset_id)}>Inspect</button>{a.publication.status==="IN_REVIEW"&&<><button onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/reject`,userEmail,{method:"POST",body:JSON.stringify({comments:"Please address the remaining governance questions."})}),"Returned for changes.")}>Return</button><button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/approve`,userEmail,{method:"POST",body:JSON.stringify({comments:"Approved."})}),"Approved.")}>Approve</button></>}{a.publication.status==="APPROVED"&&<button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published.")}>Publish</button>}</div></div>)}</> }

function PublicationHistory({assets,selectedAssetId,setSelectedAssetId,userEmail}) { const [history,setHistory]=useState(null); useEffect(()=>{if(selectedAssetId)api(`/assets/${selectedAssetId}/history`,userEmail).then(setHistory)},[selectedAssetId,userEmail]); return <><h1>Publication History</h1><p className="lead">Approved releases are immutable snapshots. DCAT JSON-LD is generated only when the release crosses the publication boundary.</p><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select><div className="two-col"><section className="panel"><h2>Audit timeline</h2>{history?.events?.length?history.events.map(e=><div className="timeline" key={e.id}><b>{e.event_type.replaceAll("_"," ")}</b><span>{e.from_status||"—"} → {e.to_status||"—"}</span><small>{e.created_at}</small></div>):<p>No events yet.</p>}</section><section className="panel"><h2>Immutable releases</h2>{history?.releases?.length?history.releases.map(r=><details key={r.id}><summary>Release v{r.version_number} {r.published_at?"· Published":"· Approved"}</summary><p><b>Snapshot hash:</b> {r.snapshot_hash}</p>{r.ckan_name&&<p><b>Catalog name:</b> {r.ckan_name}</p>}{r.publication_result?.dcat_payload&&<><p><b>Generated DCAT JSON-LD</b></p><pre>{JSON.stringify(r.publication_result.dcat_payload,null,2)}</pre></>}</details>):<p>No releases yet.</p>}</section></div></> }

function Metric({label,value}) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }
function Status({value}) { return <span className={`status status-${(value||"").toLowerCase()}`}>{(value||"").replaceAll("_"," ")}</span> }
function friendlyType(value){return (value||"").replaceAll("_"," ").toLowerCase().replace(/\b\w/g,m=>m.toUpperCase())}

createRoot(document.getElementById("root")).render(<App/>);
