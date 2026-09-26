from __future__ import annotations
import json, os, shutil, sys, tkinter as tk, webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_NAME="AZRAS Installer"


def _app_version() -> str:
    """PATCH_003: the version shown on screen comes from VERSION.json (it was a
    hard-coded 5.0.4-p032 while VERSION.json said 5.0.4-p001 / patch 2)."""
    roots=[Path(__file__).resolve().parent]
    if getattr(sys,"_MEIPASS",None):
        roots.append(Path(sys._MEIPASS))
    if getattr(sys,"frozen",False):
        roots.append(Path(sys.executable).resolve().parent)
    for root in roots:
        try:
            v=json.loads((root/"VERSION.json").read_text(encoding="utf-8-sig")).get("version")
            if v:
                return str(v)
        except (OSError,ValueError,AttributeError):
            continue
    return DEFAULT_APP_VERSION


# Fallback only; dev_checks/version_consistency_self_check.py keeps it equal to VERSION.json.
DEFAULT_APP_VERSION="5.0.4"
APP_VERSION=_app_version()
COMPANY="ACE Comprehensive Consulting Co., Ltd."
APPDATA=Path(os.environ.get("APPDATA",Path.home()))/"AZRAS"
CONFIG_PATH=APPDATA/"installer_config.json"
LANGUAGE_ORDER=("en","ja")
LANG_LABELS={"en":"English","ja":"日本語"}

# English canonical internal schema.  These values are stable across UI languages.
CANONICAL_LANGUAGE = "en"
CANONICAL_SCHEMA_VERSION = "1.0"
TOOL_KEYS = {
    "python": "python",
}
STATUS_CODES = {
    True: "found",
    False: "missing",
}

LANG_CODES={v:k for k,v in LANG_LABELS.items()}

TEXT={
"ja":{
"subtitle":f"Version {APP_VERSION}  |  初回セットアップ・必要ソフト確認",
"note":"AZRASで利用する外部ツールを確認します。すべてが常に必須ではありません。\n図面入力は詳細図PDFを基本とします。",
 "language":"言語 / Language","shortcuts":"AZRASアイコンを作成","shortcuts_done":"デスクトップとスタートメニューにAZRASアイコンを作成しました。","shortcuts_error":"AZRASアイコンを作成できませんでした。\n\n{error}","rescan":"再確認","config":"設定情報を開く","guide":"インストール手順書を開く","finish":"完了",
"tool":"ソフト","purpose":"用途","required":"必要となる場合","status":"状態","path":"検出場所","selected":"選択したソフト",
"select_from_list":"一覧から選択してください。","download":"公式ダウンロード","browse":"実行ファイルを指定","checking":"確認中…",
"checking_tools":"必要ソフトを確認しています…","found":"検出済み","missing":"未検出",
"done_count":"確認完了：{found}/{total}件を検出。用途に応じて不足分だけ導入してください。",
"select_tool":"対象ソフトを選択してください。","select_python":"Pythonを選択してください。","python_file":"Python実行ファイルを指定",
"invalid_python":"Pythonの実行ファイルとして認識できません。\n\npython.exe / python3x.exe / py.exe を指定してください。",
"config_note":"AZRAS専用の共通設定フォルダーは使用しません。\nPythonは通常どおりWindowsへインストールしてください。",
"finished":"Pythonの確認が完了しました。","python_purpose":"AZRASのソース版起動・EXEビルド","python_required":"開発版・ソース版",
"python_note":"配布EXEだけを使う場合は不要です。"},
"en":{
"subtitle":f"Version {APP_VERSION}  |  Initial Setup / Required Software Check",
"note":"Checks external tools used by AZRAS. Not every tool is required for every use case.\nDetailed PDF drawings are the standard drawing input.",
 "language":"Language","shortcuts":"Create AZRAS Icons","shortcuts_done":"Created the AZRAS icon on the Desktop and Start menu.","shortcuts_error":"Could not create AZRAS icons.\n\n{error}","rescan":"Check Again","config":"Open Configuration Information","guide":"Open Installation Guide","finish":"Finish",
"tool":"Software","purpose":"Purpose","required":"Required For","status":"Status","path":"Detected Path","selected":"Selected Software",
"select_from_list":"Select an item from the list.","download":"Official Download","browse":"Select Executable","checking":"Checking…",
"checking_tools":"Checking required software…","found":"Detected","missing":"Not Detected",
"done_count":"Check complete: {found}/{total} detected. Install only what is required for your use case.",
"select_tool":"Select the target software.","select_python":"Select Python.","python_file":"Select Python Executable",
"invalid_python":"The selected file is not recognized as a Python executable.\n\nSelect python.exe / python3x.exe / py.exe.",
"config_note":"AZRAS does not use a dedicated shared-settings folder.\nInstall Python normally in Windows.",
"finished":"Python check is complete.","python_purpose":"Run the AZRAS source edition / build the EXE",
"python_required":"Development / source edition","python_note":"Not required when using only the distributed EXE."}
}
URLS={"python":"https://www.python.org/downloads/windows/"}

def canonical_tool_record(result: ToolResult) -> dict:
    """Return language-neutral persisted metadata using English canonical text."""
    en = TEXT["en"]
    purpose = en["python_purpose"] if result.key == "python" else result.purpose
    required_for = en["python_required"] if result.key == "python" else result.required_for
    note = en["python_note"] if result.key == "python" else result.note
    return {
        "key": result.key,
        "label": result.label,
        "purpose": purpose,
        "required_for": required_for,
        "found": bool(result.found),
        "status_code": STATUS_CODES[bool(result.found)],
        "path": result.path,
        "note": note,
        "canonical_language": CANONICAL_LANGUAGE,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
    }



def localize_status(status_code: str, language: str) -> str:
    """Translate a canonical status code only at the presentation boundary."""
    txt = TEXT.get(language, TEXT[CANONICAL_LANGUAGE])
    if status_code == "found":
        return txt["found"]
    if status_code == "missing":
        return txt["missing"]
    return status_code



def canonical_installer_state(results, ui_language: str) -> dict:
    """Build persisted installer state in English canonical form.

    ui_language is only a presentation preference and never changes the
    language of persisted tool metadata.
    """
    iterable = results.values() if isinstance(results, dict) else results
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "canonical_language": CANONICAL_LANGUAGE,
        "ui_language": ui_language,
        "tools": [canonical_tool_record(r) for r in iterable],
    }


@dataclass
class ToolResult:
    key:str
    label:str
    purpose:str
    required_for:str
    found:bool
    path:str=""
    note:str=""

def load_config()->dict:
    if not CONFIG_PATH.exists(): return {}
    try:
        d=json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d,dict) else {}
    except Exception:
        return {}

def save_config(data:dict)->None:
    APPDATA.mkdir(parents=True,exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data if isinstance(data,dict) else {},ensure_ascii=False,indent=2),encoding="utf-8")

def which_path(*names:str)->str:
    for name in names:
        v=shutil.which(name)
        if v:return v
    return ""

def valid_executable_name(path:str|Path,key:str)->bool:
    name=str(path).replace("\\","/").rsplit("/",1)[-1].lower()
    if key=="python":
        return name=="py.exe" or (name.startswith("python") and name.endswith(".exe"))
    return False

def detect_python(config:dict,language:str="en")->ToolResult:
    # Internal tool metadata is canonical English. UI translation is applied
    # only when rendering the selected language.
    canonical=TEXT["en"]
    path=""
    if not getattr(sys,"frozen",False):
        exe=Path(sys.executable)
        if exe.is_file() and "python" in exe.name.lower(): path=str(exe)
    if not path:path=which_path("py.exe","py","python.exe","python")
    configured=config.get("python","")
    if configured and Path(configured).is_file() and valid_executable_name(configured,"python"):
        path=configured
    elif configured:
        config.pop("python",None)
    return ToolResult(
        TOOL_KEYS["python"],
        "Python",
        canonical["python_purpose"],
        canonical["python_required"],
        bool(path),
        path,
        canonical["python_note"],
    )

# PATCH_05: presentation labels for the canonical architecture status.
TEXT["en"].setdefault("canonical_standard", "Internal data standard: English (Canonical)")
TEXT["ja"].setdefault("canonical_standard", "内部データ標準：英語（Canonical）")


class InstallerApp(tk.Tk):
    def __init__(self)->None:
        super().__init__()
        # English is the canonical/default language. Japanese is a presentation translation.
        self.language="en"
        self.language_var=tk.StringVar(value=LANG_LABELS[self.language])
        self.config_data=load_config()
        self.results={}
        self._build_ui()
        self.after(150,self.scan)

    def _build_ui(self)->None:
        for child in list(self.winfo_children()): child.destroy()
        txt=TEXT[self.language]
        self.title(f"{APP_NAME} Version {APP_VERSION} — {COMPANY}")
        self.geometry("1080x690"); self.minsize(900,600)
        header=tk.Frame(self,bg="#0b63b6",height=112); header.pack(fill="x"); header.pack_propagate(False)
        tk.Label(header,text="AZRAS Installer",fg="white",bg="#0b63b6",font=("Yu Gothic UI",28,"bold")).pack(anchor="w",padx=30,pady=(18,0))
        tk.Label(header,text=txt["subtitle"],fg="white",bg="#0b63b6",font=("Yu Gothic UI",12)).pack(anchor="w",padx=32)
        tk.Label(self,justify="left",anchor="w",padx=20,pady=12,text=txt["note"],font=("Yu Gothic UI",11)).pack(fill="x")
        ttk.Label(
            self,
            text=txt["canonical_standard"],
            anchor="w",
            font=("Yu Gothic UI",10,"bold"),
        ).pack(fill="x",padx=20,pady=(0,8))
        toolbar=tk.Frame(self); toolbar.pack(fill="x",padx=20,pady=(0,8))
        ttk.Label(toolbar,text=txt["language"]).pack(side="left")
        cb=ttk.Combobox(toolbar,textvariable=self.language_var,values=[LANG_LABELS[code] for code in LANGUAGE_ORDER],state="readonly",width=12)
        cb.pack(side="left",padx=(6,18)); cb.bind("<<ComboboxSelected>>",self.change_language)
        ttk.Button(toolbar,text=txt["rescan"],command=self.scan).pack(side="left")
        ttk.Button(toolbar,text=txt["config"],command=self.open_config_folder).pack(side="left",padx=8)
        ttk.Button(toolbar,text=txt["guide"],command=self.open_guide).pack(side="left")
        ttk.Button(toolbar,text=txt["shortcuts"],command=self.create_azras_shortcuts).pack(side="left",padx=8)
        ttk.Button(toolbar,text=txt["finish"],command=self.finish).pack(side="right")
        cols=("tool","purpose","required","status","path")
        self.tree=ttk.Treeview(self,columns=cols,show="headings",height=12)
        heads={"tool":txt["tool"],"purpose":txt["purpose"],"required":txt["required"],"status":txt["status"],"path":txt["path"]}
        widths={"tool":170,"purpose":250,"required":160,"status":95,"path":370}
        for k in cols:self.tree.heading(k,text=heads[k]);self.tree.column(k,width=widths[k],anchor="w")
        self.tree.pack(fill="both",expand=True,padx=20,pady=6);self.tree.bind("<<TreeviewSelect>>",self.on_select)
        action=ttk.LabelFrame(self,text=txt["selected"]);action.pack(fill="x",padx=20,pady=(4,12))
        self.detail_var=tk.StringVar(value=txt["select_from_list"])
        ttk.Label(action,textvariable=self.detail_var,wraplength=760).pack(side="left",padx=12,pady=10,fill="x",expand=True)
        ttk.Button(action,text=txt["download"],command=self.open_download).pack(side="right",padx=6,pady=10)
        ttk.Button(action,text=txt["browse"],command=self.browse_tool).pack(side="right",padx=6,pady=10)
        self.footer_var=tk.StringVar(value=txt["checking"])
        ttk.Label(self,textvariable=self.footer_var,anchor="w").pack(fill="x",padx=22,pady=(0,10))

    def change_language(self,_event=None)->None:
        language=LANG_CODES.get(self.language_var.get(),"en")
        if language==self.language:return
        self.language=language; self.language_var.set(LANG_LABELS[language]); self._build_ui(); self.scan()

    def scan(self)->None:
        txt=TEXT[self.language]; self.footer_var.set(txt["checking_tools"]); self.update_idletasks()
        results=[detect_python(self.config_data,self.language)]
        try:save_config(self.config_data)
        except OSError:pass
        self.results={r.key:r for r in results}
        for item in self.tree.get_children():self.tree.delete(item)
        for r in results:
            status=localize_status(STATUS_CODES[bool(r.found)], self.language)
            purpose = txt["python_purpose"] if r.key=="python" else r.purpose
            required_for = txt["python_required"] if r.key=="python" else r.required_for
            self.tree.insert("","end",iid=r.key,values=(r.label,purpose,required_for,status,r.path or "—"),tags=("ok" if r.found else "missing",))
        self.tree.tag_configure("ok",foreground="#1a7f37");self.tree.tag_configure("missing",foreground="#b42318")
        found=sum(1 for r in results if r.found);self.footer_var.set(txt["done_count"].format(found=found,total=len(results)))

    def selected_key(self):
        s=self.tree.selection();return s[0] if s else None
    def on_select(self,_event=None):
        k=self.selected_key()
        if not k:return
        r=self.results[k];sep="：" if self.language=="ja" else ": ";pun="。" if self.language=="ja" else ". "
        txt=TEXT[self.language]
        purpose = txt["python_purpose"] if r.key=="python" else r.purpose
        note = txt["python_note"] if r.key=="python" else r.note
        self.detail_var.set(f"{r.label}{sep}{purpose}{pun}{note}")
    def open_download(self):
        k=self.selected_key()
        if not k:messagebox.showinfo(APP_NAME,TEXT[self.language]["select_tool"]);return
        webbrowser.open(URLS[k])
    def browse_tool(self):
        k=self.selected_key();txt=TEXT[self.language]
        if k!="python":messagebox.showinfo(APP_NAME,txt["select_python"]);return
        path=filedialog.askopenfilename(title=txt["python_file"],filetypes=[("Executable","*.exe"),("All files","*.*")])
        if not path:return
        if not valid_executable_name(path,"python"):messagebox.showerror(APP_NAME,txt["invalid_python"]);return
        self.config_data["python"]=path;self.scan()
    def open_config_folder(self):messagebox.showinfo(APP_NAME,TEXT[self.language]["config_note"])
    def open_guide(self):
        d=Path(__file__).resolve().parent/"docs"
        guide=d/"AZRAS_Installation_Guide_EN.html" if self.language=="en" and (d/"AZRAS_Installation_Guide_EN.html").exists() else d/"AZRAS_Installation_Guide_JA.html"
        webbrowser.open(guide.as_uri())
    def create_azras_shortcuts(self):
        txt=TEXT[self.language]
        try:
            from create_AZRAS_shortcuts import create_shortcuts
            create_shortcuts()
            messagebox.showinfo(APP_NAME,txt["shortcuts_done"])
        except Exception as exc:
            messagebox.showerror(APP_NAME,txt["shortcuts_error"].format(error=exc))

    def finish(self):
        try:save_config(self.config_data)
        except OSError:pass
        messagebox.showinfo(APP_NAME,TEXT[self.language]["finished"]);self.destroy()

if __name__=="__main__":InstallerApp().mainloop()
