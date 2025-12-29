import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# Paths
DATA_DIR = "data"
DB_DIR = "chroma_db"

def load_pdfs():
    documents = []
    for file in os.listdir(DATA_DIR):
        if file.endswith(".pdf"):
            loader = PyPDFLoader(os.path.join(DATA_DIR, file))
            documents.extend(loader.load())
    return documents

def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )
    return splitter.split_documents(documents)

def build_vector_db(chunks):
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=DB_DIR
    )

    return vectordb

if __name__ == "__main__":
    print("Loading PDFs...")
    docs = load_pdfs()
    print(f"Loaded {len(docs)} pages")

    print("Splitting documents...")
    chunks = split_documents(docs)
    print(f"Created {len(chunks)} chunks")

    print("Building vector database...")
    db = build_vector_db(chunks)

    print("✅ Phase-1 Vector DB Ready")
