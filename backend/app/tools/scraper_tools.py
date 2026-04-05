import json
import logging
import os
from typing import Any

from bs4 import BeautifulSoup
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
async def scrape_webpage(url: str) -> str:
    """Scrape visible text and links from a webpage, bypassing simple JavaScript blocks.
    
    Useful for extracting job listings from continuous scroll or JavaScript-heavy career pages.
    
    Args:
        url: The URL to scrape.
        
    Returns:
        Structured text containing page content and extracted links, or an error message.
    """
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Navigate and wait for network to be idle to ensure dynamic content loads
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Small extra delay for good measure for frameworks that render post network-idle
            await page.wait_for_timeout(2000)
            
            # Scroll to bottom a few times to trigger lazy loading if any
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
                
            content = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(content, "html.parser")
            
            # Remove scripts and styles
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
                
            # Extract plain text
            text = soup.get_text(separator="\n", strip=True)
            
            # Extract links
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href and href != "#" and not href.startswith("javascript:"):
                    # Quick clean up relative links (rough estimation, could use urljoin as well)
                    if href.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        href = f"{parsed.scheme}://{parsed.netloc}{href}"
                    link_text = a.get_text(strip=True)
                    if link_text:
                        links.append(f"[{link_text}]({href})")
            
            links_text = "\n".join(links[:150]) # limit to 150 links to avoid excessive token usage
            
            # Truncate text if too long
            max_text = 20000
            if len(text) > max_text:
                text = text[:max_text] + "... [TRUNCATED]"
                
            return f"--- PAGE TEXT ---\n{text}\n\n--- EXTRACTED LINKS ---\n{links_text}"
            
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return f"Failed to scrape webpage at {url}. Error: {e}"


@tool
def append_to_google_sheet(sheet_id: str, data: list[dict[str, Any]], tab_name: str = None) -> str:
    """Append a list of dictionaries to a Google Sheet.
    
    The Google Sheet MUST be shared with the Service Account email.
    
    Args:
        sheet_id: The ID of the Google Sheet (found in the URL: docs.google.com/spreadsheets/d/<sheet_id>/edit).
        data: A list of dictionaries representing the rows to append. 
              Example: [{"Job Title": "Engineer", "Link": "http..."}]
              The keys must match the header row of the existing Google Sheet!
        tab_name: (Optional) The name of the specific tab/worksheet to append to (e.g. 'Raw Data').
                  If not provided, defaults to the first sheet.
              
    Returns:
        A success message with the number of rows appended, or an error message.
    """
    import base64
    import gspread
    from google.oauth2.service_account import Credentials
    
    if not data:
        return "No data provided to append."

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = None
    
    # Check for credentials in environment variable (base64 encoded JSON)
    b64_creds = os.getenv("GOOGLE_CREDENTIALS")
    if b64_creds:
        try:
            creds_info = json.loads(base64.b64decode(b64_creds).decode("utf-8"))
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        except Exception as e:
            return f"Failed to parse GOOGLE_CREDENTIALS from environment. Error: {e}"
            
    # Fallback to local file
    if not creds:
        creds_path = os.path.join(os.getcwd(), "google_credentials.json")
        if os.path.exists(creds_path):
            try:
                creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
            except Exception as e:
                return f"Failed to load google_credentials.json. Error: {e}"
        else:
            return ("Authentication failed: Could not find GOOGLE_CREDENTIALS in env or "
                    "google_credentials.json on disk. Please tell the user to configure them.")
            
    if not creds:
        return "Authentication failed: No valid credentials found."

    try:
        client = gspread.authorize(creds)
        
        # Open the spreadsheet by ID
        try:
            spreadsheet = client.open_by_key(sheet_id)
            if tab_name:
                try:
                    sheet = spreadsheet.worksheet(tab_name)
                except gspread.exceptions.WorksheetNotFound:
                     return f"Error: Tab named '{tab_name}' not found in the spreadsheet. Available tabs are: {[ws.title for ws in spreadsheet.worksheets()]}"
            else:
                sheet = spreadsheet.sheet1 # Getting the first sheet
        except gspread.exceptions.SpreadsheetNotFound:
            return f"Error: Spreadsheet with ID '{sheet_id}' not found. Make sure it's shared with the service account."
        except Exception as e:
            return f"Error opening spreadsheet: {e}"
            
        # Get existing headers to map the dictionary
        try:
            existing_headers = sheet.row_values(1)
        except Exception as e:
            return f"Could not read headers from the sheet (row 1). Error: {e}"
            
        if not existing_headers:
            # If sheet is empty, use the keys from the first dict as headers
            existing_headers = list(data[0].keys())
            sheet.append_row(existing_headers)
        else:
            # Verify that the keys from the data actually match the headers.
            # If there's no overlap, we would just append empty rows!
            data_keys = set(data[0].keys()) if data else set()
            header_set = set(existing_headers)
            if not data_keys.intersection(header_set):
                return f"Error: The keys in your data ({list(data_keys)}) do not match ANY of the expected column headers in row 1 of the sheet: {existing_headers}. Please revise your JSON keys to exactly match the existing headers."
            
        # Prepare rows to append based on headers
        rows_to_append = []
        for row_dict in data:
            row_vals = []
            for header in existing_headers:
                row_vals.append(row_dict.get(header, ""))
            rows_to_append.append(row_vals)
            
        # Append the rows
        sheet.append_rows(rows_to_append)
        return f"Successfully appended {len(rows_to_append)} rows to the Google Sheet (ID: {sheet_id})."
        
    except gspread.exceptions.APIError as e:
        return f"Google Sheets API Error: {e}"
    except Exception as e:
        logger.error(f"Error appending to Google Sheet: {e}", exc_info=True)
        return f"Failed to append to Google Sheet. Error: {e}"
