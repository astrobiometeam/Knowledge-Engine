
import os
import sqlite3
import json
import re
import io
import csv
from flask import request, jsonify
# from summai import summarize_text  
# Note: The summarization model (facebook/bart-large-cnn)
# must be downloaded before first use. This process may take a few minutes.
# This line is commented out temporarily to avoid delays during initial setup.
from nslsl_scraper import NSLSLScraper
from task_nasa_scraper import NASATaskBookScraper
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import Counter
from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
import xmltodict
from ratelimit import limits, sleep_and_retry
from urllib.parse import urlencode
import pandas as pd
import requests
from bs4 import BeautifulSoup
import requests
from nltk.corpus import stopwords
from nltk import word_tokenize, pos_tag
from collections import Counter
import json
from flask import Flask, request, jsonify
from spacy.tokens import Doc
import httpx
import traceback
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import re
from datetime import datetime, date, timezone
from flask import Response
from textblob import TextBlob
from db_checker import ensure_papers_columns

ensure_papers_columns()

import spacy
from spacytextblob.spacytextblob import SpacyTextBlob


nlp = spacy.load("en_core_web_sm")


nlp.add_pipe("spacytextblob")


_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

def call_chatbot_with_results(items, source, q, session_id="advanced", limit_for_prompt=10):

    mini = [{
        "title": it.get("title"),
        "url": it.get("url"),
        "doi": it.get("doi"),
        "abstract": (it.get("abstract") or "")[:1200]
    } for it in (items or [])[:limit_for_prompt]]

    prompt = (
    f'These are the results of my search in {source} for "{q}". '
    f'Based on this list, give a concise summary of all of them + the most important points '
    f'And finally, your analytical conclusion:\n'
    f'{json.dumps(mini, ensure_ascii=False)}'
    )

    try:
        res = requests.post(
            CHATBOT_URL,
            json={
                "message": prompt,
                "session_id": session_id,
                "use_custom_voice": False,
                "context_limit": 10
            },
            timeout=120
        )
        res.raise_for_status()
        data = res.json() if "application/json" in (res.headers.get("content-type", "")) else {}
        return {
            "ok": bool(data.get("success")),
            "mode": data.get("mode"),
            "summary": data.get("response"),
            "audio_url": data.get("audio_url"),
            "raw": data
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _chatbot_payload_from_request(default_source, query_text, limit, date_from=None, date_to=None):
    try:
        return call_chatbot_and_get_summary(
            query=query_text,
            source=default_source,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            session_id=request.args.get('session_id', 'advanced')
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

def normalize_publication_date(value):

    if value is None:
        return None


    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is not None:
            try:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                dt = dt.replace(tzinfo=None)
        return dt

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)


    if isinstance(value, (int, float)):
        v = int(value)
        if 1000 <= v <= 9999:
            return datetime(v, 1, 1)
        try:
            return datetime.utcfromtimestamp(v)
        except Exception:
            pass

    s = str(value).strip()
    if not s:
        return None


    s = re.sub(r'(?i)\b(circa|c\.|approx|approx\.)\b', '', s).strip()

    s = re.split(r'\s+to\s+|–|—|-', s)[0].strip()


    try:
        ds = s.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ds)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        pass

    
    fmts = [
        '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d', '%Y/%m/%d', '%d %B %Y', '%d %b %Y',
        '%B %d, %Y', '%b %d, %Y', '%Y-%m', '%Y/%m', '%Y'
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            continue


    parts = re.split(r'[./\s-]', s)
    try:
        if len(parts) >= 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime(y, m, d)
        if len(parts) == 2:
            y, m = int(parts[0]), int(parts[1])
            return datetime(y, m, 1)
    except Exception:
        pass


    m = re.search(r'([A-Za-z]+)[\s,.-]*?(\d{4})', s)
    if m:
        mon_str = m.group(1)[:3].lower()
        yr = int(m.group(2))
        mon = _MONTHS.get(mon_str)
        if mon:
            return datetime(yr, mon, 1)


    ysearch = re.search(r'(19|20)\d{2}', s)
    if ysearch:
        y = int(ysearch.group(0))
        return datetime(y, 1, 1)

    return None

def generate_summary(text: str) -> str:
    if not text:
        return ""
    try:
        if len(text.strip()) < 120:
            return text.strip()
        return summarize_text(text)
    except Exception as e:
        print(f"[Summary] failed: {e}")
        return text



try:
    import nltk
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt_tab', quiet=True)
    nltk.download('averaged_perceptron_tagger_eng')
    nltk.download('averaged_perceptron_tagger', quiet=True)
    NLTK_AVAILABLE = True
except:
    NLTK_AVAILABLE = False
    print("NLTK not available - using simplified NLP")






class Config:

    SECRET_KEY = 'space-biology-secret-key-2024'


    NASA_API_KEY = 'fuc5eCBedrisI2kXpAcuNePORgda5yaDU81ObWgc'
    NCBI_API_KEY = '5d284f3d30d26f0932a52005747d66dced08'
    PUBMED_EMAIL = 'amirarsalan.tayebi1@gmail.com'


    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATABASE_PATH = os.path.join(BASE_DIR, 'space_biology.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


    NASA_TECHNICAL_REPORTS_URL = 'https://ntrs.nasa.gov/api/citations/search'
    NASA_ADS_URL = 'https://ui.adsabs.harvard.edu/v1/search/query'


    PUBMED_SEARCH_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi'
    PUBMED_FETCH_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
    PUBMED_SUMMARY_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi'


    OSDR_BASE_URL = "https://osdr.nasa.gov"
    OSDR_SEARCH_URL = f"{OSDR_BASE_URL}/osdr/data/search"
    OSDR_META_URL = f"{OSDR_BASE_URL}/osdr/data/osd/meta/{{osd_id}}"
    OSDR_FILES_URL = f"{OSDR_BASE_URL}/osdr/data/osd/files/{{osd_id}}"
    OSDR_DOWNLOAD_PREFIX = OSDR_BASE_URL


    CROSSREF_BASE_URL = "https://api.crossref.org"


    NASA_ADS_API_KEY = 'qNP5l0eg3Ayo3VwSX778BklqKG8fmTj5TOayIj6W'
    NASA_ADS_BASE_URL = 'https://api.adsabs.harvard.edu/v1'
    NASA_ADS_SEARCH_URL = f"{NASA_ADS_BASE_URL}/search/query"
    NASA_ADS_METRICS_URL = f"{NASA_ADS_BASE_URL}/metrics"
    NASA_ADS_CITATIONS_URL = f"{NASA_ADS_BASE_URL}/citations"
    NASA_ADS_EXPORT_BIBTEX_URL = f"{NASA_ADS_BASE_URL}/export/bibtex"


    OPENALEX_BASE_URL = "https://api.openalex.org"


    EUROPE_PMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    BIORXIV_BASE_URL = "https://api.biorxiv.org/details"


    MAX_SEARCH_RESULTS = 100
    RESULTS_PER_PAGE = 10
    API_REQUEST_DELAY = 0.334


    MAX_GRAPH_NODES = 100
    MAX_GRAPH_LINKS = 200

    @classmethod
    def validate_apis(cls):

        missing = []
        if not cls.NASA_API_KEY or cls.NASA_API_KEY == 'your-nasa-api-key':
            missing.append('NASA_API_KEY')
        if not cls.NCBI_API_KEY or cls.NCBI_API_KEY == 'your-ncbi-api-key':
            missing.append('NCBI_API_KEY')
        if not cls.PUBMED_EMAIL or cls.PUBMED_EMAIL == 'your-email@domain.com':
            missing.append('PUBMED_EMAIL')

        if missing:
            raise ValueError(
                f"Missing or invalid API keys: {', '.join(missing)}")

        print("All API keys validated successfully")



CHATBOT_URL = os.environ.get("CHATBOT_URL", "http://127.0.0.1:8000/chat-text")

async def ping_chatbot_auto(query, source, date_from=None, date_to=None, limit=10, session_id="default"):
    range_part = f" {date_from}–{date_to}" if date_from and date_to else (f" {date_from}–" if date_from else (f" –{date_to}" if date_to else ""))
    in_source = f"in {source}" if source else "in best sources"
    prompt = (f'Search {in_source} for: "{query}"{range_part}, limit {limit}. '
              f'Then give me: a concise summary of ALL returned papers, the most interesting/novel points, and your own synthesized conclusion.')

    async with httpx.AsyncClient(timeout=None) as client:
        await client.post("http://127.0.0.1:8000/chat-text", json={
            "message": prompt,
            "session_id": session_id,
            "use_custom_voice": False,
            "context_limit": 10
        })
def call_chatbot_and_get_summary(query, source="", date_from=None, date_to=None, limit=10, session_id="advanced"):

    
    
    
    def _range(df, dt):
        if df and dt: return f" between {df} and {dt}"
        if df: return f" from {df} onwards"
        if dt: return f" to {dt}"
        return ""
    rng = _range(date_from, date_to)
    in_src = f"In source {source}" if source else "In best sources"
    prompt = (f'{in_src} search for "{query}"{rng} (max {limit} results). '
              f'Then provide a concise summary of all the articles found + the most interesting/new points and finally your analytical conclusion.')

    try:
        res = requests.post(
            CHATBOT_URL,
            json={
                "message": prompt,
                "session_id": session_id,
                "use_custom_voice": False,
                "context_limit": 10
            },
            timeout=60
        )
        res.raise_for_status()
        data = res.json() if "application/json" in (res.headers.get("content-type","")) else {}
        return {
            "ok": bool(data.get("success")),
            "mode": data.get("mode"),
            "summary": data.get("response"),
            "raw": data
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

db = SQLAlchemy()


class Paper(db.Model):

    __tablename__ = 'papers'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    abstract = db.Column(db.Text)
    authors = db.Column(db.Text)
    source = db.Column(db.String(100))
    url = db.Column(db.String(500))
    keywords = db.Column(db.Text)
    publication_date = db.Column(db.DateTime)
    doi = db.Column(db.String(200))
    pubmed_id = db.Column(db.String(50))
    nasa_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sentiment = db.Column(db.String(20))
    objective = db.Column(db.Text)

    
    knowledge_nodes = db.relationship(
        'KnowledgeNode', backref='paper', lazy=True)

    def to_dict(self):
        abstract_text = self.abstract or ""
        summary = ""

        if abstract_text.strip():
            try:
                if len(abstract_text) < 120:
                    summary = abstract_text
                else:
                    summary = summarize_text(abstract_text)
            except Exception as e:
                print(f"[Paper] summarize_text failed for paper id={self.id}: {e}")
                summary = abstract_text

        return {
            'id': self.id,
            'title': self.title,
            'abstract': self.abstract,
            'summary': summary,
            'authors': json.loads(self.authors) if self.authors else [],
            'source': self.source,
            'url': self.url,
            'keywords': json.loads(self.keywords) if self.keywords else [],
            'publication_date': self.publication_date.isoformat() if self.publication_date else None,
            'doi': self.doi,
            'pubmed_id': self.pubmed_id,
            'nasa_id': self.nasa_id,
            'created_at': self.created_at.isoformat(),
            'sentiment': self.sentiment,
            'objective': self.objective
        }


class KnowledgeNode(db.Model):

    __tablename__ = 'knowledge_nodes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    node_type = db.Column(db.String(50))
    description = db.Column(db.Text)
    confidence = db.Column(db.Float)
    category = db.Column(db.String(100))
    node_metadata = db.Column(db.Text)
    paper_id = db.Column(db.Integer, db.ForeignKey('papers.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        desc_text = self.description or ""
        summary = ""

        if desc_text.strip():
            try:
                if len(desc_text) < 120:
                    summary = desc_text
                else:
                    summary = summarize_text(desc_text)
            except Exception as e:
                print(f"[KnowledgeNode] summarization failed for id={self.id}: {e}")
                summary = desc_text

        return {
            'id': self.id,
            'name': self.name,
            'node_type': self.node_type,
            'description': self.description,
            'summary': summary,
            'confidence': self.confidence,
            'category': self.category,
            'metadata': json.loads(self.node_metadata) if self.node_metadata else {},
            'paper_id': self.paper_id,
            'created_at': self.created_at.isoformat()
        }


class SearchHistory(db.Model):

    __tablename__ = 'search_history'

    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(500), nullable=False)
    results_count = db.Column(db.Integer, default=0)
    search_time = db.Column(db.DateTime, default=datetime.utcnow)
    user_ip = db.Column(db.String(45))
    filters_used = db.Column(db.Text)
    sources_searched = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'query': self.query,
            'results_count': self.results_count,
            
            'search_time': self.search_time.isoformat(),
            'user_ip': self.user_ip,
            'filters_used': json.loads(self.filters_used) if self.filters_used else {},
            'sources_searched': json.loads(self.sources_searched) if self.sources_searched else []
        }






class RealNASAService:


    def __init__(self):
        self.api_key = Config.NASA_API_KEY
        self.ncbi_api_key = Config.NCBI_API_KEY
        self.pubmed_email = Config.PUBMED_EMAIL
        self.session = requests.Session()

        
        self.session.headers.update({
            'User-Agent': 'Space Biology Research Platform/1.0',
            'Accept': 'application/json'
        })

    @sleep_and_retry
    @limits(calls=3, period=1)
    def _make_request(self, url, params=None):

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"API request error: {e}")
            return None

    
    def _parse_date(self, value):

        if not value:
            return None
        try:
            s = str(value).strip()
            
            if s.isdigit() and len(s) == 4:
                return datetime(int(s), 1, 1)
            
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            
            parts = s.replace("/", "-").split("-")
            if len(parts) >= 3:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            if len(parts) == 2:
                return datetime(int(parts[0]), int(parts[1]), 1)
        except Exception as e:
            print(f"not parse date '{value}': {e}")
        return None

    def _get_keywords(self, keywords, text=None, max_keywords=10):

        try:
            
            if keywords:
                if isinstance(keywords, (list, tuple, set)):
                    kws = [str(k).strip() for k in keywords if k and str(k).strip()]
                else:
                    kws = [k.strip() for k in re.split(r'[;,\|\n]', str(keywords)) if k.strip()]
                out = []
                seen = set()
                for k in kws:
                    lk = k.lower()
                    if lk not in seen:
                        seen.add(lk)
                        out.append(k)
                    if len(out) >= max_keywords:
                        break
                return out

            
            if not text:
                return []
            nlp = NLPService()
            return nlp.extract_keywords(text, max_keywords=max_keywords) or []
        except Exception as e:
            print(f"get keywords error: {e}")
            return []
    

    def _parse_date(self, value):

        if not value:
            return None
        try:
            s = str(value).strip()
            
            if s.isdigit() and len(s) == 4:
                return datetime(int(s), 1, 1)
            
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            
            parts = s.replace("/", "-").split("-")
            if len(parts) >= 3:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                return datetime(int(parts[0]), int(parts[1]), 1)
        except Exception as e:
            print(f"not parse date '{value}': {e}")
        return None

    def search_nasa_technical_reports(self, query, limit=20):

        try:
            params = {
                'q': query,
                'api_key': self.api_key,
                'rows': limit,
                'format': 'json'
            }

            response = self._make_request(
                Config.NASA_TECHNICAL_REPORTS_URL, params)
            if not response:
                return []

            data = response.json()
            papers = []

            for item in data.get('response', {}).get('docs', []):
                paper = {
                    'title': item.get('title', 'No Title'),
                    'abstract': item.get('abstract', ''),
                    'authors': item.get('author', []),
                    'source': 'NASA Technical Reports',
                    'url': item.get('downloadUrl', ''),
                    'nasa_id': item.get('id', ''),
                    'keywords': item.get('subject', []),
                    'publication_date': self._parse_date(item.get('publicationDate'))
                }
                papers.append(paper)

            return papers

        except Exception as e:
            print(f"Technical Reports search error: {e}")
            return []
    def search_nasa_ads(self, query, limit=20, with_metrics=False, with_bibtex=False):

        try:
            headers = {
                "Authorization": f"Bearer {Config.NASA_ADS_API_KEY}",
                "Accept": "application/json"
            }
            params = {
                "q": query,
                "fl": "title,author,abstract,doi,bibcode,pubdate,keyword",
                "rows": limit,
                "sort": "date desc"
            }
            r = requests.get(Config.NASA_ADS_SEARCH_URL, headers=headers, params=params, timeout=30, verify=False)
            r.raise_for_status()
            data = r.json()

            nlp = NLPService()
            papers = []
            for doc in data.get("response", {}).get("docs", []):
                bibcode = doc.get("bibcode", "")
                title = doc.get("title", ["No Title"])[0] if doc.get("title") else "No Title"
                abstract = doc.get("abstract", "")
                authors = doc.get("author", [])
                subjects = doc.get("keyword", [])

                
                if subjects:
                    keywords = subjects
                else:
                    keywords = nlp.extract_keywords(abstract or title, max_keywords=10)

                paper = {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "source": "NASA ADS",
                    "url": f"https://ui.adsabs.harvard.edu/abs/{bibcode}",
                    "doi": doc.get("doi", [None])[0] if doc.get("doi") else None,
                    "nasa_id": bibcode,
                    "publication_date": self._parse_date(doc.get("pubdate")),
                    "keywords": keywords,
                }

                
                if with_metrics and bibcode:
                    metrics_data = self.get_nasa_ads_metrics(bibcode)
                    if metrics_data:
                        paper["metrics"] = metrics_data

                
                if with_bibtex and bibcode:
                    bibtex_str = self.get_nasa_ads_bibtex(bibcode)
                    if bibtex_str:
                        paper["bibtex"] = bibtex_str

                papers.append(paper)

            return papers

        except Exception as e:
            return []

     
    def _fetch_abstract_from_url(self, url: str, doi: str = None, pmid: str = None) -> str:

        try:
            
            if not url:
                if doi:
                    url = f"https://doi.org/{doi}"
                elif pmid:
                    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                else:
                    return ""

            
            r = self.session.get(url, timeout=15, verify=False)
            r.raise_for_status()
            html = r.text
            soup = BeautifulSoup(html, "lxml")

            
            self.authors = [m["content"].strip() for m in soup.find_all("meta", attrs={"name": "citation_author"}) if m.get("content")]
            self.publication_date = ""
            m = soup.find("meta", attrs={"name": "citation_publication_date"})
            if m and m.get("content"):
                self.publication_date = m["content"].strip()

            
            for meta_name in ("description", "og:description", "twitter:description", "citation_abstract"):
                m = soup.find("meta", attrs={"name": meta_name})
                if m and m.get("content"):
                    return m["content"].strip()
                m = soup.find("meta", attrs={"property": meta_name})
                if m and m.get("content"):
                    return m["content"].strip()

            
            selectors = [
                ("div", {"class": re.compile(r"abstract", re.I)}),
                ("section", {"class": re.compile(r"abstract", re.I)}),
                ("div", {"id": re.compile(r"abstract", re.I)}),
                ("section", {"id": re.compile(r"abstract", re.I)}),
                ("div", {"class": re.compile(r"abstract-content", re.I)}),
                ("div", {"class": re.compile(r"tsec", re.I)}),
                ("p", {"class": re.compile(r"abstract", re.I)})
            ]
            for tag, attrs in selectors:
                el = soup.find(tag, attrs=attrs)
                if el:
                    text = el.get_text(" ", strip=True)
                    if text and len(text) > 30:
                        return text

            
            for heading in soup.find_all(["h2", "h3", "h4"]):
                if heading.get_text(strip=True).lower().startswith("abstract"):
                    parts = []
                    sib = heading.find_next_sibling()
                    while sib and len(parts) < 4:
                        if sib.name in ["p", "div", "section"]:
                            t = sib.get_text(" ", strip=True)
                            if t:
                                parts.append(t)
                                break
                        sib = sib.find_next_sibling()
                    if parts:
                        return " ".join(parts)

            
            paras = soup.find_all("p")
            for p in paras:
                t = p.get_text(" ", strip=True)
                if len(t) > 200:
                    return t

            
            return ""
        except Exception as e:
            print(f"Error fetching abstract from {url}: {e}")
            return ""

    def search_sb_publication_csv(self, query, limit=20):

        try:
            csv_path = os.path.join(Config.BASE_DIR, "SB_publication_PMC.csv")
            if not os.path.exists(csv_path):
                print(f"SB CSV not found: {csv_path}")
                return []

            results = []
            qlower = (query or "").strip().lower()
            nlp = NLPService()
            if pd is not None:
                
                df = pd.read_csv(csv_path, dtype=str).fillna("")
                
                def get_field(row, names):
                    for n in names:
                        if n in row and row[n]:
                            return str(row[n])
                    
                    for col in row.index:
                        for n in names:
                            if col.lower() == n.lower() and row[col]:
                                return str(row[col])
                    return ""

                for _, row in df.iterrows():
                    title = get_field(row, ["title", "Title", "article_title"])
                    abstract = get_field(row, ["abstract", "Abstract", "summary"])
                    url = get_field(row, ["url", "link", "pmc_url", "article_url", "fulltext", "pdf_link"])
                    doi = get_field(row, ["doi", "DOI"])
                    pmid = get_field(row, ["pmid", "PMID"])
                    keywords = get_field(row, ["keywords", "Keywords"])
                    authors = get_field(row, ["authors", "Authors"])

                    hay = " ".join([title, abstract, keywords, authors]).lower()
                    if qlower and qlower not in hay:
                        continue

                    
                    if (not abstract or len(abstract.strip()) < 30):
                        fetched = self._fetch_abstract_from_url(url, doi=doi, pmid=pmid)
                        if fetched:
                            abstract = fetched
                            
                            if not authors:
                                authors = "; ".join(getattr(self, "authors", []))
                            
                            if not get_field(row, ["publication_date", "pubdate", "date", "year"]):
                                pubdate = getattr(self, "publication_date", "")
                            else:
                                pubdate = get_field(row, ["publication_date", "pubdate", "date", "year"])
                        else:
                            pubdate = get_field(row, ["publication_date", "pubdate", "date", "year"])

                    
                    nlp = NLPService()

                    
                    if keywords.strip():
                        keywords_list = [k.strip() for k in re.split(r";|,", keywords) if k.strip()]
                    else:
                        keywords_list = nlp.extract_keywords(abstract or title, max_keywords=10)

                    result = {
                        "title": title or "No Title",
                        "abstract": abstract or "",
                        "authors": [a.strip() for a in re.split(r";|,", authors) if a.strip()] if authors else getattr(self, "authors", []),
"publication_date": pubdate or None,
                        "source": "SB Publication",
                        "url": url or (f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "")),
                        "doi": doi or None,
                        "pubmed_id": pmid or None,
                        "keywords": keywords_list,
                        "sentiment": nlp.analyze_sentiment(abstract),
                        "objective": nlp.extract_objective(abstract),
                        
                    }
                    results.append(result)
                    if len(results) >= limit:
                        break

                return results

            else:
                
                with open(csv_path, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        title = (row.get("title") or row.get("Title") or row.get("article_title") or "")
                        abstract = (row.get("abstract") or row.get("Abstract") or row.get("summary") or "")
                        url = (row.get("url") or row.get("link") or row.get("pmc_url") or row.get("article_url") or "")
                        doi = (row.get("doi") or row.get("DOI") or "")
                        pmid = (row.get("pmid") or row.get("PMID") or "")
                        keywords = (row.get("keywords") or "")
                        authors = (row.get("authors") or "")

                        hay = " ".join([title, abstract, keywords, authors]).lower()
                        if qlower and qlower not in hay:
                            continue

                        if (not abstract or len(abstract.strip()) < 30):
                            fetched = self._fetch_abstract_from_url(url, doi=doi, pmid=pmid)
                            if fetched:
                                abstract = fetched

                        result = {
                            "title": title or "No Title",
                            "abstract": abstract or "",
                            "authors": [a.strip() for a in re.split(r";|,", authors) if a.strip()] if authors else [],
                            "source": "SB Publication",
                            "url": url or (f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "")),
                            "doi": doi or None,
                            "pubmed_id": pmid or None,
                            "keywords": [k.strip() for k in re.split(r";|,", keywords) if k.strip()] if keywords else [],
                            "sentiment": nlp.analyze_sentiment(abstract),
                            "objective": nlp.extract_objective(abstract),
                            "publication_date": row.get("publication_date") or row.get("pubdate") or row.get("date") or None
                        }
                        results.append(result)
                        if len(results) >= limit:
                            break

                return results

        except Exception as e:
            print(f"CSV search error: {e}")
            return []

    def search_pubmed_space_biology(self, query, limit=20):

        try:
            
            enhanced_query = f"({query}) AND (space biology OR microgravity OR space flight OR astronaut OR space medicine OR astrobiology)"

            
            search_params = {
                'db': 'pubmed',
                'term': query,
                'retmax': limit,
                'retmode': 'json',
                'api_key': self.ncbi_api_key,
                'tool': 'SpaceBiologyPlatform',
                'email': self.pubmed_email,
                'mindate': date_from,
                'maxdate': date_to
            }

            search_response = self._make_request(
                Config.PUBMED_SEARCH_URL, search_params)
            if not search_response:
                return []

            search_data = search_response.json()
            ids = search_data.get('esearchresult', {}).get('idlist', [])

            if not ids:
                return []

            
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(ids),
                'retmode': 'xml',
                'api_key': self.ncbi_api_key,
                'tool': 'SpaceBiologyPlatform',
                'email': self.pubmed_email
            }

            fetch_response = self._make_request(
                Config.PUBMED_FETCH_URL, fetch_params)
            if not fetch_response:
                return []

            return self._parse_pubmed_xml(fetch_response.text)

        except Exception as e:
            print(f"pubmed search error: {e}")
            return []

    def search_pubmed(self, query, limit=20):

        try:
            
            search_params = {
                'db': 'pubmed',
                'term': query,
                'retmax': limit,
                'retmode': 'json',
                'api_key': self.ncbi_api_key,
                'tool': 'SpaceBiologyPlatform',
                'email': self.pubmed_email
            }
            search_response = self._make_request(Config.PUBMED_SEARCH_URL, search_params)
            if not search_response:
                return []

            search_data = search_response.json()
            ids = search_data.get('esearchresult', {}).get('idlist', [])
            print("PubMed ID found:", ids)

            if not ids:
                return []

            
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(ids),
                'retmode': 'xml',
                'api_key': self.ncbi_api_key,
                'tool': 'SpaceBiologyPlatform',
                'email': self.pubmed_email
            }
            fetch_response = self._make_request(Config.PUBMED_FETCH_URL, fetch_params)
            if not fetch_response:
                return []

            
            print("FETCH XML START")
            print(fetch_response.text[:1000])
            print("FETCH XML END")

            return self._parse_pubmed_xml(fetch_response.text)

        except Exception as e:
            print(f"pubmed search error: {e}")
            return []

    def search_genelab_data(self, query, limit=10):

        try:
            params = {
                'term': query,
                'size': limit,
                'api_key': self.api_key
            }

            response = self._make_request(Config.GENELAB_API_URL, params)
            if not response:
                return []

            data = response.json()
            papers = []

            for item in data.get('hits', {}).get('hits', []):
                source_data = item.get('_source', {})
                paper = {
                    'title': source_data.get('study_title', 'No Title'),
                    'abstract': source_data.get('study_description', ''),
                    'authors': [source_data.get('study_pi', 'Unknown')],
                    'source': 'NASA GeneLab',
                    'url': f"https://genelab-data.ndc.nasa.gov/genelab/accession/{source_data.get('accession', '')}",
                    'keywords': source_data.get('study_factors', []),
                    'publication_date': self._parse_date(source_data.get('study_public_release_date'))
                }
                papers.append(paper)

            return papers

        except Exception as e:
            print(f"genelab search error: {e}")
            return []
    


    def _parse_pubmed_xml(self, xml_text):

        try:
            papers = []
            root = ET.fromstring(xml_text)
            nlp = NLPService()

            for article in root.findall(".//PubmedArticle"):
                pmid = article.findtext(".//PMID") or ""

                
                title = article.findtext(".//ArticleTitle") or "No Title"

                
                abstract_parts = []
                for a in article.findall(".//AbstractText"):
                    if a.text:
                        abstract_parts.append(a.text.strip())
                abstract = " ".join(abstract_parts)

                
                authors = []
                for author in article.findall(".//Author"):
                    last_name = author.findtext("LastName", "")
                    fore_name = author.findtext("ForeName", "") or author.findtext("FirstName", "")
                    if last_name and fore_name:
                        authors.append(f"{fore_name} {last_name}")
                    elif last_name:
                        authors.append(last_name)

                
                pub_date = None
                date_elem = article.find(".//PubDate")
                if date_elem is not None:
                    y = date_elem.findtext("Year")
                    m = date_elem.findtext("Month")
                    d = date_elem.findtext("Day")
                    try:
                        pub_date = datetime(
                            int(y) if y else 1900,
                            int(m) if m and m.isdigit() else 1,
                            int(d) if d and d.isdigit() else 1
                        )
                    except:
                        pass

                
                keywords = [kw.text.strip() for kw in article.findall(".//Keyword") if kw.text]

                
                if not keywords:
                    keywords = nlp.extract_keywords(abstract or title, max_keywords=10)

                papers.append({
                    "title": title,
                    "abstract": abstract,
                    "summary": generate_summary(abstract),
                    "authors": authors,
                    "source": "PubMed",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "pubmed_id": pmid,
                    "keywords": keywords,
                    "publication_date": pub_date,
                    
                    "sentiment": nlp.analyze_sentiment(abstract),
                    "objective": nlp.extract_objective(abstract),
                })

            print(f"Parsed {len(papers)} papers from pubmed xml")
            return papers

        except Exception as e:
            print(f"pubmed xml parsing error : {e}")
            return []

    def search_all_sources(self, query, limit_per_source=10):

        all_papers = []
        sources_used = []

        
        try:
            nasa_papers = self.search_nasa_technical_reports(
                query, limit_per_source)
            all_papers.extend(nasa_papers)
            if nasa_papers:
                sources_used.append('NASA Technical Reports')
        except Exception as e:
            print(f"Technical Reports error : {e}")

        
        try:
            pubmed_papers = self.search_pubmed_space_biology(
                query, limit_per_source)
            all_papers.extend(pubmed_papers)
            if pubmed_papers:
                sources_used.append('PubMed')
        except Exception as e:
            print(f"pubmed error : {e}")

        
        
        try:
            osdr_papers = self.search_osdr_genelab(
                term=query, limit=limit_per_source // 2)
            all_papers.extend(osdr_papers)
            if osdr_papers:
                sources_used.append('NASA GeneLab')
        except Exception as e:
            print(f"osdr genelab error : {e}")
        

        
        
        try:
            sb_items = self.search_sb_publication_csv(query, limit_per_source)
            
            if sb_items:
                all_papers.extend(sb_items)
                sources_used.append("SB_Publication_CSV")
        except Exception as e:
            print(f"sb publication CSV error : {e}")

        
        
        try:
            task_scraper = NASATaskBookScraper(headless=True)
            task_results = task_scraper.search_tasks(
                keywords=query,
                max_results=limit_per_source
            )
            if task_results:
                
                formatted = []
                for t in task_results:
                    formatted.append({
                        "title": t.title,
                        "abstract": t.description,
                        "authors": [t.investigator] if t.investigator else [],
                        "source": "NASA Task Book",
                        "url": t.url,
                        "doi": None,
                        "keywords": t.keywords,
                        "publication_date": t.fiscal_year,
                        "task_id": t.task_id,
                        "sentiment": nlp.analyze_sentiment(abstract),
                        "objective": nlp.extract_objective(abstract)
                    })
                all_papers.extend(formatted)
                sources_used.append("NASA Task Book")
        except Exception as e:
            print(f"task Book Scraper error : {e}")

        
        try:
            oa_papers = self.search_openalex(query, limit_per_source, is_oa=None, from_date=None)
            all_papers.extend(oa_papers)
            if oa_papers:
                sources_used.append("OpenAlex")
        except Exception as e:
            print(f"OpenAlex error: {e}")
        
        try:
            cr_papers = self.search_crossref(query, limit_per_source)
            all_papers.extend(cr_papers)
            if cr_papers:
                sources_used.append("Crossref")
        except Exception as e:
            print(f"crossref error : {e}")

        
        try:
            geo_items = self.search_ncbi_geo(query, limit_per_source)
            all_papers.extend(geo_items)
            if geo_items:
                sources_used.append("NCBI GEO")
        except Exception as e:
            print(f"NCBI GEO error: {e}")

        
        try:
            bio_items = self.search_biorxiv(query, from_date=None, to_date=None, limit=limit_per_source, server="biorxiv")
            all_papers.extend(bio_items)
            if bio_items:
                sources_used.append("bioRxiv")
        except Exception as e:
            print(f"bioRxiv error : {e}")

        
        try:
            epmc = self.search_europe_pmc(query, limit_per_source)
            all_papers.extend(epmc)
            if epmc:
                sources_used.append("Europe PMC")
        except Exception as e:
            print(f"Europe PMC error : {e}")

        
        try:
            bio = self.search_biorxiv_like(server="biorxiv", query=query, limit=limit_per_source, mode="ANY")
            all_papers.extend(bio)
            if bio:
                sources_used.append("bioRxiv")
        except Exception as e:
            print(f"bioRxiv error : {e}")

        return all_papers, sources_used

    

    def search_osdr_genelab(self, term=None, limit=10,
                            accession=None,
                            study_identifier=None,
                            phrase_filters=None):

        try:
            params = {"type": "cgene", "size": limit}

            if accession:
                params["ffield"] = "Accession.raw"
                params["fvalue"] = accession
            elif study_identifier:
                params["ffield"] = "Study Identifier.raw"
                params["fvalue"] = study_identifier
            else:
                phrases = []
                if phrase_filters:
                    phrases += [f"\"{p}\"" for p in phrase_filters if p]
                if term:
                    phrases.append(term if (term.startswith('"') and term.endswith('"')) else term)
                if phrases:
                    params["term"] = " AND ".join(phrases)

            r = self._make_request(Config.OSDR_SEARCH_URL, params)
            if not r:
                return []

            nlp = NLPService()
            data = r.json()
            results = []
            for hit in data.get("hits", {}).get("hits", []):
                src = hit.get("_source", {})
                acc = src.get("Accession", "")
                osd_id = None
                if isinstance(acc, str) and acc.startswith("OSD-"):
                    try:
                        osd_id = int(acc.split("-")[-1])
                    except:
                        pass

                results.append({
                    "title": src.get("Study Title") or src.get("Project Title") or "No Title",
                    "abstract": src.get("Study Description") or "",
                    "authors": [],
                    "source": "NASA GeneLab",
                    "url": Config.OSDR_META_URL.format(osd_id=osd_id) if osd_id else "",
                    "keywords": [k.strip() for k in (src.get("Study Factor Type") or "").split(",") if k.strip()],
                    "publication_date": src.get("Study Public Release Date"),
                    "nasa_id": acc,
                    "organism": src.get("organism"),
                    "assay_type": src.get("Study Assay Technology Type"),
                    "osd_id": osd_id,
                    "sentiment": nlp.analyze_sentiment(src.get("Study Description") or ""),
                    "objective": nlp.extract_objective(src.get("Study Description") or "")
                })

            return results

        except Exception as e:
            print(f"OSDR search error : {e}")
            return []


    def search_openalex(self, query, limit=20, is_oa=None, from_date=None):

        try:
            url = f"{Config.OPENALEX_BASE_URL}/works"
            filters = []
            if from_date:
                filters.append(f"from_publication_date:{from_date}")
            if is_oa is True:
                filters.append("is_oa:true")

            params = {
                "search": query,
                "filter": ",".join(filters) if filters else None,
                "per-page": min(200, int(limit)),
                "mailto": self.pubmed_email,
                "select": "id,doi,title,authorships,publication_year,publication_date,primary_location,open_access,abstract_inverted_index,concepts"
            }
            params = {k: v for k, v in params.items() if v is not None}

            r = self.session.get(url, params=params, timeout=30)
            if not r.ok:
                return []

            data = r.json()

            
            def _reconstruct_abstract(inv):
                if not inv:
                    return ""
                try:
                    maxpos = max(p for poss in inv.values() for p in poss)
                    words = [""] * (maxpos + 1)
                    for w, poss in inv.items():
                        for p in poss:
                            words[p] = w
                    return " ".join(x for x in words if x)
                except:
                    return ""

            nlp = NLPService()

            results = []
            for it in data.get("results", []):
                abstract_text = _reconstruct_abstract(it.get("abstract_inverted_index"))
                authors = [a.get("author", {}).get("display_name", "")
                        for a in it.get("authorships", []) if a.get("author")]

                
                keywords = [c.get("display_name") for c in it.get("concepts", [])][:10]
                if not keywords:
                    keywords = nlp.extract_keywords(abstract_text or it.get("title") or query, max_keywords=10)

                results.append({
                    "title": it.get("title") or "No Title",
                    "abstract": abstract_text,
                    "authors": [x for x in authors if x],
                    "source": "OpenAlex",
                    "url": it.get("id"),
                    "doi": (it.get("doi") or "").replace("https://doi.org/", ""),
                    "keywords": keywords,
                    "sentiment": nlp.analyze_sentiment(abstract_text or it.get("title") or query),
                    "objective": nlp.extract_objective(abstract_text or it.get("title") or query),
                    "publication_date": self._parse_date(it.get("publication_date") or it.get("publication_year"))
                })

            return results
        except Exception as e:
            print(f"openAlex search error : {e}")
            return []

    def search_crossref(self, query, limit=20):

        try:
            url = f"{Config.CROSSREF_BASE_URL}/works"
            params = {
                "query": query,
                "rows": min(100, int(limit)),
                "mailto": self.pubmed_email
            }
            r = self.session.get(url, params=params, timeout=30)
            if not r.ok:
                return []

            data = r.json()
            items = data.get("message", {}).get("items", [])
            results = []
            nlp = NLPService()
            for it in items:
                title = (it.get("title") or ["No Title"])[0]
                doi = it.get("DOI") or ""
                url = it.get("URL") or ""
                authors = []
                for a in it.get("author", []) or []:
                    name = f"{a.get('given','')} {a.get('family','')}".strip()
                    if name: authors.append(name)
                
                year = None
                if "published-print" in it:
                    year = it["published-print"]["date-parts"][0][0]
                elif "published-online" in it:
                    year = it["published-online"]["date-parts"][0][0]
                abstract = it.get("abstract") or ""
                subjects = it.get("subject", []) or []
                
                keywords = subjects
                if not keywords:
                    nlp = NLPService()
                    keywords = nlp.extract_keywords(abstract or title, max_keywords=10)

                results.append({
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "source": "Crossref",
                    "url": url,
                    "doi": doi,
                    "keywords": keywords,
                    "sentiment": nlp.analyze_sentiment(abstract or title),
                    "objective": nlp.extract_objective(abstract or title),
                    "publication_date": str(year) if year else None
                })
            return results
        except Exception as e:
            print(f"crossref search error : {e}")
            return []

    def search_ncbi_geo(self, query, limit=20):

        try:
            
            s_params = {
                "db": "gds",
                "term": query,
                "retmax": min(100, int(limit)),
                "retmode": "json",
                "api_key": self.ncbi_api_key,
                "tool": "SpaceBiologyPlatform",
                "email": self.pubmed_email
            }
            s = self.session.get(Config.PUBMED_SEARCH_URL, params=s_params, timeout=30)
            if not s.ok:
                return []
            ids = (s.json().get("esearchresult", {}) or {}).get("idlist", [])
            if not ids:
                return []

            
            e_params = {
                "db": "gds",
                "id": ",".join(ids),
                "retmode": "json",
                "api_key": self.ncbi_api_key,
                "tool": "SpaceBiologyPlatform",
                "email": self.pubmed_email
            }
            e = self.session.get(Config.PUBMED_SUMMARY_URL, params=e_params, timeout=30)
            if not e.ok:
                return []
            res = e.json().get("result", {})

            results = []
            nlp = NLPService()
            for uid in res.get("uids", []):
                v = res.get(uid, {})
                if not v:
                    continue
                acc = v.get("accession") or v.get("acc")
                
                url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}" if acc else None

                
                kw = []
                for k in (v.get("taxon"), v.get("gdstype"), v.get("ptechtype"), v.get("platformtitle")):
                    if k: kw.append(k)

                abstract = v.get("summary") or ""
                title = v.get("title") or f"GEO dataset {acc or uid}"

                results.append({
                    "title": title,
                    "abstract": abstract,
                    "authors": [],
                    "source": "NCBI GEO",
                    "url": url,
                    "doi": None,
                    "keywords": kw,
                    "publication_date": v.get("pdat"),
                    
                    "sentiment": nlp.analyze_sentiment(abstract or title),
                    "objective": nlp.extract_objective(abstract or title)
                })
            return results
        except Exception as e:
            print(f"ncbi geo search error : {e}")
            return []

    def search_biorxiv(self, query, from_date="", to_date="",
                    limit=20, server="biorxiv", match_mode="ANY", categories=None, max_pages=10):

        try:
            import html
            q_terms = [t.strip() for t in (query or "").split() if t.strip()]
            match_all = (str(match_mode).upper() == "ALL")
            want = int(limit)

            results = []
            cursor = 0
            pages = 0

            
            nlp = NLPService()

            
            def hit_filter(item):
                title = (item.get("title") or "")
                abstr = (item.get("abstract") or "")
                cat   = (item.get("category") or "")
                hay   = f"{title} {abstr} {cat}".lower()
                
                if q_terms:
                    if match_all:
                        for t in q_terms:
                            if t.lower() not in hay:
                                return False
                    else:
                        if not any(t.lower() in hay for t in q_terms):
                            return False
                
                if categories:
                    if (item.get("category") or "").lower() not in [c.lower() for c in categories]:
                        return False
                return True

            session = self.session
            base = f"{Config.BIORXIV_BASE_URL}/{server}/{from_date}/{to_date}"

            while len(results) < want and pages < max_pages:
                url = f"{base}/{cursor}/json"
                r = session.get(url, timeout=60)
                if not r.ok:
                    break

                data = r.json() or {}
                coll = data.get("collection", [])
                if not coll:
                    break

                for it in coll:
                    if not hit_filter(it):
                        continue

                    
                    authors_str = it.get("authors", "")
                    authors = [a.strip() for a in authors_str.split(";") if a.strip()]

                    
                    abstract_raw = it.get("abstract") or ""
                    abstract_txt = html.unescape(abstract_raw)
                    title = it.get("title") or "No Title"

                    results.append({
                        "title": title,
                        "abstract": abstract_txt,
                        "authors": authors,
                        "source": "bioRxiv" if server == "biorxiv" else "medRxiv",
                        "url": f"https://doi.org/{it.get('doi')}" if it.get("doi") else None,
                        "doi": it.get("doi"),
                        "keywords": [it.get("category")] if it.get("category") else [],
                        
                        "sentiment": nlp.analyze_sentiment(abstract_txt or title),
                        "objective": nlp.extract_objective(abstract_txt or title),
                        "publication_date": it.get("date")
                    })
                    if len(results) >= want:
                        break

                
                messages = data.get("messages") or []
                cursor += 100
                pages += 1

                try:
                    total = None
                    if messages and isinstance(messages[0], dict):
                        total = int(messages[0].get("total") or 0)
                    if total is not None and cursor >= total:
                        break
                except Exception:
                    pass

            return results[:want]

        except Exception as e:
            print(f"BioRxiv search error : {e}")
            return []

    def _bool(v):
        return str(v).lower() in {"1","true","y","yes","on"}


    def search_europe_pmc(self, query, limit=20, date_from=None, date_to=None):

        base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        
        
        date_filter = ""
        if date_from and date_to:
            date_filter = f' AND (FIRST_PDATE:[{date_from} TO {date_to}])'
        params = {
            "query": f"{query}{date_filter}".strip(),
            "resultType": "core",
            "pageSize": min(limit, 100),
            "format": "json"
        }

        resp = self._make_request(base_url, params=params)
        if not resp:
            return []
        data = resp.json() or {}
        results = data.get("resultList", {}).get("result", []) or []
        nlp = NLPService()
        papers = []
        for r in results[:limit]:
            title = r.get("title") or "No Title"
            abstract = r.get("abstractText") or ""
            author_str = r.get("authorString") or ""
            authors = [a.strip() for a in author_str.split(";") if a.strip()] if author_str else []
            doi = r.get("doi")
            pmid = r.get("pmid")
            src = "Europe PMC"

            url = None
            if doi:
                url = f"https://doi.org/{doi}"
            else:
                
                src_code = r.get("source") or "MED"
                rid = r.get("id") or (pmid or "")
                if rid:
                    url = f"https://europepmc.org/abstract/{src_code}/{rid}"

            
            pub_date = None
            first_pub = r.get("firstPublicationDate")
            if first_pub:
                pub_date = self._parse_date(first_pub)
            elif r.get("pubYear"):
                try:
                    pub_date = datetime(int(r["pubYear"]), 1, 1)
                except:
                    pass

            subjects = r.get("subject") or r.get("subjectList") or r.get("keywords") or []
            papers.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "source": src,
                "url": url or "",
                "keywords": self._get_keywords(subjects, abstract or title),
                "publication_date": pub_date,
                "pubmed_id": pmid,
                "sentiment": nlp.analyze_sentiment(abstract or title),
                "objective": nlp.extract_objective(abstract or title),
                "doi": doi
            })

        
        
        
        try:
            
            history = SearchHistory(
                query=query,
                results_count=len(papers),
                user_ip=request.remote_addr if request else None,
                filters_used=json.dumps({
                    "date_from": date_from,
                    "date_to": date_to,
                    "limit": limit
                }),
                sources_searched=json.dumps(["Europe PMC"])
            )
            db.session.add(history)

            
            for r in papers:
                exists = None
                if r.get("doi"):
                    exists = Paper.query.filter_by(doi=r["doi"]).first()
                elif r.get("pubmed_id"):
                    exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()

                if not exists:
                    pub_date = None
                    try:
                        pub_date = normalize_publication_date(r.get("publication_date"))
                    except Exception as e:
                        print(f"database : publication_date parse error for '{r.get('title')}' : {e}")

                    paper_obj = Paper(
                        title=r.get("title"),
                        abstract=r.get("abstract"),
                        authors=json.dumps(r.get("authors", [])),
                        source=r.get("source"),
                        url=r.get("url"),
                        keywords=json.dumps(r.get("keywords", [])),
                        publication_date=pub_date,
                        doi=r.get("doi"),
                        pubmed_id=r.get("pubmed_id"),
                        nasa_id=r.get("nasa_id"),
                        sentiment=r.get("sentiment"),
                        objective=r.get("objective")
                    )
                    db.session.add(paper_obj)

            db.session.commit()
        except Exception as db_err:
            db.session.rollback()
            print(f"database error : {db_err}")
        

        return papers


    def search_biorxiv_like(self, server="biorxiv", query="", date_from=None, date_to=None,
                            limit=20, mode="ANY", max_pages=3):

        import re
        base = "https://api.biorxiv.org/details"
        if not (date_from and date_to):
            
            today = datetime.utcnow().date()
            date_to = date_to or today.isoformat()
            date_from = date_from or f"{today.year-2}-01-01"

        
        terms = [t for t in re.split(r"\s+", query.strip()) if t]
        def match_any(title, abstract):
            text = f"{title}\n{abstract}".lower()
            return any(t.lower() in text for t in terms) if terms else True
        def match_all(title, abstract):
            text = f"{title}\n{abstract}".lower()
            return all(t.lower() in text for t in terms) if terms else True
        matcher = match_all if mode == "ALL" else match_any

        collected = []
        cursor = 0
        page = 0
        while len(collected) < limit and page < max_pages:
            url = f"{base}/{server}/{date_from}/{date_to}/{cursor}/json"
            resp = self._make_request(url)
            if not resp:
                break
            data = resp.json() or {}
            coll = data.get("collection", []) or []
            if not coll:
                break

            for it in coll:
                title = it.get("title") or "No Title"
                abstract = it.get("abstract") or ""
                if not matcher(title, abstract):
                    continue

                
                a_str = it.get("authors") or ""
                authors = [a.strip() for a in a_str.split(";") if a.strip()]

                doi = it.get("doi")
                pub_date = self._parse_date(it.get("date"))
                src = "medRxiv" if server.lower() == "medrxiv" else "bioRxiv"
                url_paper = f"https://doi.org/{doi}" if doi else ""

                collected.append({
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "source": src,
                    "url": url_paper,
                    "keywords": [it.get("category")] if it.get("category") else [],
                    "publication_date": pub_date,
                    "doi": doi
                })
                if len(collected) >= limit:
                    break

            
            page += 1
            cursor += 100

        return collected[:limit]






class NLPService:
    def __init__(self):
        self.space_biology_keywords = [
            'microgravity', 'space', 'astronaut', 'radiation', 'bone loss',
            'muscle atrophy', 'plant growth', 'cellular changes', 'orbit',
            'ISS', 'weightlessness', 'cosmic radiation', 'space medicine',
            'astrobiology', 'zero gravity', 'bone density',
            'DNA damage', 'protein expression', 'metabolism', 'adaptation',
            'exercise', 'countermeasures', 'calcium', 'osteoporosis',
            'genetic effects', 'stress response', 'root development',
            'space flight', 'mars', 'lunar', 'space station', 'spacewalk'
        ]

    def extract_keywords(self, text, max_keywords=10):

        if not text:
            return []

        text_lower = text.lower()
        keywords = []

        
        for kw in self.space_biology_keywords:
            if kw in text_lower and kw not in keywords:
                keywords.append(kw)

        
        if NLTK_AVAILABLE:

            stops = set(stopwords.words("english"))
            tokens = [w for w in word_tokenize(text_lower) if w.isalpha() and w not in stops]

            
            tagged = pos_tag(tokens)
            nouns_adjs = [w for w, pos in tagged if pos.startswith("NN") or pos.startswith("JJ")]

            
            freq = Counter(nouns_adjs)
            for w, _ in freq.most_common(max_keywords):
                if w not in keywords and len(w) > 3:
                    keywords.append(w)
        else:
            
            words = re.findall(r'\b[a-zA-Z]{4,}\b', text_lower)
            freq = Counter(words)
            for w, _ in freq.most_common(max_keywords):
                if w not in keywords:
                    keywords.append(w)

        return keywords[:max_keywords]



    def analyze_concepts(self, text):

        try:
            concepts = []
            keywords = self.extract_keywords(text)

            for keyword in keywords:
                category = self._categorize_concept(keyword)
                concepts.append({
                    'concept': keyword.replace(' ', '_'),
                    'confidence': min(0.9, 0.6 + (len(keyword) / 20)),
                    'category': category
                })

            return concepts

        except Exception as e:
            print(f"Concept analysis error : {e}")
            return []

    def analyze_sentiment(self, text):
        if not text:
            return "neutral"
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            if polarity > 0.1:
                return "positive"
            elif polarity < -0.1:
                return "negative"
            return "neutral"
        except:
            return "neutral"

    def extract_objective(self, text):

        if not text:
            return ""
        sentences = text.split(".")
        for s in sentences:
            if any(word in s.lower() for word in ["objective", "aim", "goal", "purpose"]):
                return s.strip()
        return sentences[0].strip() if sentences else ""

    def _categorize_concept(self, concept):

        categories = {
            'space_biology': ['microgravity', 'space', 'orbit', 'weightlessness', 'astrobiology', 'zero gravity'],
            'medicine': ['bone loss', 'muscle atrophy', 'astronaut', 'space medicine', 'bone density', 'osteoporosis'],
            'physics': ['radiation', 'cosmic radiation', 'gravity'],
            'botany': ['plant growth', 'cellular changes', 'root development'],
            'genetics': ['DNA damage', 'genetic effects', 'protein expression'],
            'physiology': ['metabolism', 'adaptation', 'stress response', 'exercise', 'countermeasures']
        }

        for category, terms in categories.items():
            if any(term in concept.lower() for term in terms):
                return category

        return 'general'


class SearchService:


    def __init__(self):
        self.nasa_service = RealNASAService()
        self.nlp_service = NLPService()

    def search_papers(self, query, filters=None, user_ip=None):

        try:
            if not query.strip():
                return []

            filters = filters or {}
            all_results = []
            sources_used = []

            
            source = filters.get('source')
            if isinstance(source, str):
                source = source.lower()
            else:
                source = ""

            
            if source == "pubmed":
                all_results = self.nasa_service.search_pubmed(query, limit=20)
                sources_used.append("PubMed")

            
            elif source == "taskbook":
                taskbook_results = self.nasa_service.search_nasa_taskbook(query, limit=20)
                if taskbook_results:
                    all_results.extend(taskbook_results)
                    sources_used.append("NASA TaskBook")

            else:
                
                db_results = self._search_local_database(query, filters)
                if db_results:
                    all_results.extend(db_results)
                    sources_used.append('Local Database')

                
                if len(all_results) < 10:
                    api_results, api_sources = self.nasa_service.search_all_sources(
                        query, 15
                    )

                    for paper_data in api_results:
                        saved_paper = self._save_paper_to_db(paper_data)
                        if saved_paper:
                            all_results.append(saved_paper.to_dict())

                    sources_used.extend(api_sources)

            
            all_results = self._remove_duplicates(all_results)

            
            filtered_results = self._apply_filters(all_results, filters)

            
            final_results = filtered_results[:Config.MAX_SEARCH_RESULTS]

            
            self._record_search(query, len(final_results),
                                filters, user_ip, sources_used)

            return final_results

        except Exception as e:
            print("search service error :", e)
            traceback.print_exc()
            return []

    def _search_local_database(self, query, filters):

        try:
            db_query = db.session.query(Paper)

            
            if query:
                db_query = db_query.filter(
                    db.or_(
                        Paper.title.contains(query),
                        Paper.abstract.contains(query),
                        Paper.keywords.contains(query)
                    )
                )

            
            if filters.get('source'):
                db_query = db_query.filter(Paper.source == filters['source'])

            if filters.get('date_from'):
                date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d')
                db_query = db_query.filter(Paper.publication_date >= date_from)

            if filters.get('date_to'):
                date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d')
                db_query = db_query.filter(Paper.publication_date <= date_to)

            papers = db_query.limit(20).all()
            return [paper.to_dict() for paper in papers]

        except Exception as e:
            print(f"local database search error : {e}")
            return []

    def _save_paper_to_db(self, paper_data):

        try:
            
            existing = None
            if paper_data.get('pubmed_id'):
                existing = Paper.query.filter_by(pubmed_id=paper_data['pubmed_id']).first()
            elif paper_data.get('title'):
                existing = Paper.query.filter_by(title=paper_data['title']).first()

            if existing:
                return existing

            
            pub_raw = paper_data.get('publication_date')
            pub_dt = normalize_publication_date(pub_raw)

            
            paper = Paper(
                title=paper_data.get('title', 'No Title'),
                abstract=paper_data.get('abstract', ''),
                authors=json.dumps(paper_data.get('authors', [])),
                source=paper_data.get('source', 'Unknown'),
                url=paper_data.get('url', ''),
                keywords=json.dumps(paper_data.get('keywords', [])),
                publication_date=pub_dt,
                pubmed_id=paper_data.get('pubmed_id'),
                nasa_id=paper_data.get('nasa_id'),
                doi=paper_data.get('doi'),
                sentiment=nlp.analyze_sentiment(item["abstract"]),
                objective=nlp.extract_objective(item["abstract"])
            )

            db.session.add(paper)
            db.session.commit()

            return paper

        except Exception as e:
            print(f"error saving paper to database : {e}")
            db.session.rollback()
            return None

    def _remove_duplicates(self, papers):

        seen_titles = set()
        unique_papers = []

        for paper in papers:
            title = (paper.get('title') or "").lower().strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_papers.append(paper)

        return unique_papers

    def _apply_filters(self, papers, filters):

        if not filters:
            return papers

        filtered = []
        for paper in papers:
            
            if filters.get('source') and paper.get('source') != filters['source']:
                continue

            
            pub_date = paper.get('publication_date')
            if pub_date:
                try:
                    if isinstance(pub_date, str):
                        pub_date = datetime.fromisoformat(
                            pub_date.replace('Z', ''))

                    if filters.get('date_from'):
                        date_from = datetime.strptime(
                            filters['date_from'], '%Y-%m-%d')
                        if pub_date < date_from:
                            continue

                    if filters.get('date_to'):
                        date_to = datetime.strptime(
                            filters['date_to'], '%Y-%m-%d')
                        if pub_date > date_to:
                            continue
                except:
                    pass

            filtered.append(paper)

        return filtered

    def _record_search(self, query, results_count, filters, user_ip, sources_used):

        try:
            search_record = SearchHistory(
                query=query,
                results_count=results_count,
                user_ip=user_ip,
                filters_used=json.dumps(filters),
                sources_searched=json.dumps(sources_used)
            )
            db.session.add(search_record)
            db.session.commit()
        except Exception as e:
            print(f"Error recording search : {e}")
            db.session.rollback()


class GraphService:


    def __init__(self):
        self.nlp_service = NLPService()

    def generate_knowledge_graph(self, query=None, max_nodes=50):

        try:
            
            if query:
                papers = Paper.query.filter(
                    db.or_(
                        Paper.title.contains(query),
                        Paper.abstract.contains(query)
                    )
                ).limit(20).all()
            else:
                papers = Paper.query.order_by(
                    Paper.created_at.desc()).limit(20).all()

            
            nodes = []
            links = []
            concept_map = {}

            for paper in papers:
                
                paper_node = {
                    'id': f"paper_{paper.id}",
                    'name': paper.title[:50] + "" if len(paper.title) > 50 else paper.title,
                    'type': 'paper',
                    'category': 'paper',
                    'value': 5,
                    'data': paper.to_dict()
                }
                nodes.append(paper_node)

                
                concepts = self.nlp_service.analyze_concepts(
                    f"{paper.title} {paper.abstract}"
                )

                for concept_data in concepts:
                    concept_id = concept_data['concept']

                    if concept_id not in concept_map:
                        concept_node = {
                            'id': concept_id,
                            'name': concept_id.replace('_', ' ').title(),
                            'type': 'concept',
                            'category': concept_data['category'],
                            'value': 3,
                            'confidence': concept_data['confidence']
                        }
                        nodes.append(concept_node)
                        concept_map[concept_id] = len(nodes) - 1

                    
                    link = {
                        'source': f"paper_{paper.id}",
                        'target': concept_id,
                        'value': concept_data['confidence']
                    }
                    links.append(link)

            
            nodes = nodes[:max_nodes]
            links = links[:Config.MAX_GRAPH_LINKS]

            return {
                'nodes': nodes,
                'links': links,
                'total_nodes': len(nodes),
                'total_links': len(links)
            }

        except Exception as e:
            print(f"Knowledge graph generation error: {e}")
            return {'nodes': [], 'links': [], 'total_nodes': 0, 'total_links': 0}


def init_database(app):

    with app.app_context():
        db_path = Config.DATABASE_PATH
        db_dir = os.path.dirname(db_path)

        
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
                print(f"database create directory : {db_dir}")
            except Exception as e:
                print(f"error create database directory : {e}")

        
        try:
            test_file = os.path.join(os.path.dirname(
                db_path) or '.', 'test_write.tmp')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print("write permission ok")
        except PermissionError:
            print("permission denied")
            return False
        except Exception as e:
            print(f"write permission error : {e}")
            return False

        try:
            
            db.create_all()
            print(f"Database create successfully at : {db_path}")
            return True
        except Exception as e:
            print(f"error creating database tables : {e}")
            return False


def get_database_stats():

    try:
        stats = {
            'total_papers': Paper.query.count(),
            'total_knowledge_nodes': KnowledgeNode.query.count(),
            'total_searches': SearchHistory.query.count(),
            'recent_papers': [p.to_dict() for p in Paper.query.order_by(Paper.created_at.desc()).limit(5).all()]
        }
        return stats
    except Exception as e:
        print(f"Error getting database stats: {e}")
        return {
            'total_papers': 0,
            'total_knowledge_nodes': 0,
            'total_searches': 0,
            'recent_papers': []
        }



def create_app():

    app = Flask(__name__)
    app.config.from_object(Config)

    
    db.init_app(app)

    return app


app = create_app()


search_service = SearchService()
graph_service = GraphService()
nlp_service = NLPService()


def filter_by_date(papers, date_from=None, date_to=None):

    df = normalize_publication_date(date_from) if date_from else None
    dt = normalize_publication_date(date_to) if date_to else None

    filtered = []
    for p in papers:
        pub_raw = p.get("publication_date")
        pub_dt = normalize_publication_date(pub_raw)
        if not pub_dt:
            continue

        ok = True
        if df and pub_dt < df:
            ok = False
        if dt and pub_dt > dt:
            ok = False

        if ok:
            filtered.append(p)

    return filtered



@app.route('/dashboard')
def render():
    return render_template('index.html')


@app.route('/')
def dashboard():

    try:
        
        stats = get_database_stats()

        
        recent_searches = SearchHistory.query.order_by(
            SearchHistory.search_time.desc()
        ).limit(5).all()

        dashboard_data = {
            'message': 'Space Biology Research Platform API - LIVE VERSION',
            'version': '2.0.0',
            'stats': stats,
            'recent_searches': [search.to_dict() for search in recent_searches],
            'endpoints': {
                'search': '/api/search',
                'papers': '/api/papers',
                'stats': '/api/stats',
                'knowledge_graph': '/api/knowledge-graph',
                'reports': '/api/reports/activity',
                'health': '/health'
            }
        }

        return jsonify(dashboard_data)

    except Exception as e:
        print(f"Error loading dashboard: {e}")
        return jsonify({
            'error': 'Dashboard error',
            'message': 'Space Biology Research Platform API - LIVE VERSION',
            'version': '2.0.0',
            'endpoints': {
                'search': '/api/search',
                'papers': '/api/papers',
                'stats': '/api/stats',
                'knowledge_graph': '/api/knowledge-graph',
                'reports': '/api/reports/activity',
                'health': '/health'
            }
        })



@app.route('/health')
def health_check():

    try:
        
        db.session.execute(db.text('SELECT 1'))
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500




@app.route("/api/sb_publication/search")
def sb_publication_search_route():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": False, "error": "q is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 200)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    results = svc.search_sb_publication_csv(q, limit=limit)

    
    results = filter_by_date(results, date_from, date_to)

    
    for item in results:
        try:
            abstract_text = (item.get('abstract') or "").strip()
            if abstract_text:
                if len(abstract_text) >= 120:
                    item['abstract'] = summarize_text(abstract_text)
                else:
                    item['abstract'] = abstract_text
        except Exception as e:
            print(f"[sb_publication_search_route] summarization failed for item '{item.get('title')}': {e}")
            item['abstract'] = item.get('abstract') or ""

    
    
    
    try:
        
        history = SearchHistory(
            query=q,
            results_count=len(results),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit
            }),
            sources_searched=json.dumps(["SB Publication"])
        )
        db.session.add(history)

        
        for r in results:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("pubmed_id"):
                exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()

            if not exists:
                pub_date = None
                try:
                    pub_date = normalize_publication_date(r.get("publication_date"))
                except Exception as e:
                    print(f"[DB] publication_date parse error for '{r.get('title')}': {e}")

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"database error : {db_err}")
    

    
    session_id = request.args.get('session_id','advanced')
    chatbot_payload = call_chatbot_with_results(
        items=results,
        source="SB_Publication",
        q=q,
        session_id=session_id
    )

    return jsonify({
    "success": True,
    "query": q,
    "count": len(results),
    "results": results,
    "chatbot": chatbot_payload
    })



@app.route("/api/taskbook/search", methods=["GET"])
def search_taskbook():

    try:
        query = request.args.get("q", "").strip()
        year = request.args.get("year")
        program = request.args.get("program")
        limit = int(request.args.get("limit", 10))
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        if not query:
            return jsonify({"error" : "query (q) is required"}), 400

        scraper = NASATaskBookScraper(headless=True)
        results = scraper.search_tasks(
            programs=[program] if program else None,
            fiscal_year=year,
            keywords=query,
            max_results=limit
        )

        nlp = NLPService()
        formatted = []

        for t in results:
            
            abstract_text = (t.description or "").strip()
            try:
                if abstract_text and len(abstract_text) >= 120:
                    abstract_text = summarize_text(abstract_text)
            except Exception as e:
                print(f"search taskbook : summarization failed for task '{t.title}': {e}")

            
            keywords = t.keywords or []
            if not keywords:
                keywords = nlp.extract_keywords(abstract_text or t.title, max_keywords=10)

            formatted.append({
                "title": t.title or "No Title",
                "abstract": abstract_text,
                "authors": [t.investigator] if t.investigator else [],
                "source": "NASA Task Book",
                "url": t.url,
                "doi": None,
                "keywords": keywords,
                "publication_date": t.fiscal_year,
                "task_id": t.task_id,
                "institution": t.institution,
                "program": t.program,
                "status": t.status,
                "funding": t.funding,
                "start_date": t.start_date,
                "end_date": t.end_date,
                "objective": nlp.extract_objective(abstract_text or t.title),
                "sentiment": nlp.analyze_sentiment(abstract_text or t.title),
                "publications": t.publications
            })

        
        formatted = filter_by_date(formatted, date_from, date_to)

        
        
        
        try:
            
            history = SearchHistory(
                query=query,
                results_count=len(formatted),
                user_ip=request.remote_addr,
                filters_used=json.dumps({
                    "date_from": date_from,
                    "date_to": date_to,
                    "limit": limit,
                    "year": year,
                    "program": program
                }),
                sources_searched=json.dumps(["NASA Task Book"])
            )
            db.session.add(history)

            
            for r in formatted:
                exists = None
                if r.get("task_id"):
                    exists = Paper.query.filter_by(nasa_id=r["task_id"]).first()

                if not exists:
                    pub_date = None
                    try:
                        pub_date = normalize_publication_date(r.get("publication_date"))
                    except Exception as e:
                        print(f"database : publication_date parse error '{r.get('title')}' : {e}")

                    paper_obj = Paper(
                        title=r.get("title"),
                        abstract=r.get("abstract"),
                        authors=json.dumps(r.get("authors", [])),
                        source=r.get("source"),
                        url=r.get("url"),
                        keywords=json.dumps(r.get("keywords", [])),
                        publication_date=pub_date,
                        doi=r.get("doi"),
                        pubmed_id=r.get("pubmed_id"),
                        nasa_id=r.get("task_id"),
                        sentiment=r.get("sentiment"),
                        objective=r.get("objective")
                    )
                    db.session.add(paper_obj)

            db.session.commit()
        except Exception as db_err:
            db.session.rollback()
            print(f"database error : {db_err}")
        

        
        session_id = request.args.get('session_id','advanced')
        chatbot_payload = call_chatbot_with_results(
            items=formatted,
            source="NASA Task Book",
            q=query,
            session_id=session_id
        )

        return jsonify({
            "query": query,
            "count": len(formatted),
            "results": formatted,
            "success": True,
            "chatbot": chatbot_payload
        })


    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500



@app.route("/api/nslsl/search", methods=["GET"])
def nslsl_search_route():

    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": False, "error": " (q) is required"}), 400

    limit = int(request.args.get("limit", 5))
    headless = request.args.get("headless", "true").lower() == "true"
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    scraper = None
    try:
        scraper = NSLSLScraper(headless=headless)
        articles = scraper.search_topic(q, max_results=limit)

        nlp = NLPService()
        results = []

        for art in articles:
            abstract_text = (art.abstract or "").strip()

            
            try:
                if abstract_text and len(abstract_text) >= 120:
                    abstract_text = summarize_text(abstract_text)
            except Exception as e:
                print(f"nslsl : summarization failed for article '{art.title}' : {e}")

            
            keywords = art.keywords or []
            if not keywords:
                keywords = nlp.extract_keywords(abstract_text or art.title, max_keywords=10)

            results.append({
                "title": art.title or "No Title",
                "authors": art.authors or [],
                "journal": art.journal or None,
                "publication_date": art.publication_date or None,
                "doi": art.doi or None,
                "abstract": abstract_text or "",
                "url": art.url or None,
                "keywords": keywords,
                "source": "NSLSL Scraper",
                "summary": generate_summary(abstract_text),
                "sentiment": nlp.analyze_sentiment(abstract_text),
                "objective": nlp.extract_objective(abstract_text),
            })

        
        results = filter_by_date(results, date_from, date_to)

        
        
        
        try:
            
            history = SearchHistory(
                query=q,
                results_count=len(results),
                user_ip=request.remote_addr,
                filters_used=json.dumps({
                    "date_from": date_from,
                    "date_to": date_to,
                    "limit": limit,
                    "headless": headless
                }),
                sources_searched=json.dumps(["NSLSL Scraper"])
            )
            db.session.add(history)

            
            for r in results:
                exists = None
                if r.get("doi"):
                    exists = Paper.query.filter_by(doi=r["doi"]).first()

                if not exists:
                    pub_date = None
                    try:
                        pub_date = normalize_publication_date(r.get("publication_date"))
                    except Exception as e:
                        print(f"database : publication_date parse error for '{r.get('title')}' : {e}")

                    paper_obj = Paper(
                        title=r.get("title"),
                        abstract=r.get("abstract"),
                        authors=json.dumps(r.get("authors", [])),
                        source=r.get("source"),
                        url=r.get("url"),
                        keywords=json.dumps(r.get("keywords", [])),
                        publication_date=pub_date,
                        doi=r.get("doi"),
                        pubmed_id=None,
                        nasa_id=None,
                        sentiment=r.get("sentiment"),
                        objective=r.get("objective")
                    )
                    db.session.add(paper_obj)

            db.session.commit()
        except Exception as db_err:
            db.session.rollback()
            print(f"database : {db_err}")
        

        
        session_id = request.args.get('session_id','advanced')
        chatbot_payload = call_chatbot_with_results(
            items=results,
            source="NSLSL",
            q=q,
            session_id=session_id
        )

        return jsonify({
            "success": True,
            "query": q,
            "count": len(results),
            "results": results,
            "chatbot": chatbot_payload
        })


    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if scraper:
            scraper.close()



@app.route("/api/ai_Analysis")
def api_ai_analysis():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": " (q) is required"}), 400

    
    
    papers = Paper.query.filter(
        Paper.title.ilike(f"%{q}%") | Paper.abstract.ilike(f"%{q}%")
    ).all()

    sentiments = {"positive": 0, "negative": 0, "neutral": 0}
    keyword_counter = Counter()
    topic_counter = Counter()

    for p in papers:
        text = (p.abstract or "") + " " + (p.title or "")
        doc = nlp(text)

        
        polarity = None
        try:
            if Doc.has_extension("blob") and getattr(doc._, "blob", None) is not None:
                polarity = getattr(doc._.blob, "polarity", None)
            elif Doc.has_extension("polarity"):
                polarity = getattr(doc._, "polarity", None)
            elif hasattr(doc._, "sentiment"):
                s = getattr(doc._, "sentiment", None)
                if isinstance(s, (tuple, list)) and len(s) >= 1:
                    polarity = s[0]
                elif isinstance(s, dict) and "polarity" in s:
                    polarity = s["polarity"]
        except Exception:
            polarity = None

        if polarity is None:
            polarity = 0.0

        if polarity > 0.05:
            sent = "positive"
        elif polarity < -0.05:
            sent = "negative"
        else:
            sent = "neutral"

        sentiments[sent] += 1

        
        kws = []
        try:
            kws = json.loads(p.keywords or "[]")
            if isinstance(kws, dict):
                kws = list(kws.keys())
            elif isinstance(kws, str):
                kws = [kw.strip() for kw in kws.split(",") if kw.strip()]
        except Exception:
            if p.keywords:
                kws = [kw.strip() for kw in p.keywords.split(",") if kw.strip()]

        keyword_counter.update(kws)

        
        for ent in doc.ents:
            
            if ent.label_ in ["PERSON", "WORK_OF_ART"]:
                continue
            topic_counter[ent.text.lower()] += 1

        print(f"debug : {text[:50]}... -> polarity: {polarity}, sentiment: {sent}")

    return jsonify({
        "query": q,
        "sentiment": sentiments,
        "keywords": [{"word": k, "count": v} for k, v in keyword_counter.most_common(10)],
        "topics": dict(topic_counter.most_common(10))
    })



@app.route("/api/osdr/search")
def osdr_search_route():
    term = request.args.get("term")
    limit = min(int(request.args.get("limit", 10)), 50)
    accession = request.args.get("accession")
    study_identifier = request.args.get("study_identifier")
    phrases = request.args.getlist("phrase")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    results = svc.search_osdr_genelab(
        term=term,
        limit=limit,
        accession=accession,
        study_identifier=study_identifier,
        phrase_filters=phrases if phrases else None
    )

    
    results = filter_by_date(results, date_from, date_to)

    
    for item in results:
        abstract_text = (item.get("abstract") or "").strip()
        try:
            if abstract_text and len(abstract_text) >= 120:
                abstract_text = summarize_text(abstract_text)
        except Exception as e:
            print(f"osdr :  summarization failed for item '{item.get('title')}' : {e}")
        item["abstract"] = abstract_text

    
    
    
    try:
        
        history = SearchHistory(
            query=term or "",
            results_count=len(results),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "accession": accession,
                "study_identifier": study_identifier,
                "phrases": phrases,
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit
            }),
            sources_searched=json.dumps(["OSDR"])
        )
        db.session.add(history)

        
        for r in results:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("pubmed_id"):
                exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()
            elif r.get("nasa_id"):
                exists = Paper.query.filter_by(nasa_id=r["nasa_id"]).first()

            if not exists:
                
                pub_date_raw = r.get("publication_date")
                pub_date = None
                try:
                    pub_date = normalize_publication_date(pub_date_raw)
                except Exception as e:
                    print(f"database publication_date parse error '{r.get('title')}' : {e}")
                    pub_date = None

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"database error : {db_err}")
    

    
    session_id = request.args.get('session_id','advanced')
    q_text = term or accession or study_identifier or (", ".join(phrases) if phrases else "")
    chatbot_payload = call_chatbot_with_results(
        items=results,
        source="OSDR",
        q=q_text,
        session_id=session_id
    )

    return jsonify({"success": True, "count": len(results), "results": results, "chatbot": chatbot_payload})


@app.route('/api/search')
def api_search():

    try:
        query = request.args.get('query', '').strip()
        if not query:
            return jsonify({
                'success': False,
                'error': ' (query) parameter is required',
                'results': []
            }), 400

        
        source = request.args.get('source', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        limit = min(int(request.args.get('limit', 20)), 100)

        
        filters = {
            'source': source or None,
            'date_from': date_from or None,
            'date_to': date_to or None
        }

        
        results = search_service.search_papers(
            query=query,
            filters=filters,
            user_ip=request.remote_addr
        )

        
        results = results[:limit]

        
        session_id = request.args.get('session_id', 'advanced')
        chatbot_payload = call_chatbot_with_results(
            items=results,
            source=(filters.get('source') or "best sources"),
            q=query,
            session_id=session_id
        )

        
        
        
        try:
            
            history = SearchHistory(
                query=query,
                results_count=len(results),
                user_ip=request.remote_addr,
                filters_used=json.dumps(filters),
                sources_searched=json.dumps([r.get("source") for r in results])
            )
            db.session.add(history)

            
            for r in results:
                paper = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=r.get("publication_date"),
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper)

            db.session.commit()
        except Exception as db_err:
            db.session.rollback()
            print(f"databse :  {db_err}")
        

        return jsonify({
            'success': True,
            'query': query,
            'total_results': len(results),
            'results': results,
            'filters_applied': {
                'source': filters['source'],
                'date_from': filters['date_from'],
                'date_to': filters['date_to'],
                'limit': limit
            },
            'chatbot': chatbot_payload,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"Search api error : {e}")
        return jsonify({
            'success': False,
            'error': 'Search failed',
            'details': str(e),
            'results': []
        }), 500



@app.route('/api/papers/<int:paper_id>')
def api_paper_detail(paper_id):

    try:
        paper = Paper.query.get(paper_id)
        if not paper:
            return jsonify({'error': 'Paper not found'}), 404

        return jsonify({
            'success': True,
            'paper': paper.to_dict(),
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"Paper detail error : {e}")
        return jsonify({'error' : 'failed to fetch paper details', 'details': str(e)}), 500


@app.route('/api/stats')
def api_stats():

    try:
        
        paper_count = db.session.query(Paper).count()
        node_count = db.session.query(KnowledgeNode).count()
        search_count = db.session.query(SearchHistory).count()

        
        all_searches = db.session.query(SearchHistory).all()

        
        today = datetime.utcnow().date()
        searches_today = sum(
            1 for search in all_searches
            if search.search_time.date() == today
        )

        
        total_results = sum(search.results_count for search in all_searches)
        avg_results = round(total_results / len(all_searches),
                            2) if all_searches else 0

        
        recent_papers_query = db.session.query(Paper).order_by(
            Paper.created_at.desc()).limit(5).all()
        recent_papers = [paper.to_dict() for paper in recent_papers_query]

        
        query_counts = {}
        for search in all_searches:
            query_counts[search.query] = query_counts.get(search.query, 0) + 1

        top_queries = sorted(query_counts.items(),
                             key=lambda x: x[1], reverse=True)[:5]

        
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_searches = [
            search for search in all_searches
            if search.search_time >= week_ago
        ]

        
        recent_searches_query = db.session.query(SearchHistory).order_by(
            SearchHistory.search_time.desc()
        ).limit(5).all()
        recent_searches = [search.to_dict() for search in recent_searches_query]

        return jsonify({
            'success': True,
            'stats': {
                'database': {
                    'total_papers': paper_count,
                    'total_knowledge_nodes': node_count,
                    'total_searches': search_count,
                    'recent_papers': recent_papers,
                    'recent_searches': recent_searches
                },
                'search_activity': {
                    'searches_today': searches_today,
                    'total_results_found': total_results,
                    'average_results_per_search': avg_results,
                    'searches_this_week': len(recent_searches)
                },
                'top_queries': [
                    {'query': query, 'count': count}
                    for query, count in top_queries
                ],
                'system': {
                    'uptime': 'Active',
                    'status': 'Operational',
                    'last_updated': datetime.utcnow().isoformat()
                }
            },
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"Stats API error : {e}")
        return jsonify({
            'success': False,
            'error': ' Statistics retrieval failed. ',
            'details': str(e)
        }), 500



@app.route("/api/biorxiv/search")
def api_biorxiv_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": False, "error": " (q) is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 500)
    from_date = request.args.get("from", None)
    to_date = request.args.get("to", None)
    server = request.args.get("server", "biorxiv")
    match_mode = request.args.get("mode", "ANY")
    cats_raw = (request.args.get("categories") or "").strip()
    categories = [c.strip() for c in cats_raw.split(",") if c.strip()] if cats_raw else None
    max_pages = min(int(request.args.get("max_pages", 10)), 50)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    items = svc.search_biorxiv(
        q, from_date=from_date, to_date=to_date,
        limit=limit, server=server, match_mode=match_mode,
        categories=categories, max_pages=max_pages
    )

    
    items = filter_by_date(items, date_from, date_to)

    
    for item in items:
        abstract_text = (item.get("abstract") or "").strip()
        
        try:
            summarizer = globals().get("summarize_text", None)
            if callable(summarizer) and abstract_text and len(abstract_text) >= 120:
                abstract_text = summarizer(abstract_text)
            else:
                abstract_text = generate_summary(abstract_text)
        except Exception as e:
            print(f"biorxix : summarization failed for item '{item.get('title')}' : {e}")
            abstract_text = generate_summary(abstract_text)
        item["abstract"] = abstract_text

    
    
    
    try:
        
        history = SearchHistory(
            query=q,
            results_count=len(items),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "from": from_date,
                "to": to_date,
                "server": server,
                "mode": match_mode,
                "categories": categories,
                "limit": limit
            }),
            sources_searched=json.dumps([server])
        )
        db.session.add(history)

        
        for r in items:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("pubmed_id"):
                exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()

            if not exists:
                
                pub_date_raw = r.get("publication_date")
                pub_date = None
                try:
                    
                    pub_date = normalize_publication_date(pub_date_raw)
                    
                    if pub_date is None and pub_date_raw:
                        print(f"database : not parse publication_date for '{r.get('title')}', value={pub_date_raw!r}")
                except Exception as e:
                    print(f"database error : publication_date parse error for '{r.get('title')}' : {e}")
                    pub_date = None

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"databse Error : {db_err}")
    

    
    session_id = request.args.get('session_id','advanced')
    label = ("medRxiv" if server.lower() == "medrxiv" else "bioRxiv")
    chatbot_payload = call_chatbot_with_results(
        items=items,
        source=label,
        q=q,
        session_id=session_id
    )

    return jsonify({
        "success": True,
        "query": q,
        "count": len(items),
        "results": items,
        "chatbot": chatbot_payload
    })





@app.route("/api/europepmc/search")
def europepmc_search_route():
    q = (request.args.get("q") or request.args.get("query") or "").strip()
    if not q:
        return jsonify({"success": False, "error": " (q) is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 100)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    papers = svc.search_europe_pmc(q, limit=limit)

    
    papers = filter_by_date(papers, date_from, date_to)

    for paper in papers:
        doi = paper.get("doi")
        pmid = paper.get("pubmed_id")
        url = paper.get("url") or ""

        abstract_text = (paper.get("abstract") or "").strip()

        
        if not abstract_text or len(abstract_text) < 50:
            fetched_abstract = ""
            if pmid:
                pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                fetched_abstract = svc._fetch_abstract_from_url(pubmed_url, pmid=pmid)
            elif doi:
                fetched_abstract = svc._fetch_abstract_from_url(f"https://doi.org/{doi}", doi=doi)
            else:
                fetched_abstract = svc._fetch_abstract_from_url(url)

            if fetched_abstract:
                abstract_text = fetched_abstract
                paper["abstract"] = abstract_text

        
        try:
            if abstract_text and len(abstract_text) >= 120:
                paper["abstract"] = summarize_text(abstract_text)
            else:
                paper["abstract"] = abstract_text
        except Exception as e:
            print(f"europepmc : summarization failed for '{paper.get('title')}' : {e}")
            paper["abstract"] = abstract_text

    
    session_id = request.args.get('session_id','advanced')
    chatbot_payload = call_chatbot_with_results(
        items=papers,
        source="Europe PMC",
        q=q,
        session_id=session_id
    )

    return jsonify({
        "success": True,
        "query": q,
        "count": len(papers),
        "results": papers,
        "chatbot": chatbot_payload
    })






@app.route("/api/medrxiv/search")
def medrxiv_search_route():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"success": False, "error": " (q) is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 200)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    mode = (request.args.get("mode") or "ANY").upper()
    max_pages = min(int(request.args.get("max_pages", 3)), 10)

    svc = RealNASAService()
    papers = svc.search_biorxiv_like(
        server="medrxiv",
        query=q,
        limit=limit,
        mode=mode,
        max_pages=max_pages
    )

    
    papers = filter_by_date(papers, date_from, date_to)

    
    for paper in papers:
        abstract_text = (paper.get("abstract") or "").strip()
        try:
            if abstract_text and len(abstract_text) >= 120:
                abstract_text = summarize_text(abstract_text)
        except Exception as e:
            print(f" medrxiv : summarization failed for paper '{paper.get('title')}' : {e}")
        paper["abstract"] = abstract_text

    
    
    
    try:
        
        history = SearchHistory(
            query=q,
            results_count=len(papers),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
                "mode": mode,
                "max_pages": max_pages
            }),
            sources_searched=json.dumps(["medrxiv"])
        )
        db.session.add(history)

        
        for r in papers:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("pubmed_id"):
                exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()

            if not exists:
                
                pub_date_raw = r.get("publication_date")
                pub_date = None
                try:
                    pub_date = normalize_publication_date(pub_date_raw)
                except Exception as e:
                    print(f"database : publication_date parse error for '{r.get('title')}' : {e}")
                    pub_date = None

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"error database : {db_err}")
    

    
    session_id = request.args.get('session_id','advanced')
    chatbot_payload = call_chatbot_with_results(
        items=papers,
        source="medRxiv",
        q=q,
        session_id=session_id
    )

    return jsonify({
        "success": True,
        "query": q,
        "count": len(papers),
        "results": papers,
        "chatbot": chatbot_payload
    })






@app.route("/api/geo/search")
def ncbi_geo_search_route():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": False, "error": " q is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 200)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    results = svc.search_ncbi_geo(q, limit=limit)

    
    results = filter_by_date(results, date_from, date_to)

    
    for item in results:
        try:
            abstract_text = (item.get('abstract') or "").strip()
            if abstract_text:
                if len(abstract_text) >= 120:
                    item['abstract'] = summarize_text(abstract_text)
                else:
                    item['abstract'] = abstract_text
        except Exception as e:
            print(f"geo summarization failed for item '{item.get('title')}' : {e}")
            item['abstract'] = item.get('abstract') or ""

    
    
    
    try:
        
        history = SearchHistory(
            query=q,
            results_count=len(results),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit
            }),
            sources_searched=json.dumps(["NCBI GEO"])
        )
        db.session.add(history)

        
        for r in results:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("url"):
                exists = Paper.query.filter_by(url=r["url"]).first()

            if not exists:
                pub_date = None
                try:
                    pub_date = normalize_publication_date(r.get("publication_date"))
                except Exception as e:
                    print(f"database : publication_date parse error for '{r.get('title')}' : {e}")

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"[DB ERROR] {db_err}")
    

    
    session_id = request.args.get('session_id','advanced')
    chatbot_payload = call_chatbot_with_results(
        items=results,
        source="NCBI GEO",
        q=q,
        session_id=session_id
    )

    return jsonify({
        "success": True,
        "query": q,
        "count": len(results),
        "results": results,
        "chatbot": chatbot_payload
    })





@app.route("/api/crossref/search")
def api_crossref_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": False, "error": " [q] is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 100)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    items = svc.search_crossref(q, limit=limit)

    
    items = filter_by_date(items, date_from, date_to)

    
    for item in items:
        abstract_text = (item.get("abstract") or "").strip()
        try:
            if abstract_text and len(abstract_text) >= 120:
                abstract_text = summarize_text(abstract_text)
        except Exception as e:
            print(f"crossref : summarization failed for item '{item.get('title')}' : {e}")
        item["abstract"] = abstract_text

    
    
    
    try:
        
        history = SearchHistory(
            query=q,
            results_count=len(items),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit
            }),
            sources_searched=json.dumps(["crossref"])
        )
        db.session.add(history)

        
        for r in items:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("pubmed_id"):
                exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()

            if not exists:
                
                pub_date_raw = r.get("publication_date")
                pub_date = None
                try:
                    pub_date = normalize_publication_date(pub_date_raw)
                except Exception as e:
                    print(f"database : publication_date parse error for '{r.get('title')}' : {e}")
                    pub_date = None

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"database error : {db_err}")
    

    
    session_id = request.args.get('session_id','advanced')
    chatbot_payload = call_chatbot_with_results(
        items=items,
        source="Crossref",
        q=q,
        session_id=session_id
    )

    return jsonify({
        "success": True,
        "query": q,
        "count": len(items),
        "results": items,
        "chatbot": chatbot_payload
    })



@app.route("/api/openalex/search")
def api_openalex_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"success": False, "error": " *q* is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 200)
    is_oa_raw = request.args.get("is_oa")
    is_oa = True if is_oa_raw == "true" else False if is_oa_raw == "false" else None
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    svc = RealNASAService()
    items = svc.search_openalex(q, limit=limit, is_oa=is_oa)

    
    items = filter_by_date(items, date_from, date_to)

    
    for item in items:
        abstract_text = (item.get("abstract") or "").strip()
        try:
            if abstract_text and len(abstract_text) >= 120:
                abstract_text = summarize_text(abstract_text)
        except Exception as e:
            print(f"openalex : summarization failed for item '{item.get('title')}' : {e}")
        item["abstract"] = abstract_text

    
    
    
    try:
        
        history = SearchHistory(
            query=q,
            results_count=len(items),
            user_ip=request.remote_addr,
            filters_used=json.dumps({
                "date_from": date_from,
                "date_to": date_to,
                "limit": limit,
                "is_oa": is_oa
            }),
            sources_searched=json.dumps(["openalex"])
        )
        db.session.add(history)

        
        for r in items:
            exists = None
            if r.get("doi"):
                exists = Paper.query.filter_by(doi=r["doi"]).first()
            elif r.get("pubmed_id"):
                exists = Paper.query.filter_by(pubmed_id=r["pubmed_id"]).first()

            if not exists:
                
                pub_date_raw = r.get("publication_date")
                pub_date = None
                try:
                    pub_date = normalize_publication_date(pub_date_raw)
                except Exception as e:
                    print(f" db : publication_date parse error for '{r.get('title')}' : {e}")
                    pub_date = None

                paper_obj = Paper(
                    title=r.get("title"),
                    abstract=r.get("abstract"),
                    authors=json.dumps(r.get("authors", [])),
                    source=r.get("source"),
                    url=r.get("url"),
                    keywords=json.dumps(r.get("keywords", [])),
                    publication_date=pub_date,
                    doi=r.get("doi"),
                    pubmed_id=r.get("pubmed_id"),
                    nasa_id=r.get("nasa_id"),
                    sentiment=r.get("sentiment"),
                    objective=r.get("objective")
                )
                db.session.add(paper_obj)

        db.session.commit()
    except Exception as db_err:
        db.session.rollback()
        print(f"db error : {db_err}")
    

    session_id = request.args.get('session_id', 'advanced')
    chatbot_payload = call_chatbot_with_results(
        items=items,
        source="OpenAlex",
        q=q,
        session_id=session_id
    )

    return jsonify({
        "success": True,
        "query": q,
        "count": len(items),
        "results": items,
        "chatbot": chatbot_payload
    })


@app.route('/api/reports/activity')
def api_activity_report():

    try:
        
        days_back = int(request.args.get('days', 30))
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)

        
        all_searches = db.session.query(SearchHistory).all()

        
        filtered_searches = [
            search for search in all_searches
            if start_date <= search.search_time <= end_date
        ]

        
        daily_activity = {}
        for search in filtered_searches:
            date_key = search.search_time.date().isoformat()
            if date_key not in daily_activity:
                daily_activity[date_key] = {
                    'date': date_key,
                    'searches': 0,
                    'total_results': 0,
                    'unique_queries': set()
                }

            daily_activity[date_key]['searches'] += 1
            daily_activity[date_key]['total_results'] += search.results_count
            daily_activity[date_key]['unique_queries'].add(search.query)

        
        activity_list = []
        for day_data in daily_activity.values():
            day_data['unique_queries'] = len(day_data['unique_queries'])
            activity_list.append(day_data)

        activity_list.sort(key=lambda x: x['date'])

        
        query_counts = {}
        for search in filtered_searches:
            query_counts[search.query] = query_counts.get(search.query, 0) + 1

        top_queries = sorted(query_counts.items(),
                             key=lambda x: x[1], reverse=True)[:10]

        
        total_searches = len(filtered_searches)
        total_results = sum(
            search.results_count for search in filtered_searches)
        avg_results = round(total_results / total_searches,
                            2) if total_searches > 0 else 0

        return jsonify({
            'success': True,
            'report': {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': days_back
                },
                'summary': {
                    'total_searches': total_searches,
                    'total_results': total_results,
                    'average_results_per_search': avg_results,
                    'unique_queries': len(set(search.query for search in filtered_searches))
                },
                'daily_activity': activity_list,
                'top_queries': [{'query': q, 'count': c} for q, c in top_queries],
                'search_trends': {
                    'peak_day': max(activity_list, key=lambda x: x['searches']) if activity_list else None,
                    'most_productive_day': max(activity_list, key=lambda x: x['total_results']) if activity_list else None
                }
            },
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"Activity report error : {e}")
        return jsonify({
            'success': False,
            'error': 'failed to generate activity report',
            'details': str(e)
        }), 500



@app.route('/api/reports/export')
def api_export_report():

    try:
        format_type = request.args.get('format', 'json').lower()

        if format_type not in ['json', 'csv']:
            return jsonify({'error': 'Invalid format. Use json or csv'}), 400

        
        searches = SearchHistory.query.order_by(
            SearchHistory.search_time.desc()).all()

        if format_type == 'json':
            data = [search.to_dict() for search in searches]
            return jsonify({
                'success': True,
                'data': data,
                'count': len(data),
                'timestamp': datetime.now().isoformat()
            })

        elif format_type == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)

            
            writer.writerow(['ID', 'Query', 'Results Count',
                            'Search Time', 'User IP', 'Filters Used'])

            
            for search in searches:
                writer.writerow([
                    search.id,
                    search.query,
                    search.results_count,
                    search.search_time.isoformat(),
                    search.user_ip,
                    search.filters_used
                ])

            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'activity_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            )

    except Exception as e:
        print(f"export report api error : {e}")
        return jsonify({'error': 'failed to export report', 'details': str(e)}), 500


@app.route('/api/health')
def api_health():

    try:
        paper_count = db.session.query(Paper).count()
        search_count = db.session.query(SearchHistory).count()

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'counts': {
                'papers': paper_count,
                'searches': search_count
            },
            'services': {
                'database': 'operational',
                'search': 'operational',
                'api': 'operational'
            },
            'version': '1.0',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500


@app.route("/nltk-status")
def nltk_status():
    return jsonify({
        "NLTK_AVAILABLE": NLTK_AVAILABLE
    })

@app.route('/api/knowledge-graph')
def api_knowledge_graph():

    try:
        query = request.args.get('query', '').strip()
        max_nodes = min(int(request.args.get('max_nodes', 50)), 100)

        
        if query:
            papers = db.session.query(Paper).filter(
                db.or_(
                    Paper.title.contains(query),
                    Paper.abstract.contains(query)
                )
            ).limit(20).all()
        else:
            papers = db.session.query(Paper).limit(20).all()

        
        nodes = []
        links = []

        for paper in papers:
            
            paper_node = {
                'id': f"paper_{paper.id}",
                'name': paper.title,
                'type': 'paper',
                'size': 20,
                'color': '#1f77b4',
                'title': paper.title,
                'abstract': paper.abstract or "",
                'source': paper.source
            }
            nodes.append(paper_node)


            if paper.keywords:
                try:
                    keywords = json.loads(paper.keywords)
                    
                    for keyword in keywords[:3]:
                        concept_id = f"concept_{keyword.replace(' ', '_')}"

                        
                        if not any(node['id'] == concept_id for node in nodes):
                            concept_node = {
                                'id': concept_id,
                                'name': keyword,
                                'type': 'concept',
                                'size': 15,
                                'color': '#ff7f0e'
                            }
                            nodes.append(concept_node)

                        
                        links.append({
                            'source': paper_node['id'],
                            'target': concept_id,
                            'type': 'contains'
                        })
                except:
                    pass

        return jsonify({
            'success': True,
            'graph': {
                'nodes': nodes[:max_nodes],
                'links': links,
                'total_papers': len(papers),
                'query': query if query else 'all'
            },
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"graph api error : {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate graph',
            'details': str(e)
        }), 500



if __name__ == '__main__':
    try:
        
        Config.validate_apis()


        db_dir = os.path.dirname(Config.DATABASE_PATH) or '.'
        test_file = os.path.join(db_dir, 'test_write.tmp')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print(" Write permission OK ")


        if init_database(app):
            print("Starting Space Biology Research Astro-Biom Platform...")
            print("Server running on http://localhost:5000")

            app.run(
                host='0.0.0.0',
                port=5000,
                debug=True
            )
        else:
            print("Faile database")

    except Exception as e:
        print(f" start error: {e}")