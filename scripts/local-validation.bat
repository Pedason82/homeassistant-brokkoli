@echo off
REM Local validation script to run the same checks as GitHub Actions
REM This allows you to validate changes before committing/pushing

echo 🔍 Starting local validation...
echo ================================

REM Change to repository root
cd /d "%~dp0\.."

echo 📁 Working directory: %CD%
echo.

REM 1. Python syntax check
echo 🐍 Checking Python syntax...
python -m py_compile custom_components\plant\__init__.py
if %errorlevel% neq 0 (
    echo ❌ Python syntax check failed
    exit /b 1
)
echo ✅ Python syntax check passed

python -m py_compile custom_components\plant\config_flow.py
if %errorlevel% neq 0 (
    echo ❌ Config flow syntax check failed
    exit /b 1
)
echo ✅ Config flow syntax check passed

python -m py_compile custom_components\plant\sensor.py
if %errorlevel% neq 0 (
    echo ❌ Sensor syntax check failed
    exit /b 1
)
echo ✅ Sensor syntax check passed

REM 2. Black formatting check
echo.
echo 🎨 Checking Black formatting...
python -m black --check --diff custom_components\
if %errorlevel% neq 0 (
    echo ⚠️  Black formatting issues found. Running auto-fix...
    python -m black custom_components\
    if %errorlevel% neq 0 (
        echo ❌ Black auto-fix failed
        exit /b 1
    )
    echo ✅ Black auto-fix completed
) else (
    echo ✅ Black formatting passed
)

REM 3. Basic HACS validation (file structure)
echo.
echo 📦 Checking HACS file structure...

if not exist "custom_components\plant\__init__.py" (
    echo ❌ Missing: custom_components\plant\__init__.py
    exit /b 1
)
echo ✅ Found: custom_components\plant\__init__.py

if not exist "custom_components\plant\manifest.json" (
    echo ❌ Missing: custom_components\plant\manifest.json
    exit /b 1
)
echo ✅ Found: custom_components\plant\manifest.json

if not exist "hacs.json" (
    echo ❌ Missing: hacs.json
    exit /b 1
)
echo ✅ Found: hacs.json

REM 4. Check manifest.json structure
echo.
echo 📋 Validating manifest.json...
python -c "import json; import sys; manifest = json.load(open('custom_components/plant/manifest.json')); required = ['domain', 'name', 'version', 'documentation', 'issue_tracker', 'codeowners']; missing = [k for k in required if k not in manifest]; sys.exit(1) if missing else print('✅ manifest.json structure valid')"
if %errorlevel% neq 0 (
    echo ❌ Manifest validation failed
    exit /b 1
)

echo.
echo 🎉 Local validation completed successfully!
echo ================================
echo ✅ All checks passed - safe to commit and push!
echo.
echo 💡 To run this script: scripts\local-validation.bat
echo 💡 To auto-fix formatting: python -m black custom_components\
pause
