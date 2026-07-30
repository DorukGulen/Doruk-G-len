import os
import sys
import csv
import time
import random
import re
from datetime import datetime

from bs4 import BeautifulSoup
import undetected_chromedriver as uc

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
MIN_DELAY_BETWEEN_PAGES = 3.0      # Sayfalar arası minimum bekleme
MAX_DELAY_BETWEEN_PAGES = 6.0      # Sayfalar arası maksimum bekleme
BATCH_SIZE_BEFORE_PAUSE = 5        # Kaç LİSTE sayfasında bir uzun mola verileceği
BATCH_PAUSE_DURATION_MIN = 15.0    # Uzun mola minimum süresi (saniye)
BATCH_PAUSE_DURATION_MAX = 30.0    # Uzun mola maksimum süresi (saniye)
ENABLE_HUMAN_SCROLL = True         # Liste sayfasında insansı scroll

ENABLE_SOUND_ALERT = True          # CAPTCHA çıktığında sesli bip uyarısı
DISABLE_IMAGES = True              # Resimleri kapatır (İnternet kullanımını %90 azaltır ve testi hızlandırır)

# Oturum / Chrome Profil Ayarları
USE_SYSTEM_CHROME_PROFILE = False
CHROME_PROFILE_NAME = "Default"    # "Default", "Profile 3", "Profile 4"

# Proxy Ayarları
ENABLE_PROXY = False
PROXY_HOST = ""
PROXY_PORT = ""
PROXY_USER = ""
PROXY_PASS = ""

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


# Windows'ta undetected_chromedriver __del__ aşamasındaki WinError 6 hatasını engelleme yaması
def _safe_uc_del(self):
    try:
        self.quit()
    except Exception:
        pass


uc.Chrome.__del__ = _safe_uc_del


# ==========================================
# YARDIMCI FONKSİYONLAR
# ==========================================
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
    """Windows kayıt defterinden yüklü Chrome'un ana sürüm numarasını tespit eder."""
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
    """HTML içeriğini lxml veya html.parser ile BeautifulSoup nesnesine dönüştürür."""
    try:
        return BeautifulSoup(html_source, "lxml")
    except Exception:
        return BeautifulSoup(html_source, "html.parser")


def resolve_chrome_profile_directory(name):
    """Chrome profil görünen adını diskteki klasör adına çevirir."""
    mapping = {
        "okul": "Profile 3",
        "iş": "Profile 4",
        "is": "Profile 4",
        "default": "Default",
        "profile 3": "Profile 3",
        "profile 4": "Profile 4",
    }
    return mapping.get(str(name).strip().lower(), name)


def _build_chrome_options():
    options = uc.ChromeOptions()

    if USE_SYSTEM_CHROME_PROFILE:
        system_user_data = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data"
        )
        profile_dir = resolve_chrome_profile_directory(CHROME_PROFILE_NAME)
        options.add_argument(f"--user-data-dir={system_user_data}")
        options.add_argument(f"--profile-directory={profile_dir}")
    else:
        profile_path = os.path.join(SCRIPT_DIR, "SeleniumProfile_Fresh")
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


def setup_driver():
    if USE_SYSTEM_CHROME_PROFILE:
        profile_dir = resolve_chrome_profile_directory(CHROME_PROFILE_NAME)
        print(f"[Driver] '{CHROME_PROFILE_NAME}' profili ({profile_dir}) sistemden yukleniyor...")
        print("[BILGI] Oturumun acilmasi icin acik Chrome pencerelerini 1 defalik kapatin.")

    if ENABLE_PROXY and PROXY_HOST and PROXY_PORT:
        print(f"[Driver] Proxy aktif: {PROXY_HOST}:{PROXY_PORT}")

    chrome_version = get_installed_chrome_version()
    print(f"[Driver] Tespit edilen Chrome surumu: {chrome_version or 'bilinmiyor'}")
    try:
        options = _build_chrome_options()
        if chrome_version:
            return uc.Chrome(options=options, version_main=chrome_version)
        return uc.Chrome(options=options)
    except Exception as e:
        print(f"[Driver] Surucu baslatma uyarisi ({e}). Yeniden deneniyor...")
        options = _build_chrome_options()
        if chrome_version:
            return uc.Chrome(options=options, version_main=chrome_version)
        return uc.Chrome(options=options)


def check_and_prompt_login(driver):
    """Oturum durumunu kontrol eder ve isteğe bağlı giriş yapılmasına imkan tanır."""
    print("[Oturum] Oturum durumu kontrol ediliyor...")
    try:
        driver.get("https://www.sahibinden.com/")
        human_delay(1.5, 2.5)
        soup = create_soup(driver.page_source)
        if (
            soup.select_one(".my-account-link")
            or soup.select_one("#user-my-account")
            or "Hesabım" in driver.page_source
        ):
            print("[Oturum] Sahibinden hesabınız açık! Oturum çerezleri kullanılıyor...")
        else:
            print("[Oturum] Henüz oturum açılmamış.")
            print("[İPUCU] Giriş yapmak isterseniz Chrome penceresinden giriş yapın (Mail doğrulama kodunu bir kere girmeniz yeterlidir, kaydedilir).")
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
# LİSTE SAYFASI PARSE
# ==========================================
def extract_headers(soup):
    """Arama sonuç tablosunun sütun başlıklarını dinamik olarak çözer."""
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
    """Tek bir ilan satirindan (tr.searchResultsItem) genel bilgileri cikarir."""
    cells = row.select("td")
    if not cells:
        return None

    row_data = {"Kaynak_Marka": brand_folder}

    # Fiyat
    price_elem = row.select_one(".searchResultsPriceValue")
    price_raw = price_elem.get_text(strip=True) if price_elem else "N/A"
    row_data["Fiyat_Raw"] = price_raw
    row_data["Normalized_Price"] = normalize_price(price_raw)

    # Konum
    location_elem = row.select_one(".searchResultsLocationValue")
    district = location_elem.get_text(" ", strip=True) if location_elem else "N/A"
    row_data["Parsed_Location"] = re.sub(r"\s+", " ", district)

    # İlan tarihi
    date_elem = row.select_one(".searchResultsDateValue")
    if date_elem:
        row_data["Ilan_Tarihi"] = re.sub(r"\s+", " ", date_elem.get_text(" ", strip=True))

    # Başlık + URL
    title_link = row.select_one("a.searchResultsTitleValue") or row.select_one("a[href*='/ilan/']")
    if title_link:
        row_data["Title"] = re.sub(r"\s+", " ", title_link.get_text(strip=True))
        href = title_link.get("href", "")
        row_data["URL"] = ("https://www.sahibinden.com" + href) if href else "N/A"
    else:
        row_data["Title"] = "N/A"
        row_data["URL"] = "N/A"

    # İlan ID (varsa)
    listing_id = row.get("data-id") or ""
    if not listing_id and row_data["URL"] != "N/A":
        match = re.search(r"-(\d+)/detay", row_data["URL"]) or re.search(r"(\d{6,})", row_data["URL"])
        listing_id = match.group(1) if match else ""
    row_data["Ilan_No"] = listing_id

    # Dinamik sütun eşleme (Marka, Seri, Model, Yıl, KM, Renk vb.)
    for idx, cell in enumerate(cells):
        col_name = headers[idx] if idx < len(headers) else f"Column_{idx}"
        if col_name == "Image":
            continue
        row_data[col_name] = re.sub(r"\s+", " ", cell.get_text(strip=True))

    return row_data


def check_is_login_wall(driver):
    """Giriş yap sayfasına (secure.sahibinden.com/giris) veya yönlendirmeye takılıp takılmadığını kontrol eder."""
    current_url = driver.current_url.lower()
    page_source = driver.page_source.lower()
    if "secure.sahibinden.com/giris" in current_url or "giriş yap" in page_source:
        return True
    return False


def handle_blocked_page(driver, brand_folder):
    """Liste görünmüyorsa CAPTCHA/blok uyarısı verir ve tekrar dener."""
    trigger_captcha_alert()
    print("\n" + "=" * 50)
    if check_is_login_wall(driver):
        print("UYARI: Sahibinden Giriş Yap Duvarına Takıldı!")
        print("1. Açılan Chrome penceresinde üye girişi yapın.")
        print("2. Veya sayfayı kapatıp yeniden başlatın.")
    else:
        print("ACTION REQUIRED: No listings found.")
        print("Likely CAPTCHA or login page appeared.")
        print("1. Check the Chrome window and solve CAPTCHA or log in.")
    print("2. Wait until listings appear.")
    print(f"Current URL: {driver.current_url}")
    print("=" * 50)
    input("İlanları görünce veya işlemi tamamlayınca ENTER'a basın...")

    for attempt in range(1, 11):
        human_delay(1.5, 3.0)
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
        human_delay(2.0, 3.5)
        human_like_scroll(driver)

        soup = create_soup(driver.page_source)
        listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")

        if not listings:
            soup, listings = handle_blocked_page(driver, brand_folder)
            if not listings:
                break

        print(f"[{brand_folder}] Sayfa {page_num} -> {len(all_scraped_data)}/{max_to_scrape} kayit")

        headers = extract_headers(soup)

        for row in listings:
            if len(all_scraped_data) >= max_to_scrape:
                break
            try:
                row_data = parse_listing_row(row, headers, brand_folder)
                if not row_data:
                    continue

                # Vitrin/tekrarlayan ilanlari atla
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

        # Sonraki sayfa
        next_button = soup.find("a", title="Sonraki")
        if next_button and next_button.get("href"):
            next_url = "https://www.sahibinden.com" + next_button["href"]
            driver.get(next_url)
            page_num += 1
            human_delay(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES)

            if page_num % BATCH_SIZE_BEFORE_PAUSE == 0:
                pause = random.uniform(BATCH_PAUSE_DURATION_MIN, BATCH_PAUSE_DURATION_MAX)
                print(f"[Anti-Bot Cooldown] {pause:.1f} saniye dinleniliyor...")
                time.sleep(pause)
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
    driver = setup_driver()
    check_and_prompt_login(driver)
    LIMIT_PER_BRAND = 999
    try:
        total_brands = len(BRANDS)
        for i, (brand_url_name, brand_folder) in enumerate(BRANDS.items(), 1):
            print(f"\n{'=' * 70}")
            print(f"[{i}/{total_brands}] Scraping {brand_folder} (Target Limit: {LIMIT_PER_BRAND})...")
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