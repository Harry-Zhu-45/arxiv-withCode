#!/usr/bin/env python3
"""
ArXiv Quant-Ph Paper Downloader
自动下载指定日期的 arXiv quant-ph 类别论文 PDF

使用方法:
    python download_arxiv_papers.py 2026-02-26
    python download_arxiv_papers.py --date 2026-02-26 --output ./papers
"""

import argparse
import re
import sys
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


class ArxivPaper:
    """ArXiv论文数据类"""
    def __init__(self, arxiv_id: str, title: str, date: str):
        self.arxiv_id = arxiv_id
        self.title = title
        self.date = date
        self.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    
    def __repr__(self):
        return f"ArxivPaper(id={self.arxiv_id})"


def parse_arxiv_page(html_content: str, target_date: str) -> List[ArxivPaper]:
    """解析ArXiv页面HTML，提取指定日期的论文"""
    papers = []
    
    # 日期解析映射
    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    
    # 1. 找到所有日期及其位置
    # 格式: <h3>Fri, 27 Feb 2026 (showing first 50 of 66 entries )</h3>
    date_header_pattern = r'<h3>\s*([A-Z][a-z]{2},\s+(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4}))'
    
    date_positions = []
    for match in re.finditer(date_header_pattern, html_content):
        day = match.group(2)
        month_abbrev = match.group(3)
        year = match.group(4)
        month = month_map.get(month_abbrev, '01')
        parsed_date = f"{year}-{month}-{day.zfill(2)}"
        
        date_positions.append({
            'date': parsed_date,
            'start': match.end()  # 从日期标题结束后开始
        })
    
    # 添加页面结束位置
    if date_positions:
        date_positions.append({'date': None, 'start': len(html_content)})
    
    # 2. 为每个日期区块，提取该区块内的所有论文
    for i, dp in enumerate(date_positions[:-1]):
        if dp['date'] != target_date:
            continue
            
        start_pos = dp['start']
        end_pos = date_positions[i + 1]['start']
        date_block = html_content[start_pos:end_pos]
        
        # 在这个区块内找到所有PDF和标题
        # 找标题: <div class='list-title mathjax'><span class='descriptor'>Title:</span> xxx</div>
        # 使用正则获取标题
        title_pattern = r"<div class='list-title[^>]*>.*?<span class='descriptor'>Title:</span>\s*(.+?)</div>"
        titles = re.findall(title_pattern, date_block, re.DOTALL)
        
        # 找PDF链接
        pdf_pattern = r'/pdf/(\d{4}\.\d{4,5})'
        pdfs = re.findall(pdf_pattern, date_block)
        
        # 配对标题和PDF（按顺序）
        for j, arxiv_id in enumerate(pdfs):
            title = titles[j] if j < len(titles) else f"Paper {arxiv_id}"
            # 清理标题
            title = re.sub(r'\s+', ' ', title).strip()
            papers.append(ArxivPaper(arxiv_id, title, dp['date']))
    
    return papers


def fetch_arxiv_page(url: str, max_retries: int = 3) -> Optional[str]:
    """获取ArXiv页面内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    for attempt in range(max_retries):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return None


def download_pdf(url: str, output_path: str, max_retries: int = 3) -> bool:
    """下载PDF文件"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    for attempt in range(max_retries):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
                content = response.read()
                with open(output_path, 'wb') as f:
                    f.write(content)
                return True
        except Exception as e:
            print(f"  Download failed (attempt {attempt+1}/{max_retries}): {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    
    return False


def main():
    parser = argparse.ArgumentParser(
        description="下载指定日期的 arXiv quant-ph 论文 PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python download_arxiv_papers.py 2026-02-26
    python download_arxiv_papers.py --date 2026-02-26 --output ./papers
    python download_arxiv_papers.py -d yesterday
        """
    )
    
    parser.add_argument(
        'date', 
        nargs='?', 
        default='yesterday',
        help='日期 (格式: YYYY-MM-DD, 或 "yesterday", "today")'
    )
    parser.add_argument(
        '--date', '-d',
        dest='date_alt',
        help='日期 (格式: YYYY-MM-DD)'
    )
    parser.add_argument(
        '--output', '-o',
        default='./arxiv_papers',
        help='输出目录 (默认: ./arxiv_papers)'
    )
    parser.add_argument(
        '--category', '-c',
        default='quant-ph',
        help='ArXiv 类别 (默认: quant-ph)'
    )
    
    args = parser.parse_args()
    
    # 处理日期参数
    date_str = args.date_alt if args.date_alt else args.date
    
    if date_str.lower() == 'today':
        target_date = datetime.now().strftime("%Y-%m-%d")
    elif date_str.lower() == 'yesterday':
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            target_date = date_str
        except ValueError:
            print(f"错误: 日期格式不正确，请使用 YYYY-MM-DD 格式", file=sys.stderr)
            sys.exit(1)
    
    print(f"目标日期: {target_date}")
    print(f"类别: {args.category}")
    print(f"输出目录: {args.output}")
    print("-" * 50)
    
    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建输出子目录: arxiv_papers/YYYY-MM-DD/{subject}
    date_dir = output_dir / target_date
    subject_dir = date_dir / args.category
    subject_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"存储目录: {subject_dir}")
    print("-" * 50)
    
    # 获取论文列表
    base_url = f"https://arxiv.org/list/{args.category}/recent"
    
    all_papers = []
    page = 0
    
    print("正在获取论文列表...")
    
    # 获取多页（每页50篇）
    while page < 5:
        if page == 0:
            url = base_url
        else:
            url = f"{base_url}?skip={page * 50}&show=50"
        
        print(f"  获取第 {page + 1} 页: {url}")
        html_content = fetch_arxiv_page(url)
        
        if not html_content:
            print(f"  无法获取第 {page + 1} 页")
            break
        
        papers = parse_arxiv_page(html_content, target_date)
        
        if not papers:
            print(f"  第 {page + 1} 页没有找到目标日期的论文")
            # 如果是第一页没找到，打印调试信息
            if page == 0:
                month_map = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
                date_debug = re.findall(r'<h3>\s*([A-Z][a-z]{2},\s+(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4}))', html_content)
                parsed_dates = []
                for d in date_debug:
                    parsed = f"{d[3]}-{month_map.get(d[2], '01')}-{d[1].zfill(2)}"
                    parsed_dates.append(parsed)
                print(f"  调试: 页面中的日期: {parsed_dates}")
            break
        
        print(f"  找到 {len(papers)} 篇论文")
        all_papers.extend(papers)
        
        # 如果当前页论文数少于50，说明已经是最后一页
        if len(papers) < 50:
            break
            
        page += 1
        time.sleep(1)
    
    print(f"\n共找到 {len(all_papers)} 篇论文")
    print("-" * 50)
    
    if not all_papers:
        print("未找到任何论文")
        sys.exit(0)
    
    # 下载PDF
    success_count = 0
    fail_count = 0
    
    print("开始下载PDF...")
    
    for i, paper in enumerate(all_papers, 1):
        output_file = subject_dir / f"{paper.arxiv_id}.pdf"
        
        # 截断标题显示
        title_short = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
        print(f"[{i}/{len(all_papers)}] {paper.arxiv_id}.pdf - {title_short}")
        print(f"    ", end="")
        
        if output_file.exists():
            print("已存在，跳过")
            success_count += 1
            continue
        
        if download_pdf(paper.pdf_url, str(output_file)):
            print("完成")
            success_count += 1
        else:
            print("失败")
            fail_count += 1
        
        time.sleep(0.3)
    
    print("-" * 50)
    print(f"下载完成!")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  存储位置: {subject_dir}")


if __name__ == "__main__":
    main()
