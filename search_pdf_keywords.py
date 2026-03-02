"""
PDF Keyword Scanner Utility
使用pymupdf (fitz)检索PDF中的关键字（github, repository, zenodo）
"""

import fitz  # pymupdf
import os
import re


def search_pdf_for_keywords(pdf_path, keywords):
    """
    Search for keywords in a PDF and print context snippets.
    
    Args:
        pdf_path: Path to the PDF file
        keywords: List of keywords to search for
    """
    # 1. Validation: Check if file exists
    if not os.path.exists(pdf_path):
        print(f"Error: The file '{pdf_path}' was not found in the current directory.")
        return

    print(f"--- Starting Analysis of {pdf_path} ---")
    print(f"Searching for keywords: {', '.join(keywords)}\n")

    found_any = False
    
    try:
        # 2. Open Document
        doc = fitz.open(pdf_path)
        
        # 3. Iterate Pages
        for page_num, page in enumerate(doc):
            # Extract text
            text = page.get_text()
            
            # Normalize text for case-insensitive search
            text_lower = text.lower()
            
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    found_any = True
                    
                    # 4. Context Reporting
                    # Find all start indices of the keyword
                    matches = [m.start() for m in re.finditer(re.escape(keyword.lower()), text_lower)]
                    
                    for start_idx in matches:
                        end_idx = start_idx + len(keyword)
                        
                        # Grab context (50 chars before and after)
                        context_start = max(0, start_idx - 50)
                        context_end = min(len(text), end_idx + 50)
                        
                        snippet = text[context_start:context_end].replace('\n', ' ')
                        
                        print(f"[FOUND] '{keyword}' on Page {page_num + 1}")
                        print(f"Context: ...{snippet}...\n")

        doc.close()

        if not found_any:
            print("No keywords were found in the document.")
        else:
            print("--- Analysis Complete ---")

    except Exception as e:
        print(f"An error occurred while processing the PDF: {e}")


if __name__ == "__main__":
    # Configuration
    TARGET_FILE = "arxiv_papers/arxiv_quant-ph_2026-03-02/2602.24152.pdf"
    SEARCH_TERMS = ["github", "repository", "zenodo"]
    
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(script_dir, TARGET_FILE)
    
    # Execution
    search_pdf_for_keywords(pdf_path, SEARCH_TERMS)
