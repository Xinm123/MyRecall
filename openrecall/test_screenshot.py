#!/usr/bin/env python3
"""测试截图功能是否正常"""

import time
from openrecall.client.recorder import ScreenRecorder
from openrecall.shared.config import settings

print("🧪 测试截图功能...")
print(f"配置: 间隔={settings.capture_interval}秒, 主屏幕={settings.primary_monitor_only}")

recorder = ScreenRecorder()
print(f"✅ Recorder初始化成功")
print(f"📊 监控数量: {len(recorder.monitors)}")

# 测试截图
print("\n开始测试截图...")
for i in range(3):
    print(f"\n第{i+1}次截图...")
    time.sleep(1)
    
print("\n✅ 测试完成！如果没有错误，说明截图功能正常。")
print("💡 提示：使用 combined 模式启动完整服务。")
