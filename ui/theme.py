"""SentinelGraph visual identity: HH Goa palette (forest green, warm yellow, pink for critical, cream cards)."""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Oranienbaum&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{
  --bg:#062A19; --s1:#0A3722; --s2:#0E452B; --line:#185C3A; --line2:#24744C;
  --ink:#FFF8E4; --ink2:#D2E2D2; --mute:#94B8A0;
  --green:#0C7A3E; --green-2:#0B6B37; --yellow:#FFE01B; --pink:#EE1E7C; --lime:#8CC63F;
  --serif:"Oranienbaum","Playfair Display",Georgia,serif;
  --legit:#79D9A0; --legit-soft:rgba(121,217,160,.14);
  --crit:#FF4F98; --crit-soft:rgba(238,30,124,.16);
  --warn:#FFE01B; --warn-soft:rgba(255,224,27,.13);
  --cream:#FFFBEF; --cream-ink:#17261E; --cream-mute:#5E6F63; --cream-line:#E0D8C3;
  --display:"Bricolage Grotesque","IBM Plex Sans",system-ui,sans-serif;
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
body,.stApp,.stMarkdown,p,label,input,textarea,button,div[data-testid="stHtml"]{font-family:var(--sans)}
.stApp{background:var(--bg)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"],[data-testid="stDecoration"],footer,#MainMenu{display:none!important}
.block-container{padding-top:1.6rem!important;padding-bottom:3rem!important;max-width:1360px}
section[data-testid="stSidebar"]{background:#0E2119;border-right:1px solid var(--line)}
[data-testid="stSidebarNav"] a{border-radius:8px}
[data-testid="stSidebarNav"] a[aria-current="page"]{background:rgba(242,201,76,.12)}
[data-testid="stSidebarNav"] a[aria-current="page"] span{color:var(--yellow)!important;font-weight:600}
[data-testid="stNavSectionHeader"]{font:500 11px/1.2 var(--mono)!important;letter-spacing:.12em;color:var(--mute)!important;text-transform:uppercase}
.stButton>button[kind="primary"]{background:var(--yellow);color:#1B1A0C;border:0;font-weight:600}
.stButton>button[kind="primary"]:hover{background:#FFD866;color:#1B1A0C}
.stTabs [data-baseweb="tab-list"]{gap:2px;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{height:40px;padding:0 14px;color:var(--mute)}
.stTabs [aria-selected="true"]{color:var(--ink)!important}
.stTabs [data-baseweb="tab-highlight"]{background:var(--yellow)}

.eyebrow{font:500 11px/1.4 var(--mono);letter-spacing:.11em;text-transform:uppercase;color:var(--mute)}
.mono{font-family:var(--mono)!important}
.muted{color:var(--mute)} .ink2{color:var(--ink2)}
h1.page{font:800 34px/1.05 var(--display);letter-spacing:-.01em;color:var(--ink);margin:4px 0 6px}
.sub{color:var(--ink2);font-size:14.5px;margin-bottom:18px}

/* status chips */
.chip{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 10px;font:500 12px/1.5 var(--mono);
  border:1px solid var(--line2);color:var(--ink2);background:var(--s1)}
.chip .d{width:7px;height:7px;border-radius:50%}
.c-legit{color:var(--legit);border-color:rgba(121,217,160,.4);background:var(--legit-soft)}
.c-crit{color:var(--crit);border-color:rgba(255,92,147,.45);background:var(--crit-soft)}
.c-warn{color:var(--warn);border-color:rgba(242,201,76,.45);background:var(--warn-soft)}
.badge{display:inline-block;font:600 10.5px/1.6 var(--mono);letter-spacing:.06em;padding:0 7px;border-radius:4px;
  background:#1D3A2C;color:var(--ink2);border:1px solid var(--line2)}
.badge.tg{background:rgba(242,201,76,.14);color:var(--yellow);border-color:rgba(242,201,76,.35)}
.badge.mem{background:rgba(121,217,160,.12);color:var(--legit);border-color:rgba(121,217,160,.35)}
.badge.cust{background:rgba(255,92,147,.10);color:#FF9DBE;border-color:rgba(255,92,147,.35)}
.badge.rag{background:rgba(160,196,255,.10);color:#A9C8FF;border-color:rgba(160,196,255,.3)}

/* case header */
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.head .line{font:500 13px/1.6 var(--mono);color:var(--ink2);margin-top:4px}

/* four questions */
.q4{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:16px;overflow:hidden;margin:16px 0 14px}
@media(max-width:1100px){.q4{grid-template-columns:1fr 1fr}}
.q4>div{background:var(--s1);padding:16px 18px}
.q4 .a{font:600 17px/1.35 var(--display);color:var(--ink);margin-top:8px}
.q4 .b{font-size:13px;line-height:1.5;color:var(--ink2);margin-top:6px}
.q4 .next .a{color:var(--yellow)}

/* kpis */
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:14px}
@media(max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}}
.kpi{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--s1)}
.kpi .n{font:600 22px/1.15 var(--mono);color:var(--ink);font-variant-numeric:tabular-nums;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .l{font-size:12px;color:var(--mute);margin-top:2px}

/* next best action */
.nba{border:1px solid rgba(242,201,76,.35);border-radius:16px;background:linear-gradient(180deg,#0E4A2C 0%,#0A3722 70%);padding:20px 22px;height:100%}
.nba .big{font:800 30px/1.1 var(--display);color:var(--ink);margin:10px 0 6px;display:flex;align-items:center;gap:12px}
.nba .big .ic{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;font:700 18px var(--mono)}
.nba .why{font-size:14.5px;line-height:1.55;color:var(--ink2);max-width:680px}
.alist{display:flex;flex-direction:column;gap:6px;margin-top:16px}
.arow{display:grid;grid-template-columns:22px 1fr auto;gap:10px;align-items:center;padding:8px 10px;border-radius:9px;background:rgba(11,26,20,.55)}
.arow .t{font:500 13.5px var(--sans);color:var(--ink)}
.arow .r{font:12px var(--sans);color:var(--mute)}
.arow .s{font:500 11px var(--mono);color:var(--mute);text-align:right;white-space:nowrap}
.gov{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border-radius:10px;overflow:hidden;margin-top:16px}
@media(max-width:1000px){.gov{grid-template-columns:1fr 1fr}}
.gov div{background:#0F2219;padding:10px 12px}
.gov .v{font:500 13px/1.4 var(--sans);color:var(--ink);margin-top:3px}

/* panels */
.panel{border:1px solid var(--line);border-radius:16px;background:var(--s1);padding:18px 20px;height:100%}
.meter{margin:10px 0 14px}
.meter .top{display:flex;justify-content:space-between;font-size:13px;color:var(--ink2)}
.meter .top b{font:600 13px var(--mono);color:var(--ink)}
.meter .track{height:8px;border-radius:4px;background:#1C372A;margin-top:6px;overflow:hidden}
.meter .fill{height:100%;border-radius:4px}
.tick{display:grid;grid-template-columns:18px 1fr;gap:8px;font-size:13.5px;line-height:1.45;color:var(--ink2);padding:4px 0}
.tick .i{font:700 13px var(--mono)}
.stopbox{margin-top:14px;border-top:1px dashed var(--line2);padding-top:14px}
.stopbox h4{font:700 16px/1.2 var(--display);color:var(--ink);margin:0 0 8px}

/* evolution */
.evo{display:grid;grid-template-columns:1fr 44px 1fr 44px 1fr;align-items:stretch;margin:6px 0 4px}
@media(max-width:1000px){.evo{grid-template-columns:1fr}.evo .arr{display:none}}
.evo .st{border:1px solid var(--line);border-radius:14px;background:var(--s1);padding:14px 16px}
.evo .st.mid{border-style:dashed;border-color:var(--line2);background:transparent}
.evo .arr{display:grid;place-items:center;color:var(--yellow);font:700 20px var(--mono)}
.evo .row{display:flex;justify-content:space-between;font-size:13px;color:var(--ink2);padding:3px 0}
.evo .row b{font:500 13px var(--mono);color:var(--ink)}
.evo .sact{margin-top:8px;font:600 14px var(--display);color:var(--ink)}
.evo .reply{font-size:13px;line-height:1.5;color:var(--ink2);margin-top:8px}

/* cream evidence cards */
.ev{background:var(--cream);color:var(--cream-ink);border-radius:12px;padding:12px 14px;border-left:5px solid var(--green)}
.ev.fraud{border-left-color:var(--pink)} .ev.legit{border-left-color:var(--green)} .ev.neutral{border-left-color:#B9B09A}
.ev .c{font-size:14px;line-height:1.5}
.ev .m{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;align-items:center}
.ev .m .ref{font:11.5px var(--mono);color:var(--cream-mute)}
.ev .badge{background:#E7DFC9;color:#2B3A31;border-color:#D8CFB6}
.ev .badge.tg{background:#F7E3A1;color:#5A4600;border-color:#EBCB6A}
.ev .badge.mem{background:#D3EEDD;color:#1D5A37;border-color:#AFDCC0}
.ev .badge.cust{background:#FFD9E6;color:#8A1740;border-color:#F5B4CB}
.ev .badge.rag{background:#DCE7FA;color:#26457A;border-color:#BCD0F1}
.ev .lr{font:600 11.5px var(--mono);color:var(--cream-ink);margin-left:auto}
.evgrid{display:flex;flex-direction:column;gap:8px}
.sec{display:flex;align-items:baseline;justify-content:space-between;margin:22px 0 10px}
.sec h3{font:800 20px/1.2 var(--display);color:var(--ink);margin:0}
.layer{font:600 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;margin:14px 0 8px;display:flex;gap:8px;align-items:center}
.layer .n{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:11px;background:var(--s2);color:var(--ink)}
.assess{display:grid;grid-template-columns:170px 1fr 64px;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}
.assess .bar{height:10px;border-radius:3px}
.assess .x{font:500 12px var(--mono);color:var(--ink);text-align:right}
.decision{border:1px solid var(--line2);border-radius:12px;padding:12px 14px;background:var(--s2);font-size:13.5px;line-height:1.55;color:var(--ink2)}

/* activity */
.act{display:grid;grid-template-columns:58px 14px 1fr;gap:8px;padding:6px 0;font-size:13px;line-height:1.4}
.act .tm{font:500 11.5px var(--mono);color:var(--mute);padding-top:1px}
.act .dt{width:9px;height:9px;border-radius:50%;margin-top:5px}
.act .tt{color:var(--ink)} .act .xx{font:11.5px var(--mono);color:var(--mute);margin-top:2px}

/* tables */
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--s1)}
.tbl table{border-collapse:collapse;width:100%;font-size:13px;min-width:960px}
.tbl th{font:500 11px/1.3 var(--mono);text-transform:uppercase;letter-spacing:.07em;color:var(--mute);text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
.tbl td{padding:10px 12px;border-bottom:1px solid var(--line);color:var(--ink2);vertical-align:top}
.tbl tr:last-child td{border-bottom:0}
.tbl .num{font-family:var(--mono);text-align:right;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl a{color:var(--yellow);text-decoration:none;font-family:var(--mono);white-space:nowrap}
.tbl .acts{font:11.5px/1.5 var(--mono);color:var(--mute)}
.stat4{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}

/* sar */
.sar{background:var(--cream);color:var(--cream-ink);border-radius:14px;overflow:hidden}
.sar .hd{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid var(--cream-line)}
.sar .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));border-bottom:1px solid var(--cream-line)}
.sar .grid div{padding:10px 18px}
.sar .eyebrow{color:var(--cream-mute)}
.sar .body{padding:16px 18px;font-size:14.5px;line-height:1.7;max-width:920px}

.side-status{font-size:12.5px;color:var(--ink2);line-height:1.9;border-top:1px solid var(--line);padding-top:10px;margin-top:8px}
.side-status .d{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:7px;vertical-align:1px}
.side-status b{font:500 12px var(--mono);color:var(--ink);float:right}
.empty{border:1px dashed var(--line2);border-radius:16px;padding:44px;text-align:center;color:var(--mute)}
.lv{display:grid;grid-template-columns:96px 1fr auto;gap:10px;font-size:13px;padding:3px 0;border-bottom:1px solid var(--line)}
.lv .k{font:500 11px/1.8 var(--mono);text-transform:uppercase}
.lv .x{font:11.5px var(--mono);color:var(--mute);white-space:nowrap}

/* ---- HH Goa site layer: vivid green, lemon-yellow condensed serif titles, pinned notice cards, cross-stitch rules ---- */
section[data-testid="stSidebar"]{background:#0B6B37;border-right:0}
section[data-testid="stSidebar"] *{--mute:#BFE3C9}
[data-testid="stSidebarNav"] a[aria-current="page"]{background:rgba(255,224,27,.16)}
[data-testid="stNavSectionHeader"]{color:#FFE01B!important;opacity:.85}
h1.page{font:400 56px/.95 var(--serif);text-transform:uppercase;letter-spacing:.01em;color:var(--yellow);margin:6px 0 8px}
.sec{border-bottom:0;padding-bottom:12px;margin:34px 0 12px;position:relative}
.sec::after{content:"";position:absolute;left:0;right:0;bottom:0;height:10px;opacity:.9;
  background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='10'%3E%3Cpath d='M2 1l8 8M10 1l-8 8' stroke='%238CC63F' stroke-width='2.2' stroke-linecap='round'/%3E%3C/svg%3E") repeat-x}
.sec h3{font:400 34px/1 var(--serif);text-transform:uppercase;color:var(--yellow);letter-spacing:.01em}
.nba .big{font:400 44px/1 var(--serif);text-transform:uppercase;letter-spacing:.01em}
.nba{border:2px solid var(--yellow);box-shadow:6px 6px 0 #021A0F}
/* notice-board cards for the four questions */
.q4{background:transparent;border:0;gap:18px;overflow:visible;margin:22px 0 18px}
.q4>div{background:var(--cream);color:var(--cream-ink);border-radius:4px;box-shadow:5px 5px 0 #021A0F;position:relative;padding:22px 18px 18px}
.q4>div::before{content:"";position:absolute;top:-7px;left:50%;width:14px;height:14px;margin-left:-7px;border-radius:50%;
  background:radial-gradient(circle at 35% 35%,#fff 0 25%,#d8d2c0 60%);box-shadow:0 1px 2px rgba(0,0,0,.4)}
.q4>div:nth-child(2)::before{background:radial-gradient(circle at 35% 35%,#fff 0 20%,var(--pink) 45%)}
.q4>div:nth-child(4)::before{background:radial-gradient(circle at 35% 35%,#fff 0 20%,var(--yellow) 45%)}
.q4 .eyebrow{color:var(--pink)}
.q4 .a{color:#0B3B22;font:700 18px/1.3 var(--display)}
.q4 .b{color:#44574B}
.q4 .next{background:#0B6B37!important;color:var(--ink)!important}
.q4 .next .eyebrow{color:var(--yellow)} .q4 .next .a{color:var(--yellow)} .q4 .next .b{color:#D9EFDF}
.kpi{box-shadow:3px 3px 0 #021A0F}
.ev{border-radius:4px;box-shadow:3px 3px 0 #021A0F}
.sar{border-radius:4px;box-shadow:6px 6px 0 #021A0F}
.panel{box-shadow:4px 4px 0 #021A0F}
.chip.c-crit{color:#FF6FAA}
.side-status{border-top:1px dashed rgba(255,224,27,.35)}
.side-status b{color:#FFF8E4}
.md{font-size:14px;line-height:1.6;color:var(--cream-ink)}
.md p{margin:0 0 8px} .md ul{margin:0 0 8px 18px;padding:0}
.md .ph{font:600 14px var(--sans);margin:6px 0 4px}
.md code.pc{font:500 12px var(--mono);background:#EEE6CF;color:#0B3B22;padding:1px 5px;border-radius:3px;white-space:nowrap}
.md table.pt{border-collapse:collapse;width:100%;margin:4px 0 10px;font-size:13px}
.md table.pt th{font:500 11px var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--cream-mute);text-align:left;padding:6px 8px;border-bottom:1px solid var(--cream-line)}
.md table.pt td{padding:7px 8px;border-bottom:1px solid var(--cream-line);vertical-align:top;line-height:1.9}
.runbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font:12.5px var(--mono);color:var(--ink2);
  border:1px dashed var(--line2);border-radius:8px;padding:8px 12px;margin:4px 0 12px}
.runbar.live{border:1px solid rgba(121,217,160,.45);background:rgba(121,217,160,.06)}
.cmp{border:1px solid var(--line2);border-radius:10px;background:var(--s1);padding:12px 14px;margin:0 0 16px;font-size:13.5px;color:var(--ink2)}
.cmpgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
@media(max-width:1000px){.cmpgrid{grid-template-columns:repeat(3,1fr)}}
.cmpgrid .v{font:500 13px/1.4 var(--mono);margin-top:3px}
.alertcard{background:var(--s1);border:1px solid var(--line2);border-radius:12px;padding:18px 20px;box-shadow:4px 4px 0 #021A0F}
.alertcard .quote{font:400 22px/1.4 var(--serif);color:var(--ink)}
</style>
"""
