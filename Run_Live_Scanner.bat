@echo off
title Live Quick Commerce Scraper & Team Sync
echo ==========================================================
echo Starting Live Storefront Scanner & Cloud Auto-Sync
echo ==========================================================

:: Ensure Chrome debug port is open
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I /N "chrome.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo Opening Chrome Debug Session on port 9222...
    start "" "chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebugSession"
    timeout /t 3 >nul
)

:scan_cycle
echo.
echo [%time%] Scraping live shelf data from Blinkit, Zepto, and Instamart...
python -c "import test_blinkit, asyncio, json, datetime; from app import load_history, save_history; h=load_history(); now=datetime.datetime.now().strftime('%%I:%%M %%p, %%d %%b'); [(h.update({f'{s}_{kw}_{pin}': {'timestamp': now, 'items': asyncio.run(getattr(test_blinkit, f'scan_{s}')(kw, '13.0470976', '77.5476596'))}})) for s in ['blinkit', 'zepto', 'instamart'] for kw in ['kaju katli', 'mysore pak', 'besan laddu'] for pin in ['560021', '560103']]; save_history(h); print('History updated successfully.')"

echo [%time%] Pushing live shelf data to GitHub...
git add shelf_history.json
git commit -m "Live storefront shelf update [%date% %time%]"
git push origin main

echo.
echo Scan complete! The Streamlit Cloud app has been updated with real-time data.
echo Next automated cycle in 10 minutes (Keep this window open, or press Ctrl+C to stop)...
timeout /t 600
goto scan_cycle
