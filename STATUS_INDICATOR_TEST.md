# 如何测试状态指示器（Spinner）

## 问题
当前所有截图都已处理完成（状态为COMPLETED），所以看不到旋转的spinner图标。

## 测试方法

### 方法1：触发新的截图（推荐）
1. 确保服务器在运行（combined模式）
2. 等待自动截图（默认每5秒一次）
3. **立即**刷新网页 http://localhost:8083
4. 你应该能看到最新的卡片显示：
   - 🔄 蓝色旋转的spinner
   - "Analyzing..." 文字
5. 等待5-10秒后刷新，应该看到✨图标和AI描述

### 方法2：手动触发截图
```bash
# 使用API触发截图
curl -X POST http://localhost:8083/api/capture
```

### 方法3：清空数据库重新开始
```bash
# 停止服务器
# 删除数据库
rm ~/.myrecall_data/db/recall.db
# 重启服务器
python -m openrecall.main --mode combined
```

## 优化说明

### 已完成的优化：
1. ✅ **时间显示精确到秒**：格式从 `%H:%M` 改为 `%H:%M:%S`
2. ✅ **Spinner增强可见性**：
   - 尺寸从12px增加到14px
   - 边框加粗到2.5px
   - 颜色使用Apple蓝色的半透明底色
   - 旋转速度从0.8s加快到0.6s
3. ✅ **AI描述优化**：
   - 限制最多显示2行（约3em高度）
   - 超出部分自动省略（...）
   - 使用CSS的-webkit-line-clamp截断
4. ✅ **AI提示词优化**：
   - 从："Briefly describe: 1) the application being used, 2) what the user is doing..."
   - 改为："In one sentence: What app is this and what is the user doing?"
   - 应该能生成更简洁的描述

### 新的AI描述示例预期：
- 旧：详细的多点描述（如附图中的长段落）
- 新：简短一句话，例如："用户在Chrome浏览器中搜索网页历史"

## 当前UI效果
- 网格布局，响应式卡片
- 卡片头部：应用名 + 时间戳（精确到秒）
- 卡片图片：懒加载，点击放大
- 卡片底部：
  - PENDING/PROCESSING → 蓝色spinner + "Analyzing..."
  - COMPLETED → ✨ + 简洁的AI描述（最多2行）
  - 无AI → "Image captured"
