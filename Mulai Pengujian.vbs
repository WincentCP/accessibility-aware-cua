Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"
If Not files.FileExists(pythonw) Then pythonw = "pythonw.exe"
shell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & root & "\scripts\research-launcher.py" & Chr(34), 0, False
