#!/usr/bin/env python3
"""
ArXiv论文下载与代码声明检索工具

Usage:
    uv run python main.py                    # 下载当天论文并检索
    uv run python main.py --download-only    # 仅下载论文
    uv run python main.py --search-only       # 仅检索已有PDF
"""

import argparse
import os
import sys
import glob
from datetime import datetime

# 导入功能模块
try:
    import fitz  # pymupdf
except ImportError:
    print("Error: pymupdf not installed. Run 'uv sync' first.")
    sys.exit(1)


# ============== 配置 ==============
ARXIV_SUBJECT = "quant-ph"
KEYWORDS = [
    "github", "gitlab", "bitbucket", "repository",
    "zenodo", "figshare", "dataverse", "osf",
    "code available", "data available", "source code",
    "open source", "publicly available", "available at"
]


# ============== 辅助函数 ==============
def get_latest_folder():
    """自动获取最新的论文文件夹"""
    pattern = f"arxiv_papers/arxiv_{ARXIV_SUBJECT}_*"
    folders = glob.glob(pattern)
    if not folders:
        return None
    # 按日期排序，取最新的
    folders.sort(reverse=True)
    return folders[0]


def extract_title_abstract(text):
    """提取标题和摘要"""
    import re
    
    title, abstract = "", ""
    
    # 查找Abstract部分
    abstract_match = re.search(r'Abstract\s*\n(.*?)(?:\nKeywords|\n\d|\Z)', text, re.DOTALL | re.IGNORECASE)
    
    if abstract_match:
        abstract = re.sub(r'\s+', ' ', abstract_match.group(1).strip())
        # 标题在Abstract之前
        title_text = text[:abstract_match.start()].strip()
        lines = [l.strip() for l in title_text.split('\n') if len(l.strip()) > 10]
        if lines:
            title = lines[-1]
    else:
        title = text[:300].strip().split('\n')[0]
    
    return title, abstract


def search_pdf(pdf_path):
    """检索单个PDF"""
    import re
    
    if not os.path.exists(pdf_path):
        return None
    
    try:
        doc = fitz.open(pdf_path)
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()
        
        title, abstract = extract_title_abstract(full_text)
        text_lower = full_text.lower()
        
        found = []
        for kw in KEYWORDS:
            if kw.lower() in text_lower:
                # 找位置和页码
                for m in re.finditer(re.escape(kw.lower()), text_lower):
                    pos = m.start()
                    # 简单估算页码
                    page_num = full_text[:pos].count('\n') // 50 + 1
                    context = full_text[max(0, pos-80):min(len(full_text), pos+len(kw)+80)].replace('\n', ' ')
                    found.append({'keyword': kw, 'page': page_num, 'context': context})
        
        return {'title': title, 'abstract': abstract, 'findings': found} if found else None
        
    except Exception as e:
        print(f"  Error: {e}")
        return None


def generate_report(results, output_path):
    """生成Markdown报告"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    md = f"""# ArXiv {ARXIV_SUBJECT} {today} 代码/数据公开声明检索报告

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

扫描PDF: {results['scanned']} 篇 | 发现声明: {len(results['found'])} 篇

---

"""
    
    if not results['found']:
        md += "未发现包含代码/数据公开声明的论文。\n"
    else:
        for i, p in enumerate(results['found'], 1):
            md += f"""## {i}. {p['arxiv_id']}

**标题**: {p['title']}

**摘要**: {p['abstract'][:300]}{'...' if len(p['abstract']) > 300 else ''}

### 发现的声明

"""
            for f in p['findings']:
                md += f"""- `{f['keyword']}` (第{f['page']}页)
  > ...{f['context']}...

"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    return output_path


# ============== 主流程 ==============
def run_download():
    """下载论文"""
    print("=" * 50)
    print("Step 1: 下载ArXiv论文")
    print("=" * 50)
    
    # 尝试导入下载模块并调用main函数
    try:
        from download_arxiv_papers import main as download_main
        import sys
        
        # 模拟命令行参数: 下载今天的论文
        sys.argv = ['download_arxiv_papers.py', 'today', '-c', ARXIV_SUBJECT]
        download_main()
    except ImportError:
        print("Error: download_arxiv_papers.py not found")
        sys.exit(1)


def run_search():
    """检索PDF"""
    print("\n" + "=" * 50)
    print("Step 2: 检索代码/数据公开声明")
    print("=" * 50)
    
    pdf_folder = get_latest_folder()
    
    if not pdf_folder or not os.path.exists(pdf_folder):
        print(f"Error: 文件夹不存在: {pdf_folder}")
        print("请先运行下载: uv run python main.py --download-only")
        sys.exit(1)
    
    # 获取所有PDF
    pdf_files = [f for f in os.listdir(pdf_folder) if f.endswith('.pdf')]
    print(f"找到 {len(pdf_files)} 个PDF文件\n")
    
    results = {'scanned': len(pdf_files), 'found': []}
    
    for i, pdf_file in enumerate(pdf_files, 1):
        arxiv_id = pdf_file.replace('.pdf', '')
        print(f"[{i}/{len(pdf_files)}] 处理 {arxiv_id}...", end=" ")
        
        result = search_pdf(os.path.join(pdf_folder, pdf_file))
        
        if result:
            result['arxiv_id'] = arxiv_id
            results['found'].append(result)
            print(f"✓ 发现 {len(result['findings'])} 处")
        else:
            print("✗")
    
    # 生成报告
    today = datetime.now().strftime('%Y-%m-%d')
    report_path = f"code_declaration_report_{today}.md"
    generate_report(results, report_path)
    
    print("\n" + "=" * 50)
    print(f"完成! 发现 {len(results['found'])} 篇包含声明")
    print(f"报告: {report_path}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description='ArXiv论文下载与检索工具')
    parser.add_argument('--download-only', action='store_true', help='仅下载论文')
    parser.add_argument('--search-only', action='store_true', help='仅检索已有PDF')
    
    args = parser.parse_args()
    
    if args.download_only:
        run_download()
    elif args.search_only:
        run_search()
    else:
        run_download()
        run_search()


if __name__ == "__main__":
    main()
