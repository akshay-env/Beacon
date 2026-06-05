import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from pathlib import Path

def load_docs(docs_path: str, extensions: list[str] = [".md", ".pdf", ".html"]) -> list[dict]:
    docs = []
    path = Path(docs_path)
    
    for ext in extensions:
        for file in path.rglob(f"*{ext}"):
            try:
                text = ""
                
                if ext == ".md":
                    text = file.read_text(encoding="utf-8", errors="ignore")
                    
                elif ext == ".pdf":
                    with fitz.open(str(file)) as pdf:
                        # Extract text from all pages
                        text = "\n\n".join(page.get_text() for page in pdf)
                        
                elif ext == ".html":
                    html_content = file.read_text(encoding="utf-8", errors="ignore")
                    soup = BeautifulSoup(html_content, "html.parser")
                    # Extract text, separate block elements with newlines, and strip whitespace
                    text = soup.get_text(separator="\n\n", strip=True)
                
                if text.strip():  # skip empty files
                    docs.append({
                        "text": text,
                        "source": str(file)
                    })
            except Exception as e:
                print(f"Skipping {file}: {e}")
    
    print(f"Loaded {len(docs)} documents")
    return docs