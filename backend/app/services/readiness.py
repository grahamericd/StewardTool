from .snapshot import build_asset_snapshot
WEIGHTS={"business_definition":15,"business_owner":15,"data_steward":10,"has_resource":15,"theme":10,"keywords":10,"update_frequency":10,"contact":5,"authoritative_source":10}

def calculate_readiness(asset):
    s=build_asset_snapshot(asset); md=s["metadata"]
    checks={"business_definition":bool(s["asset"].get("business_definition")),"business_owner":bool(s["asset"].get("business_owner")),"data_steward":bool(s["asset"].get("data_steward")),"has_resource":bool(s["resources"]),"theme":bool(md.get("theme")),"keywords":bool(md.get("keyword")),"update_frequency":bool(md.get("update_frequency")),"contact":bool(md.get("contact")),"authoritative_source":any(r.get("is_authoritative") for r in s["resources"])}
    score=sum(WEIGHTS[k] for k,v in checks.items() if v)
    missing=[k for k,v in checks.items() if not v]
    return {"score":score,"checks":checks,"missing":missing,"ready_to_submit":score>=70 and checks["business_definition"] and checks["business_owner"] and checks["has_resource"]}
