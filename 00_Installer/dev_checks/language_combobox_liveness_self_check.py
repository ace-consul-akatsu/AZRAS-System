from pathlib import Path
import ast, sys
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PATCH_634: this check exists because of the Module 4 / Module 6 (Evaluation
# package) bug class: a language-selector tk.StringVar assigned to a local
# variable (never stored as self.xxx) is garbage-collected as soon as
# build() returns UNLESS its own <<ComboboxSelected>> handler references it
# (e.g. "lang.get()"). If the handler instead only calls widget.current(),
# nothing keeps the StringVar alive, tkinter.StringVar.__del__ unsets the
# underlying Tcl variable, and the combobox silently renders blank.
#
# v2 (this revision): pairs each specific Combobox widget with the specific
# StringVar passed as its textvariable=, and only checks THAT widget's own
# <<ComboboxSelected>>.bind() handler. An earlier version of this script
# collected every StringVar defined anywhere in the enclosing function and
# required every bind() handler in that function to reference all of them,
# which produced false positives whenever a build() method contained more
# than one unrelated Combobox/StringVar pair.
#
# A flagged case is one where:
#   1. widget = ttk.Combobox(..., textvariable=varname, ...)
#   2. widget.bind("<<ComboboxSelected>>", handler) exists
#   3. varname is not referenced inside handler
#   4. varname is not kept alive some other way in the same function: as a
#      self.<attr> assignment target, or stored as a value inside a
#      self.<attr>[...] container (dict/list element), which is the pattern
#      already used correctly elsewhere in this codebase
# This is still a heuristic (not full alias/liveness analysis), but it no
# longer conflates unrelated widgets in the same method.

def _names_used(node) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

def _resolve_handler_names_used(func_node, handler) -> set[str]:
    """Names 'used' by a bind() handler expression.

    Handles two shapes seen in this codebase:
      - an inline lambda: names used directly (default args and body).
      - a bare Name referring to a nested `def handler(...):` defined
        earlier in the same enclosing function: resolve to that nested
        FunctionDef and use its whole body + default-argument values
        (e.g. "def on_mat(_e, mv=matvar): ..." keeps matvar alive via the
        function's __defaults__ even though matvar never appears inside
        the handler *call site* itself).
    """
    if isinstance(handler, ast.Name):
        for n in ast.walk(func_node):
            if isinstance(n, ast.FunctionDef) and n.name == handler.id:
                return _names_used(n)
        return {handler.id}
    return _names_used(handler)

def _kept_alive_elsewhere(func_node, varname: str) -> bool:
    for n in ast.walk(func_node):
        if isinstance(n, ast.Assign):
            for target in n.targets:
                is_self_attr = isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"
                is_self_subscript = (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "self"
                )
                if (is_self_attr or is_self_subscript) and varname in _names_used(n.value):
                    return True
    return False

def _combobox_var_pairs(func_node):
    pairs = []
    for n in ast.walk(func_node):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            call = n.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "Combobox":
                for kw in call.keywords:
                    if kw.arg == "textvariable" and isinstance(kw.value, ast.Name):
                        pairs.append((n.targets[0].id, kw.value.id, n))
    return pairs

def _scan_function(func_node, relpath):
    findings = []
    pairs = _combobox_var_pairs(func_node)
    if not pairs:
        return findings

    for widget_name, var_name, _def_node in pairs:
        for n in ast.walk(func_node):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "bind"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == widget_name):
                args = n.args
                if len(args) < 2:
                    continue
                event_arg = args[0]
                if not (isinstance(event_arg, ast.Constant) and event_arg.value == "<<ComboboxSelected>>"):
                    continue
                handler = args[1]
                if var_name in _resolve_handler_names_used(func_node, handler):
                    continue
                if _kept_alive_elsewhere(func_node, var_name):
                    continue
                findings.append(
                    f"{relpath}:{n.lineno}: '{widget_name}' <<ComboboxSelected>> handler does not "
                    f"reference its own textvariable '{var_name}' and it is not kept alive elsewhere "
                    f"— it will be garbage-collected after this method returns, and the combobox "
                    f"will render blank."
                )
    return findings

files = sorted(
    p for p in _ROOT.rglob("*.py")
    if "PATCH" not in p.parts and "dev_checks" not in p.parts
)

findings = []
for f in files:
    try:
        tree = ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
    except SyntaxError:
        continue
    relpath = f.relative_to(_ROOT)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_scan_function(node, relpath))

if findings:
    for line in findings:
        print("[NG]", line)
    raise SystemExit(1)
print("LANGUAGE_COMBOBOX_LIVENESS_PASS")
