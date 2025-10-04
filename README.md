#  NASA Space Biology Knowledge Engine Astro-Biome & AI Chatbot 

![Team Logo](/image/logo.jpg)

![Astro-Biome]

![Team Logo Motion](/image/logomotion.mp4)

[![NASA Space Apps Challenge](https://img.shields.io/badge/Event-NASA%20Space%20Apps%202025-blue)](https://www.spaceappschallenge.org/)
![Difficulty: Advanced](https://img.shields.io/badge/Difficulty-Advanced-red)
![Subjects: AI, Data, Biology, Space](https://img.shields.io/badge/Subjects-AI%2FML%20%7C%20Knowledge%20Graph%20%7C%20Space%20Biology-green)
![Big Data](https://img.shields.io/badge/Big%20Data-orange)

---

##  Project Overview

![Dashboard](/image/dashboard.png)

**NASA Space Biology Knowledge Engine** Astro-Biome : NASA Space Biology Knowledge Engine is an advanced, AI-powered platform crafted for the [NASA Space Apps Challenge 2025](https://www.spaceappschallenge.org/).  
Our mission is to transform NASA's vast archive of space biology research and publications into a dynamic, interactive resource—making critical bioscience knowledge accessible for researchers, engineers, and mission planners.

---

##  The Challenge

- [**NASA Space Biology Knowledge Engine**](https://www.spaceappschallenge.org/2025/challenges/build-a-space-biology-knowledge-engine/)

**NASA** has generated thousands of **space biology** research articles, experiments, and data points over decades. However, accessing, understanding, and connecting relevant information remains a significant challenge.
Our solution, Astro-Biome, leverages AI, Machine **Summarization**, **Knowledge Graphs**, and Conversational **Chatbot** | **UX—so** users can instantly search, **summarize**, and interact with the latest findings.
Beyond simple **summaries**, Astro-Biome highlights each article’s **objective**, detects whether results are **positive** or **negative**, shows which **topics** are well-studied, and uncovers **research gaps** that still need exploration.

---

##  Core Features

1. **Multi-source Data Crawling & Indexing :** Automated extraction and indexing from 9 major scientific sources (Task Book, NSLSL, PubMed, PMC, EuropePMC, CrossRef, medRxiv, NCBI, doi.org, arXiv, and NASA-exclusive datasets).
2. **Smart Search & Advanced Filtering :** Rapid search by topic, year, study type, keywords, or source with semantic and lexical query support.
3. **AI Summarization (Transformer & RAG) :** Generates concise summaries, multi-level abstracts, and analytical insights using state-of-the-art NLP models and retrieval-augmented generation (RAG).
4. **Biomedical Knowledge Graph :** Visualizes relationships across concepts, genes, conditions, publications, and experiments for structural understanding.
5. **Interactive Dashboard & Visual Analytics :** Trend charts, study distributions, and visual outputs for presentations and research.
6. **Text-to-Speech (TTS) :** Listen to research summaries and chatbot responses for accessibility and rapid review.
7. **Summary Validation :** Confidence scores for summary accuracy and alignment with the original text.
8. **Export & Sharing :** Download results, reports, and knowledge graphs as CSV, PDF, or shareable links.
9. **Responsive, Shareable UI :** Modern dashboard and chat interface for desktop and mobile.
10. **Scalable & Extensible :** Easily add new sources, models, or analytical modules.
11. **Advanced Chatbot Astro-Biome :**  
    - Natural, multi-modal conversational interface powered by GPT-4o  
    - Understands context, research intent, and provides guided search planning  
    - Supports text, voice, image, and multimodal interactions  
    - Capable of generating scientific illustrations, analyzing research, and providing expert-level answers in astrobiology and space bioscience

---

##  AI Chatbot : Astro Bot

![ChatBot](/image/chatbot.png)

- **Special feature** : Dedicated avatar for better user experience.

- **Search** and retrieve information from 9 major scientific sources Task Book, NSLSL, PubMed, PMC, EuropePMC, SB_Publication, OSDR implemented with Python code and does not use API, but rather information is extracted directly from the sources and the results are displayed in the form of a summary and analysis.

- **Role:** Renowned astrobiologist, NASA/ESA research partner, expert in extremophiles, exoplanets, biosignatures, and cosmic biology.

- **Personality:** Warm, enthusiastic, and scientifically rigorous. Explains complex concepts with analogies and real NASA mission examples.

- **Capabilities:**
    - Conversational search and research planning (text or voice)
    - Semantic understanding of user queries and research goals
    - Extraction and visualization of key bioscience topics
    - Generation of scientific illustrations for papers or concepts
    - Multimodal support: text, voice, image, code
    - Session history, user profile analytics, and personalized learning insights
    - Search and retrieve information from 9 major scientific sources Task Book, NSLSL, PubMed, PMC, EuropePMC, SB_Publication, OSDR , ...
    - Image analysis: Identifying and examining visual content related to space research
    - Scope of Response: Only answers questions and topics related to NASA and biospace and does not engage in activities outside this field.

---

## Team Members

- **Amir Hossein Khosravi** (Owner)
- Amir Arsalan Tayebi
- Taha Jafarnejad
- Tanin Mohaghegh
- Fatima Nouri Moghadam
- Setareh Talaiee

> Our team combines expertise in software engineering, machine learning, conversational AI, and space biology—guaranteeing both scientific and technical excellence.

---

## Our target audience

- **Space Biology Researchers :** Hypothesis generation, literature review, and gap detection
- **Program Managers & Investors :** Data-driven funding decisions and trend analysis
- **Mission Architects :** Planning for safe, efficient lunar and Martian exploration
- **Educators & Students :** Accessible space biology knowledge, AI-powered learning

---


## Innovation & Competitive Edge

- **Conversational AI Search :** Plan and execute complex queries through natural language and guided dialogue
- **Multi-modal Interaction :** Supports text, speech, images, and research documents
- **Knowledge Graphs & RAG :** Visual and semantic organization of bioscience data, leveraging latest trends in 2024 AI research
- **Automated Summarization & Validation :** Multi-level summaries, confidence scoring, and scientific alignment
- **Session-based Analytics :** Personalized learning history, user profile tracking, and session export
- **Dedicated Avatar** : Avatar for better user experience and greater user interaction
---

## Quick Start

1. **Clone the repository:**  
   `git clone https://github.com/astrobiome/Engine_Astro_Biome.git`
2. **Install requirements:**  
   `pip install -r requirements.txt`
3. **Run the application:**  
   `python app.py`
4. **Open the dashboard:**  
   [http://localhost:5000](http://localhost:5000)
5. **Run the voice.py** : (To listen to the article as audio, the Python code must be executed.)
   `python voice.py`
6. **Run the ChatBot**
   `ChatBot/python app.py`
7. **open the ChatBot** : To see the chatbot, log in to port 8000.
   [http://localhost:8000](http://localhost:8000)
   
---

##  Resources provided by NASA Contest

- [NASA Open Science Data Repository (OSDR)](https://osdr.nasa.gov)
- [NASA Space Life Sciences Library (NSLSL)](https://extapps.ksc.nasa.gov/NSLSL/)
- [NASA Task Book](https://taskbook.nasaprs.com/)
- The [SB_Publication](https://pmc.ncbi.nlm.nih.gov/) dataset (608 papers) initially contained only titles and links.

---

---

## Resources added by our Astro-Biome team

- [Europe PMC](https://www.thelancet.com/)
- [NCBI GEO](https://www.ncbi.nlm.nih.gov/geo/)
- [PubMed](https://pubmed.ncbi.nlm.nih.gov/)
- [Crossref](https://link.springer.com/)
- [OpenAlex](https://openalex.org)
---

##  Unique Aspects

- **Conversational research orchestration** : Plan, refine, and execute searches in dialogue

- **Multi-source, context-aware retrieval** : Pulls from NASA, PubMed, and global databases, guided by user intent and session history

- **Python-based search engine (no API)** : Custom-built search using Python web scraping and parsing for retrieving enriched scientific data

- **Image Analysis** : Detect and analyze visual content relevant to **space biology** and research

- **Dedicated Avatar** : Personalized **avatar** for enhanced user experience and engagement

- **Voice and image support** : Users can interact via **speech** or **upload** or **images/documents** for analysis

 - **Ability to save** : Ability to save **activity** in **csv**** format, **knowledge graph** in **json**, **save searches** in **csv** file

---

## Image Engine Astro-Biome

![Main Dashboard Dark](/image/dashboard.png)

![Main Dashboard Light](/image/dashboard-light.png)

![Knowledge graph](/imge/Knowledge-graph.png)

![Activity Report](/image/Activity-Report.png)

![Advanced Search Dark](/image/Advanced-Search.png)

![Advanced Search Light](/image/Advanced-Search-light.png)

![Advanced-Search-Read-the-article](/image/Advanced-Search-Read-article.png)

![Advanced-Search-article](/image/Advanced-Search-article.png)

![Column-chart-analysis](/image/Column-chart-of-analysis-of-the-word-Bone.png)

![ChatBot UI](/image/chatbot.png)

![ChatBot Avatar](/image/avatar.png)

> **Empowering the next generation of space biology research and discovery. Explore the cosmos with us!**
