"""
File content extractor: downloads files from DIAL storage and extracts text based on file type.
Supports: TXT, PDF (text only), CSV (as markdown), HTML/HTM.
"""
import io
from pathlib import Path

import pdfplumber
import pandas as pd
from aidial_client import Dial
from bs4 import BeautifulSoup


class DialFileContentExtractor:
    """
    Extracts text content from files stored in DIAL file storage.
    
    Supported formats:
    - TXT: Plain text decode
    - PDF: Text extraction via pdfplumber (text-based PDFs only)
    - CSV: Converted to markdown table via pandas
    - HTML/HTM: Text extraction via BeautifulSoup (strips scripts/styles)
    - Others: Fallback to UTF-8 decode
    
    External I/O:
    - Downloads files from DIAL storage via HTTP
    """

    def __init__(self, endpoint: str, api_key: str):
        """
        Initialize extractor with DIAL client.
        
        Args:
            endpoint: DIAL Core endpoint (e.g., http://localhost:8080)
            api_key: Per-request API key for file access
        """
        # Create DIAL client for file downloads
        self.client = Dial(base_url=endpoint, api_key=api_key)

    def extract_text(self, file_url: str) -> str:
        """
        Download file from DIAL storage and extract text content.
        
        Flow:
        1. Download file from DIAL storage (files.download)
        2. Detect file extension from filename
        3. Delegate to format-specific extractor
        
        Args:
            file_url: DIAL file URL (e.g., files/appdata/report.csv)
        
        Returns:
            Extracted text content (or error message if failed)
        
        External I/O:
            - HTTP download from DIAL file storage
        """
        # Download file from DIAL storage
        downloaded_file = self.client.files.download(file_url)
        
        # Extract filename and content from response
        filename = downloaded_file.filename
        content = downloaded_file.content
        
        # Detect file extension (lowercase for case-insensitive matching)
        file_extension = Path(filename).suffix.lower()
        
        # Delegate to format-specific extractor
        return self.__extract_text(content, file_extension, filename)

    def __extract_text(self, file_content: bytes, file_extension: str, filename: str) -> str:
        """
        Extract text content based on file type.
        
        Supported formats:
        - .txt: UTF-8 decode (ignore errors)
        - .pdf: pdfplumber text extraction (text-based PDFs only)
        - .csv: Pandas → markdown table
        - .html/.htm: BeautifulSoup text extraction (strips scripts/styles)
        - Default: UTF-8 decode fallback
        
        Args:
            file_content: Raw file bytes
            file_extension: File extension (e.g., '.pdf', '.csv')
            filename: Original filename (for error logging)
        
        Returns:
            Extracted text content (empty string on error)
        
        Error handling:
            All exceptions caught, logged, and return empty string
        """
        try:
            # Plain text files
            if file_extension == '.txt':
                return file_content.decode('utf-8', errors='ignore')
            
            # PDF files (text-based only, no OCR)
            elif file_extension == '.pdf':
                # Load PDF from bytes
                pdf_bytes = io.BytesIO(file_content)
                
                # Extract text from all pages
                with pdfplumber.open(pdf_bytes) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            pages_text.append(page_text)
                    
                    # Join all pages with newlines
                    return '\n'.join(pages_text)
            
            # CSV files → markdown table
            elif file_extension == '.csv':
                # Decode CSV content
                decoded_content = file_content.decode('utf-8', errors='ignore')
                
                # Read CSV via pandas
                csv_buffer = io.StringIO(decoded_content)
                df = pd.read_csv(csv_buffer)
                
                # Convert to markdown table (without index column)
                return df.to_markdown(index=False)
            
            # HTML files → text extraction
            elif file_extension in ['.html', '.htm']:
                # Decode HTML content
                decoded_content = file_content.decode('utf-8', errors='ignore')
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(decoded_content, features='html.parser')
                
                # Remove script and style elements (they're not readable text)
                for element in soup(["script", "style"]):
                    element.decompose()
                
                # Extract text with newline separators
                return soup.get_text(separator='\n', strip=True)
            
            # Fallback: try UTF-8 decode for unknown file types
            else:
                return file_content.decode('utf-8', errors='ignore')
        
        except Exception as e:
            # Log error and return empty string (tool will handle error messaging)
            print(f"⚠️ Error extracting text from {filename} ({file_extension}): {e}")
            return ""
