from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import csv
import time
import re
import json
from dataclasses import dataclass, field
from typing import List, Optional
import socket
from urllib.parse import urljoin, urlparse

@dataclass
class Article:
    title: str
    authors: List[str]
    journal: str
    publication_date: str
    volume: str
    pages: str
    doi: str
    nslsl_id: str
    abstract: str
    publication_type: str
    url: str
    keywords: List[str] = field(default_factory=list)


class NSLSLScraper:
    def __init__(self, headless: bool = False):
        options = webdriver.ChromeOptions()
        
        
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--ignore-certificate-errors-spki-list")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        if headless:
            options.add_argument("--headless")
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(10)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        self.base_url = "https://extapps.ksc.nasa.gov/NSLSL/"
        
    
    def search_topic(self, query: str, max_results: int = 20) -> List[Article]:
        
        articles = []
        
        try:
            print(f"Search for topic : {query}")
            
            
            search_url = urljoin(self.base_url, "Search")
            print(f"Loading search page : {search_url}")
            self.driver.get(search_url)
            
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.ID, "searchCriteria"))
            )

            print("Search page loaded")
            
            time.sleep(3)
            
            
            search_box = self.driver.find_element(By.ID, "searchCriteria")
            search_box.clear()
            search_box.send_keys(query)
            print(f"Keyword '{query}' entered")
            
            
            search_box.send_keys(Keys.RETURN)
            print("Search completed")
            
            
            time.sleep(10)
            
            
            article_links = self._extract_article_links()
            
            if not article_links:
                print("No article links found")
                # ذخیره صفحه برای debug
                with open("debug_results_page.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                print("Results page saved for debug")
                return articles
            
            print(f"{len(article_links)} article links found")
            
            
            article_links = article_links[:max_results]
            
            
            for i, link in enumerate(article_links, 1):
                print(f"\n Processing article {i}/{len(article_links)}")
                print(f"Link: {link}")
                
                article = self._extract_single_article(link, i)
                if article:
                    articles.append(article)
                    print(f"Article {i} was successfully extracted")
                else:
                    print(f"Error extracting article {i}")
                
                
                self.driver.back()
                time.sleep(2)
                
        except Exception as e:
            print(f"General error in search: {str(e)}")
            
        return articles
    
    def _extract_article_links(self) -> List[str]:
        
        links = []
        
        try:
            
            selectors = [
                "a[href*='/NSLSL/Search/DetailsForId/']",
                "a[href*='DetailsForId']",
                "a[href*='Details']",
                "cite a",
                ".result a",
                "div[class*='result'] a"
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        print(f"{len(elements)} links with selector '{selector}' found")
                        for elem in elements:
                            href = elem.get_attribute('href')
                            if href and ('DetailsForId' in href or 'Details' in href):
                                full_url = urljoin(self.base_url, href)
                                if full_url not in links:
                                    links.append(full_url)
                        if links:
                            break
                except Exception as e:
                    print(f"Error in selector {selector}: {str(e)}")
                    continue
            
            
            if not links:
                xpath_selectors = [
                    "//a[contains(@href, 'DetailsForId')]",
                    "//a[contains(@href, 'Details')]",
                    "//cite//a",
                    "//div[contains(@class, 'result')]//a"
                ]
                
                for xpath in xpath_selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, xpath)
                        if elements:
                            print(f"{len(elements)} link found with XPath '{xpath}'")
                            for elem in elements:
                                href = elem.get_attribute('href')
                                if href:
                                    full_url = urljoin(self.base_url, href)
                                    if full_url not in links:
                                        links.append(full_url)
                            if links:
                                break
                    except Exception as e:
                        print(f" Error in XPath {xpath}: {str(e)}")
                        continue
            
        except Exception as e:
            print(f"Error extracting links : {str(e)}")
        
        return links
    
    def _extract_single_article(self, article_url: str, article_num: int) -> Optional[Article]:
        
        try:
            
            self.driver.get(article_url)
            time.sleep(5)
            
            
            with open(f"debug_article_{article_num}.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print(f"Article page {article_num} saved for debug")
            
            
            title = self._extract_title_from_detail_page()
            authors = self._extract_authors_from_detail_page()
            journal = self._extract_journal_from_detail_page()
            year = self._extract_year_from_detail_page()
            volume = self._extract_volume_from_detail_page()
            pages = self._extract_pages_from_detail_page()
            doi = self._extract_doi_from_detail_page()
            nslsl_id = self._extract_nslsl_id_from_detail_page()
            abstract = self._extract_abstract_from_detail_page()
            publication_type = self._extract_publication_type_from_detail_page()
            keywords = self._extract_keywords_from_detail_page()
            
            print(f"Extracted information for article {article_num} : ")
            print(f"Title : {title[:50]}..." if title else "Title: not found")
            print(f"Authors : {len(authors)} people")
            print(f" Journal: {journal[:30]}..." if journal else " Journal: not found")
            print(f"Year: {year}")
            print(f"Abstract: {len(abstract)} characters" if abstract else "Abstract: not found")
            print(f"   NSLSL ID: {nslsl_id}")
            
            
            article = Article(
                title=title,
                authors=authors,
                journal=journal,
                publication_date=year,
                volume=volume,
                pages=pages,
                doi=doi,
                nslsl_id=nslsl_id,
                abstract=abstract,
                publication_type=publication_type,
                url=article_url
            )
            
            
            if title or nslsl_id:
                return article
            else:
                print(f"⚠️ Article {article_num} does not have enough information")
                return None
                
        except Exception as e:
            print(f"Error extracting article {article_num} : {str(e)}")
            return None
    
    def _extract_title_from_detail_page(self) -> str:

        title_selectors = [
            "h1.title",
            "h1",
            "h2.title", 
            "h2",
            ".title h1",
            ".title h2",
            "[class*='title']",
            "#title",
            ".article-title",
            ".publication-title"
        ]
        
        for selector in title_selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                title = element.text.strip()
                if title and len(title) > 10 and not title.startswith(('NASA', 'NSLSL', 'Search')):
                    return title
            except:
                continue
        

        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            

            skip_patterns = [
                'NASA', 'NSLSL', 'Search', 'Home', 'Menu', 'Login',
                'Copyright', 'Privacy', 'Contact', 'Help', 'About',
                'Data provided by', 'Scientific and Technical Information'
            ]
            
            for line in lines:
                if (len(line) > 15 and 
                    not any(pattern in line for pattern in skip_patterns) and
                    not line.startswith(('http', 'www', 'doi:', 'NSLSL ID:', 'Author'))):
                    return line[:200]  # محدود کردن طول
        except:
            pass
        
        return ""
    
    def _extract_authors_from_detail_page(self) -> List[str]:

        authors = []
        

        author_selectors = [
            ".authors",
            ".author",
            "[class*='author']",
            ".byline",
            ".creator"
        ]
        
        for selector in author_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if text and len(text) > 2:
                        # تقسیم نویسندگان
                        author_list = re.split(r'[,;]|\sand\s|\s&\s', text)
                        for author in author_list:
                            clean_author = re.sub(r'\s+', ' ', author.strip())
                            if len(clean_author) > 2 and clean_author not in authors:
                                authors.append(clean_author)
                if authors:
                    return authors[:10]  
            except:
                continue
        

        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            author_patterns = [
                r'Author(?:s)?:\s*(.+?)(?:\n|$)',
                r'By:\s*(.+?)(?:\n|$)',
                r'Written by:\s*(.+?)(?:\n|$)',
                r'Creator(?:s)?:\s*(.+?)(?:\n|$)'
            ]
            
            for pattern in author_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    author_text = match.group(1).strip()
                    if author_text:
                        author_list = re.split(r'[,;]|\sand\s|\s&\s', author_text)
                        for author in author_list:
                            clean_author = re.sub(r'\s+', ' ', author.strip())
                            if len(clean_author) > 2 and clean_author not in authors:
                                authors.append(clean_author)
                if authors:
                    return authors[:10]
        except Exception as e:
            print(f"Error extracting authors : {str(e)}")
        
        return authors
    
    def _extract_abstract_from_detail_page(self) -> str:

        print("Search for abstract...")
        
        
        abstract_selectors = [
            "#abstract",
            ".abstract",
            ".summary", 
            "[class*='abstract']",
            "[class*='summary']",
            ".description",
            "[id*='abstract']",
            "[id*='summary']",
            "div.abstract",
            "p.abstract",
            "section.abstract"
        ]
        
        for selector in abstract_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if text and len(text) > 50:
                        print(f"Abstract found with selector '{selector}': {len(text)} characters")
                        return text
            except Exception as e:
                print(f"Error in selector {selector}: {str(e)}")
                continue
        
        
        xpath_selectors = [
            "//*[contains(@class, 'abstract')]",
            "//*[contains(@id, 'abstract')]",
            "//*[contains(@class, 'summary')]", 
            "//*[contains(text(), 'Abstract')]//following-sibling::*",
            "//*[text()='Abstract']//following-sibling::*",
            "//*[contains(text(), 'Summary')]//following-sibling::*"
        ]
        
        for xpath in xpath_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for element in elements:
                    text = element.text.strip()
                    if text and len(text) > 50:
                        print(f"Abstract found with XPath '{xpath}': {len(text)} characters")
                        return text
            except Exception as e:
                print(f"Error in XPath {xpath}: {str(e)}")
                continue
        
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            print(f"Total length of page text: {len(page_text)} characters")
            
            
            abstract_patterns = [
                r'Abstract\s*[:\-]?\s*(.{50,2000}?)(?:\n\s*\n|\nKeywords?|\nIntroduction|\n[A-Z][A-Z\s]+:|\nReferences|\nConclusion)',
                r'Summary\s*[:\-]?\s*(.{50,2000}?)(?:\n\s*\n|\nKeywords?|\nIntroduction|\n[A-Z][A-Z\s]+:|\nReferences|\nConclusion)',
                r'ABSTRACT\s*[:\-]?\s*(.{50,2000}?)(?:\n\s*\n|\nKEYWORDS?|\nINTRODUCTION|\n[A-Z][A-Z\s]+:|\nREFERENCES|\nCONCLUSION)',
                r'Description\s*[:\-]?\s*(.{50,2000}?)(?:\n\s*\n|\nKeywords?|\nIntroduction|\n[A-Z][A-Z\s]+:|\nReferences)',
                r'Overview\s*[:\-]?\s*(.{50,2000}?)(?:\n\s*\n|\nKeywords?|\nIntroduction|\n[A-Z][A-Z\s]+:|\nReferences)'
            ]
            
            for i, pattern in enumerate(abstract_patterns, 1):
                print(f"Checking pattern {i}: {pattern[:50]}...")
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    abstract = match.group(1).strip()
                    abstract = re.sub(r'\s+', ' ', abstract)  # پاک‌سازی فضاهای اضافی
                    if len(abstract) > 100:
                        print(f"Abstract found with pattern {i}: {len(abstract)} characters")
                        print(f"Start of text : {abstract[:100]}...")
                        return abstract
            
            
            paragraphs = page_text.split('\n\n')
            print(f"{len(paragraphs)} paragraphs found")
            
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if (len(para) > 200 and len(para) < 2000 and 
                    not para.startswith(('NASA', 'NSLSL', 'Copyright', 'Privacy', 'Home', 'Menu', 'Search')) and
                    not any(word in para.upper() for word in ['MENU', 'LOGIN', 'SEARCH', 'NAVIGATION', 'COPYRIGHT'])):
                    
                    
                    scientific_indicators = ['research', 'study', 'analysis', 'method', 'result', 'conclusion', 
                                           'experiment', 'data', 'finding', 'investigation', 'approach']
                    
                    if any(word in para.lower() for word in scientific_indicators):
                        print(f"Abstract text found in paragraph {i+1}: {len(para)} characters")
                        print(f" Start of text : {para[:100]}...")
                        return para[:1500]  
            
        except Exception as e:
            print(f"Error parsing page text: {str(e)}")
        
        print("Abstract not found")
        return ""
    
    def _extract_keywords_from_detail_page(self) -> List[str]:
        
        keywords = []
        try:
            
            selectors = ["#keywords", ".keywords", "[class*='keyword']", "[id*='keyword']"]
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        lis = elem.find_elements(By.TAG_NAME, "li")
                        if lis:
                            for li in lis:
                                text = li.text.strip()
                                if text:
                                    keywords.append(text)
                        else:
                            text = elem.text.strip()
                            if text:
                                parts = [p.strip() for p in re.split(r'[,;]', text) if p.strip()]
                                keywords.extend(parts)
                    if keywords:
                        return keywords
                except:
                    continue

            
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            pattern = r"Keywords\s*[:\-]?\s*(.+?)(?:\n\s*\n|Publication Types|Languages|Biological Classifications|Attachments|Number of Views|$)"
            m = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
            if m:
                block = m.group(1).strip()
                parts = [p.strip() for p in re.split(r'[\n,;•]', block) if p.strip()]
                keywords.extend(parts)

            return keywords
        except Exception as e:
            print(f"Error extracting Keywords: {e}")
            return []

            
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            pattern = r"Keywords\s*[:\-]?\s*(.+?)(?:\n\s*\n|Publication Types|Languages|Biological Classifications|Attachments|Number of Views|$)"
            m = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
            if m:
                block = m.group(1).strip()
                parts = [p.strip() for p in re.split(r'[\n,;•]', block) if p.strip()]
                return parts

        except Exception as e:
            print(f"Error extracting Keywords: {e}")
        return []
    def _extract_journal_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            journal_patterns = [
                r'Journal:\s*(.+?)(?:\n|$)',
                r'Published in:\s*(.+?)(?:\n|$)',
                r'Source:\s*(.+?)(?:\n|$)',
                r'Publication:\s*(.+?)(?:\n|$)',
                r'Periodical:\s*(.+?)(?:\n|$)',
                r'In:\s*(.+?)(?:\n|$)'
            ]
            
            for pattern in journal_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    journal = match.group(1).strip()
                    
                    journal = re.sub(r'\b\d{4}\b.*', '', journal).strip()
                    journal = re.sub(r'[,;].*', '', journal).strip()
                    if len(journal) > 3:
                        return journal
        except:
            pass
        
        return ""
    #
    def _extract_year_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text

            
            year_patterns = [
                r'Year:\s*(\d{4})',
                r'Date:\s*.*?(\d{4})',
                r'Published:\s*.*?(\d{4})',
                r'Pub Date:\s*(\d{4})',   
                r'\b(19[5-9]\d|20[0-4]\d)\b',   
                r'\.\s*(\d{4})\s+vol\.'         
            ]

            for pattern in year_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    years = [int(year) for year in matches if 1800 <= int(year) <= 2100]
                    if years:
                        return str(max(years))
        except Exception as e:
            print(f"Error extracting year: {e}")

        return ""
    
    def _extract_volume_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            volume_patterns = [
                r'Volume\s*(\d+)',
                r'Vol\.\s*(\d+)',
                r'V\.\s*(\d+)',
                r'Volume:\s*(\d+)'
            ]
            
            for pattern in volume_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)
        except:
            pass
        
        return ""
    
    def _extract_pages_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            page_patterns = [
                r'Pages?\s*(\d+(?:-\d+)?)',
                r'pp?\.\s*(\d+(?:-\d+)?)',
                r'p\.\s*(\d+(?:-\d+)?)',
                r'Pages?:\s*(\d+(?:-\d+)?)'
            ]
            
            for pattern in page_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)
        except:
            pass
        
        return ""
    
    def _extract_doi_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            doi_patterns = [
                r'doi:\s*(10\.\d+/[^\s]+)',
                r'DOI:\s*(10\.\d+/[^\s]+)',
                r'Digital Object Identifier:\s*(10\.\d+/[^\s]+)'
            ]
            
            for pattern in doi_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)
        except:
            pass
        
        return ""
    
    def _extract_nslsl_id_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            nslsl_patterns = [
                r'NSLSL\s*ID:\s*(\d+)',
                r'ID:\s*(\d+)',
                r'Record\s*ID:\s*(\d+)',
                r'Document\s*ID:\s*(\d+)'
            ]
            
            for pattern in nslsl_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            
            url_match = re.search(r'/DetailsForId/(\d+)', self.driver.current_url)
            if url_match:
                return url_match.group(1)
                
        except:
            pass
        
        return ""
    
    def _extract_publication_type_from_detail_page(self) -> str:
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            type_patterns = [
                r'Publication Type:\s*(.+?)(?:\n|$)',
                r'Document Type:\s*(.+?)(?:\n|$)',
                r'Type:\s*(.+?)(?:\n|$)'
            ]
            
            for pattern in type_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        except:
            pass
        
        return "Unknown"
    
    def save_to_csv(self, articles: List[Article], filename: str):
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                'Title', 'Authors', 'Journal', 'publication_date', 'Volume', 'Pages',
                'DOI', 'NSLSL_ID', 'Abstract', 'Publication_Type', 'URL', 'Keywords'
            ])
            
            for article in articles:
                writer.writerow([
                    article.title,
                    '; '.join(article.authors),
                    article.journal,
                    article.publication_date,   
                    # article.year,
                    article.volume,
                    article.pages,
                    article.doi,
                    article.nslsl_id,
                    article.abstract[:500] + ('...' if len(article.abstract) > 500 else ''),
                    article.publication_type,
                    article.url,
                    '; '.join(article.keywords)
                ])
        
        print(f"{len(articles)} articles saved to file {filename}")
    
    def save_to_json(self, articles: List[Article], filename: str):
        
        articles_dict = []
        for article in articles:
            articles_dict.append({
                'title': article.title,
                'authors': article.authors,
                'journal': article.journal,
                'publication_date': article.publication_date, 
                'volume': article.volume,
                'pages': article.pages,
                'doi': article.doi,
                'nslsl_id': article.nslsl_id,
                'abstract': article.abstract,
                'keywords': article.keywords,
                'publication_type': article.publication_type,
                'url': article.url
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(articles_dict, f, ensure_ascii=False, indent=2)
        
        print(f"{len(articles)} articles saved to JSON file {filename}")
    
    def close(self):
        
        try:
            self.driver.quit()
            print("Browser closed")
        except:
            pass

def main():
    print("=" * 50)

    # Default values
    topic = "microgravity"
    max_results = 5
    save_format = "csv"

    scraper = None
    try:
        scraper = NSLSLScraper(headless=False)
        articles = scraper.search_topic(topic, max_results)

        if articles:
            timestamp = int(time.time())

            if save_format in ['csv', 'both']:
                csv_filename = f"{topic}_{timestamp}_articles.csv"
                scraper.save_to_csv(articles, csv_filename)

            if save_format in ['json', 'both']:
                json_filename = f"{topic}_{timestamp}_articles.json"
                scraper.save_to_json(articles, json_filename)

            print(f"\n🎉 Done!")
            print(f"📊 Found {len(articles)} articles")

            # Show summary of results
            for i, article in enumerate(articles, 1):
                print(f"\n--- Article {i} ---")
                print(f"Title: {article.title[:80]}...")
                print(f"Authors: {'; '.join(article.authors[:2])}")
                print(f"Journal: {article.journal}")
                print(f"Publication Date: {article.publication_date}")
                print(f"Abstract: {len(article.abstract)} characters")
                print(f"NSLSL ID: {article.nslsl_id}")
                print(f"Link: {article.url}")

        else:
            print("❌ No articles found!")
            print("💡 Please check the debug files")

    except Exception as e:
        print(f"❌ General Error: {str(e)}")

    finally:
        if scraper:
            scraper.close()

if __name__ == "__main__":
    main()
