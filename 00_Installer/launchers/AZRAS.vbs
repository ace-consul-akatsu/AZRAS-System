Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = Chr(34) & base & "\..\run_AZRAS_Launcher_without_build.bat" & Chr(34)
sh.Run cmd, 0, False
