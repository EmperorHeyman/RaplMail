; RaplMail NSIS installer hooks.
;
; The app hides to the tray on close and runs a Python "sidecar"
; (raplmail-backend.exe, which itself spawns a same-named child process). If any
; of these are alive during an upgrade, the installer can't overwrite the locked
; .exe and you end up with a half-updated install ("error opening
; raplmail-backend.exe"). Kill them all before copying files.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /T /IM raplmail-backend.exe'
  nsExec::Exec 'taskkill /F /T /IM raplmail-backend-x86_64-pc-windows-msvc.exe'
  nsExec::Exec 'taskkill /F /T /IM raplmail.exe'
  Sleep 1000
!macroend
