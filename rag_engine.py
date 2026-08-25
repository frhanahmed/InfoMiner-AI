import os
import re
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from dotenv import load_dotenv
from groq import Groq
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents import Document

load_dotenv()

_embeddings = None

# This will generate the embeddings for the data
def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    return _embeddings

# This will help to extract the URLs from the prompt or message from which answers will be found
def extract_urls_from_text(text: str):
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    return re.findall(url_pattern, text)


# This will help to extract and store information from PDF or URLs 
# depending upon the source of information into LangChain Document Object

def extract_data_from_sources(uploaded_files, urls):
    docs = []

    # For PDFs
    if uploaded_files:
        for file in uploaded_files:
            pdf_reader = PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                if text:
                    docs.append(Document(page_content=text,metadata={"source": f"📄 PDF: {file.name}", "page": page_num}))

    # For URLs
    if urls:
        for url in urls:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, "html.parser")
                    for elem in soup(["script", "style", "nav", "footer", "header"]):
                        elem.decompose()
                    clean_text = " ".join(soup.stripped_strings)
                    docs.append(Document(page_content=clean_text,metadata={"source": f"🔗 Link: {url}", "page": "Web"}))
            except Exception as e:
                print(f"Error scraping {url}: {e}")
    return docs

# Converts documents into embeddings and indexes/stores them into FAISS(Vector Database used here)
def add_to_vector_store(docs, existing_vector_store=None):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=750, chunk_overlap=100)
    chunks = text_splitter.split_documents(docs)
    embeddings = get_embeddings()

    if existing_vector_store is None:
        return FAISS.from_documents(chunks, embeddings)
    else:
        existing_vector_store.add_documents(chunks)
        return existing_vector_store

# Queries vector DB and yields/returns relevant token chunks via Groq(API used here for free of cost) streaming.
def query_rag_chat_stream(vector_store, chat_history, user_message: str):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set.")

    context_str = ""
    sources_used = set()

    if vector_store is not None:
        relevant_chunks = vector_store.similarity_search(user_message, k=4)
        for chunk in relevant_chunks:
            src = f"{chunk.metadata['source']} (Page {chunk.metadata['page']})"
            sources_used.add(src)
            context_str += f"\n---\n[Source: {src}]\n{chunk.page_content}\n"

    system_instruction = (
        "You are InfoMiner-AI, an intelligent conversational research assistant. "
        "Answer the user's questions or execute their prompts using the provided context. "
        "If document/link context is provided, cite the exact sources used at the end of your response. "
        "If no context exists, answer conversationally."
    )

    messages = [{"role": "system", "content": system_instruction}]
    for msg in chat_history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"Context:\n{context_str}\n\nPrompt: {user_message}" if context_str else user_message
    })

    client = Groq(api_key=api_key)
    stream_response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=messages,
        temperature=0.3,
        stream=True
    )

    # This function will generate the answer as a stream
    def response_generator():
        for chunk in stream_response:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    return response_generator()