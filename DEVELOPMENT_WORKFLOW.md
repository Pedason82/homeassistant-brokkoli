# 🚀 Improved Development Workflow

This guide provides faster, more efficient ways to develop and validate changes before pushing to GitHub.

## 🎯 **Quick Start - Recommended Workflow**

### **Option 1: VSCode Tasks (Fastest)**
1. **Make your changes** in VSCode
2. **Press `Ctrl+Shift+P`** → Type "Tasks: Run Task"
3. **Select "🔍 Local Validation"** - runs all checks locally in ~10 seconds
4. **If validation passes**, select "🚀 Quick Commit & Push"
5. **Done!** - No waiting for GitHub Actions

### **Option 2: Command Line**
```bash
# Run local validation (10 seconds vs 2+ minutes on GitHub)
./scripts/local-validation.sh

# If all checks pass, commit and push
git add .
git commit -m "your message"
git push
```

## 📋 **Available Tools**

### **1. Local Validation Scripts**
- **Linux/Mac**: `./scripts/local-validation.sh`
- **Windows**: `.\scripts\local-validation.bat`

**What it checks:**
- ✅ Python syntax validation
- ✅ Black code formatting
- ✅ HACS file structure
- ✅ Manifest.json validation
- ⚠️ TODO/FIXME comments
- ⚠️ Print statements (should use logging)

### **2. VSCode Tasks** (Press `Ctrl+Shift+P` → "Tasks: Run Task")
- **🔍 Local Validation** - Full validation suite
- **🎨 Auto-fix Black Formatting** - Fix formatting issues
- **🐍 Python Syntax Check** - Quick syntax validation
- **📦 HACS Validation** - Check HACS requirements
- **🚀 Quick Commit & Push** - Validate + commit + push

### **3. Individual Commands**
```bash
# Format code
python -m black custom_components/

# Check syntax
python -m py_compile custom_components/plant/__init__.py

# Check formatting without fixing
python -m black --check --diff custom_components/
```

## 🔧 **VSCode Extensions (Recommended)**

### **Install These Extensions:**
1. **GitHub Actions** (`cschleiden.vscode-github-actions`)
   - Monitor workflow runs directly in VSCode
   - View logs without leaving editor
   - Get notifications when builds complete

2. **Python** (`ms-python.python`)
   - Real-time syntax checking
   - Integrated linting

3. **Black Formatter** (`ms-python.black-formatter`)
   - Auto-format on save
   - Real-time formatting feedback

### **Extension Setup:**
```json
// Add to .vscode/settings.json
{
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true
}
```

## ⚡ **Speed Comparison**

| Method | Time | Feedback |
|--------|------|----------|
| **Local Validation** | ~10 seconds | Immediate |
| **GitHub Actions** | 2-3 minutes | Delayed |
| **VSCode Tasks** | ~10 seconds | Immediate + UI |

## 🎯 **Best Practices**

### **Before Every Commit:**
1. **Run local validation** - catches 95% of issues
2. **Fix any formatting** - auto-fix with Black
3. **Review changes** - ensure no unintended modifications
4. **Commit with clear message** - describe what changed

### **Development Cycle:**
```
Edit Code → Local Validation → Fix Issues → Commit → Push
    ↑                                              ↓
    └──────────── Continue Development ←───────────┘
```

### **When to Use GitHub Actions:**
- **Final validation** before merging
- **Integration testing** with full environment
- **Release preparation** and tagging
- **Collaborative review** process

## 🛠️ **Advanced Options**

### **Act - Local GitHub Actions**
For running actual GitHub Actions locally:
```bash
# Install act (requires Docker)
# Windows: choco install act-cli
# Mac: brew install act
# Linux: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run GitHub Actions locally
act -j ci  # Run CI workflow
act -j hacs  # Run HACS workflow
```

### **Pre-commit Hooks**
Automatically run validation before every commit:
```bash
# Install pre-commit
pip install pre-commit

# Setup hooks (creates .pre-commit-config.yaml)
pre-commit install
```

## 🎉 **Benefits**

✅ **10x Faster Feedback** - 10 seconds vs 2+ minutes  
✅ **Offline Development** - No internet required for validation  
✅ **Immediate Error Detection** - Catch issues before committing  
✅ **Reduced GitHub Actions Usage** - Save on CI/CD minutes  
✅ **Better Developer Experience** - Integrated with VSCode  
✅ **Consistent Code Quality** - Same checks as CI/CD  

## 🚨 **Troubleshooting**

### **Script Permission Issues (Linux/Mac):**
```bash
chmod +x scripts/local-validation.sh
```

### **Python Module Not Found:**
```bash
pip install black
```

### **VSCode Task Not Working:**
- Ensure you're in the repository root
- Check that scripts exist and are executable
- Verify Python is in your PATH

---

**💡 Pro Tip:** Set up the VSCode tasks and use `Ctrl+Shift+P` → "🔍 Local Validation" for the fastest development experience!
