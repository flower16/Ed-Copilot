import os
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

# Determine the absolute paths dynamically
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, 'chroma_db')

class WakeCountyRetriever:
    def __init__(self):
        print("Loading Chroma DB...")
        embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        self.vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
        
        print("Initializing BM25 Retriever from Chroma documents...")
        all_docs_data = self.vectorstore.get()
        docs = []
        if all_docs_data['documents']:
            for doc_text, doc_metadata in zip(all_docs_data['documents'], all_docs_data['metadatas']):
                docs.append(Document(page_content=doc_text, metadata=doc_metadata))
                
        self.bm25_retriever = BM25Retriever.from_documents(docs)
        self.bm25_retriever.k = 10
        
        print("Loading Cross-Encoder for Reranking...")
        self.cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    def invoke(self, query: str, top_k: int = 4) -> list[Document]:
        # 1. Retrieve from both
        dense_docs = self.vectorstore.similarity_search(query, k=10)
        sparse_docs = self.bm25_retriever.invoke(query)
        
        # 2. Reciprocal Rank Fusion (RRF)
        doc_map = {}
        for rank, doc in enumerate(dense_docs):
            doc_map[doc.page_content] = doc_map.get(doc.page_content, 0) + 1.0 / (rank + 60)
        for rank, doc in enumerate(sparse_docs):
            doc_map[doc.page_content] = doc_map.get(doc.page_content, 0) + 1.0 / (rank + 60)
            
        # Sort by RRF score and take top 10 unique docs for reranking
        sorted_rrf = sorted(doc_map.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Rebuild Document objects for the top 10
        # (We can find the original metadata by searching the original lists)
        all_retrieved = dense_docs + sparse_docs
        content_to_meta = {d.page_content: d.metadata for d in all_retrieved}
        
        candidates = []
        for content, _ in sorted_rrf:
            candidates.append(Document(page_content=content, metadata=content_to_meta[content]))
            
        # 3. Cross-Encoder Reranking
        pairs = [[query, doc.page_content] for doc in candidates]
        scores = self.cross_encoder.predict(pairs)
        
        for doc, score in zip(candidates, scores):
            doc.metadata["rerank_score"] = float(score)
            
        candidates.sort(key=lambda x: x.metadata["rerank_score"], reverse=True)
        return candidates[:top_k]

def get_hybrid_retriever():
    return WakeCountyRetriever()

if __name__ == "__main__":
    retriever = get_hybrid_retriever()
    
    query = "What is NC.M3.F-IF.4 about?"
    print(f"\n--- Testing Retrieval Pipeline ---")
    print(f"Query: '{query}'")
    
    results = retriever.invoke(query)
    
    for i, doc in enumerate(results):
        print(f"\n--- Result {i+1} ---")
        print(f"Course: {doc.metadata.get('course_id')}")
        print(f"Standard: {doc.metadata.get('standard_id')}")
        print(f"Text Snippet: {doc.page_content[:200]}...")
