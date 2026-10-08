"""Work summary for the Glance Work page (stdlib only; imported by app.py).

One cached document with four independent parts, each {"ok": bool, "err": str, ...}, so one system being down never blanks the others:
  bp  Brightpearl  : sales orders (last 30 days, with totals), channels, countries, top products, status board, purchase orders, stock
  hs  HubSpot      : deal pipeline, won/lost, new leads, support tickets, tasks, meetings, owners, domains
  wp  WordPress    : WooCommerce orders and products, site content, plugins, response time
  pa  PythonAnywhere: CPU quota, web apps, scheduled tasks, consoles, error-log tail
plus "kpi" (headline numbers) and "attention" (things that need a human).

Credentials come from the container environment (WORK_*), are only ever sent to their own service, and never reach the browser.
Personal data stays minimal: customer names are shown only for companies / non-marketplace buyers, never addresses or e-mail addresses.
search() and order() are read-only lookups used by the Work page's search box.
"""
import base64
import datetime
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
UA = "glance-admin/1 (work)"
HS_PORTAL = os.environ.get("WORK_HS_PORTAL", "")
HS_UI = "https://app-eu1.hubspot.com"
NOT_SALES = {1, 5, 22, 17}          # Sales Quote, Cancelled SO, Blank, Cancelled (credit): never counted as revenue
_state = {"bp_channels": None, "bp_channels_at": 0, "hs_owners": None, "hs_owners_at": 0, "hs_pipes": None, "hs_pipes_at": 0}


def _env(n, d=""):
    return os.environ.get(n, d)


def configured():
    return any(_env(k) for k in ("WORK_BP_TOKEN", "WORK_HUBSPOT_TOKEN", "WORK_WP_KEY", "WORK_PA_TOKEN"))


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _ts(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _local(ts):
    return datetime.datetime.fromtimestamp(ts, UK)


def _age_min(ts):
    return max(0, int((time.time() - ts) / 60)) if ts else None


def _gbp(v, pence=False):
    v = _f(v)
    return ("£{:,.2f}" if pence else "£{:,.0f}").format(v)


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def _http(url, headers=None, body=None, method=None, timeout=25):
    h = {"User-Agent": UA}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return (json.loads(raw.decode("utf-8")) if raw else None), dict(r.headers)


def _section(fn, *a):
    try:
        out = fn(*a)
        out["ok"] = True
        out["err"] = ""
        return out
    except urllib.error.HTTPError as e:
        return {"ok": False, "err": "HTTP %d" % e.code}
    except (urllib.error.URLError, OSError):
        return {"ok": False, "err": "unreachable"}
    except Exception as e:                      # a parsing slip in one section must not take the page down
        return {"ok": False, "err": ("%s: %s" % (type(e).__name__, e))[:120]}


def _days(n=30):
    """Local calendar dates, oldest first, ending today."""
    today = datetime.datetime.now(UK).date()
    return [today - datetime.timedelta(days=i) for i in range(n - 1, -1, -1)]


def _bars(values):
    """Percent heights (min 3 for non-zero so a quiet day is still visible)."""
    top = max(values) if values and max(values) > 0 else 1
    return [(max(3, int(round(v * 100 / top))) if v > 0 else 0) for v in values]


def _series(by_day, key):
    ds = _days(30)
    vals = [by_day.get(d.isoformat(), 0) for d in ds]
    hs = _bars(vals)
    return [{"d": d.strftime("%a %d %b"), "v": v, "h": h, "k": key} for d, v, h in zip(ds, vals, hs)]


# ============================================================================================================== Brightpearl
def _bp_headers():
    return {_env("WORK_BP_APPREF_HEADER", "brightpearl-app-ref"): _env("WORK_BP_APPREF"),
            _env("WORK_BP_TOKEN_HEADER", "brightpearl-account-token"): _env("WORK_BP_TOKEN")}


def _bp(path, retry=True):
    url = _env("WORK_BP_BASE").rstrip("/") + path
    try:
        d, h = _http(url, _bp_headers(), timeout=30)
    except urllib.error.HTTPError as e:
        if e.code in (429, 503) and retry:             # throttled: wait out the period (capped) and try once more
            try:
                wait = min(8.0, float(e.headers.get("brightpearl-next-throttle-period", "3000")) / 1000.0)
            except ValueError:
                wait = 3.0
            time.sleep(wait)
            return _bp(path, False)
        raise
    _state["bp_remaining"] = h.get("brightpearl-requests-remaining") or h.get("Brightpearl-Requests-Remaining")
    return (d or {}).get("response")


def _bp_search(path, per=500, limit=3000):
    """All rows of an order/product search as dicts keyed by column name."""
    rows, first, cols = [], 1, None
    while len(rows) < limit:
        r = _bp("%s%spageSize=%d&firstResult=%d" % (path, "&" if "?" in path else "?", per, first))
        cols = cols or [c["name"] for c in r["metaData"]["columns"]]
        rows += [dict(zip(cols, x)) for x in r["results"]]
        if not r["metaData"].get("morePagesAvailable"):
            break
        first += per
    return rows


def _bp_count(path):
    r = _bp(path + ("&" if "?" in path else "?") + "pageSize=1")
    return int(r["metaData"].get("resultsAvailable") or 0)


def _bp_channels():
    if _state["bp_channels"] is None or time.time() - _state["bp_channels_at"] > 6 * 3600:
        _state["bp_channels"] = {c["id"]: c["name"] for c in _bp("/product-service/channel") or []}
        _state["bp_channels_at"] = time.time()
    return _state["bp_channels"]


def _bp_statuses():
    return {s["statusId"]: s["name"] for s in _bp("/order-service/order-status") or []}


def _bp_orders(ids):
    out = []
    ids = sorted(set(ids))
    for i in range(0, len(ids), 100):
        out += _bp("/order-service/order/" + ",".join(str(x) for x in ids[i:i + 100])) or []
    return out


def _party_name(p):
    p = p or {}
    return _clip(p.get("companyName") or p.get("addressFullName") or "", 40)


def _order(o, channels):
    tv = o.get("totalValue") or {}
    cur = o.get("currency") or {}
    rate = _f(cur.get("exchangeRate"), 1.0) or 1.0
    parties = o.get("parties") or {}
    cust, dl = parties.get("customer") or {}, parties.get("delivery") or {}
    ch = ((o.get("assignment") or {}).get("current") or {}).get("channelId")
    rows = []
    for r in (o.get("orderRows") or {}).values():
        q = _f((r.get("quantity") or {}).get("magnitude"))
        net = _f(((r.get("rowValue") or {}).get("rowNet") or {}).get("value")) / rate
        if r.get("productName") and (q or net):
            rows.append({"name": _clip(r["productName"], 70), "sku": r.get("productSku") or "", "qty": q, "gbp": net})
    placed = _ts(o.get("placedOn") or o.get("createdOn"))
    return {"id": o.get("id"), "ref": _clip(o.get("reference"), 28) or "#%s" % o.get("id"), "at": placed, "sid": (o.get("orderStatus") or {}).get("orderStatusId"),
            "status": (o.get("orderStatus") or {}).get("name") or "", "gbp": _f(tv.get("baseTotal")), "net": _f(tv.get("baseNet")),
            "cur": cur.get("orderCurrencyCode") or "GBP", "orig": _f(tv.get("total")), "pay": o.get("orderPaymentStatus") or "",
            "ship": o.get("shippingStatusCode") or "", "country": dl.get("countryIsoCode") or cust.get("countryIsoCode") or "",
            "channel": channels.get(ch) or "Other", "who": "" if (o.get("reference") or "").count("-") == 2 else _party_name(cust),   # Amazon-style refs (123-1234567-1234567) are private buyers: no name
             "rows": rows,
            "contact": cust.get("contactId")}


def bp_summary():
    ch = _bp_channels()
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00.000Z")
    found = _bp_search("/order-service/order-search?orderTypeId=1&createdOn=%s/&sort=createdOn.DESC" % since)
    orders = [_order(o, ch) for o in _bp_orders([r["orderId"] for r in found])]
    sales = [o for o in orders if o["sid"] not in NOT_SALES]
    quotes = [o for o in orders if o["sid"] == 1]
    now = time.time()
    today = datetime.datetime.now(UK).date()
    by_day, by_day_n, by_ch, by_co, by_prod = {}, {}, {}, {}, {}
    for o in sales:
        d = _local(o["at"]).date().isoformat()
        by_day[d] = by_day.get(d, 0) + o["gbp"]
        by_day_n[d] = by_day_n.get(d, 0) + 1
        c = by_ch.setdefault(o["channel"], {"name": o["channel"], "gbp": 0.0, "n": 0})
        c["gbp"] += o["gbp"]
        c["n"] += 1
        k = by_co.setdefault(o["country"] or "??", {"cc": o["country"] or "??", "gbp": 0.0, "n": 0})
        k["gbp"] += o["gbp"]
        k["n"] += 1
        for r in o["rows"]:
            p = by_prod.setdefault(r["name"], {"name": r["name"], "sku": r["sku"], "qty": 0.0, "gbp": 0.0})
            p["qty"] += r["qty"]
            p["gbp"] += r["gbp"]

    def window(a, b):
        sel = [o for o in sales if a <= (today - _local(o["at"]).date()).days < b]
        return {"n": len(sel), "gbp": sum(o["gbp"] for o in sel)}
    t0, t1, w7, w7p = window(0, 1), window(1, 2), window(0, 7), window(7, 14)
    tot = sum(o["gbp"] for o in sales) or 1.0
    chans = sorted(by_ch.values(), key=lambda x: -x["gbp"])
    for c in chans:
        c["pct"] = int(round(c["gbp"] * 100 / tot))
        c["fmt"] = _gbp(c["gbp"])
    cos = sorted(by_co.values(), key=lambda x: -x["gbp"])[:8]
    for c in cos:
        c["pct"] = int(round(c["gbp"] * 100 / tot))
        c["fmt"] = _gbp(c["gbp"])
    prods = sorted(by_prod.values(), key=lambda x: -x["gbp"])[:10]
    pmax = max([p["gbp"] for p in prods] or [1]) or 1
    for p in prods:
        p["fmt"] = _gbp(p["gbp"])
        p["w"] = max(3, int(p["gbp"] * 100 / pmax))
        p["qty"] = int(p["qty"])
    statuses = _bp_statuses()
    board = []
    for sid in (1, 2, 16, 15, 20, 22):
        try:
            board.append({"sid": sid, "name": statuses.get(sid, str(sid)), "n": _bp_count("/order-service/order-search?orderTypeId=1&orderStatusId=%d" % sid)})
        except urllib.error.HTTPError:
            pass
    watch = []
    for sid in (16, 15, 2):                     # orders that need a human: awaiting payment, back order, new order
        try:
            rows = _bp_search("/order-service/order-search?orderTypeId=1&orderStatusId=%d&sort=createdOn.DESC" % sid, per=20, limit=20)
            for o in _bp_orders([r["orderId"] for r in rows]):
                x = _order(o, ch)
                x["age"] = _age_min(x["at"])
                watch.append(x)
        except urllib.error.HTTPError:
            pass
    po = []
    try:
        for sid in (6, 7, 14):
            rows = _bp_search("/order-service/order-search?orderTypeId=2&orderStatusId=%d&sort=createdOn.DESC" % sid, per=10, limit=10)
            for o in _bp_orders([r["orderId"] for r in rows]):
                p = (o.get("parties") or {}).get("supplier") or {}
                po.append({"id": o["id"], "ref": _clip(o.get("reference"), 24), "status": (o.get("orderStatus") or {}).get("name"), "gbp": _gbp(_f((o.get("totalValue") or {}).get("baseTotal"))),
                           "who": _party_name(p), "age": _age_min(_ts(o.get("createdOn")))})
        po.sort(key=lambda x: x["age"] if x["age"] is not None else 1e9)
    except urllib.error.HTTPError:
        pass
    returns = 0
    try:
        returns = _bp_count("/order-service/order-search?orderTypeId=3&createdOn=%s/" % since)
    except urllib.error.HTTPError:
        pass
    recent = sorted(sales, key=lambda x: -x["at"])[:12]
    for o in recent:
        o["age"] = _age_min(o["at"])
        o["fmt"] = _gbp(o["gbp"], True)
        o["items"] = ", ".join("%s×%d" % (_clip(r["name"], 26), r["qty"]) for r in o["rows"][:2]) + (" +%d" % (len(o["rows"]) - 2) if len(o["rows"]) > 2 else "")
        o.pop("rows", None)
    for o in watch:
        o["fmt"] = _gbp(o["gbp"], True)
        o.pop("rows", None)
    daily = _series(by_day, "gbp")
    for d in daily:
        d["f"] = _gbp(d["v"])
    watch.sort(key=lambda x: x["age"] if x["age"] is not None else 1e12)
    return {"from": daily[0]["d"], "today": {"n": t0["n"], "gbp": t0["gbp"], "fmt": _gbp(t0["gbp"])}, "yesterday": {"n": t1["n"], "gbp": t1["gbp"], "fmt": _gbp(t1["gbp"])},
            "w7": {"n": w7["n"], "gbp": w7["gbp"], "fmt": _gbp(w7["gbp"])}, "w7prev": {"n": w7p["n"], "gbp": w7p["gbp"], "fmt": _gbp(w7p["gbp"])},
            "d30": {"n": len(sales), "gbp": sum(o["gbp"] for o in sales), "fmt": _gbp(sum(o["gbp"] for o in sales)), "aov": _gbp(sum(o["gbp"] for o in sales) / max(1, len(sales)), True)},
            "quotes30": len(quotes), "returns30": returns, "daily": daily, "daily_n": _series(by_day_n, "n"), "channels": chans, "countries": cos, "products": prods,
            "board": board, "watch": watch[:14], "po": po[:8], "recent": recent, "orders_total": _bp_count("/order-service/order-search?orderTypeId=1"),
            "budget": _state.get("bp_remaining")}


# ============================================================================================================== HubSpot
def _hs_headers():
    return {"Authorization": "Bearer " + _env("WORK_HUBSPOT_TOKEN")}


_hs_gate = {"lock": threading.Lock(), "last": 0.0}


def _hs(path, body=None):
    """HubSpot's search API allows about 4-5 calls a second: space the calls out and honour Retry-After on a 429."""
    for attempt in range(4):
        with _hs_gate["lock"]:
            wait = 0.28 - (time.time() - _hs_gate["last"])
            if wait > 0:
                time.sleep(wait)
            _hs_gate["last"] = time.time()
        try:
            return _http("https://api.hubapi.com" + path, _hs_headers(), body)[0]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                try:
                    delay = float(e.headers.get("Retry-After", "1"))
                except ValueError:
                    delay = 1.0
                time.sleep(min(10.0, max(0.5, delay)))
                continue
            raise


def _hs_search(obj, props, filters=None, sorts=None, limit=100, maxn=1000):
    out, after, total = [], None, 0
    while len(out) < maxn:
        body = {"limit": min(100, limit if limit < 100 else 100), "properties": props, "filterGroups": [{"filters": filters}] if filters else []}
        if sorts:
            body["sorts"] = sorts
        if after:
            body["after"] = after
        r = _hs("/crm/v3/objects/%s/search" % obj, body)
        total = r.get("total", total)
        out += [dict(x.get("properties") or {}, id=x["id"]) for x in r.get("results", [])]
        after = ((r.get("paging") or {}).get("next") or {}).get("after")
        if not after or len(out) >= limit:
            break
    return out[:limit], total


def _hs_owners():
    if _state["hs_owners"] is None or time.time() - _state["hs_owners_at"] > 3600:
        r = _hs("/crm/v3/owners?limit=100")
        _state["hs_owners"] = {o["id"]: ("%s %s" % (o.get("firstName") or "", o.get("lastName") or "")).strip() or o.get("email", "") for o in r.get("results", [])}
        _state["hs_owners_at"] = time.time()
    return _state["hs_owners"]


def _hs_pipes():
    if _state["hs_pipes"] is None or time.time() - _state["hs_pipes_at"] > 3600:
        deals = {}
        for p in _hs("/crm/v3/pipelines/deals").get("results", []):
            for s in p.get("stages", []):
                m = s.get("metadata") or {}
                deals[s["id"]] = {"label": (s.get("label") or "").strip(), "order": s.get("displayOrder", 0), "won": str(m.get("isClosed")).lower() == "true" and str(m.get("probability")) in ("1.0", "1"),
                                  "closed": str(m.get("isClosed")).lower() == "true"}
        tickets = {}
        for p in _hs("/crm/v3/pipelines/tickets").get("results", []):
            for s in p.get("stages", []):
                tickets[s["id"]] = {"label": s.get("label"), "closed": str((s.get("metadata") or {}).get("isClosed")).lower() == "true"}
        _state["hs_pipes"] = {"deals": deals, "tickets": tickets}
        _state["hs_pipes_at"] = time.time()
    return _state["hs_pipes"]


def _rec(obj, i):
    return "%s/contacts/%s/record/%s/%s" % (HS_UI, HS_PORTAL, obj, i)


def hs_summary():
    owners, pipes = _hs_owners(), _hs_pipes()
    now = time.time()
    ms = int(now * 1000)
    d30 = int((now - 30 * 86400) * 1000)
    out = {}

    deals, _ = _hs_search("deals", ["dealname", "amount", "dealstage", "closedate", "createdate", "hubspot_owner_id", "hs_lastmodifieddate", "hs_is_closed_won", "hs_is_closed"], maxn=2000, limit=2000)
    stages = pipes["deals"]
    funnel, won30, lost30, stale, soon, by_owner, won_month = {}, {"n": 0, "gbp": 0.0}, {"n": 0}, [], [], {}, {}
    open_deals = []
    for d in deals:
        st = stages.get(d.get("dealstage"), {"label": d.get("dealstage") or "?", "order": 99, "closed": False, "won": False})
        amt = _f(d.get("amount"))
        closed = str(d.get("hs_is_closed")).lower() == "true" or st.get("closed")
        is_won = str(d.get("hs_is_closed_won")).lower() == "true"
        cd = _ts(d.get("closedate"))
        if is_won:
            m = _local(cd).strftime("%Y-%m") if cd else None
            if m:
                won_month[m] = won_month.get(m, 0) + amt
            if cd and cd >= now - 30 * 86400:
                won30["n"] += 1
                won30["gbp"] += amt
        elif closed:
            if cd and cd >= now - 30 * 86400:
                lost30["n"] += 1
        else:
            open_deals.append((d, st, amt, cd))
    for d, st, amt, cd in open_deals:
        f = funnel.setdefault(st["label"], {"name": st["label"], "n": 0, "gbp": 0.0, "order": st["order"]})
        f["n"] += 1
        f["gbp"] += amt
        o = owners.get(d.get("hubspot_owner_id"), "Unassigned")
        by_owner.setdefault(o, {"name": o, "n": 0, "gbp": 0.0})
        by_owner[o]["n"] += 1
        by_owner[o]["gbp"] += amt
        mod = _ts(d.get("hs_lastmodifieddate"))
        row = {"id": d["id"], "name": _clip(d.get("dealname"), 46), "gbp": amt, "fmt": _gbp(amt), "stage": st["label"], "owner": owners.get(d.get("hubspot_owner_id"), ""),
               "url": _rec("0-3", d["id"]), "close": _local(cd).strftime("%d %b") if cd else "", "close_in": int((cd - now) / 86400) if cd else None, "idle": int((now - mod) / 86400) if mod else None}
        if mod and now - mod > 30 * 86400:
            stale.append(row)
        if cd and 0 <= cd - now <= 14 * 86400:
            soon.append(row)
    fl = sorted(funnel.values(), key=lambda x: x["order"])
    fmax = max([f["n"] for f in fl] or [1])
    for f in fl:
        f["fmt"] = _gbp(f["gbp"])
        f["w"] = max(4, int(f["n"] * 100 / fmax))
    pipe_val = sum(f["gbp"] for f in fl)
    recent = sorted(deals, key=lambda d: d.get("createdate") or "", reverse=True)[:8]
    months = sorted(won_month)[-6:]
    mx = max([won_month[m] for m in months] or [1]) or 1
    out["deals"] = {"total": len(deals), "open": len(open_deals), "pipeline": pipe_val, "pipeline_fmt": _gbp(pipe_val), "funnel": fl,
                    "won30": {"n": won30["n"], "fmt": _gbp(won30["gbp"])}, "lost30": lost30["n"],
                    "win_rate": int(round(won30["n"] * 100 / max(1, won30["n"] + lost30["n"]))) if won30["n"] + lost30["n"] else None,
                    "stale": sorted(stale, key=lambda x: -x["gbp"])[:6], "stale_n": len(stale), "soon": sorted(soon, key=lambda x: x["close_in"])[:6],
                    "owners": sorted(by_owner.values(), key=lambda x: -x["gbp"])[:6],
                    "recent": [{"name": _clip(d.get("dealname"), 46), "fmt": _gbp(_f(d.get("amount"))), "stage": stages.get(d.get("dealstage"), {}).get("label", ""), "url": _rec("0-3", d["id"]),
                                "age": _age_min(_ts(d.get("createdate")))} for d in recent],
                    "months": [{"m": datetime.datetime.strptime(m, "%Y-%m").strftime("%b"), "v": won_month[m], "f": _gbp(won_month[m]), "h": max(3, int(won_month[m] * 100 / mx)) if won_month[m] else 0} for m in months]}
    omax = max([o["gbp"] for o in out["deals"]["owners"]] or [1]) or 1
    for o in out["deals"]["owners"]:
        o["fmt"] = _gbp(o["gbp"])
        o["w"] = max(3, int(o["gbp"] * 100 / omax))

    contacts, ctotal = _hs_search("contacts", ["firstname", "lastname", "company", "createdate", "hs_analytics_source", "lifecyclestage", "hs_lead_status"],
                                  [{"propertyName": "createdate", "operator": "GTE", "value": str(d30)}], [{"propertyName": "createdate", "direction": "DESCENDING"}], maxn=1500, limit=1500)
    by_day, src, life = {}, {}, {}
    for c in contacts:
        d = _local(_ts(c.get("createdate"))).date().isoformat()
        by_day[d] = by_day.get(d, 0) + 1
        s = (c.get("hs_analytics_source") or "UNKNOWN").replace("_", " ").title()
        src[s] = src.get(s, 0) + 1
        l = (c.get("lifecyclestage") or "other").title()
        life[l] = life.get(l, 0) + 1
    srcl = sorted(({"name": k, "n": v} for k, v in src.items()), key=lambda x: -x["n"])[:7]
    smax = max([s["n"] for s in srcl] or [1])
    for s in srcl:
        s["w"] = max(4, int(s["n"] * 100 / smax))
    daily = _series(by_day, "n")
    out["leads"] = {"new30": len(contacts), "daily": daily, "sources": srcl, "lifecycle": sorted(({"name": k, "n": v} for k, v in life.items()), key=lambda x: -x["n"])[:5],
                    "recent": [{"name": _clip(("%s %s" % (c.get("firstname") or "", c.get("lastname") or "")).strip() or c.get("company") or "(no name)", 34), "company": _clip(c.get("company"), 30),
                                "source": (c.get("hs_analytics_source") or "").replace("_", " ").title(), "stage": (c.get("lifecyclestage") or "").title(), "url": _rec("0-1", c["id"]),
                                "age": _age_min(_ts(c.get("createdate")))} for c in contacts[:9]]}
    new7 = sum(1 for c in contacts if _ts(c.get("createdate")) >= now - 7 * 86400)
    out["leads"]["new7"] = new7

    out["totals"] = {}
    for obj in ("contacts", "companies", "deals", "tickets"):
        out["totals"][obj] = _hs_search(obj, [], limit=1, maxn=1)[1]

    tk, _ = _hs_search("tickets", ["subject", "hs_pipeline_stage", "hs_ticket_priority", "createdate", "hs_lastmodifieddate"], [{"propertyName": "hs_pipeline_stage", "operator": "NEQ", "value": "4"}],
                       [{"propertyName": "createdate", "direction": "ASCENDING"}], limit=100)
    tst = {}
    for t in tk:
        lab = (pipes["tickets"].get(t.get("hs_pipeline_stage")) or {}).get("label") or "?"
        tst[lab] = tst.get(lab, 0) + 1
    fresh = sum(1 for t in tk if _age_min(_ts(t.get("createdate"))) is not None and _age_min(_ts(t.get("createdate"))) < 30 * 1440
                and (pipes["tickets"].get(t.get("hs_pipeline_stage")) or {}).get("label") in ("New", "Waiting on us"))
    tk.sort(key=lambda t: t.get("createdate") or "", reverse=True)
    out["tickets"] = {"open": len(tk), "fresh_wait": fresh, "stale": sum(1 for t in tk if (_age_min(_ts(t.get("createdate"))) or 0) > 180 * 1440),
                      "by_stage": [{"name": k, "n": v} for k, v in sorted(tst.items(), key=lambda x: -x[1])],
                      "oldest": [{"name": _clip(t.get("subject") or "(no subject)", 52), "stage": (pipes["tickets"].get(t.get("hs_pipeline_stage")) or {}).get("label") or "", "prio": (t.get("hs_ticket_priority") or "").title(),
                                  "age": _age_min(_ts(t.get("createdate"))), "url": _rec("0-5", t["id"])} for t in tk[:8]]}

    open_f = [{"propertyName": "hs_task_status", "operator": "NEQ", "value": "COMPLETED"}]
    _, t_open = _hs_search("tasks", [], open_f, limit=1, maxn=1)
    _, t_over = _hs_search("tasks", [], open_f + [{"propertyName": "hs_timestamp", "operator": "LT", "value": str(ms)}], limit=1, maxn=1)
    _, t_over30 = _hs_search("tasks", [], open_f + [{"propertyName": "hs_timestamp", "operator": "LT", "value": str(ms)}, {"propertyName": "hs_timestamp", "operator": "GTE", "value": str(d30)}], limit=1, maxn=1)
    nxt, _ = _hs_search("tasks", ["hs_task_subject", "hs_timestamp", "hs_task_priority", "hs_task_type", "hubspot_owner_id"], open_f + [{"propertyName": "hs_timestamp", "operator": "GTE", "value": str(ms)}],
                        [{"propertyName": "hs_timestamp", "direction": "ASCENDING"}], limit=8)
    out["tasks"] = {"open": t_open, "overdue": t_over, "overdue30": t_over30, "next": [{"name": _clip(t.get("hs_task_subject") or "(untitled)", 50), "due": _local(_ts(t.get("hs_timestamp"))).strftime("%a %d %b %H:%M"),
                                                               "prio": (t.get("hs_task_priority") or "").title(), "owner": owners.get(t.get("hubspot_owner_id"), "")} for t in nxt]}

    mt, mtotal = _hs_search("meetings", ["hs_meeting_title", "hs_meeting_start_time", "hs_meeting_outcome"], [{"propertyName": "hs_meeting_start_time", "operator": "GTE", "value": str(ms)}],
                            [{"propertyName": "hs_meeting_start_time", "direction": "ASCENDING"}], limit=6)
    out["meetings"] = {"upcoming": mtotal, "next": [{"name": _clip(m.get("hs_meeting_title") or "Meeting", 50), "when": _local(_ts(m.get("hs_meeting_start_time"))).strftime("%a %d %b %H:%M")} for m in mt]}

    try:
        doms = _hs("/cms/v3/domains").get("results", [])
        out["domains"] = [{"name": d.get("domain"), "ok": bool(d.get("isResolving")), "https": bool(d.get("isHttpsEnabled"))} for d in doms]
    except urllib.error.HTTPError:
        out["domains"] = []
    out["url"] = "%s/contacts/%s" % (HS_UI, HS_PORTAL)
    return out


# ============================================================================================================== WordPress / WooCommerce
def _wp_headers():
    tok = base64.b64encode(("%s:%s" % (_env("WORK_WP_USER"), _env("WORK_WP_KEY"))).encode()).decode()
    return {"Authorization": "Basic " + tok, "User-Agent": "Mozilla/5.0 (glance-admin)"}


def _wp(path, headers_too=False):
    d, h = _http(_env("WORK_WP_URL").rstrip("/") + "/wp-json" + path, _wp_headers(), timeout=30)
    return (d, h) if headers_too else d


def _wp_total(path):
    _, h = _wp(path + ("&" if "?" in path else "?") + "per_page=1", True)
    return int(h.get("X-WP-Total") or 0)


def wp_summary():
    out = {}
    base = _env("WORK_WP_URL").rstrip("/")
    t0 = time.time()
    status = 0
    try:
        req = urllib.request.Request(base + "/", headers={"User-Agent": "Mozilla/5.0 (glance-admin)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read(2048)
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except (urllib.error.URLError, OSError):
        status = 0
    out["site"] = {"url": base, "status": status, "ms": int((time.time() - t0) * 1000), "up": 200 <= status < 400}

    after = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
    orders, page = [], 1
    while page <= 8:
        batch, h = _wp("/wc/v3/orders?per_page=100&orderby=date&order=desc&after=%s&page=%d" % (after, page), True)
        orders += batch
        if page >= int(h.get("X-WP-TotalPages") or 1):
            break
        page += 1
    REV = ("completed", "processing")
    by_day, by_day_n, by_status, prods, by_co = {}, {}, {}, {}, {}
    gross = 0.0
    for o in orders:
        st = o.get("status") or "?"
        by_status[st] = by_status.get(st, 0) + 1
        if st in REV:
            t = _f(o.get("total"))
            gross += t
            d = (o.get("date_created") or "")[:10]
            by_day[d] = by_day.get(d, 0) + t
            by_day_n[d] = by_day_n.get(d, 0) + 1
            cc = (o.get("billing") or {}).get("country") or "??"
            by_co[cc] = by_co.get(cc, 0) + t
            for li in o.get("line_items", []):
                p = prods.setdefault(li.get("name"), {"name": _clip(li.get("name"), 46), "qty": 0, "gbp": 0.0})
                p["qty"] += int(li.get("quantity") or 0)
                p["gbp"] += _f(li.get("total"))
    n_rev = sum(by_status.get(s, 0) for s in REV)
    pr = sorted(prods.values(), key=lambda x: -x["gbp"])[:6]
    pmax = max([p["gbp"] for p in pr] or [1]) or 1
    for p in pr:
        p["fmt"] = _gbp(p["gbp"])
        p["w"] = max(3, int(p["gbp"] * 100 / pmax))
    recent = []
    for o in orders[:10]:
        li = o.get("line_items") or []
        recent.append({"num": o.get("number"), "status": o.get("status"), "fmt": _gbp(_f(o.get("total")), True), "cc": (o.get("billing") or {}).get("country") or "",
                       "who": _clip((o.get("billing") or {}).get("company") or "", 30), "items": _clip(", ".join("%s×%s" % (_clip(i.get("name"), 28), i.get("quantity")) for i in li[:2]), 70),
                       "age": _age_min(_ts((o.get("date_created_gmt") or "") + "+00:00")), "pay": _clip(o.get("payment_method_title"), 24), "url": "%s/wp-admin/post.php?post=%s&action=edit" % (base, o.get("id"))})
    proc = [o for o in orders if o.get("status") == "processing"]
    daily = _series(by_day, "gbp")
    for d in daily:
        d["f"] = _gbp(d["v"])
    out["shop"] = {"n30": n_rev, "gbp30": gross, "fmt30": _gbp(gross), "aov": _gbp(gross / max(1, n_rev), True), "daily": daily, "daily_n": _series(by_day_n, "n"),
                   "status": [{"name": k, "n": v} for k, v in sorted(by_status.items(), key=lambda x: -x[1])], "recent": recent, "products": pr, "processing": len(proc),
                   "countries": [{"cc": k, "fmt": _gbp(v)} for k, v in sorted(by_co.items(), key=lambda x: -x[1])[:6]]}
    try:
        out["shop"]["orders_total"] = _wp_total("/wc/v3/orders")
    except urllib.error.HTTPError:
        pass
    items = _wp("/wc/v3/products?per_page=50&status=publish")
    out["catalog"] = [{"name": _clip(p["name"], 52), "stock": p.get("stock_status"), "qty": p.get("stock_quantity") if p.get("manage_stock") else None, "price": _gbp(_f(p.get("price")), True), "sold": int(_f(p.get("total_sales")))}
                      for p in sorted(items, key=lambda x: -_f(x.get("total_sales")))][:12]
    out["catalog_n"] = len(items)
    c = {}
    for k, p in (("posts", "/wp/v2/posts?status=publish"), ("drafts", "/wp/v2/posts?status=draft"), ("pending", "/wp/v2/posts?status=pending"), ("scheduled", "/wp/v2/posts?status=future"),
                 ("pages", "/wp/v2/pages?status=publish"), ("media", "/wp/v2/media"), ("comments_hold", "/wp/v2/comments?status=hold"), ("users", "/wp/v2/users")):
        try:
            c[k] = _wp_total(p)
        except urllib.error.HTTPError:
            c[k] = None
    out["content"] = c
    posts = _wp("/wp/v2/posts?per_page=6&status=any&orderby=modified&_fields=id,title,status,modified_gmt,link")
    out["posts"] = [{"title": _clip((p.get("title") or {}).get("rendered"), 60).replace("&#8211;", "–").replace("&amp;", "&").replace("&#8217;", "'"), "status": p.get("status"),
                     "age": _age_min(_ts((p.get("modified_gmt") or "") + "+00:00")), "url": p.get("link")} for p in posts]
    plugins = _wp("/wp/v2/plugins")
    act = [p for p in plugins if p.get("status") == "active"]
    out["plugins"] = {"total": len(plugins), "active": len(act), "inactive": len(plugins) - len(act), "names": [_clip(p.get("name"), 28) for p in act][:14]}
    try:
        env = _wp("/wc/v3/system_status").get("environment", {})
        out["stack"] = {"wp": env.get("wp_version"), "php": env.get("php_version"), "wc": env.get("version"), "server": _clip(env.get("server_info"), 30), "db": _clip(env.get("mysql_version"), 20)}
    except urllib.error.HTTPError:
        out["stack"] = {}
    out["admin"] = base + "/wp-admin/"
    return out


# ============================================================================================================== PythonAnywhere
def _pa(path, raw=False, timeout=30):
    url = "https://www.pythonanywhere.com/api/v0/user/%s/%s" % (_env("WORK_PA_USER"), path)
    req = urllib.request.Request(url, headers={"Authorization": "Token " + _env("WORK_PA_TOKEN"), "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read(3_000_000)
        return b.decode("utf-8", "replace") if raw else json.loads(b.decode())


def _next_run(t):
    """PythonAnywhere does not report next_run for most plans: derive it from the schedule (times are UTC)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        minute = int(t.get("minute"))
        if t.get("interval") == "hourly":
            n = now.replace(minute=minute, second=0, microsecond=0)
            if n <= now:
                n += datetime.timedelta(hours=1)
        else:
            n = now.replace(hour=int(t.get("hour")), minute=minute, second=0, microsecond=0)
            if n <= now:
                n += datetime.timedelta(days=1)
        return n.timestamp()
    except (TypeError, ValueError):
        return 0


def _script(cmd):
    m = re.findall(r"python3?(?:\.\d+)?\s+([\w./-]+\.py)", cmd or "")
    return m[-1].split("/")[-1][:-3] if m else _clip(cmd, 40)


def pa_summary():
    out = {}
    cpu = _pa("cpu/")
    lim, used = _f(cpu.get("daily_cpu_limit_seconds"), 1), _f(cpu.get("daily_cpu_total_usage_seconds"))
    out["cpu"] = {"used": int(used), "limit": int(lim), "pct": round(used * 100 / lim, 1) if lim else 0, "reset_min": int((_ts(cpu.get("next_reset_time")) - time.time()) / 60)}
    apps = []
    for w in _pa("webapps/"):
        apps.append({"domain": w.get("domain_name"), "py": w.get("python_version"), "on": bool(w.get("enabled")), "exp": w.get("expiry"), "dir": _clip((w.get("source_directory") or "").split("/")[-1], 28),
                     "url": "https://" + str(w.get("domain_name")).lower()})
    out["apps"] = apps
    tasks = []
    for t in _pa("schedule/"):
        n = _next_run(t)
        tasks.append({"name": _script(t.get("command")), "when": ("every hour at :%02d" % int(t.get("minute"))) if t.get("interval") == "hourly" and str(t.get("minute")).isdigit() else
                      ("daily %02d:%02d UTC" % (int(t.get("hour")), int(t.get("minute"))) if str(t.get("hour")).isdigit() and str(t.get("minute")).isdigit() else str(t.get("interval"))),
                      "on": bool(t.get("enabled")), "in_min": max(0, int((n - time.time()) / 60)) if n else None, "last": t.get("last_run"), "_n": n})
    grouped = {}
    for t in tasks:
        g = grouped.setdefault(t["name"], {"name": t["name"], "when": [], "on": True, "in_min": None, "n": 0, "_n": 1e12})
        g["n"] += 1
        g["when"].append(t["when"].replace("every hour at ", "").replace("daily ", ""))
        g["on"] = g["on"] and t["on"]
        if t["_n"] and t["_n"] < g["_n"]:
            g["_n"], g["in_min"] = t["_n"], t["in_min"]
    tasks = sorted(grouped.values(), key=lambda x: x["_n"])
    for t in tasks:
        t.pop("_n", None)
        hourly = all(w.startswith(":") for w in t["when"])
        t["when"] = ("hourly " + " ".join(t["when"])) if hourly else ", ".join(t["when"])
    out["tasks"] = tasks
    cons = _pa("consoles/")
    out["consoles"] = [{"name": _clip(c.get("name") or c.get("executable"), 32)} for c in cons][:6]
    out["always_on"] = len(_pa("always_on/"))
    logs = []
    for a in apps:
        dom = str(a["domain"])
        try:
            body = _pa("files/path/var/log/%s.error.log" % dom.lower(), raw=True, timeout=40)
        except urllib.error.HTTPError:
            continue
        lines = [l for l in body.splitlines() if l.strip()]
        tail = lines[-400:]
        errs = [l for l in tail if re.search(r"Traceback|Error|Exception|CRITICAL", l)]
        last = ""
        for l in reversed(tail):
            m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", l)
            if m:
                last = m.group(1)
                break
        logs.append({"domain": dom, "lines": len(lines), "errors": len(errs), "last": last, "tail": [_clip(l, 150) for l in errs[-4:]]})
    out["logs"] = logs
    out["url"] = "https://www.pythonanywhere.com/user/%s/" % _env("WORK_PA_USER")
    return out


# ============================================================================================================== combined
def _attention(d):
    a = []

    def add(level, src, text, url=""):
        a.append({"level": level, "src": src, "text": text, "url": url})
    bp, hs, wp, pa = d.get("bp") or {}, d.get("hs") or {}, d.get("wp") or {}, d.get("pa") or {}
    for key, name in (("bp", "Brightpearl"), ("hs", "HubSpot"), ("wp", "WordPress"), ("pa", "PythonAnywhere")):
        if d.get(key) and not d[key].get("ok"):
            add("bad", name, "%s is not answering (%s)" % (name, d[key].get("err")))
    if bp.get("ok"):
        recent_unpaid = [w for w in bp.get("watch", []) if w["sid"] == 16 and (w["age"] or 0) < 60 * 1440]
        if recent_unpaid:
            add("warn", "Brightpearl", "%d order%s awaiting payment (last 60 days, %s)" % (len(recent_unpaid), "" if len(recent_unpaid) == 1 else "s", _gbp(sum(w["gbp"] for w in recent_unpaid))))
        for b in bp.get("board", []):
            if b["sid"] == 15 and b["n"]:
                add("warn", "Brightpearl", "%d back order%s" % (b["n"], "" if b["n"] == 1 else "s"))
    if hs.get("ok"):
        t = hs.get("tickets", {})
        if t.get("fresh_wait"):
            add("warn", "HubSpot", "%d support ticket%s from the last 30 days still new / waiting on us" % (t["fresh_wait"], "" if t["fresh_wait"] == 1 else "s"), HS_UI + "/contacts/%s/objects/0-5/views/all/list" % HS_PORTAL)
        if t.get("stale"):
            add("info", "HubSpot", "%d support ticket%s open for 6+ months (consider closing)" % (t["stale"], "" if t["stale"] == 1 else "s"))
        k = hs.get("tasks", {})
        if k.get("overdue30"):
            add("info", "HubSpot", "%d task%s overdue from the last 30 days (%d older ones overdue too)" % (k["overdue30"], "" if k["overdue30"] == 1 else "s", k["overdue"] - k["overdue30"]), HS_UI + "/tasks/%s" % HS_PORTAL)
        dl = hs.get("deals", {})
        if dl.get("soon"):
            add("info", "HubSpot", "%d deal%s due to close in the next 14 days (%s)" % (len(dl["soon"]), "" if len(dl["soon"]) == 1 else "s", ", ".join(x["name"][:22] for x in dl["soon"][:2])))
        if dl.get("stale_n"):
            add("info", "HubSpot", "%d open deal%s untouched for 30+ days" % (dl["stale_n"], "" if dl["stale_n"] == 1 else "s"))
        for dm in hs.get("domains", []):
            if not dm["ok"]:
                add("warn", "HubSpot", "Domain %s is not resolving" % dm["name"])
    if wp.get("ok"):
        if not wp["site"]["up"]:
            add("bad", "WordPress", "Website returned %s" % (wp["site"]["status"] or "no response"), wp["site"]["url"])
        if wp["shop"]["processing"]:
            add("warn", "WooCommerce", "%d order%s in Processing (to ship)" % (wp["shop"]["processing"], "" if wp["shop"]["processing"] == 1 else "s"), wp["admin"] + "edit.php?post_type=shop_order")
        if wp["content"].get("comments_hold"):
            add("info", "WordPress", "%d comment%s waiting for moderation" % (wp["content"]["comments_hold"], "" if wp["content"]["comments_hold"] == 1 else "s"))
        for c in wp.get("catalog", []):
            if c["stock"] == "outofstock":
                add("warn", "WooCommerce", "Out of stock: %s" % c["name"])
            elif c["qty"] is not None and c["qty"] <= 20:
                add("info", "WooCommerce", "Low stock: %s (%d left)" % (c["name"], c["qty"]))
    if pa.get("ok"):
        if pa["cpu"]["pct"] >= 80:
            add("warn", "PythonAnywhere", "CPU quota %.0f%% used today" % pa["cpu"]["pct"], pa.get("url", ""))
        for ap in pa["apps"]:
            if not ap["on"]:
                add("bad", "PythonAnywhere", "Web app %s is disabled" % ap["domain"])
        for lg in pa.get("logs", []):
            if lg["errors"] >= 5:
                add("info", "PythonAnywhere", "%s error log has %d error lines in its recent tail" % (lg["domain"], lg["errors"]))
    order = {"bad": 0, "warn": 1, "info": 2}
    a.sort(key=lambda x: order[x["level"]])
    return a


def build():
    jobs = {"bp": bp_summary if _env("WORK_BP_TOKEN") else None, "hs": hs_summary if _env("WORK_HUBSPOT_TOKEN") else None,
            "wp": wp_summary if _env("WORK_WP_KEY") else None, "pa": pa_summary if _env("WORK_PA_TOKEN") else None}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(_section, fn) for k, fn in jobs.items() if fn}
        d = {k: f.result() for k, f in futs.items()}
    bp, hs, wp, pa = d.get("bp") or {}, d.get("hs") or {}, d.get("wp") or {}, d.get("pa") or {}
    kpi = {}
    if bp.get("ok"):
        delta = None
        if bp["w7prev"]["gbp"] > 0:
            delta = int(round((bp["w7"]["gbp"] - bp["w7prev"]["gbp"]) * 100 / bp["w7prev"]["gbp"]))
        kpi["bp"] = {"today_fmt": bp["today"]["fmt"], "today_n": bp["today"]["n"], "w7_fmt": bp["w7"]["fmt"], "w7_n": bp["w7"]["n"], "w7_delta": delta, "d30_fmt": bp["d30"]["fmt"], "d30_n": bp["d30"]["n"]}
    if hs.get("ok"):
        kpi["hs"] = {"pipeline_fmt": hs["deals"]["pipeline_fmt"], "open": hs["deals"]["open"], "new7": hs["leads"]["new7"], "tickets": hs["tickets"]["open"], "tasks_over": hs["tasks"]["overdue30"], "won30": hs["deals"]["won30"]["fmt"]}
    if wp.get("ok"):
        kpi["wp"] = {"fmt30": wp["shop"]["fmt30"], "n30": wp["shop"]["n30"], "processing": wp["shop"]["processing"], "up": wp["site"]["up"], "ms": wp["site"]["ms"]}
    d["kpi"] = kpi
    d["attention"] = _attention(d)
    d["at"] = int(time.time())
    return d


# ============================================================================================================== lookups used by the page's search box
def _hs_find(obj, q, props, label):
    r = _hs("/crm/v3/objects/%s/search" % obj, {"query": q, "limit": 5, "properties": props})
    out = []
    for x in r.get("results", []):
        p = x.get("properties") or {}
        if obj == "contacts":
            title = ("%s %s" % (p.get("firstname") or "", p.get("lastname") or "")).strip() or p.get("email") or "(no name)"
            sub = ", ".join(v for v in (p.get("company"), (p.get("lifecyclestage") or "").title()) if v)
            url = _rec("0-1", x["id"])
        elif obj == "companies":
            title, sub, url = p.get("name") or "(no name)", p.get("domain") or "", _rec("0-2", x["id"])
        else:
            title, sub, url = p.get("dealname") or "(deal)", _gbp(_f(p.get("amount"))), _rec("0-3", x["id"])
        out.append({"title": _clip(title, 60), "sub": _clip(sub, 60), "url": url, "kind": label})
    return out


def search(q):
    q = re.sub(r"\s+", " ", str(q or "")).strip()[:80]
    if len(q) < 2:
        raise ValueError("type at least two characters")
    res = {"q": q, "groups": []}
    jobs = []
    if _env("WORK_HUBSPOT_TOKEN"):
        jobs += [("HubSpot contacts", lambda: _hs_find("contacts", q, ["firstname", "lastname", "email", "company", "lifecyclestage"], "contact")),
                 ("HubSpot companies", lambda: _hs_find("companies", q, ["name", "domain"], "company")),
                 ("HubSpot deals", lambda: _hs_find("deals", q, ["dealname", "amount"], "deal"))]
    if _env("WORK_WP_KEY"):
        jobs.append(("WooCommerce orders", lambda: [{"title": "Order #%s" % o.get("number"), "sub": "%s · %s · %s" % (o.get("status"), _gbp(_f(o.get("total")), True), _clip((o.get("billing") or {}).get("company") or (o.get("billing") or {}).get("country"), 30)),
                                                     "url": _env("WORK_WP_URL").rstrip("/") + "/wp-admin/post.php?post=%s&action=edit" % o.get("id"), "kind": "woo"}
                                                    for o in _wp("/wc/v3/orders?per_page=5&search=" + urllib.parse.quote(q))]))
    if _env("WORK_BP_TOKEN"):
        def bp_find():
            ch = _bp_channels()
            if q.isdigit():
                ids = [int(q)]
            else:
                ids = [r["orderId"] for r in _bp_search("/order-service/order-search?customerRef=%s" % urllib.parse.quote(q), per=5, limit=5)]
            if not ids:
                return []
            out = []
            for o in _bp_orders(ids):
                x = _order(o, ch)
                out.append({"title": "Order %s · %s" % (x["id"], x["ref"]), "sub": "%s · %s · %s" % (x["status"], _gbp(x["gbp"], True), x["channel"]), "url": "", "kind": "bp", "id": x["id"]})
            return out
        jobs.append(("Brightpearl orders", bp_find))
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [(name, ex.submit(fn)) for name, fn in jobs]
        for name, f in futs:
            try:
                rows = f.result()
            except Exception:
                rows = None
            res["groups"].append({"name": name, "items": rows or [], "err": rows is None})
    return res


def order(oid):
    oid = int(oid)
    if oid < 1 or oid > 10 ** 9:
        raise ValueError("bad order id")
    ch = _bp_channels()
    got = _bp_orders([oid])
    if not got:
        raise ValueError("no such order")
    o = got[0]
    x = _order(o, ch)
    cur = (o.get("currency") or {})
    return {"id": x["id"], "ref": x["ref"], "status": x["status"], "placed": _local(x["at"]).strftime("%a %d %b %Y %H:%M") if x["at"] else "", "channel": x["channel"], "country": x["country"],
            "total": _gbp(x["gbp"], True), "net": _gbp(x["net"], True), "orig": ("%.2f %s" % (x["orig"], x["cur"])) if x["cur"] != "GBP" else "", "fx": cur.get("exchangeRate") if x["cur"] != "GBP" else "",
            "pay": x["pay"], "ship": x["ship"], "who": x["who"], "rows": [{"name": r["name"], "sku": r["sku"], "qty": int(r["qty"]), "fmt": _gbp(r["gbp"], True)} for r in x["rows"]]}
