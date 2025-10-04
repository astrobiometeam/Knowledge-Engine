from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, UnexpectedAlertPresentException
import csv
import time
import re
import json
from dataclasses import dataclass
from typing import List, Optional
import socket
from urllib.parse import urljoin, urlparse

@dataclass
class TaskBookEntry:
    title: str
    investigator: str
    institution: str
    program: str
    fiscal_year: str
    task_id: str
    description: str
    status: str
    funding: str
    start_date: str
    end_date: str
    keywords: List[str]
    publications: List[str]
    url: str

class NASATaskBookScraper:
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
        self.driver.set_page_load_timeout(120)
        self.driver.implicitly_wait(10)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        self.base_url = "https://taskbook.nasaprs.com/tbp/"
        
    
    def search_tasks(self, programs: List[str] = None, fiscal_year: str = None, keywords: str = None, project_title: str = None, max_results: int = 20) -> List[TaskBookEntry]:
        
        tasks = []
        
        try:
            
            
            
            main_url = urljoin(self.base_url, "index.cfm")
            
            self.driver.get(main_url)
            
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            
            time.sleep(3)
            

            
            self._set_search_filters_main(programs, fiscal_year, keywords, project_title)
            

            self._perform_search()
            

            time.sleep(5)
            

            page_source = self.driver.page_source.lower()
            if "no tasks found" in page_source or "no records found" in page_source:
                
                with open("debug_no_results.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                return tasks
            

            task_links = self._extract_task_links_improved()
            
            if not task_links:
                print("No task link found")

                with open("debug_taskbook_results.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                print(" Results page saved for debug")
                return tasks
            
            print(f" {len(task_links)} task links found")
            

            task_links = task_links[:max_results]
            

            for i, (link, title) in enumerate(task_links, 1):
                print(f"\n Processing task {i}/{len(task_links)}")
                print(f" Title: {title}")
                print(f" Link: {link}")
                
                task = self._extract_single_task(link, i, title)
                if task:
                    tasks.append(task)
                    print(f" Task {i} extracted successfully")
                else:
                    print(f" Error extracting task {i}")
                

                try:
                    self.driver.back()
                    time.sleep(3)
                except:

                    print("Return failed - retry...")
                    self._perform_search()
                    time.sleep(3)
                
        except Exception as e:
            print(f" General error in search: {str(e)} ")
            
        return tasks
    
    def _set_search_filters_main(self, programs: List[str] = None, fiscal_year: str = None, keywords: str = None, project_title: str = None):

        try:
            print(" Starting to set search filters...")
            

            print("Setting divisions...")
            

            division_checkboxes = []
            

            checkbox_selectors = [
                "input[name='division']",
                "input[type='checkbox'][name='division']",
                "input[type='checkbox']"
            ]
            
            for selector in checkbox_selectors:
                try:
                    checkboxes = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f" found with '{selector}': {len(checkboxes)} checkbox")
                    
                    for checkbox in checkboxes:
                        try:
                            name = checkbox.get_attribute('name')
                            value = checkbox.get_attribute('value')
                            title = checkbox.get_attribute('title')
                            
                            print(f"   Checkbox: name='{name}', value='{value}', title='{title}'")
                            
                            if name == 'division' or 'division' in str(name).lower():
                                division_checkboxes.append(checkbox)
                        except:
                            continue
                            
                    if division_checkboxes:
                        break
                        
                except Exception as e:
                    print(f"Error in selector '{selector}': {str(e)}")
                    continue
            
            if not division_checkboxes:
                print(" No division checkbox found - General search...")
                all_checkboxes = self.driver.find_elements(By.TAG_NAME, "input")
                for checkbox in all_checkboxes:
                    try:
                        input_type = checkbox.get_attribute('type')
                        if input_type == 'checkbox':
                            division_checkboxes.append(checkbox)
                    except:
                        continue
            
            print(f"A total of {len(division_checkboxes)} division checkboxes were found")
            
            for checkbox in division_checkboxes:
                try:
                    if checkbox.is_selected():
                        checkbox.click()
                        time.sleep(0.3)
                        print("Unchecked is a checkbox")
                except Exception as e:
                    print(f"Error in uncheck: {str(e)}")
                    continue
            

            if programs:
                programs_selected = 0
                
                for program in programs:
                    program_lower = program.lower()
                    print(f" Search for program: {program}")
                    
                    for checkbox in division_checkboxes:
                        try:
                            value = checkbox.get_attribute('value')
                            title = checkbox.get_attribute('title')
                            

                            match_found = False
                            
                            if value:
                                value_lower = str(value).lower()
                                
                               
                                if (("human" in program_lower and ("2" == value or "ub" in value_lower)) or
                                    ("space" in program_lower and "biology" in program_lower and ("3" == value or "uf" in value_lower)) or
                                    ("physical" in program_lower and ("1" == value or "ug" in value_lower))):
                                    match_found = True
                            
                            
                            if title and not match_found:
                                title_lower = str(title).lower()
                                if (("human" in program_lower and ("ub" in title_lower or "human" in title_lower)) or
                                    ("space" in program_lower and "biology" in program_lower and ("uf" in title_lower or "space" in title_lower)) or
                                    ("physical" in program_lower and ("ug" in title_lower or "physical" in title_lower))):
                                    match_found = True
                            
                            if match_found and not checkbox.is_selected():
                                checkbox.click()
                                programs_selected += 1
                                print(f" Program '{program}' selected (value: {value}, title: {title})")
                                time.sleep(0.3)
                                break
                                
                        except Exception as e:
                            print(f"Error selecting checkbox: {str(e)}")
                            continue
                
                if programs_selected == 0:

                    print(" No apps selected - Select all...")
                    for checkbox in division_checkboxes[:3]:  
                        try:
                            if not checkbox.is_selected():
                                checkbox.click()
                                time.sleep(0.3)
                                print(" An application was selected")
                        except:
                            continue
            else:

                print(" Selecting all apps...")
                for checkbox in division_checkboxes[:3]:  
                    try:
                        if not checkbox.is_selected():
                            checkbox.click()
                            time.sleep(0.3)
                            print(" An application was selected")
                    except:
                        continue
            

            title_filled = False
            title_selectors = [
                "input[name='title']",
                "input[id='title']",
                "input[name='project_title']",
                "input[id='project_title']",
                "input[name*='title']",
                "input[placeholder*='title']",
                "input[placeholder*='Project Title']"
            ]
            
            print(" Search for Project Title field...")
            for selector in title_selectors:
                try:
                    title_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Search with selector '{selector}': {len(title_elements)} elements found")
                    
                    for element in title_elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                element.clear()
                                if project_title:
                                    element.send_keys(project_title)
                                    print(f"The project title '{project_title}' was entered in the title field")
                                elif keywords:
                                    element.send_keys(keywords)
                                    print(f"Keyword '{keywords}' entered in title field")
                                title_filled = True
                                break
                        except Exception as e:
                            print(f"Error filling element: {str(e)}")
                            continue
                    
                    if title_filled:
                        break
                        
                except Exception as e:
                    print(f"Error in selector '{selector}': {str(e)}")
                    continue
            
            
            if fiscal_year:
                print(f"Set fiscal year: {fiscal_year}")
                try:
                    fy_selects = self.driver.find_elements(By.TAG_NAME, "select")
                    
                    for select_elem in fy_selects:
                        try:
                            select_obj = Select(select_elem)
                            options = select_obj.options
                            
                            for option in options:
                                option_text = option.text.strip()
                                if fiscal_year in option_text or fiscal_year.replace('FY', '') in option_text:
                                    select_obj.select_by_visible_text(option_text)
                                    print(f" Fiscal year '{option_text}' selected")
                                    break
                        except:
                            continue
                            
                except Exception as e:
                    print(f" Error setting fiscal year: {str(e)}")
            
            print("Search filters setup complete")
                    
        except Exception as e:
            print(f"General error setting filters: {str(e)}")
    
    def _perform_search(self):

        try:
            print(" Starting search...")
            
            
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                print(f"Alert found: {alert_text}")
                alert.accept()
                time.sleep(1)
                
                
                if "division" in alert_text.lower():
                    print("Resetting programs...")
                    self._fix_division_selection()
                    
            except:
                pass  
            
            
            search_selectors = [
                "input[type='submit'][value*='Search']",
                "input[type='submit'][name*='Search']",
                "input[type='submit'][id*='Search']",
                "input[type='submit']",
                "button[type='submit']",
                "input[value='Start Search']"
            ]
            
            search_button = None
            for selector in search_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"Searching for buttons with '{selector}': {len(buttons)} buttons found")
                    
                    for button in buttons:
                        try:
                            if button.is_displayed() and button.is_enabled():
                                button_text = button.get_attribute('value') or button.text
                                print(f"Button: '{button_text}'")
                                search_button = button
                                break
                        except:
                            continue
                    
                    if search_button:
                        break
                except:
                    continue
            
            if search_button:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
                    time.sleep(1)
                    search_button.click()
                    print(" Search button clicked")
                except Exception as e:
                    print(f"Retrying with JavaScript...")
                    self.driver.execute_script("arguments[0].click();", search_button)
                    print("Search button clicked with JavaScript")
            else:
                
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                if forms:
                    forms[0].submit()
                    print("Form submitted")
            
            
            time.sleep(2)
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                print(f"New Alert: {alert_text}")
                alert.accept()
                
                if "division" in alert_text.lower():
                    print(" Division problem persists - try again...")
                    self._fix_division_selection()
                    return self._perform_search()
                    
            except:
                pass
            
            return True
            
        except Exception as e:
            print(f"Error performing search: {str(e)}")
            return False
    
    def _fix_division_selection(self):

        try:
            print("Fixing division selection problem...")
            
            
            checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            
            
            selected_count = 0
            for checkbox in checkboxes:
                try:
                    if not checkbox.is_selected() and selected_count < 3:
                        checkbox.click()
                        selected_count += 1
                        print(f"Checkbox {selected_count} selected")
                        time.sleep(0.5)
                        
                        if selected_count >= 3:
                            break
                except:
                    continue
            
            print(f"A total of {selected_count} divisions were selected")
            
        except Exception as e:
            print(f" Error solving division problem : {str(e)}")
    
    def _extract_task_links_improved(self) -> List[tuple]:

        links = []
        
        try:
            time.sleep(5)
            

            all_links = self.driver.find_elements(By.TAG_NAME, "a")
            
            for link in all_links:
                try:
                    href = link.get_attribute('href')
                    link_text = link.text.strip()
                    
                    if (href and 
                        'action=public_query_taskbook_content' in href and 
                        'taskid=' in href.lower() and
                        'sort' not in href.lower() and
                        'col=' not in href.lower() and
                        link_text and 
                        len(link_text) > 3):
                        
                        full_url = urljoin(self.base_url, href) if not href.startswith('http') else href
                        
                        if not any(full_url == existing_url for existing_url, _ in links):
                            links.append((full_url, link_text))
                            print(f"Task Link added : {link_text[:50]}...")
                            
                except:
                    continue
                    
        except Exception as e:
            print(f" Error extracting links: {str(e)}")
        
        print(f" Finally {len(links)} valid task links found")
        return links
    
    def _extract_single_task(self, task_url: str, task_num: int, expected_title: str = "") -> Optional[TaskBookEntry]:

        try:
            print(f"Loading task {task_num}: {task_url}")
            
            
            self.driver.get(task_url)
            
            
            time.sleep(8)
            
            
            with open(f"debug_task_{task_num}.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print(f"Task page {task_num} saved for debug")
            
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            if ('no task found' in page_text or 
                'task not available' in page_text or 
                'error' in page_text):
                print(f"Task {task_num} is not available")
                return None
            
            print(f"Task {task_num} page is valid")
            

            task_id = ""
            task_id_match = re.search(r'taskid=(\d+)', task_url, re.IGNORECASE)
            if task_id_match:
                task_id = task_id_match.group(1)
                print(f"Task ID : {task_id}")
            
            # استخراج اطلاعات بر اساس ساختار واقعی NASA TaskBook
            title = self._extract_task_title(expected_title)
            investigator = self._extract_task_investigator()
            institution = self._extract_task_institution()
            program = self._extract_task_program()
            fiscal_year = self._extract_task_fiscal_year()
            description = self._extract_task_description()
            status = self._extract_task_status()
            funding = self._extract_task_funding()
            start_date, end_date = self._extract_task_dates()
            keywords = self._extract_task_keywords()
            publications = self._extract_task_publications()
            
            print(f" Extracted information for task {task_num}:")
            print(f"Title: {title[:50]}..." if title else "Title: not found")
            print(f" Principal Investigator: {investigator}")
            print(f"Institution: {institution}")
            print(f"Program: {program}")
            print(f"Fiscal year: {fiscal_year}")
            print(f" Task ID: {task_id}")
            print(f"Status: {status}")
            print(f"Status: {status}")
            print(f"Keywords: {len(keywords)} items")
            print(f"Publications: {len(publications)} items")
            

            task = TaskBookEntry(
                title=title,
                investigator=investigator,
                institution=institution,
                program=program,
                fiscal_year=fiscal_year,
                task_id=task_id,
                description=description,
                status=status,
                funding=funding,
                start_date=start_date,
                end_date=end_date,
                keywords=keywords,
                publications=publications,
                url=task_url
            )
            

            if title or task_id or investigator:
                return task
            else:
                print(f"Task {task_num} does not have enough information")
                return None
                
        except Exception as e:
            print(f" Error extracting task {task_num}: {str(e)}")
            return None
    
    def _extract_task_title(self, expected_title: str = "") -> str:

        try:
            
            if expected_title and len(expected_title.strip()) > 3:
                return expected_title.strip()
            
            
            headers = self.driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3")
            for header in headers:
                text = header.text.strip()
                if text and len(text) > 10 and "task book" not in text.lower():
                    return text
            
            
            try:
                page_title = self.driver.title
                if page_title and "task book" not in page_title.lower() and len(page_title) > 10:
                    return page_title.strip()
            except:
                pass
            
            
            bold_elements = self.driver.find_elements(By.CSS_SELECTOR, "b, strong")
            for element in bold_elements:
                text = element.text.strip()
                if text and len(text) > 15 and "task" not in text.lower():
                    return text
                    
        except Exception as e:
            print(f" Error extracting title: {str(e)}")
        
        return expected_title if expected_title else ""
    
    def _extract_task_investigator(self) -> str:

        try:

            patterns = [
                r'Principal\s+Investigator[:\s]*([^<\n]+)',
                r'PI[:\s]*([^<\n]+)',
                r'Investigator[:\s]*([^<\n]+)',
                r'Lead[:\s]*([^<\n]+)',
                r'Director[:\s]*([^<\n]+)'
            ]
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    result = match.group(1).strip()
                    result = re.sub(r'\s+', ' ', result)  
                    if result and len(result) > 3 and len(result) < 100:
                        
                        if re.match(r'^[A-Za-z\s\.,\-]+$', result):
                            return result
                            
        except Exception as e:
            print(f" Error extracting researcher: {str(e)}")
        
        return ""
    
    def _extract_task_institution(self) -> str:

        try:
            patterns = [
                r'Institution[:\s]*([^<\n]+)',
                r'Organization[:\s]*([^<\n]+)',
                r'Affiliation[:\s]*([^<\n]+)',
                r'University[:\s]*([^<\n]+)',
                r'Center[:\s]*([^<\n]+)',
                r'Laboratory[:\s]*([^<\n]+)'
            ]
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    result = match.group(1).strip()
                    result = re.sub(r'\s+', ' ', result)
                    if result and len(result) > 5 and len(result) < 200:
                        return result
                        
        except Exception as e:
            print(f" Error extracting institution: {str(e)}")
        
        return ""
    
    def _extract_task_program(self) -> str:

        try:
            patterns = [
                r'Program[:\s]*([^<\n]+)',
                r'Division[:\s]*([^<\n]+)',
                r'Research\s+Area[:\s]*([^<\n]+)',
                r'Field[:\s]*([^<\n]+)'
            ]
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            
            known_programs = [
                "Human Research", "Space Biology", "Physical Sciences",
                "Human Research Program", "Space Biology Program", 
                "Physical Sciences Program"
            ]
            
            
            for program in known_programs:
                if program.lower() in page_text.lower():
                    return program
            
            
            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    result = match.group(1).strip()
                    result = re.sub(r'\s+', ' ', result)
                    if result and len(result) > 3 and len(result) < 100:
                        return result
                        
        except Exception as e:
            print(f" Error extracting program: {str(e)}")
        
        return ""
    
    def _extract_task_fiscal_year(self) -> str:

        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            

            patterns = [
                r'Fiscal\s+Year[:\s]*(FY\s*\d{4})',
                r'FY[:\s]*(\d{4})',
                r'(\d{4})\s*Fiscal\s+Year',
                r'Year[:\s]*(\d{4})',
                r'(FY\d{4})',
                r'(\d{4})'
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE)
                for match in matches:
                    result = match.group(1).strip()

                    year_num = re.search(r'\d{4}', result)
                    if year_num:
                        year = int(year_num.group())
                        if 2000 <= year <= 2030:
                            if not result.startswith('FY'):
                                result = f"FY{result}"
                            return result
                            
        except Exception as e:
            print(f" Error extracting fiscal year: {str(e)}")
        
        return ""
    
    def _extract_task_description(self) -> str:

        try:

            patterns = [
                r'Description[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Abstract[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Summary[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Objective[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Overview[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)'
            ]
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    result = match.group(1).strip()
                    result = re.sub(r'\s+', ' ', result)  
                    if result and len(result) > 50:
                        return result[:1000]  
            
            
            paragraphs = self.driver.find_elements(By.CSS_SELECTOR, "p, div")
            for para in paragraphs:
                text = para.text.strip()
                if text and len(text) > 100 and len(text) < 2000:
                    
                    if not any(keyword in text.lower() for keyword in 
                              ['menu', 'navigation', 'home', 'contact', 'search', 'login']):
                        return text[:1000]
                        
        except Exception as e:
            print(f"Error extracting description: {str(e)}")
        
        return ""
    
    def _extract_task_status(self) -> str:

        try:
            patterns = [
                r'Status[:\s]*([^<\n]+)',
                r'State[:\s]*([^<\n]+)',
                r'Progress[:\s]*([^<\n]+)',
                r'Phase[:\s]*([^<\n]+)'
            ]
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            

            known_statuses = [
                "Active", "Completed", "In Progress", "Ongoing", 
                "Closed", "Suspended", "Cancelled"
            ]
            

            for status in known_statuses:
                if status.lower() in page_text.lower():
                    return status
            

            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    result = match.group(1).strip()
                    result = re.sub(r'\s+', ' ', result)
                    if result and len(result) > 2 and len(result) < 50:
                        return result
                        
        except Exception as e:
            print(f"Error extracting status: {str(e)}")
        
        return ""
    
    def _extract_task_funding(self) -> str:
        
        try:
            patterns = [
                r'Funding[:\s]*([^<\n]+)',
                r'Budget[:\s]*([^<\n]+)',
                r'Award[:\s]*([^<\n]+)',
                r'Grant[:\s]*([A-Z0-9\-]+)',
                r'(\$[\d,]+(?:\.\d{2})?)',
                r'([A-Z]{2,3}[\d\-]+[A-Z]*)'  
            ]
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            funding_info = []
            
            for pattern in patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    result = match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
                    result = re.sub(r'\s+', ' ', result)
                    if result and len(result) > 2 and result not in funding_info:
                        funding_info.append(result)
            
            return '; '.join(funding_info[:3])  
                        
        except Exception as e:
            print(f"Error extracting funding: {str(e)}")
        
        return ""
    
    def _extract_task_dates(self) -> tuple:

        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            start_patterns = [
                r'Start\s+Date[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'Begin[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'Started[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'From[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
            ]
            
            end_patterns = [
                r'End\s+Date[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'Complete[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'Finish[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'To[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'Until[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
            ]
            
            start_date = ""
            end_date = ""
            

            for pattern in start_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE)
                for match in matches:
                    start_date = match.group(1).strip()
                    break
                if start_date:
                    break
            

            for pattern in end_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE)
                for match in matches:
                    end_date = match.group(1).strip()
                    break
                if end_date:
                    break
            

            if not start_date or not end_date:
                date_range_pattern = r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})\s*[\-–to]\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
                matches = re.finditer(date_range_pattern, page_text, re.IGNORECASE)
                for match in matches:
                    if not start_date:
                        start_date = match.group(1).strip()
                    if not end_date:
                        end_date = match.group(2).strip()
                    break
            
            return start_date, end_date
                        
        except Exception as e:
            print(f"Error extracting dates: {str(e)}")
        
        return "", ""
    
    def _extract_task_keywords(self) -> List[str]:

        keywords = []
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            keyword_patterns = [
                r'Keywords?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Tags?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Topics?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Subject[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)'
            ]
            
            for pattern in keyword_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    keyword_text = match.group(1).strip()
                    if keyword_text:
                        # تقسیم با کاما، سمی‌کالن یا and
                        keyword_list = re.split(r'[,;]|\sand\s', keyword_text)
                        for keyword in keyword_list:
                            clean_keyword = keyword.strip()
                            if len(clean_keyword) > 2 and clean_keyword not in keywords:
                                keywords.append(clean_keyword)
                        if keywords:
                            return keywords[:15]  
        except:
            pass
        
        return keywords
    
    def _extract_task_publications(self) -> List[str]:

        publications = []
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            pub_patterns = [
                r'Publications?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Papers?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'Articles?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)',
                r'References?[:\s]*(.+?)(?:\n\n|\n[A-Z][A-Z\s]+:|$)'
            ]
            
            for pattern in pub_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    pub_text = match.group(1).strip()
                    if pub_text:
                        # تقسیم انتشارات
                        pub_list = re.split(r'\n(?=\d+\.|\w+,|\w+\s+\(\d{4}\))', pub_text)
                        for pub in pub_list:
                            clean_pub = pub.strip()
                            if len(clean_pub) > 20 and clean_pub not in publications:
                                publications.append(clean_pub)
                        if publications:
                            return publications[:10]  
        except:
            pass
        
        return publications
    
    def save_to_csv(self, tasks: List[TaskBookEntry], filename: str):

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                'Title', 'Investigator', 'Institution', 'Program', 'Fiscal_Year',
                'Task_ID', 'Description', 'Status', 'Funding', 'Start_Date', 
                'End_Date', 'Keywords', 'Publications', 'URL'
            ])
            
            for task in tasks:
                writer.writerow([
                    task.title,
                    task.investigator,
                    task.institution,
                    task.program,
                    task.fiscal_year,
                    task.task_id,
                    task.description[:500] + ('...' if len(task.description) > 500 else ''),
                    task.status,
                    task.funding,
                    task.start_date,
                    task.end_date,
                    '; '.join(task.keywords),
                    '; '.join([pub[:100] for pub in task.publications]),
                    task.url
                ])
        
        print(f"{len(tasks)} task saved to file {filename}")
    
    def save_to_json(self, tasks: List[TaskBookEntry], filename: str):
        
        tasks_dict = []
        for task in tasks:
            tasks_dict.append({
                'title': task.title,
                'investigator': task.investigator,
                'institution': task.institution,
                'program': task.program,
                'fiscal_year': task.fiscal_year,
                'task_id': task.task_id,
                'description': task.description,
                'status': task.status,
                'funding': task.funding,
                'start_date': task.start_date,
                'end_date': task.end_date,
                'keywords': task.keywords,
                'publications': task.publications,
                'url': task.url
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(tasks_dict, f, ensure_ascii=False, indent=2)
        
        print(f"{len(tasks)} task saved to JSON file {filename}")
    
    def close(self):
        
        try:
            self.driver.quit()
            print("Browser closed")
        except:
            pass

def main():
    print("=" * 70)
    
    print("Available programs :")
    print("1. Human Research")
    print("2. Space Biology")
    print("3. Physical Sciences")
    
    program_choice = input("Select the desired programs (1,2,3 or all): ").strip()
    programs = []
    if program_choice == 'all' or '1' in program_choice:
        programs.append('Human Research')
    if program_choice == 'all' or '2' in program_choice:
        programs.append('Space Biology')
    if program_choice == 'all' or '3' in program_choice:
        programs.append('Physical Sciences')
    
    if not programs:
        programs = ['Human Research', 'Space Biology', 'Physical Sciences']
    
    fiscal_year = input(" Fiscal year : ").strip()
    keywords = input("Keywords: ").strip()
    project_title = input("title : ").strip()
    max_results = int(input(" Maximum number of results (default 5) : ") or "5")
    
    save_format = input("Save format (csv/json/both) : ").strip().lower()
    if save_format not in ['csv', 'json', 'both']:
        save_format = 'csv'
    
    scraper = None
    try:
        scraper = NASATaskBookScraper(headless=False)
        
        
        tasks = scraper.search_tasks(
            programs=programs,
            fiscal_year=fiscal_year if fiscal_year else None,
            keywords=keywords if keywords else None,
            project_title=project_title if project_title else None,
            max_results=max_results
        )
        
        if tasks:
            timestamp = int(time.time())
            
            if save_format in ['csv', 'both']:
                csv_filename = f"nasa_taskbook_{timestamp}.csv"
                scraper.save_to_csv(tasks, csv_filename)
            
            if save_format in ['json', 'both']:
                json_filename = f"nasa_taskbook_{timestamp}.json"
                scraper.save_to_json(tasks, json_filename)
            
            print(f"\nSearch completed.")
            print(f"{len(tasks)} tasks found")
            

            for i, task in enumerate(tasks, 1):
                print(f"\n--- Task {i} ---")
                print(f"Title: {task.title[:80]}...")
                print(f"Principal Investigator: {task.investigator}")
                print(f"Institution: {task.institution}")
                print(f"Program: {task.program}")
                print(f"Fiscal Year: {task.fiscal_year}")
                print(f"Task ID: {task.task_id}")
                print(f"Status: {task.status}")
                print(f"Funding: {task.funding}")
                print(f"Keywords: {len(task.keywords)} item")
                print(f"Link: {task.url}")
                
        else:
            print(" No valid tasks found!")
            print("Please check the debug files")
            
    except Exception as e:
        print(f"General error in scraping system : {str(e)}")
    
    finally:
        if scraper:
            scraper.close()

if __name__ == "__main__":
    main()