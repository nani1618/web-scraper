import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
from groq import Groq
import textwrap
from typing import List, Dict
import pandas as pd
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
from urllib.parse import quote_plus
from datetime import datetime, timedelta
import random
import os

# Check and install Playwright browsers if necessary (first run or Streamlit Cloud)
try:
    # Only attempt to import and check if we're on Streamlit Cloud or first run
    import playwright
    from playwright.sync_api import sync_playwright
    
    # Create a placeholder for initialization status
    if 'playwright_initialized' not in st.session_state:
        st.session_state.playwright_initialized = False
    
    # Check if we need to install browsers
    if not st.session_state.playwright_initialized:
        with st.spinner("Setting up browser automation (first run only)..."):
            import subprocess
            try:
                # Run the installation command
                result = subprocess.run(
                    ["playwright", "install", "chromium"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                st.session_state.playwright_initialized = True
            except subprocess.CalledProcessError as e:
                st.warning(f"Playwright browser installation failed, but the app may still work with Selenium: {e.stderr}")
            except Exception as e:
                st.warning(f"Couldn't initialize Playwright: {str(e)}")
except ImportError:
    # Playwright is not installed, but that's fine - we'll try Selenium first
    pass

# HTML processing and LLM functions
def get_html_content(url: str) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    # Add timeout to avoid hanging
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.text

def get_html_content_selenium(url: str, wait_time: int = 5) -> str:
    """
    Get HTML content using Selenium for dynamic content loading
    
    Args:
        url: URL to fetch
        wait_time: Time to wait for dynamic content to load
        
    Returns:
        HTML content as string
    """
    try:
        driver = setup_driver()
        driver.get(url)
        
        # Wait for dynamic content to load
        time.sleep(wait_time)
        
        # Get the page source
        html_content = driver.page_source
        
        return html_content
    except Exception as e:
        st.error(f"Error fetching content with Selenium: {str(e)}")
        return ""
    finally:
        driver.quit()

def process_chunk_with_llm(client, chunk: str, platform: str = "ebay") -> Dict:
    """
    Process the extracted text with LLM to extract product details.
    
    Args:
        client: The LLM client
        chunk: The text chunk to process
        platform: The platform/website being processed (ebay, walmart, flipkart, aliexpress, oyorooms)
        
    Returns:
        Dict containing the extracted product information
    """
    
    if platform.lower() == "ebay":
        prompt = f"""
        Extract product details from the following eBay product page text and return in JSON format.
        Include all products from the page, not only digital products.
        
        Return a JSON with a "products" array containing all extracted products, like this:
        {{
            "products": [
                {{
                    "name": "Product full name with specifications",
                    "price": "Current price (e.g., $129.99)",
                    "shipping": "Shipping details if available",
                    "condition": "New, Used, etc.",
                    "location": "Seller location if available",
                    "rating": "Seller rating if available",
                    "sold": "Number sold if available",
                    "watchers": "Number of watchers if available"
                }},
                {{
                    "name": "Another product name",
                    ...other fields...
                }}
            ]
        }}
        
        Text: {chunk}
        
        Return only the JSON object without any additional text.
        """
    elif platform.lower() == "flipkart":
        prompt = f"""
        Extract product details from the following Flipkart product page text and return in JSON format.
        
        Return a JSON with a "products" array containing all extracted products, like this:
        {{
            "products": [
                {{
                    "name": "Product full name with specifications",
                    "price": "Current price (e.g., ₹12,999)",
                    "original_price": "Original price if discounted (e.g., ₹15,999)",
                    "discount": "Discount percentage if available (e.g., 23% off)",
                    "rating": "Product rating (e.g., 4.3)",
                    "reviews_count": "Number of reviews and ratings",
                    "highlights": ["key feature 1", "key feature 2"],
                    "availability": "In Stock or Out of Stock",
                    "offers": ["Exchange Offer", "Bank Offer", etc],
                    "delivery": "Delivery information"
                }},
                {{
                    "name": "Another product name",
                    ...other fields...
                }}
            ]
        }}
        
        Text: {chunk}
        
        Return only the JSON object without any additional text.
        """
    elif platform.lower() == "aliexpress":
        prompt = f"""
        Extract product details from the following AliExpress product page text and return in JSON format.
        
        Return a JSON with a "products" array containing all extracted products, like this:
        {{
            "products": [
                {{
                    "name": "Product full name",
                    "price": "Current price",
                    "original_price": "Original price before discount if available",
                    "discount_percentage": "Discount percentage if available",
                    "shipping": "Shipping details",
                    "seller": "Store name",
                    "orders": "Number of orders if available",
                    "rating": "Product rating",
                    "reviews": "Number of reviews",
                    "description": "Short product description"
                }},
                {{
                    "name": "Another product name",
                    ...other fields...
                }}
            ]
        }}
        
        Text: {chunk}
        
        Return only the JSON object without any additional text.
        """
    elif platform.lower() == "oyorooms":
        prompt = f"""
        Extract hotel listing details from the following OYO Rooms page text and return in JSON format.
        
        Return a JSON with a "hotels" array containing all extracted hotel listings, like this:
        {{
            "hotels": [
                {{
                    "name": "Full hotel name",
                    "original_price": "Original price (e.g., ₹1595)",
                    "discounted_price": "Discounted price (e.g., ₹599)",
                    "discount_percentage": "Discount percentage (e.g., 73% off)",
                    "location": "Hotel location/area",
                    "rating": "Customer rating (e.g., 3.2)",
                    "total_ratings": "Number of ratings",
                    "rating_text": "Rating description (e.g., Good, Very Good)",
                    "amenities": ["list", "of", "amenities"],
                    "popularity": "Booking information if available",
                    "tags": ["Wizard Member", "etc"]
                }},
                {{
                    "name": "Another hotel name",
                    ...other fields...
                }}
            ]
        }}
        
        Text: {chunk}
        
        Return only the JSON object without any additional text.
        """
    else:
        # Generic prompt for other platforms
        prompt = f"""
        Extract product details from the following text and return them in JSON format.
        
        Return a JSON with a "products" array containing all extracted products, like this:
        {{
            "products": [
                {{
                    "name": "Product Name 1",
                    "price": "Price Value",
                    "no_of_reviews": "Number of reviews",
                    "availability": "Availability status",
                    "description": "Product description",
                    ...any other relevant fields...
                }},
                {{
                    "name": "Another product name",
                    ...other fields...
                }}
            ]
        }}
        
        Text: {chunk}
        
        Return only the JSON object without any additional text.
        """
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        top_p=0.9,
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

def process_url(client, url: str, platform: str = "ebay", chunk_size: int = 8000) -> List[Dict]:
    try:
        # Use Selenium for OYO Rooms to handle dynamic content
        if platform.lower() == "oyorooms":
            html = get_html_content_selenium(url, wait_time=10)
        else:
            html = get_html_content(url)
            
        soup = BeautifulSoup(html, 'html.parser')
        for element in soup(['script', 'style', 'iframe']):
            element.decompose()
        
        body_content = soup.body.text
        
        # Always chunk the content to find more products
        chunks = textwrap.wrap(body_content, chunk_size, break_long_words=False)
        all_items = []
        
        # Process each chunk separately to find products/hotels
        for i, chunk in enumerate(chunks):
            st.text(f"Processing chunk {i+1}/{len(chunks)}...")
            result = process_chunk_with_llm(client, chunk, platform)
            
            # Extract products or hotels from the result depending on platform
            if platform.lower() == "oyorooms":
                if "hotels" in result and isinstance(result["hotels"], list):
                    # Mark which chunk this came from
                    for hotel in result["hotels"]:
                        hotel["chunk_id"] = i+1
                    all_items.extend(result["hotels"])
            else:
                if "products" in result and isinstance(result["products"], list):
                    # Mark which chunk this came from
                    for product in result["products"]:
                        product["chunk_id"] = i+1
                    all_items.extend(result["products"])
        
        # Return all found items
        if platform.lower() == "oyorooms":
            st.text(f"Found {len(all_items)} hotels across {len(chunks)} chunks")
        else:
            st.text(f"Found {len(all_items)} products across {len(chunks)} chunks")
        return all_items
            
    except Exception as e:
        st.error(f"Processing failed: {str(e)}")
        return [{"error": f"Processing failed: {str(e)}"}]

# URL extraction functions from App1.py

def setup_driver():
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Check for Streamlit Cloud environment (special handling required)
        is_streamlit_cloud = os.environ.get('STREAMLIT_SHARING', '') == 'true'
        
        if is_streamlit_cloud:
            # For Streamlit Cloud, we need to use the WebDriver manager to get the driver
            st.info("Running on Streamlit Cloud - using webdriver_manager")
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.core.utils import ChromeType
            from selenium.webdriver.chrome.service import Service
            
            service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            # For local execution, use the standard approach
            driver = webdriver.Chrome(options=chrome_options)
            
        return driver
    except Exception as e:
        # Display error details for troubleshooting
        st.error(f"Error setting up Chrome driver: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        
        # Try alternative approach with playwright
        try:
            st.info("Trying alternative browser automation with Playwright...")
            # Import here to not require it unless needed
            import playwright.sync_api as pw
            
            # Create browser instance
            browser = pw.sync_playwright().start().chromium.launch(headless=True)
            page = browser.new_page()
            
            # Create a wrapper to mimic webdriver interface
            class PlaywrightWrapper:
                def __init__(self, browser, page):
                    self.browser = browser
                    self.page = page
                
                def get(self, url):
                    self.page.goto(url)
                
                def page_source(self):
                    return self.page.content()
                
                def quit(self):
                    self.browser.close()
                
                @property
                def page_source(self):
                    return self.page.content()
            
            return PlaywrightWrapper(browser, page)
            
        except Exception as alt_e:
            st.error(f"Alternative browser automation also failed: {str(alt_e)}")
            raise

def extract_ebay_product_urls(query, progress_bar):
    """Extract eBay search page URLs"""
    base_url = "https://www.ebay.com"
    pages = []
    max_pages = 5
    
    try:
        for page in range(1, max_pages + 1):
            progress_bar.progress(page / max_pages)
            
            encoded_query = quote_plus(query)
            if page == 1:
                search_url = f"{base_url}/sch/i.html?_nkw={encoded_query}&_ipg=240"
            else:
                search_url = f"{base_url}/sch/i.html?_nkw={encoded_query}&_ipg=240&_pgn={page}"
            
            pages.append({'url': search_url})
            time.sleep(0.5)
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    progress_bar.progress(1.0)
    return pages

def extract_walmart_product_urls(query, progress_bar):
    """Extract Walmart search page URLs"""
    base_url = "https://www.walmart.com"
    pages = []
    max_pages = 5
    
    try:
        for page in range(1, max_pages + 1):
            progress_bar.progress(page / max_pages)
            
            search_url = f"{base_url}/search?q={query.replace(' ', '+')}&page={page}"
            pages.append({'url': search_url})
            time.sleep(0.5)
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    progress_bar.progress(1.0)
    return pages

def extract_aliexpress_urls(query, progress_bar, num_pages=5):
    """Extract AliExpress search page URLs"""
    base_url = "https://www.aliexpress.com"
    pages = []
    
    try:
        for page in range(1, num_pages + 1):
            progress_bar.progress(page / num_pages)
            
            # Format for AliExpress search pages
            search_url = f"{base_url}/wholesale?SearchText={query.replace(' ', '+')}&page={page}"
            pages.append({'url': search_url})
            
            # Add random delay between requests to avoid rate limiting
            time.sleep(random.uniform(1.0, 2.0))
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    progress_bar.progress(1.0)
    return pages

def extract_flipkart_product_urls(query, progress_bar, num_pages=1):
    """Extract Flipkart search page URLs"""
    pages = []
    
    try:
        for page in range(1, num_pages + 1):
            progress_bar.progress(page / num_pages)
            url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}&page={page}"
            pages.append({'url': url})
            
            # Add longer random delay between Flipkart requests to avoid rate limiting
            time.sleep(random.uniform(2.0, 3.5))
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    progress_bar.progress(1.0)
    return pages

def extract_oyorooms_urls(query, progress_bar):
    """Extract OYO Rooms search page URLs"""
    base_url = "https://www.oyorooms.com"
    pages = []
    max_pages = 5
    
    try:
        # Extract city from query
        city = query.strip()
        
        # Create sample dates for check-in and check-out (next day)
        today = datetime.now()
        tomorrow = today.strftime("%d/%m/%Y")
        day_after = (today + timedelta(days=1)).strftime("%d/%m/%Y")
        
        # URL-encode the dates properly (replace / with %2F)
        tomorrow_encoded = tomorrow.replace("/", "%2F")
        day_after_encoded = day_after.replace("/", "%2F")
        
        for page in range(1, max_pages + 1):
            progress_bar.progress(page / max_pages)
            
            # Format for OYO Rooms search pages (city-based search)
            search_url = f"{base_url}/search?checkin={tomorrow_encoded}&checkout={day_after_encoded}&city={city.replace(' ', '%20')}&country=india&guests=1&location={city.replace(' ', '%20')}%2C%20India&rooms=1&searchType=city&page={page}"
            pages.append({'url': search_url})
            time.sleep(0.5)
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    progress_bar.progress(1.0)
    return pages

def get_csv_download_link(df, filename):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV File</a>'
    return href

# Initialize session state
if 'scraping_completed' not in st.session_state:
    st.session_state.scraping_completed = False
if 'results_df' not in st.session_state:
    st.session_state.results_df = None
if 'processing_completed' not in st.session_state:
    st.session_state.processing_completed = False
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = []

# Streamlit UI
st.title("Web Scraper & Data Extractor")

# Sidebar for selecting scraper
with st.sidebar:
    st.title("Web Scrapers")
    scraper_option = "Product Scraper"  # Fixed to Product Scraper only

st.header("E-commerce Product Scraper")

# Scraper selection
scraper_option = st.selectbox(
    "Select Platform",
    ["eBay", "Walmart", "Flipkart", "AliExpress", "OYO Rooms"]
)

# Input field based on selected scraper
if scraper_option == "OYO Rooms":
    user_input = st.text_input("Enter city name (e.g., Hyderabad, Mumbai, Delhi):")
else:
    user_input = st.text_input("Enter search query:")

# Show pages slider for all platforms
num_pages = st.slider("Number of pages to scrape", 1, 10, 3)

# Help text based on platform
if scraper_option == "OYO Rooms":
    st.info("For OYO Rooms, enter a city name to search for hotels. The script will create URLs with default dates (today and tomorrow).")
elif scraper_option == "Flipkart":
    st.warning("Flipkart may block requests if too many are made. Use fewer pages to avoid rate limiting.")

# LLM API Key input
api_key = st.text_input("Enter Groq API Key", type="password")

# Scrape button
if st.button("Scrape & Extract Data"):
    if not user_input:
        st.error("Please enter a search query")
        st.stop()
        
    if not api_key:
        st.error("Please enter your Groq API key")
        st.stop()
        
    # Set up client
    client = Groq(api_key=api_key)
    
    # Initialize progress elements
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    status_text.text("Step 1/2: Generating search URLs...")
    
    try:
        # Generate URLs
        if scraper_option == "eBay":
            urls = extract_ebay_product_urls(user_input, progress_bar)
        elif scraper_option == "Walmart":
            urls = extract_walmart_product_urls(user_input, progress_bar)
        elif scraper_option == "Flipkart":
            urls = extract_flipkart_product_urls(user_input, progress_bar, num_pages)
        elif scraper_option == "AliExpress":
            urls = extract_aliexpress_urls(user_input, progress_bar, num_pages)
        elif scraper_option == "OYO Rooms":
            urls = extract_oyorooms_urls(user_input, progress_bar)
        
        if not urls:
            st.warning("No URLs found. Please try a different search query.")
            st.stop()
        
        # Display URLs (collapsed by default)
        with st.expander(f"Generated {len(urls)} URLs"):
            for i, url_data in enumerate(urls):
                st.text(f"{i+1}. {url_data['url']}")
        
        # Process first few URLs
        max_urls_to_process = min(3, len(urls))
        status_text.text(f"Step 2/2: Extracting data from {max_urls_to_process} URLs...")
        
        extracted_data = []
        urls_to_process = urls[:max_urls_to_process]
        
        for i, url_data in enumerate(urls_to_process):
            url = url_data['url']
            progress_value = 0.5 + ((i+1) / (2 * max_urls_to_process))
            progress_bar.progress(progress_value)
            status_text.text(f"Processing URL {i+1}/{max_urls_to_process}: {url}")
            
            try:
                results = process_url(client, url, scraper_option.lower())
                
                # Add URL to each result
                for result in results:
                    result['source_url'] = url
                
                extracted_data.extend(results)
            
            except Exception as e:
                st.error(f"Error processing URL {url}: {str(e)}")
            
            # Wait a bit between requests
            time.sleep(1)
        
        # Display results
        progress_bar.progress(1.0)
        status_text.text("Processing complete!")
        
        if extracted_data:
            # Create dataframe
            df = pd.DataFrame(extracted_data)
            
            # Display the table
            st.subheader("Extracted Data")
            st.dataframe(df)
            
            # Download button
            csv = df.to_csv(index=False).encode('utf-8')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Filename based on platform
            filename = f"hotels_{timestamp}.csv" if scraper_option == "OYO Rooms" else f"products_{timestamp}.csv"
            download_label = "Download Data (CSV)"
            
            st.download_button(
                label=download_label,
                data=csv,
                file_name=filename,
                mime="text/csv"
            )
            
            # Summary statistics
            st.subheader("Summary")
            if scraper_option == "OYO Rooms":
                st.info(f"Found {len(extracted_data)} hotels from {max_urls_to_process} pages")
            else:
                st.info(f"Found {len(extracted_data)} products from {max_urls_to_process} pages")
        else:
            st.warning("No data could be extracted from the URLs.")
            
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
    
    finally:
        progress_bar.empty()

# Add note about Flipkart Review Scraper
st.markdown("---")
with st.expander("Need to scrape Flipkart reviews?"):
    st.markdown("""
    The Flipkart Review Scraper is available as a separate tool. 
    
    To use it, run this command in your terminal:
    ```
    python flipkart_review_scraper.py
    ```
    
    The review scraper works best when run directly rather than through this interface.
    """)
