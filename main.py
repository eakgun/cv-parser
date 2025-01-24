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
    Process CV text using pdfminer based purely on formatting and layout.
    Using the same order as raw text extraction.
    """
    # First get the raw text in correct order
    raw_text = extract_raw_text(pdf_file)
    
    # Reset file pointer
    pdf_file.seek(0)
    
    # Collect font sizes for each text element
    text_properties = {}
    for page_layout in extract_pages(pdf_file):
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    if isinstance(text_line, LTTextLineHorizontal):
                        chars = [char for char in text_line if isinstance(char, LTChar)]
                        if chars:
                            text = text_line.get_text().strip()
                            if text and not re.match(r'^Page \d+ of \d+$', text):
                                size = mean(char.size for char in chars)
                                text_properties[text] = size
    
    if not text_properties:
        return []
    
    # Calculate average font size
    avg_font_size = mean(text_properties.values())
    
    def is_header(text: str) -> bool:
        """Determine if text is likely a header based only on formatting"""
        font_size = text_properties.get(text, avg_font_size)
        return (
            text.isupper() or  # All caps text
            (
                font_size >= avg_font_size + 0.7 and  # Font size threshold
                len(text.split()) <= 2 and            # Word count threshold
                not text.endswith(('.', ','))         # Not a sentence
            )
        )
    
    sections = []
    current_section = None
    buffer = []
    
    # Process text in the original order
    for text in raw_text:
        # Handle the name (first text)
        if not sections:
            sections.append({
                "depth": 1,
                "text": text
            })
            continue
        
        # Handle section headers
        if is_header(text):
            # Process any buffered content before starting new section
            if buffer and current_section:
                if "content" not in current_section:
                    current_section["content"] = []
                current_section["content"].append({
                    "depth": current_section["depth"] + 1,
                    "text": " ".join(buffer)
                })
                buffer = []
            
            # Create new section
            current_section = {
                "depth": 1,
                "text": text
            }
            sections.append(current_section)
        else:
            # Add to buffer for regular content
            buffer.append(text)
    
    # Process any remaining buffer
    if buffer and current_section:
        if "content" not in current_section:
            current_section["content"] = []
        current_section["content"].append({
            "depth": current_section["depth"] + 1,
            "text": " ".join(buffer)
        })
    
    return sections

def extract_raw_text(pdf_file) -> List[str]:
    """Extract raw text from PDF with layout consideration."""
    raw_text = []
    
    for page_layout in extract_pages(pdf_file):
        # Group text elements by their vertical position
        elements = []
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                y_pos = element.y1  # top position
                x_pos = element.x0  # left position
                
                for text_line in element:
                    if isinstance(text_line, LTTextLineHorizontal):
                        text = text_line.get_text().strip()
                        if text and not re.match(r'^Page \d+ of \d+$', text):
                            elements.append((y_pos, x_pos, text))
        
        # Sort by vertical position first (top to bottom), then horizontal (left to right)
        elements.sort(key=lambda x: (-x[0], x[1]))
        
        # Add sorted text to raw_text
        for _, _, text in elements:
            raw_text.append(text)
    
    return raw_text

@app.post("/parse-cv/")
@limiter.limit("10/minute")
async def parse_cv(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """
    Parse uploaded CV/Resume PDF and return both raw and structured JSON.
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
        
        # Get raw text
        raw_text = extract_raw_text(pdf_file)
        
        # Reset file pointer for processing
        pdf_file.seek(0)
        
        # Process PDF using pdfminer
        structured_data = process_text_with_pdfminer(pdf_file)
        
        # Return both raw and structured data
        return JSONResponse(content={
            "result": {
                #"raw_text": raw_text, # Uncomment to return raw text FOR DEBUGGING
                "data": structured_data
            }
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {"message": "CV Parser API - Upload your CV/Resume PDF to /parse-cv/ endpoint"}
