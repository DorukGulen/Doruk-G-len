import os
import sys
import io
import csv
import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
import re

# Windows konsolunda (cp1254/cp1252) Unicode yazdırma hatasını engellemek için UTF-8 reconfigure
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

# ==========================================
# SCRAPER & ANTI-BOT CONFIGURATION
# ==========================================
# Adım 1: İnsansı Davranış & Gecikmeler
MIN_DELAY_BETWEEN_PAGES = 3.0      # Sayfalar arası minimum bekleme (3.0 saniye)
MAX_DELAY_BETWEEN_PAGES = 6.0      # Sayfalar arası maksimum bekleme (6.0 saniye)
BATCH_SIZE_BEFORE_PAUSE = 5        # Kaç ilanda bir uzun mola verileceği
BATCH_PAUSE_DURATION_MIN = 15.0    # Uzun mola minimum süresi (saniye)
BATCH_PAUSE_DURATION_MAX = 30.0    # Uzun mola maksimum süresi (saniye)
ENABLE_HUMAN_SCROLL = True         # Detay sayfasında otomatik insansı scroll yapılması

# Adım 3: CAPTCHA Sesli Uyarı & Çözücü Ayarları
ENABLE_SOUND_ALERT = True          # CAPTCHA çıktığında sesli bip uyarısı çal
CAPTCHA_SOLVER_API_KEY = ""        # 2Captcha / CapMonster API Key (Opsiyonel)

# Oturum / Chrome Profil Ayarları
USE_SYSTEM_CHROME_PROFILE = False       # Kendi Chrome profillerinizden birini kullanmak için True yapın
CHROME_PROFILE_NAME = "Default"         # Açmak istediğiniz profil adı: "Default", "Profile 3", "Profile 4"  

# Proxy Ayarları
ENABLE_PROXY = False               # Proxy satın aldıysanız True yapın
PROXY_HOST = ""                    # Örnek: "123.45.67.89" veya "zproxy.lum-superproxy.io"
PROXY_PORT = ""                    # Örnek: "8080" veya "22225"
PROXY_USER = ""                    # Kullanıcı adı (varsa)
PROXY_PASS = ""                    # Şifre (varsa)



# Windows'ta undetected_chromedriver __del__ aşamasındaki WinError 6 hatasını engelleme yaması
def _safe_uc_del(self):
    try:
        self.quit()
    except Exception:
        pass

uc.Chrome.__del__ = _safe_uc_del


def trigger_captcha_alert():
    """CAPTCHA tespit edildiğinde sesli uyarı verir (Windows)."""
    if ENABLE_SOUND_ALERT:
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 300)
                time.sleep(0.1)
        except Exception:
            pass


def human_like_scroll(driver):
    """Sayfayı insansı bir şekilde yavaşça aşağı ve yukarı kaydırır."""
    if not ENABLE_HUMAN_SCROLL:
        return
    try:
        total_height = driver.execute_script("return document.body.scrollHeight")
        if not total_height or total_height <= 0:
            return
        steps = random.randint(2, 4)
        for i in range(1, steps + 1):
            scroll_to = int(total_height * (i / steps) * random.uniform(0.7, 0.95))
            driver.execute_script(f"window.scrollTo({{top: {scroll_to}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.2, 0.5))
        driver.execute_script("window.scrollTo({top: 150, behavior: 'smooth'});")
        time.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


def human_delay(min_sec=MIN_DELAY_BETWEEN_PAGES, max_sec=MAX_DELAY_BETWEEN_PAGES):
    """Rastgele insansı bekleme süresi."""
    time.sleep(random.uniform(min_sec, max_sec))


def get_installed_chrome_version():
    """Windows kayıt defterinden (Registry) yüklü Chrome'un ana sürüm numarasını otomatik tespit eder."""
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
    """HTML içeriğini lxml veya html.parser ile güvenli bir şekilde BeautifulSoup nesnesine dönüştürür."""
    try:
        return BeautifulSoup(html_source, "lxml")
    except Exception:
        return BeautifulSoup(html_source, "html.parser")

# En yaygın 10 otomobil markası - sahibinden.com URL formatı
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
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Desktop'a kaydet - izin sorunu yaşamamak için
DATA_BASE_DIR = os.path.join(
    os.path.expanduser("~"), "Desktop", "Datas", "Vehicles", "Otomobil"
)


def check_and_prompt_login(driver):
    """Sahibinden hesabına giriş yapılıp yapılmadığını kontrol eder (Zorunlu tutmadan devam eder)."""
    print("[Oturum] Oturum durumu kontrol ediliyor...")
    try:
        driver.get("https://www.sahibinden.com/")
        human_delay(1.5, 2.5)
        soup = create_soup(driver.page_source)
        
        if soup.select_one(".my-account-link") or soup.select_one("#user-my-account") or "Hesabım" in driver.page_source:
            print("[Oturum] Sahibinden hesabınız açık! Veri çekimine başlanıyor...")
        else:
            print("[Oturum] Oturum açılmamış (Misafir modunda taramaya devam ediliyor)...")
    except Exception:
        pass


def resolve_chrome_profile_directory(name):
    """Chrome profil görünen adını ('Okul', 'İş', 'Default') diskteki klasör adına çevirir."""
    mapping = {
        "okul": "Profile 3",
        "iş": "Profile 4",
        "is": "Profile 4",
        "default": "Default",
        "profile 3": "Profile 3",
        "profile 4": "Profile 4",
    }
    clean_name = str(name).strip().lower()
    return mapping.get(clean_name, name)


def prepare_cloned_profile(profile_name):
    """Diğer Chrome profilleriniz açık olsa dahi kilitlenmeden Okul oturum çerezleriyle başlatır."""
    system_user_data = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data")
    profile_dir = resolve_chrome_profile_directory(profile_name)
    source_profile_path = os.path.join(system_user_data, profile_dir)
    
    target_profile_dir = os.path.join(SCRIPT_DIR, f"SeleniumProfile_{profile_dir}")
    target_default_dir = os.path.join(target_profile_dir, "Default")
    
    os.makedirs(target_default_dir, exist_ok=True)
    
    # Oturum, çerez ve ayar dosyalarını güvenli şekilde klonla
    items_to_copy = ["Network", "Cookies", "Web Data", "Preferences", "Local Storage"]
    for item in items_to_copy:
        src = os.path.join(source_profile_path, item)
        dst = os.path.join(target_default_dir, item)
        if os.path.exists(src):
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
            except Exception:
                pass
                
    return target_profile_dir


def _build_chrome_options():
    """Her çağrıda taze bir ChromeOptions nesnesi oluşturur."""
    options = uc.ChromeOptions()
    
    if USE_SYSTEM_CHROME_PROFILE:
        system_user_data = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data")
        profile_dir = resolve_chrome_profile_directory(CHROME_PROFILE_NAME)
        options.add_argument(f"--user-data-dir={system_user_data}")
        options.add_argument(f"--profile-directory={profile_dir}")
    else:
        profile_path = os.path.join(SCRIPT_DIR, "SeleniumProfile_Fresh")
        options.add_argument(f"--user-data-dir={profile_path}")
        
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    
    # Proxy Yapılandırması
    if ENABLE_PROXY and PROXY_HOST and PROXY_PORT:
        if PROXY_USER and PROXY_PASS:
            proxy_str = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
        else:
            proxy_str = f"http://{PROXY_HOST}:{PROXY_PORT}"
        options.add_argument(f"--proxy-server={proxy_str}")
    
    return options


def setup_driver():
    if USE_SYSTEM_CHROME_PROFILE:
        profile_dir = resolve_chrome_profile_directory(CHROME_PROFILE_NAME)
        print(f"[Driver] '{CHROME_PROFILE_NAME}' profiliniz ({profile_dir}) dogrudan sistemden yukleniyor...")
        print("[BILGI] Sahibinden oturumunuzun otomatik acilmasi icin acik olan Chrome pencerelerinizi 1 defalik kapatin.")
    
    if ENABLE_PROXY and PROXY_HOST and PROXY_PORT:
        print(f"[Driver] Proxy aktif edildi: {PROXY_HOST}:{PROXY_PORT}")
    
    chrome_version = get_installed_chrome_version()
    print(f"[Driver] Tespit edilen Chrome surumu: {chrome_version or 'bilinmiyor'}")
    try:
        options = _build_chrome_options()
        if chrome_version:
            driver = uc.Chrome(options=options, version_main=chrome_version)
        else:
            driver = uc.Chrome(options=options)
    except Exception as e:
        print(f"[Driver] Surucu baslatma uyarisi ({e}). Yeniden deneniyor...")
        options = _build_chrome_options()
        if chrome_version:
            driver = uc.Chrome(options=options, version_main=chrome_version)
        else:
            driver = uc.Chrome(options=options)
    return driver


def check_detail_captcha(driver):
    soup = create_soup(driver.page_source)
    # Detay sayfası yüklenmediyse ve koruma sayfası/captcha çıktıysa
    if not soup.select_one(".classifiedDetail") and not soup.select_one("ul.classifiedInfoList"):
        trigger_captcha_alert()
        print("\n" + "=" * 50)
        print("ACTION REQUIRED: Listing detail page not loaded.")
        print("Likely CAPTCHA or block page appeared.")
        print("1. Solve the captcha in Chrome or verify your session.")
        print("2. Wait until details load.")
        print(f"Current URL: {driver.current_url}")
        print("=" * 50)
        input("Once details are visible, press ENTER here...")
        return True
    return False


def parse_detail_page(driver, url):
    print(f"Loading detail page: {url}")
    driver.get(url)
    human_delay(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES)
    human_like_scroll(driver)
    
    # Captcha kontrolü
    while check_detail_captcha(driver):
        human_delay(1.0, 2.0)
        
    soup = create_soup(driver.page_source)
    details = {}
    
    # classifiedInfoList içindeki detay alanlarını çek (Vites, Yakıt, Motor Gücü vb.)
    info_items = soup.select("ul.classifiedInfoList li")
    for li in info_items:
        label_elem = li.select_one("strong")
        value_elem = li.select_one("span")
        if label_elem and value_elem:
            label = label_elem.get_text(strip=True).rstrip(":")
            value = value_elem.get_text(strip=True)
            details[label] = value
            
    # Açıklama metnini çek
    desc_elem = soup.select_one("#classifiedDescription")
    if desc_elem:
        text = desc_elem.get_text(separator=" ", strip=True)
        details["Description"] = text[:1000] # CSV'yi temiz tutmak için 1000 karakter limiti
        
    return details


def scrape_brand(driver, brand_url_name, brand_folder, max_to_scrape=100):
    url = f"https://www.sahibinden.com/{brand_url_name}?pagingSize=20"

    print(f"\nLoading {url}...")
    driver.get(url)

    all_scraped_data = []
    page_num = 1

    # Adım 1: Arama sonuçlarından ilan listelerini topla (max_to_scrape kadar)
    while len(all_scraped_data) < max_to_scrape:
        time.sleep(2.5)

        soup = create_soup(driver.page_source)
        listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")

        # CAPTCHA / LOGIN check
        if not listings:
            trigger_captcha_alert()
            print("\n" + "=" * 50)
            print("ACTION REQUIRED: No listings found.")
            print("Likely CAPTCHA or login page appeared.")
            print("1. Check the Chrome window and solve CAPTCHA or log in.")
            print("2. Wait until listings appear.")
            print(f"Current URL: {driver.current_url}")
            print("=" * 50)
            input("After you can see listings, press ENTER here...")

            max_checks = 10
            for attempt in range(1, max_checks + 1):
                human_delay(1.5, 3.0)
                soup = create_soup(driver.page_source)
                listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")
                if listings:
                    break
                print(f"Still no listings (check {attempt}/{max_checks}). Refreshing page...")
                driver.refresh()

            if not listings:
                print(f"Still no listings for {brand_folder}. Skipping list collection.")
                break

        print(f"Collecting listings from {brand_folder} page {page_num} ({len(all_scraped_data)}/{max_to_scrape} collected)...")

        # Table header'larını dinamik olarak çöz
        th_elements = soup.select("#searchResultsTable thead th")
        headers = []
        for idx, th in enumerate(th_elements):
            text = th.get_text(strip=True)
            text = re.sub(r"\s+", " ", text)
            if not text:
                classes = th.get("class", [])
                if any("gallery" in c.lower() for c in classes) or idx == 0:
                    text = "Image"
                else:
                    text = f"Column_{idx}"
            headers.append(text)

        for row in listings:
            if len(all_scraped_data) >= max_to_scrape:
                break
            try:
                cells = row.select("td")
                if not cells:
                    continue

                row_data = {}

                # 1. Tanımlı Özel Alanlar (Her zaman çekilecek alanlar)
                price_elem = row.select_one(".searchResultsPriceValue")
                price_raw = price_elem.text.strip() if price_elem else "N/A"
                price = normalize_price(price_raw)
                row_data["Normalized_Price"] = price

                location_elem = row.select_one(".searchResultsLocationValue")
                district = (
                    location_elem.text.strip().replace("\n", " ")
                    if location_elem
                    else "N/A"
                )
                district = re.sub(r"\s+", " ", district)
                row_data["Parsed_Location"] = district

                # İlan başlığı ve Link/URL
                title_link = row.select_one("a.searchResultsTitleValue") or row.select_one("a[href*='/ilan/']")
                if title_link:
                    row_data["Title"] = re.sub(r"\s+", " ", title_link.get_text(strip=True))
                    href = title_link.get("href", "")
                    if href:
                        row_data["URL"] = "https://www.sahibinden.com" + href
                    else:
                        row_data["URL"] = "N/A"
                else:
                    row_data["Title"] = "N/A"
                    row_data["URL"] = "N/A"

                # 2. Dinamik Sütun Eşleme (Marka, Seri, Model, Yıl, KM, Renk vb.)
                for idx, cell in enumerate(cells):
                    col_name = headers[idx] if idx < len(headers) else f"Column_{idx}"
                    if col_name == "Image":
                        continue
                    
                    cell_text = cell.get_text(strip=True)
                    cell_text = re.sub(r"\s+", " ", cell_text)
                    row_data[col_name] = cell_text

                all_scraped_data.append(row_data)

            except Exception as exc:
                print(f"Row parse error: {exc}")
                continue

        if len(all_scraped_data) >= max_to_scrape:
            break

        # Sonraki sayfa
        next_button = soup.find("a", title="Sonraki")
        if next_button and "href" in next_button.attrs:
            next_url = "https://www.sahibinden.com" + next_button["href"]
            driver.get(next_url)
            page_num += 1
            human_delay(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES)
        else:
            print(f"Finished all list pages for {brand_folder}.")
            break

    # Adım 2: Toplanan ilanların her birinin detay sayfasına girerek detayları çek
    if all_scraped_data:
        print(f"\nFetching detail pages for {len(all_scraped_data)} listings in {brand_folder}...")
        for i, listing in enumerate(all_scraped_data, 1):
            url = listing.get("URL")
            if not url or url == "N/A":
                continue
            
            print(f"[{i}/{len(all_scraped_data)}] ", end="")
            try:
                details = parse_detail_page(driver, url)
                listing.update(details)
                human_delay(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES)
            except Exception as exc:
                print(f"Detail parse error for {url}: {exc}")
                continue

            # Anti-bot dinlenme molası (Her BATCH_SIZE_BEFORE_PAUSE ilanda bir)
            if i % BATCH_SIZE_BEFORE_PAUSE == 0 and i < len(all_scraped_data):
                pause_time = random.uniform(BATCH_PAUSE_DURATION_MIN, BATCH_PAUSE_DURATION_MAX)
                print(f"\n[Anti-Bot Cooldown] {i} ilan detayları çekildi. {pause_time:.1f} saniye dinleniliyor...")
                time.sleep(pause_time)

        save_to_csv(brand_folder, all_scraped_data)
    else:
        print(f"No listings found for {brand_folder}, skipping save.")


def save_to_csv(brand_folder, data):
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(DATA_BASE_DIR, brand_folder)
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, f"{today_str}.csv")

    # Kolon isimlerini dinamik olarak topla ve sırala
    fieldnames = []
    preferred_order = [
        "Title", "URL", "Normalized_Price", "Parsed_Location", 
        "Marka", "Seri", "Model", "Yıl", "KM", "Renk", 
        "Yakıt", "Vites", "Kasa Tipi", "Motor Hacmi", "Motor Gücü", "Çekiş", "Boya-Değişen"
    ]
    
    all_keys = set()
    for row in data:
        all_keys.update(row.keys())
        
    for key in preferred_order:
        if key in all_keys:
            fieldnames.append(key)
            all_keys.remove(key)
            
    fieldnames.extend(sorted(list(all_keys)))
    
    if "Image" in fieldnames:
        fieldnames.remove("Image")

    with open(file_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)

    print(f"Saved {len(data)} records to {file_path}")


def normalize_price(price_text):
    if not price_text or price_text == "N/A":
        return None
    cleaned = price_text.lower()
    cleaned = cleaned.replace("tl", "").replace("₺", "").strip()
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
            if len(parts) > 1 and all(part.isdigit() for part in parts):
                if all(len(part) == 3 for part in parts[1:]):
                    cleaned = "".join(parts)
    try:
        return float(cleaned)
    except ValueError:
        return None


def main():
    driver = setup_driver()
    check_and_prompt_login(driver)
    LIMIT_PER_BRAND = 100
    try:
        total_brands = len(BRANDS)
        for i, (brand_url_name, brand_folder) in enumerate(BRANDS.items(), 1):
            print(f"\n{'='*70}")
            print(f"[{i}/{total_brands}] Scraping {brand_folder} (Target Limit: {LIMIT_PER_BRAND})...")
            print(f"{'='*70}")
            
            scrape_brand(driver, brand_url_name, brand_folder, LIMIT_PER_BRAND)
    finally:
        driver.quit()
        print("\nAll done!")


if __name__ == "__main__":
    main()
