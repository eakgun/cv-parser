from fastapi import FastAPI, UploadFile, HTTPException, Request, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import io
import re
from typing import List, Dict, Any, Tuple
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTLine, LTTextLineHorizontal
from statistics import mean




# Initialize FastAPI app
app = FastAPI(title="CV Parser API")

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def process_text_with_pdfminer(pdf_file) -> Dict[str, Any]:
    """
    Process CV text using pdfminer for better structure detection based on font sizes and positioning.
    Supports arbitrary depth levels based on font size hierarchy.
    """
    result = {"depth": 0, "text": "CV/Resume", "content": []}
    
    # Track font sizes and their frequencies
    font_sizes = []
    current_sections = {}  # Dictionary to track current section at each depth
    buffer = []
    
    # First pass: collect all font sizes and their frequencies
    font_size_freq = {}
    for page_layout in extract_pages(pdf_file):
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    if isinstance(text_line, LTTextLineHorizontal):
                        chars = [char for char in text_line if isinstance(char, LTChar)]
                        if chars:
                            size = mean(char.size for char in chars)
                            font_sizes.append(size)
                            font_size_freq[size] = font_size_freq.get(size, 0) + 1
    
    if not font_sizes:
        return result
    
    # Group similar font sizes together (within 0.5 point difference)
    grouped_sizes = {}
    for size in sorted(font_size_freq.keys(), reverse=True):
        found_group = False
        for group_size in grouped_sizes:
            if abs(size - group_size) < 0.5:
                grouped_sizes[group_size] += font_size_freq[size]
                found_group = True
                break
        if not found_group:
            grouped_sizes[size] = font_size_freq[size]
    
    # Create depth mapping for significant font sizes (used more than once)
    significant_sizes = sorted(
        [size for size, freq in grouped_sizes.items() if freq > 1],
        reverse=True
    )
    font_size_to_depth = {size: idx + 1 for idx, size in enumerate(significant_sizes)}
    
    def get_depth(font_size: float) -> int:
        """Determine depth level based on closest significant font size"""
        if not font_size_to_depth:
            return 1
        return min(font_size_to_depth.items(), key=lambda x: abs(x[0] - font_size))[1]
    
    def add_buffered_content(up_to_depth: int):
        """Add buffered content to the appropriate section"""
        if not buffer:
            return
            
        text = " ".join(buffer).strip()
        if not text:
            buffer.clear()
            return
            
        content = {
            "depth": up_to_depth + 1,
            "text": text
        }
        
        if up_to_depth in current_sections:
            if "content" not in current_sections[up_to_depth]:
                current_sections[up_to_depth]["content"] = []
            current_sections[up_to_depth]["content"].append(content)
        buffer.clear()
    
    # Process text with font size information
    for page_layout in extract_pages(pdf_file):
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    if isinstance(text_line, LTTextLineHorizontal):
                        chars = [char for char in text_line if isinstance(char, LTChar)]
                        if not chars:
                            continue
                            
                        text = text_line.get_text().strip()
                        if not text or re.match(r'^Page \d+ of \d+$', text):
                            continue
                        
                        # Get font characteristics
                        line_font_size = mean(char.size for char in chars)
                        current_depth = get_depth(line_font_size)
                        
                        # Check if this looks like a header
                        is_header = (
                            len(text.split()) <= 5 and  # Short text
                            text[0].isupper() and       # Starts with uppercase
                            not text.endswith('.') and  # Doesn't end with period
                            not any(char.isdigit() for char in text[:2])  # Doesn't start with number
                        )
                        
                        # Special handling for the first large text (usually name)
                        if current_depth == 1 and not result["content"]:
                            result["content"].append({
                                "depth": current_depth,
                                "text": text,
                                "content": []
                            })
                            continue
                        
                        # If this is a header, start a new section
                        if is_header:
                            # Process any buffered content before starting new section
                            if current_sections:
                                add_buffered_content(max(current_sections.keys()))
                            
                            # Clear out any deeper sections
                            current_sections = {k: v for k, v in current_sections.items() if k < current_depth}
                            
                            # Create new section
                            new_section = {
                                "depth": current_depth,
                                "text": text,
                                "content": []
                            }
                            
                            # Add to appropriate parent
                            if current_depth == 1:
                                result["content"].append(new_section)
                            else:
                                parent_depth = max((k for k in current_sections.keys() if k < current_depth), default=0)
                                if parent_depth in current_sections:
                                    if "content" not in current_sections[parent_depth]:
                                        current_sections[parent_depth]["content"] = []
                                    current_sections[parent_depth]["content"].append(new_section)
                            
                            current_sections[current_depth] = new_section
                        else:
                            # Add to buffer for regular content
                            buffer.append(text)
    
    # Process any remaining buffer
    if buffer and current_sections:
        add_buffered_content(max(current_sections.keys()))
    
    return result

@app.post("/parse-cv/")
@limiter.limit("10/minute")
async def parse_cv(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """
    Parse uploaded CV/Resume PDF and return structured JSON.
    Rate limited to 10 requests per minute.
    """
    # Validate file existence
    if not file:
        raise HTTPException(status_code=400, detail="Error:No file uploaded")
        
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Error: file is not a PDF")
    
    try:
        # Read the uploaded file
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Error:Empty file uploaded")
            
        pdf_file = io.BytesIO(content)
        
        # Process PDF using pdfminer
        structured_data = process_text_with_pdfminer(pdf_file)
        
        return JSONResponse(content={"result": structured_data})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {"message": "CV Parser API - Upload your CV/Resume PDF to /parse-cv/ endpoint"}
