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
from datetime import datetime

# HTML processing and LLM functions
def get_html_content(url: str) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def process_chunk_with_llm(client, chunk: str, platform: str = "amazon") -> Dict:
    """
    Process the extracted text with LLM to extract product details.
    
    Args:
        client: The LLM client
        chunk: The text chunk to process
        platform: The platform/website being processed (amazon, ebay, walmart, alibaba, aliexpress)
        
    Returns:
        Dict containing the extracted product information
    """
    
    if platform.lower() == "amazon":
        prompt = f"""
        Extract product details from the following Amazon product page text and return in JSON format.
        Include all products from the page, not only digital products.
        
        Return a JSON with a "products" array containing all extracted products, like this:
        {{
            "products": [
                {{
                    "name": "Samsung Galaxy S25 Ultra 5G AI Smartphone (Titanium Silverblue, 12GB RAM, 1TB Storage)",
                    "price": "₹1,59,999",
                    "no_of_reviews": 139,
                    "availability": "In stock",
                    "description": "200MP Camera, S Pen Included, Long Battery Life",
                    "color": "Titanium Silverblue",
                    "ram": "12GB",
                    "storage": "1TB",
                    "rating": 4.1,
                    "discount": "4% off",
                    "coupon_discount": "₹6,000 off",
                    "delivery": "FREE delivery Wed, 23 Apr"
                }},
                {{
                    "name": "Another product name",
                    "price": "price value",
                    ...other fields...
                }}
            ]
        }}
        
        Text: {chunk}
        
        Return only the JSON object without any additional text.
        """
    elif platform.lower() == "alibaba":
        prompt = f"""
        Extract product details from the following Alibaba product page text and return in JSON format.
        
        Return a JSON with a "products" array containing all extracted products, like this:
        {{
            "products": [
                {{
                    "name": "Product full name",
                    "price": "Price range or exact price",
                    "moq": "Minimum order quantity",
                    "shipping": "Shipping details",
                    "supplier": "Supplier name",
                    "supplier_rating": "Supplier rating if available",
                    "supplier_country": "Country of supplier",
                    "product_rating": "Product rating if available",
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

def process_url(client, url: str, platform: str = "amazon", chunk_size: int = 8000) -> List[Dict]:
    try:
        html = get_html_content(url)
        soup = BeautifulSoup(html, 'html.parser')
        for element in soup(['script', 'style', 'iframe']):
            element.decompose()
        
        body_content = soup.body.text
        
        # Always chunk the content to find more products
        chunks = textwrap.wrap(body_content, chunk_size, break_long_words=False)
        all_products = []
        
        # Process each chunk separately to find products
        for i, chunk in enumerate(chunks):
            st.text(f"Processing chunk {i+1}/{len(chunks)}...")
            result = process_chunk_with_llm(client, chunk, platform)
            
            # Extract products from the result
            if "products" in result and isinstance(result["products"], list):
                # Mark which chunk this came from
                for product in result["products"]:
                    product["chunk_id"] = i+1
                all_products.extend(result["products"])
        
        # Return all found products
        st.text(f"Found {len(all_products)} products across {len(chunks)} chunks")
        return all_products
            
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

def extract_amazon_product_urls(search_term, progress_bar, num_pages=1):
    """Extract Amazon search page URLs"""
    pages = []
    
    try:
        for page in range(1, num_pages + 1):
            progress_bar.progress(page / num_pages)
            url = f"https://www.amazon.in/s?k={search_term.replace(' ', '+')}&page={page}"
            pages.append({'url': url})
            time.sleep(0.5)
    
    except Exception as e:
        st.error(f"An error occurred: {e}")
    
    return pages

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

def extract_alibaba_urls(query, progress_bar):
    """Extract Alibaba search page URLs"""
    base_url = "https://www.alibaba.com"
    pages = []
    max_pages = 5
    
    try:
        for page in range(1, max_pages + 1):
            progress_bar.progress(page / max_pages)
            
            # Format for Alibaba search pages
            search_url = f"{base_url}/trade/search?keywords={query.replace(' ', '+')}&page={page}"
            pages.append({'url': search_url})
            time.sleep(0.5)
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    progress_bar.progress(1.0)
    return pages

def extract_aliexpress_urls(query, progress_bar):
    """Extract AliExpress search page URLs"""
    base_url = "https://www.aliexpress.com"
    pages = []
    max_pages = 5
    
    try:
        for page in range(1, max_pages + 1):
            progress_bar.progress(page / max_pages)
            
            # Format for AliExpress search pages
            search_url = f"{base_url}/wholesale?SearchText={query.replace(' ', '+')}&page={page}"
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
st.title("Web Scraper & LLM-based Product Extractor")

tab1, tab2 = st.tabs(["URL Scraping", "Data Extraction"])

with tab1:
    st.subheader("Step 1: Extract URLs from E-commerce Platforms")
    
    # Scraper selection
    scraper_option = st.selectbox(
        "Select Platform",
        ["Amazon", "eBay", "Walmart", "Alibaba", "AliExpress"]
    )
    
    # Input field based on selected scraper
    user_input = st.text_input("Enter search query:")
    input_type = "query"
    # Show pages slider only for Amazon
    if scraper_option == "Amazon":
        num_pages = st.slider("Number of pages to scrape", 1, 10, 5)
    
    # Scrape button
    if st.button("Start URL Scraping"):
        if user_input:
            progress_bar = st.progress(0)
            progress_text = st.empty()
            
            progress_text.text("Scraping in progress...")
            
            try:
                if scraper_option == "Amazon":
                    results = extract_amazon_product_urls(user_input, progress_bar, num_pages)
                elif scraper_option == "eBay":
                    results = extract_ebay_product_urls(user_input, progress_bar)
                elif scraper_option == "Walmart":
                    results = extract_walmart_product_urls(user_input, progress_bar)
                elif scraper_option == "Alibaba":
                    results = extract_alibaba_urls(user_input, progress_bar)
                elif scraper_option == "AliExpress":
                    results = extract_aliexpress_urls(user_input, progress_bar)
                
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
        st.success(f"{len(st.session_state.results_df)} URLs ready for processing")
        
        num_urls_to_process = st.slider("Number of URLs to process", 
                                       min_value=1, 
                                       max_value=min(10, len(st.session_state.results_df)), 
                                       value=1)
        
        if st.button("Extract Product Details"):
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
        st.subheader("Extracted Product Details")
        
        # Create dataframe directly from the product list
        if st.session_state.extracted_data:
            df = pd.DataFrame(st.session_state.extracted_data)
            
            # Display the table
            st.dataframe(df)
            
            # Download button
            csv = df.to_csv(index=False).encode('utf-8')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"products_{timestamp}.csv"
            st.download_button(
                label="Download Products (CSV)",
                data=csv,
                file_name=filename,
                mime="text/csv"
            )
    else:
        if st.session_state.scraping_completed:
            st.info("Click 'Extract Product Details' to process the URLs")
