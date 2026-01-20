# Phase 8.3 Control Center - 完整测试执行指南

## 快速开始

### 第一步：安装测试依赖

```bash
cd /Users/tiiny/Test/MyRecall/openrecall

# 安装pytest
/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  pip install pytest pytest-asyncio -q
```

### 第二步：运行自动化API测试

```bash
# 运行所有22个API测试（包括启动/停止服务器）
/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  python -m pytest tests/test_phase8_3_control_center.py -v -s --tb=short

# 预计耗时: 45-60秒
# 预期: 全部通过 (22/22 tests passed)
```

### 第三步：手动UI测试

#### 3.1 启动服务器

```bash
cd /Users/tiiny/Test/MyRecall/openrecall

/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  python -m openrecall.server
```

**预期输出:**
```
Running on http://127.0.0.1:8083
```

#### 3.2 打开浏览器

访问 `http://localhost:8083`

#### 3.3 手动测试检查清单

```
UI渲染检查:
☐ 页面加载成功
☐ 顶部工具栏可见
☐ 右侧有Control Center按钮（滑块图标）
☐ 按钮在搜索按钮右边

交互测试:
☐ 点击Control Center按钮 → Popover出现
☐ Popover有3个部分：Privacy, Intelligence, View
☐ Privacy有2个toggle: Recording, Upload
☐ Intelligence有1个toggle: AI Processing  
☐ View有1个toggle: Show AI

功能测试:
☐ 点击Recording toggle → 变灰色 → API请求成功
☐ 点击Upload toggle → 状态改变 → API请求成功
☐ 点击AI Processing toggle → 状态改变 → API请求成功
☐ 点击Show AI toggle → 页面AI文字消失 → API请求成功

恢复测试:
☐ 所有toggle都能切换回去
☐ 再次点击 → 状态改变回来
☐ 刷新页面 → 状态从API恢复

关闭测试:
☐ 在Popover外点击 → 关闭
☐ 再次点击按钮 → 打开
☐ 在其他页面也能使用 (/timeline, /search)
```

---

## 详细测试执行步骤

### 方案A: 完整自动化测试（推荐）

#### 步骤1: 准备环境

```bash
cd /Users/tiiny/Test/MyRecall/openrecall

# 检查Python环境
/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  python --version
# 预期: Python 3.12.x
```

#### 步骤2: 安装依赖

```bash
/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  pip install pytest pytest-asyncio requests -q

echo "✓ 依赖安装完成"
```

#### 步骤3: 运行测试

```bash
/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  python -m pytest tests/test_phase8_3_control_center.py -v -s --tb=short
```

**预期输出示例:**
```
tests/test_phase8_3_control_center.py::TestControlCenterAPI::test_01_api_endpoint_exists PASSED
tests/test_phase8_3_control_center.py::TestControlCenterAPI::test_02_api_returns_valid_json PASSED
tests/test_phase8_3_control_center.py::TestControlCenterAPI::test_03_api_initial_state PASSED
...
tests/test_phase8_3_control_center.py::TestControlCenterAPI::test_22_json_content_type_required PASSED

============= 22 passed in 45.23s =============
```

#### 步骤4: 检查测试覆盖

| 测试编号 | 测试名称 | 预期结果 |
|---------|--------|--------|
| 01 | API端点存在 | ✓ PASSED |
| 02 | 返回有效JSON | ✓ PASSED |
| 03 | 初始状态 | ✓ PASSED |
| 04-11 | POST请求 (8个) | ✓ ALL PASSED |
| 12-13 | 多键更新 | ✓ ALL PASSED |
| 14-16 | 边界测试 | ✓ ALL PASSED |
| 17-18 | 状态一致性 | ✓ ALL PASSED |
| 19-20 | 性能测试 | ✓ ALL PASSED |
| 21 | 并发测试 | ✓ PASSED |
| 22 | Content-Type | ✓ PASSED |

---

### 方案B: 使用curl进行手动API测试

#### 步骤1: 启动服务器（新终端）

```bash
cd /Users/tiiny/Test/MyRecall/openrecall

/opt/homebrew/Caskroom/miniconda/base/bin/conda run -p /opt/homebrew/Caskroom/miniconda/base \
  python -m openrecall.server
```

#### 步骤2: 在另一个终端测试API

```bash
# 测试1: 获取当前配置
echo "测试1: GET /api/config"
curl -s http://localhost:8083/api/config | jq .
# 预期: JSON对象包含所有4个设置

# 测试2: 禁用Recording
echo -e "\n测试2: POST禁用Recording"
curl -s -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"recording_enabled": false}' | jq .
# 预期: recording_enabled = false

# 测试3: 禁用Upload
echo -e "\n测试3: POST禁用Upload"
curl -s -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"upload_enabled": false}' | jq .
# 预期: upload_enabled = false

# 测试4: 禁用AI Processing
echo -e "\n测试4: POST禁用AI Processing"
curl -s -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"ai_processing_enabled": false}' | jq .
# 预期: ai_processing_enabled = false

# 测试5: 禁用Show AI
echo -e "\n测试5: POST禁用Show AI"
curl -s -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"ui_show_ai": false}' | jq .
# 预期: ui_show_ai = false

# 测试6: 重置所有为true
echo -e "\n测试6: 重置所有设置"
curl -s -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "recording_enabled": true,
    "upload_enabled": true,
    "ai_processing_enabled": true,
    "ui_show_ai": true
  }' | jq .
# 预期: 所有值都是true

# 测试7: 并发请求（5个并行POST）
echo -e "\n测试7: 并发请求"
for i in {1..5}; do
  curl -s -X POST http://localhost:8083/api/config \
    -H "Content-Type: application/json" \
    -d "{\"recording_enabled\": $(($i % 2))}" > /dev/null &
done
wait
echo "✓ 5个并发请求完成"
```

#### 步骤3: 验证响应

预期输出格式（每次调用都返回完整配置）:
```json
{
  "recording_enabled": true|false,
  "upload_enabled": true|false,
  "ai_processing_enabled": true|false,
  "ui_show_ai": true|false
}
```

---

### 方案C: 使用浏览器DevTools手动测试

#### 步骤1: 打开DevTools

```
Chrome/Edge: F12
Firefox: F12
Safari: Cmd+Option+I
```

#### 步骤2: 打开Network标签

- 点击"Network"标签
- 确保"记录"已启用（红点）
- 清除之前的请求

#### 步骤3: 启用过滤（可选）

- 在过滤框输入: "api/config"
- 只显示API请求

#### 步骤4: 测试每个toggle

**Recording Toggle测试:**
```
操作: 点击"Recording"开关关闭

Network标签应显示:
  请求: POST /api/config
  请求体: {"recording_enabled": false}
  响应状态: 200
  响应体: {..., "recording_enabled": false, ...}

观察:
  ✓ Toggle变灰色
  ✓ 平滑动画（~250ms）
  ✓ API调用完成
```

**Upload Toggle测试:**
```
操作: 点击"Upload"开关关闭

验证:
  ✓ Network中看到POST请求
  ✓ 请求体: {"upload_enabled": false}
  ✓ Toggle状态改变
```

**AI Processing Toggle测试:**
```
操作: 点击"AI Processing"开关关闭

验证:
  ✓ 发送POST请求
  ✓ 观察服务器日志（应显示AI processing disabled）
```

**Show AI Toggle测试（关键）:**
```
操作: 点击"Show AI"开关关闭

验证步骤:
  1. Elements标签中检查<body>
     预期: <body class="hide-ai">

  2. 页面中的AI文字（如果有ai-insight-text）
     预期: display: none (在Computed Styles中)

  3. 再次打开Show AI
     预期: hide-ai类移除，AI文字显示
```

#### 步骤5: 检查Console

- 打开"Console"标签
- 查看是否有错误信息
- 预期：无错误（除了可能的网络警告）

#### 步骤6: 性能检查

- 打开"Performance"标签
- 点击"Record"
- 快速点击几个toggle
- 停止录制
- 检查帧率（应该>30 FPS）

---

## 测试报告模板

### 测试执行报告

**日期:** _____________
**执行人:** _____________
**环境:** 
- 操作系统: _____________
- 浏览器: _____________
- Python版本: _____________

### 自动化测试结果

```
测试总数: 22
通过: ___  失败: ___  跳过: ___
通过率: ___%
耗时: ___秒

失败的测试（如有）:
□ 无失败
□ test_xxx - 原因: ___________
```

### 手动UI测试结果

```
基础功能:
☐ Control Center按钮显示
☐ Popover打开/关闭
☐ Popover结构正确

交互功能:
☐ Recording toggle工作
☐ Upload toggle工作
☐ AI Processing toggle工作
☐ Show AI toggle工作

API集成:
☐ Network中看到POST请求
☐ 请求体格式正确
☐ 响应状态200
☐ 响应数据有效

性能:
☐ API响应 <100ms
☐ UI响应即时
☐ 动画流畅

错误处理:
☐ 离线状态自动恢复
☐ 无JavaScript错误
☐ 数据一致性

浏览器兼容性:
☐ Chrome
☐ Firefox
☐ Safari
```

### 发现的问题

| ID | 问题 | 严重性 | 状态 |
|----|----|-----|----|
| | | | |

### 签字

测试者: ________________  日期: ________________

---

## 常见问题排查

### Q1: "Control Center按钮不显示"

**原因可能:**
1. icons.html中没有icon_sliders宏
2. layout.html中没有正确引用
3. 浏览器缓存

**解决:**
```bash
# 清除Python缓存
find . -type d -name __pycache__ -delete
find . -type f -name "*.pyc" -delete

# 重启服务器，硬刷浏览器 (Cmd+Shift+R)
```

### Q2: "Popover不出现"

**原因可能:**
1. Alpine.js未加载
2. JavaScript错误

**调试:**
```javascript
// 在浏览器Console中输入:
console.log(Alpine)  // 应该显示Alpine对象
console.log(document.querySelector('[x-data="controlCenter()"]'))  // 应该返回元素
```

### Q3: "API请求失败"

**原因可能:**
1. 服务器未运行
2. 防火墙阻止
3. 端口被占用

**检查:**
```bash
# 检查服务器是否运行
curl http://localhost:8083

# 检查端口
lsof -i :8083

# 查看服务器日志
# （应该显示接收到的POST请求）
```

### Q4: "Show AI效果不工作"

**原因可能:**
1. CSS规则未加载
2. 元素类名不匹配
3. 浏览器缓存

**检查:**
```javascript
// 在Console中:
document.body.classList.contains('hide-ai')  // 应该返回true/false
getComputedStyle(document.querySelector('.ai-insight-text')).display
// 应该返回'none'或继承值
```

---

## 下一步行动

测试完成后：

1. ✅ 记录所有测试结果
2. ✅ 如有失败，按问题排查指南解决
3. ✅ 拍摄UI工作的截图（可选）
4. ✅ 更新此文档的测试报告部分
5. ✅ 提交测试结果

---

## 相关文档

- **实现文档:** [PHASE_8.3_IMPLEMENTATION.md](PHASE_8.3_IMPLEMENTATION.md)
- **测试指南:** [PHASE_8.3_TEST_GUIDE.md](PHASE_8.3_TEST_GUIDE.md)
- **自动化测试:** [test_phase8_3_control_center.py](../tests/test_phase8_3_control_center.py)
- **运行脚本:** [run_phase8_3_tests.sh](../run_phase8_3_tests.sh)
