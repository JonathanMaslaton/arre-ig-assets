#!/usr/bin/env python3
"""arre IG cloud auto-poster (Composio REST v3, no CLI).
Publishes the earliest PENDING item in schedule.json whose publish_at_utc has passed.
Account-guarded to @arrehomellc. Secret env: COMPOSIO_API_KEY."""
import json, os, sys, time, datetime, urllib.request

BASE = os.environ.get("COMPOSIO_BASE", "https://backend.composio.dev")
KEY  = os.environ.get("COMPOSIO_API_KEY")
GUARD_USERNAME = "arrehomellc"
IG_USER_ID = "27581619711517338"
CONNECTED_ACCOUNT_ID = "ca_HG7PdDXJjlB8"
USER_ID = "pg-test-770c33c2-f3bf-40f8-9d1b-b5b156533ed6"
SCHED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.json")

def execute(slug, args):
    body = {"connected_account_id": CONNECTED_ACCOUNT_ID, "user_id": USER_ID, "arguments": args}
    req = urllib.request.Request(f"{BASE}/api/v3/tools/execute/{slug}",
        data=json.dumps(body).encode(), method="POST",
        headers={"x-api-key": KEY, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=180); b = json.load(r)
    except urllib.error.HTTPError as e:
        try: b = json.loads(e.read())
        except Exception: b = {"successful": False}
    ok = bool(isinstance(b, dict) and b.get("successful"))
    d = b.get("data", {}) if isinstance(b, dict) else {}
    d = d.get("data", d) if isinstance(d, dict) else d
    return ok, d, b

def guard():
    ok, d, raw = execute("INSTAGRAM_GET_USER_INFO", {"ig_user_id": IG_USER_ID})
    if not ok or d.get("username") != GUARD_USERNAME:
        raise SystemExit(f"ACCOUNT GUARD FAILED: {str(raw)[:300]}")
    print("guard ok ->", d.get("username"))

def publish_item(it):
    caption, urls = it["caption"], it["image_urls"]
    if it["type"] == "STORY":
        ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA",
                           {"ig_user_id": IG_USER_ID, "media_type": "STORIES", "image_url": urls[0]})
        if not ok: raise RuntimeError(f"story container: {str(raw)[:300]}")
        creation = d.get("id")
        time.sleep(5)
        ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH",
                           {"ig_user_id": IG_USER_ID, "creation_id": creation})
        if not ok: raise RuntimeError(f"story publish: {str(raw)[:300]}")
        return d.get("id"), None
    if it["type"] == "IMAGE":
        ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA",
                           {"ig_user_id": IG_USER_ID, "image_url": urls[0], "caption": caption})
        if not ok: raise RuntimeError(f"container: {str(raw)[:300]}")
        creation = d.get("id")
    else:
        children = []
        for u in urls:
            ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA",
                               {"ig_user_id": IG_USER_ID, "image_url": u, "is_carousel_item": True})
            if not ok: raise RuntimeError(f"child: {str(raw)[:300]}")
            children.append(d.get("id"))
        ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA",
                           {"ig_user_id": IG_USER_ID, "media_type": "CAROUSEL",
                            "children": children, "caption": caption})
        if not ok: raise RuntimeError(f"carousel: {str(raw)[:300]}")
        creation = d.get("id")
    time.sleep(5)
    ok,d,raw = execute("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH",
                       {"ig_user_id": IG_USER_ID, "creation_id": creation})
    if not ok: raise RuntimeError(f"publish: {str(raw)[:300]}")
    mid = d.get("id")
    ok,d2,_ = execute("INSTAGRAM_GET_IG_MEDIA", {"ig_media_id": mid, "fields": "permalink"})
    return mid, (d2 or {}).get("permalink")

def main():
    if not KEY: raise SystemExit("COMPOSIO_API_KEY not set")
    sched = json.load(open(SCHED)); guard()
    if "--selftest" in sys.argv:
        print("SELFTEST OK. pending:", sum(1 for s in sched if s["status"]=="PENDING")); return
    now = datetime.datetime.now(datetime.timezone.utc)
    due = sorted([s for s in sched if s["status"]=="PENDING"
        and datetime.datetime.fromisoformat(s["publish_at_utc"].replace("Z","+00:00")) <= now],
        key=lambda s: s["publish_at_utc"])
    if not due: print("nothing due at", now.isoformat()); return
    it = due[0]; print("publishing", it["id"], it["type"])
    mid, link = publish_item(it)
    it["status"], it["media_id"], it["permalink"] = "DONE", mid, link
    json.dump(sched, open(SCHED,"w"), indent=2)
    print("PUBLISHED", it["id"], "->", link)

if __name__ == "__main__": main()
