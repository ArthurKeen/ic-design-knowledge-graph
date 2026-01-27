"""
Document conversion utilities for GraphRAG import

Supports conversion of PDF documents to Markdown using
Docling or pymupdf4llm for GraphRAG ingestion.

Usage:
    from document_converter import DocumentConverter
    
    # Use pymupdf (faster)
    converter = DocumentConverter(method='pymupdf')
    markdown_text = converter.convert('document.pdf')
    
    # Use docling (more accurate)
    converter = DocumentConverter(method='docling')
    markdown_text = converter.convert('document.pdf')
"""

import os
import logging
from typing import Optional, Literal, List
from pathlib import Path

class DocumentConverter:
    """Convert documents to Markdown for GraphRAG import"""
    
    def __init__(self, method: Literal['docling', 'pymupdf'] = 'pymupdf'):
        """
        Initialize document converter
        
        Args:
            method: Conversion method ('docling' for accuracy, 'pymupdf' for speed)
        """
        self.method = method
        self.logger = logging.getLogger(__name__)
        
        # Lazy import dependencies based on method
        if method == 'docling':
            try:
                from docling.document_converter import DocumentConverter as DoclingConverter
                self.docling_converter = DoclingConverter()
            except ImportError:
                self.logger.error("Docling not installed. Install with: pip install docling==2.26.0")
                raise
        elif method == 'pymupdf':
            try:
                import pymupdf4llm
                self.pymupdf = pymupdf4llm
            except ImportError:
                self.logger.error("pymupdf4llm not installed. Install with: pip install pymupdf4llm")
                raise
        else:
            raise ValueError(f"Unknown conversion method: {method}. Use 'docling' or 'pymupdf'")
            
    def pdf_to_markdown_docling(self, pdf_path: str) -> str:
        """
        Convert PDF using Docling (more accurate, preserves structure)
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Markdown content as string
        """
        try:
            self.logger.info(f"Converting {pdf_path} using Docling...")
            result = self.docling_converter.convert(pdf_path)
            markdown_content = result.document.export_to_markdown()
            self.logger.info(f"✓ Converted {pdf_path} ({len(markdown_content)} chars)")
            return markdown_content
            
        except Exception as e:
            self.logger.error(f"Docling conversion failed for {pdf_path}: {e}")
            raise
            
    def pdf_to_markdown_pymupdf(self, pdf_path: str, page_chunks: bool = False) -> str:
        """
        Convert PDF using pymupdf4llm (faster, good quality)
        
        Args:
            pdf_path: Path to PDF file
            page_chunks: If True, returns page-by-page chunks; if False, single document
            
        Returns:
            Markdown content as string
        """
        try:
            self.logger.info(f"Converting {pdf_path} using pymupdf4llm...")
            chunks = self.pymupdf.to_markdown(pdf_path, page_chunks=page_chunks)
            
            # Handle chunked vs continuous output
            if isinstance(chunks, list):
                # Page chunks - combine with page headers
                markdown_content = "\n\n".join([
                    f"## Page {i}\n\n{chunk}" 
                    for i, chunk in enumerate(chunks, 1)
                ])
            else:
                # Single continuous markdown
                markdown_content = chunks
                
            self.logger.info(f"✓ Converted {pdf_path} ({len(markdown_content)} chars)")
            return markdown_content
            
        except Exception as e:
            self.logger.error(f"pymupdf4llm conversion failed for {pdf_path}: {e}")
            raise
            
    def convert(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert PDF to markdown using configured method
        
        Args:
            pdf_path: Path to PDF file
            output_path: Optional path to save markdown file (if None, only returns string)
            
        Returns:
            Markdown content as string
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        # Convert based on method
        if self.method == 'docling':
            markdown_content = self.pdf_to_markdown_docling(pdf_path)
        else:  # pymupdf
            markdown_content = self.pdf_to_markdown_pymupdf(pdf_path)
            
        # Optionally save to file
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                self.logger.info(f"✓ Saved markdown to: {output_path}")
            except Exception as e:
                self.logger.error(f"Failed to save markdown to {output_path}: {e}")
                raise
                
        return markdown_content
        
    def convert_directory(self, 
                         input_dir: str, 
                         output_dir: str, 
                         pattern: str = "*.pdf") -> List[str]:
        """
        Convert all PDF files in a directory
        
        Args:
            input_dir: Directory containing PDF files
            output_dir: Directory to save markdown files
            pattern: Glob pattern for matching files (default: "*.pdf")
            
        Returns:
            List of output markdown file paths
        """
        from pathlib import Path
        import glob
        
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        pdf_files = list(input_path.glob(pattern))
        self.logger.info(f"Found {len(pdf_files)} PDF files in {input_dir}")
        
        output_files = []
        for pdf_file in pdf_files:
            # Generate output filename
            output_file = output_path / f"{pdf_file.stem}.md"
            
            try:
                self.convert(str(pdf_file), str(output_file))
                output_files.append(str(output_file))
            except Exception as e:
                self.logger.error(f"Failed to convert {pdf_file}: {e}")
                continue
                
        self.logger.info(f"✓ Converted {len(output_files)}/{len(pdf_files)} files")
        return output_files


def convert_or1200_docs(output_dir: str = "./markdown_output", 
                        method: Literal['docling', 'pymupdf'] = 'pymupdf') -> List[str]:
    """
    Convenience function to convert all OR1200 documentation PDFs
    
    Args:
        output_dir: Directory to save markdown files
        method: Conversion method
        
    Returns:
        List of converted markdown file paths
    """
    from config import OR1200_DOCS
    
    converter = DocumentConverter(method=method)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_files = []
    for pdf_path in OR1200_DOCS:
        if not os.path.exists(pdf_path):
            logging.warning(f"PDF not found: {pdf_path}")
            continue
            
        output_file = output_path / f"{Path(pdf_path).stem}.md"
        try:
            converter.convert(pdf_path, str(output_file))
            output_files.append(str(output_file))
        except Exception as e:
            logging.error(f"Failed to convert {pdf_path}: {e}")
            
    return output_files
