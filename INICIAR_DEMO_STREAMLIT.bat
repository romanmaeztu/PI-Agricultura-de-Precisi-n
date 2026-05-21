@echo off
setlocal

title Demo TFG - Riego predictivo

cd /d "%~dp0"

echo ============================================================
echo  DEMO TFG - SISTEMA PREDICTIVO DE RIEGO
echo ============================================================
echo.
echo Carpeta del proyecto:
echo %CD%
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
    ) else (
        echo ERROR: No se ha encontrado Python en el equipo.
        echo Instala Python o activa "Add python.exe to PATH".
        echo.
        pause
        exit /b 1
    )
)

echo Comprobando Streamlit...
%PYTHON_CMD% -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo Streamlit no esta instalado. Instalando dependencias...
    if exist requirements.txt (
        %PYTHON_CMD% -m pip install -r requirements.txt
    ) else (
        %PYTHON_CMD% -m pip install streamlit
    )
    if errorlevel 1 (
        echo.
        echo ERROR: No se pudieron instalar las dependencias.
        echo Revisa la conexion a Internet o instala Streamlit manualmente:
        echo %PYTHON_CMD% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Arrancando la aplicacion en:
echo http://localhost:8501
echo.
echo Si el navegador no se abre automaticamente, copia esa URL.
echo Para detener la demo, cierra esta ventana o pulsa Ctrl+C.
echo.

start "" "http://localhost:8501"
%PYTHON_CMD% -m streamlit run app.py --server.port 8501 --server.address localhost

echo.
pause
