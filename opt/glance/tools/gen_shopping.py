#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/shopping.yml: the Shopping tab.
Left: shopping list, wishlist, gift ideas (PIN-locked). Middle: multi-shop search, deals with your alert words, saved eBay searches, price watches.
Right: Raspberry Pi stock, Discogs, purchases and spend. Data and state come from glance-admin (/api/shopping/*).
Re-runnable: python3 /opt/glance/tools/gen_shopping.py [output-path]"""
import json
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/shopping.yml"
GA = "http://${HOST_SVC}:3005"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def card(title, url, template, cache="1m", extra=""):
    return ("        - type: custom-api\n          title: %s\n          title-url: %s\n%s          cache: %s\n          url: %s/api/shopping/summary\n"
            "          template: |\n%s\n") % (title, url, extra, cache, GA, block(template, 12))


def html_widget(title, comp, extra_attrs=""):
    return ("        - type: html\n          title: %s\n          source: |\n            <div class=\"widget-header\"><h2 class=\"uppercase\">%s</h2></div>\n"
            "            <div data-wb=\"%s\" data-wb-noindex%s></div>\n") % (title, title, comp, extra_attrs)


AGE = '{{ if lt (X) 0 }}{{ else if lt (X) 90 }}{{ X }}m ago{{ else if lt (X) 2880 }}{{ div (X) 60 }}h ago{{ else }}{{ div (X) 1440 }}d ago{{ end }}'


def age(x):
    return AGE.replace("X", x)


# ------------------------------------------------------------------------------------------------ search across shops
ENGINES = [
    ["eBay UK", "https://www.ebay.co.uk/sch/i.html?_nkw={QUERY}", "si:ebay"], ["Amazon UK", "https://www.amazon.co.uk/s?k={QUERY}", "si:amazon"],
    ["CeX", "https://uk.webuy.com/search?stext={QUERY}", "mdi:swap-horizontal"], ["Scan", "https://www.scan.co.uk/search?q={QUERY}", "mdi:chip"],
    ["CCL", "https://www.cclonline.com/search/?q={QUERY}", "mdi:chip"], ["Overclockers", "https://www.overclockers.co.uk/search?sSearch={QUERY}", "mdi:chip"],
    ["Argos", "https://www.argos.co.uk/search/{QUERY}/", "mdi:cart-outline"], ["Currys", "https://www.currys.co.uk/search?q={QUERY}", "mdi:cart-outline"],
    ["Screwfix", "https://www.screwfix.com/search?search={QUERY}", "mdi:tools"], ["Toolstation", "https://www.toolstation.com/search?q={QUERY}", "mdi:tools"],
    ["B&Q", "https://www.diy.com/search?term={QUERY}", "mdi:hammer-wrench"], ["Wickes", "https://www.wickes.co.uk/search?text={QUERY}", "mdi:hammer-wrench"],
    ["Rough Trade", "https://www.roughtrade.com/gb/search?q={QUERY}", "mdi:album"], ["Discogs", "https://www.discogs.com/sell/list?q={QUERY}&currency=GBP", "si:discogs"],
    ["Vinted", "https://www.vinted.co.uk/catalog?search_text={QUERY}", "si:vinted"], ["Gumtree", "https://www.gumtree.com/search?search_category=all&q={QUERY}", "mdi:cart-outline"],
    ["Facebook Marketplace", "https://www.facebook.com/marketplace/search/?query={QUERY}", "si:facebook"], ["PriceSpy", "https://pricespy.co.uk/search?search={QUERY}", "mdi:tag-search"],
    ["Google Shopping", "https://www.google.com/search?tbm=shop&gl=uk&q={QUERY}", "si:google"], ["HotUKDeals", "https://www.hotukdeals.com/search?q={QUERY}", "mdi:fire"],
]
search_w = ("        - type: html\n          title: Shop search\n          source: |\n            <div class=\"widget-header\"><h2 class=\"uppercase\">Shop search</h2></div>\n"
            "            <div data-wb=\"search\" data-wb-noindex data-engines='%s'></div>\n") % json.dumps(ENGINES, separators=(",", ":"))

# ------------------------------------------------------------------------------------------------ deals
DEAL_ROW = """
<div class="wb-deal{{ if gt (len (.Array "hits")) 0 }} wb-deal-hit{{ end }}">
  {{ if ne (.String "thumb") "" }}<img src="{{ .String "thumb" }}" alt="" loading="lazy">{{ end }}
  <div class="wb-deal-main">
    <a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a>{{ range .Array "hits" }}<span class="wb-hitchip">{{ .String "" }}</span>{{ end }}
    <div class="size-h6 color-subdue">{{ .String "source" }}{{ if ne (.String "merchant") "" }} &middot; {{ .String "merchant" }}{{ end }}{{ if ne (.String "price") "" }} &middot; <span class="color-primary">{{ .String "price" }}</span>{{ end }} &middot; AGE</div>
  </div>
</div>
""".replace("AGE", age('.Int "age_min"'))

deals_t = """
{{ if .JSON.Bool "deals.ok" }}
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 {{ if gt (.JSON.Int "deals.match_count") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "deals.match_count" }}</div><div class="size-h6">MATCH YOUR WORDS</div></div>
  <div><div class="size-h3 color-highlight">{{ len (.JSON.Array "deals.latest") }}</div><div class="size-h6">LATEST DEALS</div></div>
  <div><div class="size-h3 color-highlight">{{ len (.JSON.Array "deals.terms") }}</div><div class="size-h6">ALERT WORDS</div></div>
</div>
<div data-wb="shop-terms" data-wb-noindex class="margin-bottom-15"></div>
{{ if gt (len (.JSON.Array "deals.matches")) 0 }}
<div class="size-h6 color-primary margin-bottom-5">MATCHING YOUR ALERT WORDS</div>
{{ range .JSON.Array "deals.matches" }}ROW{{ end }}
<div class="margin-bottom-15"></div>
{{ else }}<p class="size-h6 color-subdue margin-bottom-15">No current deal matches your alert words.</p>{{ end }}
<div class="size-h6 color-subdue margin-bottom-5">LATEST</div>
{{ $i := 0 }}{{ range .JSON.Array "deals.latest" }}{{ $i = add $i 1 }}{{ if le $i 12 }}ROW{{ end }}{{ end }}
<details class="wb-fold margin-top-10"><summary>More deals ({{ len (.JSON.Array "deals.latest") }} loaded)</summary>
  <div class="margin-top-10">{{ $j := 0 }}{{ range .JSON.Array "deals.latest" }}{{ $j = add $j 1 }}{{ if gt $j 12 }}ROW{{ end }}{{ end }}</div>
</details>
{{ if gt (len (.JSON.Array "deals.errors")) 0 }}<p class="size-h6 color-subdue margin-top-10">Some sources did not answer: {{ range .JSON.Array "deals.errors" }}{{ .String "" }}; {{ end }}</p>{{ end }}
{{ else }}<p class="color-negative">Deals are not available yet: {{ .JSON.String "deals.err" }}</p>{{ end }}
""".replace("ROW", DEAL_ROW)

# ------------------------------------------------------------------------------------------------ stock + discogs
stock_t = """
{{ if .JSON.Bool "stock.ok" }}
{{ if gt (len (.JSON.Array "stock.items")) 0 }}
<ul class="list list-gap-8 size-h6">
{{ range .JSON.Array "stock.items" }}
  <li><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a><div class="color-subdue">AGE</div></li>
{{ end }}
</ul>
{{ else }}<p class="color-subdue">Nothing in stock in the UK right now. Checked every 15 minutes (rpilocator.com).</p>{{ end }}
{{ else }}<p class="color-negative size-h6">Stock feed unavailable: {{ .JSON.String "stock.err" }}</p>{{ end }}
""".replace("AGE", age('.Int "age_min"'))

discogs_t = """
{{ if .JSON.Bool "discogs.ok" }}
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "discogs.items" }}</div><div class="size-h6">RELEASES</div></div>
  <div><div class="size-h3 color-highlight">&pound;{{ .JSON.Int "discogs.value_median" | formatNumber }}</div><div class="size-h6">MEDIAN VALUE</div></div>
  <div><div class="size-h3 {{ if gt (.JSON.Int "discogs.wantlist") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "discogs.wantlist" }}</div><div class="size-h6">WANTLIST</div></div>
</div>
<p class="size-h6 color-subdue margin-bottom-10">Collection estimated between &pound;{{ .JSON.Int "discogs.value_min" | formatNumber }} (minimum) and &pound;{{ .JSON.Int "discogs.value_max" | formatNumber }} (maximum), by Discogs marketplace data.</p>
{{ if gt (len (.JSON.Array "discogs.wants")) 0 }}
<div class="size-h6 color-primary margin-bottom-5">WANTLIST &middot; CHEAPEST FOR SALE NOW</div>
<ul class="list list-gap-4 size-h6 margin-bottom-10">
{{ range .JSON.Array "discogs.wants" }}
  <li class="flex justify-between gap-10"><a class="color-highlight text-truncate" href="{{ .String "url" }}" target="_blank">{{ .String "artist" }} &ndash; {{ .String "title" }}</a><span class="shrink-0">{{ if gt (.Float "lowest") 0.0 }}&pound;{{ printf "%.2f" (.Float "lowest") }} <span class="color-subdue">({{ .Int "for_sale" }})</span>{{ else }}<span class="color-subdue">none for sale</span>{{ end }}</span></li>
{{ end }}
</ul>
{{ else }}<p class="size-h6 color-subdue margin-bottom-10">Your Discogs wantlist is empty. Add releases to it on Discogs and their cheapest marketplace price will appear here.</p>{{ end }}
<div class="size-h6 color-subdue margin-bottom-5">RECENTLY ADDED</div>
<div class="wb-strip">
{{ range .JSON.Array "discogs.recent" }}
  <div class="wb-card square" style="flex-basis:7rem"><a href="{{ .String "url" }}" target="_blank">
    <img src="{{ .String "thumb" }}" alt="" loading="lazy">
    <div class="wb-title">{{ .String "title" }}</div><div class="wb-sub">{{ .String "artist" }}{{ if ne (.String "year") "" }} &middot; {{ .String "year" }}{{ end }}</div>
  </a></div>
{{ end }}
</div>
<p class="size-h6 margin-top-10"><a class="color-subdue" href="{{ .JSON.String "discogs.profile_url" }}" target="_blank">Open collection on Discogs</a></p>
{{ else if .JSON.Bool "discogs.configured" }}<p class="color-negative size-h6">Discogs: {{ .JSON.String "discogs.err" }}</p>
{{ else }}<p class="color-subdue size-h6">Add DISCOGS_TOKEN to the server .env to see your collection here.</p>{{ end }}
"""

# ------------------------------------------------------------------------------------------------ gift ideas (locked): the widget content is just the interactive component
gifts_t = '<div data-wb="shop-wish" data-gifts="1" data-wb-noindex></div>'

page = "- name: Shopping\n  slug: shopping\n  width: wide\n  columns:\n"
page += "    - size: small\n      widgets:\n"
page += html_widget("Shopping list", "shop-list") + "\n" + html_widget("Wishlist", "shop-wish") + "\n"
page += card("Gift ideas", "http://${HOST_SVC}:3002/shopping", gifts_t, cache="10m", extra="          css-class: wb-restricted\n") + "\n"
page += "    - size: full\n      widgets:\n"
page += search_w + "\n"
page += card("Deals", "https://www.hotukdeals.com", deals_t, cache="1m") + "\n"
page += html_widget("eBay saved searches", "shop-ebay") + "\n"
page += html_widget("Price watches", "shop-watch") + "\n"
page += "    - size: small\n      widgets:\n"
page += card("Raspberry Pi stock (UK)", "https://rpilocator.com/?country=GB", stock_t, cache="5m") + "\n"
page += card("Discogs", "https://www.discogs.com", discogs_t, cache="10m") + "\n"
page += html_widget("Purchases and spend", "shop-spend") + "\n"

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
