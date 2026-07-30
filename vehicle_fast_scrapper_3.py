import os
import sys
import csv
import time
import random
import re
import argparse
import imaplib
import email
from datetime import datetime

from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Windows konsolunda UTF-8 reconfigure
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

# ==========================================
# ULTRA FAST SCRAPER CONFIGURATION
# ==========================================
MIN_DELAY_BETWEEN_PAGES = 1.0      # Sayfalar arası minimum bekleme (HIZLI)
MAX_DELAY_BETWEEN_PAGES = 1.8      # Sayfalar arası maksimum bekleme
BATCH_SIZE_BEFORE_PAUSE = 9999     # Yapay uzun molaları devredışı bırak
ENABLE_HUMAN_SCROLL = False        # Yavaş insansı scroll'u devredışı bırak (Maksimum hız)

ENABLE_SOUND_ALERT = True          # CAPTCHA / Engel çıktığında sesli bip uyarısı
DISABLE_IMAGES = True              # Resimleri kapat (İnternet ve sayfa yüklenme hızını 5x katlar)

# Oturum / Chrome Profil Ayarları
USE_SYSTEM_CHROME_PROFILE = False
CHROME_PROFILE_NAME = "Default"

# Proxy Ayarları
ENABLE_PROXY = False
PROXY_HOST = ""
PROXY_PORT = ""
PROXY_USER = ""
PROXY_PASS = ""

# E-Posta Doğrulama Ayarları (OTOMATİK ÇÖZÜM İÇİN DOLDURUN)
EMAIL_USER = "drkgln2005@gmail.com" 
EMAIL_PASS = "Dorukcan59"
IMAP_SERVER = "outlook.office365.com" # Üniversite e-postaları genelde Office365 kullanır

# 1.000 ve üzeri ilanı olan otomobil markaları
BRANDS = {
    "renault": "Renault",
    "volkswagen": "Volkswagen",
    "fiat": "Fiat",
    "bmw": "BMW",
    "mercedes-benz": "Mercedes-Benz",
    "ford": "Ford",
    "opel": "Opel",
    "peugeot": "Peugeot",
    "hyundai": "Hyundai",
    "toyota": "Toyota",
    "skoda": "Skoda",
    "tofas": "Tofaş",
    "seat": "Seat",
    "volvo": "Volvo",
    "nissan": "Nissan",
    "mini": "Mini",
    "mazda": "Mazda",
    "porsche": "Porsche",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_BASE_DIR = os.path.join(
    os.path.expanduser("~"), "Desktop", "Datas", "Vehicles", "Otomobil"
)


# Windows'ta undetected_chromedriver __del__ hatası yaması
def _safe_uc_del(self):
    try:
        self.quit()
    except Exception:
        pass


uc.Chrome.__del__ = _safe_uc_del


# ==========================================
# YARDIMCI FONKSİYONLAR VE E-POSTA DOĞRULAMA
# ==========================================
def get_sahibinden_code():
    """E-posta kutusuna bağlanıp Sahibinden'den gelen son kodu çeker."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('inbox')

        status, messages = mail.search(None, '(FROM "sahibinden.com")')
        mail_ids = messages[0].split()

        if not mail_ids:
            return None

        latest_email_id = mail_ids[-1]
        status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
        
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors='ignore')
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors='ignore')

                match = re.search(r'\b\d{6}\b', body)
                if match:
                    return match.group(0)
    except Exception as e:
        print(f"[E-Posta] Hata: {e}")
    finally:
        try:
            mail.logout()
        except:
            pass
    return None

def solve_verification(driver):
    """Ekranda doğrulama kodu kutucukları varsa bulur ve e-postadan kodu çekip girer."""
    try:
        # Doğrulama kutucuklarını bulmayı dene (maxlength=1 olan inputlar genellikle OTP kutularıdır)
        input_boxes = driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1']")
        
        if len(input_boxes) == 6:
            print("[Doğrulama] Doğrulama ekranı tespit edildi. Kod bekleniyor (10sn)...")
            time.sleep(10) # E-postanın gelmesi için kısa bir süre bekle
            
            code = get_sahibinden_code()
            if code:
                print(f"[Doğrulama] Kod bulundu: {code}. Kutuya giriliyor...")
                for i, char in enumerate(code):
                    input_boxes[i].send_keys(char)
                    time.sleep(0.15)
                print("[Doğrulama] Kod başarıyla girildi.")
                return True
            else:
                print("[Doğrulama] Kod e-postada bulunamadı.")
    except Exception as e:
        print(f"[Doğrulama] Çözüm sırasında hata oluştu: {e}")
    return False

def trigger_captcha_alert():
    if ENABLE_SOUND_ALERT:
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 300)
                time.sleep(0.1)
        except Exception:
            pass

def human_delay(min_sec=MIN_DELAY_BETWEEN_PAGES, max_sec=MAX_DELAY_BETWEEN_PAGES):
    time.sleep(random.uniform(min_sec, max_sec))

def get_installed_chrome_version():
    try:
        import winreg
        key_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
        ]
        for root_key, sub_key in key_paths:
            try:
                key = winreg.OpenKey(root_key, sub_key)
                version, _ = winreg.QueryValueEx(key, "version")
                return int(version.split(".")[0])
            except Exception:
                continue
    except Exception:
        pass
    return None

def create_soup(html_source):
    try:
        return BeautifulSoup(html_source, "lxml")
    except Exception:
        return BeautifulSoup(html_source, "html.parser")

def resolve_chrome_profile_directory(name):
    mapping = {
        "okul": "Profile 3",
        "iş": "Profile 4",
        "is": "Profile 4",
        "default": "Default",
    }
    return mapping.get(str(name).strip().lower(), name)

def _build_chrome_options(profile_suffix="Fresh"):
    options = uc.ChromeOptions()

    if USE_SYSTEM_CHROME_PROFILE:
        system_user_data = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data"
        )
        profile_dir = resolve_chrome_profile_directory(CHROME_PROFILE_NAME)
        options.add_argument(f"--user-data-dir={system_user_data}")
        options.add_argument(f"--profile-directory={profile_dir}")
    else:
        profile_path = os.path.join(SCRIPT_DIR, f"SeleniumProfile_{profile_suffix}")
        options.add_argument(f"--user-data-dir={profile_path}")

    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")

    if DISABLE_IMAGES:
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

    if ENABLE_PROXY and PROXY_HOST and PROXY_PORT:
        if PROXY_USER and PROXY_PASS:
            proxy_str = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
        else:
            proxy_str = f"http://{PROXY_HOST}:{PROXY_PORT}"
        options.add_argument(f"--proxy-server={proxy_str}")

    return options

def setup_driver(profile_suffix="Fresh"):
    chrome_version = get_installed_chrome_version()
    print(f"[Driver] Chrome surumu: {chrome_version or 'bilinmiyor'} | Profil: SeleniumProfile_{profile_suffix}")
    try:
        options = _build_chrome_options(profile_suffix)
        if chrome_version:
            return uc.Chrome(options=options, version_main=chrome_version)
        return uc.Chrome(options=options)
    except Exception as e:
        print(f"[Driver] Yeniden deneniyor ({e})...")
        options = _build_chrome_options(profile_suffix)
        if chrome_version:
            return uc.Chrome(options=options, version_main=chrome_version)
        return uc.Chrome(options=options)

def check_and_prompt_login(driver):
    print("[Oturum] Oturum durumu kontrol ediliyor...")
    try:
        driver.get("https://www.sahibinden.com/")
        human_delay(1.0, 1.8)
        soup = create_soup(driver.page_source)
        if (
            soup.select_one(".my-account-link")
            or soup.select_one("#user-my-account")
            or "Hesabım" in driver.page_source
        ):
            print("[Oturum] Sahibinden hesabınız açık! Oturum çerezleri kullanılıyor...")
        else:
            print("[Oturum] Henüz oturum açılmamış.")
            print("[İPUCU] Giriş yapmak isterseniz Chrome penceresinden giriş yapın.")
            print("Giriş yaptıktan sonra (veya misafir modunda devam etmek için) konsolda ENTER'a basın...")
            input("Devam etmek için ENTER'a basın...")
    except Exception:
        pass

def normalize_price(price_text):
    if not price_text or price_text == "N/A":
        return None
    cleaned = price_text.lower().replace("tl", "").replace("₺", "").strip()
    cleaned = re.sub(r"[^\d,\.]", "", cleaned)
    if not cleaned:
        return None
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        if "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) > 1 and all(p.isdigit() for p in parts):
                if all(len(p) == 3 for p in parts[1:]):
                    cleaned = "".join(parts)
    try:
        return float(cleaned)
    except ValueError:
        return None


# ==========================================
# LİSTE SAYFASI PARSE VE ENGEL YÖNETİMİ
# ==========================================
def extract_headers(soup):
    headers = []
    for idx, th in enumerate(soup.select("#searchResultsTable thead th")):
        text = re.sub(r"\s+", " ", th.get_text(strip=True))
        if not text:
            classes = th.get("class", [])
            if any("gallery" in c.lower() for c in classes) or idx == 0:
                text = "Image"
            else:
                text = f"Column_{idx}"
        headers.append(text)
    return headers

def parse_listing_row(row, headers, brand_folder):
    cells = row.select("td")
    if not cells:
        return None

    row_data = {"Kaynak_Marka": brand_folder}

    price_elem = row.select_one(".searchResultsPriceValue")
    price_raw = price_elem.get_text(strip=True) if price_elem else "N/A"
    row_data["Fiyat_Raw"] = price_raw
    row_data["Normalized_Price"] = normalize_price(price_raw)

    location_elem = row.select_one(".searchResultsLocationValue")
    district = location_elem.get_text(" ", strip=True) if location_elem else "N/A"
    row_data["Parsed_Location"] = re.sub(r"\s+", " ", district)

    date_elem = row.select_one(".searchResultsDateValue")
    if date_elem:
        row_data["Ilan_Tarihi"] = re.sub(r"\s+", " ", date_elem.get_text(" ", strip=True))

    title_link = row.select_one("a.searchResultsTitleValue") or row.select_one("a[href*='/ilan/']")
    if title_link:
        row_data["Title"] = re.sub(r"\s+", " ", title_link.get_text(strip=True))
        href = title_link.get("href", "")
        row_data["URL"] = ("https://www.sahibinden.com" + href) if href else "N/A"
    else:
        row_data["Title"] = "N/A"
        row_data["URL"] = "N/A"

    listing_id = row.get("data-id") or ""
    if not listing_id and row_data["URL"] != "N/A":
        match = re.search(r"-(\d+)/detay", row_data["URL"]) or re.search(r"(\d{6,})", row_data["URL"])
        listing_id = match.group(1) if match else ""
    row_data["Ilan_No"] = listing_id

    for idx, cell in enumerate(cells):
        col_name = headers[idx] if idx < len(headers) else f"Column_{idx}"
        if col_name == "Image":
            continue
        row_data[col_name] = re.sub(r"\s+", " ", cell.get_text(strip=True))

    return row_data

def check_is_login_wall(driver):
    current_url = driver.current_url.lower()
    page_source = driver.page_source.lower()
    if "secure.sahibinden.com/giris" in current_url or "giriş yap" in page_source:
        return True
    return False

def handle_blocked_page(driver, brand_folder):
    trigger_captcha_alert()
    print("\n" + "=" * 50)
    
    # 1. Otomatik Doğrulama Kontrolü
    if solve_verification(driver):
        print("Otomatik doğrulama tamamlandı, sayfa güncelleniyor...")
        human_delay(2.0, 3.0)
        
        soup = create_soup(driver.page_source)
        listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")
        if listings:
            return soup, listings
    
    # 2. Doğrulama başarısızsa veya farklı bir engelse manuel müdahale
    if check_is_login_wall(driver):
        print("UYARI: Sahibinden Giriş Yap Duvarına Takıldı!")
    else:
        print("ACTION REQUIRED: No listings found (CAPTCHA/Block).")
    print(f"Current URL: {driver.current_url}")
    print("=" * 50)
    input("İlanları görünce veya işlemi tamamlayınca ENTER'a basın...")

    for attempt in range(1, 11):
        human_delay(1.0, 2.0)
        soup = create_soup(driver.page_source)
        listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")
        if listings:
            return soup, listings
        print(f"Still no listings (check {attempt}/10). Refreshing page...")
        driver.refresh()

    print(f"Still no listings for {brand_folder}. Skipping.")
    return None, []

def scrape_brand(driver, brand_url_name, brand_folder, max_to_scrape=999):
    url = f"https://www.sahibinden.com/{brand_url_name}?pagingSize=50"
    print(f"\nLoading {url}...")
    driver.get(url)

    all_scraped_data = []
    seen_keys = set()
    page_num = 1

    while len(all_scraped_data) < max_to_scrape:
        human_delay(0.8, 1.2)

        soup = create_soup(driver.page_source)
        listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")

        if not listings:
            soup, listings = handle_blocked_page(driver, brand_folder)
            if not listings:
                break

        print(f"[{brand_folder}] Sayfa {page_num} -> {len(all_scraped_data)}/{max_to_scrape} kayit (Hızlı Mod)")

        headers = extract_headers(soup)

        for row in listings:
            if len(all_scraped_data) >= max_to_scrape:
                break
            try:
                row_data = parse_listing_row(row, headers, brand_folder)
                if not row_data:
                    continue

                key = row_data.get("Ilan_No") or row_data.get("URL")
                if key and key != "N/A":
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                all_scraped_data.append(row_data)
            except Exception as exc:
                print(f"Row parse error: {exc}")
                continue

        if len(all_scraped_data) >= max_to_scrape:
            break

        next_button = soup.find("a", title="Sonraki")
        if next_button and next_button.get("href"):
            next_url = "https://www.sahibinden.com" + next_button["href"]
            driver.get(next_url)
            page_num += 1
            human_delay(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES)
        else:
            print(f"Finished all list pages for {brand_folder}.")
            break

    if all_scraped_data:
        save_to_csv(brand_folder, all_scraped_data)
    else:
        print(f"No listings found for {brand_folder}, skipping save.")

def save_to_csv(brand_folder, data):
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(DATA_BASE_DIR, brand_folder)
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, f"{today_str}.csv")

    preferred_order = [
        "Ilan_No", "Kaynak_Marka", "Title", "URL",
        "Marka", "Seri", "Model", "Yıl", "KM", "Renk",
        "Fiyat_Raw", "Normalized_Price",
        "Ilan_Tarihi", "Parsed_Location",
    ]

    all_keys = set()
    for row in data:
        all_keys.update(row.keys())

    fieldnames = []
    for key in preferred_order:
        if key in all_keys:
            fieldnames.append(key)
            all_keys.discard(key)
    fieldnames.extend(sorted(all_keys))

    if "Image" in fieldnames:
        fieldnames.remove("Image")

    with open(file_path, mode="w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)

    print(f"Saved {len(data)} records to {file_path}")

def main():
    parser = argparse.ArgumentParser(description="Ultra Fast Vehicle Scraper v3")
    parser.add_argument("--term", type=str, default="Fresh", help="Terminal profil takısı (ör: 1, 2, 3)")
    parser.add_argument("--brands", nargs="+", help="Sadece belirli markaları çek (ör: renault volkswagen fiat)")
    args = parser.parse_args()

    driver = setup_driver(args.term)
    check_and_prompt_login(driver)
    LIMIT_PER_BRAND = 999

    target_brands = BRANDS
    if args.brands:
        selected_brands = {}
        for b in args.brands:
            b_clean = b.lower().strip()
            if b_clean in BRANDS:
                selected_brands[b_clean] = BRANDS[b_clean]
        if selected_brands:
            target_brands = selected_brands

    try:
        total_brands = len(target_brands)
        for i, (brand_url_name, brand_folder) in enumerate(target_brands.items(), 1):
            print(f"\n{'=' * 70}")
            print(f"[{i}/{total_brands}] [HIZLI SCRAPE v3] Scraping {brand_folder} (Target Limit: {LIMIT_PER_BRAND})...")
            print(f"{'=' * 70}")
            scrape_brand(driver, brand_url_name, brand_folder, LIMIT_PER_BRAND)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("\nAll done!")


if __name__ == "__main__":
    main()