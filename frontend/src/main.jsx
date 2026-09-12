import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";

const USERS = { Steward: "steward@demo.gov", Approver: "approver@demo.gov", "Org Admin": "admin@demo.gov", "Enterprise Admin": "enterprise@demo.gov" };
const NAV = ["My Organization", "Discover Data", "Stewardship Inbox", "Data Asset 360", "Review Queue", "Publication History"];

function App() {
  const [page, setPage] = useState("My Organization");
  const [userLabel, setUserLabel] = useState("Steward");
  const [me, setMe] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [assets, setAssets] = useState([]);
  const [systems, setSystems] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [assetTab, setAssetTab] = useState("Overview");
  const [selectedQualityIssueId, setSelectedQualityIssueId] = useState(null);
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
      {page === "My Organization" && <Dashboard dashboard={dashboard} assets={assets} onOpen={id=>{setSelectedAssetId(id);setPage("Data Asset 360")}} />}
      {page === "Discover Data" && <Discover systems={systems} userEmail={userEmail} onDone={async id=>{await refresh();setSelectedAssetId(id);setPage("Data Asset 360")}} />}
      {page === "Stewardship Inbox" && <Inbox tasks={tasks} onGuide={task=>{
        setSelectedAssetId(task.asset_id);
        if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
          setAssetTab("Data Quality");
          setSelectedQualityIssueId(Number(task.source_reference));
        } else {
          setAssetTab("Governance");
          setSelectedQualityIssueId(null);
        }
        setPage("Data Asset 360");
      }} />}
      {page === "Data Asset 360" && <Asset360 asset={selectedAsset} assets={assets} systems={systems} userEmail={userEmail} selectedAssetId={selectedAssetId} setSelectedAssetId={id=>{setSelectedAssetId(id);setSelectedQualityIssueId(null);setAssetTab("Overview")}} doAction={doAction} tab={assetTab} setTab={setAssetTab} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} />}
      {page === "Review Queue" && <ReviewQueue assets={assets} userEmail={userEmail} doAction={doAction} onOpen={id=>{setSelectedAssetId(id);setPage("Data Asset 360")}} />}
      {page === "Publication History" && <PublicationHistory assets={assets} selectedAssetId={selectedAssetId} setSelectedAssetId={setSelectedAssetId} userEmail={userEmail} />}
    </main>
  </div>;
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
    <h1>My Next Steps</h1><p className="lead">You do not need to know which governance module to visit. These are the actions that need your attention.</p>
    <div className="task-summary">{["HIGH","MEDIUM","LOW"].map(p=><Metric key={p} label={`${p} priority`} value={tasks.filter(t=>t.priority===p).length}/>)}</div>
    {sorted.length===0 && <div className="empty">Nothing needs attention right now.</div>}
    {sorted.map(t=><div className={`task task-${t.priority.toLowerCase()}`} key={t.id}>
      <div className="task-head"><div><div className="eyebrow">{t.governance_domain} · {t.asset_name}</div><h3>{t.title}</h3></div><span className="priority">{t.priority}</span></div>
      <div className="two-col compact"><div><b>Why this matters</b><p>{t.why_it_matters}</p></div><div><b>Recommended next step</b><p>{t.recommended_action}</p></div></div>
      <button className="primary" onClick={()=>onGuide(t)}>Guide me</button>
    </div>)}
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

function Asset360({asset,assets,systems,userEmail,selectedAssetId,setSelectedAssetId,doAction,tab,setTab,selectedQualityIssueId,setSelectedQualityIssueId}) {
  const [quality,setQuality]=useState(null), [metaKey,setMetaKey]=useState("theme"), [metaValue,setMetaValue]=useState("Professional Licensing"), [gov,setGov]=useState({});
  useEffect(()=>{if(asset){setGov({business_owner:asset.asset.business_owner||"",data_steward:asset.asset.data_steward||"",classification:asset.asset.classification||"",retention_requirement:asset.asset.retention_requirement||"",retention_authority:asset.asset.retention_authority||""});api(`/assets/${asset.asset.asset_id}/quality`,userEmail).then(setQuality)}},[asset?.asset?.asset_id,userEmail]);
  if(!asset)return <p>No data assets yet.</p>; const a=asset.asset;
  return <><div className="title-row"><div><h1>Information Details</h1><p className="lead">One place to understand what this information means, where it lives, how it is governed, and whether it can be trusted.</p></div><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select></div>
    <section className="asset-hero"><div><div className="eyebrow">{a.business_domain||"Business information"}</div><h2>{a.name}</h2><p>{a.business_definition}</p></div><div className="hero-scores"><div><span>Governance</span><strong>{asset.readiness.score}%</strong></div><div><span>Quality</span><strong>{asset.quality?.overall_score != null ? `${asset.quality.overall_score}%` : "—"}</strong></div><Status value={asset.publication.status}/></div></section>
    <div className="tabs">{["Overview","Metadata & Tags","Governance","Data Quality","Publication"].map(t=><button key={t} className={tab===t?"tab active":"tab"} onClick={()=>setTab(t)}>{t}</button>)}</div>
    {tab==="Overview"&&<div className="two-col"><section className="panel"><h2>Governance readiness</h2>{asset.readiness.checks.map(c=><div className="readiness-row" key={c.key}><span className={c.complete?"ok":"warn"}>{c.complete?"✓":"!"}</span><div><b>{c.title}</b><small>{c.complete?"Complete":c.guidance}</small></div></div>)}</section><section className="panel"><h2>Where this information lives</h2>{asset.resources.map(r=><div className="resource" key={r.resource_id}><b>{r.name}</b><span>{friendlyType(r.resource_type)} · {r.structure_type}</span><span>{r.system||"No system"}{r.is_authoritative?" · Authoritative source":""}</span></div>)}</section></div>}
    {tab==="Metadata & Tags"&&<section className="panel"><div className="eyebrow">Plain language → standards behind the scenes</div><h2>Help people understand and find this information</h2><p className="muted">The user never sees DCAT field names. These answers are mapped to standards when published.</p><label>{metaKey==="theme"?"What business area does this information relate to?":metaKey==="keyword"?"What words would someone search for?":metaKey==="update_frequency"?"How often is this information updated?":"Who can answer questions about this information?"}</label><select value={metaKey} onChange={e=>setMetaKey(e.target.value)}><option value="theme">Business area</option><option value="keyword">Search terms</option><option value="update_frequency">Update frequency</option><option value="contact">Contact point</option></select><input value={metaValue} onChange={e=>setMetaValue(e.target.value)}/><button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset_id}/metadata`,userEmail,{method:"PUT",body:JSON.stringify({metadata_key:metaKey,metadata_value:metaKey==="keyword"?metaValue.split(",").map(x=>x.trim()).filter(Boolean):metaKey==="contact"?{name:metaValue,email:"contact@example.gov"}:metaValue})}),"Metadata saved and readiness recalculated.")}>Save metadata</button></section>}
    {tab==="Governance"&&<section className="panel"><h2>Govern this information</h2><div className="form-grid"><label>Business owner<input value={gov.business_owner||""} onChange={e=>setGov({...gov,business_owner:e.target.value})}/></label><label>Data steward<input value={gov.data_steward||""} onChange={e=>setGov({...gov,data_steward:e.target.value})}/></label><label>Classification<select value={gov.classification||""} onChange={e=>setGov({...gov,classification:e.target.value})}><option value="">Needs review</option><option>Public</option><option>Internal</option><option>Sensitive</option><option>Restricted</option><option>Needs Expert Review</option></select></label><label>Retention requirement<input value={gov.retention_requirement||""} onChange={e=>setGov({...gov,retention_requirement:e.target.value})} placeholder="e.g., 5 years after closure"/></label><label className="wide">Retention authority<input value={gov.retention_authority||""} onChange={e=>setGov({...gov,retention_authority:e.target.value})} placeholder="Records schedule / policy source"/></label></div><button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset_id}/governance`,userEmail,{method:"PATCH",body:JSON.stringify(gov)}),"Governance information saved.")}>Save governance decisions</button></section>}
    {tab==="Data Quality"&&<QualityPanel quality={quality} asset={asset} userEmail={userEmail} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} doAction={async(fn,msg)=>{await doAction(fn,msg);setQuality(await api(`/assets/${a.asset_id}/quality`,userEmail))}}/>}
    {tab==="Publication"&&<PublicationPanel asset={asset} userEmail={userEmail} doAction={doAction}/>} 
  </>;
}

function QualityPanel({quality,asset,userEmail,doAction,selectedQualityIssueId,setSelectedQualityIssueId}) {
  const q=quality?.profiles?.[0];
  const structured=asset.resources.filter(r=>r.structure_type==="STRUCTURED");
  const [resourceId,setResourceId]=useState(structured[0]?.resource_id||"");
  const [projectCode,setProjectCode]=useState("");
  const [tableGroupId,setTableGroupId]=useState("");
  const [testSuiteId,setTestSuiteId]=useState("");
  const [decisionIssue,setDecisionIssue]=useState(null);
  const [notes,setNotes]=useState("");
  const [engineStatus,setEngineStatus]=useState(null);
  const link=quality?.links?.find(x=>x.resource_id===Number(resourceId));
  useEffect(()=>{api("/quality/engine/status",userEmail).then(setEngineStatus).catch(()=>setEngineStatus(null));},[userEmail]);
  const openIssues=(quality?.issues||[]).filter(i=>i.status!=="RESOLVED");

  useEffect(()=>{
    if(!selectedQualityIssueId || !quality?.issues?.length) return;
    const issue=quality.issues.find(i=>i.id===Number(selectedQualityIssueId));
    if(issue){
      setDecisionIssue(issue);
      setNotes("");
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
      <label>Structured resource to assess</label>
      <select value={resourceId} onChange={e=>setResourceId(e.target.value)}>{structured.map(r=><option key={r.resource_id} value={r.resource_id}>{r.name} · {r.system||"No system"}</option>)}</select>
      {structured.length===0&&<div className="education strong"><b>No structured resource is available.</b><p>Quality profiling applies to structured resources. Unstructured PDFs and document libraries remain governed through metadata, classification, retention, and other stewardship workflows.</p></div>}
      {quality?.engine_mode==="real"&&<details className="config-box" open><summary>TestGen connection mapping</summary><p className="muted">Create the database connection, table group, and test suite in TestGen once. AI Data Steward then drives profiling and test runs through its REST API.</p><label>Project code<input value={projectCode} onChange={e=>setProjectCode(e.target.value)} placeholder={engineStatus?.project_code||"e.g. default"}/></label><label>Table group ID<input value={tableGroupId} onChange={e=>setTableGroupId(e.target.value)}/></label><label>Test suite ID<input value={testSuiteId} onChange={e=>setTestSuiteId(e.target.value)}/></label><div className="button-row"><button onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/link`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId),project_code:projectCode||engineStatus?.project_code,table_group_id:tableGroupId,test_suite_id:testSuiteId,external_table_name:structured.find(r=>r.resource_id===Number(resourceId))?.name})}),"TestGen mapping saved.")}>Save TestGen mapping</button><button className="primary" onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/test-connection`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Authenticated TestGen connection succeeded.")}>Test connection</button></div></details>}
      <div className="button-row"><button className="primary" disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/assess`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Data quality assessment completed. Review the findings and suggested expectations below.")}>Assess Data Quality</button><button disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/run`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Approved quality checks ran. Any failures were converted into stewardship work.")}>Run Approved Checks</button></div>
    </section>

    <section className="panel">
      <div className="eyebrow">Can we trust it?</div><h2>Quality Health</h2>
      {q?<><div className="quality-score"><strong>{q.overall_score}%</strong><span>Overall quality · {q.source}</span></div><div className="quality-grid"><Metric label="Completeness" value={q.completeness_score!=null?`${q.completeness_score}%`:"—"}/><Metric label="Validity" value={q.validity_score!=null?`${q.validity_score}%`:"—"}/><Metric label="Uniqueness" value={q.uniqueness_score!=null?`${q.uniqueness_score}%`:"—"}/><Metric label="Consistency" value={q.consistency_score!=null?`${q.consistency_score}%`:"—"}/><Metric label="Timeliness" value={q.timeliness_score!=null?`${q.timeliness_score}%`:"—"}/></div></>:<p>No quality assessment has been recorded.</p>}
    </section>

    <section className="panel"><h2>Quality expectations</h2><p className="muted">{quality?.engine_mode==="real"?"The mapped TestGen test suite is the execution source. AI Data Steward converts failures into guided stewardship work.":"TestGen discovers patterns and candidate checks. The steward decides which expectations should become governed rules."}</p>{quality?.rules?.length?quality.rules.map(r=><div className="rule" key={r.id}><div><b>{r.plain_language_rule}</b><span>{friendlyType(r.rule_type)} · {r.status}</span>{r.latest_result&&<small>{r.latest_result.failed_count||0} failed in the latest run</small>}</div><div className="button-row mini">{r.status==="PROPOSED"&&<><button className="primary" onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"APPROVED"})}),"Quality expectation approved.")}>Approve</button><button onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"REJECTED"})}),"Quality expectation rejected.")}>Reject</button></>}</div></div>):<p>Run an assessment to generate suggested expectations.</p>}</section>

    <section className="panel"><h2>Quality issues requiring a stewardship decision</h2><p className="muted">Technical findings become understandable human work. A failed check is not automatically treated as bad data.</p>{openIssues.length===0&&<div className="empty">No unresolved quality issues.</div>}{openIssues.map(i=><div className={`quality-issue severity-${i.severity.toLowerCase()}`} key={i.id}><div className="task-head"><div><div className="eyebrow">{i.source} · {i.issue_type.replaceAll("_"," ")}</div><h3>{i.title}</h3></div><span className="priority">{i.severity}</span></div><p>{i.description}</p>{i.failed_count!=null&&<p><b>{i.failed_count.toLocaleString()}</b> affected records</p>}{i.details?.sample_values&&<div className="sample-values"><b>Example values</b><span>{i.details.sample_values.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<button className="primary" onClick={()=>{setSelectedQualityIssueId(i.id);setDecisionIssue(i);setNotes("");window.setTimeout(()=>document.getElementById("guided-investigation")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}}>Guide Me</button></div>)}</section>

    {decisionIssue&&<section id="guided-investigation" className="panel guide-panel"><div className="eyebrow">Guided investigation</div><h2>{decisionIssue.title}</h2><p><b>Step 1 — Understand what happened.</b> Review the evidence above. A failed check means the data did not meet an approved expectation; it does not by itself tell us why.</p><p><b>Step 2 — Make a stewardship decision.</b> Choose the explanation that best matches what you know. If you cannot determine it, escalate instead of guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","The data is incorrect"],["VALID_EXCEPTION","This is a valid exception"],["EXPECTATION_NEEDS_CHANGE","The quality expectation needs to change"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${decisionIssue.id}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Decision recorded: ${label}.`).then(()=>{setDecisionIssue(null);setSelectedQualityIssueId(null)})}>{label}</button>)}</div></section>}
  </>;
}

function PublicationPanel({asset,userEmail,doAction}) {
  return <section className="panel"><div className="eyebrow">Enterprise Catalog</div><h2>Publication readiness</h2><p>The publication validator knows the catalog profile. The steward only sees what needs to be completed.</p>{asset.readiness.checks.filter(c=>c.required).map(c=><div className="readiness-row" key={c.key}><span className={c.complete?"ok":"warn"}>{c.complete?"✓":"!"}</span><div><b>{c.title}</b><small>{c.complete?"Ready for publication":c.guidance}</small></div></div>)}<div className="lifecycle">{["DRAFT","IN_REVIEW","APPROVED","PUBLISHED"].map(s=><div key={s} className={asset.publication.status===s?"life current":"life"}>{s.replace("_"," ")}</div>)}</div><div className="button-row"><button className="primary" onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/submit`,userEmail,{method:"POST",body:JSON.stringify({comments:"Ready for review."})}),"Submitted for review.")}>Submit for review</button><button onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/approve`,userEmail,{method:"POST",body:JSON.stringify({comments:"Approved."})}),"Approved and immutable release created.")}>Approve</button><button onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published to the configured catalog adapter.")}>Publish</button></div></section>;
}

function ReviewQueue({assets,userEmail,doAction,onOpen}) { const review=assets.filter(a=>["IN_REVIEW","APPROVED","NEEDS_UPDATE"].includes(a.publication.status)); return <><h1>Review Queue</h1><p className="lead">Assets waiting for governance approval or enterprise publication.</p>{review.length===0&&<div className="empty">Nothing is waiting for review.</div>}{review.map(a=><div className="review-row" key={a.asset.asset_id}><div><b>{a.asset.name}</b><span>{a.readiness.score}% governance readiness · {a.quality?.overall_score??"—"}% quality</span></div><Status value={a.publication.status}/><div className="button-row"><button onClick={()=>onOpen(a.asset.asset_id)}>Inspect</button>{a.publication.status==="IN_REVIEW"&&<><button onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/reject`,userEmail,{method:"POST",body:JSON.stringify({comments:"Please address the remaining governance questions."})}),"Returned for changes.")}>Return</button><button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/approve`,userEmail,{method:"POST",body:JSON.stringify({comments:"Approved."})}),"Approved.")}>Approve</button></>}{a.publication.status==="APPROVED"&&<button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published.")}>Publish</button>}</div></div>)}</> }

function PublicationHistory({assets,selectedAssetId,setSelectedAssetId,userEmail}) { const [history,setHistory]=useState(null); useEffect(()=>{if(selectedAssetId)api(`/assets/${selectedAssetId}/history`,userEmail).then(setHistory)},[selectedAssetId,userEmail]); return <><h1>Publication History</h1><p className="lead">Approved releases are immutable snapshots. DCAT JSON-LD is generated only when the release crosses the publication boundary.</p><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select><div className="two-col"><section className="panel"><h2>Audit timeline</h2>{history?.events?.length?history.events.map(e=><div className="timeline" key={e.id}><b>{e.event_type.replaceAll("_"," ")}</b><span>{e.from_status||"—"} → {e.to_status||"—"}</span><small>{e.created_at}</small></div>):<p>No events yet.</p>}</section><section className="panel"><h2>Immutable releases</h2>{history?.releases?.length?history.releases.map(r=><details key={r.id}><summary>Release v{r.version_number} {r.published_at?"· Published":"· Approved"}</summary><p><b>Snapshot hash:</b> {r.snapshot_hash}</p>{r.ckan_name&&<p><b>Catalog name:</b> {r.ckan_name}</p>}{r.publication_result?.dcat_payload&&<><p><b>Generated DCAT JSON-LD</b></p><pre>{JSON.stringify(r.publication_result.dcat_payload,null,2)}</pre></>}</details>):<p>No releases yet.</p>}</section></div></> }

function Metric({label,value}) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }
function Status({value}) { return <span className={`status status-${(value||"").toLowerCase()}`}>{(value||"").replaceAll("_"," ")}</span> }
function friendlyType(value){return (value||"").replaceAll("_"," ").toLowerCase().replace(/\b\w/g,m=>m.toUpperCase())}

createRoot(document.getElementById("root")).render(<App/>);
