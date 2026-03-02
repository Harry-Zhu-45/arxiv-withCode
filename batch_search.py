"""
批量PDF检索脚本
扫描arxiv_quant-ph_2026-03-02文件夹中所有PDF，查找代码/数据公开声明
"""

import fitz  # pymupdf
import os
import re
from datetime import datetime


# 扩展关键字列表，包括更多公开代码/数据的声明
KEYWORDS = [
    "github", "gitlab", "bitbucket", "repository", 
    "zenodo", "figshare", "dataverse", "osf",
    "code available", "data available", "source code", 
    "open source", "publicly available", "available at"
]


def extract_title_and_abstract(text):
    """
    从PDF文本中提取标题和摘要
    arXiv论文通常在开头有标题和摘要
    """
    lines = text.split('\n')
    
    # 标题通常是第一行或前几行的较大字体文本
    # 摘要通常在关键词前面
    title = ""
    abstract = ""
    
    # 尝试找到标题（在Abstract之前的内容）
    abstract_match = re.search(r'Abstract\s*\n(.*?)(?:\n|$)', text, re.DOTALL | re.IGNORECASE)
    
    if abstract_match:
        # 找到Abstract的位置
        abstract_start = abstract_match.start()
        title_text = text[:abstract_start].strip()
        # 取最后几行作为标题（去掉作者等信息）
        title_lines = title_text.split('\n')
        # 过滤掉空行和很短的行
        title_lines = [line.strip() for line in title_lines if len(line.strip()) > 10]
        if title_lines:
            title = title_lines[-1].strip()  # 取最后一行的非空内容
        
        # 提取摘要
        abstract = abstract_match.group(1).strip()
        # 清理摘要（去除多余空白）
        abstract = re.sub(r'\s+', ' ', abstract)
    else:
        # 如果没找到Abstract，使用前500字符作为标题
        title = text[:500].strip().split('\n')[0]
    
    return title, abstract


def search_pdf_for_keywords(pdf_path):
    """
    搜索PDF中的关键字，返回找到的关键字和上下文
    """
    if not os.path.exists(pdf_path):
        return None, []
    
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        # 提取所有页面的文本
        for page in doc:
            full_text += page.get_text() + "\n"
        
        doc.close()
        
        # 提取标题和摘要
        title, abstract = extract_title_and_abstract(full_text)
        
        # 搜索关键字
        found_keywords = []
        text_lower = full_text.lower()
        
        for keyword in KEYWORDS:
            if keyword.lower() in text_lower:
                # 找到所有匹配位置
                matches = [(m.start(), m.group()) for m in re.finditer(re.escape(keyword.lower()), text_lower)]
                
                for start_idx, match_text in matches:
                    # 获取上下文（前后100个字符）
                    context_start = max(0, start_idx - 100)
                    context_end = min(len(full_text), start_idx + len(keyword) + 100)
                    context = full_text[context_start:context_end].replace('\n', ' ')
                    
                    # 找到页码
                    page_num = 1
                    cumulative_len = 0
                    doc = fitz.open(pdf_path)
                    for page in doc:
                        page_text = page.get_text()
                        cumulative_len += len(page_text)
                        if cumulative_len > start_idx:
                            break
                        page_num += 1
                    doc.close()
                    
                    found_keywords.append({
                        'keyword': keyword,
                        'page': page_num,
                        'context': context
                    })
        
        if found_keywords:
            return {
                'title': title,
                'abstract': abstract,
                'keywords': found_keywords
            }, found_keywords
        
        return None, []
        
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return None, []


def generate_markdown(results, output_file):
    """
    生成markdown格式的报告
    """
    md_content = f"""# arXiv quant-ph 2026-03-02 论文代码/数据公开声明检索报告

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

共扫描PDF数量: {results['total_scanned']}
发现包含代码/数据公开声明的论文: {len(results['found'])}

---

"""
    
    if not results['found']:
        md_content += "未发现任何包含代码/数据公开声明的论文。\n"
    else:
        for i, paper in enumerate(results['found'], 1):
            md_content += f"""## {i}. {paper['title']}

**arXiv ID**: {paper['arxiv_id']}

### 摘要
{paper['abstract'][:500]}{'...' if len(paper['abstract']) > 500 else ''}

### 发现的声明

"""
            for kw in paper['keywords']:
                md_content += f"""- **关键字**: `{kw['keyword']}`
  - **页码**: 第{kw['page']}页
  - **上下文**: ...{kw['context']}...

"""

            md_content += "---\n\n"
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    return md_content


def main():
    # 配置
    pdf_folder = "arxiv_papers/arxiv_quant-ph_2026-03-02"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_dir = os.path.join(script_dir, pdf_folder)
    
    # 获取所有PDF文件
    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
    
    print(f"开始扫描 {len(pdf_files)} 个PDF文件...")
    
    results = {
        'total_scanned': len(pdf_files),
        'found': []
    }
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_dir, pdf_file)
        arxiv_id = pdf_file.replace('.pdf', '')
        
        print(f"处理: {arxiv_id}...", end=" ")
        
        result, found = search_pdf_for_keywords(pdf_path)
        
        if found:
            result['arxiv_id'] = arxiv_id
            results['found'].append(result)
            print(f"✓ 发现 {len(found)} 处声明")
        else:
            print("✗ 无")
    
    # 生成markdown报告
    today = datetime.now().strftime('%Y-%m-%d')
    output_file = os.path.join(script_dir, f"code_declaration_report_{today}.md")
    
    md_content = generate_markdown(results, output_file)
    
    print(f"\n扫描完成！")
    print(f"发现 {len(results['found'])} 篇包含代码/数据公开声明的论文")
    print(f"报告已保存到: {output_file}")
    
    # 打印摘要
    if results['found']:
        print("\n=== 发现列表 ===")
        for i, paper in enumerate(results['found'], 1):
            print(f"{i}. {paper['arxiv_id']}: {paper['title'][:60]}...")


if __name__ == "__main__":
    main()
