#!/usr/bin/env python3
"""
ArXiv多主题论文下载与代码声明检索工具

支持 subjects: quant-ph, physics.optics, cond-mat, physics.flu-dyn

Usage:
    uv run python main.py                    # 下载当天所有主题论文并检索
    uv run python main.py --download-only    # 仅下载论文
    uv run python main.py --search-only       # 仅检索已有PDF
"""

import argparse
import glob
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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
    "cond-mat",
    "physics.flu-dyn",
]

# 主题显示名称映射
SUBJECT_DISPLAY_NAMES = {
    "quant-ph": "Quantum Physics",
    "physics.optics": "Optics",
    "cond-mat": "Condensed Matter",
    "physics.flu-dyn": "Fluid Dynamics",
}

KEYWORDS = [
    "github", "gitlab", "bitbucket", "repository",
    "zenodo", "figshare", "dataverse",
    "code available", "data available", "source code",
    "open source", "available at"
]

# 负向排除短语：命中关键字但语境为不可用时不计入
EXCLUDE_PHRASES = [
    "not publicly available",
    "are not publicly available",
    "not publicly released",
    "not available to the public",
    "not available publicly",
    "not open source",
    "not released",
    "not available"
]

EXCLUDE_CONTEXT_WINDOW = 200

# 输出目录配置
OUTPUT_ROOT = "arxiv_papers"
REPORT_ROOT = "reports"


# ============== 辅助函数 ==============
def get_today_date():
    """获取今天的日期字符串"""
    return datetime.now().strftime('%Y-%m-%d')


def get_subject_folder(subject, date):
    """获取某个主题的文件夹路径"""
    return f"{OUTPUT_ROOT}/{date}/{subject}"


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
    pattern = f"{OUTPUT_ROOT}/????-??-??"
    all_date_folders = glob.glob(pattern)
    
    # 兼容Windows路径
    all_date_folders = [f.replace('\\', '/') for f in all_date_folders]
    
    if not all_date_folders:
        return []
    
    # 提取日期并排序
    date_folders = {}
    for folder in all_date_folders:
        date = os.path.basename(folder)
        if date:
            date_folders[date] = folder

    if not date_folders:
        return []

    # 返回最新日期的所有主题文件夹
    latest_date = max(date_folders.keys())
    latest_date_folder = date_folders[latest_date]
    result = []
    subject_folders = glob.glob(f"{latest_date_folder}/*")
    subject_folders = [f.replace('\\', '/') for f in subject_folders]
    for f in subject_folders:
        if os.path.isdir(f):
            subject = os.path.basename(f)
            result.append((subject, f))
    return result


def normalize_whitespace(text):
    """Normalize repeated whitespace inside metadata fields."""
    if not text:
        return ""
    return " ".join(str(text).split())


def normalize_arxiv_id(value):
    """Normalize an arXiv identifier to the bare xxxx.xxxxx form."""
    if not value:
        return ""

    normalized = normalize_whitespace(value)
    normalized = normalized.rsplit("/", 1)[-1]
    if normalized.endswith(".pdf"):
        normalized = normalized[:-4]
    if "?" in normalized:
        normalized = normalized.split("?", 1)[0]

    version_match = re.match(r"^(.+?)v\d+$", normalized)
    if version_match:
        normalized = version_match.group(1)

    return normalized


def is_metadata_complete(metadata):
    """Return True when cached metadata is good enough for report output."""
    if not isinstance(metadata, dict):
        return False

    authors = metadata.get("authors", [])
    if isinstance(authors, str):
        authors = [authors]

    return bool(normalize_whitespace(metadata.get("title"))) and bool(
        normalize_whitespace(metadata.get("abstract"))
    ) and any(normalize_whitespace(author) for author in authors)


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


def fetch_url(url, timeout=30, max_retries=3):
    """获取URL内容（文本）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    for attempt in range(max_retries):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    return None


def fetch_arxiv_metadata(arxiv_ids):
    """通过arXiv官方API获取标题和摘要"""
    if not arxiv_ids:
        return {}

    base_url = "https://export.arxiv.org/api/query?"
    batch_size = 50
    metadata = {}

    for i in range(0, len(arxiv_ids), batch_size):
        batch = [normalize_arxiv_id(arxiv_id) for arxiv_id in arxiv_ids[i:i + batch_size]]
        batch = [arxiv_id for arxiv_id in batch if arxiv_id]
        if not batch:
            continue

        query = urllib.parse.urlencode({
            "id_list": ",".join(batch),
            "start": 0,
            "max_results": len(batch),
        })
        url = base_url + query
        xml_text = fetch_url(url, timeout=40)
        if not xml_text:
            continue

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"API parse error: {e}", file=sys.stderr)
            continue

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        batch_metadata = {}
        for entry in root.findall("atom:entry", ns):
            id_node = entry.find("atom:id", ns)
            title_node = entry.find("atom:title", ns)
            summary_node = entry.find("atom:summary", ns)

            if id_node is None or not id_node.text:
                continue

            abs_url = id_node.text.strip()
            arxiv_id = normalize_arxiv_id(abs_url)

            title = title_node.text.strip() if title_node is not None and title_node.text else ""
            summary = summary_node.text.strip() if summary_node is not None and summary_node.text else ""
            authors = []
            for author_node in entry.findall("atom:author/atom:name", ns):
                if author_node.text:
                    author_name = normalize_whitespace(author_node.text)
                    if author_name:
                        authors.append(author_name)

            title = normalize_whitespace(title)
            summary = normalize_whitespace(summary)

            batch_metadata[arxiv_id] = {
                "title": title,
                "abstract": summary,
                "authors": authors,
            }

        metadata.update(batch_metadata)
        missing_in_batch = [arxiv_id for arxiv_id in batch if arxiv_id not in batch_metadata]
        if missing_in_batch:
            print(
                f"Warning: metadata missing for {len(missing_in_batch)} IDs in API batch",
                file=sys.stderr,
            )

        time.sleep(0.5)

    return metadata


def load_metadata_cache(cache_path):
    """读取本地元数据缓存"""
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw_cache = json.load(f)
    except Exception:
        return {}

    if not isinstance(raw_cache, dict):
        return {}

    normalized_cache = {}
    for arxiv_id, metadata in raw_cache.items():
        normalized_id = normalize_arxiv_id(arxiv_id)
        if not normalized_id or not isinstance(metadata, dict):
            continue

        authors = metadata.get("authors", [])
        if isinstance(authors, str):
            authors = [authors]
        elif not isinstance(authors, list):
            authors = []

        normalized_cache[normalized_id] = {
            "title": normalize_whitespace(metadata.get("title")),
            "abstract": normalize_whitespace(metadata.get("abstract")),
            "authors": [
                author_name
                for author in authors
                if (author_name := normalize_whitespace(author))
            ],
        }

    return normalized_cache


def save_metadata_cache(cache_path, metadata):
    """保存元数据缓存到本地"""
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=True, indent=2)
    except Exception as e:
        print(f"Warning: failed to save metadata cache: {e}")


def search_pdf(pdf_path, arxiv_id, subject, metadata_lookup=None):
    """检索单个PDF"""
    import re
    
    if not os.path.exists(pdf_path):
        return None
    
    try:
        doc = fitz.open(pdf_path)
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()

        meta = metadata_lookup.get(normalize_arxiv_id(arxiv_id), {}) if metadata_lookup else {}
        fallback_title, fallback_abstract = extract_title_abstract(full_text)
        title = meta.get("title") or fallback_title or arxiv_id
        abstract = meta.get("abstract") or fallback_abstract
        authors = meta.get("authors", [])
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
                    context_start = max(0, pos - EXCLUDE_CONTEXT_WINDOW)
                    context_end = min(len(full_text), pos + len(kw) + EXCLUDE_CONTEXT_WINDOW)
                    context = full_text[context_start:context_end].replace('\n', ' ')
                    context_lower = context.lower()
                    if any(p in context_lower for p in EXCLUDE_PHRASES):
                        continue
                    found.append({'keyword': kw, 'page': page_num, 'context': context})
        
        return {
            'title': title, 
            'abstract': abstract, 
            'authors': authors,
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
            authors_line = (
                f"**Authors**: {', '.join(p['authors'])}\n\n"
                if p.get('authors')
                else ""
            )
            abstract_text = p['abstract'] if p['abstract'] else "_Abstract unavailable._"
            md += f"""### {i}. [{p['arxiv_id']}]({p['abs_url']})

**Subject**: {p['subject_display']}  
**Title**: {p['title']}

{authors_line}**Abstract**: {abstract_text}

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

        arxiv_ids = [f.replace('.pdf', '') for f in pdf_files]
        cache_path = os.path.join(folder, "metadata.json")
        metadata_lookup = load_metadata_cache(cache_path)
        refresh_ids = [
            arxiv_id for arxiv_id in arxiv_ids
            if not is_metadata_complete(metadata_lookup.get(normalize_arxiv_id(arxiv_id)))
        ]
        if refresh_ids:
            print(f"  Refreshing metadata for {len(refresh_ids)} papers")
            fetched = fetch_arxiv_metadata(refresh_ids)
            if fetched:
                metadata_lookup.update(fetched)
                save_metadata_cache(cache_path, metadata_lookup)
        else:
            print("  Metadata cache is complete")
        
        results = {'subject': subject, 'scanned': len(pdf_files), 'found': []}
        
        for i, pdf_file in enumerate(pdf_files, 1):
            arxiv_id = pdf_file.replace('.pdf', '')
            print(f"  [{i}/{len(pdf_files)}] {arxiv_id}...", end=" ")
            
            result = search_pdf(os.path.join(folder, pdf_file), arxiv_id, subject, metadata_lookup)
            
            if result:
                results['found'].append(result)
                print(f"FOUND {len(result['findings'])} matches")
            else:
                print("NONE")
        
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
