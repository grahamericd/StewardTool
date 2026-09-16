const BASE=import.meta.env.VITE_API_BASE||"/api";
const TOKEN_KEY="ai_data_steward_access_token";

export function getAccessToken(){ return localStorage.getItem(TOKEN_KEY); }
export function setAccessToken(token){ token?localStorage.setItem(TOKEN_KEY,token):localStorage.removeItem(TOKEN_KEY); }
export function clearAccessToken(){ localStorage.removeItem(TOKEN_KEY); }

// Demo mode is the only mode where the backend reads X-User-Email, so the
// header is never sent anywhere else.
let demoMode=false;
export function setDemoMode(value){ demoMode=Boolean(value); }

export class ApiError extends Error{
  constructor(message,status){ super(message); this.name="ApiError"; this.status=status; }
}

function headers(identity,options={}){
  const h={"Content-Type":"application/json",...(options.headers||{})};
  const token=getAccessToken();
  if(token) h.Authorization=`Bearer ${token}`;
  else if(identity&&demoMode) h["X-User-Email"]=identity;
  return h;
}

function describe(detail,body){
  if(typeof detail==="string") return detail;
  if(detail&&typeof detail==="object"){
    if(typeof detail.message==="string") return detail.message;
    if(Array.isArray(detail)){
      const first=detail[0];
      if(first&&typeof first.msg==="string"){
        const field=Array.isArray(first.loc)?first.loc[first.loc.length-1]:null;
        return field?`${field}: ${first.msg}`:first.msg;
      }
    }
  }
  if(typeof body==="string"&&body.trim()) return body.trim().slice(0,300);
  return "Something went wrong. Please try again.";
}

async function request(path,options,requestHeaders){
  const r=await fetch(`${BASE}${path}`,{...options,headers:requestHeaders});
  const t=await r.text();
  let d=null;
  try{ d=t?JSON.parse(t):null; }catch{ d=t; }
  if(!r.ok){
    if(r.status===401&&getAccessToken()) clearAccessToken();
    throw new ApiError(describe(d?.detail,t),r.status);
  }
  return d;
}

export async function api(path,identity,options={}){
  return request(path,options,headers(identity,options));
}

export async function publicApi(path,options={}){
  return request(path,options,{"Content-Type":"application/json",...(options.headers||{})});
}
