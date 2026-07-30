import os
import sys
import io
import csv
import time
import random
import json
import shutil
import math
from datetime import datetime
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.keys import Keys
import re

# Windows konsolunda (cp1254/cp1252) Unicode/Emoji yazdırma hatasını engellemek için UTF-8 reconfigure
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass


# ==========================================
# ADVANCED FAST SCRAPER CONFIGURATION
# ==========================================
# Gecikme ayarları (Liste sayfaları arası bekleme)
MIN_DELAY_BETWEEN_PAGES = 1.0      # Liste sayfaları arası minimum bekleme (saniye)
MAX_DELAY_BETWEEN_PAGES = 2.0      # Liste sayfaları arası maksimum bekleme (saniye)
ENABLE_WARMUP = False              # Google ısınma akışını atlamak (doğrudan hızlı başlamak) için False yapın

# CAPTCHA / IP Engeli Sesli Uyarı Ayarları
ENABLE_SOUND_ALERT = True          # Engel veya CAPTCHA çıktığında sesli bip uyarısı çal

# Seed Fiyat Aralıkları (1000 limitini aşmak için ikili arama taban fiyatları)
SEED_RANGES = [
    (0,          250_000),
    (250_001,    500_000),
    (500_001,  1_000_000),
    (1_000_001, 2_000_000),
    (2_000_001, 99_999_999)
]

# Oturum / Chrome Profil Ayarları
USE_SYSTEM_CHROME_PROFILE = False       # Kendi Chrome profillerinizden birini kullanmak için True yapın
CHROME_PROFILE_NAME = "Okul"         # Açmak istediğiniz profil adı: "Default", "Profile 3", "Profile 4"  

# Proxy Ayarları
ENABLE_PROXY = False               # Proxy satın aldıysanız True yapın
PROXY_HOST = ""                    # Örnek: "123.45.67.89" veya "zproxy.lum-superproxy.io"
PROXY_PORT = ""                    # Örnek: "8080" veya "22225"
PROXY_USER = ""                    # Kullanıcı adı (varsa)
PROXY_PASS = ""                    # Şifre (varsa)


# Oturum / Login Duvarı Engeli İstisnası
class LoginRequiredException(Exception):
    pass


# Windows'ta undetected_chromedriver __del__ aşamasındaki WinError 6 hatasını engelleme yaması
def _safe_uc_del(self):
    try:
        self.quit()
    except Exception:
        pass

uc.Chrome.__del__ = _safe_uc_del


def trigger_captcha_alert():
    """CAPTCHA veya engel tespit edildiğinde sesli uyarı verir (Windows)."""
    if ENABLE_SOUND_ALERT:
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 300)
                time.sleep(0.1)
        except Exception:
            pass


def human_delay(min_sec=MIN_DELAY_BETWEEN_PAGES, max_sec=MAX_DELAY_BETWEEN_PAGES):
    """Rastgele insansı bekleme süresi."""
    time.sleep(random.uniform(min_sec, max_sec))


def _check_login_wall(driver):
    """Sert oturum/giriş duvarı engelini kontrol eder."""
    page_source = driver.page_source.lower()
    current_url = driver.current_url.lower()

    if "sahibinden.com" in current_url:
        if "giriş yapmanız gerekmektedir" in page_source or "secure.sahibinden.com/giris" in current_url:
            trigger_captcha_alert()
            print("[ALERT] Sert Oturum/Login Engeli Algilandi! Profil temizlenip yeniden baslatilacak...")
            raise LoginRequiredException("Giris duvarına takıldı.")


# ==========================================
# UCRETSIZ OTOMATIK CHALLENGE / CAPTCHA COZUCU
# ==========================================
AUTO_SOLVE_MAX_WAIT = 30           # Challenge sayfasinda maksimum bekleme suresi (saniye)
AUTO_SOLVE_MAX_RETRIES = 3         # Otomatik cozum deneme sayisi

def _is_challenge_page(driver):
    """Sahibinden challenge/loading sayfasinda olup olmadigini kontrol eder."""
    current_url = driver.current_url.lower()
    page_source = driver.page_source.lower()
    
    challenge_indicators = [
        "/cs/tloading" in current_url,
        "/cs/challenge" in current_url,
        "olagan disi erisim" in page_source,
        "unusual activity" in page_source,
        "captcha" in page_source and "sahibinden" in current_url,
        "cf-turnstile" in page_source,
        "challenge-platform" in page_source,
        "just a moment" in page_source and "sahibinden" in current_url,
    ]
    return any(challenge_indicators)


def _try_click_turnstile(driver):
    """Cloudflare Turnstile / checkbox challenge varsa otomatik tiklamaya calisir."""
    try:
        # Turnstile iframe'ini bul
        iframes = driver.find_elements("css selector", "iframe[src*='turnstile'], iframe[src*='challenge'], iframe[src*='captcha'], iframe[title*='challenge']")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                # Checkbox veya verify butonunu tikla
                clickables = driver.find_elements("css selector", "input[type='checkbox'], .cb-i, #challenge-stage input, button")
                for elem in clickables:
                    if elem.is_displayed():
                        time.sleep(random.uniform(0.3, 0.8))
                        elem.click()
                        print("[AutoSolve] Turnstile checkbox/button tiklandi.")
                        time.sleep(2)
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
                continue
        
        # iframe disinda direkt checkbox/buton varsa
        direct_buttons = driver.find_elements("css selector", 
            "button[type='submit'], input[type='submit'], .challenge-form button, "
            "#challenge-form button, .g-recaptcha, .h-captcha")
        for btn in direct_buttons:
            try:
                if btn.is_displayed():
                    time.sleep(random.uniform(0.5, 1.0))
                    btn.click()
                    print("[AutoSolve] Direkt challenge butonu tiklandi.")
                    time.sleep(2)
            except Exception:
                continue
                
    except Exception as e:
        print(f"[AutoSolve] Turnstile tiklama hatasi: {e}")


def _auto_solve_challenge(driver):
    """
    Ucretsiz otomatik challenge cozucu:
    1. Challenge sayfasini tespit et
    2. JS'nin otomatik cozmesini bekle (cogu challenge 5-15 sn icinde cozulur)
    3. Turnstile/checkbox varsa otomatik tikla
    4. Cozulmezse sayfayi yenile ve tekrar dene
    5. Hicbiri islemezse False dondur (kullaniciya sor)
    """
    if not _is_challenge_page(driver):
        return True  # Challenge yok, devam et
    
    print(f"[AutoSolve] Challenge/CAPTCHA sayfasi tespit edildi: {driver.current_url}")
    
    for retry in range(1, AUTO_SOLVE_MAX_RETRIES + 1):
        print(f"[AutoSolve] Deneme {retry}/{AUTO_SOLVE_MAX_RETRIES} - Otomatik cozum bekleniyor...")
        
        # Adim 1: JS challenge'in kendini cozmesini bekle
        start = time.time()
        while (time.time() - start) < AUTO_SOLVE_MAX_WAIT:
            if not _is_challenge_page(driver):
                print(f"[AutoSolve] Challenge otomatik cozuldu! ({time.time() - start:.1f} sn)")
                return True
            
            # Adim 2: Her 3 saniyede Turnstile/checkbox tiklamaya calis
            if int(time.time() - start) % 3 == 0:
                _try_click_turnstile(driver)
            
            time.sleep(1.0)
        
        # Adim 3: Cozulmediyse sayfayi yenile
        if retry < AUTO_SOLVE_MAX_RETRIES:
            print(f"[AutoSolve] {AUTO_SOLVE_MAX_WAIT}sn icerisinde cozulemedi. Sayfa yenileniyor...")
            driver.refresh()
            time.sleep(random.uniform(3.0, 5.0))
    
    print("[AutoSolve] Otomatik cozum basarisiz. Manuel mudahale gerekiyor.")
    return False


def human_like_scroll(driver, target_duration=2.0):
    """Sayfayı insansı bir şekilde kaydırır."""
    start_time = time.time()
    try:
        while (time.time() - start_time) < target_duration:
            total_height = driver.execute_script("return document.body.scrollHeight")
            if not total_height:
                break
            current_pos = driver.execute_script("return window.pageYOffset;")
            step = random.randint(200, 400)
            new_pos = current_pos + step
            if new_pos > total_height:
                new_pos = max(0, total_height - random.randint(100, 300))
            driver.execute_script(f"window.scrollTo({{top: {new_pos}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


def warmup_session(driver):
    """Organik Isınma Akışı: Google -> Sahibinden -> Arama."""
    if not ENABLE_WARMUP:
        print("[Isınma] Organik ısınma akışı devredışı (Hızlı başlanıyor)...")
        return
    print("[WARMUP] Organik tarayıcı ısınma (warmup) akışı başlatılıyor...")
    try:
        driver.get("https://www.google.com")
        human_delay(2.0, 4.0)

        try:
            search_q = driver.find_element("name", "q")
            search_q.send_keys("sahibinden otomobil")
            search_q.send_keys(Keys.ENTER)
            human_delay(3.0, 5.0)

            sahibinden_link = driver.find_element("xpath", "//a[contains(@href, 'sahibinden.com')]")
            driver.execute_script("arguments[0].click();", sahibinden_link)
            human_delay(4.0, 6.0)
        except Exception:
            driver.get("https://www.sahibinden.com/")
            human_delay(3.0, 5.0)

        _check_login_wall(driver)
        print("[WARMUP] Isınma tamamlandı!")
    except LoginRequiredException:
        raise
    except Exception as e:
        print(f"[WARMUP] Isınma aşamasında hafif aksama: {e}. Doğrudan taramaya geçiliyor.")


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

# Hızlı çekim verilerinin ve checkpoint'lerin kaydedileceği klasörler
DATA_BASE_DIR = os.path.join(
    os.path.expanduser("~"), "Desktop", "Datas", "Vehicles", "Otomobil_Fast"
)
CHECKPOINT_DIR = os.path.join(SCRIPT_DIR, "checkpoints")
TODAY_STR = datetime.now().strftime("%Y-%m-%d")
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, f"checkpoint_fast_{TODAY_STR}.json")


# ==========================================
# CHECKPOINT (KALDIĞI YERDEN DEVAM ETME) SISTEMI
# ==========================================
def _load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"scraped_urls": [], "completed_brands": []}


def _save_checkpoint(data):
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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
    """Her çağrıda taze bir ChromeOptions nesnesi oluşturur (uc tek kullanımlık olduğu için)."""
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


def scrape_brand_fast(driver, brand_url_name, brand_folder, max_to_scrape=100, checkpoint=None):
    """Detay sayfalarına girmeden doğrudan arama listesinden verileri çeker (Çok Hızlı ve Checkpoint destekli)."""
    if checkpoint is None:
        checkpoint = {"scraped_urls": [], "completed_brands": []}

    url = f"https://www.sahibinden.com/{brand_url_name}?pagingSize=20"

    print(f"\n[Fast Scraper] Loading list page: {url}...")
    driver.get(url)

    all_scraped_data = []
    page_num = 1
    scraped_urls = set(checkpoint.get("scraped_urls", []))

    while len(all_scraped_data) < max_to_scrape:
        human_delay(MIN_DELAY_BETWEEN_PAGES, MAX_DELAY_BETWEEN_PAGES)
        _check_login_wall(driver)

        soup = create_soup(driver.page_source)
        listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")

        # CAPTCHA / LOGIN / IP BLOCK kontrolü
        if not listings:
            _check_login_wall(driver)
            trigger_captcha_alert()
            print("\n" + "=" * 50)
            print("DIKKAT: Sayfa yüklenemedi veya IP ENGELİ (Olağan Dışı Erişim) Çıktı!")
            print("1. Modeminizi kapatıp açarak IP adresi değiştirebilirsiniz.")
            print("2. Veya Chrome penceresindeki CAPTCHA doğrulamasını manuel çözün.")
            print(f"Mevcut URL: {driver.current_url}")
            print("=" * 50)
            input("Engeli kaldırdıktan veya doğrulamayı yaptıktan sonra ENTER'a basın...")

            max_checks = 10
            for attempt in range(1, max_checks + 1):
                human_delay(1.5, 3.0)
                _check_login_wall(driver)
                soup = create_soup(driver.page_source)
                listings = soup.select("#searchResultsTable tbody tr.searchResultsItem")
                if listings:
                    break
                print(f"Still no listings (check {attempt}/{max_checks}). Refreshing page...")
                driver.refresh()

            if not listings:
                print(f"No listings found for {brand_folder}. Skipping.")
                break

        print(f"[{brand_folder}] Collecting page {page_num} ({len(all_scraped_data)}/{max_to_scrape} gathered)...")

        # Tablo başlıklarını çöz
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

        # Tablodan verileri çek
        for row in listings:
            if len(all_scraped_data) >= max_to_scrape:
                break
            try:
                cells = row.select("td")
                if not cells:
                    continue

                row_data = {}

                # Özel Alanlar
                price_elem = row.select_one(".searchResultsPriceValue")
                price_raw = price_elem.text.strip() if price_elem else "N/A"
                row_data["Normalized_Price"] = normalize_price(price_raw)

                location_elem = row.select_one(".searchResultsLocationValue")
                district = (
                    location_elem.text.strip().replace("\n", " ")
                    if location_elem
                    else "N/A"
                )
                row_data["Parsed_Location"] = re.sub(r"\s+", " ", district)

                # Başlık ve İlan URL'si
                title_link = row.select_one("a.searchResultsTitleValue") or row.select_one("a[href*='/ilan/']")
                if title_link:
                    row_data["Title"] = re.sub(r"\s+", " ", title_link.get_text(strip=True))
                    href = title_link.get("href", "")
                    item_url = "https://www.sahibinden.com" + href if href else "N/A"
                    row_data["URL"] = item_url
                else:
                    row_data["Title"] = "N/A"
                    row_data["URL"] = "N/A"

                if item_url in scraped_urls:
                    continue

                # Liste tablosundaki diğer sütunlar (Model, Seri, Yıl, KM, Renk vb.)
                for idx, cell in enumerate(cells):
                    col_name = headers[idx] if idx < len(headers) else f"Column_{idx}"
                    if col_name == "Image":
                        continue
                    cell_text = re.sub(r"\s+", " ", cell.get_text(strip=True))
                    row_data[col_name] = cell_text

                all_scraped_data.append(row_data)
                scraped_urls.add(item_url)

            except Exception as exc:
                print(f"Row parse error: {exc}")
                continue

        # Anlık checkpoint kaydı
        checkpoint["scraped_urls"] = list(scraped_urls)
        _save_checkpoint(checkpoint)

        if len(all_scraped_data) >= max_to_scrape:
            break

        # Sonraki sayfa düğmesi
        next_button = soup.find("a", title="Sonraki")
        if next_button and "href" in next_button.attrs:
            next_url = "https://www.sahibinden.com" + next_button["href"]
            driver.get(next_url)
            page_num += 1
        else:
            print(f"Reached end of search results for {brand_folder}.")
            break

    if all_scraped_data:
        save_to_csv(brand_folder, all_scraped_data)
    else:
        print(f"No new listings saved for {brand_folder}.")


def save_to_csv(brand_folder, data):
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(DATA_BASE_DIR, brand_folder)
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, f"{today_str}.csv")

    fieldnames = []
    preferred_order = [
        "Title", "URL", "Normalized_Price", "Parsed_Location", 
        "Marka", "Seri", "Model", "Yıl", "KM", "Renk"
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

    file_exists = os.path.isfile(file_path)
    with open(file_path, mode="a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(data)

    print(f"--> [Fast Scraper] Incremental saved {len(data)} records to {file_path}")


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
            if len(parts) > 1 and all(part.isdigit() for part in parts):
                if all(len(part) == 3 for part in parts[1:]):
                    cleaned = "".join(parts)
    try:
        return float(cleaned)
    except ValueError:
        return None


def main():
    LIMIT_PER_BRAND = 100

    while True:
        checkpoint = _load_checkpoint()
        driver = None

        try:
            driver = setup_driver()
            warmup_session(driver)
            check_and_prompt_login(driver)

            total_brands = len(BRANDS)
            for i, (brand_url_name, brand_folder) in enumerate(BRANDS.items(), 1):
                if brand_folder in checkpoint.get("completed_brands", []):
                    print(f"[SKIP] Skipping completed brand: {brand_folder}")
                    continue

                print(f"\n{'='*70}")
                print(f"[{i}/{total_brands}] FAST Scraping {brand_folder} (Target Limit: {LIMIT_PER_BRAND})...")
                print(f"{'='*70}")
                
                scrape_brand_fast(driver, brand_url_name, brand_folder, LIMIT_PER_BRAND, checkpoint)

                checkpoint["completed_brands"].append(brand_folder)
                _save_checkpoint(checkpoint)

            print("\n[SUCCESS] Tüm markalar başarıyla tamamlandı!")
            break

        except LoginRequiredException:
            wait_time = random.uniform(15.0, 25.0)
            print(f"\n[WAIT] Oturum engeli algılandı. {wait_time:.1f} saniye soğuma bekleniyor...")
            time.sleep(wait_time)

            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

            profile_path = os.path.join(SCRIPT_DIR, "SeleniumProfile_Fresh")
            if os.path.exists(profile_path):
                try:
                    shutil.rmtree(profile_path)
                    print(f"[CLEAN] Eski profil temizlendi: {profile_path}")
                except Exception as e:
                    print(f"Profil silinemedi: {e}")

            print("[RESTART] Yeni profil ile otomatik yeniden başlatılıyor...\n")
            continue

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
