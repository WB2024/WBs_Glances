#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/work.yml: the Work tab (Brightpearl, HubSpot, WordPress / WooCommerce, PythonAnywhere).
Everything comes from glance-admin (/api/work/summary, cached and refreshed every 5 minutes; the API keys never leave the server).
The sections are independent: if one system is down its cards say so and the others keep working.
Site addresses come from the Glance environment (WORK_WP_URL, WORK_PA_USER, WORK_HS_PORTAL), nothing business-specific is written here.
Re-runnable: python3 /opt/glance/tools/gen_work.py [output-path]"""
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/work.yml"
GA = "http://${HOST_SVC}:3005"
HS = "https://app-eu1.hubspot.com/contacts/${WORK_HS_PORTAL}"
WP = "${WORK_WP_URL}/wp-admin/"
PA = "https://www.pythonanywhere.com/user/${WORK_PA_USER}/"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def card(title, url, template, cache="1m", extra=""):
    link = "          title-url: %s\n" % url if url else ""
    return ("        - type: custom-api\n          title: %s\n%s%s          cache: %s\n          url: %s/api/work/summary\n"
            "          template: |\n%s\n") % (title, link, extra, cache, GA, block(template, 12))


def ok(src, body, name):
    return '{{ if .JSON.Bool "%s.ok" }}%s{{ else }}<p class="color-negative">%s: {{ .JSON.String "%s.err" }}</p>{{ end }}' % (src, body, name, src)


AGEX = '{{ if lt (X) 1 }}just now{{ else if lt (X) 90 }}{{ X }}m{{ else if lt (X) 2880 }}{{ div (X) 60 }}h{{ else if lt (X) 1051200 }}{{ div (X) 1440 }}d{{ else }}{{ div (div (X) 1440) 365 }}y{{ end }}'


def age(expr):
    return AGEX.replace("X", expr)


# ----------------------------------------------------------------------------------------------- pulse (headline numbers + what needs attention)
pulse = """
{{ if .JSON.Exists "kpi.bp" }}
<div class="wb-wk-kpigroup">
  <div class="size-h6 color-subdue wb-wk-gtitle">SALES ORDERS &middot; BRIGHTPEARL</div>
  <div class="wb-wk-kpis">
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">TODAY</div><div class="wb-wk-big">{{ .JSON.String "kpi.bp.today_fmt" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "kpi.bp.today_n" }} orders</div></div>
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">LAST 7 DAYS</div><div class="wb-wk-big">{{ .JSON.String "kpi.bp.w7_fmt" }}{{ if ne (.JSON.Int "kpi.bp.w7_delta") 0 }}<span class="wb-wk-delta {{ if gt (.JSON.Int "kpi.bp.w7_delta") 0 }}wb-wk-up">&#9650;{{ else }}wb-wk-down">&#9660;{{ end }} {{ .JSON.Int "kpi.bp.w7_delta" }}%</span>{{ end }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "kpi.bp.w7_n" }} orders &middot; vs the week before</div></div>
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">LAST 30 DAYS</div><div class="wb-wk-big">{{ .JSON.String "kpi.bp.d30_fmt" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "kpi.bp.d30_n" }} orders &middot; avg {{ .JSON.String "bp.d30.aov" }}</div></div>
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">QUOTES &middot; RETURNS (30 D)</div><div class="wb-wk-big">{{ .JSON.Int "bp.quotes30" }} <span class="color-subdue">&middot;</span> {{ .JSON.Int "bp.returns30" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "bp.orders_total" | formatNumber }} orders all time</div></div>
  </div>
</div>
{{ end }}
{{ if .JSON.Exists "kpi.hs" }}
<div class="wb-wk-kpigroup">
  <div class="size-h6 color-subdue wb-wk-gtitle">PIPELINE &middot; HUBSPOT</div>
  <div class="wb-wk-kpis">
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">OPEN PIPELINE</div><div class="wb-wk-big">{{ .JSON.String "kpi.hs.pipeline_fmt" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "kpi.hs.open" }} open deals</div></div>
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">WON (30 D)</div><div class="wb-wk-big">{{ .JSON.String "kpi.hs.won30" }}</div><div class="size-h6 color-subdue">{{ if .JSON.Exists "hs.deals.win_rate" }}{{ .JSON.Int "hs.deals.win_rate" }}% win rate{{ else }}&nbsp;{{ end }}</div></div>
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">NEW LEADS (7 D)</div><div class="wb-wk-big">{{ .JSON.Int "kpi.hs.new7" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "hs.leads.new30" }} in 30 days</div></div>
    <div class="wb-wk-kpi {{ if gt (.JSON.Int "hs.tickets.fresh_wait") 0 }}warn{{ end }}"><div class="size-h6 color-subdue">OPEN TICKETS</div><div class="wb-wk-big">{{ .JSON.Int "kpi.hs.tickets" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "hs.tickets.fresh_wait" }} recent need a reply</div></div>
  </div>
</div>
{{ end }}
{{ if .JSON.Exists "kpi.wp" }}
<div class="wb-wk-kpigroup">
  <div class="size-h6 color-subdue wb-wk-gtitle">WEB SHOP &middot; WOOCOMMERCE</div>
  <div class="wb-wk-kpis">
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">LAST 30 DAYS</div><div class="wb-wk-big">{{ .JSON.String "kpi.wp.fmt30" }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "kpi.wp.n30" }} orders</div></div>
    <div class="wb-wk-kpi {{ if gt (.JSON.Int "kpi.wp.processing") 0 }}warn{{ end }}"><div class="size-h6 color-subdue">TO SHIP</div><div class="wb-wk-big">{{ .JSON.Int "kpi.wp.processing" }}</div><div class="size-h6 color-subdue">orders in Processing</div></div>
    <div class="wb-wk-kpi {{ if not (.JSON.Bool "kpi.wp.up") }}bad{{ end }}"><div class="size-h6 color-subdue">WEBSITE</div><div class="wb-wk-big">{{ if .JSON.Bool "kpi.wp.up" }}<span class="color-positive">Online</span>{{ else }}<span class="color-negative">Down</span>{{ end }}</div><div class="size-h6 color-subdue">{{ .JSON.Int "kpi.wp.ms" }} ms home page</div></div>
    <div class="wb-wk-kpi"><div class="size-h6 color-subdue">AUTOMATION CPU</div><div class="wb-wk-big">{{ .JSON.Float "pa.cpu.pct" }}%</div><div class="size-h6 color-subdue">of today's PythonAnywhere quota</div></div>
  </div>
</div>
{{ end }}
<div class="size-h6 color-subdue wb-wk-gtitle margin-top-15">NEEDS ATTENTION</div>
{{ range .JSON.Array "attention" }}
  <div class="wb-wk-att size-h6"><span class="wb-wk-lv {{ .String "level" }}">&#9679;</span><span class="wb-wk-src">{{ .String "src" }}</span>{{ if ne (.String "url") "" }}<a class="grow min-width-0" href="{{ .String "url" }}" target="_blank">{{ .String "text" }}</a>{{ else }}<span class="grow min-width-0">{{ .String "text" }}</span>{{ end }}</div>
{{ else }}<p class="color-positive size-h6">Nothing needs attention right now.</p>{{ end }}
"""

# ----------------------------------------------------------------------------------------------- sales charts
sales_chart = ok("bp", """
<div class="flex justify-between items-baseline margin-bottom-5"><div class="size-h6 color-subdue">REVENUE PER DAY &middot; LAST 30 DAYS</div><div class="size-h6 color-subdue">total {{ .JSON.String "bp.d30.fmt" }}</div></div>
<div class="wb-wk-chart">{{ range .JSON.Array "bp.daily" }}<i style="height:{{ .Int "h" }}%" title="{{ .String "d" }} &middot; {{ .String "f" }}"></i>{{ end }}</div>
<div class="wb-wk-axis size-h6 color-subdue"><span>{{ .JSON.String "bp.from" }}</span><span>today</span></div>
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">ORDERS PER DAY</div>
<div class="wb-wk-chart small cool">{{ range .JSON.Array "bp.daily_n" }}<i style="height:{{ .Int "h" }}%" title="{{ .String "d" }} &middot; {{ .Int "v" }} orders"></i>{{ end }}</div>
""", "Brightpearl")

channels = ok("bp", """
<div class="size-h6 color-subdue margin-bottom-5">REVENUE BY CHANNEL &middot; 30 DAYS</div>
{{ range .JSON.Array "bp.channels" }}<div class="wb-wk-hb size-h6"><span class="nm color-highlight" title="{{ .String "name" }}">{{ .String "name" }}</span><span class="wb-wk-track"><i style="width:{{ .Int "pct" }}%"></i></span><span class="val">{{ .String "fmt" }} <span class="color-subdue">&middot; {{ .Int "n" }}</span></span></div>{{ end }}
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">TOP DESTINATIONS</div>
{{ range .JSON.Array "bp.countries" }}<div class="wb-wk-hb size-h6"><span class="nm color-highlight">{{ .String "cc" }}</span><span class="wb-wk-track cool"><i style="width:{{ .Int "pct" }}%"></i></span><span class="val">{{ .String "fmt" }} <span class="color-subdue">&middot; {{ .Int "n" }}</span></span></div>{{ end }}
""", "Brightpearl")

products = ok("bp", """
{{ range .JSON.Array "bp.products" }}<div class="wb-wk-hb wide size-h6"><span class="nm color-highlight" title="{{ .String "name" }}">{{ .String "name" }}</span><span class="wb-wk-track alt"><i style="width:{{ .Int "w" }}%"></i></span><span class="val">{{ .String "fmt" }} <span class="color-subdue">&middot; {{ .Int "qty" }} units</span></span></div>{{ end }}
""", "Brightpearl")

recent_orders = ok("bp", """
{{ range .JSON.Array "bp.recent" }}
  <div class="wb-wk-row size-h6">
    <div class="main"><button type="button" class="wb-wk-link" data-wk-order="{{ .Int "id" }}">{{ .String "ref" }}</button> <span class="wb-pill">{{ .String "channel" }}</span>{{ if ne (.String "country") "" }} <span class="color-subdue">{{ .String "country" }}</span>{{ end }}{{ if ne (.String "who") "" }} <span class="color-subdue">&middot; {{ .String "who" }}</span>{{ end }}
      <div class="color-subdue text-truncate">{{ .String "items" }}</div></div>
    <div class="side"><div class="color-highlight">{{ .String "fmt" }}</div><div class="color-subdue">{{ .String "status" }} &middot; AGE</div></div>
  </div>
{{ end }}
""".replace("AGE", age('.Int "age"')), "Brightpearl")

orders_attention = ok("bp", """
<div class="wb-wk-chips margin-bottom-10 size-h6">
  {{ range .JSON.Array "bp.board" }}<span class="wb-wk-chip{{ if and (gt (.Int "n") 0) (or (eq (.Int "sid") 16) (eq (.Int "sid") 15)) }} warn{{ end }}"><b>{{ .Int "n" | formatNumber }}</b>{{ .String "name" }}</span>{{ end }}
</div>
<div class="size-h6 color-subdue wb-wk-sub">ORDERS WAITING ON SOMETHING</div>
{{ range .JSON.Array "bp.watch" }}
  <div class="wb-wk-row size-h6">
    <div class="main"><button type="button" class="wb-wk-link" data-wk-order="{{ .Int "id" }}">{{ .String "ref" }}</button> <span class="color-subdue">{{ .String "channel" }}{{ if ne (.String "who") "" }} &middot; {{ .String "who" }}{{ end }}</span></div>
    <div class="side"><span class="color-highlight">{{ .String "fmt" }}</span> <span class="color-subdue">&middot; {{ .String "status" }} &middot; AGE</span></div>
  </div>
{{ else }}<p class="color-positive size-h6">No orders waiting.</p>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">PURCHASE ORDERS IN PROGRESS</div>
{{ range .JSON.Array "bp.po" }}
  <div class="wb-wk-row size-h6"><div class="main">{{ .String "ref" }}{{ if ne (.String "who") "" }} <span class="color-subdue">&middot; {{ .String "who" }}</span>{{ end }}</div><div class="side"><span class="color-highlight">{{ .String "gbp" }}</span> <span class="color-subdue">&middot; {{ .String "status" }} &middot; AGE</span></div></div>
{{ else }}<p class="color-subdue size-h6">No open purchase orders.</p>{{ end }}
""".replace("AGE", age('.Int "age"')), "Brightpearl")

# ----------------------------------------------------------------------------------------------- HubSpot
funnel = ok("hs", """
<div class="size-h6 color-subdue margin-bottom-5">OPEN DEALS BY STAGE &middot; {{ .JSON.Int "hs.deals.open" }} deals &middot; {{ .JSON.String "hs.deals.pipeline_fmt" }}</div>
{{ range .JSON.Array "hs.deals.funnel" }}<div class="wb-wk-hb wide size-h6"><span class="nm color-highlight" title="{{ .String "name" }}">{{ .String "name" }}</span><span class="wb-wk-track"><i style="width:{{ .Int "w" }}%"></i></span><span class="val">{{ .Int "n" }} <span class="color-subdue">&middot; {{ .String "fmt" }}</span></span></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">OPEN PIPELINE BY OWNER</div>
{{ range .JSON.Array "hs.deals.owners" }}<div class="wb-wk-hb size-h6"><span class="nm color-highlight">{{ .String "name" }}</span><span class="wb-wk-track cool"><i style="width:{{ .Int "w" }}%"></i></span><span class="val">{{ .Int "n" }} <span class="color-subdue">&middot; {{ .String "fmt" }}</span></span></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">WON PER MONTH</div>
<div class="wb-wk-chart small alt">{{ range .JSON.Array "hs.deals.months" }}<i style="height:{{ .Int "h" }}%" title="{{ .String "m" }} &middot; {{ .String "f" }}"></i>{{ end }}</div>
<div class="wb-wk-axis size-h6 color-subdue">{{ range .JSON.Array "hs.deals.months" }}<span>{{ .String "m" }}</span>{{ end }}</div>
""", "HubSpot")

deal_lists = ok("hs", """
<div class="size-h6 color-subdue wb-wk-sub">CLOSING IN THE NEXT 14 DAYS</div>
{{ range .JSON.Array "hs.deals.soon" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><a href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a><div class="color-subdue">{{ .String "stage" }}{{ if ne (.String "owner") "" }} &middot; {{ .String "owner" }}{{ end }}</div></div><div class="side"><div class="color-highlight">{{ .String "fmt" }}</div><div class="color-subdue">{{ .String "close" }}</div></div></div>
{{ else }}<p class="color-subdue size-h6">None scheduled.</p>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">LATEST DEALS</div>
{{ range .JSON.Array "hs.deals.recent" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><a href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a><div class="color-subdue">{{ .String "stage" }}</div></div><div class="side"><div class="color-highlight">{{ .String "fmt" }}</div><div class="color-subdue">AGE</div></div></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">BIGGEST DEALS GONE QUIET (30+ DAYS) &middot; {{ .JSON.Int "hs.deals.stale_n" }}</div>
{{ range .JSON.Array "hs.deals.stale" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><a href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a><div class="color-subdue">{{ .String "stage" }}{{ if ne (.String "owner") "" }} &middot; {{ .String "owner" }}{{ end }}</div></div><div class="side"><div class="color-highlight">{{ .String "fmt" }}</div><div class="color-subdue">{{ .Int "idle" }} d idle</div></div></div>{{ end }}
""".replace("AGE", age('.Int "age"')), "HubSpot")

leads = ok("hs", """
<div class="flex justify-between items-baseline margin-bottom-5"><div class="size-h6 color-subdue">NEW CONTACTS PER DAY &middot; 30 DAYS</div><div class="size-h6 color-subdue">{{ .JSON.Int "hs.leads.new30" }} total</div></div>
<div class="wb-wk-chart small alt">{{ range .JSON.Array "hs.leads.daily" }}<i style="height:{{ .Int "h" }}%" title="{{ .String "d" }} &middot; {{ .Int "v" }}"></i>{{ end }}</div>
<div class="size-h6 color-subdue wb-wk-sub">WHERE THEY COME FROM</div>
{{ range .JSON.Array "hs.leads.sources" }}<div class="wb-wk-hb size-h6"><span class="nm color-highlight">{{ .String "name" }}</span><span class="wb-wk-track cool"><i style="width:{{ .Int "w" }}%"></i></span><span class="val">{{ .Int "n" }}</span></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">LATEST</div>
{{ range .JSON.Array "hs.leads.recent" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><a href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a>{{ if ne (.String "company") "" }}<span class="color-subdue"> &middot; {{ .String "company" }}</span>{{ end }}</div><div class="side color-subdue">{{ .String "source" }} &middot; AGE</div></div>{{ end }}
""".replace("AGE", age('.Int "age"')), "HubSpot")

support = ok("hs", """
<div class="wb-wk-chips margin-bottom-10 size-h6">
  <span class="wb-wk-chip"><b>{{ .JSON.Int "hs.tickets.open" }}</b>open tickets</span>
  {{ range .JSON.Array "hs.tickets.by_stage" }}<span class="wb-wk-chip"><b>{{ .Int "n" }}</b>{{ .String "name" }}</span>{{ end }}
</div>
<div class="size-h6 color-subdue wb-wk-sub">NEWEST OPEN TICKETS</div>
{{ range .JSON.Array "hs.tickets.oldest" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><a href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a><div class="color-subdue">{{ .String "stage" }}{{ if ne (.String "prio") "" }} &middot; {{ .String "prio" }}{{ end }}</div></div><div class="side color-subdue">AGE</div></div>{{ else }}<p class="color-positive size-h6">No open tickets.</p>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">NEXT TASKS &middot; {{ .JSON.Int "hs.tasks.open" }} open, {{ .JSON.Int "hs.tasks.overdue30" }} overdue this month</div>
{{ range .JSON.Array "hs.tasks.next" }}<div class="wb-wk-row size-h6"><div class="main text-truncate">{{ .String "name" }}<div class="color-subdue">{{ .String "owner" }}{{ if and (ne (.String "prio") "") (ne (.String "prio") "None") }} &middot; {{ .String "prio" }}{{ end }}</div></div><div class="side color-subdue">{{ .String "due" }}</div></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">UPCOMING MEETINGS &middot; {{ .JSON.Int "hs.meetings.upcoming" }}</div>
{{ range .JSON.Array "hs.meetings.next" }}<div class="wb-wk-row size-h6"><div class="main text-truncate">{{ .String "name" }}</div><div class="side color-subdue">{{ .String "when" }}</div></div>{{ else }}<p class="color-subdue size-h6">No meetings booked.</p>{{ end }}
""".replace("AGE", age('.Int "age"')), "HubSpot")

# ----------------------------------------------------------------------------------------------- shop and site
shop = ok("wp", """
<div class="flex justify-between items-baseline margin-bottom-5"><div class="size-h6 color-subdue">SHOP REVENUE PER DAY &middot; 30 DAYS</div><div class="size-h6 color-subdue">{{ .JSON.String "wp.shop.fmt30" }} &middot; {{ .JSON.Int "wp.shop.n30" }} orders &middot; avg {{ .JSON.String "wp.shop.aov" }}</div></div>
<div class="wb-wk-chart small">{{ range .JSON.Array "wp.shop.daily" }}<i style="height:{{ .Int "h" }}%" title="{{ .String "d" }} &middot; {{ .String "f" }}"></i>{{ end }}</div>
<div class="wb-wk-chips margin-top-10 size-h6">{{ range .JSON.Array "wp.shop.status" }}<span class="wb-wk-chip{{ if eq (.String "name") "processing" }} warn{{ end }}"><b>{{ .Int "n" }}</b>{{ .String "name" }}</span>{{ end }}</div>
<div class="size-h6 color-subdue wb-wk-sub">LATEST ORDERS</div>
{{ range .JSON.Array "wp.shop.recent" }}<div class="wb-wk-row size-h6"><div class="main"><a href="{{ .String "url" }}" target="_blank">#{{ .String "num" }}</a> <span class="wb-pill">{{ .String "status" }}</span>{{ if ne (.String "cc") "" }} <span class="color-subdue">{{ .String "cc" }}</span>{{ end }}{{ if ne (.String "who") "" }} <span class="color-subdue">&middot; {{ .String "who" }}</span>{{ end }}<div class="color-subdue text-truncate">{{ .String "items" }}</div></div><div class="side"><div class="color-highlight">{{ .String "fmt" }}</div><div class="color-subdue">AGE</div></div></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">BEST SELLERS (30 D)</div>
{{ range .JSON.Array "wp.shop.products" }}<div class="wb-wk-hb wide size-h6"><span class="nm color-highlight" title="{{ .String "name" }}">{{ .String "name" }}</span><span class="wb-wk-track alt"><i style="width:{{ .Int "w" }}%"></i></span><span class="val">{{ .String "fmt" }} <span class="color-subdue">&middot; {{ .Int "qty" }}</span></span></div>{{ end }}
""".replace("AGE", age('.Int "age"')), "WooCommerce")

catalog = ok("wp", """
{{ range .JSON.Array "wp.catalog" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><span class="{{ if eq (.String "stock") "instock" }}color-positive{{ else if eq (.String "stock") "outofstock" }}color-negative{{ else }}color-primary{{ end }}">&#9679;</span> {{ .String "name" }}</div><div class="side color-subdue">{{ if .Exists "qty" }}{{ if ne (.String "qty") "" }}{{ .Int "qty" }} in stock &middot; {{ end }}{{ end }}{{ .String "price" }} &middot; {{ .Int "sold" }} sold</div></div>{{ end }}
""", "WooCommerce")

site = ok("wp", """
<div class="wb-wk-sys size-h6"><span class="{{ if .JSON.Bool "wp.site.up" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow">Website</span><span class="color-subdue">HTTP {{ .JSON.Int "wp.site.status" }} &middot; {{ .JSON.Int "wp.site.ms" }} ms</span></div>
<div class="wb-wk-chips margin-top-5 margin-bottom-10 size-h6">
  <span class="wb-wk-chip"><b>{{ .JSON.Int "wp.content.posts" }}</b>posts</span>
  <span class="wb-wk-chip{{ if gt (.JSON.Int "wp.content.drafts") 0 }} warn{{ end }}"><b>{{ .JSON.Int "wp.content.drafts" }}</b>drafts</span>
  <span class="wb-wk-chip"><b>{{ .JSON.Int "wp.content.pages" }}</b>pages</span>
  <span class="wb-wk-chip"><b>{{ .JSON.Int "wp.content.media" }}</b>media</span>
  <span class="wb-wk-chip"><b>{{ .JSON.Int "wp.content.users" }}</b>accounts</span>
  <span class="wb-wk-chip"><b>{{ .JSON.Int "wp.plugins.active" }}</b>plugins active</span>
</div>
<div class="size-h6 color-subdue wb-wk-sub">RECENTLY EDITED</div>
{{ range .JSON.Array "wp.posts" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><a href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a></div><div class="side color-subdue">{{ .String "status" }} &middot; AGE</div></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">STACK</div>
<div class="size-h6 color-subdue">WordPress {{ .JSON.String "wp.stack.wp" }} &middot; WooCommerce {{ .JSON.String "wp.stack.wc" }} &middot; PHP {{ .JSON.String "wp.stack.php" }} &middot; {{ .JSON.String "wp.stack.server" }}</div>
""".replace("AGE", age('.Int "age"')), "WordPress")

# ----------------------------------------------------------------------------------------------- PythonAnywhere
automation = ok("pa", """
<div class="flex justify-between items-baseline margin-bottom-5"><div class="size-h6 color-subdue">CPU QUOTA TODAY</div><div class="size-h6 color-subdue">{{ .JSON.Int "pa.cpu.used" }} / {{ .JSON.Int "pa.cpu.limit" }} s &middot; resets in {{ div (.JSON.Int "pa.cpu.reset_min") 60 }} h</div></div>
<div class="wb-wk-gauge"><i class="{{ if gt (.JSON.Float "pa.cpu.pct") 85.0 }}hi{{ else if gt (.JSON.Float "pa.cpu.pct") 60.0 }}mid{{ end }}" style="width:{{ .JSON.Float "pa.cpu.pct" }}%"></i></div>
<div class="size-h6 color-subdue wb-wk-sub">WEB APPS</div>
{{ range .JSON.Array "pa.apps" }}<div class="wb-wk-sys size-h6"><span class="{{ if .Bool "on" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow text-truncate"><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "domain" }}</a></span><span class="color-subdue">Python {{ .String "py" }} &middot; {{ .String "dir" }}</span></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">SCHEDULED TASKS &middot; {{ len (.JSON.Array "pa.tasks") }}</div>
{{ range .JSON.Array "pa.tasks" }}<div class="wb-wk-row size-h6"><div class="main text-truncate"><span class="{{ if .Bool "on" }}color-positive{{ else }}color-subdue{{ end }}">&#9679;</span> {{ .String "name" }}<div class="color-subdue">{{ .String "when" }}</div></div><div class="side color-subdue">{{ if .Exists "in_min" }}next in {{ if lt (.Int "in_min") 90 }}{{ .Int "in_min" }} min{{ else }}{{ div (.Int "in_min") 60 }} h{{ end }}{{ end }}</div></div>{{ end }}
<div class="size-h6 color-subdue wb-wk-sub">ERROR LOGS (RECENT TAIL)</div>
{{ range .JSON.Array "pa.logs" }}<div class="wb-wk-sys size-h6"><span class="{{ if gt (.Int "errors") 4 }}color-primary{{ else }}color-positive{{ end }}">&#9679;</span><span class="grow text-truncate">{{ .String "domain" }}</span><span class="color-subdue">{{ .Int "errors" }} error lines &middot; last entry {{ .String "last" }}</span></div>{{ else }}<p class="color-subdue size-h6">No log information.</p>{{ end }}
<div class="size-h6 color-subdue margin-top-10">{{ .JSON.Int "pa.always_on" }} always-on tasks &middot; {{ len (.JSON.Array "pa.consoles") }} open consoles</div>
""", "PythonAnywhere")

# ----------------------------------------------------------------------------------------------- sidebar
status = """
<div class="wb-wk-sys size-h6"><span class="{{ if .JSON.Bool "bp.ok" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow">Brightpearl</span><span class="color-subdue">{{ if .JSON.Bool "bp.ok" }}{{ .JSON.String "bp.budget" }} calls left{{ else }}{{ .JSON.String "bp.err" }}{{ end }}</span></div>
<div class="wb-wk-sys size-h6"><span class="{{ if .JSON.Bool "hs.ok" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow">HubSpot</span><span class="color-subdue">{{ if .JSON.Bool "hs.ok" }}{{ .JSON.Int "hs.totals.contacts" | formatNumber }} contacts{{ else }}{{ .JSON.String "hs.err" }}{{ end }}</span></div>
<div class="wb-wk-sys size-h6"><span class="{{ if .JSON.Bool "wp.ok" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow">WordPress</span><span class="color-subdue">{{ if .JSON.Bool "wp.ok" }}{{ .JSON.Int "wp.site.ms" }} ms{{ else }}{{ .JSON.String "wp.err" }}{{ end }}</span></div>
<div class="wb-wk-sys size-h6"><span class="{{ if .JSON.Bool "pa.ok" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow">PythonAnywhere</span><span class="color-subdue">{{ if .JSON.Bool "pa.ok" }}{{ len (.JSON.Array "pa.tasks") }} tasks{{ else }}{{ .JSON.String "pa.err" }}{{ end }}</span></div>
{{ if .JSON.Bool "hs.ok" }}<div class="size-h6 color-subdue wb-wk-sub">HUBSPOT DOMAINS</div>
{{ range .JSON.Array "hs.domains" }}<div class="wb-wk-sys size-h6"><span class="{{ if .Bool "ok" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span><span class="grow text-truncate">{{ .String "name" }}</span><span class="color-subdue">{{ if .Bool "https" }}https{{ else }}http{{ end }}</span></div>{{ end }}{{ end }}
<div class="margin-top-15" data-wb="work-refresh" data-wb-noindex></div>
""".replace('{{ range $k, $n := (dict) }}{{ end }}\n', "")

search_w = """        - type: html
          title: Work search
          source: |
            <div class="widget-header"><h2 class="uppercase">Work search</h2></div>
            <div data-wb="work-search" data-wb-noindex></div>
"""

links = """        - type: bookmarks
          title: Work links
          groups:
            - links:
                - { title: "HubSpot",                url: "https://app-eu1.hubspot.com/contacts/${WORK_HS_PORTAL}",                                icon: si:hubspot }
                - { title: "HubSpot deals",          url: "https://app-eu1.hubspot.com/contacts/${WORK_HS_PORTAL}/objects/0-3/views/all/board",     icon: si:hubspot }
                - { title: "HubSpot tickets",        url: "https://app-eu1.hubspot.com/contacts/${WORK_HS_PORTAL}/objects/0-5/views/all/list",     icon: si:hubspot }
                - { title: "HubSpot tasks",          url: "https://app-eu1.hubspot.com/tasks/${WORK_HS_PORTAL}",                                    icon: si:hubspot }
                - { title: "Brightpearl",            url: "https://euw1.brightpearl.com",                                                    icon: mdi:package-variant-closed }
                - { title: "WordPress admin",        url: "${WORK_WP_URL}/wp-admin/",                                                               icon: si:wordpress }
                - { title: "WooCommerce orders",     url: "${WORK_WP_URL}/wp-admin/edit.php?post_type=shop_order",                                  icon: si:woocommerce }
                - { title: "PythonAnywhere",         url: "https://www.pythonanywhere.com/user/${WORK_PA_USER}/",                                   icon: si:pythonanywhere }
                - { title: "PythonAnywhere tasks",   url: "https://www.pythonanywhere.com/user/${WORK_PA_USER}/tasks_tab/",                         icon: si:pythonanywhere }
"""

# ----------------------------------------------------------------------------------------------- page
page = "- name: Work\n  slug: work\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += card("Business pulse", HS, pulse) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Sales", None, sales_chart), 12) + "\n"
page += block(card("Channels and destinations", None, channels), 12) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Latest sales orders", None, recent_orders), 12) + "\n"
page += block(card("Top products", None, products), 12) + "\n"
page += card("Orders needing attention", None, orders_attention) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Sales pipeline", HS + "/objects/0-3/views/all/board", funnel), 12) + "\n"
page += block(card("Deals to watch", HS + "/objects/0-3/views/all/board", deal_lists), 12) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Leads", HS + "/objects/0-1/views/all/list", leads), 12) + "\n"
page += block(card("Support and follow-ups", HS + "/objects/0-5/views/all/list", support), 12) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Web shop", WP + "edit.php?post_type=shop_order", shop), 12) + "\n"
page += block(card("Website", WP, site), 12) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Shop catalogue", WP + "edit.php?post_type=product", catalog), 12) + "\n"
page += block(card("Automation (PythonAnywhere)", PA, automation), 12) + "\n"
page += "    - size: small\n      widgets:\n" + search_w + "\n"
page += card("Systems", None, status, cache="1m") + "\n"
page += links

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
