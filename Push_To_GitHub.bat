@echo off
title Push AGDL T^&A Tracker to GitHub
color 0b
echo ========================================================
echo       PUSH AGDL T^&A TRACKER TO GITHUB (Mishu2755)
echo ========================================================
echo.
echo [1/3] Checking Git Status...
git status -s
echo.
echo [2/3] Adding files and updating commit...
git add .
git commit -m "Update AGDL T&A Tracker" 2>nul
echo.
echo [3/3] Pushing to https://github.com/Mishu2755/agdl-tna-tracker ...
git push -u origin main
echo.
if %errorlevel% neq 0 (
    echo [ERROR] Push failed. 
    echo Please make sure you created the empty repository named "agdl-tna-tracker" on github.com first!
) else (
    echo [SUCCESS] Code successfully pushed to GitHub!
    echo Now open Render.com to complete the free 24/7 deployment.
)
echo.
pause
