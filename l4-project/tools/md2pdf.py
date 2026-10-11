import sys, subprocess, pathlib, markdown
src = pathlib.Path(sys.argv[1]).resolve(); out = src.with_suffix(".pdf")
body = markdown.markdown(src.read_text(), extensions=["tables", "fenced_code", "sane_lists"])
css = """body{font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:10.5pt;line-height:1.45;color:#1a1a1a;margin:0}
h1{font-size:19pt;border-bottom:2px solid #333;padding-bottom:4px}h2{font-size:14pt;margin-top:22px;border-bottom:1px solid #ccc}
h3{font-size:12pt}table{border-collapse:collapse;width:100%;margin:8px 0;font-size:9.5pt}
th,td{border:1px solid #bbb;padding:4px 6px;text-align:left;vertical-align:top}th{background:#f0f0f0}
code{font-family:Menlo,monospace;font-size:8.8pt;background:#f4f4f4;padding:1px 3px}pre{background:#f4f4f4;padding:8px;white-space:pre-wrap}
pre code{background:none;padding:0}img{max-width:100%;border:1px solid #bbb;margin:6px 0}@page{size:A4;margin:16mm}"""
html = src.with_suffix(".tmp.html")
html.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>")
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu",
                "--no-pdf-header-footer", f"--print-to-pdf={out}", html.as_uri()], check=True, capture_output=True)
html.unlink(); print("wrote", out)
