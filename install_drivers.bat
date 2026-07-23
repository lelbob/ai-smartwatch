@echo off
:: Check for administrative privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Administrator privileges confirmed. Installing drivers...
    pnputil /add-driver "%~dp0drivers\SPD_Driver_R4.20.4201\Win10\Drivers\*.inf" /subdirs /install
    echo.
    echo Installation finished! You can now close this window.
    pause
) else (
    echo ========================================================
    echo ERROR: This script must be run as Administrator!
    echo ========================================================
    echo Please right-click this file (install_drivers.bat) 
    echo and select "Run as Administrator".
    echo.
    pause
)
