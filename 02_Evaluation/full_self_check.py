from __future__ import annotations

import ast
import copy
import importlib
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CHECK_MODULES = [
    "main",
    "module3.app",
    "module4.app",
    "module6.app",
    "module7.app",
    "core.project_store",
    "core.project_context",
    "core.project_coordinator",
    "core.version",
]

REQUIRED_FILES = [
    "VERSION.json",
    "lang/ja.json",
    "lang/en.json",
    "data/component_life_database_v9_2.json",
    "data/construction_scenario_profiles_v9_2.json",
    "data/environmental_lca_factors_v9_3.json",
    "data/construction_cost_database_v9_4.json",
    "data/investment_assumptions_v9_5.json",
    "data/repair_demolition_cost_assumptions_v9_6.json",
]

GUI_IMPORTS = {
    # Evaluation exposes only the two formal 200-year screens.
    # Modules 3/5/7 remain internal calculation support and must not be
    # required as standalone buttons by the UI wiring self-check.
    "module4.app": "Module4App",
    "module6.app": "Module6App",
}

MODULE_CONSTRUCTORS = {
    # Only formal standalone Evaluation screens are checked against the
    # launcher constructor contract. Internal support modules are covered
    # by import/resource checks and the evaluation pipeline.
    4: ("module4/app.py", "Module4App"),
    6: ("module6/app.py", "Module6App"),
}

MODULE_RESOURCES = {
    "Module 3": [
        "data/component_life_database_v9_2.json",
        "data/construction_scenario_profiles_v9_2.json",
    ],
    "Module 4": [
        "data/environmental_lca_factors_v9_3.json",
    ],
    "Module 5": [
        "data/construction_cost_database_v9_4.json",
    ],
    "Module 6": [
        "data/region_master_v1.json",
        "data/investment_assumptions_v9_5.json",
    ],
    "Module 7": [
        "data/repair_demolition_cost_assumptions_v9_6.json",
    ],
}


def section(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def check_startup(errors: list[str]) -> None:
    section("1/5 Startup / Version / Resource")

    for name in CHECK_MODULES:
        try:
            importlib.import_module(name)
            print(f"[OK] import {name}")
        except Exception as exc:
            errors.append(f"import {name}: {exc}")
            print(f"[NG] import {name}: {exc}")

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if path.is_file():
            print(f"[OK] file {rel}")
        else:
            errors.append(f"missing file: {rel}")
            print(f"[NG] missing file: {rel}")

    try:
        meta = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
        json_version = str(meta.get("version", ""))
        json_schema = str(meta.get("schema_version", ""))

        import core.version as core_version_module
        import core.project_store as project_store_module

        core_version_module = importlib.reload(core_version_module)

        if core_version_module.VERSION == json_version:
            print(f"[OK] version {json_version}")
        else:
            errors.append(
                f"version mismatch: VERSION.json={json_version}, "
                f"core.version={core_version_module.VERSION}"
            )
            print("[NG] version mismatch")

        if core_version_module.SCHEMA_VERSION == json_schema:
            print(f"[OK] core schema {json_schema}")
        else:
            errors.append("core schema mismatch")
            print("[NG] core schema mismatch")

        if project_store_module.SCHEMA_VERSION == json_schema:
            print(f"[OK] project schema {json_schema}")
        else:
            errors.append("project schema mismatch")
            print("[NG] project schema mismatch")

    except Exception as exc:
        errors.append(f"version/schema check: {exc}")
        print(f"[NG] version/schema check: {exc}")


def check_project_json(errors: list[str]) -> None:
    section("2/5 Project JSON Round-trip")

    try:
        from core.project_store import load_project, new_project, save_project

        project = new_project()
        original = copy.deepcopy(project)

        with tempfile.TemporaryDirectory(prefix="azras_eval_check_") as tmp:
            path = Path(tmp) / "project_check.json"
            save_project(
                project,
                path,
                saved_by="full_self_check",
                create_backup=False,
            )
            print("[OK] temporary Project JSON saved")

            loaded = load_project(path)
            print("[OK] temporary Project JSON loaded")

            outputs = loaded.get("module_outputs")
            required_keys = [f"module{i}" for i in range(1, 8)]
            missing = (
                [key for key in required_keys if key not in outputs]
                if isinstance(outputs, dict)
                else required_keys
            )
            if missing:
                errors.append("missing current Evaluation module_outputs keys: " + ", ".join(missing))
                print("[NG] current Evaluation module_outputs key check")
            else:
                print("[OK] current Evaluation module_outputs contains module1 through module7")
            # Legacy module8/module9 keys may be preserved by the shared Project
            # schema, but they are not active Evaluation requirements.

            schema = str(loaded.get("schema_version", ""))
            if schema == "3.0":
                print("[OK] Project JSON schema 3.0")
            else:
                errors.append(f"unexpected project schema: {schema}")
                print(f"[NG] unexpected project schema: {schema}")

            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                print("[OK] saved JSON is valid JSON object")
            else:
                errors.append("saved JSON root is not an object")
                print("[NG] saved JSON root is not an object")

        if project == original:
            print("[OK] test used temporary storage only")

    except Exception as exc:
        errors.append(f"Project JSON round-trip: {exc}")
        print(f"[NG] Project JSON round-trip: {exc}")


def check_gui_wiring(errors: list[str]) -> None:
    section("3/5 Main UI Wiring")

    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.setdefault(node.module, set()).update(
                alias.name for alias in node.names
            )

    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    for module_name, class_name in GUI_IMPORTS.items():
        if class_name in imported.get(module_name, set()) and class_name in names:
            print(f"[OK] {module_name} -> {class_name}")
        else:
            errors.append(f"GUI wiring missing: {module_name}.{class_name}")
            print(f"[NG] GUI wiring missing: {module_name}.{class_name}")

    required_fragments = [
        "Project JSONを開く",
        "self.project_context.path is None",
        "self.open_module(cls, p)",
        "ensure_internal_200_year_support(",
        "load_project(path)",
    ]
    for fragment in required_fragments:
        if fragment in source:
            print(f"[OK] main.py contains: {fragment}")
        else:
            errors.append(f"main.py missing: {fragment}")
            print(f"[NG] main.py missing: {fragment}")


def _class_init_args(path: Path, class_name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "__init__":
                    return [arg.arg for arg in child.args.args]
    raise RuntimeError(f"{class_name}.__init__ not found")


def check_constructors(errors: list[str]) -> None:
    section("4/5 Module Constructor Interface")

    for module_no, (rel, class_name) in MODULE_CONSTRUCTORS.items():
        try:
            args = _class_init_args(ROOT / rel, class_name)
            valid = (
                len(args) >= 5
                and args[0] == "self"
                and args[1] in {"master", "parent"}
                and args[2:5] == ["root_dir", "language", "project_context"]
            )
            if valid:
                print(
                    f"[OK] Module {module_no}: {class_name}"
                    f"({args[1]}, root_dir, language, project_context)"
                )
            else:
                errors.append(f"{class_name} constructor mismatch: {args[:5]}")
                print(f"[NG] Module {module_no}: constructor mismatch")
        except Exception as exc:
            errors.append(f"{class_name}: {exc}")
            print(f"[NG] Module {module_no}: {exc}")

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    expected_call = "app_class(self, ROOT, self.i18n.language, self.project_context)"
    if expected_call in main_source:
        print("[OK] main.py constructor call order")
    else:
        errors.append("main.py constructor call mismatch")
        print("[NG] main.py constructor call mismatch")


def check_module_resources(errors: list[str]) -> None:
    section("5/5 Module Startup Resources")

    for module_name, files in MODULE_RESOURCES.items():
        for rel in files:
            if (ROOT / rel).is_file():
                print(f"[OK] {module_name}: {rel}")
            else:
                errors.append(f"{module_name}: missing {rel}")
                print(f"[NG] {module_name}: missing {rel}")


def main() -> int:
    errors: list[str] = []

    print("AZRAS Evaluation FULL SELF CHECK")

    check_startup(errors)
    check_project_json(errors)
    check_gui_wiring(errors)
    check_constructors(errors)
    check_module_resources(errors)

    print()
    print("=" * 64)
    if errors:
        print(f"AZRAS EVALUATION FULL SELF CHECK FAILED: {len(errors)} error(s)")
        for item in errors:
            print(f"- {item}")
        return 1

    print("AZRAS EVALUATION FULL SELF CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
