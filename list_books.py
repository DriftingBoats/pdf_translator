#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出输出目录中的所有书籍

用法:
  python list_books.py                    # 使用默认配置
  python list_books.py --config my.json   # 使用指定配置
  python list_books.py --output-dir ./output  # 直接指定输出目录
"""

import json
import argparse
import logging
from pathlib import Path
from typing import List, Tuple

# 设置简洁的日志格式
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)

def load_config(config_path: str = "config.json") -> dict:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"❌ 配置文件 {config_path} 不存在")
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"❌ 配置文件格式错误: {e}")
        return {}

def find_book_directories(base_dir: Path) -> List[Tuple[str, Path, dict]]:
    """查找所有书籍目录"""
    books = []
    
    if not base_dir.exists():
        return books
    
    # 检查base_dir本身是否是书籍目录
    if is_book_directory(base_dir):
        stats = get_book_stats(base_dir)
        books.append((base_dir.name, base_dir, stats))
        return books
    
    # 遍历子目录查找书籍
    for item in base_dir.iterdir():
        if item.is_dir() and is_book_directory(item):
            stats = get_book_stats(item)
            books.append((item.name, item, stats))
    
    return sorted(books, key=lambda x: x[0])

def is_book_directory(dir_path: Path) -> bool:
    """判断是否为书籍目录"""
    # 检查是否包含翻译相关的子目录或文件
    indicators = [
        'chap_md',           # 章节markdown目录
        'raw_content',       # 原始内容目录
        'glossary.tsv',      # 术语表文件
    ]
    
    found_indicators = 0
    for indicator in indicators:
        if (dir_path / indicator).exists():
            found_indicators += 1
    
    # 至少包含2个指示器才认为是书籍目录
    return found_indicators >= 2

def get_book_stats(book_dir: Path) -> dict:
    """获取书籍统计信息"""
    stats = {
        'total_batches': 0,
        'completed_batches': 0,
        'glossary_terms': 0,
        'has_final_md': False
    }
    
    # 统计批次信息
    chap_dir = book_dir / 'chap_md'
    if chap_dir.exists():
        batch_files = list(chap_dir.glob('batch_*.md'))
        stats['total_batches'] = len(batch_files)
        
        # 统计非空的批次文件
        for batch_file in batch_files:
            try:
                content = batch_file.read_text(encoding='utf-8')
                if content.strip():
                    stats['completed_batches'] += 1
            except Exception:
                pass
    
    # 统计术语表
    glossary_file = book_dir / 'glossary.tsv'
    if glossary_file.exists():
        try:
            content = glossary_file.read_text(encoding='utf-8')
            lines = [line for line in content.strip().split('\n') if line.strip() and '\t' in line]
            stats['glossary_terms'] = len(lines)
        except Exception:
            pass
    
    # 检查是否有最终合并的markdown文件
    for md_file in book_dir.glob('*.md'):
        if md_file.name not in ['README.md', 'GUIDE.md'] and not md_file.name.startswith('batch_'):
            stats['has_final_md'] = True
            break
    
    return stats

def analyze_book_quality(book_dir: Path) -> dict:
    """分析书籍翻译质量"""
    quality = {
        'problem_batches': [],
        'completion_rate': 0.0,
        'avg_segment_diff': 0.0
    }
    
    chap_dir = book_dir / 'chap_md'
    raw_content_dir = book_dir / 'raw_content'
    
    if not (chap_dir.exists() and raw_content_dir.exists()):
        return quality
    
    total_batches = 0
    completed_batches = 0
    total_diff = 0.0
    
    for batch_file in sorted(chap_dir.glob('batch_*.md')):
        total_batches += 1
        batch_num = int(batch_file.stem.split('_')[1])
        
        try:
            # 读取翻译结果
            translated_content = batch_file.read_text(encoding='utf-8')
            if not translated_content.strip():
                continue
            
            completed_batches += 1
            translated_segments = len(re.findall(r'<c\d+>', translated_content))
            
            # 读取原始文本
            raw_file = raw_content_dir / f'batch_{batch_num:03d}.txt'
            if raw_file.exists():
                raw_content = raw_file.read_text(encoding='utf-8')
                original_segments = len(re.findall(r'<c\d+>', raw_content))
                
                if original_segments > 0:
                    diff_ratio = abs(original_segments - translated_segments) / original_segments
                    total_diff += diff_ratio
                    
                    # 如果差异超过20%，标记为问题批次
                    if diff_ratio > 0.2:
                        quality['problem_batches'].append({
                            'batch': batch_num,
                            'original': original_segments,
                            'translated': translated_segments,
                            'diff_ratio': diff_ratio
                        })
        except Exception:
            continue
    
    if total_batches > 0:
        quality['completion_rate'] = completed_batches / total_batches
    
    if completed_batches > 0:
        quality['avg_segment_diff'] = total_diff / completed_batches
    
    return quality

def main():
    parser = argparse.ArgumentParser(description='列出输出目录中的所有书籍')
    parser.add_argument('--config', default='config.json', help='配置文件路径')
    parser.add_argument('--output-dir', help='直接指定输出目录路径')
    parser.add_argument('--detailed', action='store_true', help='显示详细的质量分析')
    
    args = parser.parse_args()
    
    # 确定输出目录
    if args.output_dir:
        base_dir = Path(args.output_dir)
    else:
        config = load_config(args.config)
        if not config:
            print("❌ 无法加载配置文件，请使用 --output-dir 直接指定目录")
            return
        base_dir = Path(config.get('output_dir', 'output'))
    
    if not base_dir.exists():
        print(f"❌ 输出目录不存在: {base_dir}")
        return
    
    # 查找书籍目录
    books = find_book_directories(base_dir)
    
    if not books:
        print(f"📚 在 {base_dir} 中未找到任何书籍目录")
        print("\n💡 书籍目录应包含以下结构:")
        print("   ├── chap_md/        # 翻译结果")
        print("   ├── raw_content/    # 原始内容")
        print("   └── glossary.tsv    # 术语表")
        return
    
    print(f"📚 在 {base_dir} 中找到 {len(books)} 本书:")
    print("=" * 80)
    
    for i, (book_name, book_path, stats) in enumerate(books, 1):
        print(f"\n{i}. 📖 {book_name}")
        print(f"   📁 路径: {book_path}")
        print(f"   📊 批次: {stats['completed_batches']}/{stats['total_batches']} 已完成")
        print(f"   📚 术语: {stats['glossary_terms']} 个条目")
        print(f"   📄 最终文档: {'✅' if stats['has_final_md'] else '❌'}")
        
        if args.detailed:
            import re
            quality = analyze_book_quality(book_path)
            completion_pct = quality['completion_rate'] * 100
            avg_diff_pct = quality['avg_segment_diff'] * 100
            
            print(f"   📈 完成率: {completion_pct:.1f}%")
            print(f"   📉 平均段落差异: {avg_diff_pct:.1f}%")
            
            if quality['problem_batches']:
                print(f"   ⚠️  问题批次: {len(quality['problem_batches'])} 个")
                for prob in quality['problem_batches'][:3]:  # 只显示前3个
                    print(f"      批次{prob['batch']}: {prob['original']}→{prob['translated']} ({prob['diff_ratio']:.1%})")
                if len(quality['problem_batches']) > 3:
                    print(f"      ... 还有 {len(quality['problem_batches']) - 3} 个问题批次")
    
    print("\n" + "=" * 80)
    print("💡 使用方法:")
    print("   # 重新翻译指定书籍的批次")
    for i, (book_name, book_path, _) in enumerate(books[:3], 1):  # 只显示前3个示例
        print(f"   python retranslate_batch.py 9 --book-dir '{book_path}'")
    
    print("\n   # 重新翻译指定书籍的所有问题批次")
    if books:
        book_name, book_path, _ = books[0]
        print(f"   python retranslate_batch.py --all-diff --book-dir '{book_path}'")

if __name__ == "__main__":
    main()