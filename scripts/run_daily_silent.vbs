Set oShell = CreateObject("WScript.Shell")
' 路径按需修改为你的项目根目录
projectRoot = "D:\数据备份\量化交易\《期末综合实验报告》"
bat = projectRoot & "\scripts\run_daily.bat"
' 0=隐藏窗口, True=不等待
oShell.Run "cmd /c """ & bat & """", 0, False

