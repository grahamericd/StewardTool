const BASE=import.meta.env.VITE_API_BASE||"/api";
const TOKEN_KEY="ai_data_steward_access_token";

export function getAccessToken(){ return localStorage.getItem(TOKEN_KEY); }
export function setAccessToken(token){ token?localStorage.setItem(TOKEN_KEY,token):localStorage.removeItem(TOKEN_KEY); }
export function clearAccessToken(){ localStorage.removeItem(TOKEN_KEY); }

function headers(identity,options={}){
  const h={"Content-Type":"application/json",...(options.headers||{})};
  const token=getAccessToken();
  if(token) h.Authorization=`Bearer ${token}`;
  else if(identity) h["X-User-Email"]=identity;
  return h;
}

export async function api(path,identity,options={}){
  const r=await fetch(`${BASE}${path}`,{...options,headers:headers(identity,options)});
  const t=await r.text();
  let d=null;
  try{ d=t?JSON.parse(t):null; }catch{ d=t; }
  if(!r.ok){
    if(r.status===401 && getAccessToken()) clearAccessToken();
    const x=d?.detail;
    throw new Error(typeof x==="string"?x:(x?.message||JSON.stringify(x||d)));
  }
  return d;
}

export async function publicApi(path,options={}){
  const r=await fetch(`${BASE}${path}`,{...options,headers:{"Content-Type":"application/json",...(options.headers||{})}});
  const t=await r.text();
  let d=null;
  try{ d=t?JSON.parse(t):null; }catch{ d=t; }
  if(!r.ok){
    const x=d?.detail;
    throw new Error(typeof x==="string"?x:(x?.message||JSON.stringify(x||d)));
  }
  return d;
}
