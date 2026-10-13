"""
SearchOS access skill for Bundesgesundheitsministerium (German Federal Health Ministry)
Extracts FAQ question-answer pairs from the Cannabis Act FAQ page.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any


BASE_URL = "https://www.bundesgesundheitsministerium.de"
FAQ_URL = f"{BASE_URL}/en/themen/cannabis/faq-cannabis-act"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}


async def fetch_page(url: str) -> str:
    """Fetch HTML content from the given URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
            return await response.text()


def parse_faq_page(html: str) -> dict[str, Any]:
    """
    Parse the FAQ page and extract all question-answer pairs organized by section.
    
    Returns a dict with:
        - sections: list of section dicts, each containing title and qa_pairs
        - total_questions: total number of Q&A pairs
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    sections = []
    total_questions = 0
    
    # Find all accordion sections
    accordion_sections = soup.find_all(class_='c-collapse-content--accordion')
    
    for section in accordion_sections:
        # Get section title from the first h2 or h3
        header = section.find(['h2', 'h3'], recursive=False)
        if not header:
            continue
            
        section_title = header.get_text().strip()
        # Clean up the title (remove open all/close all buttons text)
        section_title = section_title.replace('open all', '').replace('close all', '').strip()
        
        if not section_title:
            continue
        
        # Find all question buttons in this section
        question_buttons = section.find_all('button', class_='c-collapse-content__tab')
        
        qa_pairs = []
        for btn in question_buttons:
            question_text = btn.get_text().strip()
            if not question_text or len(question_text) < 10:
                continue
            
            # Find the answer - it's in the next sibling div of the parent h3
            parent_h3 = btn.find_parent('h3')
            answer_text = ""
            
            if parent_h3:
                answer_div = parent_h3.find_next_sibling('div')
                if answer_div:
                    # Get clean text, preserving structure
                    answer_text = answer_div.get_text(separator=' ', strip=True)
            
            if answer_text:
                qa_pairs.append({
                    'question': question_text,
                    'answer': answer_text
                })
                total_questions += 1
        
        if qa_pairs:
            sections.append({
                'title': section_title,
                'qa_pairs': qa_pairs,
                'question_count': len(qa_pairs)
            })
    
    return {
        'sections': sections,
        'total_questions': total_questions,
        'url': FAQ_URL
    }


def search_qa_pairs(data: dict[str, Any], query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Search for Q&A pairs matching the query.
    Case-insensitive search in both questions and answers.
    """
    query_lower = query.lower()
    results = []
    
    for section in data.get('sections', []):
        section_title = section.get('title', '')
        
        for qa in section.get('qa_pairs', []):
            question = qa.get('question', '')
            answer = qa.get('answer', '')
            
            # Check if query matches question or answer
            if query_lower in question.lower() or query_lower in answer.lower():
                results.append({
                    'section': section_title,
                    'question': question,
                    'answer': answer,
                    'relevance': 'question_match' if query_lower in question.lower() else 'answer_match'
                })
                
                if len(results) >= limit:
                    return results
    
    return results


def get_section_by_name(data: dict[str, Any], section_name: str) -> dict[str, Any] | None:
    """Get a specific section by its name (case-insensitive partial match)."""
    section_name_lower = section_name.lower()
    
    for section in data.get('sections', []):
        if section_name_lower in section.get('title', '').lower():
            return section
    
    return None


def get_qa_by_index(data: dict[str, Any], section_index: int, qa_index: int) -> dict[str, Any] | None:
    """Get a specific Q&A pair by section and question index."""
    sections = data.get('sections', [])
    
    if section_index < 0 or section_index >= len(sections):
        return None
    
    section = sections[section_index]
    qa_pairs = section.get('qa_pairs', [])
    
    if qa_index < 0 or qa_index >= len(qa_pairs):
        return None
    
    return {
        'section': section.get('title'),
        'question': qa_pairs[qa_index].get('question'),
        'answer': qa_pairs[qa_index].get('answer')
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Functions:
        - get_all: Fetch and return all FAQ Q&A pairs organized by section
        - search: Search for Q&A pairs matching a query
        - get_section: Get all Q&A pairs from a specific section
        - get_qa: Get a specific Q&A pair by section and question index
    
    Parameters:
        - function: The function to execute (required)
        - query: Search query (required for 'search' function)
        - section: Section name (required for 'get_section' function)
        - section_index: Section index (required for 'get_qa' function)
        - qa_index: Question index within section (required for 'get_qa' function)
        - limit: Maximum number of results (optional, default 10 for search)
    """
    function = params.get('function', '')
    
    try:
        # Fetch and parse the FAQ page
        html = await fetch_page(FAQ_URL)
        data = parse_faq_page(html)
        
        if function == 'get_all':
            # Return all Q&A pairs
            return {
                'success': True,
                'data': data,
                'summary': {
                    'total_sections': len(data['sections']),
                    'total_questions': data['total_questions'],
                    'sections_overview': [
                        {'title': s['title'], 'question_count': s['question_count']}
                        for s in data['sections']
                    ]
                }
            }
        
        elif function == 'search':
            query = params.get('query', '').strip()
            if not query:
                return {
                    'success': False,
                    'error': 'query parameter is required for search function'
                }
            
            limit = params.get('limit', 10)
            results = search_qa_pairs(data, query, limit)
            
            return {
                'success': True,
                'query': query,
                'results': results,
                'total_matches': len(results)
            }
        
        elif function == 'get_section':
            section_name = params.get('section', '').strip()
            if not section_name:
                return {
                    'success': False,
                    'error': 'section parameter is required for get_section function'
                }
            
            section = get_section_by_name(data, section_name)
            if not section:
                available_sections = [s['title'] for s in data['sections']]
                return {
                    'success': False,
                    'error': f'Section not found. Available sections: {available_sections}'
                }
            
            return {
                'success': True,
                'section': section
            }
        
        elif function == 'get_qa':
            try:
                section_index = int(params.get('section_index', -1))
                qa_index = int(params.get('qa_index', -1))
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'section_index and qa_index must be integers'
                }
            
            result = get_qa_by_index(data, section_index, qa_index)
            if not result:
                return {
                    'success': False,
                    'error': f'Q&A pair not found. There are {len(data["sections"])} sections.'
                }
            
            return {
                'success': True,
                'qa': result
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: get_all, search, get_section, get_qa'
            }
    
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Error: {str(e)}'
        }