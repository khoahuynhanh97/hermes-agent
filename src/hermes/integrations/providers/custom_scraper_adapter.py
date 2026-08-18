import os

def run_custom_scraper(product_name, output_dir, log_callback=None):
    """
    Template for developers to add their own custom scrapers.
    You can import selenium, playright, beautifulsoup4, or any other library here.
    
    Args:
        product_name (str): Product search query.
        output_dir (str): Directory where downloaded files should be saved.
        log_callback (callable): Function to log messages to the GUI console.
        
    Returns:
        list: List of absolute file paths downloaded successfully.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    log("[*] Bắt đầu chạy Custom Scraper Adapter...")
    log("[*] Lưu ý: Đây là file mẫu (Boilerplate). Nhà phát triển có thể chèn logic cào bằng Selenium/Playwright/Scrapy tại đây.")
    log("[-] Hiện tại chưa có website đích nào được cấu hình trong Custom Scraper. Hoàn thành!")
    
    # Example of how you would return downloads:
    # downloaded = []
    # return downloaded
    return []
