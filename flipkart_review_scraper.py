import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import random
from urllib.parse import urlparse, parse_qs, urlencode
import streamlit as st
import os

# Global variable for wait time
DEFAULT_WAIT_TIME = (2, 4)  # (min, max) seconds

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

def get_review_page_content(url):
    """Get HTML content of a review page using requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Referer': 'https://www.flipkart.com/',
            'Cache-Control': 'max-age=0',
        }
        
        st.info("Fetching review content...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html_content = response.text
            
            # Check if we got a valid page with reviews
            if "product-reviews" in html_content and "Certified Buyer" in html_content:
                st.success("Successfully fetched reviews")
                return html_content, None
            else:
                # Check for various error conditions
                if "Be the first to Review this product" in html_content:
                    return None, "No reviews found for this product."
                    
                if "Page Not Found" in html_content:
                    return None, "Page not found. The URL may be invalid or the product might not exist."
                    
                if "Access Denied" in html_content:
                    return None, "Access denied. Flipkart might be blocking automated access."
                    
                return None, "Got response but couldn't find reviews on the page."
        else:
            return None, f"Request failed with status code {response.status_code}"
    except Exception as e:
        return None, f"Error accessing review page: {str(e)}"

def extract_reviews_from_page(html_content, debug_mode=False):
    """Extract review data from Flipkart HTML content"""
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    reviews_data = []
    
    # Look for reviews with class 'EKFha-' which contains actual review content
    review_elements = soup.find_all('div', {'class': 'EKFha-'})
    
    if review_elements:
        for review in review_elements:
            try:
                review_data = {}
                
                # The first character is often the rating (e.g., "5Amazing...")
                review_text = review.text.strip()
                
                # Extract rating from the beginning of the text
                rating = "Unknown"
                if review_text and review_text[0].isdigit():
                    rating = review_text[0]
                review_data['rating'] = rating
                
                # Process the text to extract different parts
                title_end = review_text.find('READ MORE') if 'READ MORE' in review_text else None
                
                if title_end:
                    # Extract title - it's between the rating and "READ MORE"
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
                else:
                    # If no "READ MORE", try to extract title and content differently
                    review_data['title'] = "No Title"
                    review_data['text'] = review_text[1:] if review_text and review_text[0].isdigit() else review_text
                
                # Check for certified buyer
                certified_pattern = re.search(r'certified buyer', review_text.lower())
                review_data['verified_purchase'] = True if certified_pattern else False
                
                # Extract reviewer name
                name_pattern = re.search(r'READ MORE([A-Za-z ]+)Certified', review_text)
                if name_pattern:
                    reviewer_name = name_pattern.group(1).strip()
                else:
                    name_pattern = re.search(r'([A-Z][a-z]+ +[A-Z][a-z]+)(?:Certified|\s*$)', review_text)
                    reviewer_name = name_pattern.group(1).strip() if name_pattern else "Unknown"
                
                # Clean up the reviewer name
                if "Certified Buyer" in reviewer_name:
                    reviewer_name = reviewer_name.replace("Certified Buyer", "").strip()
                
                review_data['reviewer_name'] = reviewer_name
                
                # Additional fields with default values
                review_data['date'] = "Unknown Date"
                review_data['helpful_votes'] = "0"
                
                # Add this review to our data
                reviews_data.append(review_data)
                
            except Exception as e:
                if debug_mode:
                    print(f"Error extracting review data: {str(e)}")
                continue
    else:
        # If no EKFha- reviews found, try the previous approach
        cPHDOP_elements = soup.find_all('div', {'class': 'cPHDOP col-12-12'})
        
        # Process each potential review container
        for review in cPHDOP_elements:
            if review.text and "Certified Buyer" in review.text:
                try:
                    # Create a basic review with what we can find
                    review_data = {
                        'reviewer_name': "Unknown",
                        'rating': "Unknown",
                        'title': "No Title",
                        'date': "Unknown Date",
                        'text': review.text[:200] + "..." if len(review.text) > 200 else review.text,
                        'helpful_votes': "0",
                        'verified_purchase': True
                    }
                    
                    # Try to find rating at the beginning
                    if review.text and review.text[0].isdigit():
                        review_data['rating'] = review.text[0]
                    
                    reviews_data.append(review_data)
                    
                except Exception:
                    continue
    
    return reviews_data

def get_next_page_url(current_url, current_page):
    """Generate the next page URL without requiring HTML parsing"""
    parsed_url = urlparse(current_url)
    query_params = parse_qs(parsed_url.query)
    
    # Calculate next page
    next_page = current_page + 1
    
    # Update the page parameter
    query_params['page'] = [str(next_page)]
    
    # Reconstruct the URL with the new page number
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

def scrape_flipkart_reviews(url, max_pages=None, start_page=1, progress_callback=None):
    """Scrape Flipkart reviews using only requests and BeautifulSoup"""
    all_reviews = []
    current_page = start_page
    current_url = url
    
    # Add page parameter if needed
    if start_page > 1 and "page=" not in current_url:
        parsed_url = urlparse(current_url)
        query_params = parse_qs(parsed_url.query)
        query_params['page'] = [str(start_page)]
        query_string = urlencode(query_params, doseq=True)
        base_url = current_url.split('?')[0]
        current_url = f"{base_url}?{query_string}"
    
    try:
        page_count = 0
        while page_count < (max_pages or float('inf')):
            if progress_callback:
                progress_callback(f"Scraping page {current_page}...")
                
            # Get the page content
            html_content, error = get_review_page_content(current_url)
            
            if error:
                if progress_callback:
                    progress_callback(f"Stopped: {error}")
                break
                
            # Extract reviews
            page_reviews = extract_reviews_from_page(html_content)
            
            if not page_reviews and current_page > start_page:
                if progress_callback:
                    progress_callback("No more reviews found. Ending scrape.")
                break
                
            all_reviews.extend(page_reviews)
            
            if progress_callback:
                progress_callback(f"Found {len(page_reviews)} reviews on page {current_page}. Total: {len(all_reviews)}")
                
            page_count += 1
            
            # Check if we've reached the max pages
            if max_pages and page_count >= max_pages:
                break
                
            # Generate next page URL
            current_page += 1
            current_url = get_next_page_url(current_url, current_page - 1)
            
            # Add a delay to avoid rate limiting
            time.sleep(random.uniform(1.5, 3))
            
    except Exception as e:
        if progress_callback:
            progress_callback(f"Error: {str(e)}")
    
    # Create DataFrame
    if all_reviews:
        return pd.DataFrame(all_reviews)
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
        debug_mode = st.checkbox("Enable debug mode", value=False)
    
    if st.button("Scrape Reviews"):
        if not review_url or "flipkart.com" not in review_url:
            st.error("Please enter a valid Flipkart product URL")
            return
            
        # Initialize progress elements
        progress_bar = st.progress(0)
        status_text = st.empty()
        st.info("The scraper will navigate through pages of reviews until it reaches the end or the specified limit.")
        
        # Function to update progress
        def update_progress(message):
            status_text.text(message)
            
        # Run the scraper
        try:
            update_progress("Starting review scraping...")
            
            # Special handling for the URL if needed
            if "product-reviews" not in review_url:
                review_url = convert_to_review_url(review_url)
                if review_url:
                    if debug_mode:
                        st.text(f"Converted to review URL: {review_url}")
                else:
                    st.error("Could not convert product URL to review URL. Please provide a direct review page URL.")
                    return
            
            # Use the simple HTTP-only method
            reviews_df = scrape_flipkart_reviews(
                review_url,
                max_pages=max_pages,
                start_page=start_page,
                progress_callback=update_progress
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
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            if debug_mode:
                import traceback
                st.code(traceback.format_exc())
        finally:
            progress_bar.empty()

if __name__ == "__main__":
    main() 
