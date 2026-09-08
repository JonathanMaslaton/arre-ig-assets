#!/usr/bin/env python3
"""arre IG cloud auto-poster (Composio REST, no CLI).
Publishes any PENDING item in schedule.json whose publish_at_utc has passed.
Account-guarded to @arrehomellc. Env: COMPOSIO_API_KEY."""
import json, os, sys, time, datetime, urllib.request

BASE = os.environ.get("COMPOSIO_BASE", "https://backend.composio.dev")
KEY  = os.environ.get("COMPOSIO_API_KEY")
GUARD_USERNAME = "arrehomellc"
IG_USER_ID = "27581619711517338"
SCHED = os.path.join(os.path.dirname(__file__), "schedule.json")

def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"x-api-key": KEY, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, {"raw": "err"}

def connected_account():
    st, b = api("GET", "/api/v3/connected_accounts?toolkit_slugs=instagram")
    items = (b or {}).get("items", []) if isinstance(b, dict) else []
    if not items:
        raise SystemExit("No Instagram connected account in this Composio project. "
                         "Connect @arrehomellc or use the correct COMPOSIO_API_KEY.")
    active = [x for x in items if str(x.get("status","")).upper()=="ACTIVE"] or items
    # pick the account whose own IG profile username == arrehomellc
    for x in active:
        cid = x["id"]
        ok, d, raw = execute("INSTAGRAM_GET_USER_INFO", cid, {"ig_user_id": "me"})
        dd = d.get("data", d) if isinstance(d, dict) else {}
        if (dd or {}).get("username") == GUARD_USERNAME:
            print("matched connected account", cid, "->", GUARD_USERNAME)
            return cid
    raise SystemExit(f"None of the {len(active)} Instagram connected accounts is {GUARD_USERNAME}.")

def execute(slug, cid, args):
    st, b = api("POST", f"/api/v3/tools/execute/{slug}",
                {"connected_account_id": cid, "arguments": args})
    d = b.get("data", b) if isinstance(b, dict) else {}
    ok = (isinstance(b, dict) and b.get("successful", st==200))
    return ok, d, b

def guard(cid):
    ok, d, raw = execute("INSTAGRAM_GET_USER_INFO", cid, {"ig_user_id": IG_USER_ID})
    u = (d or {}).get("username") or (d.get("data",{}) if isinstance(d,dict) else {}).get("username")
    if u != GUARD_USERNAME:
        raise SystemExit(f"ACCOUNT GUARD FAILED: got {u!r}, expected {GUARD_USERNAME}. raw={str(raw)[:300]}")
    print("guard ok ->", u)

def _id(d):
    return (d or {}).get("id") or (d.get("data",{}) if isinstance(d,dict) else {}).get("id")

def publish_item(cid, it):
    caption = it["caption"]; urls = it["image_urls"]
    if it["type"] == "IMAGE":
        ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA", cid,
                           {"ig_user_id": IG_USER_ID, "image_url": urls[0], "caption": caption})
        if not ok: raise RuntimeError(f"container: {str(raw)[:300]}")
        creation = _id(d)
    else:  # CAROUSEL
        children = []
        for u in urls:
            ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA", cid,
                               {"ig_user_id": IG_USER_ID, "image_url": u, "is_carousel_item": True})
            if not ok: raise RuntimeError(f"child: {str(raw)[:300]}")
            children.append(_id(d))
        ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA", cid,
                           {"ig_user_id": IG_USER_ID, "media_type": "CAROUSEL",
                            "children": children, "caption": caption})
        if not ok: raise RuntimeError(f"carousel: {str(raw)[:300]}")
        creation = _id(d)
    time.sleep(5)
    ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", cid,
                       {"ig_user_id": IG_USER_ID, "creation_id": creation})
    if not ok: raise RuntimeError(f"publish: {str(raw)[:300]}")
    mid = _id(d)
    ok,d2,_ = execute("INSTAGRAM_GET_IG_MEDIA", cid, {"ig_media_id": mid, "fields": "permalink"})
    link = (d2 or {}).get("permalink") or (d2.get("data",{}) if isinstance(d2,dict) else {}).get("permalink")
    return mid, link

def main():
    if not KEY: raise SystemExit("COMPOSIO_API_KEY not set")
    sched = json.load(open(SCHED))
    cid = connected_account()
    guard(cid)
    if "--selftest" in sys.argv:
        print("SELFTEST OK. connected_account:", cid,
              "| pending:", sum(1 for s in sched if s["status"]=="PENDING")); return
    now = datetime.datetime.now(datetime.timezone.utc)
    due = [s for s in sched if s["status"]=="PENDING"
           and datetime.datetime.fromisoformat(s["publish_at_utc"].replace("Z","+00:00")) <= now]
    if not due:
        print("nothing due at", now.isoformat()); return
    due.sort(key=lambda s: s["publish_at_utc"])
    it = due[0]  # one per run
    print("publishing", it["id"], it["type"])
    mid, link = publish_item(cid, it)
    it["status"], it["media_id"], it["permalink"] = "DONE", mid, link
    json.dump(sched, open(SCHED, "w"), indent=2)
    print("PUBLISHED", it["id"], "->", link)

if __name__ == "__main__":
    main()
