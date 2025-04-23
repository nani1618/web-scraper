import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import random
from urllib.parse import urlparse, parse_qs
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Global variable for wait time
DEFAULT_WAIT_TIME = (2, 4)  # (min, max) seconds

def setup_driver(custom_user_agent=None):
    """Configure and return a headless Chrome webdriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Default user agents to rotate if no custom one is provided
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    ]
    
    # Use custom user agent if provided
    if custom_user_agent:
        chrome_options.add_argument(f"user-agent={custom_user_agent}")
    else:
        chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")
        
    return webdriver.Chrome(options=chrome_options)

def extract_product_info_from_url(url):
    """Extract the product ID and other info from a Flipkart review URL"""
    product_info = {}
    
    # Extract product ID (pid) from URL
    pid_match = re.search(r'pid=([A-Z0-9]+)', url)
    if pid_match:
        product_info['pid'] = pid_match.group(1)
    
    # Extract listing ID (lid) from URL
    lid_match = re.search(r'lid=([A-Z0-9]+)', url)
    if lid_match:
        product_info['lid'] = lid_match.group(1)
    
    # Extract product name from URL
    name_match = re.search(r'/([^/]+)/product-reviews/', url)
    if name_match:
        product_info['name'] = name_match.group(1).replace('-', ' ')
    
    # Extract item ID from URL
    item_match = re.search(r'itm([a-z0-9]+)', url)
    if item_match:
        product_info['item_id'] = 'itm' + item_match.group(1)
    
    return product_info

def get_review_page_content(url, driver=None, wait_time=None):
    """Get HTML content of a review page using Selenium to bypass anti-bot measures"""
    try:
        # If no driver is provided, create a new one
        should_close_driver = driver is None
        if driver is None:
            driver = setup_driver()
        
        # Log the URL being accessed for debugging
        print(f"Accessing URL: {url}")
        
        driver.get(url)
        
        # Wait for page to load
        min_wait, max_wait = wait_time if wait_time else DEFAULT_WAIT_TIME
        time.sleep(random.uniform(min_wait, max_wait))  # Random wait time to appear more human-like
        
        # Check for various error conditions
        page_source = driver.page_source
        
        # Check for access denied or bot detection
        if "Access Denied" in page_source or "automated access" in page_source:
            return None, "Access denied. Flipkart is blocking automated access."
        
        # Check for no reviews
        if "Be the first to Review this product" in page_source:
            return None, "No reviews found for this product."
        
        # Check if page not found
        if "Page Not Found" in page_source or "The page you are looking for does not exist" in page_source:
            return None, "Page not found. The URL may be invalid or the product might not exist."
        
        # Close driver if we created it in this function
        if should_close_driver:
            driver.quit()
            
        return page_source, None
    except Exception as e:
        if driver and should_close_driver:
            driver.quit()
        return None, f"Error accessing review page: {str(e)}"

def extract_reviews_from_page(html_content, debug_mode=False):
    """Extract review data from Flipkart HTML content"""
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    reviews_data = []
    
    if debug_mode:
        print("DEBUG: HTML Structure Analysis")
        print("="*80)
    
    # Look for reviews with class 'EKFha-' which contains actual review content
    review_elements = soup.find_all('div', {'class': 'EKFha-'})
    
    if debug_mode:
        print(f"Found {len(review_elements)} review elements with class 'EKFha-'")
    
    if review_elements:
        for i, review in enumerate(review_elements):
            try:
                if debug_mode:
                    print(f"\nProcessing review {i+1}:")
                
                review_data = {}
                
                # The first character is often the rating (e.g., "5Amazing...")
                review_text = review.text.strip()
                
                if debug_mode:
                    print(f"Review text: {review_text[:50]}...")
                
                # Extract rating from the beginning of the text
                rating = "Unknown"
                if review_text and review_text[0].isdigit():
                    rating = review_text[0]
                    if debug_mode:
                        print(f"Rating extracted: {rating}")
                review_data['rating'] = rating
                
                # Process the text to extract different parts
                # After the rating, the next few characters are usually the review title
                title_end = review_text.find('READ MORE') if 'READ MORE' in review_text else None
                
                if title_end:
                    # Extract title - it's between the rating and "READ MORE"
                    # Skip the digit and find the end of the title words (typically "Wonderful", "Amazing", etc.)
                    title_start = 1  # Skip the rating digit
                    title_words = ["Wonderful", "Amazing", "Classy", "Perfect", "Fabulous", "Excellent", 
                                   "Very Good", "Good", "Pretty good", "Mind-blowing", "Worth the money", 
                                   "Terrific", "Just average", "Fair", "Not recommended"]
                    
                    title = "No Title"
                    for word in title_words:
                        if review_text[title_start:].startswith(word):
                            title = word
                            title_start += len(word)
                            break
                    
                    # Extract main review text after the title
                    if title != "No Title":
                        review_content = review_text[title_start:title_end].strip()
                    else:
                        review_content = review_text[1:title_end].strip()
                    
                    review_data['title'] = title
                    review_data['text'] = review_content
                    
                    if debug_mode and title != "No Title":
                        print(f"Found title: {title}")
                        print(f"Review content: {review_content[:50]}...")
                else:
                    # If no "READ MORE", try to extract title and content differently
                    lines = review_text.split('\n')
                    if len(lines) > 1:
                        if lines[0] and lines[0][0].isdigit():
                            # First character is rating, rest of first line might be title
                            first_line = lines[0][1:].strip()
                            
                            # Check if first line contains common title words
                            title_words = ["Wonderful", "Amazing", "Classy", "Perfect", "Fabulous", "Excellent", 
                                           "Very Good", "Good", "Pretty good", "Mind-blowing", "Worth the money", 
                                           "Terrific", "Just average", "Fair", "Not recommended"]
                            
                            title = "No Title"
                            for word in title_words:
                                if word in first_line:
                                    title = word
                                    first_line = first_line.replace(word, "", 1).strip()
                                    break
                            
                            review_data['title'] = title
                            
                            # If there's remaining text in first line, it's part of review text
                            if first_line:
                                review_data['text'] = first_line
                            elif len(lines) > 1:
                                review_data['text'] = ' '.join(lines[1:])
                            else:
                                review_data['text'] = "No review text"
                        else:
                            review_data['title'] = "No Title"
                            review_data['text'] = review_text
                    else:
                        review_data['title'] = "No Title"
                        review_data['text'] = review_text[1:] if review_text and review_text[0].isdigit() else review_text
                
                # Check for certified buyer
                certified_pattern = re.search(r'certified buyer', review_text.lower())
                review_data['verified_purchase'] = True if certified_pattern else False
                if debug_mode and review_data['verified_purchase']:
                    print("Found certified buyer badge")
                
                # Extract reviewer name - typically after "READ MORE" or at the end
                name_pattern = re.search(r'READ MORE([A-Za-z ]+)Certified', review_text)
                if name_pattern:
                    reviewer_name = name_pattern.group(1).strip()
                else:
                    # Try to find the name another way - look for common patterns in reviewer names
                    name_pattern = re.search(r'([A-Z][a-z]+ +[A-Z][a-z]+)(?:Certified|\s*$)', review_text)
                    if name_pattern:
                        reviewer_name = name_pattern.group(1).strip()
                    else:
                        reviewer_name = "Unknown"
                
                # Clean up the reviewer name to remove "Certified Buyer" text
                if "Certified Buyer" in reviewer_name:
                    reviewer_name = reviewer_name.replace("Certified Buyer", "").strip()
                
                review_data['reviewer_name'] = reviewer_name
                if debug_mode and reviewer_name != "Unknown":
                    print(f"Extracted reviewer name: {reviewer_name}")
                
                # We don't have date information in this structure
                review_data['date'] = "Unknown Date"
                
                # No information about helpful votes either
                review_data['helpful_votes'] = "0"
                
                # Add this review to our data
                reviews_data.append(review_data)
                
            except Exception as e:
                if debug_mode:
                    print(f"Error extracting review data: {str(e)}")
                continue
    else:
        # If no EKFha- reviews found, try the previous approach
        if debug_mode:
            print("No 'EKFha-' review elements found. Trying alternative methods.")
        
        # Find all possible review containers
        cPHDOP_elements = soup.find_all('div', {'class': 'cPHDOP col-12-12'})
        if debug_mode:
            print(f"Found {len(cPHDOP_elements)} cPHDOP elements to try")
        
        # Process each potential review container
        for i, review in enumerate(cPHDOP_elements):
            if review.text and "Certified Buyer" in review.text:
                try:
                    if debug_mode:
                        print(f"\nAttempting to extract from container {i+1}:")
                    
                    # Create a basic review with what we can find
                    review_data = {
                        'reviewer_name': "Unknown",
                        'rating': "Unknown",
                        'title': "No Title",
                        'date': "Unknown Date",
                        'text': review.text[:200] + "..." if len(review.text) > 200 else review.text,  # Take the whole text as review
                        'helpful_votes': "0",
                        'verified_purchase': True if "Certified Buyer" in review.text else False
                    }
                    
                    # Try to find rating at the beginning
                    if review.text and review.text[0].isdigit():
                        review_data['rating'] = review.text[0]
                        if debug_mode:
                            print(f"Found rating: {review_data['rating']}")
                    
                    reviews_data.append(review_data)
                    if debug_mode:
                        print(f"Added review with text beginning: {review_data['text'][:50]}...")
                    
                except Exception as e:
                    if debug_mode:
                        print(f"Error extracting review: {str(e)}")
    
    return reviews_data

def check_has_next_page(html_content):
    """Check if there is a next page of reviews on Flipkart"""
    if not html_content:
        return False
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Debug print what the page navigation looks like
    pagination_elements = soup.find_all('div', string=lambda t: t and 'Page' in t)
    if pagination_elements:
        print(f"Found pagination text: {pagination_elements[0].text}")
    
    # Look for the pagination container with page number info
    pagination_text = soup.find('div', string=lambda t: t and 'Page' in t and 'of' in t)
    if pagination_text:
        # Extract current page and total pages
        page_info = pagination_text.text.strip()
        match = re.search(r'Page (\d+) of (\d+)', page_info)
        if match:
            current_page = int(match.group(1))
            total_pages = int(match.group(2))
            print(f"Current page: {current_page}, Total pages: {total_pages}")
            return current_page < total_pages
    
    # Method 1: Check for next page button
    next_button = soup.find('a', {'class': '_1LKTO3'})
    if next_button and "Next" in next_button.get_text():
        return True
    
    # Method 2: Look for the "Next" text link
    next_link = soup.find('span', string=lambda t: t and 'Next' in t)
    if next_link:
        return True
    
    # Method 3: Look for any navigation element with "Next" text
    next_nav = soup.find_all(string=lambda t: t and 'Next' in t)
    if next_nav:
        return True
    
    # Method 4: Check pagination container
    pagination = soup.find('div', {'class': '_2MImiq'})
    if pagination:
        # Find all page buttons
        page_buttons = pagination.find_all('span')
        # If there are page buttons, check if any is selected (current page)
        for button in page_buttons:
            if '_2Kfbh8' in button.get('class', []):  # This class indicates current page
                # If current page is not the last button, there's a next page
                if button != page_buttons[-1]:
                    return True
    
    # Method 5: Check for any nav with page numbers
    nav_container = soup.find('nav')
    if nav_container:
        page_links = nav_container.find_all('a')
        if page_links and len(page_links) > 1:
            # If we have multiple page links, there's likely a next page
            return True
    
    # Method 6: Look for any element containing pagination info
    page_info = soup.find(string=lambda t: t and re.search(r'Page\s+\d+\s+of\s+\d+', t) if t else False)
    if page_info:
        match = re.search(r'Page\s+(\d+)\s+of\s+(\d+)', page_info)
        if match and int(match.group(1)) < int(match.group(2)):
            return True
    
    return False

def get_next_page_url(current_url, html_content, current_page):
    """Generate the next page URL for Flipkart reviews"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Method 1: Try to extract from pagination links
    next_button = soup.find('a', {'class': '_1LKTO3'})
    if next_button and next_button.get('href'):
        next_href = next_button.get('href')
        if next_href.startswith('/'):
            # Relative URL, need to make absolute
            parsed_url = urlparse(current_url)
            return f"{parsed_url.scheme}://{parsed_url.netloc}{next_href}"
        else:
            return next_href
    
    # Method 2: Look for "Next" text in any link
    nav_links = soup.find_all('a')
    for link in nav_links:
        if link.text and 'Next' in link.text:
            next_href = link.get('href')
            if next_href:
                if next_href.startswith('/'):
                    # Relative URL, need to make absolute
                    parsed_url = urlparse(current_url)
                    return f"{parsed_url.scheme}://{parsed_url.netloc}{next_href}"
                else:
                    return next_href
    
    # Method 3: Modify the page parameter in the URL
    parsed_url = urlparse(current_url)
    query_params = parse_qs(parsed_url.query)
    
    # Calculate next page
    next_page = current_page + 1
    
    # Find total pages from page info text
    total_pages = None
    page_info = soup.find(string=lambda t: t and 'Page' in t and 'of' in t if t else False)
    if page_info:
        match = re.search(r'Page\s+\d+\s+of\s+(\d+)', page_info)
        if match:
            total_pages = int(match.group(1))
    
    # Don't go beyond total pages if we know them
    if total_pages and next_page > total_pages:
        return None
    
    # Update the page parameter
    query_params['page'] = [str(next_page)]
    
    # Reconstruct the URL with the new page number
    from urllib.parse import urlencode
    query_string = urlencode(query_params, doseq=True)
    
    # Get the base URL without query parameters
    base_url = current_url.split('?')[0]
    
    # Combine base URL with new query parameters
    next_url = f"{base_url}?{query_string}"
    
    print(f"Generated next URL: {next_url}")
    return next_url

def convert_to_review_url(product_url):
    """Convert a Flipkart product URL to a review URL"""
    # Check if it's already a review URL
    if "product-reviews" in product_url:
        return product_url
    
    # Extract product portion from URL
    product_path_match = re.search(r'flipkart\.com/([^/]+)/p/', product_url)
    if not product_path_match:
        return None
    
    product_path = product_path_match.group(1)
    
    # Extract product ID and listing ID
    pid_match = re.search(r'pid=([A-Z0-9]+)', product_url)
    lid_match = re.search(r'lid=([A-Z0-9]+)', product_url)
    
    if not pid_match:
        return None
    
    pid = pid_match.group(1)
    lid = lid_match.group(1) if lid_match else ""
    
    # Extract item ID
    item_match = re.search(r'(itm[a-z0-9]+)', product_url)
    item_id = item_match.group(1) if item_match else ""
    
    # Construct review URL
    parsed_url = urlparse(product_url)
    base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    if lid and item_id:
        review_url = f"{base_domain}/{product_path}/product-reviews/{item_id}?pid={pid}&lid={lid}&marketplace=FLIPKART"
    else:
        review_url = f"{base_domain}/{product_path}/product-reviews/itm?pid={pid}&marketplace=FLIPKART"
    
    return review_url

def scrape_flipkart_reviews(start_url, max_pages=None, start_page=1, wait_time=None, progress_callback=None, custom_user_agent=None, debug_mode=False):
    """
    Scrape Flipkart product reviews across multiple pages
    
    Args:
        start_url: Starting URL for review scraping
        max_pages: Maximum number of pages to scrape (None = no limit)
        start_page: Page number to start scraping from
        wait_time: Tuple of (min, max) seconds to wait between pages
        progress_callback: Function to call with progress updates
        custom_user_agent: Custom user agent string to use
        debug_mode: Enable debug output
        
    Returns:
        DataFrame with all scraped reviews
    """
    all_reviews = []
    
    # Ensure URL is a valid Flipkart URL
    if "flipkart.com" not in start_url:
        if progress_callback:
            progress_callback("Error: Not a Flipkart URL")
        return pd.DataFrame()
    
    # If not a review URL, try to convert it to one
    if "product-reviews" not in start_url:
        review_url = convert_to_review_url(start_url)
        if review_url:
            start_url = review_url
            if progress_callback:
                progress_callback(f"Converting to review URL: {start_url}")
        else:
            if progress_callback:
                progress_callback("Error: Could not convert product URL to review URL")
            return pd.DataFrame()
    
    # Adjust URL to start from specified page
    parsed_url = urlparse(start_url)
    query_params = parse_qs(parsed_url.query)
    
    # Set starting page number
    if start_page > 1:
        query_params['page'] = [str(start_page)]
        from urllib.parse import urlencode
        query_string = urlencode(query_params, doseq=True)
        base_url = start_url.split('?')[0]
        start_url = f"{base_url}?{query_string}"
    
    current_url = start_url
    current_page = start_page
    
    # Set up the driver with specified user agent if available
    driver = setup_driver(custom_user_agent)
    
    try:
        while True:
            # Update progress
            if progress_callback:
                progress_callback(f"Scraping page {current_page}...")
            
            # Get page content
            html_content, error = get_review_page_content(current_url, driver, wait_time)
            
            if error:
                # Report the error
                if progress_callback:
                    progress_callback(f"Stopped: {error}")
                break
            
            # Extract reviews from the page
            if progress_callback:
                progress_callback("Analyzing page structure...")
            
            page_reviews = extract_reviews_from_page(html_content, debug_mode=debug_mode)
            all_reviews.extend(page_reviews)
            
            if progress_callback:
                progress_callback(f"Found {len(page_reviews)} reviews on page {current_page}. Total: {len(all_reviews)}")
            
            # If no reviews found on the current page, we might have reached the end
            if len(page_reviews) == 0 and current_page > start_page:
                if progress_callback:
                    progress_callback("No reviews found on this page. Possibly reached the end.")
                break
            
            # Check if we should stop based on max_pages
            if max_pages and (current_page - start_page + 1) >= max_pages:
                if progress_callback:
                    progress_callback(f"Reached maximum number of pages ({max_pages}).")
                break
                
            # Check if there's a next page
            has_next = check_has_next_page(html_content)
            if not has_next:
                if progress_callback:
                    progress_callback("Reached the last page of reviews.")
                break
                
            # Get the next page URL
            current_url = get_next_page_url(current_url, html_content, current_page)
            current_page += 1
            
            # Add a delay to avoid being blocked
            min_wait, max_wait = wait_time if wait_time else DEFAULT_WAIT_TIME
            time.sleep(random.uniform(min_wait, max_wait))
    finally:
        # Always close the driver
        if driver:
            driver.quit()
    
    # Convert to DataFrame
    if all_reviews:
        # Create the DataFrame
        reviews_df = pd.DataFrame(all_reviews)
        return reviews_df
    else:
        return pd.DataFrame()

def main():
    st.title("Flipkart Product Review Scraper")
    
    review_url = st.text_input("Enter Flipkart product URL (product page or review page):", 
                              placeholder="https://www.flipkart.com/product-name/product-reviews/itm123?pid=ABC123")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_page = st.number_input("Start from page:", min_value=1, value=1)
    
    with col2:
        max_pages = st.number_input("Number of pages to scrape (0 = no limit):", 
                                   min_value=0, max_value=100, value=3)
        max_pages = None if max_pages == 0 else max_pages
    
    with col3:
        min_delay = st.number_input("Delay between pages (seconds):", 
                                 min_value=1, max_value=10, value=3)
    
    # Advanced options
    with st.expander("Advanced Options"):
        extract_verified_only = st.checkbox("Only include Certified Buyer reviews", value=False)
        
        default_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15"
        custom_user_agent = st.text_input("Custom User Agent:", 
                                        value=default_agent)
        
        debug_mode = st.checkbox("Enable debug mode", value=False)
        
        st.info("Flipkart typically has less aggressive anti-scraping measures than Amazon.")
    
    if st.button("Scrape Reviews"):
        if not review_url or "flipkart.com" not in review_url:
            st.error("Please enter a valid Flipkart product URL")
            return
            
        # Initialize progress elements
        progress_bar = st.progress(0)
        status_text = st.empty()
        debug_info = st.empty() if debug_mode else None
        st.info("The scraper will navigate through pages of reviews until it reaches the end or the specified limit.")
        
        # Function to update progress
        def update_progress(message):
            status_text.text(message)
        
        # Function to update debug info
        def update_debug(message):
            if debug_mode and debug_info:
                with debug_info.container():
                    st.text(message)
            
        # Run the scraper
        try:
            # Configure wait time
            wait_time = (min_delay, min_delay + 2)
            
            update_progress("Starting review scraping...")
            
            # Special handling for the URL if needed
            if "product-reviews" not in review_url:
                review_url = convert_to_review_url(review_url)
                if review_url:
                    update_debug(f"Converted to review URL: {review_url}")
                else:
                    st.error("Could not convert product URL to review URL. Please provide a direct review page URL.")
                    return
            
            # Adjust scraping based on options
            reviews_df = scrape_flipkart_reviews(
                review_url, 
                max_pages=max_pages,
                start_page=start_page,
                wait_time=wait_time,
                progress_callback=update_progress,
                custom_user_agent=custom_user_agent,
                debug_mode=debug_mode
            )
            
            # Filter verified purchases if requested
            if extract_verified_only and not reviews_df.empty and 'verified_purchase' in reviews_df.columns:
                verified_df = reviews_df[reviews_df['verified_purchase'] == True]
                if len(verified_df) > 0:
                    reviews_df = verified_df
                    update_progress(f"Filtered to {len(reviews_df)} certified buyer reviews")
                else:
                    update_progress("No certified buyer reviews found, showing all reviews")
            
            if reviews_df.empty:
                st.warning("No reviews were found or could be scraped.")
                
                # Provide troubleshooting advice
                with st.expander("Troubleshooting Tips"):
                    st.markdown("""
                    **Why might the scraper fail to find reviews?**
                    
                    1. **URL format issues:** Make sure you're using a valid Flipkart product or review URL.
                       Example: `https://www.flipkart.com/product-name/product-reviews/itm123?pid=ABC123`
                       
                    2. **No reviews exist:** The product might not have any reviews yet
                    
                    3. **Changed HTML structure:** Flipkart may have updated their page structure
                    
                    4. **Access blocked:** Try increasing the delay between requests
                    """)
                
                return
                
            # Display the results
            st.success(f"Successfully scraped {len(reviews_df)} reviews!")
            st.dataframe(reviews_df)
            
            # Provide download button
            csv = reviews_df.to_csv(index=False).encode('utf-8')
            
            # Extract product info for filename
            product_info = extract_product_info_from_url(review_url)
            product_id = product_info.get('pid', 'product')
            
            st.download_button(
                label="Download Reviews (CSV)",
                data=csv,
                file_name=f"flipkart_reviews_{product_id}.csv",
                mime="text/csv"
            )
            
            # Show some statistics
            if len(reviews_df) > 0:
                st.subheader("Review Statistics")
                
                # Rating distribution
                if 'rating' in reviews_df.columns:
                    try:
                        # Convert rating to numeric
                        reviews_df['rating_numeric'] = pd.to_numeric(reviews_df['rating'], errors='coerce')
                        
                        st.write("Rating Distribution:")
                        rating_counts = reviews_df['rating_numeric'].value_counts().sort_index()
                        st.bar_chart(rating_counts)
                        
                        # Average rating
                        avg_rating = reviews_df['rating_numeric'].mean()
                        st.metric("Average Rating", f"{avg_rating:.1f}/5.0")
                    except Exception as e:
                        st.warning(f"Could not generate rating statistics: {str(e)}")
                
                # Most helpful reviews
                if 'helpful_votes' in reviews_df.columns:
                    try:
                        reviews_df['helpful_votes_numeric'] = pd.to_numeric(reviews_df['helpful_votes'], errors='coerce')
                        st.write("Most Helpful Reviews:")
                        helpful_reviews = reviews_df.sort_values('helpful_votes_numeric', ascending=False).head(5)
                        for _, review in helpful_reviews.iterrows():
                            st.markdown(f"**{review['title']}** - {review['rating']}/5 stars")
                            st.markdown(f"_{review['reviewer_name']} on {review['date']}_")
                            st.markdown(f"{review['text'][:300]}..." if len(review['text']) > 300 else review['text'])
                            st.markdown(f"Helpful votes: {review['helpful_votes']}")
                            st.markdown("---")
                    except Exception as e:
                        st.warning(f"Could not display helpful reviews: {str(e)}")
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            import traceback
            if debug_mode:
                st.code(traceback.format_exc())
        finally:
            progress_bar.empty()

if __name__ == "__main__":
    main() 