"""Build the standalone dashboard page from the template and the analysis outputs.
Run from this folder: python 04_build_dashboard.py  ->  outputs/dashboard.html"""
HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<style>html{color-scheme:light}</style></head><body>')
t = open("dashboard_template.html", encoding="utf-8").read()
agg = open("outputs/dashboard_agg.json", encoding="utf-8").read()
res = open("outputs/results.json", encoding="utf-8").read()
open("outputs/dashboard.html", "w", encoding="utf-8").write(HEAD + t.replace("__DATA__", agg).replace("__RES__", res) + "</body></html>")
print("wrote outputs/dashboard.html")
