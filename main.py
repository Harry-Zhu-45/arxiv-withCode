#!/usr/bin/env python3
"""
ArXiv多主题论文下载与代码声明检索工具

支持 subjects: quant-ph, physics.optics, cond-mat

Usage:
    uv run python main.py                    # 下载当天所有主题论文并检索
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
# 要监控的 ArXiv 主题列表
ARXIV_SUBJECTS = [
    "quant-ph",
    "physics.optics", 
    "cond-mat"
]

# 主题显示名称映射
SUBJECT_DISPLAY_NAMES = {
    "quant-ph": "Quantum Physics",
    "physics.optics": "Optics",
    "cond-mat": "Condensed Matter"
}

KEYWORDS = [
    "github", "gitlab", "bitbucket", "repository",
    "zenodo", "figshare", "dataverse", "osf",
    "code available", "data available", "source code",
    "open source", "publicly available", "available at"
]

# 输出目录配置
OUTPUT_ROOT = "arxiv_papers"
REPORT_ROOT = "reports"


# ============== 辅助函数 ==============
def get_today_date():
    """获取今天的日期字符串"""
    return datetime.now().strftime('%Y-%m-%d')


def get_subject_folder(subject, date):
    """获取某个主题的文件夹路径"""
    return f"{OUTPUT_ROOT}/arxiv_{subject}_{date}"


def get_all_subject_folders(date):
    """获取所有主题的文件夹"""
    folders = []
    for subject in ARXIV_SUBJECTS:
        folder = get_subject_folder(subject, date)
        if os.path.exists(folder):
            folders.append((subject, folder))
    return folders


def get_latest_date_folders():
    """自动获取最新日期的所有主题文件夹"""
    # 查找最新的日期
    pattern = f"{OUTPUT_ROOT}/arxiv_*_????-??-??"
    all_folders = glob.glob(pattern)
    
    # 兼容Windows路径
    all_folders = [f.replace('\\', '/') for f in all_folders]
    
    if not all_folders:
        return []
    
    # 提取日期并排序
    date_folders = {}
    for folder in all_folders:
        # 提取日期 (arxiv_quant-ph_2026-03-02 -> 2026-03-02)
        parts = folder.split('_')
        if len(parts) >= 3:
            date = parts[-1]
            if date not in date_folders:
                date_folders[date] = []
            date_folders[date].append(folder)
    
    if not date_folders:
        return []
    
    # 返回最新日期的文件夹
    latest_date = max(date_folders.keys())
    result = []
    for f in date_folders[latest_date]:
        # 提取subject (e.g., arxiv_cond-mat_2026-03-02 -> cond-mat)
        # 格式: .../arxiv_papers/arxiv_{subject}_{date}
        folder_name = os.path.basename(f)  # 获取最后一部分，如 arxiv_cond-mat_2026-03-02
        # 去掉arxiv_前缀和日期后缀
        subject = folder_name.replace('arxiv_', '').rsplit('_', 1)[0]
        result.append((subject, f))
    return result


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


def search_pdf(pdf_path, arxiv_id, subject):
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
        
        # 构建arXiv摘要链接
        abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        
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
        
        return {
            'title': title, 
            'abstract': abstract, 
            'findings': found,
            'arxiv_id': arxiv_id,
            'abs_url': abs_url,
            'subject': subject,
            'subject_display': SUBJECT_DISPLAY_NAMES.get(subject, subject)
        } if found else None
        
    except Exception as e:
        print(f"  Error: {e}")
        return None


def generate_unified_report(all_results, output_path):
    """生成统一的Markdown报告"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 统计
    total_scanned = sum(r['scanned'] for r in all_results)
    total_found = sum(len(r['found']) for r in all_results)
    
    md = f"""# ArXiv Daily Code/Data Declaration Report

**Date**: {today}  
**Subjects**: {', '.join([SUBJECT_DISPLAY_NAMES.get(s, s) for s in ARXIV_SUBJECTS])}  
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Summary

| Subject | Scanned | Found |
|---------|---------|-------|
"""
    
    # 按主题统计
    for r in all_results:
        subject = r['subject']
        display = SUBJECT_DISPLAY_NAMES.get(subject, subject)
        md += f"| {display} | {r['scanned']} | {len(r['found'])} |\n"
    
    md += f"""
**Total**: {total_scanned} papers scanned, {total_found} papers with declarations found

---

"""
    
    # 收集所有找到的论文
    all_found = []
    for r in all_results:
        all_found.extend(r['found'])
    
    if not all_found:
        md += "## Results\n\nNo papers with code/data declarations found.\n"
    else:
        md += f"## Results ({len(all_found)} papers)\n\n"
        
        for i, p in enumerate(all_found, 1):
            md += f"""### {i}. [{p['arxiv_id']}]({p['abs_url']})

**Subject**: {p['subject_display']}  
**Title**: {p['title']}

**Abstract**: {p['abstract'][:300]}{'...' if len(p['abstract']) > 300 else ''}

**Declarations Found**:

"""
            for f in p['findings']:
                md += f"""- `{f['keyword']}` (Page {f['page']})
  > ...{f['context']}...

"""

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    return output_path


# ============== 主流程 ==============
def run_download():
    """下载所有主题的论文"""
    print("=" * 60)
    print("Step 1: 下载ArXiv论文")
    print("=" * 60)
    
    today = get_today_date()
    
    # 尝试导入下载模块
    try:
        from download_arxiv_papers import main as download_main
        import sys
    except ImportError:
        print("Error: download_arxiv_papers.py not found")
        sys.exit(1)
    
    # 逐个下载每个主题
    for subject in ARXIV_SUBJECTS:
        print(f"\n>>> 下载主题: {subject}")
        print("-" * 40)
        
        try:
            sys.argv = ['download_arxiv_papers.py', today, '-c', subject]
            download_main()
        except SystemExit:
            pass  # 忽略下载脚本的退出
        except Exception as e:
            print(f"Error downloading {subject}: {e}")
        
        import time
        time.sleep(1)  # 避免请求过快


def run_search():
    """检索所有主题的PDF"""
    print("\n" + "=" * 60)
    print("Step 2: 检索代码/数据公开声明")
    print("=" * 60)
    
    # 获取所有主题的文件夹
    subject_folders = get_latest_date_folders()
    
    if not subject_folders:
        print("Error: 未找到任何论文文件夹")
        print("请先运行下载: uv run python main.py --download-only")
        sys.exit(1)
    
    print(f"找到以下文件夹:")
    for subject, folder in subject_folders:
        print(f"  - {subject}: {folder}")
    print()
    
    all_results = []
    
    # 逐个主题检索
    for subject, folder in subject_folders:
        print(f"--- 处理主题: {subject} ---")
        
        pdf_files = [f for f in os.listdir(folder) if f.endswith('.pdf')]
        print(f"找到 {len(pdf_files)} 个PDF文件")
        
        results = {'subject': subject, 'scanned': len(pdf_files), 'found': []}
        
        for i, pdf_file in enumerate(pdf_files, 1):
            arxiv_id = pdf_file.replace('.pdf', '')
            print(f"  [{i}/{len(pdf_files)}] {arxiv_id}...", end=" ")
            
            result = search_pdf(os.path.join(folder, pdf_file), arxiv_id, subject)
            
            if result:
                results['found'].append(result)
                print(f"✓ {len(result['findings'])} 处")
            else:
                print("✗")
        
        all_results.append(results)
        print()
    
    # 生成统一报告
    today = get_today_date()
    report_dir = REPORT_ROOT
    report_path = f"{report_dir}/code_declaration_report_{today}.md"
    
    generate_unified_report(all_results, report_path)
    
    # 汇总统计
    total_scanned = sum(r['scanned'] for r in all_results)
    total_found = sum(len(r['found']) for r in all_results)
    
    print("=" * 60)
    print("完成!")
    print(f"  扫描: {total_scanned} 篇")
    print(f"  发现: {total_found} 篇包含声明")
    print(f"  报告: {report_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='ArXiv多主题论文下载与检索工具')
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
