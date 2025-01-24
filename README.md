# CV Parser API

A FastAPI-based service that parses CVs/Resumes in PDF format and returns structured data based on formatting and layout characteristics.

## Setup and Installation

### Prerequisites

- Python 3.8+
- pip
- virtualenv or conda env (recommended)

### Installation Steps

```bash
# Create and activate virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Clone the repository
git clone https://github.com/yourusername/cv-parser-api

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload --port 8000
```

## Limitations and Complexity

## Usage

### 1. Interactive API Documentation (Swagger UI)

FastAPI provides automatic interactive API documentation:

1. Start the server and visit:

   - Swagger UI: `http://localhost:8000/docs`
   - Alternative docs: `http://localhost:8000/redoc`
2. Using Swagger UI:

   - Navigate to the `/parse-cv/` endpoint
   - Click "Try it out"
   - Upload your PDF file using the file selector
   - Click "Execute"
   - View the response below

### 2. API Endpoint Direct Usage

```python

import requests

# Upload and parse a CV
files = {'file': open('cv.pdf', 'rb')}

response = requests.post('http://localhost:8000/parse-cv/', files=files)

# Response structure
{
    "result": {
        "raw_text": ["..."],  # Original text in reading order (IF ENABLED)
        "data": [             # Structured hierarchical data
            {
                "depth": 1,
                "text": "Section Title",
                "content": [...]
            }
        ]
    }
}

```


## Limitations

1. **Layout Detection**

   - Relies heavily on font sizes and formatting
   - May misinterpret complex layouts or designs
   - Assumes consistent formatting for section headers
2. **Content Structure**

   - Cannot guarantee perfect section detection
   - May group or split sections incorrectly
   - Limited understanding of content semantics
3. **Performance**

   - Synchronous processing
   - Memory usage scales with PDF size
   - Rate limited to 10 requests per minute

### Complexity Analysis

1. **Time Complexity**

   - PDF Parsing: O(n) where n is the number of text elements
   - Layout Analysis: O(n log n) due to sorting operations
   - Section Detection: O(n)
   - Overall: O(n log n)
2. **Processing Steps**

   ```
   1. PDF Text Extraction
   2. Layout Analysis
   3. Font Size Collection
   4. Section Detection
   5. Content Grouping
   6. Structure Generation
   ```

### Future Improvements

1. **Robustness**

   - Enhanced layout detection
   - Better handling of inconsistent formatting
   - Support for more document types
2. **Performance**

   - Asynchronous processing
3. **Features**

   - Smarter way for detecting structure (Maybe OCR?)


## Possible Implementation of State Management

  1.**Job Management Flow**

    Upload PDF → Get Job ID → Check Status → Retrieve Results

2. **Endpoints**

```python
POST /jobs/ # Upload PDF, returns job_id
GET /jobs/{job_id} # Check job status
GET /jobs/{job_id}/result # Get processing results
```

3. **Job States**PENDING → PROCESSING → COMPLETED/FAILED


### Implementation Components

1. **Storage Layer**

   - **Job Metadata Storage** (Redis/PostgreSQL)
     ```json
     {
         "job_id": "uuid",
         "status": "PROCESSING",
         "created_at": "timestamp",
         "updated_at": "timestamp",
         "result": null,
         "error": null
     }
     ```
   - **File Storage** (S3/Local)
     - Store uploaded PDFs
     - Store processing results
2. **Processing Queue**

   - Message queue (Redis/RabbitMQ)
   - Worker processes
   - Retry mechanism

### Considerations

1. **Data Management**

   - Job expiration/cleanup
   - Result caching
   - Storage optimization
2. **Error Handling**

   - Retry policies
   - Error reporting
   - Client notification
3. **Security**

   - Job ID generation (UUID)
   - Access control
   - Rate limiting


## Rate Limiting

- 10 requests per minute per IP address
- Returns 429 status code when exceeded

## Error Handling

```json
{
    "400": "Invalid or empty PDF file",
    "429": "Rate limit exceeded",
    "500": "Internal processing error"
}
```

## Security Notes

### CORS Configuration

The current CORS configuration allows all origins, methods, and headers:

```python

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

```

⚠️ **Warning**: This configuration is for development purposes only. For production:

- Specify exact allowed origins
- Limit allowed methods
- Define specific allowed headers
- Consider security implications

Example of production CORS settings:

```python

app.add_middleware(

    CORSMiddleware,

    allow_origins=["https://example-frontend-domain.com"],

    allow_credentials=True,

    allow_methods=["POST", "GET"],

    allow_headers=["Content-Type", "Authorization"],

)

```


## Design Philosophy

### Simplicity Over Complexity

The parser follows a minimalist approach focusing on two key structural levels:

1.**Headers (depth: 1)**

- Main sections of the document
- Detected through multiple formatting characteristics:

  - Text in uppercase OR
  - Font size significantly larger than document average (≥ avg + 0.7) AND
  - Short text (≤ 2 words) AND
  - Not ending with sentence punctuation (., ,)
- Examples: "SKILLS", "EDUCATION", "EXPERIENCE"

2.**Content (depth: 2)**

- Information under each header
- Regular text and details
- Examples: skill lists, job descriptions, education details

### Why Two Levels?

While the system was initially designed to support multiple depth levels based on font sizes, this was simplified to two levels because:

1.**Practical Usage**

- Most CVs naturally follow a two-level structure
- Headers → Content organization is most common
- Deeper nesting rarely adds value

2.**Reliability**

- Font-based depth detection can be unreliable
- Simpler structure means more consistent results
- Reduces false positives in section detection

3.**Maintainability**

- Clearer, more predictable output structure
- Easier to process downstream
- More stable across different CV formats



## License

MIT License - See LICENSE file for details
