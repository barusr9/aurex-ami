"""Print a Slides-artifact deck (project/deck.json + project/slides/*.html) to a PDF with
headless Chrome, one 1920x1080 page per slide, in deck order.
Usage: python deck2pdf.py <deck_root> <out.pdf> [blob_id=local.png ...]
Speaker notes (<aside>) are dropped; <x-icon> elements are replaced by a plain dot."""
import json, pathlib, re, subprocess, sys

root = pathlib.Path(sys.argv[1]).resolve(); out = pathlib.Path(sys.argv[2]).resolve()
blobs = dict(a.split("=", 1) for a in sys.argv[3:])
deck = json.loads((root / "project/deck.json").read_text())
fonts = "".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck.get("faces", {}).values() if "href" in f)
pages = []
for sid in deck["order"]:
    html = (root / f"project/slides/{sid}.html").read_text()
    html = re.sub(r"<aside>.*?</aside>", "", html, flags=re.S)
    html = re.sub(r"<x-icon[^>]*></x-icon>", '<div style="width:56px;height:56px;border-radius:50%;background:#A8560A"></div>', html)
    for bid, path in blobs.items():
        html = html.replace(f"/_blob/{bid}", pathlib.Path(path).resolve().as_uri())
    pages.append(html)
css = """@page{size:1920px 1080px;margin:0}html,body{margin:0;padding:0}
section{width:1920px;height:1080px;box-sizing:border-box;position:relative;overflow:hidden;page-break-after:always;break-after:page}
section:last-of-type{page-break-after:auto}h1,h2,h3,p,ul,ol{margin:0}h1{font-size:96px;font-weight:600;line-height:1.1}h2{font-size:64px;font-weight:600;line-height:1.15}
h3{font-size:44px;font-weight:600;line-height:1.2}p{font-size:32px;line-height:1.4}table{border-collapse:collapse;width:100%}
th,td{padding:0.35em 0.6em;border-bottom:1px solid #C9C4B8;vertical-align:top}th{font-weight:600}a{color:inherit}img{display:block}"""
page = root / "deck.print.html"
page.write_text(f"<!doctype html><html><head><meta charset='utf-8'>{fonts}<style>{css}</style></head><body>{''.join(pages)}</body></html>")
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                "--virtual-time-budget=8000", f"--print-to-pdf={out}", page.as_uri()], check=True, capture_output=True)
print("wrote", out, f"({len(pages)} slides)")
