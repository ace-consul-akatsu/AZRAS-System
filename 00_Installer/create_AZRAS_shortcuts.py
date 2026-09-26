from __future__ import annotations
import os, subprocess, ctypes
from pathlib import Path

BASE=Path(__file__).resolve().parent
L=BASE/"launchers"
I=BASE/"assets"/"icons"

FOLDERID_Desktop = ctypes.c_byte * 16
desktop_guid = bytes.fromhex("B4BFCC3A-DB2C-424C-B029-7FE99A87C641".replace("-",""))
# GUID byte order adjustment for first 3 fields
def guid_bytes(hexstr):
    import uuid
    u=uuid.UUID(hexstr)
    return u.bytes_le

def get_known_folder_path(guid_str: str) -> Path:
    shell32=ctypes.windll.shell32
    ole32=ctypes.windll.ole32
    ppath=ctypes.c_wchar_p()
    buf=(ctypes.c_ubyte*16).from_buffer_copy(guid_bytes(guid_str))
    hr=shell32.SHGetKnownFolderPath(ctypes.byref(buf),0,None,ctypes.byref(ppath))
    if hr != 0:
        raise OSError(f"SHGetKnownFolderPath failed: {hr}")
    try:
        return Path(ppath.value)
    finally:
        ole32.CoTaskMemFree(ppath)

def q(s): return str(s).replace("'","''")

def create_shortcuts():
    desktop=get_known_folder_path("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
    start=Path(os.environ["APPDATA"])/"Microsoft"/"Windows"/"Start Menu"/"Programs"/"AZRAS"
    desktop.mkdir(parents=True,exist_ok=True)
    start.mkdir(parents=True,exist_ok=True)
    wscript=Path(os.environ.get("WINDIR",r"C:\Windows"))/"System32"/"wscript.exe"

    name="AZRAS"
    script=L/"AZRAS.vbs"
    icon=I/"AZRAS_AZRAS.ico"

    created=[]
    for folder in (desktop,start):
        lnk=folder/f"{name}.lnk"
        ps=f"""$ws=New-Object -ComObject WScript.Shell;
$s=$ws.CreateShortcut('{q(lnk)}');
$s.TargetPath='{q(wscript)}';
$s.Arguments='\"{q(script)}\"';
$s.WorkingDirectory='{q(BASE)}';
$s.IconLocation='{q(icon)},0';
$s.Description='AZRAS v2.2.0';
$s.Save();"""
        subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-Command",ps],
                       check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if not lnk.exists():
            raise OSError(f"Shortcut was not created: {lnk}")
        created.append(lnk)
    return created

if __name__=="__main__":
    create_shortcuts()
