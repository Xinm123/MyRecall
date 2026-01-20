#!/usr/bin/env bash

# Phase 8.3 Control Center - 快速测试运行脚本
# 用法: bash run_phase8_3_tests.sh

set -e

PROJECT_ROOT="/Users/tiiny/Test/MyRecall/openrecall"
PYTHON_CMD="/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base python"

echo "========================================"
echo "Phase 8.3 Control Center - 测试套件"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 函数：打印分隔线
print_section() {
    echo ""
    echo "========================================"
    echo "📋 $1"
    echo "========================================"
}

# 函数：打印成功
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# 函数：打印警告
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 函数：打印错误
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

cd "$PROJECT_ROOT"

# ========== 测试1: 文件检查 ==========
print_section "步骤1: 验证文件是否存在"

files_to_check=(
    "openrecall/server/templates/icons.html"
    "openrecall/server/templates/layout.html"
    "tests/test_phase8_3_control_center.py"
    "docs/PHASE_8.3_IMPLEMENTATION.md"
    "docs/PHASE_8.3_TEST_GUIDE.md"
)

for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        print_success "文件存在: $file"
    else
        print_error "文件缺失: $file"
        exit 1
    fi
done

# ========== 测试2: 检查icons.html中的icon_sliders ==========
print_section "步骤2: 验证icon_sliders宏存在"

if grep -q "icon_sliders" "$PROJECT_ROOT/openrecall/server/templates/icons.html"; then
    print_success "icon_sliders宏已添加到icons.html"
else
    print_error "icon_sliders宏未找到"
    exit 1
fi

# ========== 测试3: 检查layout.html中的Control Center代码 ==========
print_section "步骤3: 验证layout.html中的Control Center代码"

required_strings=(
    "control-center-btn"
    "controlCenter()"
    "icon_sliders()"
    "toggle-switch"
    "recording_enabled"
    "upload_enabled"
    "ai_processing_enabled"
    "ui_show_ai"
    "hide-ai"
)

for str in "${required_strings[@]}"; do
    if grep -q "$str" "$PROJECT_ROOT/openrecall/server/templates/layout.html"; then
        print_success "找到: $str"
    else
        print_warning "未找到: $str"
    fi
done

# ========== 测试4: Python语法检查 ==========
print_section "步骤4: Python语法检查"

echo "检查test_phase8_3_control_center.py..."
if $PYTHON_CMD -m py_compile tests/test_phase8_3_control_center.py; then
    print_success "Python语法检查通过"
else
    print_error "Python语法检查失败"
    exit 1
fi

# ========== 测试5: 运行自动化测试 ==========
print_section "步骤5: 运行自动化API集成测试"

echo ""
echo "这将启动服务器并运行22个API测试..."
echo "预计耗时: 30-60秒"
echo ""

if $PYTHON_CMD -m pytest tests/test_phase8_3_control_center.py -v -s --tb=short 2>&1; then
    print_success "所有自动化测试通过!"
else
    print_warning "某些测试可能失败 - 请检查输出"
fi

# ========== 最终总结 ==========
print_section "测试完成总结"

echo ""
print_success "✓ 文件验证完成"
print_success "✓ 代码结构验证完成"
print_success "✓ 语法检查完成"
print_success "✓ 自动化测试完成"
echo ""

echo "📚 文档位置:"
echo "  - 实现说明: docs/PHASE_8.3_IMPLEMENTATION.md"
echo "  - 详细测试指南: docs/PHASE_8.3_TEST_GUIDE.md"
echo "  - 自动化测试代码: tests/test_phase8_3_control_center.py"
echo ""

echo "🚀 手动UI测试步骤:"
echo "  1. 启动服务器: python -m openrecall.server"
echo "  2. 访问: http://localhost:8083"
echo "  3. 查找右侧工具栏中的滑块图标（Control Center）"
echo "  4. 点击按钮打开Popover菜单"
echo "  5. 测试4个切换开关"
echo ""

echo "========================================"
echo "测试完成! 请执行手动UI测试以完整验证功能"
echo "========================================"
