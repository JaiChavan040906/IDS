# Public link (Cloudflare quick tunnel)

Shares the portal running on this laptop through a free public `https://….trycloudflare.com`
link that opens on any phone or computer. No account is needed. The link works only while
the window stays open, and a new link is made every time.

## Start

Double-click `start_portal_public.bat`, or in PowerShell (project folder):

```
.\start_portal_public.bat
```

1. Type a password for **admin** and one for **analyst** (the demo passwords are not allowed).
2. Wait about a minute. The window shows **PUBLIC LINK: https://….trycloudflare.com**, copies it to
   the clipboard and opens it in the browser.
3. Share the link. Sign in with the passwords you typed.
4. Press any key in that window to stop. The link stops working immediately.

## Notes

- This mode uses its own fresh database (`data\ids_public.db`), so your normal data and the demo
  logins on this laptop are not touched. Alerts and decisions made through the public link are
  cleared the next time it starts.
- The Warehouse tab starts hidden; the admin can switch it on in Administration → Overview.
- Any portal already running on the laptop is stopped first (only one can use port 8001).
- Needs `tools\cloudflared.exe` (Cloudflare's official tool, from github.com/cloudflare/cloudflared
  releases, file `cloudflared-windows-amd64.exe`). It is not in git; download it again on a new laptop.
- Keep the laptop awake and online while the link is in use.
