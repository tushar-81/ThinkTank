import re
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from selenium import webdriver
from rank_bm25 import BM25Okapi
from openai import OpenAI
from sklearn.metrics.pairwise import cosine_similarity
from backend.Agents.Common_State import State
import requests
import trafilatura
from dotenv import load_dotenv
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ddgs import DDGS
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import requests
from datetime import datetime
import pytz

load_dotenv()
client = OpenAI()

tz = pytz.timezone("Asia/Kolkata")
today=datetime.now(tz)

def search(query: str):
    with DDGS() as ddgs:
        results = ddgs.text(
            query,
            max_results=15
        )
        return list(results)


def get_words_list(text: str):
    stop_words = set(ENGLISH_STOP_WORDS)
    lemmatizer = WordNetLemmatizer()

    # Fix merged words (camelCase → split)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Separate numbers from words
    text = re.sub(r'(\d+)', r' \1 ', text)

    # Lowercase
    text = text.lower()

    # Extract words
    words = re.findall(r'\b[a-zA-Z]+\b', text)

    # Remove stopwords + lemmatize
    final_words = [
        lemmatizer.lemmatize(word)
        for word in words
        if word not in stop_words and len(word) > 2
    ]

    return final_words

def keyword_score(sentence : str, body:str):
    
    sentence_list=get_words_list(sentence)

    body_word_list=get_words_list(body)

    if not body_word_list: 
        return 0.0

    sentence_set=set(sentence_list)
    score=0
    for a in body_word_list:
        if any(a.startswith(b) or b.startswith(a) for b in sentence_set):
            #checking prefix between a & b
            score+=1  

    final_score=score/len(body_word_list)

    return final_score 

def filter_list(query, A_dict_list):
    filtered_list=[]

    for a_dict in A_dict_list:

        body=a_dict.get('body')
        title=a_dict.get('title')

        score1=keyword_score(query, body)
        score2=keyword_score(query, title)

        score=0.95*score1+0.05*score2
        a_dict['keyword_score']=score
        
        if score>0.10:
            filtered_list.append(a_dict)

    filtered_list=sorted(filtered_list, key=lambda x: x['keyword_score'], reverse=True)
    return filtered_list


def get_html_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        html = requests.get(url, headers=headers, timeout=10).text
        content = trafilatura.extract(html)
    except Exception:
        content = None

    if not content or len(content) < 150:
        try:
            driver = webdriver.Chrome()
            driver.get(url)
            html = driver.page_source
            content = trafilatura.extract(html)
            driver.quit()
        except Exception:
            content = ''

    return str(content) if content else ''

def chunk_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,       
        chunk_overlap=50,      
        separators=["\n\n", "\n", ".", " "]
    )
    
    chunks = splitter.split_text(text)
    return chunks


def bm25_retrieve(text:str, query:str):
    chunks = chunk_text(text)
    
    tokenized_corpus = [get_words_list(s) for s in chunks]
    
    bm25 = BM25Okapi(tokenized_corpus)
    
    tokenized_query = get_words_list(query)
    
    scores = bm25.get_scores(tokenized_query)
    
    # Rank sentences
    ranked = sorted(
        zip(chunks, scores),
        key=lambda x: x[1],
        reverse=True
    )
    ranked=ranked[:40]
    ranked_sentences=[sentence[0] for sentence in ranked]
    return ranked_sentences


def get_webpage(query: str, A_dict_list: list):
    filtered_list = filter_list(query=query, A_dict_list=A_dict_list)

    if len(filtered_list) > 4:
        filtered_list = filtered_list[:4]

    web_content_chunks = {}

    for filter in filtered_list:
        website = str(filter.get('href'))

        try:
            content = get_html_content(website)

            # skip if content is empty or too short
            if not content or len(content) < 50:
                continue

            sentences = bm25_retrieve(text=content, query=query)

            if not sentences:
                continue

            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=[query] + sentences
            )

            embeddings = [item.embedding for item in response.data]
            query_embedding = embeddings[0]
            sentence_embeddings = embeddings[1:]
            scores = cosine_similarity([query_embedding], sentence_embeddings)[0]

            results = sorted(
                zip(sentences, scores),
                key=lambda x: x[1],
                reverse=True
            )

            web_content_chunks[website] = results[:7]

        except Exception as e:
            print(f"[Search] skipping {website}: {e}")
            continue

    return web_content_chunks
    

def Search_agent(state:State):
    print("search agent started")
    query = state['LLM_instruction']
    print(query)
    search_results=search(query=query)
    print(search_results)
    web_search_dict=get_webpage(query, search_results)

    search_string=''

    for key, value in web_search_dict.items():
        search_string+=f'Source : {key}\n Result : {value} \n\n'

    instruction=f"""You are an AI assistant tasked with answering a user’s query using provided web search results.

## Input Structure

You will receive:

* **Query**: The user’s question
* **Search Results**: A list of sources, where each source contains:

  * `source`: webpage title or URL
  * `content`: a list of relevant text snippets extracted from that webpage

## Your Objective

Generate a **clear, accurate, and concise answer** to the query using only the provided content.

## Instructions

1. **Synthesize, don’t copy**

   * Combine information from multiple sources into a single coherent response
   * Avoid repeating the same information if it appears in multiple sources

2. **Remove redundancy**

   * If different sources say the same thing, include it only once
   * Prefer the most complete or clearly worded version

3. **Maintain factual consistency**

   * Do not add information that is not present in the provided results
   * If sources conflict, prefer the majority or most reliable phrasing

4. **Structure the response**

   * Start with a direct answer to the query
   * Follow with supporting details if necessary
   * Use simple, readable language

5. **Source grounding (light)**

   * Do not explicitly cite links unless asked
   * Ensure all statements are grounded in the given content

6. **Handle incomplete information**

   * If the results are insufficient, say:
     “The available sources do not provide enough information to fully answer this.”

7. **Avoid meta statements**

   * Do not mention “search results”, “provided context”, or similar phrases

8. **Strictly ensure that results that are more recent with respect to today's date will given more preference**

## Output Requirements

* Clear and human-readable
* No duplication
* No unnecessary verbosity
* Focus on relevance to the query

## Goal

Produce a response that feels like a **single, well-written answer**, even though it is derived from multiple overlapping sources.
"""
    
    user_message=f"""

Date for reference :
{today}

Query :
{query}

Web Results:
{search_string}

Answer the query using the above results.
""" 
    
    llm=ChatOpenAI(model='gpt-4o-mini')
    response=llm.invoke([SystemMessage(content=instruction), HumanMessage(content=user_message)])
    print(response)
    return {
        'messages' : [AIMessage(content=response.content)]
    }