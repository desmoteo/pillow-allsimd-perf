"""merge_rerun.py FULL RERUN: replaces FULL's results for every case RERUN
measured (all variants), takes RERUN's case list and commit: for a partial
rerun at a commit whose code differs from FULL's only in those cases'
kernels, or of cases added to the benchmark."""

import json
import sys

full_path, rerun_path = sys.argv[1:3]
full = json.load(open(full_path))
rerun = json.load(open(rerun_path))
cases = set()
for name, v in rerun["variants"].items():
    dst = full["variants"][name]
    for case, r in v["results"].items():
        dst["results"][case] = r
        cases.add(case)
    for key in ("notes", "errors"):
        for case, r in v.get(key, {}).items():
            dst.setdefault(key, {})[case] = r
# The rerun's case list is the full, current one: new cases get their titles.
full["cases"] = rerun["cases"]
full["suites"] = rerun["suites"]
old = full["machine"]["commit"]
full["machine"]["commit"] = rerun["machine"]["commit"]
full["date"] = rerun["date"]
json.dump(full, open(full_path, "w"), indent=1)
print(f"{len(cases)} cases from {rerun['machine']['commit']} (rest measured at {old})")
