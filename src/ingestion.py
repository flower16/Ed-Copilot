import os
import re
import sys
import fitz  # PyMuPDF
from typing import List, Dict
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

# Load environment variables
load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DB_DIR = os.path.join(os.path.dirname(DATA_DIR), 'chroma_db')
# Must match the collection the Wake County agent reads (see src/agents/wake_county_agent.py).
COLLECTION_NAME = "nc_math_standards"

def get_indexed_sources(db_dir: str) -> set:
    """
    Checks Chroma DB to find the set of PDF filenames that have already been indexed.
    """
    if not os.path.exists(db_dir):
        return set()
    try:
        print("Checking already indexed files in Chroma DB...")
        embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        vectorstore = Chroma(collection_name=COLLECTION_NAME, persist_directory=db_dir, embedding_function=embeddings)
        data = vectorstore.get()
        if data and 'metadatas' in data and data['metadatas']:
            sources = set(m.get('source') for m in data['metadatas'] if m.get('source'))
            return sources
    except Exception as e:
        print(f"Warning: Could not read existing Chroma DB sources: {e}")
    return set()

def parse_pdfs(data_dir: str, indexed_sources: set = None) -> List[Dict]:
    """
    Reads PDFs from the data directory and extracts text.
    Skips any PDF that matches a filename in `indexed_sources`.
    Returns a list of dictionaries with page-level text and metadata.
    """
    raw_documents = []
    if indexed_sources is None:
        indexed_sources = set()
        
    for filename in os.listdir(data_dir):
        if not filename.endswith('.pdf'):
            continue
            
        if filename in indexed_sources:
            print(f"Skipping (Already Indexed): {filename}")
            continue
            
        file_path = os.path.join(data_dir, filename)
        course_match = re.search(r'Math (\d)', filename)
        course_id = f"M{course_match.group(1)}" if course_match else "Unknown"
        
        print(f"Parsing: {filename} (Course: {course_id})")
        doc = fitz.open(file_path)
        
        full_text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            full_text += text + "\n"
            
        raw_documents.append({
            "text": full_text,
            "metadata": {
                "course_id": course_id,
                "source": filename
            }
        })
        
    return raw_documents

def chunk_by_standard(raw_documents: List[Dict]) -> List[Dict]:
    """
    Splits the full text of the PDFs into semantic chunks based on the NC Math standard IDs.
    Example standard ID: NC.M1.A-APR.1 or NC.M3.F-IF.4
    """
    chunks = []
    # Regex to match the NC Math Standard pattern
    # e.g. NC.M1.N-RN.1 or NC.M3.F-TF.2
    standard_pattern = re.compile(r'(NC\.M[1-3]\.[A-Z]+-[A-Z]+\.\d+[a-z]?)')
    
    for doc in raw_documents:
        text = doc["text"]
        metadata = doc["metadata"]
        
        # Find all occurrences of standard IDs
        matches = list(standard_pattern.finditer(text))
        
        if not matches:
            print(f"Warning: No standards found in {metadata['source']}")
            continue
            
        for i in range(len(matches)):
            start_idx = matches[i].start()
            # The chunk ends where the next standard begins, or at the end of the document
            end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            chunk_text = text[start_idx:end_idx].strip()
            standard_id = matches[i].group(1)
            
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    "course_id": metadata["course_id"],
                    "standard_id": standard_id,
                    "source": metadata["source"]
                }
            })
            
    return chunks

def index_to_chroma(chunks: List[Dict]):
    print("\nInitializing embedding model (BAAI/bge-small-en-v1.5)...")
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    
    docs = []
    for chunk in chunks:
        docs.append(Document(
            page_content=chunk["text"],
            metadata=chunk["metadata"]
        ))
        
    if os.path.exists(DB_DIR):
        print(f"Chroma DB exists. Appending {len(docs)} new chunks to {DB_DIR}...")
        vectorstore = Chroma(collection_name=COLLECTION_NAME, persist_directory=DB_DIR, embedding_function=embeddings)
        vectorstore.add_documents(docs)
    else:
        print(f"Creating new Chroma DB and indexing {len(docs)} chunks at {DB_DIR}...")
        vectorstore = Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=DB_DIR
        )
    print("Vector DB indexing complete!")

if __name__ == "__main__":
    print("--- Starting Incremental Data Ingestion Pipeline ---")
    
    # 1. Fetch list of already indexed sources
    indexed_sources = get_indexed_sources(DB_DIR)
    if indexed_sources:
        print(f"Found {len(indexed_sources)} already indexed file(s) in vector DB: {list(indexed_sources)}")
    
    # 2. Parse only new PDFs
    raw_docs = parse_pdfs(DATA_DIR, indexed_sources=indexed_sources)
    
    if not raw_docs:
        print("\nNo new PDF files found. Vector DB is up to date!")
        sys.exit(0)
        
    # 3. Chunk the new documents
    print("\n--- Chunking by Standard ---")
    chunks = chunk_by_standard(raw_docs)
    print(f"\nNew chunks generated: {len(chunks)}")
    
    # Print sample chunk
    if chunks:
        print("\n--- Sample New Chunk ---")
        sample = chunks[0]
        print(f"Course: {sample['metadata']['course_id']}")
        print(f"Standard ID: {sample['metadata']['standard_id']}")
        print(f"Text Preview: {sample['text'][:300]}...\n")
        
    # 4. Append to Chroma DB
    index_to_chroma(chunks)
