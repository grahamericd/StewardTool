import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearAccessToken, getAccessToken, publicApi, setAccessToken, setDemoMode } from "./api";
import "./styles.css";

const USERS = { Steward: "steward@demo.gov", "Ground Zero": "groundzero@demo.gov", Approver: "approver@demo.gov", "Org Admin": "admin@demo.gov", "Enterprise Admin": "enterprise@demo.gov" };
const LANDSCAPE_SESSION_KEY = "ai_data_steward_landscape_session";
const PRIMARY_NAV = ["Steward Home", "My Information", "Business Landscape", "Systems inventory", "Relationship Builder", "Discover Information", "My Next Steps"];
const REVIEW_NAV = ["Review Queue", "Publishing History"];
const ADMIN_NAV = ["User Administration"];

// One definition of where a task is worked on. This lived in three places and
// two of them sent description and location tasks to the Governance guide,
// which has no step for them, so the guided task never started.
const UNDERSTAND_TASK_TYPES = ["business_definition","theme","keywords","update_frequency","contact","review_change_purpose"];
const LOCATION_TASK_TYPES = ["has_resource","authoritative_source","review_change_locations","review_change_official_source","landscape_official_source"];

export function routeForTask(task){
  if(!task) return null;
  if(task.task_type==="landscape_submit_for_review"){
    return {tab:"Share & Publish",guided:task,qualityIssueId:null};
  }
  if(task.source_type==="QUALITY_ISSUE" && task.source_reference){
    return { tab:"Can This Information Be Trusted?", guided:null, qualityIssueId:Number(task.source_reference) };
  }
  const route = { tab:"Governance", guided:task, qualityIssueId:null };
  // The scheduled review opens the broad review questionnaire. Tasks created
  // by that review must instead route to their focused correction workflow.
  if(task.source_type==="PERIODIC_REVIEW" || task.task_type==="periodic_review" || task.task_type==="review_change_active_use") route.tab="Review & Maintain";
  else if(task.governance_domain==="QUALITY") route.tab="Can This Information Be Trusted?";
  else if(["METADATA","DESCRIPTION"].includes(task.governance_domain) || UNDERSTAND_TASK_TYPES.includes(task.task_type)) route.tab="Help Others Understand It";
  else if(LOCATION_TASK_TYPES.includes(task.task_type)) route.tab="Where It Lives";
  return route;
}

function NextStepCallout({title, body}) {
  return <div className="education strong"><b>{title}</b><p>{body}</p></div>;
}

function BrandLogo({dark = false}) {
  return (
    <img
      className="brand-logo"
      src={dark ? "/clearpath-data-logo-horizontal-dark.svg" : "/clearpath-data-logo-horizontal-light.svg"}
      alt="ClearPath Data logo"
    />
  );
}

class ErrorBoundary extends React.Component {
  constructor(props){ super(props); this.state={error:null}; }
  static getDerivedStateFromError(error){ return {error}; }
  componentDidCatch(error,info){ console.error("AI Data Steward failed to render",error,info); }
  render(){
    if(!this.state.error) return this.props.children;
    return <div className="auth-shell"><div className="auth-card">
      <div className="brand"><BrandLogo /></div>
      <h1>This page could not be displayed</h1>
      <p>Nothing you entered has been lost. Reload the page to continue; if it keeps happening, tell your administrator what you were doing.</p>
      <button onClick={()=>window.location.reload()}>Reload</button>
    </div></div>;
  }
}

function App() {
  const [page, setPage] = useState("Steward Home");
  const [userLabel, setUserLabel] = useState("Steward");
  const [authConfig, setAuthConfig] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [signedIn, setSignedIn] = useState(Boolean(getAccessToken()));
  const [me, setMe] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [assets, setAssets] = useState([]);
  const [systems, setSystems] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [discoverySummary, setDiscoverySummary] = useState(null);
  const [landscapeSessions, setLandscapeSessions] = useState([]);
  const [landscapeScope, setLandscapeScope] = useState(() => {
    try {
      const raw = localStorage.getItem(LANDSCAPE_SESSION_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  });
  const [selectedAssetId, setSelectedAssetId] = useState(null);
  const [assetTab, setAssetTab] = useState("Overview");
  const [selectedQualityIssueId, setSelectedQualityIssueId] = useState(null);
  const [guidedTask, setGuidedTask] = useState(null);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState("info");
  const [busy, setBusy] = useState(false);
  const [navOpen,setNavOpen]=useState(false);
  const inFlight = useRef(false);
  const userEmail = authConfig?.mode==="demo" ? USERS[userLabel] : null;
  const canReview = ["APPROVER","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(me?.role);
  const canAdministerUsers = ["ORG_ADMIN","ENTERPRISE_ADMIN"].includes(me?.role);
  const canConstructLandscape = ["STEWARD","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(me?.role);
  const primaryNavigation = canConstructLandscape
    ? PRIMARY_NAV
    : PRIMARY_NAV.filter(item=>!["Discover Information","My Next Steps"].includes(item));

  const fail = useCallback(text=>{ setMessageTone("error"); setMessage(text); },[]);
  const succeed = useCallback(text=>{ setMessageTone("success"); setMessage(text||""); },[]);

  useEffect(()=>{
    publicApi("/auth/config")
      .then(cfg=>{
        setAuthConfig(cfg);
        setDemoMode(cfg.mode==="demo");
        if(cfg.mode==="demo") setSignedIn(true);
        else setSignedIn(Boolean(getAccessToken()));
      })
      .catch(e=>fail(e.message))
      .finally(()=>setAuthReady(true));
  },[fail]);

  async function refresh() {
    const [meData, dash, assetData, systemData, taskData, discoveryData, sessionData] = await Promise.all([
      api("/me", userEmail), api("/dashboard", userEmail), api("/assets", userEmail), api("/systems", userEmail), api("/tasks", userEmail), api("/discovery/summary", userEmail), api("/discovery/sessions", userEmail)
    ]);
    setMe(meData); setDashboard(dash); setAssets(assetData); setSystems(systemData); setTasks(taskData); setDiscoverySummary(discoveryData); setLandscapeSessions(Array.isArray(sessionData) ? sessionData : []);
    const savedId = localStorage.getItem(LANDSCAPE_SESSION_KEY);
    if (savedId) {
      const saved = (sessionData||[]).find(session => Number(session.id) === Number(savedId));
      if (saved) setLandscapeScope(saved);
      else {
        setLandscapeScope(null);
        localStorage.removeItem(LANDSCAPE_SESSION_KEY);
      }
    } else if ((sessionData||[]).length) {
      const latest = sessionData[0];
      setLandscapeScope(latest);
      localStorage.setItem(LANDSCAPE_SESSION_KEY, String(latest.id));
    } else {
      setLandscapeScope(null);
      localStorage.removeItem(LANDSCAPE_SESSION_KEY);
    }
    if (!selectedAssetId && assetData.length) setSelectedAssetId(assetData[0].asset.asset_id);
    return { tasks: taskData, assets: assetData };
  }
  // A 401 anywhere means the session ended. Without this the user stayed in the
  // signed-in shell with stale data and every later action failed.
  const handleExpiredSession = useCallback(()=>{
    if(authConfig?.mode==="demo") return false;
    clearAccessToken();
    setSignedIn(false);
    setMe(null);
    fail("Your session has ended. Please sign in again.");
    return true;
  },[authConfig,fail]);

  useEffect(() => {
    if(!authReady || !signedIn) return;
    refresh().catch(e=>{
      if(e.status===401 && handleExpiredSession()) return;
      fail(e.message);
    });
  }, [userEmail,authReady,signedIn]);
  const selectedAsset = useMemo(() => assets.find(a => a.asset.asset_id === selectedAssetId), [assets, selectedAssetId]);

  function openReviewContext(asset) {
    if (!asset) return;
    const status = asset?.publication?.status;
    setSelectedAssetId(asset.asset.asset_id);
    setSelectedQualityIssueId(null);
    setGuidedTask(null);
    setAssetTab(status === "NEEDS_UPDATE" ? "Review & Maintain" : "Share & Publish");
    setPage("Information Details");
  }

  // Returns whether the action succeeded, so callers no longer advance a wizard
  // to its "complete" step after a failed save. The in-flight guard makes a
  // second click a no-op rather than a second publish.
  async function doAction(fn, successMessage) {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    try {
      setMessage("");
      await fn();
      await refresh();
      succeed(successMessage);
      return true;
    } catch (e) {
      if (!(e.status === 401 && handleExpiredSession())) fail(e.message);
      return false;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function handleLogin(email,password){
    setMessage("");
    const result=await publicApi("/auth/login",{method:"POST",body:JSON.stringify({email,password})});
    setAccessToken(result.access_token);
    // The sign-in effect performs the initial load; calling refresh() here too
    // issued every request twice and let the slower response win.
    setSignedIn(true);
  }

  async function handleLogout(){
    try{ await api("/auth/logout",null,{method:"POST"}); }catch{}
    clearAccessToken();
    localStorage.removeItem(LANDSCAPE_SESSION_KEY);
    setSignedIn(false);
    setMe(null); setDashboard(null); setAssets([]); setSystems([]); setTasks([]);
    // Leaving these set showed the previous user's asset to the next person who
    // signed in on the same browser.
    setSelectedAssetId(null); setSelectedQualityIssueId(null); setGuidedTask(null);
    setAssetTab("Overview");
    setPage("Steward Home");
    setMessage("");
  }

  async function handleCreateLandscape({ name, businessDomain, stewardOwner, purpose }) {
    const payload = {
      title: name.trim(),
      status: "ACTIVE",
      summary: purpose.trim() || "Ground Zero landscape scope",
      context_snapshot: {
        landscape_name: name.trim(),
        business_domain: businessDomain.trim() || null,
        steward_owner: stewardOwner.trim() || null,
        purpose: purpose.trim() || null,
        business_first: true,
        is_ground_zero_scope: true,
        created_via: "new_landscape_flow",
      },
    };
    const created = await api("/discovery/sessions", userEmail, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setLandscapeScope(created);
    setLandscapeSessions(prev => [created, ...prev.filter(session => session.id !== created.id)]);
    localStorage.setItem(LANDSCAPE_SESSION_KEY, String(created.id));
    return created;
  }

  async function handleResetLandscape() {
    localStorage.removeItem(LANDSCAPE_SESSION_KEY);
    setLandscapeScope(null);
    setPage("Steward Home");
  }

  async function handlePasswordChange(currentPassword,newPassword){
    await api("/auth/change-password",null,{method:"POST",body:JSON.stringify({current_password:currentPassword,new_password:newPassword})});
    await refresh();
    setMessage("Password changed.");
  }

  async function handleLandscapeHandoffStage(stage){
    if(stage.page==="Discover Information"){
      setPage("Discover Information");
      return;
    }
    if(stage.page==="Review Queue"){
      try{await refresh()}catch(e){fail(e.message)}
      setPage("Review Queue");
      return;
    }
    if(!stage.asset_id) return;
    setSelectedAssetId(Number(stage.asset_id));
    setSelectedQualityIssueId(null);
    setAssetTab(stage.tab||"Overview");
    setGuidedTask(stage.task_id?tasks.find(task=>task.id===stage.task_id)||null:null);
    setPage("Information Details");
    try{
      const refreshed=await refresh();
      if(stage.task_id) setGuidedTask(refreshed?.tasks?.find(task=>task.id===stage.task_id)||null);
    }catch(e){fail(e.message)}
  }

  if(!authReady) return <div className="auth-shell"><div className="auth-card"><div className="brand"><BrandLogo /></div><p>Loading secure sign-in…</p></div></div>;

  if(authConfig?.mode!=="demo" && !signedIn){
    return <LoginPage onLogin={handleLogin} message={message} setMessage={setMessage}/>;
  }

  if(authConfig?.mode!=="demo" && me?.must_change_password){
    return <ChangePasswordPage me={me} minLength={authConfig?.password_min_length||12} onChangePassword={handlePasswordChange} onLogout={handleLogout} message={message} setMessage={setMessage}/>;
  }

  return <div className={`app${navOpen?" nav-open":""}`}>
    <aside onClick={e=>{if(e.target.closest("button")) setNavOpen(false)}}>
      <div className="brand"><BrandLogo dark /></div>
      <div className="tagline">Clear path from discovery to governance.</div>

      <div className="nav-section">
        <div className="nav-label">Your stewardship</div>
        <nav>{primaryNavigation.map(n => {
          const active = page===n || (page==="Information Details" && n==="My Information");
          return <button key={n} onClick={() => setPage(n)} className={active?"active":""}>{n}</button>;
        })}</nav>
      </div>

      {canReview&&<div className="nav-section reviewer-nav">
        <div className="nav-label">Review & publishing</div>
        <nav>{REVIEW_NAV.map(n => <button key={n} onClick={() => setPage(n)} className={page===n?"active":""}>{n}</button>)}</nav>
      </div>}

      {canAdministerUsers&&<div className="nav-section admin-nav">
        <div className="nav-label">Administration</div>
        <nav>{ADMIN_NAV.map(n => <button key={n} onClick={() => setPage(n)} className={page===n?"active":""}>{n}</button>)}</nav>
      </div>}

      <div className="aside-guidance">
        <b>Not sure where to start?</b>
        <p>Open My Next Steps. ClearPath Data will guide you to the work that needs attention.</p>
      </div>
    </aside>
    <main className={busy?"is-busy":undefined} aria-busy={busy||undefined}>
      <header>
        <button className="mobile-nav-toggle" aria-label={navOpen?"Close navigation":"Open navigation"} onClick={()=>setNavOpen(!navOpen)}>{navOpen?"Close":"Menu"}</button>
        <div><div className="org">{me?.organization?.name || "Loading..."}</div><div className="role">{me?.role || ""}</div><small className="role-context">{roleResponsibility(me?.role)}</small></div>
        {authConfig?.mode==="demo"
          ? <label className="role-switch demo-control"><span>Demo role</span><select value={userLabel} onChange={e=>{setUserLabel(e.target.value);setPage("Steward Home");setSelectedQualityIssueId(null);setGuidedTask(null);setAssetTab("Overview")}}>{Object.keys(USERS).map(u=><option key={u}>{u}</option>)}</select><small>Changing roles starts a new work context.</small></label>
          : <div className="signed-in-user"><div><b>{me?.user?.display_name||me?.user?.email}</b><small>{me?.user?.email}</small></div><button onClick={handleLogout}>Sign out</button></div>}
      </header>
      {message && <div className={`message message-${messageTone}`} role="status" aria-live="polite">{message}</div>}
      {page === "Steward Home" && <StewardHome role={me?.role} dashboard={dashboard} assets={assets} systems={systems} tasks={tasks} discoverySummary={discoverySummary} onboardingKey={me?`${me.organization?.id||"org"}:${me.user?.id||me.user?.email}`:userEmail||"demo"} landscapeScope={landscapeScope} onCreateLandscape={handleCreateLandscape} onResetLandscape={handleResetLandscape} onTask={task=>{
        const route=routeForTask(task);
        setSelectedAssetId(task.asset_id);
        setGuidedTask(route.guided);
        setAssetTab(route.tab);
        setSelectedQualityIssueId(route.qualityIssueId);
        setPage("Information Details");
      }} onInventory={()=>setPage("My Information")} onDiscover={()=>setPage("Discover Information")} onAllTasks={()=>setPage("My Next Steps")} />}
      {page === "My Information" && <Dashboard dashboard={dashboard} assets={assets} onOpen={id=>{setSelectedAssetId(id);setPage("Information Details")}} />}
      {page === "Business Landscape" && <BusinessLandscape role={me?.role} systems={systems} userEmail={userEmail} landscapeScope={landscapeScope} onDiscover={()=>setPage("Discover Information")} onRelationships={()=>setPage("Relationship Builder")} onHandoffStage={handleLandscapeHandoffStage} />}
      {page === "Systems inventory" && <BusinessLandscape role={me?.role} systems={systems} userEmail={userEmail} landscapeScope={landscapeScope} onDiscover={()=>setPage("Discover Information")} onRelationships={()=>setPage("Relationship Builder")} onHandoffStage={handleLandscapeHandoffStage} initialTab="Systems inventory" />}
      {page === "Relationship Builder" && <RelationshipBuilder role={me?.role} userEmail={userEmail} onBusinessLandscape={()=>setPage("Business Landscape")} />}
      {page === "Discover Information" && canConstructLandscape && <Discover systems={systems} userEmail={userEmail} onDone={async id=>{await refresh();setSelectedAssetId(id);setPage("Information Details")}} />}
      {page === "My Next Steps" && <Inbox tasks={tasks} assets={assets} discoverySummary={discoverySummary} onDiscover={()=>setPage("Discover Information")} onGuide={task=>{
        const route=routeForTask(task);
        setSelectedAssetId(task.asset_id);
        setGuidedTask(route.guided);
        setAssetTab(route.tab);
        setSelectedQualityIssueId(route.qualityIssueId);
        setPage("Information Details");
      }} />}
      {page === "Information Details" && <Asset360 asset={selectedAsset} assets={assets} systems={systems} tasks={tasks} role={me?.role} userEmail={userEmail} onDiscover={()=>setPage("Discover Information")} onNextSteps={()=>setPage("My Next Steps")} selectedAssetId={selectedAssetId} setSelectedAssetId={id=>{setSelectedAssetId(id);setSelectedQualityIssueId(null);setGuidedTask(null);setAssetTab("Overview")}} doAction={doAction} tab={assetTab} setTab={setAssetTab} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} guidedTask={guidedTask} setGuidedTask={setGuidedTask} />}
      {page === "Review Queue" && <ReviewQueue assets={assets} role={me?.role} userEmail={userEmail} doAction={doAction} onOpen={openReviewContext} />}
      {page === "Publishing History" && <PublicationHistory assets={assets} selectedAssetId={selectedAssetId} setSelectedAssetId={setSelectedAssetId} userEmail={userEmail} />}
      {page === "User Administration" && canAdministerUsers && <UserAdministration userEmail={userEmail} currentUserId={me?.user?.id} authMode={authConfig?.mode} />}
    </main>
  </div>;
}


function LoginPage({onLogin,message,setMessage}){
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [busy,setBusy]=useState(false);

  async function submit(e){
    e.preventDefault();
    if(!email.trim()||!password) return;
    setBusy(true); setMessage("");
    try{ await onLogin(email.trim(),password); }
    catch(err){ setMessage(err.message); }
    finally{ setBusy(false); }
  }

  return <div className="auth-shell">
    <div className="auth-card">
      <div className="brand"><BrandLogo /></div>
      <div className="eyebrow">Secure sign-in</div>
      <h1>Welcome back</h1>
      <p className="lead">Sign in with the account provided by your organization.</p>
      {message&&<div className="message">{message}</div>}
      <form className="auth-form" onSubmit={submit}>
        <label>Email<input type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} required/></label>
        <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>
        <button className="primary" disabled={busy}>{busy?"Signing in…":"Sign in"}</button>
      </form>
      <p className="auth-help">If you cannot sign in, contact the person who administers ClearPath Data for your organization.</p>
    </div>
  </div>;
}

function ChangePasswordPage({me,minLength,onChangePassword,onLogout,message,setMessage}){
  const [currentPassword,setCurrentPassword]=useState("");
  const [newPassword,setNewPassword]=useState("");
  const [confirm,setConfirm]=useState("");
  const [busy,setBusy]=useState(false);

  async function submit(e){
    e.preventDefault();
    setMessage("");
    if(newPassword.length<minLength){setMessage(`New password must be at least ${minLength} characters.`);return;}
    if(newPassword!==confirm){setMessage("New passwords do not match.");return;}
    setBusy(true);
    try{await onChangePassword(currentPassword,newPassword);}
    catch(err){setMessage(err.message);}
    finally{setBusy(false);}
  }

  return <div className="auth-shell">
    <div className="auth-card">
      <div className="brand"><BrandLogo /></div>
      <div className="eyebrow">Account security</div>
      <h1>Change your password</h1>
      <p className="lead">{me?.user?.display_name}, choose a password you do not use for another account.</p>
      {message&&<div className="message">{message}</div>}
      <form className="auth-form" onSubmit={submit}>
        <label>Current password<input type="password" autoComplete="current-password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} required/></label>
        <label>New password<input type="password" autoComplete="new-password" minLength={minLength} value={newPassword} onChange={e=>setNewPassword(e.target.value)} required/><small>At least {minLength} characters.</small></label>
        <label>Confirm new password<input type="password" autoComplete="new-password" value={confirm} onChange={e=>setConfirm(e.target.value)} required/></label>
        <button className="primary" disabled={busy}>{busy?"Saving…":"Change password"}</button>
      </form>
      <button className="link-button" onClick={onLogout}>Sign out instead</button>
    </div>
  </div>;
}


function StewardHome({role,dashboard,assets,systems,tasks,discoverySummary,onboardingKey,onTask,onInventory,onDiscover,onAllTasks,landscapeScope,onCreateLandscape,onResetLandscape}) {
  const introStorageKey=`steward_intro_complete:${onboardingKey||"unknown"}`;
  const [showIntro,setShowIntro]=useState(()=>localStorage.getItem(introStorageKey)!=="yes");
  useEffect(()=>{setShowIntro(localStorage.getItem(introStorageKey)!=="yes")},[introStorageKey]);
  const priorityOrder={HIGH:0,MEDIUM:1,LOW:2};
  const work=[...(tasks||[])].sort((a,b)=>(priorityOrder[a.priority]??9)-(priorityOrder[b.priority]??9));
  const now=work.filter(t=>(t.bucket||"NOW")==="NOW");
  const waiting=work.filter(t=>(t.bucket||"NOW")==="WAITING");
  const next=now[0];
  const assetCount=assets?.length||0;
  const groundZero=Boolean(discoverySummary?.ground_zero);
  const hasLandscapeScope = Boolean(landscapeScope);
  const canConstruct=["STEWARD","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const isApprover=role==="APPROVER";
  const isAdmin=["ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const landscapeName = landscapeScope?.title || landscapeScope?.context_snapshot?.landscape_name || "Your landscape";
  const qualityTasks=work.filter(t=>t.source_type==="QUALITY_ISSUE").length;
  const governanceTasks=work.filter(t=>t.source_type!=="QUALITY_ISSUE").length;
  const groundZeroMilestones=[
    {title:"1. Scope", body:"Define the business area and what you are trying to map."},
    {title:"2. Business layer", body:"Capture business functions, concepts, and processes."},
    {title:"3. Systems", body:"Identify the tools and applications that support the work."},
    {title:"4. Relationships", body:"Connect business activities to systems and information."},
    {title:"5. Validate", body:"Check completeness and continue to the next stewardship step."},
  ];
  const progressMilestones = [
    {title:"Scope", complete: assetCount > 0 || Boolean(discoverySummary?.ground_zero), hint:"Start with a known business area or source."},
    {title:"Business layer", complete: assetCount > 0, hint:"Capture the business concepts and work being supported."},
    {title:"Systems", complete: (systems||[]).length > 0, hint:"Add the tools and applications that support the work."},
    {title:"Relationships", complete: (assets||[]).some(a => (a.resources||[]).length > 0 || (a.asset?.business_owner || a.asset?.data_steward)), hint:"Connect business meaning to the places where the information lives."},
    {title:"Validate", complete: Boolean(dashboard?.average_governance_readiness && dashboard.average_governance_readiness >= 25), hint:"Confirm completeness and move to stewardship status."},
  ];

  const responsibilities=[
    ["Understand","Know what information exists, what it means, where it lives, and who is responsible."],
    ["Govern","Confirm ownership, classification, retention, and other stewardship decisions."],
    ["Trust","Review quality findings and make evidence-based decisions without guessing."],
    ["Maintain","Keep information current as systems, policies, quality, and business needs change."],
    ["Publish","Help information move to approval and publication when it is ready."]
  ];

  if (!hasLandscapeScope) {
    if(!canConstruct) return <section className="panel ground-zero-panel"><div className="eyebrow">Landscape governance</div><h1>No landscape is ready for review</h1><p className="lead">A steward must establish the business scope before readiness and governance review can begin.</p></section>;
    return <LandscapeScopeStart onCreateLandscape={onCreateLandscape} onDiscover={onDiscover} showIntro={showIntro} setShowIntro={setShowIntro} introStorageKey={introStorageKey} />;
  }

  if (groundZero) {
    return <>
      {showIntro&&<section className="welcome-panel">
        <div className="eyebrow">New to data stewardship?</div>
        <h1>You do not need to be a governance expert.</h1>
        <p className="lead">Your role is to help make sure important information is understood, responsibly governed, and trustworthy. AI Data Steward will show you what needs attention, explain why it matters, and guide you through the decision.</p>
        <div className="responsibility-grid">{responsibilities.map(([title,text],idx)=><div className="responsibility-card" key={title}><span>{idx+1}</span><div><b>{title}</b><p>{text}</p></div></div>)}</div>
        <div className="callout"><b>What you are not expected to do</b><p>You do not need to know every governance rule, make legal or security decisions alone, or guess when you are unsure. Your job is to recognize what needs attention, bring the right context together, make the decisions you are qualified to make, and involve the right expert when needed.</p></div>
        <div className="button-row"><button className="primary" onClick={()=>{localStorage.setItem(introStorageKey,"yes");setShowIntro(false)}}>Start discovering my landscape</button><button onClick={onDiscover}>Help me identify information</button></div>
      </section>}

      <section className="panel ground-zero-panel">
        <div className="eyebrow">Ground Zero</div>
        <h1>Build your data landscape</h1>
        <p className="lead">Before you can govern information, you need to understand what your organization has. Start with something you already know about: a system, spreadsheet, shared folder, report, email flow, application, or any other place where work happens.</p>
        <div className="ground-zero-options">
          <div><b>Why this comes first</b><span>AI Data Steward helps you organize business knowledge into a shared landscape before you move into ownership, trust, and governance decisions.</span></div>
          <div><b>What to do next</b><span>Describe one familiar place your team uses to do work. We will turn that starting point into a candidate landscape record and guide the next question.</span></div>
        </div>
        <div className="ground-zero-roadmap">
          {groundZeroMilestones.map((milestone, index)=><div key={milestone.title} className="ground-zero-roadmap-item">
            <span>{index + 1}</span>
            <div>
              <b>{milestone.title}</b>
              <small>{milestone.body}</small>
            </div>
          </div>)}
        </div>
        <div className="next-milestones">
          <div className="next-milestone"><span>1</span><div><b>Confirm the official source</b><small>Decide which location the organization should rely on when versions differ.</small></div></div>
          <div className="next-milestone"><span>2</span><div><b>Clarify business meaning</b><small>Describe what the information helps the team do and who it supports.</small></div></div>
          <div className="next-milestone"><span>3</span><div><b>Review trust and readiness</b><small>Check quality findings, owner context, and readiness before publishing.</small></div></div>
        </div>
        <div className="education strong"><b>What happens next</b><p>Once one familiar source is identified, the app will guide you from a working record into a more trusted, governed definition and then into review or publication.</p></div>
        <div className="button-row"><button className="primary" onClick={onDiscover}>Start discovering my landscape</button><button onClick={()=>setShowIntro(true)}>What is my role?</button></div>
      </section>
    </>;
  }

  return <>
    {(isApprover||isAdmin)&&<section className="education strong role-landscape-guidance"><b>{isApprover?"Governance and readiness view":"Landscape health and oversight"}</b><p>{isApprover?"Review completeness, relationships, and submitted governance evidence. Landscape construction remains with the steward.":"Monitor completeness and unresolved gaps across the organization. Administrators may intervene when needed, but accountable stewards should normally maintain the business map."}</p></section>}
    {showIntro&&<section className="welcome-panel">
      <div className="eyebrow">New to data stewardship?</div>
      <h1>You do not need to be a governance expert.</h1>
      <p className="lead">Your role is to help make sure important information is understood, responsibly governed, and trustworthy. AI Data Steward will show you what needs attention, explain why it matters, and guide you through the decision.</p>
      <div className="responsibility-grid">{responsibilities.map(([title,text],idx)=><div className="responsibility-card" key={title}><span>{idx+1}</span><div><b>{title}</b><p>{text}</p></div></div>)}</div>
      <div className="callout"><b>What you are not expected to do</b><p>You do not need to know every governance rule, make legal or security decisions alone, or guess when you are unsure. Your job is to recognize what needs attention, bring the right context together, make the decisions you are qualified to make, and involve the right expert when needed.</p></div>
      <div className="button-row"><button className="primary" onClick={()=>{localStorage.setItem(introStorageKey,"yes");setShowIntro(false)}}>Show me what needs my attention</button><button onClick={onDiscover}>Help me identify information</button></div>
    </section>}

    <div className="steward-home-head">
      <div><div className="eyebrow">Steward Home</div><h1>{hasLandscapeScope ? "What needs your attention" : "Tell us about the work you support"}</h1><p className="lead">{hasLandscapeScope ? "Work the highest-value item first. When you are unsure, choose “I’m not sure” rather than guessing." : "Start with a program, service, or responsibility you already know. We will guide you from there."}</p></div>
      <button onClick={()=>setShowIntro(true)}>What is my role?</button>
    </div>

    {hasLandscapeScope && <section className="panel landscape-scope-panel">
      <div className="eyebrow">Current area of work</div>
      <div className="scope-header-row">
        <div>
          <h2>{landscapeName}</h2>
          <p className="lead">{landscapeScope?.context_snapshot?.business_domain || "Business domain not yet recorded"} · {landscapeScope?.context_snapshot?.steward_owner || "Steward owner pending"}</p>
        </div>
        {canConstruct&&<button onClick={onResetLandscape}>Map another area of work</button>}
      </div>
      <p>{landscapeScope?.context_snapshot?.purpose || "Describe the purpose or use case for this landscape so the work remains grounded in business intent."}</p>
    </section>}

    {(assetCount > 0 || groundZero) && <section className="panel ground-zero-panel">
      <div className="eyebrow">Landscape build progress</div>
      <h2>Milestones for your data landscape</h2>
      <p className="lead">Use this as your working checklist. The goal is to move from a familiar source to a connected, useful business view, then continue into stewardship.</p>
      <div className="ground-zero-roadmap">
        {progressMilestones.map((milestone,index)=><div key={milestone.title} className={milestone.complete ? "ground-zero-roadmap-item active" : "ground-zero-roadmap-item"}>
          <span>{index + 1}</span>
          <div>
            <b>{milestone.title}</b>
            <small>{milestone.complete ? "Complete" : milestone.hint}</small>
          </div>
        </div>)}
      </div>
      <div className="button-row">{canConstruct?<button className="primary" onClick={onDiscover}>Continue building my landscape</button>:<button className="primary" onClick={onInventory}>Review governed information</button>}</div>
    </section>}

    {assetCount > 0 && <section className="panel journey-bridge">
      <div className="eyebrow">From discovery to stewardship</div>
      <h2>Your first landscape record is in motion.</h2>
      <p className="lead">The next steps are intentional: confirm the official source, define the business meaning, and review the trust signals before anyone treats this as a trusted asset.</p>
      <div className="journey-next-list">
        <div><span>1</span><div><b>Pick the official source</b><small>Choose the location the organization should rely on when versions differ.</small></div></div>
        <div><span>2</span><div><b>Clarify the business meaning</b><small>Describe what the information helps the team do and who it supports.</small></div></div>
        <div><span>3</span><div><b>Review trust and readiness</b><small>Check quality findings, ownership, and whether it is ready to be shared.</small></div></div>
      </div>
    </section>}

    <NextStepCallout title="What to do next" body={groundZero ? "Start with one familiar system, screen, file, folder, report, or email flow and identify the business information it contains." : "Work from the top of the list and resolve the highest-priority item before moving to the next one."} />

    <div className="metrics four">
      <Metric label="Information assets" value={assetCount}/>
      <Metric label="Needs your attention" value={now.length}/>
      <Metric label="Waiting on others" value={waiting.length}/>
      <Metric label="Stewardship progress" value={`${dashboard?.average_governance_readiness??0}%`}/>
    </div>

    {next ? <section className="panel start-here">
      <div className="eyebrow">Start here</div>
      <h2>{next.title}</h2>
      <p><b>{next.asset_name}</b> · {responsibilityLabel(next)}</p>
      <div className="guided-task-grid">
        <div><b>Why this matters</b><p>{next.why_it_matters}</p></div>
        <div><b>What you should do</b><p>{next.recommended_action}</p></div>
        <div><b>What this responsibility means</b><p>{next.learn_text}</p></div>
      </div>
      <button className="primary" onClick={()=>onTask(next)}>{next.source_type==="QUALITY_ISSUE"?"Review findings":"Start guided task"}</button>
    </section> : assetCount===0 ? <section className="panel onboarding-start"><div className="eyebrow">Your first step</div><h2>Start by identifying one system or tool.</h2><p>Think of a system, spreadsheet, shared folder, inbox, or other place your team uses to do its work. We will help you turn that starting point into useful business information.</p><button className="primary" onClick={onDiscover}>Identify information</button></section> : <section className="panel success-panel"><h2>You are caught up.</h2><p>Nothing currently needs your attention. AI Data Steward will bring work back here when something changes.</p></section>}

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
        <div className={assetCount>0&&governanceTasks===0?"journey done":assetCount>0?"journey current":"journey"}><span>3</span><b>Govern</b><small>Classification, retention, accountability</small></div>
        <div className={assetCount>0&&qualityTasks===0?"journey done":assetCount>0?"journey current":"journey"}><span>4</span><b>Trust</b><small>Review evidence and quality</small></div>
        <div className="journey"><span>5</span><b>Publish & maintain</b><small>Approve, publish, and keep current</small></div>
      </div>
      <div className="button-row"><button onClick={onInventory}>View my information</button><button onClick={onDiscover}>Add information</button></div>
    </section>
  </>;
}

function LandscapeScopeStart({onCreateLandscape,onDiscover,showIntro,setShowIntro,introStorageKey}) {
  const [name,setName]=useState("");
  const [businessDomain,setBusinessDomain]=useState("");
  const [stewardOwner,setStewardOwner]=useState("");
  const [purpose,setPurpose]=useState("");
  const [busy,setBusy]=useState(false);

  async function submit(e){
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await onCreateLandscape({ name, businessDomain, stewardOwner, purpose });
      localStorage.setItem(introStorageKey, "yes");
      setShowIntro(false);
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel ground-zero-panel">
    <div className="eyebrow">Getting started</div>
    <h1>Tell us about the work you support</h1>
    <p className="lead">Think of a program, service, or responsibility your team handles. You do not need to know where every file lives or understand technical systems yet.</p>
    <div className="ground-zero-options">
      <div><b>What happens next</b><span>We will turn what you enter into a working map and ask simple questions about the people, information, and tools involved.</span></div>
      <div><b>It is fine not to know everything</b><span>Start with what is familiar. You can mark uncertain details and return to them later.</span></div>
    </div>
    <form className="landscape-form" onSubmit={submit}>
      <div className="two-col compact">
        <label>What should we call this area of work?<input value={name} onChange={e=>setName(e.target.value)} placeholder="e.g., Professional licensing" required /></label>
        <label>Which team or program does it belong to?<input value={businessDomain} onChange={e=>setBusinessDomain(e.target.value)} placeholder="e.g., Licensing, Finance, Child welfare" /></label>
      </div>
      <div className="two-col compact">
        <label>Who can help keep this information current?<input value={stewardOwner} onChange={e=>setStewardOwner(e.target.value)} placeholder="A person, role, or team is fine" /></label>
        <label>What does this work help people accomplish?<textarea rows="3" value={purpose} onChange={e=>setPurpose(e.target.value)} placeholder="For example: Review applications and issue professional licenses." /></label>
      </div>
      <div className="button-row">
        <button type="button" onClick={onDiscover}>Start with information I know</button>
        <button className="primary" type="submit" disabled={busy || !name.trim()}>{busy ? "Starting…" : "Start with this work"}</button>
      </div>
    </form>
  </section>;
}

function Dashboard({dashboard, assets, onOpen}) {
  if (!dashboard) return <p>Loading...</p>;
  return <>
    <h1>My Information</h1>
    <p className="lead">See the business information your organization has identified, what still needs attention, and whether it is ready to use and share.</p>
    <div className="metrics six">
      <Metric label="Systems we know about" value={dashboard.systems}/><Metric label="Information we know about" value={dashboard.assets}/><Metric label="Needs attention" value={dashboard.open_tasks}/><Metric label="Stewardship progress" value={`${dashboard.average_governance_readiness}%`}/><Metric label="Average information trust" value={dashboard.average_quality_score==null?"Not assessed yet":`${dashboard.average_quality_score}%`}/><Metric label="Document/content locations" value={dashboard.unstructured_resources}/>
    </div>
    <h2>Information</h2>
    <div className="grid">{assets.map(a=><div className="card" key={a.asset.asset_id}>
      <div className="eyebrow">{a.asset.business_domain || "Business information"}</div><h3>{a.asset.name}</h3><p>{a.asset.business_definition || "Definition needs review."}</p>
      <div className="status-line"><span>Stewardship progress</span><b>{a.readiness.score}%</b></div><div className="progress"><div style={{width:`${a.readiness.score}%`}} /></div>
      <div className="status-line"><span>Information trust</span><b>{a.quality?.overall_score != null ? `${a.quality.overall_score}%` : "Not assessed"}</b></div>
      <div className="status-line"><span>Open tasks</span><b>{a.task_summary.open}</b></div>
      <div className="status-line"><span>Publication</span><Status value={a.publication.status}/></div>
      <button className="primary" onClick={()=>onOpen(a.asset.asset_id)}>View details</button>
    </div>)}</div>
  </>;
}

function Inbox({tasks, assets, discoverySummary, onDiscover, onGuide}) {
  const rank = {HIGH:0, MEDIUM:1, LOW:2};
  const sorted = [...tasks].sort((a,b)=>(rank[a.priority]??9)-(rank[b.priority]??9));
  const groundZero = Boolean(discoverySummary?.ground_zero);
  return <>
    <h1>My Next Steps</h1><p className="lead">Start at the top. AI Data Steward will explain why each item matters and guide you to the right decision. If you are unsure, choose that option rather than guessing.</p>
    <div className="task-summary">{["HIGH","MEDIUM","LOW"].map(p=><Metric key={p} label={priorityLabel(p)} value={tasks.filter(t=>t.priority===p).length}/>)}</div>
    {groundZero ? <section className="panel ground-zero-panel"><div className="eyebrow">Ground Zero</div><h2>There is nothing to steward yet.</h2><p className="lead">This organization has not identified a meaningful information landscape. Begin by recording one familiar system or tool, then build the first bit of governed information around it.</p><button className="primary" onClick={onDiscover}>Identify a starting point</button></section> : sorted.length===0 && (assets?.length ? <EmptyState title="You’re caught up." text="AI Data Steward will bring work back here when something changes or needs review."/> : <section className="panel onboarding-start"><div className="eyebrow">Your first step</div><h2>Identify information your team uses.</h2><p>Start with a familiar system, spreadsheet, shared folder, inbox, or other place where work happens.</p><button className="primary" onClick={onDiscover}>Identify information</button></section>)}
    <NextStepCallout title="What to do next" body={groundZero ? "Identify one familiar system or tool to create your first information record. After that, AI Data Steward will show you the next stewardship decision." : "Work the highest-priority item at the top of the list. Open it to understand the issue, then complete the guided action tied to that item before moving on."} />
    {sorted.map(t=>{const isQuality=t.source_type==="QUALITY_ISSUE";return <div className={`task task-${t.priority.toLowerCase()}`} key={t.id}>
      <div className="task-head"><div><div className="eyebrow">{responsibilityLabel(t)} · {t.asset_name}</div><h3>{t.title}</h3></div><span className="priority">{priorityLabel(t.priority)}</span></div>
      <div className="two-col compact"><div><b>Why this matters</b><p>{isQuality?"The quality check found patterns that need a steward's review. They are observations, not automatic errors.":t.why_it_matters}</p></div><div><b>Recommended next step</b><p>{isQuality?"Open the findings workbench, start with the first item marked Needs review, and work through the findings one at a time.":t.recommended_action}</p></div></div>
      <button className="primary" onClick={()=>onGuide(t)}>{isQuality?"Review findings":"Start guided task"}</button>
    </div>})}
  </>;
}

function BusinessLandscape({role,systems,userEmail,landscapeScope,onDiscover,onRelationships,onHandoffStage,initialTab="Business functions"}) {
  const tabs=["Business functions","Business concepts","Business processes","Departments & units","Systems inventory"];
  const systemTypes=[
    ["APPLICATION","Application"],
    ["REPOSITORY","Repository"],
    ["REPORTING_TOOL","Reporting tool"],
    ["INTEGRATION","Integration"],
    ["EXTERNAL_SYSTEM","External system"],
    ["OTHER","Other"],
    ["UNKNOWN","Not sure yet"],
  ];
  const systemTypePlurals={APPLICATION:"Applications",REPOSITORY:"Repositories",REPORTING_TOOL:"Reporting tools",INTEGRATION:"Integrations",EXTERNAL_SYSTEM:"External systems"};
  const knowledgeStates=[
    ["CONFIRMED","Known","I can identify this system with confidence."],
    ["PARTIAL","Partly known","I know some details, but important pieces are missing."],
    ["UNCERTAIN","Uncertain","This is a lead or possibility that still needs confirmation."],
  ];
  const emptySystemForm={name:"",system_type:"UNKNOWN",knowledge_status:"UNCERTAIN",known_details:"",business_purpose:"",description:"",vendor:"",system_owner:""};
  const endpointByTab={
    "Business functions":"/landscape/functions",
    "Business concepts":"/landscape/concepts",
    "Business processes":"/landscape/processes",
    "Departments & units":"/landscape/units",
  };
  const fieldSets={
    "Business functions":[
      {name:"name",label:"Function name",required:true},
      {name:"purpose",label:"Business outcome",type:"textarea",wide:true},
      {name:"description",label:"Description",type:"textarea",wide:true},
      {name:"owner",label:"Business owner"},
    ],
    "Business concepts":[
      {name:"name",label:"Concept name",required:true},
      {name:"category",label:"Category"},
      {name:"definition",label:"Business definition",type:"textarea",wide:true},
      {name:"description",label:"Notes",type:"textarea",wide:true},
      {name:"owner",label:"Business owner"},
    ],
    "Business processes":[
      {name:"name",label:"Process name",required:true},
      {name:"description",label:"What happens",type:"textarea",wide:true},
      {name:"trigger",label:"What starts it",type:"textarea",wide:true},
      {name:"frequency",label:"How often"},
    ],
    "Departments & units":[
      {name:"name",label:"Department or unit name",required:true},
      {name:"unit_type",label:"Type",type:"select",options:[["DEPARTMENT","Department"],["DIVISION","Division"],["BUSINESS_UNIT","Business unit"],["TEAM","Team"],["OTHER","Other"]]},
      {name:"description",label:"What this group is responsible for",type:"textarea",wide:true},
    ],
  };
  const emptyForm={name:"",purpose:"",description:"",owner:"",category:"",definition:"",trigger:"",frequency:"",unit_type:"DEPARTMENT",source_function_id:"",target_function_id:""};
  const [activeTab,setActiveTab]=useState(initialTab);
  const [functions,setFunctions]=useState([]);
  const [concepts,setConcepts]=useState([]);
  const [flows,setFlows]=useState([]);
  const [units,setUnits]=useState([]);
  const [mappings,setMappings]=useState([]);
  const [systemInventory,setSystemInventory]=useState([]);
  const [completion,setCompletion]=useState(null);
  const [savedDraft,setSavedDraft]=useState(null);
  const [resumeAvailable,setResumeAvailable]=useState(false);
  const [draftUpdatedAt,setDraftUpdatedAt]=useState(null);
  const [draftReady,setDraftReady]=useState(false);
  const [resumedDraft,setResumedDraft]=useState(false);
  const [revisions,setRevisions]=useState([]);
  const [handoff,setHandoff]=useState(null);
  const [handoffBusy,setHandoffBusy]=useState(false);
  const [form,setForm]=useState(emptyForm);
  const [systemForm,setSystemForm]=useState(emptySystemForm);
  const [selectedUnitId,setSelectedUnitId]=useState("");
  const [editing,setEditing]=useState(null);
  const [editingSystemId,setEditingSystemId]=useState(null);
  const [showSystemForm,setShowSystemForm]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const canEdit=["STEWARD","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const isAdmin=["ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);

  async function load(includeDraft=false){
    const requests=[
      api("/landscape/functions",userEmail),
      api("/landscape/concepts",userEmail),
      api("/landscape/flows",userEmail),
      api("/landscape/units",userEmail),
      api("/landscape/function-unit-mappings",userEmail),
      api("/system-inventory",userEmail),
      api("/landscape/completion",userEmail),
    ];
    if(includeDraft&&canEdit) requests.push(api("/landscape/draft",userEmail));
    const [functionItems,conceptItems,flowItems,unitItems,mappingItems,inventoryItems,completionSummary,draftResponse]=await Promise.all(requests);
    setFunctions(functionItems);
    setConcepts(conceptItems);
    setFlows(flowItems);
    setUnits(unitItems);
    setMappings(mappingItems);
    setSystemInventory(inventoryItems);
    setCompletion(completionSummary);
    if(includeDraft&&canEdit){
      const data=draftResponse?.draft_data||{};
      setSavedDraft(Object.keys(data).length?data:null);
      setResumeAvailable(Object.keys(data).length>0);
      setDraftUpdatedAt(draftResponse?.updated_at||null);
      setRevisions(draftResponse?.revisions||[]);
      setDraftReady(true);
    }
  }

  useEffect(()=>{load(true).catch(e=>setError(e.message))},[userEmail,canEdit]);

  async function createCheckpoint(label){
    const result=await api("/landscape/draft/checkpoint",userEmail,{method:"POST",body:JSON.stringify({label})});
    setRevisions(current=>[result.revision,...current.filter(revision=>revision.id!==result.revision.id)].slice(0,20));
  }

  async function clearServerDraft(){
    await api("/landscape/draft",userEmail,{method:"PATCH",body:JSON.stringify({draft_data:{}})});
    setSavedDraft(null);setResumeAvailable(false);setDraftUpdatedAt(null);setResumedDraft(false);
  }

  async function discardCurrentEntry(){
    resetForm();resetSystemForm();
    try{await clearServerDraft()}catch(e){setError(`Could not discard the saved draft: ${e.message}`)}
  }

  function resumeDraft(){
    if(!savedDraft) return;
    if(tabs.includes(savedDraft.active_tab)) setActiveTab(savedDraft.active_tab);
    if(savedDraft.form) setForm({...emptyForm,...savedDraft.form});
    if(savedDraft.system_form) setSystemForm({...emptySystemForm,...savedDraft.system_form});
    setSelectedUnitId(savedDraft.selected_unit_id||"");
    setEditing(savedDraft.editing_id||null);
    setEditingSystemId(savedDraft.editing_system_id||null);
    setShowSystemForm(Boolean(savedDraft.show_system_form));
    setResumedDraft(true);
    setResumeAvailable(false);
    setSavedDraft(null);
  }

  async function restoreRevision(revision){
    if(!window.confirm(`Restore “${revision.label}”? Current landscape state will be checkpointed first.`)) return;
    setBusy(true);setError("");
    try{
      await api(`/landscape/draft/restore/${revision.id}`,userEmail,{method:"POST"});
      resetForm();resetSystemForm();
      await load(true);
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  const hasBusinessFormContent=[form.name,form.purpose,form.description,form.owner,form.category,form.definition,form.trigger,form.frequency,form.source_function_id,form.target_function_id].some(value=>typeof value==="string"&&value.trim());
  const activePartialDraft=showSystemForm||editing!==null||editingSystemId!==null||hasBusinessFormContent;
  function currentDraftSnapshot(){
    return {
      active_tab:activeTab,
      form,
      system_form:systemForm,
      selected_unit_id:selectedUnitId,
      editing_id:editing,
      editing_system_id:editingSystemId,
      show_system_form:showSystemForm,
    };
  }
  async function persistPartialDraft(event){
    if(event?.currentTarget?.contains(event.relatedTarget)||!activePartialDraft) return;
    const draftData=currentDraftSnapshot();
    try{
      const result=await api("/landscape/draft",userEmail,{method:"PATCH",body:JSON.stringify({draft_data:draftData})});
      setDraftUpdatedAt(result.updated_at);setSavedDraft(draftData);setResumeAvailable(true);
    }catch(e){setError(`Draft autosave failed: ${e.message}`)}
  }
  function changeLandscapeTab(tab){
    if(activePartialDraft) persistPartialDraft();
    resetForm();resetSystemForm();setActiveTab(tab);setError("");
  }
  useEffect(()=>{
    if(!draftReady||!activePartialDraft) return;
    const draftData=currentDraftSnapshot();
    const timer=setTimeout(()=>{
      api("/landscape/draft",userEmail,{method:"PATCH",body:JSON.stringify({draft_data:draftData})})
        .then(result=>{setDraftUpdatedAt(result.updated_at);setSavedDraft(draftData)})
        .catch(e=>setError(`Draft autosave failed: ${e.message}`));
    },450);
    return ()=>clearTimeout(timer);
  },[activeTab,form,systemForm,selectedUnitId,editing,editingSystemId,showSystemForm,draftReady,userEmail]);

  const businessCount=functions.length+concepts.length+flows.length+units.length;
  const unconfirmedSystems=systemInventory.filter(item=>item.knowledge_status!=="CONFIRMED").length;
  const readinessLabel=completion?.state==="READY_TO_PROCEED"?"Ready to proceed":completion?.state==="NOT_STARTED"?"Not started":"In progress";
  const primaryGuidance=completion?.guidance?.filter(item=>item.severity!=="SUCCESS")||[];
  async function prepareLandscapeHandoff(){
    setHandoffBusy(true);setError("");
    try{setHandoff(await api("/landscape/handoff",userEmail,{method:"POST"}))}
    catch(e){setError(e.message)}finally{setHandoffBusy(false)}
  }
  const activeRecords=activeTab==="Business functions"?functions:activeTab==="Business concepts"?concepts:activeTab==="Business processes"?flows:units;
  const pluralLabel=activeTab==="Business functions"?"functions":activeTab==="Business concepts"?"concepts":activeTab==="Business processes"?"processes":"departments and units";
  const functionsById=Object.fromEntries(functions.map(item=>[item.id,item.name]));

  function resetForm(){setForm(emptyForm);setEditing(null);setSelectedUnitId("")}

  function resetSystemForm(){setSystemForm(emptySystemForm);setEditingSystemId(null);setShowSystemForm(false)}

  function editSystem(item){
    setSystemForm({
      ...emptySystemForm,
      ...item,
      knowledge_status:item.knowledge_status==="UNASSESSED"?"UNCERTAIN":item.knowledge_status,
    });
    setEditingSystemId(item.system_id);
    setShowSystemForm(true);
  }

  async function saveSystem(e){
    e.preventDefault();
    setBusy(true);setError("");
    try{
      await createCheckpoint(editingSystemId?"Before editing a system inventory item":"Before adding a system inventory item");
      await api(editingSystemId?`/system-inventory/${editingSystemId}`:"/system-inventory",userEmail,{
        method:editingSystemId?"PATCH":"POST",
        body:JSON.stringify(systemForm),
      });
      resetSystemForm();
      await clearServerDraft();
      await load();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function deleteSystem(item){
    if(!window.confirm(`Delete “${item.name}” from the systems inventory? Resource records will remain but become unlinked.`)) return;
    setBusy(true);setError("");
    try{
      await createCheckpoint(`Before deleting system ${item.name}`);
      await api(`/system-inventory/${item.system_id}`,userEmail,{method:"DELETE"});
      if(editingSystemId===item.system_id){resetSystemForm();await clearServerDraft()}
      await load();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  function beginEdit(item){
    setEditing(item.id);
    setForm({...emptyForm,...item,source_function_id:item.source_function_id||"",target_function_id:item.target_function_id||""});
    if(activeTab==="Business functions"){
      setSelectedUnitId(String(mappings.find(mapping=>mapping.function_id===item.id)?.unit_id||""));
    }
  }

  async function save(e){
    e.preventDefault();
    const path=endpointByTab[activeTab];
    if(!path) return;
    const payload={...form};
    if(activeTab==="Business processes"){
      payload.source_function_id=payload.source_function_id?Number(payload.source_function_id):null;
      payload.target_function_id=payload.target_function_id?Number(payload.target_function_id):null;
    }
    setBusy(true);setError("");
    try{
      await createCheckpoint(editing?`Before editing ${activeTab.toLowerCase()}`:`Before adding ${activeTab.toLowerCase()}`);
      const saved=await api(editing?`${path}/${editing}`:path,userEmail,{method:editing?"PATCH":"POST",body:JSON.stringify(payload)});
      if(activeTab==="Business functions"){
        const currentMappings=mappings.filter(mapping=>mapping.function_id===saved.id);
        for(const mapping of currentMappings) await api(`/landscape/function-unit-mappings/${mapping.id}`,userEmail,{method:"DELETE"});
        if(selectedUnitId) await api("/landscape/function-unit-mappings",userEmail,{method:"POST",body:JSON.stringify({function_id:saved.id,unit_id:Number(selectedUnitId)})});
      }
      resetForm();
      await clearServerDraft();
      await load();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function remove(item){
    const path=endpointByTab[activeTab];
    if(!path||!window.confirm(`Delete “${item.name}”?`)) return;
    setBusy(true);setError("");
    try{await createCheckpoint(`Before deleting ${item.name}`);await api(`${path}/${item.id}`,userEmail,{method:"DELETE"});await load();if(editing===item.id){resetForm();await clearServerDraft()}}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function removeMapping(mapping){
    setBusy(true);setError("");
    try{await createCheckpoint("Before changing department mappings");await api(`/landscape/function-unit-mappings/${mapping.id}`,userEmail,{method:"DELETE"});await load()}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }

  function recordDetail(item){
    if(activeTab==="Business functions"){
      const mapped=mappings.filter(mapping=>mapping.function_id===item.id).map(mapping=>units.find(unit=>unit.id===mapping.unit_id)?.name).filter(Boolean);
      return <>{item.purpose&&<p>{item.purpose}</p>}<small>{item.owner||"Owner not recorded"}{mapped.length?` · ${mapped.join(", ")}`:" · No department or unit mapped"}</small></>;
    }
    if(activeTab==="Business concepts") return <>{item.definition&&<p>{item.definition}</p>}<small>{item.category||"Business concept"}{item.owner?` · ${item.owner}`:""}</small></>;
    if(activeTab==="Business processes") return <>{item.description&&<p>{item.description}</p>}<small>{item.frequency||"Frequency not recorded"}{item.source_function_id?` · ${functionsById[item.source_function_id]||"Function"}`:""}{item.target_function_id?` → ${functionsById[item.target_function_id]||"Function"}`:""}</small></>;
    return <><p>{item.description||"Responsibility description not recorded."}</p><small>{item.unit_type.replaceAll("_"," ")}</small></>;
  }

  return <>
    <div className="business-landscape-head">
      <div><div className="eyebrow">Ground Zero · {activeTab==="Systems inventory"?"Systems layer":"Business map"}</div><h1>{activeTab==="Systems inventory"?"Systems inventory":landscapeScope?.title||"Business Landscape"}</h1><p className="lead">{activeTab==="Systems inventory"?"Record the applications and technical connections that support business work. Uncertain or incomplete details can stay clearly marked for follow-up.":"Map the work, shared language, and accountable groups first. These are business items, separate from the software and technical sources that support them."}</p></div>
    </div>
    <section className="education strong role-landscape-guidance"><b>{canEdit?(isAdmin?"Administrator oversight with intervention access":"Steward construction workspace"):"Read-only readiness and governance review"}</b><p>{canEdit?(isAdmin?"Monitor landscape health and unresolved gaps. Make changes only when administrative intervention is appropriate.":"Build the business and systems layers, map relationships, and resolve the gaps shown below."):"Review completeness, gaps, and governance connections. An assigned steward or administrator must make changes."}</p></section>
    {resumeAvailable&&savedDraft&&<section className="resume-draft-banner"><div><div className="eyebrow">Saved unfinished work</div><b>{savedDraft.form?.name||savedDraft.system_form?.name||"Landscape entry in progress"}</b><span>{draftUpdatedAt?`Last saved ${new Date(draftUpdatedAt).toLocaleString()}`:"Saved for resuming"}</span></div><div className="button-row"><button type="button" onClick={()=>clearServerDraft().catch(e=>setError(e.message))}>Discard draft</button><button type="button" className="primary" onClick={resumeDraft}>Resume</button></div></section>}
    <div className="business-counts">
      <div><strong>{businessCount}</strong><span>Business items mapped</span></div>
      <div><strong>{functions.length}</strong><span>Functions</span></div>
      <div><strong>{concepts.length}</strong><span>Concepts</span></div>
      <div><strong>{flows.length}</strong><span>Processes</span></div>
      <div><strong>{units.length}</strong><span>Departments & units</span></div>
      <div className="technical-count"><strong>{systemInventory.length}</strong><span>Technical systems</span></div>
    </div>
    {completion&&<section className={`landscape-completion state-${completion.state.toLowerCase()}`}>
      <div className="completion-score-block"><div className="eyebrow">Landscape completeness</div><strong>{completion.completeness_score}%</strong><span>{readinessLabel} · {completion.checks_complete} of {completion.checks_total} checks</span><div className="completion-progress"><i style={{width:`${completion.completeness_score}%`}} /></div></div>
      <div className="completion-guidance-block"><div className="completion-guidance-heading"><div><div className="eyebrow">What needs attention</div><h2>{completion.ready_to_proceed?"Core landscape is connected":"Build out the landscape"}</h2></div>{onRelationships&&<button type="button" onClick={onRelationships}>Review connections</button>}</div>
        {primaryGuidance.length===0?<p className="completion-clear">{completion.guidance?.[0]?.message||"The landscape is ready to proceed."}</p>:<ul className="completion-guidance-list">{primaryGuidance.map(item=><li key={item.code} className={`guidance-${item.severity.toLowerCase()}`}><span aria-hidden="true">{item.severity==="ACTION"?"!":"·"}</span>{item.message}</li>)}</ul>}
        {(completion.unconnected_systems?.length>0||completion.duplicate_concepts?.length>0||completion.incomplete_functions?.length>0)&&<details className="completion-details"><summary>See the specific items</summary>
          {completion.unconnected_systems?.length>0&&<p><b>Unconnected systems:</b> {completion.unconnected_systems.map(item=>item.name).join(", ")}</p>}
          {completion.incomplete_functions?.length>0&&<p><b>Functions to clarify:</b> {completion.incomplete_functions.map(item=>`${item.name} (${item.missing.join(" and ")})`).join(", ")}</p>}
          {completion.duplicate_concepts?.length>0&&<p><b>Possible duplicate concepts:</b> {completion.duplicate_concepts.map(group=>group.items.map(item=>item.name).join(" / ")).join("; ")}</p>}
        </details>}
      </div>
    </section>}
    {completion?.ready_to_proceed&&<section className="landscape-ready-handoff">
      <div className="landscape-ready-heading"><div><div className="eyebrow">Ground Zero complete · Stewardship begins</div><h2>Landscape ready for next step</h2><p>The business scope is connected to its systems. Continue into the asset-level stewardship workflow; later review and approval remain explicit human decisions.</p></div>{!handoff&&<button type="button" className="primary" onClick={prepareLandscapeHandoff} disabled={handoffBusy}>{handoffBusy?"Preparing…":canEdit?"Create next-step tasks":"Review workflow readiness"}</button>}</div>
      {handoff&&<>
        {handoff.created_task_ids?.length>0&&<div className="handoff-created-note">Created {handoff.created_task_ids.length} next-step task{handoff.created_task_ids.length===1?"":"s"} from current asset readiness.</div>}
        {handoff.next_stage&&(canEdit||handoff.next_stage.key==="approval")&&<div className="handoff-next-action"><div><div className="eyebrow">Recommended next step</div><b>{handoff.next_stage.label}</b><small>{handoff.next_stage.asset_name||"Start by identifying an information asset."}</small></div><button type="button" className="primary" onClick={()=>onHandoffStage?.(handoff.next_stage)}>{handoff.next_stage.page==="Review Queue"?"Open review queue":handoff.next_stage.page==="Discover Information"?"Identify information":handoff.next_stage.tab==="Share & Publish"?"Prepare approval":"Continue"}</button></div>}
        <div className="handoff-stage-list">{handoff.stages.map((stage,index)=>{
          const stageLabels={understanding:"Understanding",official_source:"Official source review",quality:"Quality assessment",approval:"Approval"};
          const statusLabels={ACTION_REQUIRED:"Action required",REVIEW_REQUIRED:"Review required",READY:"Ready",BLOCKED:"Complete earlier stewardship first",IN_REVIEW:"In review",WAITING_FOR_SUBMISSION:"Waiting for steward submission",WAITING_FOR_INFORMATION:"Needs an information asset",COMPLETE:"Complete"};
          const routeable=Boolean((canEdit||stage.key==="approval")&&(stage.asset_id||stage.page==="Review Queue"||stage.page==="Discover Information"));
          const isBlocked=stage.status==="BLOCKED"||stage.status==="WAITING_FOR_INFORMATION";
          return <article className={`handoff-stage ${stage.status.toLowerCase()}`} key={stage.key}>
            <span className="handoff-stage-number">{index+1}</span>
            <div className="handoff-stage-copy"><b>{stageLabels[stage.key]||stage.label}</b><small>{stage.asset_name?`${stage.asset_name} · `:""}{statusLabels[stage.status]||stage.status}{stage.task_count?` · ${stage.task_count} task${stage.task_count===1?"":"s"}`:""}</small></div>
            <button type="button" disabled={!routeable||isBlocked} onClick={()=>onHandoffStage?.(stage)}>{stage.page==="Review Queue"?"Open review queue":stage.page==="Discover Information"?"Identify information":stage.key==="approval"?"Prepare approval":"Open stage"}</button>
          </article>;
        })}</div>
      </>}
    </section>}
    {canEdit&&revisions.length>0&&<details className="landscape-revision-history"><summary>Restore a previous landscape version <span>{revisions.length} saved</span></summary><div className="revision-list">{revisions.map(revision=><div className="revision-row" key={revision.id}><div><b>{revision.label}</b><small>{new Date(revision.created_at).toLocaleString()}</small></div><button type="button" disabled={busy} onClick={()=>restoreRevision(revision)}>Restore</button></div>)}</div></details>}
    <div className="education strong business-why"><b>Why this matters</b><p>Business functions describe what your organization does; concepts describe the terms it shares; processes describe how work moves. Mapping them to a department or unit makes ownership visible before you connect any technical system.</p></div>
    {error&&<div className="message message-error" role="alert">{error}</div>}
    <div className="tabs business-tabs" role="tablist" aria-label="Landscape item type">
      {tabs.map(tab=><button key={tab} role="tab" aria-selected={activeTab===tab} className={activeTab===tab?"tab active":"tab"} onClick={()=>changeLandscapeTab(tab)}>{tab}</button>)}
    </div>
    {activeTab==="Systems inventory"?<section className="panel technical-landscape-panel systems-inventory-panel">
      <div className="eyebrow">Ground Zero · Systems layer</div>
      <div className="inventory-title-row"><div><h2>Systems inventory</h2><p className="lead">{canEdit?"Record the applications and technical connections that support business work. You can add an item before every detail is known.":"Review the applications and technical connections recorded by the steward."}</p></div>{canEdit&&<button className="primary" onClick={()=>{setSystemForm(emptySystemForm);setEditingSystemId(null);setShowSystemForm(true)}}>Add a system</button>}</div>
      <div className="inventory-guidance"><b>Uncertainty is useful information.</b><span>Mark what is confirmed, what is only partly known, or what still needs checking. Nothing here is treated as verified just because it was entered.</span></div>
      <div className="system-inventory-counts">
        {systemTypes.slice(0,5).map(([type])=><div key={type}><strong>{systemInventory.filter(item=>item.system_type===type).length}</strong><span>{systemTypePlurals[type]}</span></div>)}
        <div className="needs-confirmation"><strong>{unconfirmedSystems}</strong><span>Need confirmation</span></div>
      </div>
      {canEdit&&showSystemForm&&<form className="inventory-form" onSubmit={saveSystem} onBlurCapture={persistPartialDraft}>
        <div className="task-head"><div><div className="eyebrow">{editingSystemId?"Update inventory":"New inventory item"}</div><h3>{editingSystemId?"What do you know about this system?":"What system or connection have you encountered?"}</h3></div><button type="button" aria-label="Close system form" onClick={resetSystemForm}>Close</button></div>
        <p className="business-guidance">A familiar name, shorthand, or “not yet identified” label is enough to start. You do not need a technical identifier.</p>
        <label>System name or working label<input required value={systemForm.name} onChange={e=>setSystemForm(current=>({...current,name:e.target.value}))} placeholder="e.g., GitLab repository, partner portal (name unknown)" /></label>
        <div className="inventory-field-label">What kind of system is it?</div>
        <div className="system-type-choices">{systemTypes.map(([type,label])=><button type="button" key={type} className={systemForm.system_type===type?"system-type-choice selected":"system-type-choice"} aria-pressed={systemForm.system_type===type} onClick={()=>setSystemForm(current=>({...current,system_type:type}))}>{label}</button>)}</div>
        <div className="inventory-field-label">How certain are you?</div>
        <div className="knowledge-choices">{knowledgeStates.map(([status,label,help])=><button type="button" key={status} aria-pressed={systemForm.knowledge_status===status} className={systemForm.knowledge_status===status?"knowledge-choice selected":"knowledge-choice"} onClick={()=>setSystemForm(current=>({...current,knowledge_status:status}))}><b>{label}</b><span>{help}</span></button>)}</div>
        <div className="form-grid inventory-details-grid">
          <label>What is it used for?<textarea rows="3" value={systemForm.business_purpose||""} onChange={e=>setSystemForm(current=>({...current,business_purpose:e.target.value}))} placeholder="Describe the business work it may support." /></label>
          <label>What do you know or need to confirm?<textarea rows="3" value={systemForm.known_details||""} onChange={e=>setSystemForm(current=>({...current,known_details:e.target.value}))} placeholder="For example: The team uses it for source code; owner and hosting are not yet known." /></label>
          <label>Vendor or provider<input value={systemForm.vendor||""} onChange={e=>setSystemForm(current=>({...current,vendor:e.target.value}))} placeholder="Optional" /></label>
          <label>Owner or contact<input value={systemForm.system_owner||""} onChange={e=>setSystemForm(current=>({...current,system_owner:e.target.value}))} placeholder="Optional" /></label>
          <label className="wide">Additional description<textarea rows="2" value={systemForm.description||""} onChange={e=>setSystemForm(current=>({...current,description:e.target.value}))} placeholder="Optional context" /></label>
        </div>
        <div className="button-row"><button type="button" onClick={resetSystemForm}>Cancel</button><button className="primary" type="submit" disabled={busy||!systemForm.name.trim()}>{busy?"Saving…":editingSystemId?"Save inventory details":"Add to systems inventory"}</button></div>
      </form>}
      {systemInventory.length===0?<EmptyState title="No systems recorded yet." text="Add a known system, a partly known connection, or an uncertain lead. Business functions and systems stay in separate layers."/>:<div className="business-record-list inventory-record-list">{systemInventory.map(item=>{
        const typeLabel=systemTypes.find(([type])=>type===item.system_type)?.[1]||"System type unknown";
        const stateLabel=item.knowledge_status==="CONFIRMED"?"Confirmed":item.knowledge_status==="PARTIAL"?"Partly known":item.knowledge_status==="UNCERTAIN"?"Uncertain":"Needs inventory";
        return <article className={`business-record technical-record inventory-record knowledge-${(item.knowledge_status||"unassessed").toLowerCase()}`} key={item.system_id}>
          <div><div className="inventory-record-meta"><span className="system-type-badge">{typeLabel}</span><span className="knowledge-badge">{stateLabel}</span></div><h3>{item.name}</h3><p>{item.business_purpose||"Business purpose not recorded yet."}</p>{item.known_details&&<div className="known-detail-note"><b>{item.knowledge_status==="CONFIRMED"?"Inventory note":"Known so far / to confirm"}</b><span>{item.known_details}</span></div>}<small>{item.vendor||"Provider not recorded"}{item.system_owner?` · ${item.system_owner}`:""}</small></div>
          {canEdit&&<div className="record-actions"><button type="button" onClick={()=>editSystem(item)}>{item.knowledge_status==="UNASSESSED"?"Complete inventory":"Edit"}</button><button type="button" className="danger-button" onClick={()=>deleteSystem(item)}>Delete</button></div>}
        </article>;
      })}</div>}
    </section>:<div className={canEdit?"business-work-area":"business-work-area read-only-landscape"}>
      {canEdit&&<section className="panel business-editor">
        <div className="eyebrow">{editing?"Edit":"Add"} · {activeTab}</div>
        <h2>{editing?"Update this business item":`Add ${activeTab.toLowerCase()}`}</h2>
        <p className="business-guidance">{activeTab==="Business functions"?"Start with an outcome or responsibility the organization performs, not an application name.":activeTab==="Business concepts"?"Use a term that business people share and can recognize across teams.":activeTab==="Business processes"?"Describe the work from its trigger through its outcome, in the language the team uses.":"Capture who the group is and what it is accountable for; you can map functions to it."}</p>
        <form className="form-grid business-form" onSubmit={save} onBlurCapture={persistPartialDraft}>
          {fieldSets[activeTab].map(field=><label key={field.name} className={field.wide?"wide":""}>{field.label}{field.type==="textarea"?<textarea rows="3" value={form[field.name]||""} required={field.required} onChange={e=>setForm(current=>({...current,[field.name]:e.target.value}))}/>:field.type==="select"?<select value={form[field.name]||""} onChange={e=>setForm(current=>({...current,[field.name]:e.target.value}))}>{field.options.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>:<input value={form[field.name]||""} required={field.required} onChange={e=>setForm(current=>({...current,[field.name]:e.target.value}))}/>}</label>)}
          {activeTab==="Business functions"&&<label className="wide">Department or unit<select value={selectedUnitId} onChange={e=>setSelectedUnitId(e.target.value)}><option value="">Not mapped yet</option>{units.map(unit=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label>}
          {activeTab==="Business processes"&&<><label>Starts in function<select value={form.source_function_id||""} onChange={e=>setForm(current=>({...current,source_function_id:e.target.value}))}><option value="">Not linked</option>{functions.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Moves to function<select value={form.target_function_id||""} onChange={e=>setForm(current=>({...current,target_function_id:e.target.value}))}><option value="">Not linked</option>{functions.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label></>}
          <div className="button-row wide"><button type="button" onClick={discardCurrentEntry} disabled={!editing&&!form.name&&!hasBusinessFormContent}>Clear</button><button type="submit" className="primary" disabled={busy||!form.name.trim()}>{busy?"Saving…":editing?"Save changes":"Add to business map"}</button></div>
        </form>
      </section>}
      <section className="panel business-records-panel">
        <div className="task-head"><div><div className="eyebrow">Running count · {pluralLabel}</div><h2>{activeRecords.length} {pluralLabel}</h2></div></div>
        {activeRecords.length===0?<EmptyState title={`No ${pluralLabel} mapped yet.`} text={canEdit?"Add a first item using plain business language. A rough starting point is fine; you can refine it as you learn more.":"No records are available for governance review."}/>:<div className="business-record-list">{activeRecords.map(item=><article className="business-record" key={item.id}><div><h3>{item.name}</h3>{recordDetail(item)}{activeTab==="Business functions"&&mappings.filter(mapping=>mapping.function_id===item.id).map(mapping=>canEdit?<button type="button" className="mapping-chip" key={mapping.id} title="Remove department or unit mapping" onClick={()=>removeMapping(mapping)}>{units.find(unit=>unit.id===mapping.unit_id)?.name||"Mapped unit"} ×</button>:<span className="mapping-chip" key={mapping.id}>{units.find(unit=>unit.id===mapping.unit_id)?.name||"Mapped unit"}</span>)}</div>{canEdit&&<div className="record-actions"><button type="button" onClick={()=>beginEdit(item)}>Edit</button><button type="button" className="danger-button" onClick={()=>remove(item)}>Delete</button></div>}</article>)}</div>}
      </section>
    </div>}
  </>;
}

function RelationshipBuilder({role,userEmail,onBusinessLandscape}) {
  const relationshipKinds=[
    {value:"SUPPORTS",label:"Connect work to a system",description:"Show which system helps people perform a business responsibility.",source:"BUSINESS_FUNCTION",target:"SYSTEM",sourceQuestion:"What work does the team do?",targetQuestion:"Which system helps with this work?"},
    {value:"DESCRIBES",label:"Connect a business term to information",description:"Show where a familiar business idea appears as managed information.",source:"BUSINESS_CONCEPT",target:"ASSET",sourceQuestion:"Which business term or idea?",targetQuestion:"Which information does it describe?"},
    {value:"OWNER",label:"Name who owns information",description:"Record the person accountable for the business use of information.",source:"ASSET",target:"PERSON",sourceQuestion:"Which information?",targetQuestion:"Who is accountable for it?"},
    {value:"STEWARD",label:"Name who maintains information",description:"Record the person who helps keep information understood and current.",source:"ASSET",target:"PERSON",sourceQuestion:"Which information?",targetQuestion:"Who helps keep it current?"},
    {value:"REPRESENTS",label:"Connect a system to a location",description:"Show the screen, file, report, or other location a system provides.",source:"SYSTEM",target:"RESOURCE",sourceQuestion:"Which system?",targetQuestion:"Which location does it provide?",advanced:true},
    {value:"DEPENDS_ON",label:"Record an upstream dependency",description:"Show that one business area, system, or information item relies on another.",dynamic:true,sourceQuestion:"What depends on something else?",targetQuestion:"What does it depend on?",advanced:true},
    {value:"PROCESS_FLOW",label:"Show how work moves",description:"Connect two business responsibilities through a defined process.",source:"BUSINESS_FUNCTION",target:"BUSINESS_FUNCTION",sourceQuestion:"Where does the work begin?",targetQuestion:"Where does it go next?",advanced:true},
  ];
  const entityLabels={BUSINESS_FUNCTION:"Business function",BUSINESS_CONCEPT:"Business concept",BUSINESS_PROCESS:"Business process",SYSTEM:"System",RESOURCE:"Resource",ASSET:"Information asset",PERSON:"Person"};
  const relationshipLabels={SUPPORTS:"supports",DESCRIBES:"describes",REPRESENTS:"provides",OWNER:"owned by",STEWARD:"stewarded by",DEPENDS_ON:"depends on",PROCESS_FLOW:"flows to"};
  const [functions,setFunctions]=useState([]);
  const [concepts,setConcepts]=useState([]);
  const [processes,setProcesses]=useState([]);
  const [systems,setSystems]=useState([]);
  const [assetRecords,setAssetRecords]=useState([]);
  const [relationships,setRelationships]=useState([]);
  const [relationshipType,setRelationshipType]=useState("SUPPORTS");
  const [dependencyEntityType,setDependencyEntityType]=useState("BUSINESS_FUNCTION");
  const [sourceId,setSourceId]=useState("");
  const [targetId,setTargetId]=useState("");
  const [processId,setProcessId]=useState("");
  const [personName,setPersonName]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const canEdit=["STEWARD","ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);
  const isAdmin=["ORG_ADMIN","ENTERPRISE_ADMIN"].includes(role);

  async function createCheckpoint(label){
    await api("/landscape/draft/checkpoint",userEmail,{method:"POST",body:JSON.stringify({label})});
  }

  async function load(){
    const [functionItems,conceptItems,processItems,systemItems,assetItems,relationshipItems]=await Promise.all([
      api("/landscape/functions",userEmail),
      api("/landscape/concepts",userEmail),
      api("/landscape/processes",userEmail),
      api("/system-inventory",userEmail),
      api("/assets",userEmail),
      api("/landscape/relationships",userEmail),
    ]);
    setFunctions(functionItems);
    setConcepts(conceptItems);
    setProcesses(processItems);
    setSystems(systemItems);
    setAssetRecords(assetItems);
    setRelationships(relationshipItems);
  }

  useEffect(()=>{load().catch(e=>setError(e.message))},[userEmail]);

  const assets=assetRecords.map(record=>record.asset);
  const resources=assetRecords.flatMap(record=>(record.resources||[]).map(resource=>({...resource,asset_name:record.asset.name})));
  const selectedKind=relationshipKinds.find(kind=>kind.value===relationshipType)||relationshipKinds[0];
  const sourceType=selectedKind.dynamic?dependencyEntityType:selectedKind.source;
  const targetType=selectedKind.dynamic?dependencyEntityType:selectedKind.target;

  function optionsFor(type){
    if(type==="BUSINESS_FUNCTION") return functions.map(item=>({id:item.id,label:item.name}));
    if(type==="BUSINESS_CONCEPT") return concepts.map(item=>({id:item.id,label:item.name}));
    if(type==="BUSINESS_PROCESS") return processes.map(item=>({id:item.id,label:item.name}));
    if(type==="SYSTEM") return systems.map(item=>({id:item.system_id,label:item.name}));
    if(type==="RESOURCE") return resources.map(item=>({id:item.resource_id,label:`${item.name}${item.asset_name?` · ${item.asset_name}`:""}`}));
    if(type==="ASSET") return assets.map(item=>({id:item.asset_id,label:item.name}));
    return [];
  }

  function labelFor(type,id,relationship){
    if(type==="PERSON") return relationship?.details?.display_name||"Person not named";
    return optionsFor(type).find(item=>String(item.id)===String(id))?.label||`${entityLabels[type]||type} not found`;
  }

  function chooseKind(value){
    setRelationshipType(value);
    setSourceId("");setTargetId("");setPersonName("");setProcessId("");
    setError("");setNotice("");
  }

  async function save(e){
    e.preventDefault();
    setError("");setNotice("");setBusy(true);
    const payload={
      source_type:sourceType,
      source_id:Number(sourceId),
      target_type:targetType,
      target_id:targetType==="PERSON"?null:Number(targetId),
      relationship_type:relationshipType,
    };
    if(targetType==="PERSON") payload.details={display_name:personName.trim()};
    if(relationshipType==="PROCESS_FLOW") payload.process_id=Number(processId);
    try{
      await createCheckpoint(`Before adding ${relationshipLabels[relationshipType]||"a relationship"} link`);
      await api("/landscape/relationships",userEmail,{method:"POST",body:JSON.stringify(payload)});
      setSourceId("");setTargetId("");setPersonName("");setProcessId("");
      setNotice("Connection saved. You can add another connection or review it below.");
      await load();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function remove(relationship){
    setBusy(true);setError("");setNotice("");
    try{
      await createCheckpoint(`Before removing ${relationshipLabels[relationship.relationship_type]||"a relationship"} link`);
      await api(`/landscape/relationships/${encodeURIComponent(relationship.id)}`,userEmail,{method:"DELETE"});
      await load();
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  const readyToSave=Boolean(sourceId&&((targetType==="PERSON"&&personName.trim())||(targetType!=="PERSON"&&targetId))&&(relationshipType!=="PROCESS_FLOW"||processId));

  return <>
    <div className="relationship-page-head"><div><div className="eyebrow">How your work fits together</div><h1>Connect what you already know</h1><p className="lead">Choose a simple statement below, then fill in its two parts. You can build this picture one connection at a time.</p></div><div className="relationship-total"><strong>{relationships.length}</strong><span>Connections</span></div></div>
    <section className="education strong role-landscape-guidance"><b>{canEdit?(isAdmin?"Relationship oversight":"Steward mapping workspace"):"Read-only governance map"}</b><p>{canEdit?(isAdmin?"Review cross-layer dependencies and intervene when an administrative correction is required.":"Add and maintain the connections that explain how business work, information, and systems fit together."):"Use these connections to evaluate ownership, dependencies, and readiness. A steward or administrator must change the map."}</p></section>
    {error&&<div className="message message-error" role="alert">{error}</div>}
    {notice&&<div className="message message-success" role="status">{notice}</div>}
    {canEdit&&<section className="panel relationship-builder-panel">
      <div className="eyebrow">Step 1</div><h2>What do you want to show?</h2>
      <div className="relationship-kind-cards">{relationshipKinds.filter(kind=>!kind.advanced).map(kind=><button className={relationshipType===kind.value?"selected":""} type="button" key={kind.value} onClick={()=>chooseKind(kind.value)}><b>{kind.label}</b><span>{kind.description}</span></button>)}</div>
      <details className="relationship-advanced" open={selectedKind.advanced||undefined}>
        <summary>More connection types</summary>
        <div className="relationship-kind-cards">{relationshipKinds.filter(kind=>kind.advanced).map(kind=><button className={relationshipType===kind.value?"selected":""} type="button" key={kind.value} onClick={()=>chooseKind(kind.value)}><b>{kind.label}</b><span>{kind.description}</span></button>)}</div>
      </details>
      <div className="relationship-form-heading"><div className="eyebrow">Step 2</div><h2>Complete the connection</h2><p>{selectedKind.description}</p></div>
      <form className="relationship-form" onSubmit={save}>
        {selectedKind.dynamic&&<label>What kind of item are you connecting?<select value={dependencyEntityType} onChange={e=>{setDependencyEntityType(e.target.value);setSourceId("");setTargetId("")}}>{[["BUSINESS_FUNCTION","Business work"],["SYSTEM","Systems"],["ASSET","Information"]].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>}
        {relationshipType==="PROCESS_FLOW"&&<label>Which process connects them?<select value={processId} onChange={e=>setProcessId(e.target.value)}><option value="">Choose a process</option>{processes.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <label>{selectedKind.sourceQuestion}<select value={sourceId} onChange={e=>setSourceId(e.target.value)}><option value="">Choose one</option>{optionsFor(sourceType).map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        {targetType==="PERSON"?<label>{selectedKind.targetQuestion}<input value={personName} onChange={e=>setPersonName(e.target.value)} placeholder="Enter a person's name"/></label>:<label>{selectedKind.targetQuestion}<select value={targetId} onChange={e=>setTargetId(e.target.value)}><option value="">Choose one</option>{optionsFor(targetType).map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>}
        <div className="relationship-sentence" aria-live="polite"><b>Your connection</b><span>{sourceId?labelFor(sourceType,sourceId):"Choose the first item"} <strong>{relationshipLabels[relationshipType]||"connects to"}</strong> {targetType==="PERSON"?(personName.trim()||"enter a person's name"):(targetId?labelFor(targetType,targetId):"choose the second item")}.</span></div>
        <div className="relationship-form-actions"><button type="submit" className="primary" disabled={busy||!readyToSave}>{busy?"Saving…":"Save this connection"}</button></div>
      </form>
    </section>}
    <section className="relationship-map-section">
      <div className="task-head"><div><div className="eyebrow">What you have connected</div><h2>Your connections</h2></div><button onClick={onBusinessLandscape}>Add or edit the items above</button></div>
      {relationships.length===0?<EmptyState title="No relationships have been mapped yet." text="Your first saved connection will appear here. You can add more links as the landscape becomes clearer."/>:<div className="relationship-list">{relationships.map(relationship=><article className="relationship-edge" key={`${relationship.id}:${relationship.relationship_type}`}>
        <div className="relationship-node"><small>{entityLabels[relationship.source_type]||relationship.source_type}</small><b>{labelFor(relationship.source_type,relationship.source_id,relationship)}</b></div>
        <div className="relationship-connector"><span>{relationshipLabels[relationship.relationship_type]||relationship.relationship_type}</span><i aria-hidden="true">→</i>{relationship.details?.process_name&&<small>{relationship.details.process_name}</small>}</div>
        <div className="relationship-node"><small>{entityLabels[relationship.target_type]||relationship.target_type}</small><b>{labelFor(relationship.target_type,relationship.target_id,relationship)}</b></div>
        <div className="relationship-edge-actions">{relationship.origin==="EXISTING"&&<small>Existing link</small>}{canEdit&&<button type="button" onClick={()=>remove(relationship)} disabled={busy} aria-label={`Remove ${relationshipLabels[relationship.relationship_type]||"relationship"}`}>Remove</button>}</div>
      </article>)}</div>}
    </section>
  </>;
}

function Discover({systems, userEmail, onDone}) {
  const [step,setStep]=useState(1);
  const [systemName,setSystemName]=useState("");
  const [systemPurpose,setSystemPurpose]=useState("");
  const [starterType,setStarterType]=useState("SYSTEM");
  const [touchpointType,setTouchpointType]=useState("SCREEN");
  const [touchpointName,setTouchpointName]=useState("");
  const [informationName,setInformationName]=useState("");
  const [customInformation,setCustomInformation]=useState("");
  const [businessUse,setBusinessUse]=useState("");
  const [createdAsset,setCreatedAsset]=useState(null);
  const [completedResource,setCompletedResource]=useState(null);
  const [createdSystem,setCreatedSystem]=useState(null);
  const [resourceName,setResourceName]=useState("");
  const [resourceType,setResourceType]=useState("APPLICATION_SCREEN");
  const [structureType,setStructureType]=useState("STRUCTURED");
  const [locationReference,setLocationReference]=useState("");

  function words(text){
    return (text||"").toLowerCase();
  }

  function suggestedInformation(){
    const text=words(`${systemPurpose} ${touchpointName} ${starterType}`);
    const suggestions=[];
    const add=(name,why)=>{ if(!suggestions.some(x=>x.name===name)) suggestions.push({name,why}); };

    if (starterType === "FILE") {
      add("File-based business records","The business information is captured in a spreadsheet, export, or file people use as a source of record.");
      add("Data extracts and working files","This file contains a recurring extract or working dataset that supports business decisions.");
    }
    if (starterType === "FOLDER") {
      add("Document collection","This folder or document set is the organized business record collection people rely on.");
      add("Supporting records","Documents and files in this collection provide the underlying business evidence or history.");
    }
    if (starterType === "EMAIL") {
      add("Recurring business output","This report or email stream is a regular business output people act on and use as a source of information.");
      add("Operational communication records","The communications carry the business information people need to monitor, respond, or decide.");
    }

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
    setCompletedResource({assetName:createdAsset.asset.name,resourceName:resourceName.trim()});
  }

  const candidates=suggestedInformation();
  const selectedInformation=customInformation.trim()||informationName.trim();
  const starterOptions=[
    ["SYSTEM","System or application","A software tool, website, or platform the team uses to get work done."],
    ["FILE","Spreadsheet or file","A CSV, spreadsheet, export, or other file people rely on for reporting or work."],
    ["FOLDER","Folder or document collection","A shared drive, library, or group of documents people use as a business record set."],
    ["EMAIL","Email or report","A mailbox, recurring report, or regular output people read or act on."],
  ];
  const discoverStepHelp = {
    1: "Milestone 1 · Scope: start with the familiar place your team already uses. This anchors the discovery in real work instead of a blank technical catalog form.",
    2: "Milestone 2 · Business context: name the specific screen, file, folder, or report people actually use. This tells us where the business information appears in the real workflow.",
    3: "Milestone 3 · Information concept: pick the kind of information this source is about. We are separating the system from the data so you can identify the actual business concept, not just the tool.",
    4: "Milestone 4 · Business meaning: describe the business purpose in plain language. That becomes the definition other people will rely on when they look for this information later.",
    5: "Milestone 5 · Source and validation: record where the information lives and confirm the next step so the landscape builds toward a trusted source and a real stewardship workflow.",
  };
  const starterCopy={
    SYSTEM:{heading:"What system or tool does your team use?", fieldLabel:"System or tool name", placeholder:"e.g., Sunbiz, Licensing System, SharePoint", purposeLabel:"What does your team use it to do?", purposePlaceholder:"Describe the work in ordinary language. For example: Register businesses and maintain their filing history.", interactionLabel:"What do you interact with in {systemName}?", interactionPlaceholder:"e.g., Corporate Filing Search screen", interactionHelp:"Think about the specific screen, page, report, or record set people use to do the work."},
    FILE:{heading:"What file or spreadsheet are you starting from?", fieldLabel:"File, spreadsheet, or export name", placeholder:"e.g., Permit data export, licensing workbook, payment file", purposeLabel:"What business information is in this file or spreadsheet?", purposePlaceholder:"Describe what the file is used for and what decisions it supports.", interactionLabel:"What part of this file or spreadsheet matters to the business?", interactionPlaceholder:"e.g., Licensing workbook tab, annual report export, payment detail file", interactionHelp:"Focus on the workbook tab, export, file section, or recurring data set people rely on."},
    FOLDER:{heading:"What folder or document collection are you starting from?", fieldLabel:"Folder, library, or collection name", placeholder:"e.g., Licensing documents, case files, training archive", purposeLabel:"What work does this collection support?", purposePlaceholder:"Explain the business purpose of this folder or document set.", interactionLabel:"What document group or folder contains the business information?", interactionPlaceholder:"e.g., Active permit applications, complaint records, training packet library", interactionHelp:"This may be a folder, document library, or shared set of records people use together."},
    EMAIL:{heading:"What report, mailbox, or recurring output are you starting from?", fieldLabel:"Report, mailbox, or source name", placeholder:"e.g., Weekly compliance report, permits inbox, client update output", purposeLabel:"What business work does this source support?", purposePlaceholder:"Describe the report or information stream and why people rely on it.", interactionLabel:"What output or communication channel is carrying the information?", interactionPlaceholder:"e.g., Daily compliance digest, vendor inbox, customer status report", interactionHelp:"Think about the recurring report, summary, email stream, or feed people use as part of the work."},
  }[starterType];

  return <><h1>Discover Your Information</h1>
    <p className="lead">You do not need to know data-governance terminology. Start with the system, screen, file, folder, email, document, or report you already use. We will help identify the business information inside it.</p>
    <div className="ground-zero-roadmap discover-roadmap">
      {[
        {title:"Scope", body:"Define the business area and starting point."},
        {title:"Business context", body:"Name the real work and working source."},
        {title:"Information concept", body:"Identify the business information itself."},
        {title:"Business meaning", body:"Describe why the information matters."},
        {title:"Source & validation", body:"Record the location and next step."},
      ].map((item,index)=><div key={item.title} className={step >= index + 1 ? "ground-zero-roadmap-item active" : "ground-zero-roadmap-item"}>
        <span>{index + 1}</span>
        <div>
          <b>{item.title}</b>
          <small>{item.body}</small>
        </div>
      </div>)}
    </div>
    <div className="education strong"><b>What to do next</b><p>{discoverStepHelp[step] || "Keep moving through the guided steps until the item is recorded and ready for stewardship."}</p></div>

    {step===1&&<section className="panel discover-guide">
      <div className="eyebrow">Step 1 · Start with what you know</div>
      <h2>{starterCopy.heading}</h2>
      <p className="lead">Choose the place you are starting from, then describe the work it supports. We will turn that familiar starting point into a first governed information item.</p>
      <div className="touchpoint-grid">
        {starterOptions.map(([value,label,help])=><button type="button" key={value} className={starterType===value?"touchpoint selected":"touchpoint"} onClick={()=>setStarterType(value)}><b>{label}</b><span>{help}</span></button>)}
      </div>
      {systems?.length>0&&<div className="known-systems">
        <span>Already known:</span>
        {systems.map(s=><button type="button" key={s.id} className={systemName===s.name?"mini-choice selected":"mini-choice"} onClick={()=>{setSystemName(s.name);setSystemPurpose(s.business_purpose||"")}}>{s.name}</button>)}
      </div>}
      <label>{starterCopy.fieldLabel}<input value={systemName} onChange={e=>setSystemName(e.target.value)} placeholder={starterCopy.placeholder}/></label>
      <label>{starterCopy.purposeLabel}<textarea rows="4" value={systemPurpose} onChange={e=>setSystemPurpose(e.target.value)} placeholder={starterCopy.purposePlaceholder}/></label>
      <div className="button-row"><button className="primary" disabled={!systemName.trim()||!systemPurpose.trim()} onClick={()=>setStep(2)}>Continue</button></div>
      <div className="education"><b>Next step</b><p>After you continue, we will anchor this to a specific screen, file, folder, or report so the information is tied to a real working pattern.</p></div>
    </section>}

    {step===2&&<section className="panel discover-guide">
      <div className="eyebrow">Step 2 · Identify something people actually use</div>
      <h2>{starterCopy.interactionLabel.replace("{systemName}", systemName)}</h2>
      <p className="lead">{starterCopy.interactionHelp}</p>
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
      <label>What is it called?<input value={touchpointName} onChange={e=>setTouchpointName(e.target.value)} placeholder={starterCopy.interactionPlaceholder}/></label>
      <div className="button-row"><button onClick={()=>setStep(1)}>Back</button><button className="primary" disabled={!touchpointName.trim()} onClick={()=>setStep(3)}>Help me identify the information</button></div>
      <div className="education"><b>Next step</b><p>Once you name the working source, we will identify the actual information it contains rather than focusing on the tool itself.</p></div>
    </section>}

    {step===3&&<section className="panel discover-guide">
      <div className="eyebrow">Step 3 · Identify the business information</div>
      <h2>{starterType === "SYSTEM" ? `What business information does "${touchpointName}" manage?` : `What business information is in "${touchpointName}"?`}</h2>
      <p className="lead">Based on what you told us, these are possibilities—not automatic answers. Choose the one that best matches how your organization thinks about the information, or enter your own.</p>
      <div className="candidate-list guided-candidates">
        {candidates.map(c=><button type="button" className={informationName===c.name&&!customInformation?"info-candidate selected":"info-candidate"} key={c.name} onClick={()=>{setInformationName(c.name);setCustomInformation("")}}><b>{c.name}</b><span>{c.why}</span></button>)}
      </div>
      <div className="or-divider"><span>or describe it yourself</span></div>
      <label>Business information name<input value={customInformation} onChange={e=>{setCustomInformation(e.target.value);if(e.target.value)setInformationName("")}} placeholder="Use the name business staff would recognize"/></label>
      <div className="education"><b>What are we doing?</b><p>We are separating the <b>system</b> from the <b>information</b>. A system can manage several kinds of business information, and the same information can exist in several places.</p></div>
      <div className="button-row"><button onClick={()=>setStep(2)}>Back</button><button className="primary" disabled={!selectedInformation} onClick={()=>setStep(4)}>Continue</button></div>
      <div className="education"><b>Next step</b><p>Now that the information is named, describe what it helps the team do so the definition is usable by business people.</p></div>
    </section>}

    {step===4&&<section className="panel discover-guide">
      <div className="eyebrow">Step 4 · Describe why it exists</div>
      <h2>What does {selectedInformation} help your team do?</h2>
      <p className="lead">Describe the business purpose, not the technology. This becomes the starting description other employees will use to understand the information.</p>
      <textarea rows="5" value={businessUse} onChange={e=>setBusinessUse(e.target.value)} placeholder={starterType === "FILE" ? "For example: Track fee payments, reconcile submissions, and support financial review of active licenses." : starterType === "FOLDER" ? "For example: Keep a shared record of documents used to process applications and respond to inquiries." : starterType === "EMAIL" ? "For example: Monitor service issues, route requests, and keep a record of customer or program status updates." : "For example: Process business registrations, confirm filing status, and respond to public and agency questions about registered entities."}/>
      <div className="discovery-summary">
        <div><span>System</span><b>{systemName}</b></div>
        <div><span>Where you encountered it</span><b>{touchpointName}</b></div>
        <div><span>Business information</span><b>{selectedInformation}</b></div>
      </div>
      <div className="button-row"><button onClick={()=>setStep(3)}>Back</button><button className="primary" disabled={!businessUse.trim()} onClick={createAsset}>This looks right</button></div>
      <div className="education"><b>Next step</b><p>After this, we will record the actual location or representation and then help you confirm which one is the trusted business source.</p></div>
    </section>}

    {step===5&&createdAsset&&<section className="panel discover-guide">
      {completedResource?<div className="completion-state"><div className="completion-mark">✓</div><div><div className="eyebrow">Discovery recorded</div><h2>You identified where this information lives.</h2><p><b>{completedResource.assetName}</b> is connected to <b>{completedResource.resourceName}</b>. This is the start of a governed information record, not the final description. The next useful steps are to confirm the official source, define the business meaning, and assess whether the information can be trusted.</p><div className="next-milestones">
        <div className="next-milestone"><span>1</span><div><b>Confirm the official source</b><small>Decide which location the organization should rely on as the trusted source.</small></div></div>
        <div className="next-milestone"><span>2</span><div><b>Clarify the business meaning</b><small>Describe what the information is for and who it supports.</small></div></div>
        <div className="next-milestone"><span>3</span><div><b>Review trust and readiness</b><small>Check quality findings and determine whether the information is ready to share.</small></div></div>
      </div><div className="education strong"><b>Next steps</b><p>Open the information details page and complete the items marked “needs attention.” Those actions determine how confidently the organization can use and share this information.</p></div><div className="button-row"><button className="primary" onClick={()=>onDone(createdAsset.asset.asset_id)}>Continue to information details</button></div></div></div>:<>
      <div className="eyebrow">Step 5 · Record where the information lives</div>
      <h2>Where did you find {createdAsset.asset.name}?</h2>
      <p className="lead">You have identified the business information. Now record the screen, file, folder, document, report, database, or interface that represents it.</p>
      <div className="education strong"><b>Important</b><p>This is not yet declaring the official business source. You are simply recording a known place where the information exists. We will guide that decision separately.</p></div>
      <label>Name for this location or representation<input value={resourceName} onChange={e=>setResourceName(e.target.value)}/></label>
      <label>Where is it located? <span className="muted">(optional)</span><input value={locationReference} onChange={e=>setLocationReference(e.target.value)} placeholder="URL, folder path, database/schema/table, report name, or other locator"/></label>
      <details className="advanced-details"><summary>Technical details</summary>
        <div className="form-grid">
          <label>Representation type<select value={resourceType} onChange={e=>setResourceType(e.target.value)}><option value="APPLICATION_SCREEN">Application screen</option><option value="FILE">File</option><option value="DOCUMENT_LIBRARY">Document library</option><option value="EMAIL_COLLECTION">Email collection</option><option value="PDF_COLLECTION">PDF/document collection</option><option value="REPORT">Report/dashboard</option><option value="SPREADSHEET">Spreadsheet</option><option value="DATABASE_TABLE">Database table</option><option value="API">API</option><option value="OTHER">Other</option></select></label>
          <label>Structure<select value={structureType} onChange={e=>setStructureType(e.target.value)}><option value="STRUCTURED">Structured</option><option value="SEMI_STRUCTURED">Semi-structured</option><option value="UNSTRUCTURED">Unstructured</option></select></label>
        </div>
      </details>
      <div className="button-row"><button className="primary" disabled={!resourceName.trim()} onClick={addResource}>Finish discovery</button></div>
      <div className="education"><b>Next step</b><p>When this is saved, the item will be ready for the official-source and stewardship checks. That tells the organization what to rely on and what still needs attention.</p></div>
      </>}
    </section>}
  </>;
}

function Asset360({asset,assets,systems,tasks,role,userEmail,onDiscover,onNextSteps,selectedAssetId,setSelectedAssetId,doAction,tab,setTab,selectedQualityIssueId,setSelectedQualityIssueId,guidedTask,setGuidedTask}) {
  const [quality,setQuality]=useState(null), [metaKey,setMetaKey]=useState("theme"), [metaValue,setMetaValue]=useState("Professional Licensing"), [gov,setGov]=useState({});
  useEffect(()=>{if(asset){setGov({business_owner:asset.asset.business_owner||"",data_steward:asset.asset.data_steward||"",classification:asset.asset.classification||"",retention_requirement:asset.asset.retention_requirement||"",retention_authority:asset.asset.retention_authority||""});api(`/assets/${asset.asset.asset_id}/quality`,userEmail).then(setQuality)}},[asset?.asset?.asset_id,userEmail]);
  if(!asset)return <p>No information has been identified yet.</p>; const a=asset.asset;
  return <><div className="title-row"><div><h1>Information Details</h1><p className="lead">This page brings together what the information means, where it lives, how it is governed, whether it can be trusted, and whether it is ready to share.</p></div><select value={selectedAssetId||""} onChange={e=>setSelectedAssetId(Number(e.target.value))}>{assets.map(x=><option key={x.asset.asset_id} value={x.asset.asset_id}>{x.asset.name}</option>)}</select></div>
    <section className="asset-hero"><div><div className="eyebrow">{a.business_domain||"Business information"}</div><h2>{a.name}</h2><p>{a.business_definition}</p></div><div className="hero-scores"><div><span>Stewardship</span><strong>{asset.readiness.score}%</strong></div><div><span>Information trust</span><strong>{asset.quality?.overall_score != null ? `${asset.quality.overall_score}%` : "—"}</strong></div><Status value={asset.publication.status}/></div></section>
    <div className="tabs">{["Overview","Where It Lives","Help Others Understand It","Governance","Can This Information Be Trusted?","Review & Maintain","Share & Publish"].map(t=><button key={t} className={tab===t?"tab active":"tab"} onClick={()=>setTab(t)}>{t}</button>)}</div>
    {tab==="Overview"&&<InformationOverview asset={asset} tasks={tasks} setTab={setTab} setGuidedTask={setGuidedTask} setSelectedQualityIssueId={setSelectedQualityIssueId}/>}
    {tab==="Where It Lives"&&<WhereItLives asset={asset} userEmail={userEmail} onDiscover={onDiscover} doAction={doAction}/>}
    {tab==="Help Others Understand It"&&<UnderstandingGuide asset={asset} userEmail={userEmail} onNextSteps={onNextSteps} doAction={doAction} />}
    {tab==="Governance"&&<GovernanceGuide asset={asset} gov={gov} setGov={setGov} userEmail={userEmail} doAction={doAction} guidedTask={guidedTask} setGuidedTask={setGuidedTask}/>}
    {tab==="Can This Information Be Trusted?"&&<QualityPanel quality={quality} asset={asset} userEmail={userEmail} onLocation={()=>setTab("Where It Lives")} selectedQualityIssueId={selectedQualityIssueId} setSelectedQualityIssueId={setSelectedQualityIssueId} doAction={async(fn,msg)=>{await doAction(fn,msg);setQuality(await api(`/assets/${a.asset_id}/quality`,userEmail))}}/>}
    {tab==="Review & Maintain"&&<PeriodicReviewPanel asset={asset} userEmail={userEmail} onNextSteps={onNextSteps} doAction={doAction} guidedTask={guidedTask} setGuidedTask={setGuidedTask}/>}
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
      label:"Information trust",
      complete:qualityCurrent,
      text:qualityCurrent
        ? `Last quality score: ${asset.quality?.overall_score!=null?`${asset.quality.overall_score}%`:"assessed"}. This is separate from submission readiness.`
        : "Quality has not yet been assessed for this information. Trust and readiness are separate decisions.",
      tab:"Can This Information Be Trusted?",
    },
    {
      key:"publish",
      label:"Ready to submit",
      complete:publishReady,
      text:publishReady?"Required stewardship checks are complete. This means the item is ready to submit for review, not that trust has been fully established.":"Required stewardship work remains before submission. Trust is reviewed separately from readiness.",
      tab:"Share & Publish",
    },
  ];

  function openTask(task){
    const route=routeForTask(task);
    if(!route) return;
    setGuidedTask(route.guided);
    setSelectedQualityIssueId(route.qualityIssueId);
    setTab(route.tab);
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
      <div className="eyebrow">Next milestones</div>
      <h2>Keep moving from discovery into stewardship</h2>
      <p className="lead">Once the landscape record exists, the work gets more specific: confirm the source, describe the business meaning, and review whether the information can be trusted.</p>
      <div className="next-milestones">
        <button type="button" className="next-milestone" onClick={()=>setTab("Where It Lives")}>
          <span>1</span>
          <div><b>Confirm the official source</b><small>Decide which location the organization should rely on when versions differ.</small></div>
        </button>
        <button type="button" className="next-milestone" onClick={()=>setTab("Help Others Understand It")}>
          <span>2</span>
          <div><b>Clarify business meaning</b><small>Describe what the information helps the team do and who it supports.</small></div>
        </button>
        <button type="button" className="next-milestone" onClick={()=>setTab("Can This Information Be Trusted?")}>
          <span>3</span>
          <div><b>Review trust and readiness</b><small>Check quality findings and stewardship readiness before publication.</small></div>
        </button>
      </div>
    </section>

    <section className="panel">
      <div className="task-head">
        <div><div className="eyebrow">Stewardship status</div><h2>What is complete and what still needs attention</h2><p className="lead">You do not need to choose a governance module. Open any item for context, or follow the recommended next action above.</p></div>
        <div className="overview-completeness"><strong>{asset.readiness?.score??0}%</strong><span>complete</span></div>
      </div>

      <div className="stewardship-status-list">
        {statusItems.map(item=><button key={item.key} type="button" className={item.complete?"stewardship-status complete":"stewardship-status attention"} onClick={()=>setTab(item.tab)}>
          <span className="status-icon">{item.complete?"✓":"!"}</span>
          <div><b>{item.label}</b><small>{item.text}</small></div>
          <span className="status-open">{item.complete?"Complete · View details":"Needs attention →"}</span>
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

function WhereItLives({asset,userEmail,onDiscover,doAction}) {
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
    const saved=await doAction(
      ()=>api(`/assets/${a.asset_id}/official-source`,userEmail,{
        method:"POST",
        body:JSON.stringify({
          resource_id:s.resource_id,
          decision_basis:basis.trim()||recommendationText()
        })
      }),
      `${s.name} is now recorded as the official source.`
    );
    if(!saved) return;
    setMode("LIST");
    setStep(1);
  }

  if(mode==="GUIDE"){
    return <section className="panel official-source-guide">
      <div className="wizard-head">
        <div><div className="eyebrow">Guided task · Official source</div><h2>Which location should people rely on as official?</h2><p className="lead">The same business information can exist in a database, download, report, spreadsheet, document library, or other location. We will help you identify which one should be trusted when those versions differ.</p></div>
        <span>Step {step} of 5</span>
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
        <h3>Is {selected()?.name} where the information is created or officially maintained?</h3>
        <p className="lead">The official source is usually the place where the business process creates or maintains the record, rather than a report or download made from it.</p>
        <Choice value={originAnswer} setValue={setOriginAnswer} options={[["yes","Yes — the record is created or maintained here"],["no","No — this location receives or copies the information"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(1)}>Back</button><button className="primary" disabled={!originAnswer||originAnswer==="unsure"} onClick={()=>setStep(3)}>Continue</button></div>
        {originAnswer==="unsure"&&<div className="education strong"><b>Good choice—do not guess.</b><p>Ask the team that creates or maintains the information where the official record is kept.</p></div>}
      </>}

      {step===3&&<>
        <h3>If two versions disagreed, would the organization rely on {selected()?.name}?</h3>
        <p className="lead">Imagine a report, spreadsheet, or download shows one value and this location shows another. Which one would staff treat as the official record for a business decision?</p>
        <Choice value={conflictAnswer} setValue={setConflictAnswer} options={[["yes","Yes — this is what we would rely on"],["no","No — another location would be considered official"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(2)}>Back</button>{conflictAnswer==="no"?<button className="primary" onClick={()=>{setSelectedId("");setConflictAnswer("");setOriginAnswer("");setStep(1)}}>Choose a different location</button>:<button className="primary" disabled={!conflictAnswer||conflictAnswer==="unsure"} onClick={()=>setStep(4)}>Continue</button>}</div>
        {conflictAnswer==="unsure"&&<div className="education strong"><b>Good choice—do not guess.</b><p>Confirm this with the business owner or the team responsible for the process before making an official-source decision.</p></div>}
      </>}

      {step===4&&<>
        <h3>Is {selected()?.name} mainly a copy, export, report, or working extract?</h3>
        <p className="lead">Copies can be useful and trustworthy, but they usually should not be labeled the official source if another location is where the record is actually maintained.</p>
        <Choice value={copyAnswer} setValue={setCopyAnswer} options={[["no","No — the official record is maintained here"],["yes","Yes — this is mainly a copy, export, report, or extract"],["unsure","I’m not sure"]]}/>
        <div className="button-row"><button onClick={()=>setStep(3)}>Back</button>{copyAnswer==="yes"?<button className="primary" onClick={()=>{setSelectedId("");setCopyAnswer("");setOriginAnswer("");setStep(1)}}>Choose a different location</button>:<button className="primary" disabled={!copyAnswer||copyAnswer==="unsure"} onClick={reviewRecommendation}>Review recommendation</button>}</div>
        {copyAnswer==="unsure"&&<div className="education strong"><b>Good choice—verify it first.</b><p>Ask whether this location is where the official record is maintained or whether it is generated from another source.</p></div>}
      </>}

      {step===5&&<>
        <h3>Recommended official source</h3>
        <div className="recommendation-card">
          <span>AI Data Steward recommends</span>
          <strong>{selected()?.name}</strong>
          <p>{basis}</p>
        </div>
        <div className="education"><b>What this decision means</b><p>Other known locations can still be useful. This simply records which one people should rely on when they need the official business record.</p></div>
        <label>Why is this the official source?<textarea rows="4" value={basis} onChange={e=>setBasis(e.target.value)} /></label>
        <div className="button-row"><button onClick={()=>setStep(4)}>Back</button><button className="primary" onClick={confirmOfficial}>Confirm official source</button></div>
      </>}
    </section>;
  }

  return <section className="panel">
    <div className="task-head">
      <div><div className="eyebrow">Where it lives</div><h2>Known locations and representations</h2><p className="lead">The same information can exist in more than one place. Record those places here, then identify which one should be relied on as the official business source.</p></div>
      <button className="primary" disabled={locations.length===0} onClick={()=>{setMode("GUIDE");setStep(1);setSelectedId(currentOfficial?.resource_id||"")}}>{currentOfficial?"Review official source":"Determine official source"}</button>
    </div>
    <div className="education strong"><b>What to do next</b><p>{currentOfficial ? "The official source is already identified. Review it if the organization’s understanding has changed, or continue to the other stewardship tasks for this information." : "The next important decision is choosing which location the organization should rely on as the official business source before the item is treated as fully governed."}</p></div>

    {locations.length===0&&<div className="empty"><p>No locations have been recorded yet.</p><button className="primary" onClick={onDiscover}>Add a location in Discover Information</button></div>}

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

function friendlyReadinessTitle(value){
  return {
    "Business definition":"What this information means",
    "Business owner":"Who is accountable for business decisions",
    "Data steward":"Who coordinates stewardship",
    "Where the information lives":"Where the information lives",
    "Business area":"What business area it supports",
    "Search terms":"How people can find it",
    "Update frequency":"How often it changes",
    "Contact point":"Who can answer questions",
    "Authoritative source":"Official business source",
    "Classification":"How it should be handled",
    "Retention requirement":"How long it should be kept",
    "Data quality assessed":"Information trust assessed"
  }[value]||value;
}

function roleResponsibility(role){
  return {
    STEWARD:"Your focus: understand, govern, and maintain information.",
    APPROVER:"Your focus: review submitted stewardship work.",
    ORG_ADMIN:"Your focus: manage users and support stewardship decisions.",
    VIEWER:"Your focus: find and understand governed information.",
    ENTERPRISE_ADMIN:"Your focus: oversee organization-wide governance and publication."
  }[role]||"Your role determines which stewardship actions are available.";
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

function PeriodicReviewPanel({asset,userEmail,onNextSteps,doAction,guidedTask,setGuidedTask}) {
  const a=asset.asset;
  const [reviewData,setReviewData]=useState(null);
  const [mode,setMode]=useState(["PERIODIC_REVIEW","PERIODIC_REVIEW_CHANGE"].includes(guidedTask?.source_type)?"REVIEW":"SUMMARY");
  const [step,setStep]=useState(1);
  const [answers,setAnswers]=useState({});
  const [notes,setNotes]=useState("");
  const [result,setResult]=useState(null);

  useEffect(()=>{
    api(`/assets/${a.asset_id}/reviews`,userEmail).then(setReviewData).catch(()=>setReviewData(null));
  },[a.asset_id,userEmail]);

  useEffect(()=>{
    if(["PERIODIC_REVIEW","PERIODIC_REVIEW_CHANGE"].includes(guidedTask?.source_type)){
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
        <NextStepCallout title="What to do next" body="Answer the current question truthfully and choose the option that reflects the real business state. If you are unsure, choose the uncertain option and the system will create a focused follow-up instead of forcing a guess." />
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
        <NextStepCallout title="What to do next" body={changedKeys.length===0 ? "Confirm the review and record that the current stewardship decisions still reflect the business reality. No additional follow-up work is required unless something changes later." : `Review the items that were flagged and use the resulting follow-up tasks to fix the specific gaps before the next stewardship cycle.`} />
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
      <div className="button-row">{result?.follow_up_tasks?.length>0&&<button className="primary" onClick={onNextSteps}>Open My Next Steps</button>}<button onClick={()=>setMode("SUMMARY")}>View review history</button></div>
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

function UnderstandingGuide({asset,userEmail,onNextSteps,doAction}) {
  const a=asset.asset;
  const existing=asset.metadata||{};
  const [step,setStep]=useState(1);
  const [businessArea,setBusinessArea]=useState(existing.theme||a.business_domain||"");
  const [audienceNeed,setAudienceNeed]=useState("");
  const [searchTerms,setSearchTerms]=useState(
    Array.isArray(existing.keyword) ? existing.keyword.join(", ") : (existing.keyword||"")
  );
  function firstMetadataValue(value){
    return Array.isArray(value) ? (value[0] ?? "") : value;
  }

  function normalizeUpdatePattern(value){
    const raw=firstMetadataValue(value);
    if(!raw) return "";
    const normalized=String(raw).trim().toUpperCase().replace(/[\s-]+/g,"_");
    const exact=["CONTINUOUS","DAILY","WEEKLY","MONTHLY","QUARTERLY","ANNUALLY","EVENT_DRIVEN","UNKNOWN"];
    if(exact.includes(normalized)) return normalized;
    if(normalized.includes("CONTINU")) return "CONTINUOUS";
    if(normalized.includes("DAILY") || normalized.includes("DAY")) return "DAILY";
    if(normalized.includes("WEEK")) return "WEEKLY";
    if(normalized.includes("MONTH")) return "MONTHLY";
    if(normalized.includes("QUART")) return "QUARTERLY";
    if(normalized.includes("ANNU") || normalized.includes("YEAR")) return "ANNUALLY";
    if(normalized.includes("EVENT")) return "EVENT_DRIVEN";
    if(normalized.includes("UNKNOWN") || normalized.includes("UNSURE") || normalized.includes("NOT_SURE")) return "UNKNOWN";
    return "";
  }

  const [updatePattern,setUpdatePattern]=useState(normalizeUpdatePattern(existing.update_frequency));
  const rawContact=firstMetadataValue(existing.contact);
  const existingContact =
    rawContact && typeof rawContact === "object"
      ? rawContact
      : { name: rawContact || "", email: "" };

  const [contactName,setContactName]=useState(String(existingContact.name || ""));
  const [contactEmail,setContactEmail]=useState(String(existingContact.email || ""));
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
      contact_point: {
        name: contactName.trim(),
        email: contactEmail.trim() || null
      }
    };

    const saved=await doAction(
      ()=>api(`/assets/${a.asset_id}/understanding`,userEmail,{
        method:"PATCH",
        body:JSON.stringify(payload)
      }),
      "Information description saved."
    );
    if(saved) setStep(6);
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
      <label>
  If someone has a business question, who should they contact?
  <input
    value={contactName}
    onChange={e=>setContactName(e.target.value)}
    placeholder="Person, team, or business office"
  />
</label>

<label>
  Email or shared mailbox
  <input
    type="email"
    value={contactEmail}
    onChange={e=>setContactEmail(e.target.value)}
    placeholder="data@example.gov"
  />
</label>

      <div className="understanding-summary">
        <div><span>Business area</span><b>{businessArea}</b></div>
        <div><span>Search terms</span><b>{searchTerms||"Not entered"}</b></div>
        <div><span>How it changes</span><b>{updatePattern||"Not selected"}</b></div>
        <div><span>Contact</span><b>{contactName||"Not entered"}{contactEmail?` · ${contactEmail}`:""}</b></div>
      </div>

      <div className="button-row"><button onClick={()=>setStep(4)}>Back</button><button className="primary" disabled={!updatePattern||!contactName.trim()} onClick={save}>Save this description</button></div>

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
      <div className="button-row"><button onClick={()=>setStep(1)}>Review or update these answers</button><button className="primary" onClick={onNextSteps}>Open My Next Steps</button></div>
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
    const saved=await doAction(
      async()=>{
        await api(`/assets/${a.asset_id}/governance`,userEmail,{method:"PATCH",body:JSON.stringify(patch)});
        // Readiness tasks often close automatically when the asset is refreshed,
        // but review follow-ups are explicit work items. Close the task that
        // launched this wizard after its decision has been persisted.
        if(guidedTask?.id){
          await api(`/tasks/${guidedTask.id}/complete`,userEmail,{method:"POST",body:JSON.stringify({})});
        }
      },
      message
    );
    if(!saved) return;
    setGov({...gov,...patch});
    setGuidedTask(null);
    setMode("");
    setStep(1);
  }

  async function askExpert(label){
    if(!guidedTask?.id) return;
    const saved=await doAction(
      ()=>api(`/tasks/${guidedTask.id}/expert-review`,userEmail,{method:"POST"}),
      `${label} has been moved to Waiting on Others for expert review.`
    );
    if(!saved) return;
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
          <button type="button" className={retentionKnown==="unsure"?"choice selected":"choice"} onClick={()=>{setRetentionKnown("unsure");setStep(4)}}>I’m not sure yet — ask Records Management</button>
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

function QualityPanel({quality,asset,userEmail,onLocation,doAction,selectedQualityIssueId,setSelectedQualityIssueId}) {
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

  async function refreshAction(fn,msg){ return doAction(fn,msg); }

  return <>
    <section className="panel decision-outcome-guide"><div className="eyebrow">Before you decide</div><h3>What happens after I choose?</h3><div className="decision-outcome-list"><div><b>The data is incorrect</b><span>Creates work to investigate and correct the source data.</span></div><div><b>This is a valid exception</b><span>Records that the business accepts this pattern for its current use.</span></div><div><b>The quality expectation needs to change</b><span>Starts work to update what the organization expects.</span></div><div><b>I need expert review</b><span>Moves the item to a waiting state for someone with the right expertise.</span></div></div></section>
    <section className="panel quality-trust-first">
      <div className="eyebrow">Information trust</div>
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
        <button className="primary" disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/assess`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Information check completed. Review any findings that need a stewardship decision.")}>Create an initial quality picture</button>
        <button disabled={!resourceId} onClick={()=>refreshAction(()=>api(`/assets/${asset.asset.asset_id}/quality/run`,userEmail,{method:"POST",body:JSON.stringify({resource_id:Number(resourceId)})}),"Approved quality checks ran. Any findings that need attention were added to stewardship work.")}>Run the checks we agreed to use</button>
      </div>
      <p className="muted quality-action-help">Start with an initial quality picture. After you review the suggested expectations, run the checks you agree should represent how this information is used.</p>

      {structured.length===0&&<div className="education strong"><b>Record a structured location before starting an automated quality check.</b><p>Documents and document libraries are still covered by description, classification, retention, ownership, and other stewardship work. When this information has a structured source, record it in Where It Lives so the checks can begin.</p><button onClick={onLocation}>Go to Where It Lives</button></div>}

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

    <section className="panel"><h2>What should this information reliably do?</h2><p className="muted">These expectations describe what the business needs to be true about the information. AI Data Steward turns failed checks into guided stewardship work rather than treating them as automatic errors.</p>{quality?.rules?.length?quality.rules.map(r=><div className="rule" key={r.id}><div><b>{r.plain_language_rule}</b><span>{friendlyType(r.rule_type)} · {r.status==="PROPOSED"?"Suggested expectation":r.status}</span>{r.status==="PROPOSED"&&<small>Use this only if it matches how your team relies on the information.</small>}{r.latest_result&&<small>{r.latest_result.failed_count||0} affected records in the latest run</small>}</div><div className="button-row mini">{r.status==="PROPOSED"&&<><button className="primary" onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"APPROVED"})}),"Quality expectation approved. It can now be included in checks.")}>Use this expectation</button><button onClick={()=>refreshAction(()=>api(`/quality/rules/${r.id}/status`,userEmail,{method:"PATCH",body:JSON.stringify({status:"REJECTED"})}),"Quality expectation rejected. It will not be used in checks.")}>Do not use it</button></>}</div></div>):<p>Start an initial quality picture to see suggested expectations.</p>}</section>

    <section className="panel"><h2>Findings that need a stewardship decision</h2><p className="muted">A finding means something is worth reviewing. It does not automatically mean the information is wrong. Use the evidence and business context to decide what it means.</p>{openIssues.length===0&&<EmptyState title="No findings need a decision." text="New findings will appear here after future checks when they need stewardship review."/>}{openIssues.map(i=>{const evidence=i.details?.evidence||{};const samples=evidence.sample_values?.length?evidence.sample_values:i.details?.sample_values;const isProfile=i.issue_type==="HYGIENE_FINDING";const summary=i.details?.finding_summary||{};return <div className={`quality-issue severity-${i.severity.toLowerCase()}`} key={i.id}><div className="task-head"><div><div className="eyebrow">{i.source} · {isProfile?"PROFILING FINDING":"QUALITY CHECK FAILURE"}</div><h3>{i.title}</h3></div><span className="priority">{i.severity}</span></div><p>{i.description}</p>{isProfile&&<><div className="finding-summary-grid"><Metric label="Needs review" value={summary.pending??i.details?.finding_count??0}/><Metric label="Reviewed" value={summary.resolved??0}/><Metric label="Expert review" value={summary.escalated??0}/><Metric label="Potential PII" value={i.details?.potential_pii_count||0}/></div><p className="muted">You do not need to understand the quality engine’s terminology. AI Data Steward translates each finding into what it means, why it matters, and what to do next.</p></>}{!isProfile&&<div className="evidence-grid">{evidence.status&&<Metric label="Result" value={evidence.status}/>} {evidence.test_type&&<Metric label="Check type" value={friendlyType(evidence.test_type)}/>} {evidence.evaluated_count!=null&&<Metric label="Records evaluated" value={Number(evidence.evaluated_count).toLocaleString()}/>} {i.failed_count!=null&&<Metric label="Records affected" value={i.failed_count.toLocaleString()}/>} {evidence.score!=null&&<Metric label="Check score" value={`${evidence.score}%`}/>}</div>}{evidence.columns?.length>0&&<p><b>Fields:</b> {evidence.columns.join(", ")}</p>}{samples?.length>0&&<div className="sample-values"><b>Example evidence</b><span>{samples.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<button className="primary" onClick={()=>{setSelectedQualityIssueId(i.id);setNotes("");if(isProfile){setHygieneIssue(i);setDecisionIssue(null);setSelectedHygieneFinding(null);window.setTimeout(()=>document.getElementById("profiling-workbench")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}else{setDecisionIssue(i);setHygieneIssue(null);window.setTimeout(()=>document.getElementById("guided-investigation")?.scrollIntoView({behavior:"smooth",block:"start"}),100)}}}>{isProfile?"Review findings":"Guide Me"}</button></div>})}</section>

    {hygieneIssue&&<section id="profiling-workbench" className="panel guide-panel"><div className="eyebrow">Profiling findings workbench</div><h2>Review findings one at a time</h2><div className="next-step-callout"><b>What to do next</b><span>Start with the first item marked <strong>Needs review</strong>. Read what TestGen found, check why it matters, then choose the stewardship decision that best matches the business reality. Work through the list one finding at a time.</span></div><p className="muted">The quality check found patterns in the information. These are observations, not automatic errors.</p><div className="finding-progress"><b>{hygieneIssue.details?.finding_summary?.pending??0} need review</b><span>{hygieneIssue.details?.finding_summary?.resolved??0} reviewed · {hygieneIssue.details?.finding_summary?.escalated??0} sent for expert review</span></div><div className="finding-list">{(hygieneIssue.details?.steward_findings||[]).map(f=><div key={f.fingerprint} className={`steward-finding status-${(f.review_status||"PENDING").toLowerCase()}`}><div className="task-head"><div><div className="eyebrow">{f.column} · {friendlyType(f.category)}</div><h3>{f.title}</h3></div><span className="finding-status">{f.review_status==="RESOLVED"?"Reviewed":f.review_status==="ESCALATED"?"Expert review":"Needs review"}</span></div><p><b>Why it matters</b><br/>{f.why_it_matters}</p><p><b>Recommended next step</b><br/>{f.recommended_action}</p>{f.affected_count!=null&&<p><b>{Number(f.affected_count).toLocaleString()}</b> affected records</p>}{f.examples?.length>0&&<div className="sample-values"><b>Example evidence</b><span>{f.examples.map(v=>v===null?"(missing)":String(v)).join(" · ")}</span></div>}<details className="technical-detail"><summary>Technical finding details</summary><code>{f.testgen_finding}</code></details><button className={f.review_status==="PENDING"?"primary":""} onClick={()=>{setSelectedHygieneFinding(f);setNotes(f.notes||"");window.setTimeout(()=>document.getElementById("finding-decision")?.scrollIntoView({behavior:"smooth",block:"center"}),100)}}>{f.review_status==="PENDING"?"Review this finding":"Review decision"}</button></div>)}</div></section>}
    {hygieneIssue&&selectedHygieneFinding&&<section id="finding-decision" className="panel guide-panel finding-decision"><div className="eyebrow">Guided finding review</div><h2>{selectedHygieneFinding.title}</h2><div className="finding-decision-context"><div><span>Field</span><b>{selectedHygieneFinding.column||"—"}</b></div><div><span>Category</span><b>{friendlyType(selectedHygieneFinding.category||"PROFILE")}</b></div><div><span>Status</span><b>{selectedHygieneFinding.review_status==="RESOLVED"?"Reviewed":selectedHygieneFinding.review_status==="ESCALATED"?"Expert review":"Needs review"}</b></div>{selectedHygieneFinding.affected_count!=null&&<div><span>Affected records</span><b>{Number(selectedHygieneFinding.affected_count).toLocaleString()}</b></div>}{selectedHygieneFinding.confidence&&<div><span>TestGen confidence</span><b>{selectedHygieneFinding.confidence}</b></div>}</div><div className="finding-decision-detail"><div><b>What TestGen found</b><p>{selectedHygieneFinding.testgen_finding||"Profiling observation"}</p></div><div className="evidence-panel"><div className="evidence-panel-head"><div><b>Evidence available for this decision</b><p className="muted">Review the evidence before choosing a stewardship decision.</p></div><span className={`evidence-level evidence-${(selectedHygieneFinding.evidence?.sufficiency?.level||"LOW").toLowerCase()}`}>{selectedHygieneFinding.evidence?.sufficiency?.level||"LOW"} evidence</span></div>{selectedHygieneFinding.evidence?.testgen?.observed_values?.length>0&&<div className="evidence-block"><b>Observed value{selectedHygieneFinding.evidence.testgen.observed_values.length===1?"":"s"}</b><div className="evidence-values">{selectedHygieneFinding.evidence.testgen.observed_values.map((v,idx)=><code key={idx}>{v===null?"(missing)":String(v)}</code>)}</div></div>}{selectedHygieneFinding.evidence?.testgen?.detail&&<div className="evidence-block"><b>TestGen evidence</b><p>{selectedHygieneFinding.evidence.testgen.detail}</p>{selectedHygieneFinding.evidence.testgen.records_profiled!=null&&<p><b>{Number(selectedHygieneFinding.evidence.testgen.records_profiled).toLocaleString()}</b> records were profiled.</p>}</div>}{selectedHygieneFinding.evidence?.testgen?.affected_count!=null&&<div className="evidence-block"><b>Estimated impact</b><p><b>{Number(selectedHygieneFinding.evidence.testgen.affected_count).toLocaleString()}</b> records match this finding{selectedHygieneFinding.evidence.testgen.affected_percent!=null?` (${selectedHygieneFinding.evidence.testgen.affected_percent}%)`:""}.</p></div>}{selectedHygieneFinding.evidence?.testgen?.patterns?.length>0&&<div className="evidence-block"><b>Observed format distribution</b><div className="pattern-list">{selectedHygieneFinding.evidence.testgen.patterns.map((p,idx)=><span key={idx}><code>{p.pattern}</code><b>{Number(p.count).toLocaleString()}</b></span>)}</div></div>}{selectedHygieneFinding.evidence?.testgen?.semantic_type&&<div className="evidence-block"><b>Detected semantic type</b><p>{selectedHygieneFinding.evidence.testgen.semantic_type}</p></div>}{selectedHygieneFinding.evidence?.testgen?.minimum_value&&<div className="evidence-block"><b>Minimum observed value</b><p><code>{selectedHygieneFinding.evidence.testgen.minimum_value}</code></p></div>}{selectedHygieneFinding.evidence?.testgen?.affected_count!=null&&<div className="evidence-block"><b>How common is it?</b><p>{Number(selectedHygieneFinding.evidence.testgen.affected_count).toLocaleString()} affected record{Number(selectedHygieneFinding.evidence.testgen.affected_count)===1?"":"s"}{selectedHygieneFinding.evidence?.profile_context?.row_count?` out of ${Number(selectedHygieneFinding.evidence.profile_context.row_count).toLocaleString()} profiled records`:""}.</p></div>}{Object.keys(selectedHygieneFinding.evidence?.profile_context||{}).length>0&&<div className="evidence-block"><b>Profile context for {selectedHygieneFinding.column}</b><div className="profile-context-grid">{selectedHygieneFinding.evidence.profile_context.data_type&&<Metric label="Data type" value={selectedHygieneFinding.evidence.profile_context.data_type}/>} {selectedHygieneFinding.evidence.profile_context.semantic_type&&<Metric label="Detected meaning" value={selectedHygieneFinding.evidence.profile_context.semantic_type}/>} {selectedHygieneFinding.evidence.profile_context.row_count!=null&&<Metric label="Rows profiled" value={Number(selectedHygieneFinding.evidence.profile_context.row_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.distinct_count!=null&&<Metric label="Distinct values" value={Number(selectedHygieneFinding.evidence.profile_context.distinct_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.null_count!=null&&<Metric label="Missing values" value={Number(selectedHygieneFinding.evidence.profile_context.null_count).toLocaleString()}/>} {selectedHygieneFinding.evidence.profile_context.null_percent!=null&&<Metric label="Missing %" value={`${selectedHygieneFinding.evidence.profile_context.null_percent}%`}/>} {selectedHygieneFinding.evidence.profile_context.min_length!=null&&<Metric label="Shortest length" value={selectedHygieneFinding.evidence.profile_context.min_length}/>} {selectedHygieneFinding.evidence.profile_context.max_length!=null&&<Metric label="Longest length" value={selectedHygieneFinding.evidence.profile_context.max_length}/>} {selectedHygieneFinding.evidence.profile_context.avg_length!=null&&<Metric label="Typical length" value={selectedHygieneFinding.evidence.profile_context.avg_length}/>}</div>{selectedHygieneFinding.evidence.profile_context.typical_values?.length>0&&<div className="typical-values"><b>Typical / common values</b>{selectedHygieneFinding.evidence.profile_context.typical_values.map((item,idx)=><span key={idx}><code>{String(item.value)}</code>{item.count!=null&&` · ${Number(item.count).toLocaleString()} records`}</span>)}</div>}</div>}<div className="evidence-block source-evidence"><b>Source-record verification</b><p>{selectedHygieneFinding.evidence?.source_record_context?.message||"Open the source system or ask the data owner to verify the underlying record when the profile evidence is not enough."}</p></div><div className={`evidence-guidance evidence-${(selectedHygieneFinding.evidence?.sufficiency?.level||"LOW").toLowerCase()}`}><b>{selectedHygieneFinding.evidence?.sufficiency?.level==="LOW"?"More evidence is needed before making a confident decision":"Evidence guidance"}</b><p>{selectedHygieneFinding.evidence?.sufficiency?.guidance||"Verify the source record or consult a business expert before deciding."}</p>{selectedHygieneFinding.evidence?.sufficiency?.limitations?.length>0&&<ul>{selectedHygieneFinding.evidence.sufficiency.limitations.map((x,idx)=><li key={idx}>{x}</li>)}</ul>}</div></div><div><b>Why it matters</b><p>{selectedHygieneFinding.why_it_matters}</p></div><div><b>Recommended next step</b><p>{selectedHygieneFinding.recommended_action}</p></div></div><p><b>What should you decide?</b> Pick the option that best matches the business reality. If the evidence is limited, verify the source or use expert review rather than guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","This data needs correction"],["VALID_EXCEPTION","This is acceptable as-is"],["EXPECTATION_NEEDS_CHANGE","Create or adjust a quality expectation"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${hygieneIssue.id}/findings/${encodeURIComponent(selectedHygieneFinding.fingerprint)}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Finding decision recorded: ${label}.`).then(()=>{setSelectedHygieneFinding(null);setNotes("");})}>{label}</button>)}</div></section>}
    {decisionIssue&&<section id="guided-investigation" className="panel guide-panel"><div className="eyebrow">Guided investigation</div><h2>{decisionIssue.title}</h2><p><b>Step 1 — Understand what TestGen found.</b> {decisionIssue.issue_type==="HYGIENE_FINDING"?"A profiling finding highlights a characteristic or pattern that deserves review; it is not a failed rule by itself.":"A quality check did not pass. Review the affected records, fields, and evidence before deciding why."}</p><p><b>Step 2 — Make a stewardship decision.</b> Choose the explanation that best matches what you know. If you cannot determine it, escalate instead of guessing.</p><label>Notes / evidence</label><textarea rows="3" value={notes} onChange={e=>setNotes(e.target.value)} placeholder="What did you learn? Who did you confirm this with?"/><div className="decision-grid">{[["BAD_DATA","The data is incorrect"],["VALID_EXCEPTION","This is a valid exception"],["EXPECTATION_NEEDS_CHANGE","The quality expectation needs to change"],["EXPERT_REVIEW","I need expert review"]].map(([value,label])=><button key={value} onClick={()=>refreshAction(()=>api(`/quality/issues/${decisionIssue.id}/decision`,userEmail,{method:"POST",body:JSON.stringify({decision_type:value,notes})}),`Decision recorded: ${label}.`).then(()=>{setDecisionIssue(null);setSelectedQualityIssueId(null)})}>{label}</button>)}</div></section>}
  </>;
}

function PublicationPanel({asset,role,userEmail,doAction}) {
  const [reviewNotes,setReviewNotes]=useState("");
  const [pendingDecision,setPendingDecision]=useState(null);
  const required=asset.readiness.checks.filter(c=>c.required);
  const missing=required.filter(c=>!c.complete);
  const ready=missing.length===0;
  const status=asset.publication.status;
  const qualityScore = asset.quality?.overall_score != null ? Number(asset.quality.overall_score) : null;
  const qualityAssessed = Boolean(asset.quality && (asset.quality.overall_score != null || asset.quality.profiles?.length || asset.quality.rules?.length || asset.quality.issues?.length));
  const qualityLabel = qualityAssessed ? (qualityScore != null ? `${qualityScore}%` : "Assessment in progress") : "Not assessed yet";
  const workflowStatus=status==="IN_REVIEW"?"Waiting for review":status==="APPROVED"?"Approved release":status==="PUBLISHED"?"Published":status==="REJECTED"?"Returned for changes":status==="NEEDS_UPDATE"?"Update required":ready?"Ready to submit":"Needs your input";

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
        ? "Required stewardship work is complete. This means the item is ready to submit for review; a quality score is separate evidence about trust, not the same thing as publication readiness."
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
        <h2>{workflowStatus}</h2>
        <p className="lead">{roleGuidance()}</p>
      </div>
      <div className="role-responsibility"><span>Your role</span><b>{roleName}</b></div>
    </div>

    <NextStepCallout title="What to do next" body={status === "IN_REVIEW" ? "Review the submission and either approve it or return it with clear notes about what still needs to change." : status === "APPROVED" ? "Publish the approved release when your organization is ready, or continue stewarding the item if more changes are needed." : status === "PUBLISHED" ? "Monitor for later changes and complete a new review when the stewardship context changes." : ready ? "Complete the required stewardship checks, then submit this information for review." : "Finish the remaining required stewardship work before submitting for review."} />

    <div className={`publication-readiness ${ready?"ready":"not-ready"}`}>
      <strong>{required.length-missing.length} of {required.length}</strong>
      <span>required checks complete before review</span>
    </div>

    <div className="publication-state-summary"><div><span>Submission readiness</span><b>{ready?"Ready to submit":"Needs your input"}</b></div><div><span>Information trust</span><b>{qualityLabel}</b></div><div><span>Publication</span><b>{status.replaceAll("_"," ")}</b></div></div>

    <div className="education strong"><b>Important</b><p><b>Submission readiness</b> and <b>information trust</b> are separate. When the required stewardship checks are complete, an item is ready to submit for review. A quality score reflects confidence in the information itself and is assessed separately.</p></div>

    {required.map(c=><div className="readiness-row" key={c.key}>
      <span className={c.complete?"ok":"warn"}>{c.complete?"✓":"!"}</span>
      <div><b>{friendlyReadinessTitle(c.title)}</b><small>{c.complete?"Complete":c.guidance}</small></div>
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
        <div><b>Your next action</b><p>{ready?"Send this information to an approver. Submission does not publish it. This readiness check is separate from information trust and quality scoring.":"Complete the required stewardship checks before sending this for review."}</p></div>
        <button className="primary" disabled={!ready} onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/submit`,userEmail,{method:"POST",body:JSON.stringify({comments:"Stewardship checks complete; ready for review."})}),"Submitted for review.")}>Submit for review</button>
      </>}

      {!canReview&&status==="IN_REVIEW"&&<div className="waiting-publication"><span className="waiting-pill">Waiting</span><div><b>Waiting for an approver</b><p>No publication action is required from you right now.</p></div></div>}

      {canReview&&status==="IN_REVIEW"&&<>
        <div><b>Your review decision</b><p>Confirm that the required stewardship information is suitable for an approved release, or return it to the steward with changes needed.</p></div>
        <label>Review notes{pendingDecision==="RETURN"&&<span className="field-required"> Required to explain what must change</span>}<textarea rows="3" value={reviewNotes} onChange={e=>setReviewNotes(e.target.value)} placeholder="What did you confirm, or what should the steward address?"/></label>
        {pendingDecision?<div className="decision-confirmation"><b>{pendingDecision==="APPROVE"?"Confirm approval":"Confirm return for changes"}</b><p>{pendingDecision==="APPROVE"?"This creates an approved release snapshot. Publishing is a separate step.":"This sends the information back to the steward and records your notes as the reason for the return."}</p><div className="button-row"><button onClick={()=>setPendingDecision(null)}>Cancel</button><button className="primary" disabled={pendingDecision==="RETURN"&&!reviewNotes.trim()} onClick={()=>doAction(()=>api(`/assets/${asset.asset.asset_id}/${pendingDecision==="APPROVE"?"approve":"reject"}`,userEmail,{method:"POST",body:JSON.stringify({comments:reviewNotes.trim()})}),pendingDecision==="APPROVE"?"Approved and governed release created.":"Returned to the steward for changes.").then(()=>{setPendingDecision(null);setReviewNotes("")})}>{pendingDecision==="APPROVE"?"Confirm approval":"Confirm return"}</button></div></div>:<div className="button-row"><button onClick={()=>setPendingDecision("RETURN")}>Return for changes</button><button className="primary" onClick={()=>setPendingDecision("APPROVE")}>Approve</button></div>}
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
      <p><b>Submission readiness</b> means the required stewardship work is complete. <b>Information trust</b> is a separate quality/assessment signal that tells you how much confidence you have in the data. <b>Approve</b> creates an immutable governed release. <b>Publish</b> shares that approved release through the configured publication connection.</p>
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

    <NextStepCallout title="What to do next" body={canReview ? "Open each submission in the queue, review the stewardship evidence, and approve or return it with clear notes when a change is required." : "This queue is read-only for your role. Wait for an approver or administrator to complete the review and publication decision."} />

    {!canReview&&<div className="education strong"><b>This queue is read-only for your role.</b><p>An Approver or administrator is responsible for approval and publication decisions.</p></div>}
    {review.length===0&&<EmptyState title="Nothing is waiting for review or publication." text="Submitted or approved items will appear here when your role has work to do."/>}

    {review.map(a=><div className="review-row role-review-row" key={a.asset.asset_id}>
      <div>
        <b>{a.asset.name}</b>
        <span>{a.readiness.score}% stewardship completeness · {a.quality?.overall_score??"—"}% information quality</span>
      </div>
      <Status value={a.publication.status}/>
      <div className="button-row">
        <button onClick={()=>onOpen(a)}>View details</button>

        {canReview&&a.publication.status==="IN_REVIEW"&&<span className="review-state-note">Open details to review and decide</span>}

        {canPublish&&a.publication.status==="APPROVED"&&<button className="primary" onClick={()=>doAction(()=>api(`/assets/${a.asset.asset_id}/publish`,userEmail,{method:"POST"}),"Published.")}>Publish approved release</button>}

        {a.publication.status==="NEEDS_UPDATE"&&<span className="review-state-note">Waiting for steward updates</span>}
      </div>
    </div>)}
  </>;
}


function UserAdministration({userEmail,currentUserId,authMode}){
  const ROLES=[
    ["STEWARD","Steward","Identifies, describes, governs, and maintains information."],
    ["APPROVER","Approver","Reviews submitted stewardship work and can approve or publish."],
    ["ORG_ADMIN","Organization Admin","Manages users and can perform stewardship and review actions."],
    ["VIEWER","Viewer","Can view information without making stewardship decisions."],
    ["ENTERPRISE_ADMIN","Enterprise Admin","Administrative and review access for the organization."]
  ];

  const [data,setData]=useState(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [form,setForm]=useState({display_name:"",email:"",role:"STEWARD"});
  const [temporary,setTemporary]=useState(null);
  const [busy,setBusy]=useState(false);

  async function load(){
    setLoading(true); setError("");
    try{setData(await api("/admin/users",userEmail));}
    catch(e){setError(e.message);}
    finally{setLoading(false);}
  }

  useEffect(()=>{load()},[userEmail]);

  async function createUser(e){
    e.preventDefault();
    setBusy(true); setError(""); setNotice(""); setTemporary(null);
    try{
      const result=await api("/admin/users",userEmail,{
        method:"POST",
        body:JSON.stringify(form)
      });
      setTemporary({
        title:"User created",
        email:result.user.email,
        password:result.temporary_password,
        message:result.message
      });
      setForm({display_name:"",email:"",role:"STEWARD"});
      setCreateOpen(false);
      await load();
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }

  async function updateMembership(user,changes,success){
    setBusy(true); setError(""); setNotice("");
    try{
      await api(`/admin/users/${user.membership_id}`,userEmail,{
        method:"PATCH",
        body:JSON.stringify(changes)
      });
      setNotice(success);
      await load();
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }

  function changeRole(user,newRole){
    if(newRole===user.role) return;
    const next=ROLES.find(r=>r[0]===newRole);
    if(!window.confirm(`Change ${user.display_name}'s role to ${next?.[1]||newRole}? This changes what they can see and do.\n\n${next?.[2]||""}`)) return;
    updateMembership(user,{role:newRole},"Role updated.");
  }

  function changeAccess(user){
    const action=user.membership_active?"deactivate":"reactivate";
    const consequence=user.membership_active
      ? "They will lose access to this organization, but their stewardship history will remain."
      : "They will regain access using their assigned role.";
    if(!window.confirm(`${action[0].toUpperCase()+action.slice(1)} ${user.display_name}?\n\n${consequence}`)) return;
    updateMembership(user,{membership_active:!user.membership_active},user.membership_active?"User deactivated.":"User reactivated.");
  }

  async function resetPassword(user){
    if(!window.confirm(`Generate a new temporary password for ${user.display_name}? Their current password will stop working.`)) return;
    setBusy(true); setError(""); setNotice(""); setTemporary(null);
    try{
      const result=await api(`/admin/users/${user.membership_id}/reset-password`,userEmail,{method:"POST"});
      setTemporary({
        title:"Temporary password generated",
        email:user.email,
        password:result.temporary_password,
        message:result.message
      });
      await load();
    }catch(e){setError(e.message);}
    finally{setBusy(false);}
  }

  async function copyPassword(){
    if(!temporary?.password) return;
    try{
      await navigator.clipboard.writeText(temporary.password);
      setNotice("Temporary password copied.");
    }catch{
      setNotice("Copy was unavailable. Select and copy the temporary password manually.");
    }
  }

  if(loading) return <><h1>User Administration</h1><div className="panel"><p>Loading organization users…</p></div></>;

  return <>
    <div className="title-row">
      <div>
        <div className="eyebrow">Administration</div>
        <h1>User Administration</h1>
        <p className="lead">Add people to your organization, assign their responsibilities, deactivate access, and reset temporary passwords.</p>
      </div>
      <button className="primary" onClick={()=>{setCreateOpen(true);setTemporary(null);setNotice("");setError("")}}>Add user</button>
    </div>

    {error&&<div className="message error-message">{error}</div>}
    {notice&&<div className="message">{notice}</div>}

    {temporary&&<section className="panel temporary-password-panel">
      <div className="task-head">
        <div>
          <div className="eyebrow">Shown once</div>
          <h2>{temporary.title}</h2>
          <p>{temporary.message}</p>
        </div>
        <button onClick={()=>setTemporary(null)}>Dismiss</button>
      </div>
      {temporary.password?<div className="temporary-password">
        <div><span>User</span><b>{temporary.email}</b></div>
        <div><span>Temporary password</span><code>{temporary.password}</code></div>
        <button className="primary" onClick={copyPassword}>Copy temporary password</button>
      </div>:<p>This authentication mode does not use a local temporary password.</p>}
      <div className="education"><b>Share it securely.</b><p>The temporary password is not retrievable after this screen is dismissed. The user will be required to choose a new password after signing in.</p></div>
    </section>}

    {createOpen&&<section className="panel admin-create-panel">
      <div className="task-head"><div><div className="eyebrow">New organization user</div><h2>Add a user</h2></div><button onClick={()=>setCreateOpen(false)}>Cancel</button></div>
      <form className="admin-user-form" onSubmit={createUser}>
        <label>Full name<input value={form.display_name} onChange={e=>setForm({...form,display_name:e.target.value})} required/></label>
        <label>Email<input type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} required/></label>
        <label>Role<select value={form.role} onChange={e=>setForm({...form,role:e.target.value})}>{ROLES.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
        <div className="education"><b>{ROLES.find(r=>r[0]===form.role)?.[1]}</b><p>{ROLES.find(r=>r[0]===form.role)?.[2]}</p></div>
        <div className="button-row"><button className="primary" disabled={busy}>Create user</button><button type="button" onClick={()=>setCreateOpen(false)}>Cancel</button></div>
      </form>
    </section>}

    <section className="panel">
      <div className="task-head">
        <div><div className="eyebrow">Organization access</div><h2>{data?.users?.length||0} users</h2><p className="muted">Roles control what each person can do. Deactivation removes access to this organization without deleting stewardship history.</p></div>
        <button onClick={load}>Refresh</button>
      </div>

      <div className="admin-user-list">
        {(data?.users||[]).map(user=>{
          const isSelf=user.user_id===currentUserId;
          const role=ROLES.find(r=>r[0]===user.role);
          return <div className={`admin-user-card ${user.membership_active?"":"inactive"}`} key={user.membership_id}>
            <div className="admin-user-identity">
              <div className="avatar-circle">{(user.display_name||user.email).slice(0,1).toUpperCase()}</div>
              <div><b>{user.display_name}{isSelf&&<span className="you-badge">You</span>}</b><span>{user.email}</span></div>
            </div>

            <div className="admin-user-role">
              <label>Role
                <select value={user.role} disabled={busy||isSelf||!user.membership_active} onChange={e=>changeRole(user,e.target.value)}>
                  {ROLES.map(([value,label])=><option value={value} key={value}>{label}</option>)}
                </select>
              </label>
              <small>{role?.[2]}</small>
            </div>

            <div className="admin-user-security">
              <span className={user.membership_active?"status status-active":"status status-inactive"}>{user.membership_active?"Active":"Inactive"}</span>
              {authMode==="local"&&<small>{user.must_change_password?"Temporary password pending":"Password established"}</small>}
            </div>

            <div className="admin-user-actions">
              {authMode==="local"&&<button disabled={busy||isSelf||!user.membership_active} onClick={()=>resetPassword(user)}>Reset password</button>}
              {isSelf
                ? <small>Manage your own password from your account.</small>
                : <button disabled={busy} onClick={()=>changeAccess(user)}>{user.membership_active?"Deactivate":"Reactivate"}</button>}
            </div>
          </div>;
        })}
      </div>

      {(data?.users||[]).length===0&&<EmptyState title="No organization users yet." text="Add the first person who will participate in this pilot."/>}
    </section>

    <section className="panel">
      <div className="eyebrow">Role guide</div>
      <h2>What the roles mean</h2>
      <div className="role-guide-grid">{ROLES.map(([value,label,description])=><div key={value}><b>{label}</b><p>{description}</p></div>)}</div>
    </section>
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

createRoot(document.getElementById("root")).render(<ErrorBoundary><App/></ErrorBoundary>);
