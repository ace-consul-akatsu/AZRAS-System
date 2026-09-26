# -*- coding: utf-8 -*-
"""v2.2.0 baseline: the published Project JSON schema matches the save format.

data/project_schema_v2_0.json fixes schema_version to "2.0", but Project JSON
has been saved as schema 3.0, so every current file failed it.
data/project_schema_v3_0.json describes the current format.  This check keeps
its schema_version equal to core/project_store.SCHEMA_VERSION and validates a
new Project against it (full JSON Schema validation when the jsonschema
package is installed; required keys and schema_version always).

Run: python dev_checks/project_schema_consistency_self_check.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FAIL = []


def check(ok, label, detail=""):
    if ok:
        print(f"  [OK]   {label}")
    else:
        FAIL.append(f"{label} :: {detail}")
        print(f"  [NG]   {label} :: {detail}")


print("project_schema_consistency self-check")
from core import project_store as PS  # noqa: E402

path = ROOT / "data" / "project_schema_v3_0.json"
check(path.exists(), "data/project_schema_v3_0.json exists")
schema = json.loads(path.read_text(encoding="utf-8-sig"))
const = (schema.get("properties", {}).get("schema_version") or {}).get("const")
check(const == PS.SCHEMA_VERSION, "schema_version in the schema equals SCHEMA_VERSION of the save format",
      f"{const} vs {PS.SCHEMA_VERSION}")
project = PS.new_project()
check(project.get("schema_version") == PS.SCHEMA_VERSION, "a new Project is saved as that schema version")
missing = [k for k in schema.get("required", []) if k not in project]
check(not missing, "a new Project has every required key", str(missing))
try:
    import jsonschema
except ImportError:
    jsonschema = None
    print("  [--]   jsonschema not installed: full JSON Schema validation not run (the checks above still apply)")
if jsonschema is not None:
    errors = [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(project)]
    check(not errors, "a new Project validates against the schema (full JSON Schema)", str(errors[:3]))

print()
if FAIL:
    print("[NG] project_schema_consistency self-check FAILED:")
    for f in FAIL:
        print("   -", f)
    raise SystemExit(1)
print("PROJECT_SCHEMA_CONSISTENCY_PASS")
