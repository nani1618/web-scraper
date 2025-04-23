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
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    return webdriver.Chrome(options=chrome_options)

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
    scraper_option = st.radio(
        "Choose a scraper:",
        ["Product Scraper", "Flipkart Review Scraper"]
    )

if scraper_option == "Product Scraper":
    st.header("E-commerce Product Scraper")
    
    tab1, tab2 = st.tabs(["URL Scraping", "Data Extraction"])
    
    with tab1:
        st.subheader("Step 1: Extract URLs from E-commerce Platforms")
        
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
        
        input_type = "query"
        # Show pages slider for all platforms
        num_pages = st.slider("Number of pages to scrape", 1, 10, 5)
        
        # Help text based on platform
        if scraper_option == "OYO Rooms":
            st.info("For OYO Rooms, enter a city name to search for hotels. The script will create URLs with default dates (today and tomorrow).")
        elif scraper_option == "Flipkart":
            st.warning("Flipkart may block requests if too many are made. Use fewer pages to avoid rate limiting.")
        
        # Scrape button
        if st.button("Start URL Scraping"):
            if user_input:
                progress_bar = st.progress(0)
                progress_text = st.empty()
                
                progress_text.text("Scraping in progress...")
                
                try:
                    if scraper_option == "eBay":
                        results = extract_ebay_product_urls(user_input, progress_bar)
                    elif scraper_option == "Walmart":
                        results = extract_walmart_product_urls(user_input, progress_bar)
                    elif scraper_option == "Flipkart":
                        results = extract_flipkart_product_urls(user_input, progress_bar, num_pages)
                    elif scraper_option == "AliExpress":
                        results = extract_aliexpress_urls(user_input, progress_bar, num_pages)
                    elif scraper_option == "OYO Rooms":
                        results = extract_oyorooms_urls(user_input, progress_bar)
                    
                    if results:
                        st.session_state.results_df = pd.DataFrame(results)
                        st.session_state.scraping_completed = True
                        progress_text.text("Scraping completed!")
                    else:
                        st.warning("No results found.")
                        
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                    
                progress_bar.empty()
        
        # Download section
        if st.session_state.scraping_completed and st.session_state.results_df is not None:
            st.subheader("Results")
            st.dataframe(st.session_state.results_df)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{scraper_option.lower()}_results_{timestamp}.csv"
            
            st.markdown(get_csv_download_link(st.session_state.results_df, filename), unsafe_allow_html=True)
            st.info(f"Found {len(st.session_state.results_df)} URLs")
    
    with tab2:
        st.subheader("Step 2: Extract Product Details with LLM")
        
        api_key = st.text_input("Enter Groq API Key", type="password")
        
        if st.session_state.scraping_completed and st.session_state.results_df is not None:
            if scraper_option == "OYO Rooms":
                st.success(f"{len(st.session_state.results_df)} hotel search URLs ready for processing")
            else:
                st.success(f"{len(st.session_state.results_df)} URLs ready for processing")
            
            num_urls_to_process = st.slider("Number of URLs to process", 
                                           min_value=1, 
                                           max_value=min(10, len(st.session_state.results_df)), 
                                           value=1)
            
            # Button label based on platform
            button_label = "Extract Hotel Details" if scraper_option == "OYO Rooms" else "Extract Product Details"
            
            if st.button(button_label):
                if api_key:
                    client = Groq(api_key=api_key)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    urls_to_process = st.session_state.results_df.head(num_urls_to_process)['url'].tolist()
                    extracted_data = []
                    
                    for i, url in enumerate(urls_to_process):
                        status_text.text(f"Processing URL {i+1}/{len(urls_to_process)}: {url}")
                        progress_bar.progress((i) / len(urls_to_process))
                        
                        results = process_url(client, url, scraper_option.lower())
                        
                        # Add URL to each result
                        for result in results:
                            result['source_url'] = url
                        
                        extracted_data.extend(results)
                        
                        # Don't overload the API
                        time.sleep(1)
                    
                    progress_bar.progress(1.0)
                    status_text.text("Processing complete!")
                    
                    if extracted_data:
                        st.session_state.extracted_data = extracted_data
                        st.session_state.processing_completed = True
                    else:
                        st.warning("No data could be extracted from the URLs.")
                else:
                    st.error("Please enter your Groq API key.")
        else:
            st.info("First extract URLs in the URL Scraping tab")
        
        # Display extracted data
        if st.session_state.processing_completed and st.session_state.extracted_data:
            # Heading based on platform
            heading = "Extracted Hotel Details" if scraper_option == "OYO Rooms" else "Extracted Product Details"
            st.subheader(heading)
            
            # Create dataframe directly from the product list
            if st.session_state.extracted_data:
                df = pd.DataFrame(st.session_state.extracted_data)
                
                # Display the table
                st.dataframe(df)
                
                # Download button
                csv = df.to_csv(index=False).encode('utf-8')
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Filename based on platform
                filename = f"hotels_{timestamp}.csv" if scraper_option == "OYO Rooms" else f"products_{timestamp}.csv"
                download_label = "Download Hotels (CSV)" if scraper_option == "OYO Rooms" else "Download Products (CSV)"
                
                st.download_button(
                    label=download_label,
                    data=csv,
                    file_name=filename,
                    mime="text/csv"
                )
        else:
            if st.session_state.scraping_completed:
                if scraper_option == "OYO Rooms":
                    st.info("Click 'Extract Hotel Details' to process the URLs")
                else:
                    st.info("Click 'Extract Product Details' to process the URLs")

elif scraper_option == "Flipkart Review Scraper":
    # Run the Flipkart Review Scraper
    # Import the main function from the flipkart review scraper
    try:
        from flipkart_review_scraper import main as flipkart_review_main
        flipkart_review_main()
    except Exception as e:
        st.error(f"Error loading Flipkart Review Scraper: {e}")
        st.info("Please ensure flipkart_review_scraper.py is in the same directory.")
