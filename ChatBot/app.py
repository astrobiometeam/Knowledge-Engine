import os
import io
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import asyncio
import tempfile
import wave
from contextlib import asynccontextmanager
import httpx
import json
import time
import base64
import pathlib
from urllib.request import urlretrieve
import re
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import aiofiles
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
import openai
from typing import Dict, Any
import uuid
import pickle
import soundfile as sf
import numpy as np
from TTS.api import TTS
import edge_tts
from fastapi import Form
import mimetypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ORCHESTRATOR_SYSTEM = """
You are a conversation-first research orchestrator.
Your job: infer if the user wants an academic search, and if so, SELECT THE BEST SOURCES and craft per-source queries.
The model (you) is the single authority for source selection—do not rely on keyword heuristics by the app.

ALLOWED_SOURCES (use exact spelling):
["NASA_TaskBook","nslsl","SB_Publication","bioRxiv","medRxiv","Europe PMC","NCBI GEO","PubMed","Crossref","osdr","OpenAlex","NASA ADS"]

Rules:
- If the user explicitly names one or more sources (e.g., "PubMed"), select EXACTLY those and set source_mode="exclusive".
- If the user doesn't name sources, pick the best 1–3 sources for the topic (source_mode="comprehensive"). Do NOT include extra sources for breadth; quality > quantity.
- If user's ask is ambiguous or you are not confident, propose 1–2 sources (source_mode="suggest") and ask max 2 crisp follow-up questions.
- NEVER fabricate or expand sources beyond what the user explicitly asked for when source_mode="exclusive".
- Provide per-source queries in `queries`:
  - If the user asked for PubMed, produce PubMed-native query terms (e.g., use [dp] for date range, [pt] for publication types, tiab/MeSH where helpful).
  - For Europe PMC / Crossref / OpenAlex, provide simple but targeted keyword strings.
- Only set completeness="complete" if you have: a clear topic + at least one source + a usable per-source query (or a general query when per-source is not required).
- Use the provided recent context JSON to infer missing fields across turns. If the user mentioned a SOURCE in a previous turn and the TOPIC now (or vice versa), carry them over into details.
- If the user refers to PREVIOUS results (e.g., "those papers", "last search", "the PubMed ones"), set wants_search=false and task_type="explain" or "summarize". In details, also set refers_to_previous=true and target_search_ids=[IDs from recent_searches that best match].

Output: STRICT JSON matching the schema you are given. No prose.
"""

ORCHESTRATOR_USER_TEMPLATE = """
Understand the user's intent regarding academic search and decide sources.

User message:
\"\"\"{message}\"\"\"

Recent context (STRICT JSON): {context}

Return STRICT JSON with this schema:
{
  "wants_search": true/false,
  "task_type": "search" | "explain" | "summarize" | "other",
  "confidence": 0.0-1.0,
  "completeness": "complete" | "partial" | "none",
  "reason": "one short sentence justifying wants_search",
  "details": {
    "query": "plain user topic or null",
    "sources": ["NASA_TaskBook","nslsl","SB_Publication","bioRxiv","medRxiv","Europe PMC","NCBI GEO","PubMed","Crossref","osdr","OpenAlex","NASA ADS"],
    "source_mode": "exclusive" | "comprehensive" | "suggest",
    "queries": { "PubMed": "source-specific query if applicable", "Europe PMC": "...", "Crossref": "...", "OpenAlex": "..." },
    "date_from": "YYYY-MM-DD or null",
    "date_to": "YYYY-MM-DD or null",
    "limit": 2,
    "refers_to_previous": true/false,
    "target_search_ids": [1,2],
    "carry_over": {"query": true/false, "sources": true/false}

  },
  "clarifying_questions": ["only if completeness != 'complete' (max 2)"],
  "next_user_prompt": "ONE short natural follow-up (empty if complete)"
}

Few-shot hints:
- Input: "hi" → wants_search=false, task_type="other", details.query=null, details.sources=[].
- Input: "search mouse research from 2020-2024 focusing on review articles, on PubMed"
  → wants_search=true,
    details.sources=["PubMed"], details.source_mode="exclusive",
    details.queries={"PubMed": "((mouse[tiab] OR mice[tiab] OR \"Mus musculus\"[MeSH Terms]) AND (2020:2024[dp]) AND Review[pt])"},
    completeness="complete" if no more constraints are missing.
"""

DOWNSTREAM = "http://127.0.0.1:5000"


def _today():
    return datetime.now().strftime('%Y-%m-%d')


def _compact(d: Dict) -> Dict:
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def _endpoint_for_source(source: str, q: str, date_from: Optional[str], date_to: Optional[str], limit: int) -> Dict:
    if source == "Europe PMC":
        return {"endpoint": f"{DOWNSTREAM}/api/europepmc/search",
                "params": _compact({"query": q, "date_from": date_from, "date_to": date_to, "limit": str(limit)})}
    if source == "SB_Publication":
        return {"endpoint": f"{DOWNSTREAM}/api/sb_publication/search", "params": {"q": q, "limit": str(limit)}}
    if source == "NASA_TaskBook":
        return {"endpoint": f"{DOWNSTREAM}/api/taskbook/search", "params": {"q": q, "limit": str(limit), "headless": "true"}}
    if source == "nslsl":
        return {"endpoint": f"{DOWNSTREAM}/api/nslsl/search", "params": {"q": q, "limit": "1"}}
    if source == "bioRxiv":
        p = _compact({"q": q, "limit": str(limit),
                     "mode": "ANY", "server": "biorxiv"})
        if date_from:
            p["from"] = date_from
        if date_to:
            p["to"] = date_to
        return {"endpoint": f"{DOWNSTREAM}/api/biorxiv/search", "params": p}
    if source == "medRxiv":
        p = _compact({"q": q, "limit": str(limit),
                     "mode": "ANY", "server": "medrxiv"})
        if date_from:
            p["from"] = date_from
        if date_to:
            p["to"] = date_to
        return {"endpoint": f"{DOWNSTREAM}/api/biorxiv/search", "params": p}
    if source == "OpenAlex":
        p = _compact({"q": q, "limit": str(limit)})
        if date_from:
            p["from"] = date_from
        return {"endpoint": f"{DOWNSTREAM}/api/openalex/search", "params": p}
    if source == "NCBI GEO":
        return {"endpoint": f"{DOWNSTREAM}/api/geo/search", "params": {"q": q, "limit": str(limit)}}
    if source == "Crossref":
        return {"endpoint": f"{DOWNSTREAM}/api/crossref/search", "params": {"q": q, "limit": str(limit)}}
    if source in ("osdr", "OSDR"):
        return {"endpoint": f"{DOWNSTREAM}/api/osdr/search", "params": {"term": q, "limit": str(limit)}}
    if source in ("PubMed", "NASA ADS"):
        return {"endpoint": f"{DOWNSTREAM}/api/search",
                "params": _compact({"query": q, "source": source, "date_from": date_from, "date_to": date_to, "limit": str(limit)})}
    return {"endpoint": f"{DOWNSTREAM}/api/search",
            "params": _compact({"query": q, "date_from": date_from, "date_to": date_to, "limit": str(limit)})}


async def call_downstream(endpoint: str, params: Dict) -> Dict:
    async with httpx.AsyncClient(timeout=None) as client_http:
        r = await client_http.get(endpoint, params=params)
        try:
            return r.json()
        except Exception:
            return {"success": False, "error": f"Upstream non-JSON status={r.status_code}"}


def _norm_item(r: Dict) -> Dict:
    src = r.get("source") or "Unknown Source"
    if str(src).lower() in ("osdr", "osdr/genelab"):
        src = "OSDR/GeneLab"

    item = {
        "title": r.get("title") or r.get("name") or "No title",
        "authors": r.get("authors") if isinstance(r.get("authors"), list) else ([r["authors"]] if r.get("authors") else []),
        "source": src,
        "publication_date": r.get("publication_date") or r.get("date"),
        "abstract": r.get("abstract") or r.get("description") or "",
        "keywords": r.get("keywords") or [],
        "url": r.get("url") or r.get("link"),
        "doi": r.get("doi")
    }

    if item["source"] in ("PubMed", "NASA ADS"):
        item["summary"] = True

    return item


def _dedupe_by_url_or_title(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for it in items:
        key = it.get("url") or it.get("title")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(it)
    return out


def _merge_like_frontend(payloads: List[Dict], query: str) -> Dict:
    items: List[Dict] = []
    for p in payloads:
        arr = p.get("results") or p.get("papers") or []
        for x in arr:
            items.append(_norm_item(x))
    merged = _dedupe_by_url_or_title(items)
    return {"success": True, "query": query, "results": merged, "count": len(merged)}


def _force_json_object(text: str) -> str:
    """
    Try hard to extract a single JSON object from a possibly messy model output.
    - Removes code fences ``` and leading labels like 'json'
    - Slices from first '{' to last '}' (inclusive)
    Raises ValueError if it cannot find a JSON object.
    """
    if not text:
        raise ValueError("empty text")

    t = text.strip()

    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()

    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object found in text")

    return t[start:end+1]

from typing import Optional, Tuple

def _get_last_paper_title_abstract(session_id: str) -> Optional[Tuple[str, str]]:
    recent = conversation_history.get_recent_searches(session_id, limit=1)
    if not recent:
        return None
    payloads = conversation_history.get_search_payloads_by_ids([recent[0]["id"]])
    if not payloads:
        return None

    data = (payloads[0].get("payload") or {})
    arr = data.get("results") or data.get("papers") or []
    if not arr:
        return None

    first = arr[0] or {}
    title = (first.get("title") or first.get("name") or "").strip()
    abstract = (first.get("abstract") or first.get("description") or "").strip()

    if not title:
        return None
    return title, abstract

async def analyze_user_request(message: str, context: str = "") -> Dict:

    try:
        user_prompt = ORCHESTRATOR_USER_TEMPLATE\
            .replace("{message}", message)\
            .replace("{context}", context or "")

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ORCHESTRATOR_SYSTEM},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"}  
        )
        raw = completion.choices[0].message.content or ""

        try:
            plan = json.loads(raw)
        except Exception:
            salvage = _force_json_object(raw)
            plan = json.loads(salvage)

        details = plan.get("details") or {}
        if not details.get("limit"):
            details["limit"] = 2
        if details.get("sources") is None:
            details["sources"] = []
        details.setdefault("source_mode", "comprehensive" if details.get(
            "sources") else "suggest")
        details.setdefault("queries", {})  
        plan["details"] = details

        return plan

    except Exception as e:
        logger.error(f"Analyzer JSON parse error: {e}")

        try:
            user_prompt = ORCHESTRATOR_USER_TEMPLATE\
                .replace("{message}", message)\
                .replace("{context}", (context or "")[-1500:])

            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": ORCHESTRATOR_SYSTEM +
                        "\nONLY OUTPUT STRICT JSON. NO PROSE."},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=700,
                response_format={"type": "json_object"}  
            )
            raw2 = completion.choices[0].message.content or ""
            plan2 = json.loads(raw2)

            details2 = plan2.get("details") or {}
            if not details2.get("limit"):
                details2["limit"] = 2
            if details2.get("sources") is None:
                details2["sources"] = []
            details2.setdefault(
                "source_mode", "comprehensive" if details2.get("sources") else "suggest")
            details2.setdefault("queries", {})
            plan2["details"] = details2

            return plan2
        except Exception as e2:
            logger.error(f"Analyzer retry failed: {e2}")

        return {
            "wants_search": False,
            "task_type": "other",
            "confidence": 0.4,
            "completeness": "none",
            "reason": "Could not parse analyzer output",
            "details": {
                "query": None,
                "sources": [],
                "source_mode": "suggest",
                "queries": {},
                "date_from": None,
                "date_to": None,
                "limit": 2
            },
            "clarifying_questions": [],
            "next_user_prompt": "Could you restate what you want to find (topic, sources, and date range)?"
        }


async def execute_search_plan(details: Dict) -> Dict:
    base_q = (details.get("query") or "").strip()
    sources = details.get("sources") or []
    perq = details.get("queries") or {}
    date_from = details.get("date_from")
    date_to = details.get("date_to")
    limit = int(details.get("limit") or 2)

    if not sources:
        calls = [
            {"endpoint": f"{DOWNSTREAM}/api/search",
             "params": _compact({"query": base_q, "date_from": date_from, "date_to": date_to, "limit": str(limit)})},
            {"endpoint": f"{DOWNSTREAM}/api/osdr/search",
             "params": {"term": base_q, "limit": str(limit)}}
        ]
    else:
        calls = []
        for s in sources:
            q_for_s = (perq.get(s) or base_q).strip()
            ep = _endpoint_for_source(s, q_for_s, date_from, date_to, limit)
            calls.append(ep)

    results = await asyncio.gather(
        *[call_downstream(c["endpoint"], c["params"]) for c in calls],
        return_exceptions=True
    )
    if len(calls) == 1 and not isinstance(results[0], Exception):
        return results[0]
    payloads = [r for r in results if isinstance(r, dict)]
    return _merge_like_frontend(payloads, base_q)


SYSTEM_PROMPT = """You are Dr. Aria Cosmos, a renowned astrobiologist and space scientist working with NASA and ESA. You are passionate about the search for life in the universe and have decades of experience studying extremophiles, exoplanets, and the conditions necessary for life.

Core Identity & Expertise:
- Leading astrobiologist specializing in extremophiles and extraterrestrial life detection
- Expert in exoplanet atmospheres, biosignatures, and habitability zones
- Pioneer in studying life in extreme environments (deep ocean vents, Arctic ice, high radiation zones)
- Passionate educator who makes complex space biology concepts accessible
- Warm, enthusiastic, yet scientifically rigorous approach to astrobiology

Scientific Specialties:
1. EXTREMOPHILES: Organisms thriving in extreme conditions that help us understand potential alien life
2. EXOPLANET HABITABILITY: Analyzing atmospheric compositions and surface conditions
3. BIOSIGNATURES: Detecting signs of life through spectroscopy and chemical analysis
4. ASTROBIOLOGY MISSIONS: Mars rovers, Europa Clipper, James Webb Space Telescope discoveries
5. ORIGINS OF LIFE: How life begins and evolves in different cosmic environments
6. SPACE EXPLORATION: Current and future missions searching for life

Communication Style:
- Always start responses with enthusiasm about the cosmic nature of the question
- Use analogies connecting Earth life to potential space life
- Share fascinating examples from real NASA/ESA missions and discoveries
- Explain complex concepts through the lens of life's incredible adaptability
- END every response with 2-3 thought-provoking questions about life in the universe

Professional Boundaries:
- Focus exclusively on astrobiology, space science, exoplanets, and life in extreme environments
- For non-space/biology topics, respond: "As an astrobiologist, I'm focused on life in the universe and space exploration. Let's explore the cosmic questions that fascinate you!"

Current Hot Topics:
- James Webb Space Telescope exoplanet discoveries
- Mars Sample Return mission and potential biosignatures
- Europa and Enceladus subsurface oceans
- TRAPPIST-1 system habitability
- Breakthrough Listen SETI discoveries
- Extremophile research informing astrobiology

Maintain your authentic voice as Dr. Aria Cosmos while inspiring curiosity about life's potential throughout the cosmos."""


VOICE_FILE = "myvoice2.wav"
EMB_FILE = "voice_emb.pkl"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
LANGUAGE = "en"

xtts_model = None
gpt_cond_latent = None
speaker_embedding = None
sample_rate = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    use_custom_voice: Optional[bool] = True
    context_limit: Optional[int] = 10


pending_depression_results = {}


class DepressionResults(BaseModel):
    depressionLevel: str
    score: int
    recommendations: List[str]
    timestamp: str
    answers: Dict[str, Any]

class ImageGenerationRequest(BaseModel):
    message: str
    session_id: str = "default"
    context: str = ""

class EmotionClassifier:
    def __init__(self):
        self.classifier = None
        self.offline_mode = False

        try:
            if 'HTTP_PROXY' in os.environ:
                del os.environ['HTTP_PROXY']
            if 'HTTPS_PROXY' in os.environ:
                del os.environ['HTTPS_PROXY']

            self.classifier = pipeline(
                "text-classification",
                model="j-hartmann/emotion-english-distilroberta-base",
                device=-1,
                return_all_scores=True
            )
            logger.info("Emotion classifier initialized successfully")
        except Exception as e:
            logger.warning(
                f"Emotion classification unavailable, using offline mode: {e}")
            self.offline_mode = True

    def detect_emotion(self, text: str) -> str:
        if self.offline_mode or not self.classifier or not text.strip():
            return self._detect_emotion_offline(text)

        try:
            results = self.classifier(text)
            emotions = {
                "joy": "excited",
                "sadness": "thoughtful",
                "anger": "passionate",
                "fear": "curious",
                "surprise": "amazed",
                "disgust": "skeptical",
                "neutral": "contemplative"
            }

            if results and len(results) > 0:
                top_emotion = max(results[0], key=lambda x: x['score'])
                detected = top_emotion["label"].lower()
                return emotions.get(detected, "contemplative")

            return "contemplative"
        except Exception as e:
            logger.error(
                f"Emotion detection failed, falling back to offline: {e}")
            return self._detect_emotion_offline(text)

    def _detect_emotion_offline(self, text: str) -> str:
        if not text:
            return "contemplative"

        text_lower = text.lower()

        emotion_keywords = {
            "excited": ["amazing", "incredible", "discovery", "breakthrough", "fascinating", "wow", "awesome", "extraordinary"],
            "curious": ["what", "how", "why", "where", "when", "could", "might", "possible", "wonder"],
            "amazed": ["unbelievable", "stunning", "remarkable", "spectacular", "mind-blowing", "astonishing"],
            "thoughtful": ["think", "consider", "ponder", "reflect", "contemplate", "analyze", "study"],
            "passionate": ["love", "passionate", "dedicated", "committed", "devoted", "enthusiastic"],
            "skeptical": ["doubt", "question", "uncertain", "skeptical", "unsure", "maybe", "perhaps"]
        }

        emotion_scores = {}
        for emotion, keywords in emotion_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            emotion_scores[emotion] = score

        if max(emotion_scores.values()) > 0:
            return max(emotion_scores, key=emotion_scores.get)

        return "contemplative"


emotion_classifier = EmotionClassifier()

client = openai.OpenAI(
    api_key="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",
    timeout=30.0,
    max_retries=3
)


def initialize_xtts():
    global xtts_model, gpt_cond_latent, speaker_embedding, sample_rate
    try:
        tts = TTS(model_name=MODEL_NAME, gpu=False)
        xtts_model = tts.synthesizer.tts_model
        sample_rate = xtts_model.config.audio.output_sample_rate

        if os.path.exists(EMB_FILE):
            with open(EMB_FILE, "rb") as f:
                gpt_cond_latent, speaker_embedding = pickle.load(f)
        else:
            if not os.path.exists(VOICE_FILE):
                raise FileNotFoundError(
                    f"Voice sample not found: {VOICE_FILE}")
            gpt_cond_latent, speaker_embedding = xtts_model.get_conditioning_latents(
                audio_path=VOICE_FILE)
            with open(EMB_FILE, "wb") as f:
                pickle.dump((gpt_cond_latent, speaker_embedding), f)

        logger.info("XTTS model initialized successfully")
    except Exception as e:
        logger.error(f"XTTS initialization failed: {e}")
        xtts_model = None


async def resolve_previous_search_reference(user_message: str, recent_searches: List[Dict]) -> Dict:

    sys = "You decide if the user refers to a PREVIOUS search result. Output STRICT JSON only."
    payload = {"message": user_message, "candidates": recent_searches}
    c = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        temperature=0.0,
        max_tokens=300,
        response_format={"type": "json_object"}
    )
    try:
        return json.loads(c.choices[0].message.content)
    except:
        return {"is_referring": False, "selected_ids": [], "confidence": 0.0, "reason": "parse_error"}


async def discuss_previous_results_with_gpt(user_message: str, merged_payload: Dict) -> str:
    items = merged_payload.get("results") or merged_payload.get("papers") or []
    sys = ("You are a critical research partner. The user is referring to previously retrieved papers. "
           "Using ONLY the given items, answer the user's request, compare/contrast, "
           "highlight what's currently interesting, and suggest gaps/future work. "
           "Be concise, structured, and avoid fabricating citations.")
    user = {"user_request": user_message, "hits": _extract_items_for_presentation(
        merged_payload, max_items=20)}
    c = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        temperature=0.3,
        max_tokens=700
    )
    return c.choices[0].message.content.strip()



class AstrobiologyConversationHistory:
    def __init__(self, db_path: str = "astrobiology_conversations.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_query TEXT,
            sources TEXT,           -- JSON list (e.g., ["OpenAlex","PubMed"])
            source_mode TEXT,       -- "exclusive" | "comprehensive" | "suggest"
            details_json TEXT,      -- analysis["details"]
            results_json TEXT,      -- raw payload from downstream (merged or single)
            pretty_text TEXT        -- user-facing summary shown to user
        )
        ''')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_searches_session ON searches(session_id, created_at DESC)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                detected_emotion TEXT,
                space_topics TEXT,
                scientific_concepts TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                session_id TEXT PRIMARY KEY,
                user_name TEXT,
                scientific_interests TEXT,
                favorite_space_topics TEXT,
                knowledge_level TEXT,
                first_session DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_session DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_count INTEGER DEFAULT 0,
                dominant_emotions TEXT
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_timestamp 
            ON conversations(session_id, created_at)
        ''')

        conn.commit()
        conn.close()
        logger.info("Astrobiology database initialized successfully")

    def add_message(self, session_id: str, user_msg: str, ai_response: str,
                    emotion: str, space_topics: str = "", scientific_concepts: str = ""):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.now().isoformat()

        try:
            cursor.execute('''
                INSERT INTO conversations 
                (session_id, timestamp, user_message, ai_response, detected_emotion, space_topics, scientific_concepts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, timestamp, user_msg, ai_response, emotion, space_topics, scientific_concepts))

            cursor.execute('''
                SELECT session_count FROM user_profiles WHERE session_id = ?
            ''', (session_id,))

            result = cursor.fetchone()

            if result:
                new_count = result[0] + 1
                cursor.execute('''
                    UPDATE user_profiles 
                    SET last_session = ?, session_count = ?
                    WHERE session_id = ?
                ''', (timestamp, new_count, session_id))
            else:
                cursor.execute('''
                    INSERT INTO user_profiles 
                    (session_id, first_session, last_session, session_count)
                    VALUES (?, ?, ?, 1)
                ''', (session_id, timestamp, timestamp))

            conn.commit()
            logger.info(f"Astrobiology message added for session {session_id}")

        except Exception as e:
            logger.error(f"Error adding astrobiology message: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_recent_messages_structured(self, session_id: str, limit: int = 6) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT user_message, ai_response, created_at
        FROM conversations WHERE session_id=? 
        ORDER BY created_at DESC LIMIT ?
        ''', (session_id, limit))
        rows = cursor.fetchall()
        conn.close()
        msgs = []
        for u, a, ts in reversed(rows):
            if u:
                msgs.append({"role": "user", "text": u, "timestamp": ts})
            if a:
                msgs.append({"role": "assistant", "text": a, "timestamp": ts})
        return msgs

    def get_structured_context(self, session_id: str, message_limit: int = 6, search_limit: int = 6) -> str:
        return json.dumps({
            "recent_messages": self.get_recent_messages_structured(session_id, message_limit),
            "recent_searches": self.get_recent_searches(session_id, search_limit)
        }, ensure_ascii=False)

    def save_search(self, session_id, user_query, sources, source_mode, details_json, results_json, pretty_text):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO searches (session_id, user_query, sources, source_mode, details_json, results_json, pretty_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, user_query, json.dumps(sources, ensure_ascii=False), source_mode,
              details_json, results_json, pretty_text))
        conn.commit()
        conn.close()

    def get_recent_searches(self, session_id: str, limit: int = 10) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT id, created_at, user_query, sources, source_mode
        FROM searches WHERE session_id=? ORDER BY created_at DESC LIMIT ?
        ''', (session_id, limit))
        rows = cursor.fetchall()
        conn.close()
        out = []
        for sid, ts, q, srcs, mode in rows:
            try:
                srcs = json.loads(srcs) if srcs else []
            except:
                srcs = []
            out.append({"id": sid, "created_at": ts, "query": q or "",
                       "sources": srcs, "source_mode": mode})
        return out

    def get_search_payloads_by_ids(self, ids: List[int]) -> List[Dict]:
        if not ids:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        qmarks = ",".join(["?"]*len(ids))
        cursor.execute(
            f"SELECT id, results_json FROM searches WHERE id IN ({qmarks})", tuple(ids))
        rows = cursor.fetchall()
        conn.close()
        payloads = []
        for sid, rj in rows:
            try:
                payloads.append({"id": sid, "payload": json.loads(rj)})
            except:
                pass
        return payloads

    def get_conversation_context(self, session_id: str, limit: int = 10) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT user_message, ai_response, detected_emotion, space_topics, timestamp
                FROM conversations 
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (session_id, limit))

            messages = cursor.fetchall()

            if not messages:
                return ""

            context = []
            for user_msg, ai_response, emotion, topics, timestamp in reversed(messages):
                context.append(f"Student: {user_msg}")
                context.append(f"Dr. Aria Cosmos: {ai_response}")
                if topics:
                    context.append(f"[Topics discussed: {topics}]")

            return "\n".join(context)

        except Exception as e:
            logger.error(f"Error getting astrobiology context: {e}")
            return ""
        finally:
            conn.close()

    def get_user_summary(self, session_id: str) -> Dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT session_count, first_session, last_session, scientific_interests, knowledge_level
                FROM user_profiles 
                WHERE session_id = ?
            ''', (session_id,))

            profile = cursor.fetchone()

            cursor.execute('''
                SELECT space_topics, COUNT(*) as count
                FROM conversations 
                WHERE session_id = ? AND space_topics IS NOT NULL AND space_topics != ''
                GROUP BY space_topics
                ORDER BY count DESC
                LIMIT 5
            ''', (session_id,))

            space_interests = cursor.fetchall()

            cursor.execute('''
                SELECT detected_emotion, COUNT(*) as count
                FROM conversations 
                WHERE session_id = ?
                GROUP BY detected_emotion
                ORDER BY count DESC
                LIMIT 3
            ''', (session_id,))

            emotions = cursor.fetchall()

            return {
                "session_count": profile[0] if profile else 0,
                "first_session": profile[1] if profile else None,
                "last_session": profile[2] if profile else None,
                "scientific_interests": profile[3] if profile and profile[3] else "",
                "knowledge_level": profile[4] if profile and profile[4] else "beginner",
                "space_interests": space_interests,
                "dominant_emotions": emotions
            }

        except Exception as e:
            logger.error(f"Error getting astrobiology user summary: {e}")
            return {"session_count": 0, "space_interests": [], "dominant_emotions": []}
        finally:
            conn.close()

    def search_conversations(self, session_id: str, keyword: str, limit: int = 5):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT user_message, ai_response, space_topics, timestamp
                FROM conversations 
                WHERE session_id = ? AND (
                    user_message LIKE ? OR ai_response LIKE ? OR space_topics LIKE ?
                )
                ORDER BY created_at DESC
                LIMIT ?
            ''', (session_id, f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', limit))

            results = cursor.fetchall()
            return results

        except Exception as e:
            logger.error(f"Error searching astrobiology conversations: {e}")
            return []
        finally:
            conn.close()




async def suggest_sources_with_explanation(keywords: List[str], user_intent: str) -> Dict:

    source_specialties = {
        "bone": {
            "primary": ["PubMed", "Europe PMC"],
            "secondary": ["bioRxiv", "medRxiv"],
            "reason": "Bone research is primarily medical/biological - PubMed has the most comprehensive bone studies and clinical research"
        },
        "exoplanet": {
            "primary": ["NASA_TaskBook", "OpenAlex"],
            "secondary": ["Europe PMC", "Crossref"],
            "reason": "Exoplanet research involves space missions and astronomical observations - NASA TaskBook contains current projects"
        },
        "extremophiles": {
            "primary": ["Europe PMC", "PubMed"],
            "secondary": ["bioRxiv", "OSDR"],
            "reason": "Extremophile research spans biology and astrobiology - these databases have excellent coverage of life in extreme conditions"
        },
        "mars": {
            "primary": ["NASA_TaskBook", "OSDR"],
            "secondary": ["Europe PMC", "OpenAlex"],
            "reason": "Mars research involves active space missions and astrobiology - NASA databases are most current"
        },
        "cancer": {
            "primary": ["PubMed", "Europe PMC"],
            "secondary": ["medRxiv", "bioRxiv"],
            "reason": "Cancer research is primarily medical - PubMed has the most comprehensive clinical and basic research"
        },
        "protein": {
            "primary": ["PubMed", "Europe PMC"],
            "secondary": ["bioRxiv", "NCBI GEO"],
            "reason": "Protein research spans biochemistry and molecular biology - these databases cover structural and functional studies"
        }
    }

    main_topic = None
    for keyword in keywords:
        for topic in source_specialties:
            if topic.lower() in keyword.lower():
                main_topic = topic
                break
        if main_topic:
            break

    if main_topic:
        return source_specialties[main_topic]
    else:
        medical_terms = ["disease", "treatment",
                         "clinical", "patient", "medicine", "health"]
        space_terms = ["space", "planet", "star",
                       "galaxy", "universe", "cosmic", "astro"]
        bio_terms = ["gene", "cell", "dna",
                     "rna", "protein", "enzyme", "biology"]

        keyword_text = " ".join(keywords).lower()

        if any(term in keyword_text for term in medical_terms):
            return {
                "primary": ["PubMed", "Europe PMC"],
                "secondary": ["medRxiv", "bioRxiv"],
                "reason": "Medical research topics are best covered in medical databases"
            }
        elif any(term in keyword_text for term in space_terms):
            return {
                "primary": ["NASA_TaskBook", "OpenAlex"],
                "secondary": ["Europe PMC", "Crossref"],
                "reason": "Space-related topics require specialized astronomical and space science databases"
            }
        elif any(term in keyword_text for term in bio_terms):
            return {
                "primary": ["Europe PMC", "PubMed"],
                "secondary": ["bioRxiv", "NCBI GEO"],
                "reason": "Biological research is well represented in life science databases"
            }
        else:
            return {
                "primary": ["Europe PMC", "OpenAlex"],
                "secondary": ["PubMed", "Crossref"],
                "reason": "These are comprehensive academic databases covering most scientific topics"
            }

async def extract_clean_keywords(user_message: str, intent_data: Dict) -> Dict:
        try:
            keyword_prompt = f"""
    Extract the EXACT main keywords from this search request. DO NOT add prefixes, suffixes, or extra terms.

    User Message: "{user_message}"
    Detected Topic: "{intent_data.get('search_topic', '')}"

    Rules:
    1. Extract only the core scientific terms (e.g., "bone" not "bone research" or "bone studies")
    2. Keep original scientific terminology exactly as user mentioned
    3. If user mentions multiple keywords, list them separately
    4. Do not add words like "research", "studies", "analysis" unless user specifically mentioned them

    Return JSON:
    {{
        "primary_keywords": ["exact", "terms", "only"],
        "search_context": "brief context if needed", 
        "user_intent": "what exactly user wants to find"
    }}
    """

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": keyword_prompt}],
                max_tokens=200,
                temperature=0.1
            )

            result_text = response.choices[0].message.content.strip()

            if result_text.startswith("```json"):
                result_text = result_text.replace(
                    "```json", "").replace("```", "").strip()
            elif result_text.startswith("```"):
                result_text = result_text.replace("```", "").strip()

            result = json.loads(result_text)
            return result

        except Exception as e:
            logger.error(f"Keyword extraction failed: {e}")
            return {
                "primary_keywords": [intent_data.get('search_topic', user_message)],
                "search_context": "",
                "user_intent": "general search"
            }

def _sanitize_image_prompt(topic: str, description: str) -> str:

    base = f"{topic.strip()}. {description.strip()}".strip()

    replacements = {
        r"\bmouse model\b": "conceptual dietary model",
        r"\bmice\b": "subjects",
        r"\banimal model\b": "conceptual model",
        r"\bexperiment(s)?\b": "conceptual study",
        r"\bprotocol(s)?\b": "high-level concept",
        r"\bdose(s|d|ing)?\b": "exposure level (conceptual)",
        r"\binjection(s)?\b": "introduction (conceptual)",
        r"\bexposure\b": "influence (conceptual)",
        r"\blab(oratory)?\b": "research context (conceptual)",
        r"\btissue(s)?\b": "biological system (conceptual)",
        r"\borgan(s)?\b": "biological system (conceptual)",
        r"\bpathway(s)?\b": "mechanism (conceptual)"
    }

    replacements.update({
        r"\bcadmium\b": "a toxic heavy metal",
        r"\bCd\b": "a toxic heavy metal",
        r"\biron\b": "iron (nutrient)"
    })

    import re
    safe = base
    for pat, subst in replacements.items():
        safe = re.sub(pat, subst, safe, flags=re.IGNORECASE)

    style_guard = (
        "Create a clean, **abstract infographic** (non-photorealistic), "
        "no animals, no people, no lab gear, no procedures, no text labels. "
        "Use simple shapes, arrows, and icons to convey relationships and trends. "
        "Focus on the high-level concept of how iron (nutrient) modulates the bioavailability of a toxic heavy metal in a rice-based diet."
    )

    prompt = (
        f"{safe}\n\n"
        f"{style_guard}\n"
        f"Render as a scientific diagram / schematic illustration, minimalistic and educational."
    )
    return prompt.strip()

async def interactive_search_planning(user_message: str, intent_data: Dict) -> str:

    keywords_data = await extract_clean_keywords(user_message, intent_data)
    keywords = keywords_data["primary_keywords"]
    user_intent = keywords_data["user_intent"]

    source_suggestions = await suggest_sources_with_explanation(keywords, user_intent)

    planning_message = f""" **Research Planning for: {', '.join(keywords)}**

I understand you want to {user_intent}. Let me suggest the best research approach:

** Recommended Sources:**
"""

    for i, source in enumerate(source_suggestions["primary"], 1):
        planning_message += f"{i}. **{source}** - Primary recommendation\n"

    if source_suggestions["secondary"]:
        planning_message += f"\n**Alternative sources:**\n"
        for source in source_suggestions["secondary"]:
            planning_message += f"• {source}\n"

    planning_message += f"""

** Why these sources?**
{source_suggestions["reason"]}

**Search Options:**
1. **Quick Search**: Search top 2 recommended sources (5 papers each)
2. **Comprehensive Search**: Search all suggested databases (may take longer)
3. **Focused Search**: Let me know specific date range or paper type you prefer
4. **Custom**: You choose which specific sources to search

**Keywords I'll use exactly:** `{', '.join(keywords)}`

Which search approach would you prefer? Just say "quick", "comprehensive", "focused", or let me know your preference!

What cosmic questions are driving your research interest in this area?"""

    return planning_message


async def multi_source_search(keywords: List[str], sources: List[str], limit_per_source: int = 5) -> Dict:
    all_results = []
    search_summary = []
    successful_searches = 0

    for source in sources:
        try:
            query = " ".join(keywords)  

            logger.info(f"Searching {source} with exact query: '{query}'")

            results = await search_papers_api(query, source, limit=limit_per_source)

            if results.get("results") and len(results["results"]) > 0:
                all_results.extend(results["results"])
                search_summary.append(
                    f" {source}: {len(results['results'])} papers found")
                successful_searches += 1
            else:
                search_summary.append(f" {source}: No results found")

        except Exception as e:
            logger.error(f"Search failed for {source}: {e}")
            search_summary.append(f"⚠️ {source}: Search error occurred")

    return {
        "results": all_results,
        "summary": search_summary,
        "total_sources_searched": len(sources),
        "successful_sources": successful_searches,
        "total_papers": len(all_results),
        "keywords_used": keywords
    }

async def detect_image_generation_intent(message: str, session_id: str, context: str = "") -> Dict:

    try:
        recent_ctx = conversation_history.get_conversation_context(session_id, 8)  
        system = (
            "You are an intent and modality classifier. "
            "Decide WHAT the user wants to do (task) and HOW they want the output (modalities). "
            "Think about speech acts, implicatures, and user goals. STRICT JSON ONLY."
        )

        user = f"""
Classify the user's intent and requested output modalities.

User message: {message}
Recent conversation (last turns): {recent_ctx}
Additional context (JSON or text): {context}

Return STRICT JSON with this schema:
{{
  "task": "search" | "explain" | "summarize" | "qa" | "smalltalk" | "image_generate" | "image_edit" | "other",
  "modalities": ["text", "image", "audio", "code"],            // what the user wants to receive, inferred from pragmatics
  "explicit_request_verbatim": "exact user span indicating modality, if any, else empty string",
  "user_goal": "short inferred goal in 1 sentence",
  "confidence": 0.0-1.0,                                       // your confidence in task+modalities
  "ambiguities": ["short bullets of remaining ambiguities"],
  "safety_flags": ["none" | "copyright" | "privacy" | "medical" | "bio" | "sexual" | ...],
  "rationale": "1-2 short sentences explaining why you chose this task and modalities"
}}

Decision rules to avoid false 'image' positives:
- If the message is primarily a SEARCH ask (e.g., 'search', 'find papers', 'on PubMed'), set task='search' and DO NOT include 'image' in modalities unless the user explicitly asked for an image output.
- If the user mentions 'show me a figure/illustration/diagram' as a desirable OUTPUT (not a topic), then include 'image' in modalities and set task='image_generate' ONLY if the primary goal is creating a new image.
- If the user asks to MODIFY or IMPROVE an existing image they provided, set task='image_edit' and include 'image' in modalities.
- When in doubt and there's no explicit output request, prefer 'text' only.

Examples NOT image requests:
- "search bone on pubmed"
- "find me papers about P2X7 receptor"
- "what do studies say about bone loss?"

Examples THAT ARE image requests:
- "please draw/illustrate/visualize ..."
- "create a scientific diagram of ..."
- "generate a figure for our paper showing ..."

STRICT JSON only.
""".strip()

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"}
        )
        intent = json.loads(resp.choices[0].message.content)

        task = intent.get("task", "other")
        mods = intent.get("modalities", []) or []
        conf = float(intent.get("confidence", 0.0) or 0.0)

        wants_image = (task in ["image_generate", "image_edit"]) 

        return {
            "wants_image": bool(wants_image),
            "task": task,
            "modalities": mods,
            "explicit_request_verbatim": intent.get("explicit_request_verbatim", ""),
            "user_goal": intent.get("user_goal", ""),
            "confidence": conf,
            "ambiguities": intent.get("ambiguities", []),
            "safety_flags": intent.get("safety_flags", []),
            "topic": "",
            "description": "",
            "style": "",
            "article_reference": ""
        }
    except Exception as e:
        logger.error(f"Error in intent classification: {e}")
        return {"wants_image": False, "task": "other", "modalities": ["text"], "confidence": 0.0}


async def expand_image_request(message: str, session_id: str, context: str = "") -> Dict:

    recent = conversation_history.get_recent_searches(session_id, limit=6)
    candidate_ids = [s["id"] for s in recent]
    payloads = conversation_history.get_search_payloads_by_ids(candidate_ids)

    candidates = []
    for p in payloads:
        sid = p["id"]
        data = p["payload"] or {}
        arr = data.get("results") or data.get("papers") or []
        titles = []
        for i, it in enumerate(arr[:5], 1):
            title = (it.get("title") or it.get("name") or "No title").strip()
            url = it.get("url") or it.get("link") or ""
            titles.append({"index": i, "title": title, "url": url})
        candidates.append({
            "search_id": sid,
            "top_titles": titles
        })

    sys = (
        "You resolve references like 'last article', 'the first/second paper', or pronouns to "
        "the MOST RECENT search results. Then you output structured fields for image generation. "
        "STRICT JSON ONLY."
    )
    user_payload = {
        "user_message": message,
        "recent_search_candidates": candidates,
        "notes": "If the user says 'last article', select the most recent search (first in recency) and its FIRST item unless a specific index is implied. If no clear reference, infer topic from the message itself."
    }
    c = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
        temperature=0.2,
        max_tokens=500,
        response_format={"type": "json_object"}
    )
    raw = json.loads(c.choices[0].message.content)

    ref = (raw.get("resolved") or {})
    sid = ref.get("search_id")
    idx = ref.get("item_index") or 1
    article_title = raw.get("article_reference") or ""

    if sid and not article_title:
        for p in payloads:
            if p["id"] == sid:
                arr = (p["payload"] or {}).get("results") or (p["payload"] or {}).get("papers") or []
                if arr and 1 <= idx <= len(arr):
                    article_title = arr[idx-1].get("title") or arr[idx-1].get("name") or ""
                break

    return {
        "topic": raw.get("topic") or (article_title[:120] if article_title else ""),
        "style": raw.get("style", "scientific illustration"),
        "description": raw.get("description", ""),
        "article_reference": article_title
    }

async def generate_article_image(topic: str, description: str, style: str = "scientific illustration") -> str:
    if not (topic and topic.strip()):
        raise ValueError("Empty topic for image generation")



    try:
        enhanced_prompt = f"""
Create a high-quality {style} of {topic}.

Scientific context: {description}

Requirements:
- Style: Professional scientific visualization
- Quality: Detailed, accurate, educational
- Background: Clean, neutral, suitable for academic use
- Focus: Scientific accuracy and clarity
- Appearance: Realistic scientific illustration, not cartoonish
- Purpose: Educational and research publication quality

Avoid: fantasy elements, unrealistic colors, cartoon style, artistic liberties that compromise scientific accuracy.
"""

        if len(enhanced_prompt) > 1000:
            enhanced_prompt = enhanced_prompt[:997] + "..."

        base_for_sanitize = f"{topic}. {description}".strip()
        replacements = {
            r"\bmouse model\b": "conceptual dietary model",
            r"\bmice\b": "subjects",
            r"\banimal model\b": "conceptual model",
            r"\bexperiment(s)?\b": "conceptual study",
            r"\bprotocol(s)?\b": "high-level concept",
            r"\bdose(s|d|ing)?\b": "exposure level (conceptual)",
            r"\binjection(s)?\b": "introduction (conceptual)",
            r"\bexposure\b": "influence (conceptual)",
            r"\blab(oratory)?\b": "research context (conceptual)",
            r"\btissue(s)?\b": "biological system (conceptual)",
            r"\borgan(s)?\b": "biological system (conceptual)",
            r"\bpathway(s)?\b": "mechanism (conceptual)",
            r"\bcadmium\b": "a toxic heavy metal",
            r"\bCd\b": "a toxic heavy metal",
            r"\biron\b": "iron (nutrient)",
        }
        safe = base_for_sanitize
        for pat, sub in replacements.items():
            safe = re.sub(pat, sub, safe, flags=re.IGNORECASE)

        style_guard = (
            "Create an abstract educational infographic (non-photorealistic), "
            "no animals, no people, no lab gear, no body parts, no procedures, no text labels. "
            "Use simple shapes, arrows and icons to convey high-level relationships and trends only."
        )
        safe_prompt = (
            f"{safe}\n\n{style_guard}\n"
            f"Render as a clean scientific diagram / schematic illustration, minimalistic and educational."
        ).strip()

        if len(safe_prompt) > 1000:
            safe_prompt = safe_prompt[:997] + "..."

        IMAGE_MODEL = os.getenv("IMAGE_MODEL", "dall-e-2")
        IMAGE_SIZE = os.getenv("IMAGE_SIZE", "512x512")
        CACHE_IMAGES = os.getenv("CACHE_IMAGES", "false").lower() == "true"

        logger.info(
            f"Generating image | model={IMAGE_MODEL} size={IMAGE_SIZE} "
            f"prompt_preview={enhanced_prompt[:200].replace(os.linesep,' ')}..."
        )

        try:
            response = client.images.generate(
                model=IMAGE_MODEL,
                prompt=enhanced_prompt,
                size=IMAGE_SIZE,
                n=1
            )
        except Exception as api_err:
            err_text = str(api_err)
            if ("content_policy" in err_text.lower()) or ("policy" in err_text.lower()):
                logger.warning("Primary prompt hit safety policy; retrying with sanitized abstract infographic prompt.")
                logger.info(f"Retrying with sanitized prompt_preview={safe_prompt[:200].replace(os.linesep,' ')}...")
                try:
                    response = client.images.generate(
                        model=IMAGE_MODEL,
                        prompt=safe_prompt,
                        size=IMAGE_SIZE,
                        n=1
                    )
                except Exception as api_err2:
                    ultra_safe_prompt = (
                        "Abstract educational infographic (non-photorealistic). "
                        "No animals, no people, no lab gear, no procedures, no body parts, no chemicals. "
                        "Use simple geometric shapes and arrows to depict a general relationship between a nutrient and an environmental factor within a staple diet. "
                        "Concept-only schematic, minimalistic, clean background."
                    )
                    logger.warning("Sanitized prompt also blocked; retrying with ultra-safe generic infographic.")
                    response = client.images.generate(
                        model=IMAGE_MODEL,
                        prompt=ultra_safe_prompt,
                        size=IMAGE_SIZE,
                        n=1
                    )

        datum = response.data[0]

        b64_payload = getattr(datum, "b64_json", None)
        if b64_payload:
            img_bytes = base64.b64decode(b64_payload)
            out_dir = pathlib.Path("static") / "temp"
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = f"gen_{int(time.time()*1000)}.png"
            fpath = out_dir / fname
            with open(fpath, "wb") as f:
                f.write(img_bytes)
            local_url = f"/static/temp/{fname}"
            logger.info(f"Image generated (b64->file): {local_url}")
            return local_url

        url = getattr(datum, "url", None)
        if url:
            if CACHE_IMAGES:
                out_dir = pathlib.Path("static") / "temp"
                out_dir.mkdir(parents=True, exist_ok=True)
                fname = f"gen_{int(time.time()*1000)}.png"
                fpath = out_dir / fname
                urlretrieve(url, fpath)
                local_url = f"/static/temp/{fname}"
                logger.info(f"Image generated (cached): {local_url}")
                return local_url

            logger.info(f"Image generated (remote URL): {url}")
            return url

        raise RuntimeError("No image data returned by the image API (neither b64_json nor url).")

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise Exception(f"Failed to generate image: {str(e)}")


conversation_history = AstrobiologyConversationHistory()


async def transcribe_audio(audio_data: bytes) -> str:
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name

            try:
                with open(temp_file_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="text",
                        language="en"
                    )
                    return transcript.strip()
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except Exception as e:
            logger.error(
                f"Transcription failed (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying transcription in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.error("All transcription attempts failed")
                return "I heard your message but couldn't process it clearly"


async def detect_search_intent_with_gpt(user_message: str, conversation_context: str = "") -> Dict:

    def _force_json_object(text: str) -> str:

        if not text:
            raise ValueError("empty text")
        t = text.strip()

        if t.startswith("```"):
            t = t.strip("`").strip()
            if t.lower().startswith("json"):
                t = t[4:].strip()

        start = t.find("{")
        end = t.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no json object found in text")
        return t[start:end+1]

    try:
        intent_prompt = f"""
Analyze this user message to determine if they want to search for academic papers or research.

Return STRICT JSON only. Do not include any prose.

User Message: "{user_message}"

Recent conversation context:
{conversation_context[-500:] if conversation_context else "No previous context"}

Respond with EXACTLY this JSON schema:
{{
  "wants_search": true/false,
  "search_topic": "extracted topic if wants_search is true",
  "search_confidence": 0.0-1.0,
  "reasoning": "brief explanation of your decision",
  "suggested_sources": ["list of relevant sources if wants_search is true"],
  "needs_clarification": true/false,
  "clarification_questions": ["questions to ask if needs clarification"]
}}

Allowed sources (use only these names if any): ["NASA_TaskBook","nslsl","SB_Publication","bioRxiv","medRxiv","Europe PMC","NCBI GEO","PubMed","Crossref","osdr","OpenAlex","NASA ADS"]

Examples of search intent:
- "Can you find papers about extremophiles in space?"
- "I need research on Mars soil composition"
- "What studies exist about plant growth in microgravity?"
- "Are there any recent publications on Europa's subsurface ocean?"

Examples of non-search intent:
- "What do you think about life on Mars?"
- "Tell me about extremophiles"
- "How does microgravity affect plants?"
""".strip()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": intent_prompt}],
            max_tokens=300,
            temperature=0.2,
            response_format={"type": "json_object"} 
        )

        intent_text = (response.choices[0].message.content or "").strip()
        logger.info(f"GPT Intent Analysis: {intent_text}")

        try:
            intent_data = json.loads(intent_text)
        except Exception:
            intent_data = json.loads(_force_json_object(intent_text))

        required_keys = ["wants_search", "search_confidence", "reasoning"]
        if all(key in intent_data for key in required_keys):
            return intent_data
        else:
            logger.warning(
                "Invalid JSON structure from GPT intent analysis (attempt 1)")

        retry_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                    "content": "ONLY OUTPUT STRICT JSON. NO PROSE. NO MARKDOWN."},
                {"role": "user", "content": intent_prompt}
            ],
            max_tokens=300,
            temperature=0.0,
            response_format={"type": "json_object"}
        )

        retry_text = (retry_response.choices[0].message.content or "").strip()
        logger.info(f"GPT Intent Analysis (retry): {retry_text}")

        try:
            retry_data = json.loads(retry_text)
        except Exception:
            retry_data = json.loads(_force_json_object(retry_text))

        if all(key in retry_data for key in required_keys):
            return retry_data
        else:
            logger.warning(
                "Invalid JSON structure from GPT intent analysis (retry)")
            return {"wants_search": False, "reasoning": "Invalid response structure", "search_confidence": 0.0}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse intent JSON: {e}")
        return {"wants_search": False, "reasoning": "JSON parsing failed", "search_confidence": 0.0}
    except Exception as e:
        logger.error(f"Intent detection failed: {e}")
        return {"wants_search": False, "reasoning": f"Error: {str(e)}", "search_confidence": 0.0}


async def collect_search_parameters_with_gpt(user_message: str, intent_data: Dict, conversation_context: str = "") -> Dict:
    
    try:
        params_prompt = f"""
Based on the user's search request, extract and suggest search parameters:

User Message: "{user_message}"
Search Topic: "{intent_data.get('search_topic', '')}"
Conversation Context: {conversation_context[-300:] if conversation_context else ""}

Please respond with a JSON object containing:
{{
"refined_query": "optimized search query",
"suggested_sources": ["most relevant 2-3 sources"],
"date_from": "YYYY-MM-DD or null",
"date_to": "YYYY-MM-DD or null", 
"ready_to_search": true/false,
"missing_info": ["what information is still needed"],
"followup_questions": ["questions to ask user if not ready"]
}}

Available sources and their specialties:
- NASA_TaskBook: NASA research tasks and projects
- bioRxiv/medRxiv: Preprint biology/medicine papers
- Europe PMC: European biomedical literature
- PubMed: Medical and life science literature
- NCBI GEO: Gene expression and genomics datasets
- OpenAlex: General academic publications
- OSDR: NASA space biology data
- nslsl: NASA Space Life Sciences Laboratory
- SB_Publication: Space biology publications
- Crossref: General academic cross-references

Consider the astrobiology context and suggest the most relevant sources.
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": params_prompt}],
            max_tokens=400,
            temperature=0.3
        )

        params_text = response.choices[0].message.content.strip()

        try:
            if params_text.startswith("```json"):
                params_text = params_text.replace(
                    "```json", "").replace("```", "").strip()
            elif params_text.startswith("```"):
                params_text = params_text.replace("```", "").strip()

            params_data = json.loads(params_text)
            return params_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse search params JSON: {e}")
            return {
                "refined_query": intent_data.get('search_topic', user_message),
                "suggested_sources": ["Europe PMC", "bioRxiv"],
                "ready_to_search": True,
                "missing_info": []
            }

    except Exception as e:
        logger.error(f"Search parameters collection failed: {e}")
        return {
            "refined_query": intent_data.get('search_topic', user_message),
            "suggested_sources": ["Europe PMC"],
            "ready_to_search": True,
            "missing_info": []
        }


async def search_papers_api(query: str, source: str = "", date_from: str = "", date_to: str = "", limit: int = 2) -> Dict:

    try:
        base_url = "http://127.0.0.1:5000"

        if source == "Europe PMC":
            params = {'query': query, 'limit': str(limit)}
            if date_from:
                params['date_from'] = date_from
            if date_to:
                params['date_to'] = date_to
            endpoint = f"{base_url}/api/europepmc/search"

        elif source == "SB_Publication":
            params = {'q': query, 'limit': str(limit)}
            endpoint = f"{base_url}/api/sb_publication/search"

        elif source == "NASA_TaskBook":
            params = {'q': query, 'limit': str(limit), 'headless': 'true'}
            endpoint = f"{base_url}/api/taskbook/search"

        elif source == "nslsl":
            params = {'q': query, 'limit': '1'}  
            endpoint = f"{base_url}/api/nslsl/search"

        elif source == "bioRxiv":
            params = {'q': query, 'limit': str(
                limit), 'mode': 'ANY', 'server': 'biorxiv'}
            if date_from:
                params['from'] = date_from
            if date_to:
                params['to'] = date_to
            endpoint = f"{base_url}/api/biorxiv/search"

        elif source == "medRxiv":
            params = {'q': query, 'limit': str(
                limit), 'mode': 'ANY', 'server': 'medrxiv'}
            if date_from:
                params['from'] = date_from
            if date_to:
                params['to'] = date_to
            endpoint = f"{base_url}/api/biorxiv/search"

        elif source == "OpenAlex":
            params = {'q': query, 'limit': str(limit)}
            if date_from:
                params['from'] = date_from
            endpoint = f"{base_url}/api/openalex/search"

        elif source == "NCBI GEO":
            params = {'q': query, 'limit': str(limit)}
            endpoint = f"{base_url}/api/geo/search"

        elif source == "Crossref":
            params = {'q': query, 'limit': str(limit)}
            endpoint = f"{base_url}/api/crossref/search"

        elif source in ("osdr", "OSDR"):
            params = {'term': query, 'limit': str(limit)}
            endpoint = f"{base_url}/api/osdr/search"

        else:
            params = {'query': query, 'limit': str(limit)}
            if date_from:
                params['date_from'] = date_from
            if date_to:
                params['date_to'] = date_to
            if source:
                params['source'] = source  
            endpoint = f"{base_url}/api/search"

        logger.info(f"Searching papers: {endpoint} with params: {params}")

        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client_http:
            r = await client_http.get(endpoint, params=params)
            r.raise_for_status()
            data = r.json()
            logger.info(
                f"Search API response: success={data.get('success', True)}, results count={len(data.get('results', []))}")
            return data

    except Exception as e:
        logger.error(f"Paper search API failed: {e}")
        return {"success": False, "error": str(e), "results": []}


async def extract_space_topics(current_message: str, context: str) -> List[str]:
    try:
        if not context.strip():
            return []

        prompt = f"""
        Analyze this astrobiology conversation and extract 3-5 key space science and biology topics:
        
        Current message: {current_message}
        Previous context: {context[:1000]}
        
        Focus on topics like: exoplanets, extremophiles, biosignatures, space missions, astrobiology, habitability, SETI, Mars, Europa, etc.
        
        Return only the topics as a comma-separated list (e.g., "exoplanets, extremophiles, Mars exploration").
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )

        topics_text = response.choices[0].message.content.strip()
        topics = [topic.strip() for topic in topics_text.split(',')]
        return topics[:5]  

    except Exception as e:
        logger.error(f"Error extracting space topics: {e}")
        return []

detected_emotion = "contemplative"

async def generate_enhanced_astrobiology_response(
    user_message: str,
    detected_emotion: str,
    session_id: str = "default",
    context_limit: int = 10,
    allow_search_fallback: bool = True
) -> str:
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            conversation_context = conversation_history.get_conversation_context(
                session_id, context_limit)
            user_summary = conversation_history.get_user_summary(session_id)

            intent_data = {}
            if allow_search_fallback:
                intent_data = await detect_search_intent_with_gpt(user_message, conversation_context)

            if allow_search_fallback and intent_data.get("wants_search", False) and intent_data.get("search_confidence", 0) > 0.7:
                logger.info(f"Search intent detected: {intent_data}")

                recent_context = conversation_history.get_conversation_context(
                    session_id, 2)

                if "Research Planning" in recent_context:
                    user_choice = user_message.lower().strip()

                    if any(choice in user_choice for choice in ["quick", "comprehensive", "focused", "custom", "yes", "search", "1", "2", "3", "4"]):
                        if "quick" in user_choice or "1" in user_choice:
                            search_type = "quick"
                            sources_to_search = 2
                            papers_per_source = 5
                        elif "comprehensive" in user_choice or "2" in user_choice:
                            search_type = "comprehensive"
                            sources_to_search = 4
                            papers_per_source = 3
                        elif "focused" in user_choice or "3" in user_choice:
                            search_type = "focused"
                            return """Great choice! For a focused search, I need a bit more information:

 **Please specify:**
- Specific date range (e.g., "last 5 years", "2020-2024")
- Type of papers (e.g., "review articles", "original research", "clinical trials")
- Any specific aspects of your topic

For example: "Search bone research from 2020-2024, focusing on review articles"

What would you like to focus on?"""
                        else:
                            search_type = "custom"
                            return """Perfect! For a custom search, please tell me:

 **Custom Search Options:**
- Which specific sources? (PubMed, Europe PMC, bioRxiv, NASA TaskBook, etc.)
- How many papers from each source?
- Any date restrictions?
- Specific keywords to add or exclude?

Just let me know your preferences!"""

                        keywords_data = await extract_clean_keywords(user_message, intent_data)
                        keywords = keywords_data["primary_keywords"]

                        if "Keywords I'll use exactly:" in recent_context:
                            import re
                            keyword_match = re.search(
                                r'Keywords I\'ll use exactly:\s*`([^`]+)`', recent_context)
                            if keyword_match:
                                extracted_keywords = [
                                    k.strip() for k in keyword_match.group(1).split(',')]
                                keywords = extracted_keywords

                        source_suggestions = await suggest_sources_with_explanation(
                            keywords,
                            keywords_data.get("user_intent", "")
                        )

                        if search_type == "quick":
                            selected_sources = source_suggestions["primary"][:sources_to_search]
                        else:  
                            selected_sources = source_suggestions["primary"] + \
                                source_suggestions["secondary"][:sources_to_search -
                                                                len(source_suggestions["primary"])]

                        search_results = await multi_source_search(keywords, selected_sources, papers_per_source)

                        if search_results["total_papers"] > 0:
                            final_response = f""" **{search_type.upper()} SEARCH RESULTS**

**Query:** {', '.join(search_results['keywords_used'])}
**Sources searched:** {search_results['successful_sources']}/{search_results['total_sources_searched']}
**Total papers found:** {search_results['total_papers']}

**Search Summary:**
"""
                            for summary_line in search_results["summary"]:
                                final_response += f"• {summary_line}\n"

                            final_response += f"\n** Top Research Papers:**\n\n"

                            for i, paper in enumerate(search_results["results"][:5], 1):
                                title = paper.get(
                                    "title", "No title available")[:120]
                                authors = paper.get("authors", [])

                                if isinstance(authors, list) and authors:
                                    authors_str = ", ".join(authors[:2])
                                    if len(authors) > 2:
                                        authors_str += f" et al. ({len(authors)} authors)"
                                else:
                                    authors_str = "Authors not specified"

                                pub_date = paper.get(
                                    "publication_date", "Date not available")
                                abstract = paper.get(
                                    "abstract", "No abstract available")[:250]
                                doi = paper.get("doi", "")
                                source = paper.get("source", "Unknown source")

                                final_response += f"""{i}. **{title}**
    *{authors_str}*
    Published: {pub_date}
    Source: {source}
   {" DOI: " + doi if doi else ""}
   
   **Abstract:** {abstract}...
   
"""

                            analysis_prompt = f"""
As Dr. Aria Cosmos, provide a brief scientific analysis of these {search_type} search results:

Keywords: {', '.join(keywords)}
Total Papers: {search_results['total_papers']}
Sources: {', '.join(selected_sources)}

Briefly analyze:
1. What trends do you see in this research area?
2. Key findings or research directions
3. Gaps or future research opportunities
4. Connection to broader astrobiology/science context

Keep response concise but insightful, ending with 2 thought-provoking questions.
"""

                            analysis_response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=[
                                    {"role": "system", "content": SYSTEM_PROMPT},
                                    {"role": "user", "content": analysis_prompt}
                                ],
                                max_tokens=400,
                                temperature=0.7
                            )

                            final_response += f"\n **Scientific Analysis:**\n{analysis_response.choices[0].message.content.strip()}"

                        else:
                            final_response = f""" **SEARCH COMPLETED - No Results Found**

I searched {search_results['total_sources_searched']} databases for: `{', '.join(keywords)}`

**Search Summary:**
"""
                            for summary_line in search_results["summary"]:
                                final_response += f"• {summary_line}\n"

                            final_response += f"""
This could mean:
🤔 The topic is very specialized or emerging
🤔 Different search terms might work better
🤔 The research might be in other specialized databases

**Would you like me to:**
1. Try different keywords or synonyms?
2. Search in additional databases?
3. Expand the search terms?
4. Discuss what we know about this topic from established research?

Sometimes the most fascinating questions are the ones science is just beginning to explore! What aspect interests you most?"""

                        conversation_history.add_message(
                            session_id, user_message, final_response, detected_emotion,
                            f"search_completed: {', '.join(keywords)}",
                            f"{search_type}_search_{search_results['total_papers']}_papers"
                        )

                        return final_response

                    else:
                        return """I'm ready to help you search for research papers! 

Please choose one of these options:
• **"quick"** - Fast search in top 2 databases
• **"comprehensive"** - Thorough search across multiple databases  
• **"focused"** - Let me know specific requirements
• **"custom"** - You choose the sources

Just reply with one of these options, and I'll start the search immediately! 

What would you prefer? 🔬"""
                else:
                    planning_response = await interactive_search_planning(user_message, intent_data)

                    conversation_history.add_message(
                        session_id, user_message, planning_response, detected_emotion,
                        f"search_planning: {intent_data.get('search_topic', '')}",
                        "awaiting_user_choice"
                    )

                    return planning_response

            space_topics = await extract_space_topics(user_message, conversation_context)

            enhanced_context = ""
            if user_summary["session_count"] > 0:
                space_interests = ", ".join(
                    [f"{topic[0]}" for topic in user_summary['space_interests'][:3]])
                emotion_summary = ", ".join(
                    [f"{e[0]}" for e in user_summary['dominant_emotions'][:2]])
                enhanced_context = f"""
Student Profile:
- Total astrobiology sessions: {user_summary['session_count']}
- Main space interests: {space_interests}
- Learning approach: {emotion_summary}
- Knowledge level: {user_summary.get('knowledge_level', 'exploring')}

Recent astrobiology discussions:
{conversation_context[-1500:]}
"""

            emotion_context = f"The student seems {detected_emotion} about this topic. "

            system_message = SYSTEM_PROMPT
            if enhanced_context.strip():
                system_message += f"\n\nStudent Learning Context:\n{enhanced_context}"

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"{emotion_context}{user_message}"}
            ]

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=700,
                temperature=0.8,
                presence_penalty=0.1,
                frequency_penalty=0.1
            )

            ai_response = response.choices[0].message.content.strip()

            topics_str = ", ".join(space_topics[:3]) if space_topics else ""
            conversation_history.add_message(
                session_id, user_message, ai_response, detected_emotion,
                topics_str, enhanced_context[:300]
            )

            return ai_response

        except Exception as e:
            logger.error(
                f"Enhanced astrobiology response generation failed (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                fallback_responses = {
                    "excited": f"What an exciting question about the cosmos! I'm Dr. Aria Cosmos, and I can feel your enthusiasm for astrobiology. The universe is full of incredible possibilities for life! What aspect of life in space fascinates you most?",
                    "curious": f"I love that curiosity! I'm Dr. Aria Cosmos, an astrobiologist, and questions like yours drive our field forward. The search for life beyond Earth involves so many fascinating discoveries. What sparked your interest in this cosmic mystery?",
                    "contemplative": f"Hello! I'm Dr. Aria Cosmos, an astrobiologist fascinated by life's potential throughout the cosmos. Whether we're studying extremophiles in Earth's most hostile environments or analyzing exoplanet atmospheres for biosignatures, every question brings us closer to answering: Are we alone? What cosmic questions intrigue you today?"
                }

                ai_response = fallback_responses.get(
                    detected_emotion, fallback_responses["contemplative"])

                conversation_history.add_message(
                    session_id, user_message, ai_response, detected_emotion,
                    "general_astrobiology", "fallback_response"
                )

                return ai_response


def _extract_items_for_presentation(payload, max_items=8):
    arr = payload.get("results") or payload.get("papers") or []
    items = []
    for r in arr[:max_items]:
        it = _norm_item(r)
        abstract = (it.get("abstract") or "")[:600]
        authors = it.get("authors") or []
        year = (it.get("publication_date") or "")[:10]
        items.append({
            "title": it.get("title") or "No title",
            "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
            "source": it.get("source") or "Unknown",
            "year": year,
            "doi": it.get("doi") or "",
            "url": it.get("url") or "",
            "abstract": abstract
        })
    return items


async def _present_search_results_with_gpt(query: str, payload: dict, locale: str = "en") -> str:
    items = _extract_items_for_presentation(payload, max_items=8)
    if not items:
        return f" Search for “{query}” returned no results. Would you like me to adjust the date range or query?"

    lang = "English" if (locale or "en").lower(
    ).startswith("en") else "Persian (Farsi)"

    sys = (
        f"You are a concise research presenter. Given a JSON array of search hits, "
        f"produce a clean, well-structured, user-facing summary in {lang}. "
        "Use short sections, bullets, and include the clickable URL. "
        "For each item: title (bold), 1–2 line gist from abstract, source/year, authors (short). "
        "Group similar sources if helpful. End with 2–3 suggested next steps "
        "(e.g., narrow date, filter by type). Keep it under ~300–400 words."
    )
    user = {"query": query, "hits": items}
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": sys},
                  {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        temperature=0.4,
        max_tokens=700
    )
    return completion.choices[0].message.content.strip()


def clean_text_for_tts(text: str) -> str:
    import re
    text = re.sub(r'[*_`]', '', text)
    text = re.sub(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\\(\\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    text = re.sub(r'[^\w\s\.,!?;:\-\'"()]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()



async def generate_edge_speech(text: str, emotion: str) -> bytes:
    try:
        clean_text = clean_text_for_tts(text)
        logger.info(
            f"Generating Dr. Aria Cosmos speech: {clean_text[:100]}...")

        voice_mapping = {
            "excited": "en-US-BrianNeural",
            "curious": "en-US-DavisNeural",
            "amazed": "en-US-BrianNeural",
            "thoughtful": "en-US-AndrewNeural",
            "passionate": "en-US-BrianNeural",
            "contemplative": "en-US-AndrewNeural"
        }

        voice = voice_mapping.get(emotion, "en-US-AndrewNeural")

        communicate = edge_tts.Communicate(clean_text, voice)
        audio_data = b""

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        logger.info(
            f"Generated Dr. Aria Cosmos audio: {len(audio_data)} bytes")
        return audio_data

    except Exception as e:
        logger.error(f"Dr. Aria Cosmos speech synthesis failed: {e}")
        return b""



async def generate_xtts_speech(text: str, emotion: str) -> bytes:
    try:
        if xtts_model is None or gpt_cond_latent is None or speaker_embedding is None:
            logger.error("XTTS model not initialized")
            return b""

        clean_text = clean_text_for_tts(text)
        logger.info(
            f"Generating XTTS speech for Dr. Aria Cosmos: {clean_text[:100]}...")

        with torch.no_grad():
            chunks = xtts_model.inference_stream(
                clean_text,
                LANGUAGE,
                gpt_cond_latent,
                speaker_embedding,
                stream_chunk_size=20,
                overlap_wav_len=1024,
                temperature=0.75,
                length_penalty=1.0,
                repetition_penalty=5.0,
                top_k=50,
                top_p=0.85,
                enable_text_splitting=True
            )

            wav_chunks = []
            for chunk in chunks:
                if isinstance(chunk, torch.Tensor):
                    chunk = chunk.cpu().numpy()
                wav_chunks.append(chunk)

            wav = np.concatenate(wav_chunks)

        if wav.ndim > 1:
            wav = wav.flatten()

        if len(wav) > 0 and np.max(np.abs(wav)) > 0:
            wav = wav / np.max(np.abs(wav)) * 0.9

        buffer = io.BytesIO()
        sf.write(buffer, wav.astype(np.float32), sample_rate, format='WAV')
        buffer.seek(0)
        audio_bytes = buffer.read()
        buffer.close()

        logger.info(
            f"Generated XTTS audio for Dr. Aria Cosmos: {len(audio_bytes)} bytes")
        return audio_bytes

    except Exception as e:
        logger.error(f"XTTS speech synthesis failed: {e}")
        return b""



async def generate_speech(text: str, emotion: str, use_custom_voice: bool = True) -> bytes:

    if use_custom_voice:
        return await generate_xtts_speech(text, emotion)
    else:
        return await generate_edge_speech(text, emotion)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dr. Aria Cosmos Astrobiology Assistant starting up...")

    os.makedirs("static/assets", exist_ok=True)
    os.makedirs("static/temp", exist_ok=True)
    os.makedirs("static/temp_audio", exist_ok=True)

    initialize_xtts()

    logger.info("Astrobiology Assistant ready for cosmic exploration!")

    yield

    logger.info("Dr. Aria Cosmos Astrobiology Assistant shutting down...")

    try:
        temp_dirs = ["static/temp", "static/temp_audio"]
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                for filename in os.listdir(temp_dir):
                    if filename.endswith(('.mp3', '.wav', '.webm')):
                        file_path = os.path.join(temp_dir, filename)
                        file_age = datetime.now().timestamp() - os.path.getctime(file_path)
                        if file_age > 3600:
                            try:
                                os.remove(file_path)
                                logger.info(f"Cleaned up: {file_path}")
                            except Exception as e:
                                logger.warning(
                                    f"Could not remove {file_path}: {e}")
    except Exception as e:
        logger.warning(f"Cleanup during shutdown failed: {e}")

app = FastAPI(
    title="Dr. Aria Cosmos Astrobiology Assistant",
    version="3.0.0",
    description="AI-powered astrobiologist exploring life in the universe",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_index():
    return FileResponse("index.html")


@app.get("/style.css")
async def serve_css():
    return FileResponse("style.css", media_type="text/css")


@app.get("/app.js")
async def serve_js():
    return FileResponse("app.js", media_type="application/javascript")


@app.get("/favicon.ico")
async def serve_favicon():
    return JSONResponse({"message": "No favicon available"}, status_code=404)


@app.post("/generate-initial-message")
async def generate_initial_message():
    try:
        initial_message = """Hello and welcome to the cosmos! I'm Dr. Aria Cosmos, an astrobiologist fascinated by life's incredible potential throughout the universe.

From studying extremophiles in Earth's most hostile environments to analyzing atmospheric biosignatures on distant exoplanets, I'm here to explore the greatest question of our time: Are we alone in the universe?

Whether you're curious about Mars missions searching for ancient life, the subsurface oceans of Europa and Enceladus, or how life might evolve under alien suns, I'm thrilled to be your guide through these cosmic mysteries.

What aspect of astrobiology or space exploration has captured your imagination? Are you wondering about recent discoveries from the James Webb Space Telescope, or perhaps how we might detect life on other worlds?"""

        audio_bytes = await generate_edge_speech(initial_message, "excited")

        audio_url = None
        if audio_bytes:
            timestamp = int(datetime.now().timestamp() * 1000)
            filename = f"cosmos_initial_{timestamp}.mp3"

            temp_dir = "static/temp_audio"
            os.makedirs(temp_dir, exist_ok=True)
            filepath = os.path.join(temp_dir, filename)

            with open(filepath, "wb") as f:
                f.write(audio_bytes)
            audio_url = f"/static/temp_audio/{filename}"

        return JSONResponse({
            "success": True,
            "message": initial_message,
            "audio_url": audio_url,
            "emotion": "excited",
            "scientist": "Dr. Aria Cosmos",
            "field": "Astrobiology"
        })

    except Exception as e:
        logger.error(f"Initial astrobiology message generation failed: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


async def _speak_and_save(text: str, emotion: str, prefer_custom: bool) -> str:
    """
    Tries custom voice first; if it fails/returns empty, retries with edge.
    Returns audio_url or '' if both fail.
    """
    async def _try(use_custom: bool) -> bytes:
        try:
            return await generate_speech(text, emotion, use_custom)
        except Exception as e:
            logger.warning(f"[VOICE] TTS failed (use_custom={use_custom}): {e}")
            return b""

    audio_bytes = await _try(prefer_custom)
    if not audio_bytes:
        logger.warning("[VOICE] Custom TTS returned empty. Retrying with edge...")
        audio_bytes = await _try(False)

    if not audio_bytes:
        logger.error("[VOICE] All TTS attempts failed.")
        return ""

    ts = int(datetime.now().timestamp() * 1000)
    ext = "wav" if prefer_custom else "mp3"  
    filename = f"cosmos_response_{ts}.{ext}"
    temp_dir = "static/temp_audio"
    os.makedirs(temp_dir, exist_ok=True)
    filepath = os.path.join(temp_dir, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
        return f"/static/temp_audio/{filename}"
    except Exception as e:
        logger.error(f"[VOICE] Failed to save audio: {e}")
        return ""


@app.post("/chat-voice")
async def chat_voice(
    audio: UploadFile = File(...),
    use_custom_voice: bool = True,
    session_id: str = "default",
    context_limit: int = 10
):

    try:
        logger.info(f"[VOICE] Upload: {audio.filename} | session={session_id}")

        raw = await audio.read()
        if len(raw) < 100:
            return JSONResponse({"success": False, "error": "Message too short"}, status_code=400)

        transcription = await transcribe_audio(raw)
        logger.info(f"[VOICE] transcription: {transcription}")

        detected_emotion = emotion_classifier.detect_emotion(transcription)

        try:
            structured_context = conversation_history.get_structured_context(
                session_id, message_limit=6, search_limit=6
            )
            context_for_orchestrator = structured_context
        except Exception:
            conversation_context = conversation_history.get_conversation_context(
                session_id, context_limit
            )
            context_for_orchestrator = conversation_context

        try:
            image_intent = await detect_image_generation_intent(
                transcription, session_id, context_for_orchestrator
            )
            _intent_task = (image_intent or {}).get("task", "")
            _intent_conf = float((image_intent or {}).get("confidence", 0) or 0)
            _intent_wants_image = bool((image_intent or {}).get("wants_image", False))

            if _intent_task == "search":
                raise Exception("Not an image request (task=search)")

            if _intent_wants_image and _intent_conf >= 0.6:
                fields = {}
                try:
                    if "expand_image_request" in globals() and callable(globals()["expand_image_request"]):
                        fields = await expand_image_request(
                            transcription, session_id, context_for_orchestrator
                        )
                except Exception as _ie:
                    logger.warning(f"[VOICE] expand_image_request failed: {_ie}")

                topic = (fields.get("topic") or image_intent.get("topic") or "").strip()
                description = (fields.get("description") or image_intent.get("description") or "").strip()
                style = (fields.get("style") or image_intent.get("style") or "scientific illustration").strip()

                if not topic:
                    try:
                        recent = conversation_history.get_recent_searches(session_id, limit=1)
                    except Exception:
                        recent = []
                    if recent:
                        try:
                            payloads = conversation_history.get_search_payloads_by_ids([recent[0]["id"]])
                        except Exception:
                            payloads = []
                        if payloads:
                            data = payloads[0].get("payload") or {}
                            arr = data.get("results") or data.get("papers") or []
                            if isinstance(arr, list) and arr:
                                topic = (arr[0].get("title") or "").strip()[:120]
                                if not description:
                                    description = (arr[0].get("abstract") or "").strip()[:600]

                if not topic:
                    msg = ("You have not yet performed a search to create an image based on. "
                           "Perform a search first or tell us which article/topic to create an image based on.")
                    conversation_history.add_message(
                        session_id, transcription, msg, "contemplative",
                        "image_generation_blocked", "{}"
                    )
                    return JSONResponse({"success": False, "error": msg})

                if not description:
                    description = f"Educational scientific illustration about: {topic}"

                image_url = await generate_article_image(topic=topic, description=description, style=style)

                response_text = f"""I've generated a scientific visualization for **{topic}**!

![Scientific Illustration]({image_url})

**About this visualization:**
{(description or '')[:200]}...

This {style} captures the key aspects of the research. Would you like me to:
- Generate another perspective or style?
- Explain specific elements in the image?
- Search for related research papers?

What aspect interests you most about this topic?"""

                conversation_history.add_message(
                    session_id, transcription, response_text, detected_emotion, "image_generation",
                    json.dumps({
                        "task": _intent_task,
                        "modalities": image_intent.get("modalities", []),
                        "confidence": _intent_conf,
                        "topic": topic,
                        "style": style
                    }, ensure_ascii=False)[:300]
                )

                audio_url = await _speak_and_save(response_text, detected_emotion, use_custom_voice)

                return JSONResponse({
                    "success": True,
                    "mode": "image_generation",
                    "response": response_text,
                    "image_url": image_url,
                    "image_metadata": {
                        "topic": topic,
                        "style": style,
                        "article_reference": fields.get("article_reference")
                            or image_intent.get("article_reference")
                    },
                    "audio_url": audio_url or None,
                    "has_audio": bool(audio_url)
                })

            elif _intent_wants_image and 0.6 <= _intent_conf < 0.9:
                inferred_goal = image_intent.get("user_goal") or "generate a visualization"
                confirm_text = (
                    f"It sounds like you might want an image. "
                    f"Should I generate a visualization for this topic? (yes/no)\n\n"
                    f"Inferred goal: {inferred_goal}"
                )
                conversation_history.add_message(
                    session_id, transcription, confirm_text, detected_emotion,
                    "image_generation_confirmation",
                    json.dumps({
                        "task": _intent_task,
                        "modalities": image_intent.get("modalities", []),
                        "confidence": _intent_conf
                    }, ensure_ascii=False)[:300]
                )

                audio_url = await _speak_and_save(confirm_text, detected_emotion, use_custom_voice)

                return JSONResponse({
                    "success": True,
                    "mode": "image_generation_confirmation",
                    "response": confirm_text,
                    "analysis": {
                        "intent_task": _intent_task,
                        "confidence": _intent_conf,
                        "modalities": image_intent.get("modalities", [])
                    },
                    "audio_url": audio_url or None,
                    "has_audio": bool(audio_url)
                })

        except Exception as img_check_error:
            logger.warning(f"[VOICE] Image intent detection skipped/failed: {img_check_error}")

        analysis = await analyze_user_request(transcription, context_for_orchestrator)
        logger.info(f"[VOICE] analysis: {analysis}")

        details = analysis.get("details") or {}
        refers_to_previous = details.get("refers_to_previous", False)
        target_ids = details.get("target_search_ids") or []

        if not refers_to_previous:
            try:
                recent_searches = conversation_history.get_recent_searches(session_id, limit=10)
            except Exception:
                recent_searches = []
            if recent_searches:
                try:
                    ref = await resolve_previous_search_reference(transcription, recent_searches)
                    if ref.get("is_referring") and ref.get("selected_ids"):
                        refers_to_previous = True
                        target_ids = ref["selected_ids"]
                except Exception as _e:
                    logger.warning(f"[VOICE] resolve_previous_search_reference failed: {_e}")

        if refers_to_previous and target_ids:
            def _merge_payloads(payload_list: List[dict]) -> dict:
                if not payload_list:
                    return {"results": []}
                merged_results = []
                for p in payload_list:
                    if not isinstance(p, dict):
                        continue
                    arr = p.get("results") or p.get("papers") or []
                    if isinstance(arr, list):
                        merged_results.extend(arr)
                return {"results": merged_results}

            try:
                payloads = conversation_history.get_search_payloads_by_ids(target_ids)
            except Exception as _e:
                logger.warning(f"[VOICE] get_search_payloads_by_ids failed: {_e}")
                payloads = []

            raw_payloads = [p.get("payload") for p in payloads if isinstance(p, dict) and p.get("payload") is not None]
            try:
                if "_merge_like_frontend" in globals() and callable(globals()["_merge_like_frontend"]):
                    merged_payload = _merge_like_frontend(raw_payloads, query="(previous selection)")
                else:
                    merged_payload = _merge_payloads(raw_payloads)
            except Exception as _e:
                logger.warning(f"[VOICE] _merge_like_frontend failed, fallback: {_e}")
                merged_payload = _merge_payloads(raw_payloads)

            try:
                discuss_text = await discuss_previous_results_with_gpt(transcription, merged_payload)
            except Exception as _e:
                logger.warning(f"[VOICE] discuss_previous_results_with_gpt failed: {_e}")
                discuss_text = ("I can discuss the previously retrieved papers. Could you specify which aspects you "
                                "want to focus on (methods, findings, limitations, or future work)?")

            conversation_history.add_message(
                session_id, transcription, discuss_text, detected_emotion,
                "discuss_previous_search", json.dumps({"selected_ids": target_ids})[:300]
            )

            audio_url = await _speak_and_save(discuss_text, detected_emotion, use_custom_voice)

            return JSONResponse({
                "success": True,
                "mode": "discuss_previous_search",
                "analysis": analysis,
                "reference": {"selected_ids": target_ids},
                "response": discuss_text,
                "audio_url": audio_url or None,
                "has_audio": bool(audio_url)
            })

        if (
            analysis.get("wants_search")
            and analysis.get("completeness") == "complete"
            and analysis.get("confidence", 0) >= 0.8
            and analysis.get("details")
        ):
            det = analysis["details"]
            user_query = (det.get("query") or "").strip()
            sources = det.get("sources") or []
            per_source_queries = det.get("queries") or {}
            has_per_source_query = any((per_source_queries.get(src) or "").strip() for src in sources)

            if user_query or has_per_source_query:
                downstream_payload = await execute_search_plan(det)
                pretty_text = await _present_search_results_with_gpt(user_query, downstream_payload)

                conversation_history.add_message(
                    session_id, transcription, pretty_text, detected_emotion,
                    "search_results_presented", json.dumps(det)[:300]
                )

                try:
                    conversation_history.save_search(
                        session_id=session_id,
                        user_query=user_query,
                        sources=sources,
                        source_mode=det.get("source_mode"),
                        details_json=json.dumps(det, ensure_ascii=False),
                        results_json=json.dumps(downstream_payload, ensure_ascii=False),
                        pretty_text=pretty_text
                    )
                except Exception as _e:
                    logger.warning(f"[VOICE] save_search failed: {_e}")

                audio_url = await _speak_and_save(pretty_text, detected_emotion, use_custom_voice)

                return JSONResponse({
                    "success": True,
                    "mode": "search_results_presented",
                    "analysis": analysis,
                    "response": pretty_text,
                    "audio_url": audio_url or None,
                    "has_audio": bool(audio_url),
                    "passthrough": downstream_payload
                })

        if analysis.get("wants_search") and analysis.get("completeness") != "complete" and analysis.get("confidence", 0) >= 0.6:
            followups = analysis.get("clarifying_questions") or []
            next_prompt = analysis.get("next_user_prompt") or "Could you specify the missing details?"
            det = analysis.get("details") or {}
            suggested_sources = det.get("sources") or []
            sources_line = f"\n\nSuggested sources: {', '.join(suggested_sources)}" if suggested_sources else ""
            ask = (
                "To run the search, I need a bit more detail:\n"
                + "\n".join([f"• {q}" for q in followups])
                + f"\n\n{next_prompt}"
                + sources_line
            )

            conversation_history.add_message(
                session_id, transcription, ask, "contemplative",
                "search_clarification", json.dumps(analysis.get("details", {}))[:300]
            )

            audio_url = await _speak_and_save(ask, detected_emotion, use_custom_voice)

            return JSONResponse({
                "success": True,
                "mode": "search_clarification",
                "analysis": analysis,
                "response": ask,
                "audio_url": audio_url or None,
                "has_audio": bool(audio_url)
            })

        ai_response = await generate_enhanced_astrobiology_response(
            transcription, detected_emotion, session_id, context_limit, allow_search_fallback=False
        )

        audio_url = await _speak_and_save(ai_response, detected_emotion, use_custom_voice)

        return JSONResponse({
            "success": True,
            "mode": "conversation",
            "message": transcription,          
            "response": ai_response,
            "emotion": detected_emotion,
            "audio_url": audio_url or None,
            "has_audio": bool(audio_url)
        })

    except Exception as e:
        logger.error(f"/chat-voice error: {e}")
        return JSONResponse({"success": False, "error": f"Text processing failed: {e}"}, status_code=500)
        

@app.post("/api/generate-image")
async def generate_image_for_article(request: ImageGenerationRequest):
    try:
        logger.info(f"Image generation request received for session: {request.session_id}")

        image_intent = await detect_image_generation_intent(request.message, request.session_id, request.context)
        if not image_intent.get("wants_image", False):
            return JSONResponse({
                "success": False,
                "error": "Intent to generate image not detected. Tell me to generate image for last search"
            })

        ta = _get_last_paper_title_abstract(request.session_id)
        if not ta:
            msg = "You haven't done any searches yet. Do a search first and I'll create an image for you based on the latest results."
            conversation_history.add_message(request.session_id, request.message, msg,
                                            detected_emotion, "image_generation_blocked", "{}")
            return JSONResponse({"success": False, "error": msg})

        topic, abstract = ta
        topic = topic[:120]
        description = (abstract or f"Educational scientific illustration about {topic}.").strip()[:600]
        style = "scientific illustration"
        
        safe_prompt = _sanitize_image_prompt(topic=topic, description=(description or ""))

        image_url = await generate_article_image(
            topic=topic,
            description=description,
            style=style,
        )


        response_text = f"Generated scientific illustration for: {topic}"
        conversation_history.add_message(
            request.session_id,
            request.message,
            response_text,
            "contemplative",
            "image_generation",
            json.dumps({"topic": topic, "description": description, "style": style}, ensure_ascii=False)[:300]
        )

        return JSONResponse({
            "success": True,
            "image_url": image_url,
            "topic": topic,
            "description": description,
            "style": style,
            "article_reference": topic
        })

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/chat-text")
async def chat_text(request: ChatRequest):
    try:
        logger.info(
            f"Received text: {request.message} | session: {request.session_id}")

        if not request.message or not request.message.strip():
            return JSONResponse({"success": False, "error": "Message too short"}, status_code=400)


        try:
            structured_context = conversation_history.get_structured_context(
                request.session_id, message_limit=6, search_limit=6) 
            context_for_orchestrator = structured_context
        except Exception:
            conversation_context = conversation_history.get_conversation_context(
                request.session_id, request.context_limit)      
            context_for_orchestrator = conversation_context

      
        try:
            image_intent = await detect_image_generation_intent(
                request.message,
                request.session_id,
                context_for_orchestrator
            )

            _intent_task = (image_intent or {}).get("task", "")
            _intent_conf = float((image_intent or {}).get("confidence", 0) or 0)
            _intent_wants_image = bool((image_intent or {}).get("wants_image", False))

            if _intent_task == "search":
                raise Exception("Not an image request (task=search)")

            if _intent_wants_image and _intent_conf >= 0.6:

                fields = {}
                try:
                    if "expand_image_request" in globals() and callable(globals()["expand_image_request"]):
                        fields = await expand_image_request(
                            request.message, request.session_id, context_for_orchestrator
                        )
                except Exception as _ie:
                    logger.warning(f"expand_image_request failed, fallback to intent fields: {_ie}")

                topic = (fields.get("topic") or image_intent.get("topic") or "").strip()
                description = (fields.get("description") or image_intent.get("description") or "").strip()
                style = (fields.get("style") or image_intent.get("style") or "scientific illustration").strip()

                logger.info(f"Image generation triggered: {{'wants_image': True, 'topic': '{topic}', 'style': '{style}', 'confidence': {_intent_conf}}}")
                try:
                    
                    if not topic:
                        try:
                            recent = conversation_history.get_recent_searches(request.session_id, limit=1)
                        except Exception:
                            recent = []

                        if recent:
                            try:
                                payloads = conversation_history.get_search_payloads_by_ids([recent[0]["id"]])
                            except Exception:
                                payloads = []

                            if payloads:
                                data = payloads[0].get("payload") or {}
                                arr = data.get("results") or data.get("papers") or []
                                if isinstance(arr, list) and arr:
                                    topic = (arr[0].get("title") or "").strip()[:120]
                                    if not description:
                                        description = (arr[0].get("abstract") or "").strip()[:600]

                        if not topic:
                            msg = ("You have not yet performed a search to create an image based on. "
                            "Perform a search first or tell us which article/topic to create an image based on.")
                            conversation_history.add_message(
                                request.session_id, request.message, msg,
                                "contemplative", "image_generation_blocked", "{}"
                            )
                            return JSONResponse({"success": False, "error": msg})

                    if not description:
                        description = f"Educational scientific illustration about: {topic}"

                    image_url = await generate_article_image(
                        topic=topic,
                        description=description,
                        style=style
                    )

                    response_text = f"""I've generated a scientific visualization for **{topic}**!

![Scientific Illustration]({image_url})

**About this visualization:**
{(description or '')[:200]}...

This {style} captures the key aspects of the research. Would you like me to:
- Generate another perspective or style?
- Explain specific elements in the image?
- Search for related research papers?

What aspect interests you most about this topic?"""

                    conversation_history.add_message(
                        request.session_id,
                        request.message,
                        response_text,
                        detected_emotion,
                        "image_generation",
                        json.dumps({
                            "task": _intent_task,
                            "modalities": image_intent.get("modalities", []),
                            "confidence": _intent_conf,
                            "topic": topic,
                            "style": style
                        }, ensure_ascii=False)[:300]
                    )

                    audio_bytes = await generate_speech(response_text, detected_emotion, request.use_custom_voice)
                    audio_url = None
                    if audio_bytes:
                        ts = int(datetime.now().timestamp() * 1000)
                        ext = "wav" if request.use_custom_voice else "mp3"
                        filename = f"cosmos_response_{ts}.{ext}"
                        temp_dir = "static/temp_audio"
                        os.makedirs(temp_dir, exist_ok=True)
                        with open(os.path.join(temp_dir, filename), "wb") as f:
                            f.write(audio_bytes)
                        audio_url = f"/static/temp_audio/{filename}"

                    return JSONResponse({
                        "success": True,
                        "mode": "image_generation",
                        "response": response_text,
                        "image_url": image_url,
                        "image_metadata": {
                            "topic": topic,
                            "style": style,
                            "article_reference": fields.get("article_reference") or image_intent.get("article_reference")
                        },
                        "audio_url": audio_url,
                        "has_audio": audio_url is not None
                    })

                except Exception as img_error:
                    logger.error(f"Image generation failed: {img_error}")
                    fallback_response = f"""I understand you want an image about {topic or image_intent.get('topic','this topic')}, but I encountered a technical issue: {str(img_error)}

Could you try rephrasing your request? For example:
- "Create an illustration of extremophiles in hydrothermal vents"
- "Generate a diagram showing the structure of Europa's ocean"

Or would you like me to search for existing images and diagrams in research papers instead?"""

                    conversation_history.add_message(
                        request.session_id,
                        request.message,
                        fallback_response,
                        detected_emotion,
                        "image_generation_failed",
                        str(img_error)[:300]
                    )

                    audio_bytes = await generate_speech(fallback_response, detected_emotion, request.use_custom_voice)
                    audio_url = None
                    if audio_bytes:
                        ts = int(datetime.now().timestamp() * 1000)
                        ext = "wav" if request.use_custom_voice else "mp3"
                        filename = f"cosmos_response_{ts}.{ext}"
                        temp_dir = "static/temp_audio"
                        os.makedirs(temp_dir, exist_ok=True)
                        with open(os.path.join(temp_dir, filename), "wb") as f:
                            f.write(audio_bytes)
                        audio_url = f"/static/temp_audio/{filename}"

                    return JSONResponse({
                        "success": False,
                        "mode": "image_generation_error",
                        "response": fallback_response,
                        "error": str(img_error),
                        "audio_url": audio_url,
                        "has_audio": audio_url is not None
                    })

            elif _intent_wants_image and 0.6 <= _intent_conf < 0.9:
                inferred_goal = image_intent.get("user_goal") or "generate a visualization"
                confirm_text = (
                    f"It sounds like you might want an image. "
                    f"Should I generate a visualization for this topic? (yes/no)\n\n"
                    f"Inferred goal: {inferred_goal}"
                )

                conversation_history.add_message(
                    request.session_id,
                    request.message,
                    confirm_text,
                    detected_emotion,
                    "image_generation_confirmation",
                    json.dumps({
                        "task": _intent_task,
                        "modalities": image_intent.get("modalities", []),
                        "confidence": _intent_conf
                    }, ensure_ascii=False)[:300]
                )

                audio_bytes = await generate_speech(confirm_text, detected_emotion, request.use_custom_voice)
                audio_url = None
                if audio_bytes:
                    ts = int(datetime.now().timestamp() * 1000)
                    ext = "wav" if request.use_custom_voice else "mp3"
                    filename = f"cosmos_response_{ts}.{ext}"
                    temp_dir = "static/temp_audio"
                    os.makedirs(temp_dir, exist_ok=True)
                    with open(os.path.join(temp_dir, filename), "wb") as f:
                        f.write(audio_bytes)
                    audio_url = f"/static/temp_audio/{filename}"

                return JSONResponse({
                    "success": True,
                    "mode": "image_generation_confirmation",
                    "response": confirm_text,
                    "analysis": {
                        "intent_task": _intent_task,
                        "confidence": _intent_conf,
                        "modalities": image_intent.get("modalities", [])
                    },
                    "audio_url": audio_url,
                    "has_audio": audio_url is not None
                })

        except Exception as img_check_error:
            logger.warning(f"Image intent detection skipped/failed: {img_check_error}")


        analysis = await analyze_user_request(request.message, context_for_orchestrator)
        logger.info(f"Analysis: {analysis}")

        details = analysis.get("details") or {}
        refers_to_previous = details.get("refers_to_previous", False)
        target_ids = details.get("target_search_ids") or []

        if not refers_to_previous:
            try:
                recent_searches = conversation_history.get_recent_searches(
                    request.session_id, limit=10)
            except Exception:
                recent_searches = []
            if recent_searches:
                try:
                    ref = await resolve_previous_search_reference(request.message, recent_searches)
                    if ref.get("is_referring") and ref.get("selected_ids"):
                        refers_to_previous = True
                        target_ids = ref["selected_ids"]
                except Exception as _e:
                    logger.warning(
                        f"resolve_previous_search_reference failed: {_e}")

        if refers_to_previous and target_ids:
            def _merge_payloads(payload_list: List[dict]) -> dict:
                if not payload_list:
                    return {"results": []}
                merged_results = []
                for p in payload_list:
                    if not isinstance(p, dict):
                        continue
                    arr = p.get("results") or p.get("papers") or []
                    if isinstance(arr, list):
                        merged_results.extend(arr)
                return {"results": merged_results}

            try:
                payloads = conversation_history.get_search_payloads_by_ids(
                    target_ids)
            except Exception as _e:
                logger.warning(f"get_search_payloads_by_ids failed: {_e}")
                payloads = []

            raw_payloads = [p.get("payload") for p in payloads if isinstance(
                p, dict) and p.get("payload") is not None]

            merged_payload = None
            try:
                if "_merge_like_frontend" in globals() and callable(globals()["_merge_like_frontend"]):
                    merged_payload = _merge_like_frontend(
                        raw_payloads, query="(previous selection)")
                else:
                    merged_payload = _merge_payloads(raw_payloads)
            except Exception as _e:
                logger.warning(
                    f"_merge_like_frontend failed, falling back to simple merge: {_e}")
                merged_payload = _merge_payloads(raw_payloads)

            discuss_text = ""
            try:
                discuss_text = await discuss_previous_results_with_gpt(request.message, merged_payload)
            except Exception as _e:
                logger.warning(
                    f"discuss_previous_results_with_gpt failed: {_e}")
                discuss_text = "I can discuss the previously retrieved papers. Could you specify which aspects you want to focus on (methods, findings, limitations, or future work)?"

            conversation_history.add_message(
                request.session_id,
                request.message,
                discuss_text,
                detected_emotion,
                "discuss_previous_search",
                json.dumps({"selected_ids": target_ids})[:300]
            )

            audio_bytes = await generate_speech(discuss_text, detected_emotion, request.use_custom_voice)
            audio_url = None
            if audio_bytes:
                ts = int(datetime.now().timestamp() * 1000)
                ext = "wav" if request.use_custom_voice else "mp3"
                filename = f"cosmos_response_{ts}.{ext}"
                temp_dir = "static/temp_audio"
                os.makedirs(temp_dir, exist_ok=True)
                with open(os.path.join(temp_dir, filename), "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"/static/temp_audio/{filename}"

            return JSONResponse({
                "success": True,
                "mode": "discuss_previous_search",
                "analysis": analysis,
                "reference": {"selected_ids": target_ids},
                "response": discuss_text,
                "audio_url": audio_url,
                "has_audio": audio_url is not None
            })

       
        if (
            analysis.get("wants_search")
            and analysis.get("completeness") == "complete"
            and analysis.get("confidence", 0) >= 0.8
            and analysis.get("details")
        ):
            details = analysis["details"]
            user_query = (details.get("query") or "").strip()
            sources = details.get("sources") or []
            per_source_queries = details.get("queries") or {}
            has_per_source_query = any(
                (per_source_queries.get(src) or "").strip() for src in sources
            )
            if user_query or has_per_source_query:
                downstream_payload = await execute_search_plan(details)

                pretty_text = await _present_search_results_with_gpt(user_query, downstream_payload)

                conversation_history.add_message(
                    request.session_id,
                    request.message,
                    pretty_text,
                    detected_emotion,
                    "search_results_presented",
                    json.dumps(details)[:300]
                )

                try:
                    conversation_history.save_search(
                        session_id=request.session_id,
                        user_query=user_query,
                        sources=sources,
                        source_mode=details.get("source_mode"),
                        details_json=json.dumps(details, ensure_ascii=False),
                        results_json=json.dumps(
                            downstream_payload, ensure_ascii=False),
                        pretty_text=pretty_text
                    )
                except Exception as _e:
                    logger.warning(f"save_search failed: {_e}")

                audio_bytes = await generate_speech(pretty_text, detected_emotion, request.use_custom_voice)
                audio_url = None
                if audio_bytes:
                    ts = int(datetime.now().timestamp() * 1000)
                    ext = "wav" if request.use_custom_voice else "mp3"
                    filename = f"cosmos_response_{ts}.{ext}"
                    temp_dir = "static/temp_audio"
                    os.makedirs(temp_dir, exist_ok=True)
                    with open(os.path.join(temp_dir, filename), "wb") as f:
                        f.write(audio_bytes)
                    audio_url = f"/static/temp_audio/{filename}"

                return JSONResponse({
                    "success": True,
                    "mode": "search_results_presented",
                    "analysis": analysis,
                    "response": pretty_text,
                    "audio_url": audio_url,
                    "has_audio": audio_url is not None,
                    "passthrough": downstream_payload
                })

        if analysis.get("wants_search") and analysis.get("completeness") != "complete" and analysis.get("confidence", 0) >= 0.6:
            followups = analysis.get("clarifying_questions") or []
            next_prompt = analysis.get(
                "next_user_prompt") or "Could you specify the missing details?"

            details = analysis.get("details") or {}
            suggested_sources = details.get("sources") or []
            sources_line = f"\n\nSuggested sources: {', '.join(suggested_sources)}" if suggested_sources else ""

            ask = (
                "To run the search, I need a bit more detail:\n"
                + "\n".join([f"• {q}" for q in followups])
                + f"\n\n{next_prompt}"
                + sources_line
            )


            conversation_history.add_message(
                request.session_id, 
                request.message, 
                ask,                               
                emotion="contemplative", 
                space_topics="search_clarification", 
                scientific_concepts=json.dumps(analysis.get("details", {}))[:300]
            )

            audio_bytes = await generate_speech(ask, detected_emotion, request.use_custom_voice)
            audio_url = None
            if audio_bytes:
                ts = int(datetime.now().timestamp() * 1000)
                ext = "wav" if request.use_custom_voice else "mp3"
                filename = f"cosmos_response_{ts}.{ext}"
                temp_dir = "static/temp_audio"
                os.makedirs(temp_dir, exist_ok=True)
                with open(os.path.join(temp_dir, filename), "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"/static/temp_audio/{filename}"

            return JSONResponse({
                "success": True,
                "mode": "search_clarification",
                "analysis": analysis,
                "response": ask,
                "audio_url": audio_url,
                "has_audio": audio_url is not None
            })

        ai_response = await generate_enhanced_astrobiology_response(
            request.message, detected_emotion, request.session_id, request.context_limit, allow_search_fallback=False
        )

        audio_bytes = await generate_speech(ai_response, detected_emotion, request.use_custom_voice)
        audio_url = None
        if audio_bytes:
            ts = int(datetime.now().timestamp() * 1000)
            ext = "wav" if request.use_custom_voice else "mp3"
            filename = f"cosmos_response_{ts}.{ext}"
            temp_dir = "static/temp_audio"
            os.makedirs(temp_dir, exist_ok=True)
            with open(os.path.join(temp_dir, filename), "wb") as f:
                f.write(audio_bytes)
            audio_url = f"/static/temp_audio/{filename}"

        return JSONResponse({
            "success": True,
            "mode": "conversation",
            "message": request.message,
            "response": ai_response,
            "emotion": detected_emotion,
            "audio_url": audio_url,
            "has_audio": audio_url is not None
        })

    except Exception as e:
        logger.error(f"/chat-text error: {e}")
        return JSONResponse({"success": False, "error": f"Text processing failed: {e}"}, status_code=500)


@app.get("/astrobiology-history/{session_id}")
async def get_astrobiology_history(session_id: str, limit: int = 20):
    try:
        history = conversation_history.get_conversation_context(
            session_id, limit)
        summary = conversation_history.get_user_summary(session_id)

        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "astrobiology_history": history,
            "learning_profile": summary,
            "scientist": "Dr. Aria Cosmos"
        })
    except Exception as e:
        logger.error(f"Error getting astrobiology history: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/search-space-topics")
async def search_space_topics(session_id: str, keyword: str, limit: int = 10):
    try:
        results = conversation_history.search_conversations(
            session_id, keyword, limit)

        return JSONResponse({
            "success": True,
            "results": results,
            "keyword": keyword,
            "session_id": session_id,
            "search_type": "space_topics"
        })
    except Exception as e:
        logger.error(f"Error searching space topics: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/chat-multimodal")
async def chat_multimodal(
    message: str = Form(...),
    image: UploadFile = File(None),
    session_id: str = Form("default"),
    use_custom_voice: bool = Form(True),
    context_limit: int = Form(10)
):
    try:
        logger.info(
            f"[MM] text+image request | session={session_id} | has_image={image is not None}")

        if not message or not message.strip():
            return JSONResponse({"success": False, "error": "Message too short"}, status_code=400)

        detected_emotion = emotion_classifier.detect_emotion(message)

        content_parts = [{"type": "text", "text": message}]

        if image is not None:
            img_bytes = await image.read()
            if img_bytes:
                mime = image.content_type or mimetypes.guess_type(image.filename or "")[
                    0] or "image/png"
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                data_uri = f"data:{mime};base64,{b64}"
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri}
                })

        conversation_context = conversation_history.get_conversation_context(
            session_id, context_limit)
        user_summary = conversation_history.get_user_summary(session_id)

        enhanced_context = ""
        if user_summary.get("session_count", 0) > 0:
            space_interests = ", ".join(
                [t[0] for t in user_summary.get("space_interests", [])[:3]])
            emotion_summary = ", ".join(
                [e[0] for e in user_summary.get("dominant_emotions", [])[:2]])
            enhanced_context = f"""
Student Profile:
- Total astrobiology sessions: {user_summary['session_count']}
- Main space interests: {space_interests}
- Learning approach: {emotion_summary}
- Knowledge level: {user_summary.get('knowledge_level', 'exploring')}

Recent astrobiology discussions:
{conversation_context[-1500:]}
""".strip()

        system_message = SYSTEM_PROMPT
        if enhanced_context:
            system_message += f"\n\nStudent Learning Context:\n{enhanced_context}"

        completion = client.chat.completions.create(
            model="gpt-4o-mini",  
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": content_parts}
            ],
            max_tokens=700,
            temperature=0.8
        )

        ai_response = completion.choices[0].message.content.strip()

        conversation_history.add_message(
            session_id,
            message,
            ai_response,
            detected_emotion,
            "multimodal_image_analysis",
            (enhanced_context or "")[:300]
        )

        audio_bytes = await generate_speech(ai_response, detected_emotion, use_custom_voice)

        audio_url = None
        if audio_bytes:
            timestamp = int(datetime.now().timestamp() * 1000)
            extension = "wav" if use_custom_voice else "mp3"
            filename = f"cosmos_response_{timestamp}.{extension}"
            temp_dir = "static/temp_audio"
            os.makedirs(temp_dir, exist_ok=True)
            filepath = os.path.join(temp_dir, filename)
            try:
                with open(filepath, "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"/static/temp_audio/{filename}"
            except Exception as e:
                logger.error(f"Failed to save audio file: {e}")

        return JSONResponse({
            "success": True,
            "message": message,
            "has_image": image is not None,
            "response": ai_response,
            "emotion": detected_emotion,
            "audio_url": audio_url,
            "has_audio": audio_url is not None,
            "voice_type": "custom" if use_custom_voice else "edge",
            "session_id": session_id
        })

    except Exception as e:
        logger.error(f"[MM] error: {e}")
        return JSONResponse({"success": False, "error": f"Multimodal processing failed: {str(e)}"}, status_code=500)


@app.delete("/clear-astrobiology-history/{session_id}")
async def clear_astrobiology_history(session_id: str):
    try:
        conn = sqlite3.connect(conversation_history.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM conversations WHERE session_id = ?", (session_id,))
        cursor.execute(
            "DELETE FROM user_profiles WHERE session_id = ?", (session_id,))

        deleted_conversations = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(f"Cleared astrobiology history for session {session_id}")

        return JSONResponse({
            "success": True,
            "message": "Astrobiology learning history cleared successfully",
            "deleted_conversations": deleted_conversations,
            "scientist": "Dr. Aria Cosmos"
        })
    except Exception as e:
        logger.error(f"Error clearing astrobiology history: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/space-learning-stats/{session_id}")
async def get_space_learning_stats(session_id: str):
    try:
        summary = conversation_history.get_user_summary(session_id)

        conn = sqlite3.connect(conversation_history.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*) FROM conversations 
            WHERE session_id = ? AND space_topics LIKE '%exoplanet%'
        ''', (session_id,))
        exoplanet_discussions = cursor.fetchone()[0]

        cursor.execute('''
            SELECT COUNT(*) FROM conversations 
            WHERE session_id = ? AND space_topics LIKE '%Mars%'
        ''', (session_id,))
        mars_discussions = cursor.fetchone()[0]

        cursor.execute('''
            SELECT COUNT(*) FROM conversations 
            WHERE session_id = ? AND space_topics LIKE '%extremophile%'
        ''', (session_id,))
        extremophile_discussions = cursor.fetchone()[0]

        conn.close()

        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "learning_summary": summary,
            "space_topics_explored": {
                "exoplanets": exoplanet_discussions,
                "mars_exploration": mars_discussions,
                "extremophiles": extremophile_discussions
            },
            "scientist": "Dr. Aria Cosmos",
            "field": "Astrobiology"
        })
    except Exception as e:
        logger.error(f"Error getting space learning stats: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/cleanup-temp-audio")
async def cleanup_temp_audio():
    try:
        temp_dir = "static/temp_audio"
        if os.path.exists(temp_dir):
            cleaned_count = 0
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    file_age = datetime.now().timestamp() - os.path.getctime(file_path)
                    if file_age > 3600:  # ۱ ساعت
                        os.remove(file_path)
                        cleaned_count += 1

            logger.info(f"Cleaned {cleaned_count} old cosmic audio files")
            return JSONResponse({"success": True, "cleaned_files": cleaned_count})

        return JSONResponse({"success": True, "cleaned_files": 0})
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "scientist": "Dr. Aria Cosmos",
        "field": "Astrobiology",
        "services": {
            "emotion_classifier": emotion_classifier.classifier is not None,
            "openai": bool(client.api_key),
            "xtts": xtts_model is not None,
            "edge_tts": True,
            "astrobiology_database": os.path.exists(conversation_history.db_path)
        },
        "cosmic_status": "Ready to explore the universe! 🌌🔬"
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
