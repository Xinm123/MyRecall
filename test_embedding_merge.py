#!/usr/bin/env python3
"""测试Embedding合并逻辑 - 验证OCR+VL文本如何合并"""

import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".myrecall_data" / "db" / "recall.db"

def show_embedding_content():
    """显示最新条目的OCR、VL和合并后的文本"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取最新的3条已完成记录
    cursor.execute("""
        SELECT id, app, title, text, description
        FROM entries
        WHERE status = 'COMPLETED'
        ORDER BY id DESC
        LIMIT 3
    """)
    
    entries = cursor.fetchall()
    conn.close()
    
    if not entries:
        print("❌ 没有已完成的条目")
        return
    
    for idx, (entry_id, app, title, text, description) in enumerate(entries, 1):
        print("\n" + "="*80)
        print(f"条目 #{entry_id}: {app} - {title}")
        print("="*80)
        
        print(f"\n📝 OCR文本 ({len(text)} 字符):")
        print("-"*80)
        print(text)
        
        print(f"\n🤖 VL描述 ({len(description)} 字符):")
        print("-"*80)
        print(description)
        
        # 模拟worker中的合并逻辑
        combined_text = f"{text}\n{description}"
        
        print(f"\n🔗 合并后的文本 (总计 {len(combined_text)} 字符):")
        print("-"*80)
        print("【这就是送入embedding模型的完整文本】")
        print(combined_text)
        print("-"*80)
        
        print(f"\n💡 分析:")
        print(f"  • OCR提取了 {len(text)} 字符")
        print(f"  • VL生成了 {len(description)} 字符")
        print(f"  • 合并后总计 {len(combined_text)} 字符用于生成embedding")
        print(f"  • 比例：OCR占 {len(text)/len(combined_text)*100:.1f}%，VL占 {len(description)/len(combined_text)*100:.1f}%")
        
        if idx < len(entries):
            print("\n" + "─"*80)

if __name__ == "__main__":
    show_embedding_content()
