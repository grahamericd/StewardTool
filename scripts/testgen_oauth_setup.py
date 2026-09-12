#!/usr/bin/env python3
import argparse, base64, hashlib, os
from urllib.parse import urlencode
import httpx

def pkce_pair():
    verifier=base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier,challenge

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base-url",default="http://localhost:8530")
    p.add_argument("--client-name",default="ai-data-steward")
    p.add_argument("--redirect-uri",default="http://localhost:8080/callback")
    args=p.parse_args(); base=args.base_url.rstrip("/")
    r=httpx.post(f"{base}/oauth/register",json={
        "client_name":args.client_name,
        "redirect_uris":[args.redirect_uri],
        "grant_types":["authorization_code","refresh_token"],
    },timeout=30)
    r.raise_for_status(); reg=r.json()
    verifier,challenge=pkce_pair()
    query=urlencode({
        "response_type":"code",
        "client_id":reg["client_id"],
        "redirect_uri":args.redirect_uri,
        "code_challenge":challenge,
        "code_challenge_method":"S256",
    })
    print("\\nOpen this URL and approve the client:\\n")
    print(f"{base}/oauth/authorize?{query}")
    print("\\nAfter redirect, copy the value after ?code= from the address bar.")
    code=input("\\nAuthorization code: ").strip()
    r=httpx.post(f"{base}/oauth/token",auth=(reg["client_id"],reg["client_secret"]),data={
        "grant_type":"authorization_code",
        "code":code,
        "redirect_uri":args.redirect_uri,
        "code_verifier":verifier,
    },timeout=30)
    r.raise_for_status(); tok=r.json()
    print("\\nPut these in .env; do not commit them:\\n")
    print("TESTGEN_MODE=real")
    print(f"TESTGEN_BASE_URL={base}")
    print("TESTGEN_AUTH_MODE=oauth_refresh")
    print(f"TESTGEN_OAUTH_CLIENT_ID={reg['client_id']}")
    print(f"TESTGEN_OAUTH_CLIENT_SECRET={reg['client_secret']}")
    print(f"TESTGEN_OAUTH_REFRESH_TOKEN={tok['refresh_token']}")
    print("\\nAlso set TESTGEN_PROJECT_CODE.")

if __name__=="__main__":
    main()
