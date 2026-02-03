#!/usr/bin/env python3
"""测试VL模型效果 - 对比OCR和OCR+VL的差异"""

import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".myrecall_data" / "db" / "recall.db"

def get_processed_entries(limit=10):
    """获取已处理的条目"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, timestamp, app, title, status, text, description 
        FROM entries 
        WHERE status = 'COMPLETED' 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (limit,))
    
    entries = cursor.fetchall()
    conn.close()
    return entries

def get_status_summary():
    """获取各状态统计"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("SELECT status, COUNT(*) FROM entries GROUP BY status")
    stats = dict(cursor.fetchall())
    
    conn.close()
    return stats

def compare_ocr_vl():
    """对比OCR和VL模型的效果"""
    print("\n" + "="*80)
    print("🔍 OpenRecall - OCR vs VL 模型效果对比")
    print("="*80 + "\n")
    
    # 显示状态统计
    stats = get_status_summary()
    print("📊 数据库状态统计:")
    for status, count in stats.items():
        icon = {
            'COMPLETED': '✅',
            'PENDING': '⏳',
            'PROCESSING': '⚙️',
            'FAILED': '❌'
        }.get(status, '❓')
        print(f"  {icon} {status}: {count} 条")
    
    print()
    
    # 获取已处理的条目
    entries = get_processed_entries(limit=10)
    
    if not entries:
        print("❌ 没有找到已完成的条目！")
        print("💡 提示：等待几秒让worker处理队列中的任务")
        return
    
    print(f"✅ 找到 {len(entries)} 条已完成的条目\n")
    
    # 逐条对比
    for idx, entry in enumerate(entries, 1):
        entry_id, timestamp, app, title, status, text, description = entry
        
        print("="*80)
        print(f"条目 #{idx} (ID: {entry_id})")
        print(f"应用: {app} | 标题: {title}")
        print("-"*80)
        
        # OCR文本
        print(f"\n📝 OCR提取文本 ({len(text)} 字符):")
        print("-"*80)
        preview = text[:300] + "..." if len(text) > 300 else text
        print(preview)
        print("-"*80)
        
        # VL描述
        if description:
            print(f"\n🤖 VL模型描述 ({len(description)} 字符):")
            print("-"*80)
            print(description)
            print("-"*80)
        else:
            print("\n❌ 没有VL模型描述")
        
        # 分析对比
        print("\n💡 分析:")
        if description:
            print(f"  • OCR提取了 {len(text)} 个字符的文本内容")
            print(f"  • VL模型生成了 {len(description)} 个字符的语义描述")
            
            # 简单的差异分析
            if "describe" in description.lower() or "image" in description.lower():
                print("  ✅ VL模型提供了图像的语义理解")
            if len(description) > 50:
                print("  ✅ VL模型生成了详细的描述")
        else:
            print("  ❌ VL模型未生成描述（可能处理失败）")
        
        print("\n")

def show_comparison_table():
    """显示对比表格"""
    entries = get_processed_entries(limit=5)
    
    if not entries:
        print("❌ 没有已完成的条目")
        return
    
    print("\n" + "="*80)
    print("OCR vs VL 模型效果对比")
    print("="*80)
    print(f"{'ID':<6} {'应用':<15} {'OCR长度':<10} {'VL长度':<10} {'VL状态':<10}")
    print("-"*80)
    
    for entry in entries:
        entry_id, timestamp, app, title, status, text, description = entry
        ocr_len = len(text) if text else 0
        vl_len = len(description) if description else 0
        vl_status = "✅ 有" if description else "❌ 无"
        
        print(f"{entry_id:<6} {app[:15]:<15} {ocr_len:<10} {vl_len:<10} {vl_status:<10}")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--table":
        show_comparison_table()
    else:
        compare_ocr_vl()
