' ==============================================================================
' 学搭子 Windows 静默执行包装脚本 (run_silent.vbs)
' 作用：在后台静默运行 run_windows.bat，杜绝弹出 CMD 黑框打扰正常使用
' 用法：wscript.exe run_silent.vbs [参数秒数，如 300]
' ==============================================================================

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

CurrentDir = FSO.GetParentFolderName(WScript.ScriptFullName)
BatPath = CurrentDir & "\run_windows.bat"

Args = ""
For Each Arg In WScript.Arguments
    Args = Args & " " & Arg
Next

' 最后一个参数 0 代表完全隐藏窗口运行，False 代表不阻塞等待
WshShell.Run """" & BatPath & """" & Args, 0, False
