"""
===============================================================================
🎓 MINDMATE AI: MISTRAL RAG & CHATBOT ENGINE
===============================================================================
This module handles:
  1. Chunking and parsing of responses.json & templates/faq.html
  2. Embeddings Vector Store using Mistral Embedding API (mistral-embed)
  3. Local caching of embeddings (rag_embeddings.pickle) for fast startup
  4. Context retrieval and Mistral Reranker (mistral-rerank-latest)
  5. JSON Mode completions via Mistral Large (mistral-large-latest)
  6. Dynamic thread title generation
===============================================================================
"""

import os
import re
import json
import pickle
import httpx
import numpy as np
from typing import List, Dict, Tuple, Any

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# API Keys & Models configuration
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_LLM_MODEL = os.getenv("MISTRAL_LLM_MODEL", "mistral-large-latest")
MISTRAL_EMBED_MODEL = "mistral-embed"
MISTRAL_RERANK_MODEL = "mistral-rerank-latest"


# ==============================================================================
# 📄 DOCUMENT CHUNKING & PARSING UTILITIES
# ==============================================================================

def parse_faq_html(file_path: str) -> List[str]:
    """
    Parses templates/faq.html using regex to extract Questions and Answers,
    forming clean text chunks for our RAG database.
    """
    chunks = []
    if not os.path.exists(file_path):
        print(f"[WARNING] FAQ file not found at: {file_path}")
        return chunks

    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()
    
    # Regular expression to extract question title and the raw inner html answer
    question_pattern = re.compile(
        r'<div\s+class="faq-question"[^>]*>\s*(.*?)\s*<span class="faq-chevron">',
        re.DOTALL
    )
    answer_pattern = re.compile(
        r'<div\s+class="faq-answer"[^>]*>\s*(.*?)\s*</div>',
        re.DOTALL
    )
    
    # Split HTML by faq-item divs to isolate each Q&A pair
    items = html.split('<div class="faq-item"')
    for item in items[1:]:
        q_match = question_pattern.search(item)
        a_match = answer_pattern.search(item)
        
        if q_match and a_match:
            question = q_match.group(1).strip()
            answer = a_match.group(1).strip()
            
            # Clean HTML tags from the answer text
            answer_clean = re.sub(r'<[^>]+>', '', answer)
            # Remove redundant whitespaces
            answer_clean = " ".join(answer_clean.split())
            
            chunks.append(f"FAQ Question: {question}\nFAQ Answer: {answer_clean}")
            
    return chunks


def parse_responses_json(file_path: str) -> List[str]:
    """
    Parses responses.json to extract validated wellness advice and
    crisis helplines, returning them as text chunks.
    """
    chunks = []
    if not os.path.exists(file_path):
        print(f"[WARNING] responses.json not found at: {file_path}")
        return chunks

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        for emotion, content in data.items():
            # 1. Parse Advice (can be dict of topics or a single string)
            if "advice" in content:
                advice_data = content["advice"]
                if isinstance(advice_data, dict):
                    for topic, advice_text in advice_data.items():
                        advice_clean = " ".join(advice_text.split())
                        chunks.append(f"Mental Wellness Coping Advice for {topic.capitalize()} / {emotion.capitalize()}:\n{advice_clean}")
                else:
                    advice_clean = " ".join(str(advice_data).split())
                    chunks.append(f"Mental Wellness Coping Advice for {emotion.capitalize()}:\n{advice_clean}")
            
            # 2. Parse Critical Helplines and Safety Check-ins
            if emotion == "critical":
                if "helplines" in content:
                    helplines_text = content["helplines"]
                    chunks.append(f"Emergency Mental Health Helplines (India):\n{helplines_text}")
                if "immediate" in content:
                    immediate_text = " ".join(content["immediate"])
                    chunks.append(f"Crisis Intervention Guidelines:\n{immediate_text}")
                if "safety" in content:
                    safety_text = content["safety"]
                    chunks.append(f"Safety Guidelines (Critical Support):\n{safety_text}")

            # 3. Parse Abuse Safety Details
            if emotion == "abuse":
                if "safety_plan" in content:
                    chunks.append(f"Abuse Support Safety Plan:\n{content['safety_plan']}")
                if "safety_check" in content:
                    chunks.append(f"Abuse Support Safety Check:\n{content['safety_check']}")

            # 4. Parse Entertainment Recommendations
            if emotion == "entertainment":
                if "songs" in content:
                    for song in content["songs"]:
                        chunks.append(f"Song Recommendation: {song}")
                if "movies" in content:
                    for movie in content["movies"]:
                        chunks.append(f"Movie Recommendation: {movie}")
                if "jokes" in content:
                    for joke in content["jokes"]:
                        chunks.append(f"Joke to lift mood: {joke}")
                    
    except Exception as e:
        print(f"[ERROR] Error parsing responses.json: {e}")
        
    return chunks


def get_all_chunks(root_dir: str = ".") -> List[str]:
    """Combines extracted chunks from both FAQ and Responses files."""
    faq_path = os.path.join(root_dir, "frontend", "faq.html")
    responses_path = os.path.join(root_dir, "responses.json")
    
    faq_chunks = parse_faq_html(faq_path)
    response_chunks = parse_responses_json(responses_path)
    
    print(f"[STATUS] Parsed {len(faq_chunks)} FAQ chunks and {len(response_chunks)} advice chunks.")
    return faq_chunks + response_chunks


# ==============================================================================
# 🧠 VECTOR STORE & SIMILARITY SEARCH (STANDARD RAG)
# ==============================================================================

class VectorStore:
    """
    Simple numpy-based Vector Store that generates embeddings via Mistral
    and calculates relevance scores using cosine similarity.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.documents: List[str] = []
        self.embeddings: List[np.ndarray] = []

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Invokes Mistral's Embeddings API to embed a batch of texts."""
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY environment variable is missing.")
            
        url = "https://api.mistral.ai/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": MISTRAL_EMBED_MODEL,
            "input": texts
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_data = response.json()
            # Extract dense vectors
            return [item["embedding"] for item in res_data["data"]]

    def add_documents(self, texts: List[str]):
        """Embeds a list of documents and indexes them in memory."""
        if not texts:
            return
        
        # Embed in batches to respect API limits
        batch_size = 16
        new_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            try:
                batch_embeds = self.get_embeddings(batch)
                new_embeddings.extend(batch_embeds)
            except Exception as e:
                print(f"[WARNING] Error embedding batch {i}-{i+len(batch)}: {e}")
                # Fallback to zero vectors in case of API failure to keep alignment
                new_embeddings.extend([[0.0] * 1024] * len(batch))
        
        for text, embed in zip(texts, new_embeddings):
            self.documents.append(text)
            self.embeddings.append(np.array(embed))

    def similarity_search(self, query: str, k: int = 10) -> List[Tuple[str, float]]:
        """Calculates cosine similarity of query against documents and returns top k."""
        if not self.documents:
            return []
            
        # Get query embedding
        query_embeds = self.get_embeddings([query])
        query_vector = np.array(query_embeds[0])
        
        results = []
        for doc, doc_vector in zip(self.documents, self.embeddings):
            # Cosine similarity formula: dot(A, B) / (norm(A) * norm(B))
            dot_product = np.dot(query_vector, doc_vector)
            norm_q = np.linalg.norm(query_vector)
            norm_d = np.linalg.norm(doc_vector)
            
            similarity = dot_product / (norm_q * norm_d) if (norm_q > 0 and norm_d > 0) else 0.0
            results.append((doc, float(similarity)))
            
        # Sort descending by similarity score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]


def initialize_rag(root_dir: str = ".") -> VectorStore:
    """
    Initializes the VectorStore. Loads from local cache if it exists;
    otherwise crawls source files, embeds chunks, and saves to cache.
    """
    vector_store = VectorStore(MISTRAL_API_KEY)
    cache_path = os.path.join(root_dir, "rag_embeddings.pickle")
    
    # 1. Try loading cached vectors
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cache = pickle.load(f)
                vector_store.documents = cache["documents"]
                vector_store.embeddings = [np.array(e) for e in cache["embeddings"]]
            print(f"[SUCCESS] RAG cache loaded successfully ({len(vector_store.documents)} chunks).")
            return vector_store
        except Exception as e:
            print(f"[WARNING] Failed to load RAG cache: {e}. Rebuilding vector index...")
            
    # 2. Build and embed chunks if cache is missing/corrupt
    if not MISTRAL_API_KEY:
        print("[WARNING] MISTRAL_API_KEY not set. RAG pipeline cannot generate embeddings.")
        return vector_store

    chunks = get_all_chunks(root_dir)
    vector_store.add_documents(chunks)
    
    # 3. Save cache for next run
    try:
        with open(cache_path, "wb") as f:
            pickle.dump({
                "documents": vector_store.documents,
                "embeddings": [e.tolist() for e in vector_store.embeddings]
            }, f)
        print("[SAVE] RAG embeddings cache saved successfully.")
    except Exception as e:
        print(f"[WARNING] Failed to cache RAG embeddings: {e}")
        
    return vector_store


# ==============================================================================
# 🔍 RERANKING COMPONENT
# ==============================================================================

async def rerank_documents(query: str, documents: List[str], k: int = 3, api_key: str = MISTRAL_API_KEY) -> List[str]:
    """
    Reranks document chunks using Mistral Chat Completions.
    """
    if not documents:
        return []
    if not api_key:
        print("[WARNING] MISTRAL_API_KEY not set. Utilizing top embeddings without reranking.")
        return documents[:k]
        
    if len(documents) <= k:
        return documents

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Format the documents with indices for the LLM
    documents_input = "\n".join([f"[{i}] {doc}" for i, doc in enumerate(documents)])

    system_prompt = """You are an information retrieval ranker.
Your task is to rank the provided text documents based on their relevance to the user's query.
You must output a JSON object containing a list of the top indices sorted in descending order of relevance.

Constraints:
1. ONLY return the indices of the most relevant documents (maximum k documents).
2. The response must be a valid JSON object with the key "indices" containing a list of integers.
3. Absolutely do not include any explanatory text, code fences, markdown, or commentary. Only output the JSON object.

Example output:
{
    "indices": [2, 0, 4]
}
"""

    user_content = f"Query: {query}\n\nDocuments to rank:\n{documents_input}\n\nReturn the top {k} indices in JSON format."

    payload = {
        "model": MISTRAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_data = response.json()
            
            content_str = res_data["choices"][0]["message"]["content"]
            result = json.loads(content_str)
            indices = result.get("indices", [])
            
            top_docs = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(documents):
                    top_docs.append(documents[idx])
            
            if not top_docs:
                return documents[:k]
                
            return top_docs[:k]
    except Exception as e:
        print(f"[WARNING] LLM Reranking failed: {e}. Falling back to top embeddings.")
        return documents[:k]



# ==============================================================================
# 💬 MISTRAL CHAT GENERATION WITH JSON MODE
# ==============================================================================

def get_mistral_chat_response(
    user_message: str,
    chat_history: List[Dict[str, str]],
    context_chunks: List[str],
    api_key: str = MISTRAL_API_KEY
) -> Dict[str, Any]:
    """
    Queries Mistral Large model incorporating conversation history and RAG context.
    Enforces a strict structured JSON output for classification & response text.
    """
    if not api_key:
        return {
            "response": "Hello! I am MindMate. Currently, my Mistral API Key is missing from the environment configurations. Please add MISTRAL_API_KEY in your .env file to enable my chat capabilities.",
            "emotion": "chitchat",
            "risk": "NORMAL",
            "confidence": "100%"
        }
        
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 1. Format the retrieved context passages
    context_text = "\n---\n".join(context_chunks) if context_chunks else "No relevant context found."
    
    # 2. System prompt definitions
    system_prompt = f"""You are MindMate, a warm, professional, and empathetic mental wellness chatbot companion for Indian students.
Your primary role is to listen actively, validate user emotions, and offer constructive coping tips.

CRITICAL GUIDELINES:
1. EXCLUSIVE MENTAL HEALTH FOCUS: You are exclusively a mental health, emotional support, and self-care companion. Do not answer questions that are unrelated to emotional support, self-care, academic pressure, coping, stress, relationships, or mental wellness (such as general knowledge, coding, math, history, or pop culture). If the user asks an unrelated question, politely decline and redirect them back to wellness and mental health topics.
2. LANGUAGE DEFAULT & MULTI-LINGUAL SUPPORT: By default, you must respond strictly in standard English. Do not use Hinglish or any other language unless the user starts the conversation in that language (e.g. they write in Bengali, Hindi, or Hinglish) OR they explicitly instruct/request you to speak in a specific language (e.g. 'reply in Bengali'). In those cases, you must immediately switch and respond in the requested language. Never override a user's language request.
3. ABSOLUTELY NO MARKDOWN STYLING: Your response text must be plain text only. Do not use any markdown formatting characters. Never use double asterisks (**), italics, headers (#), backticks, or raw bullet lists (* or -). If you need to make lists, use plain numbering (e.g., '1.', '2.') and use simple double newlines (\\n\\n) to separate paragraphs.
4. Tone & Context: Speak in a warm, welcoming, friendly, and non-judgmental tone. Incorporate information from the provided RAG Context (coping tips, helpline numbers) naturally, without copy-pasting it word-for-word.
5. Distress/Crisis Check: Assess the user's emotion and risk level. If they show signs of severe crisis (abuse, self-harm, grief, self-destructive behavior), immediately prioritize providing emergency numbers (112, AASRA: 9820466567, iCall: 9152987821) in your response.
6. Memory: Adapt to the conversation history to maintain context flow.

RAG CONTEXT DATABASE:
{context_text}

OUTPUT STRUCTURE:
You MUST respond with a valid JSON object. Do not add any markdown formatting or extra text outside this JSON object:
{{
  "response": "Your empathetic, detailed chat reply in the detected user language. PLAIN TEXT ONLY. No markdown formatting (no **, #, -, *). Use plain numbering and double newlines.",
  "emotion": "Categorize user's query: 'happy', 'sad', 'critical', 'chitchat', or 'out_of_context'.",
  "risk": "Categorize risk level: 'NORMAL', 'LOW', 'MODERATE', 'HIGH', or 'CRITICAL'.",
  "confidence": "Your classification confidence percentage string (e.g., '95%')."
}}
"""

    # 3. Assemble message array
    messages = [{"role": "system", "content": system_prompt}]
    
    # Append past chat history (Format: [{'sender': 'user'|'bot', 'message': '...'}])
    for turn in chat_history:
        role = "user" if turn["sender"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["message"]})
        
    # Append the new user message
    messages.append({"role": "user", "content": user_message})
    
    payload = {
        "model": MISTRAL_LLM_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"}
    }
    
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_data = response.json()
            
            # Parse output string into a dictionary
            content_str = res_data["choices"][0]["message"]["content"]
            result = json.loads(content_str)
            
            # Enforce schema validity
            required_keys = ["response", "emotion", "risk", "confidence"]
            if not all(key in result for key in required_keys):
                raise ValueError("JSON is missing required schema fields.")
                
            return result
            
    except Exception as e:
        print(f"[ERROR] Mistral API Completion Error: {e}")
        # Standard friendly fallback response
        return {
            "response": "I'm here with you, but I'm having a little trouble connecting to my servers. Can you tell me more about how you are feeling right now?",
            "emotion": "sad",
            "risk": "NORMAL",
            "confidence": "50%"
        }


# ==============================================================================
# 🏷️ DYNAMIC CHAT THREAD TITLING
# ==============================================================================

def generate_thread_title(first_message: str, api_key: str = MISTRAL_API_KEY) -> str:
    """
    Summarizes the first message in a thread to create a 2-4 word chat title.
    Uses mistral-small-latest for fast, cost-efficient summaries.
    """
    if not api_key or not first_message:
        return "New Chat"
        
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    system_prompt = (
        "You are an assistant that summarizes the user's first chat message into a very brief chat topic title. "
        "Keep it strictly between 2 to 4 words. Do not use punctuation, quotes, or introductory text. "
        "Examples: 'Exam stress help', 'Feeling lonely', 'Anxious thoughts'."
    )
    
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Summarize this message: {first_message}"}
        ],
        "max_tokens": 10
    }
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_data = response.json()
            title = res_data["choices"][0]["message"]["content"].strip()
            # Clean wrapping quotes if generated
            title = re.sub(r'^["\']|["\']$', '', title)
            return title
    except Exception as e:
        print(f"[WARNING] Title generation error: {e}")
        return "New Chat"


# ==============================================================================
# 🤖 STREAMING GENERATION & CLASSIFICATION HELPERS
# ==============================================================================

async def get_mistral_chat_stream(
    user_message: str,
    chat_history: List[Dict[str, str]],
    context_chunks: List[str],
    api_key: str = MISTRAL_API_KEY
):
    """
    Yields chunks of text response from Mistral Large in real-time.
    """
    if not api_key:
        yield "Hello! I am MindMate. Currently, my Mistral API Key is missing. Please add it to your configuration."
        return

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # 1. Format context
    context_text = "\n---\n".join(context_chunks) if context_chunks else "No relevant context found."

    # 2. System prompt
    system_prompt = f"""You are MindMate, a warm, professional, and empathetic mental wellness chatbot companion for Indian students.
Your primary role is to listen actively, validate user emotions, and offer constructive coping tips.

CRITICAL GUIDELINES:
1. EXCLUSIVE MENTAL HEALTH FOCUS: You are exclusively a mental health, emotional support, and self-care companion. Do not answer questions that are unrelated to emotional support, self-care, academic pressure, coping, stress, relationships, or mental wellness (such as general knowledge, coding, math, history, or pop culture). If the user asks an unrelated question, politely decline and redirect them back to wellness and mental health topics.
2. LANGUAGE DEFAULT & MULTI-LINGUAL SUPPORT: By default, you must respond strictly in standard English. Do not use Hinglish or any other language unless the user starts the conversation in that language (e.g. they write in Bengali, Hindi, or Hinglish) OR they explicitly instruct/request you to speak in a specific language (e.g. 'reply in Bengali'). In those cases, you must immediately switch and respond in the requested language. Never override a user's language request.
3. ABSOLUTELY NO MARKDOWN STYLING: Your response text must be plain text only. Do not use any markdown formatting characters. Never use double asterisks (**), italics, headers (#), backticks, or raw bullet lists (* or -). If you need to make lists, use plain numbering (e.g., '1.', '2.') and use simple double newlines (\\n\\n) to separate paragraphs.
4. Tone & Context: Speak in a warm, welcoming, friendly, and non-judgmental tone. Incorporate information from the provided RAG Context (coping tips, helpline numbers) naturally, without copy-pasting it word-for-word.
5. Distress/Crisis Check: Assess the user's emotion and risk level. If they show signs of severe crisis (abuse, self-harm, grief, self-destructive behavior), immediately prioritize providing emergency numbers (112, AASRA: 9820466567, iCall: 9152987821) in your response.
6. Memory: Adapt to the conversation history to maintain context flow.

RAG CONTEXT DATABASE:
{context_text}
"""

    messages = [{"role": "system", "content": system_prompt}]
    for turn in chat_history:
        role = "user" if turn["sender"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["message"]})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": MISTRAL_LLM_MODEL,
        "messages": messages,
        "stream": True
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            content = data_json["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except Exception:
                            pass
    except Exception as e:
        print(f"[ERROR] Mistral Streaming error: {e}")
        yield "I am having trouble connecting to my service. How can I help you?"


def classify_message(user_message: str, api_key: str = MISTRAL_API_KEY) -> Dict[str, Any]:
    """
    Runs a fast classification query to evaluate user's emotion and risk level.
    """
    if not api_key:
        return {"emotion": "chitchat", "risk": "NORMAL", "confidence": "100%"}

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    system_prompt = """You are an emotion and risk assessment assistant. Categorize the user's query into emotion, risk, and confidence metrics.
You MUST respond with a valid JSON object. Do not add any markdown formatting or extra text outside this JSON object:
{
  "emotion": "Categorize user's query: 'happy', 'sad', 'critical', 'chitchat', or 'out_of_context'.",
  "risk": "Categorize risk level: 'NORMAL', 'LOW', 'MODERATE', 'HIGH', or 'CRITICAL'.",
  "confidence": "Your classification confidence percentage string (e.g., '95%')."
}
"""
    payload = {
        "model": MISTRAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_data = response.json()
            content_str = res_data["choices"][0]["message"]["content"]
            return json.loads(content_str)
    except Exception as e:
        print(f"[WARNING] Classification error: {e}")
        return {"emotion": "chitchat", "risk": "NORMAL", "confidence": "80%"}
