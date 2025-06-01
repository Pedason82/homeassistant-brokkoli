#!/bin/bash
# Local validation script to run the same checks as GitHub Actions
# This allows you to validate changes before committing/pushing

set -e  # Exit on any error

echo "🔍 Starting local validation..."
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2 passed${NC}"
    else
        echo -e "${RED}❌ $2 failed${NC}"
        exit 1
    fi
}

# Change to repository root
cd "$(dirname "$0")/.."

echo "📁 Working directory: $(pwd)"
echo ""

# 1. Python syntax check
echo "🐍 Checking Python syntax..."
python -m py_compile custom_components/plant/__init__.py
print_status $? "Python syntax check"

python -m py_compile custom_components/plant/config_flow.py
print_status $? "Config flow syntax check"

python -m py_compile custom_components/plant/sensor.py
print_status $? "Sensor syntax check"

# 2. Black formatting check
echo ""
echo "🎨 Checking Black formatting..."
python -m black --check --diff custom_components/
BLACK_EXIT=$?
if [ $BLACK_EXIT -eq 0 ]; then
    print_status 0 "Black formatting"
else
    echo -e "${YELLOW}⚠️  Black formatting issues found. Running auto-fix...${NC}"
    python -m black custom_components/
    print_status $? "Black auto-fix"
fi

# 3. Basic HACS validation (file structure)
echo ""
echo "📦 Checking HACS file structure..."

# Check required files
required_files=(
    "custom_components/plant/__init__.py"
    "custom_components/plant/manifest.json"
    "hacs.json"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ Found: $file${NC}"
    else
        echo -e "${RED}❌ Missing: $file${NC}"
        exit 1
    fi
done

# Check manifest.json structure
echo ""
echo "📋 Validating manifest.json..."
python -c "
import json
import sys
try:
    with open('custom_components/plant/manifest.json', 'r') as f:
        manifest = json.load(f)
    required_keys = ['domain', 'name', 'version', 'documentation', 'issue_tracker', 'codeowners']
    missing = [key for key in required_keys if key not in manifest]
    if missing:
        print(f'Missing keys in manifest.json: {missing}')
        sys.exit(1)
    print('✅ manifest.json structure valid')
except Exception as e:
    print(f'❌ manifest.json validation failed: {e}')
    sys.exit(1)
"
print_status $? "Manifest validation"

# 4. Check for common issues
echo ""
echo "🔍 Checking for common issues..."

# Check for TODO/FIXME comments
echo "Checking for TODO/FIXME comments..."
if grep -r "TODO\|FIXME" custom_components/ --exclude-dir=__pycache__ | head -5; then
    echo -e "${YELLOW}⚠️  Found TODO/FIXME comments (review recommended)${NC}"
else
    echo -e "${GREEN}✅ No TODO/FIXME comments found${NC}"
fi

# Check for print statements (should use logging)
echo "Checking for print statements..."
if grep -r "print(" custom_components/ --exclude-dir=__pycache__ | head -5; then
    echo -e "${YELLOW}⚠️  Found print() statements (consider using _LOGGER)${NC}"
else
    echo -e "${GREEN}✅ No print() statements found${NC}"
fi

echo ""
echo "🎉 Local validation completed successfully!"
echo "================================"
echo "✅ All checks passed - safe to commit and push!"
echo ""
echo "💡 To run this script: ./scripts/local-validation.sh"
echo "💡 To auto-fix formatting: python -m black custom_components/"
