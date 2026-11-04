import sqlite3
import feedparser
import requests
from bs4 import BeautifulSoup
import os
import re
import html as html_mod
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================================================
# KONFIGURASI
# ==========================================================================
BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "database_hasil5" / "database.sqlite"
RSS_FILE = BASE_DIR / "rss_list.txt"

# ⚠️ Iklan Adsterra akan disisipkan ke setiap artikel
ADSTERRA_CODE = """
<div style="text-align:center; margin:20px 0;">
    <script type="text/javascript">
        atOptions = {'key' : 'f9e40eb3b3cd05f1038aac7b36b33ad2','format' : 'iframe','height' : 90,'width' : 728,'params' : {}};
    </script>
    <script type="text/javascript" src="https://upholdbrilliancerecast.com/f9e40eb3b3cd05f1038aac7b36b33ad2/invoke.js"></script>
</div>
"""

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

AUTHOR_NAME = "Admin"

# ==========================================================================
# BAGIAN 1: FUNGSI DATABASE & SCRAPING
# ==========================================================================
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artikel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE, judul TEXT, konten TEXT, gambar TEXT,
            tanggal_publish TEXT, tanggal_update TEXT
        )
    """)
    conn.commit()
    conn.close()

def extract_full_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code != 200: return None, None, None
        soup = BeautifulSoup(response.text, 'html.parser')

        image_url = None
        og_image = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
        if og_image and og_image.get('content'): image_url = og_image['content']

        paragraphs = soup.find_all('p')
        full_text = []
        for p in paragraphs:
            text = p.get_text().strip()
            if len(text) > 40 and not any(x in text.lower() for x in ['cookie', 'privacy', 'subscribe', 'rights reserved']):
                full_text.append(f"<p>{text}</p>")

        return "\n".join(full_text) if full_text else None, image_url, None
    except Exception:
        return None, None, None

def process_single_feed(feed_url):
    feed_url = feed_url.strip()
    if not feed_url or feed_url.startswith("#"): return 0, 0

    baru = 0
    duplikat = 0

    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=5)
        if response.status_code != 200: return 0, 0
        
        feed = feedparser.parse(response.content)
        conn = sqlite3.connect(str(DB_PATH), timeout=15)
        cursor = conn.cursor()

        for entry in feed.entries[:5]: # Ambil max 5 berita terbaru per RSS
            link = entry.get('link', '')
            judul = entry.get('title', 'Tanpa Judul')
            if not link: continue

            cursor.execute("SELECT id FROM artikel WHERE link = ?", (link,))
            if cursor.fetchone():
                duplikat += 1
                continue

            full_text_html, image_url, _ = extract_full_content(link)
            if not full_text_html:
                full_text_html = f"<p>{entry.get('summary', 'Konten tidak tersedia.')}</p>"

            tanggal = datetime.now().isoformat()
            img_tag = f'<div style="text-align:center; margin-bottom:20px;"><img src="{image_url}" alt="{judul}" style="max-width:100%; height:auto; border-radius:8px;" loading="lazy"></div>' if image_url else ""
            
            # Konten disisipi iklan
            konten_lengkap = f"""
            {img_tag}
            {ADSTERRA_CODE}
            <div class="article-body" style="font-size: 16px; line-height: 1.8; color: #333;">
                {full_text_html}
                <p style="margin-top: 25px;">
                    <a href="{link}" target="_blank" rel="nofollow noopener" style="color: #0d6efd; text-decoration: none; font-weight: bold;">
                        &rarr; Baca artikel asli
                    </a>
                </p>
            </div>
            {ADSTERRA_CODE}
            """

            try:
                cursor.execute(
                    "INSERT INTO artikel (link, judul, konten, gambar, tanggal_publish, tanggal_update) VALUES (?, ?, ?, ?, ?, ?)",
                    (link, judul, konten_lengkap, image_url, tanggal, tanggal)
                )
                conn.commit()
                baru += 1
            except sqlite3.IntegrityError:
                duplikat += 1
            except Exception:
                pass
        conn.close()
    except Exception:
        pass
    return baru, duplikat

def jalankan_scraping():
    if not RSS_FILE.exists():
        print(f"[ERROR] File {RSS_FILE} tidak ditemukan!")
        return
    init_db()
    
    with open(RSS_FILE, "r", encoding="utf-8") as f:
        rss_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    print(f"[*] Memulai scraping dari {len(rss_urls)} RSS...")
    total_baru, total_duplikat = 0, 0
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_single_feed, url): url for url in rss_urls}
        for future in as_completed(futures):
            b, d = future.result()
            total_baru += b
            total_duplikat += d

    print(f"[SELESAI SCRAPING] Baru: {total_baru} | Duplikat: {total_duplikat}\n")


# ==========================================================================
# BAGIAN 2: EKSPOR KE XML BLOGGER
# ==========================================================================
def esc(text):
    if not text: return ""
    return html_mod.escape(str(text))

def generate_blogger_xml():
    print("[*] Membaca database untuk export Blogger...")
    
    if not DB_PATH.exists():
        print("❌ Database tidak ada. Tidak ada yang bisa diexport.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT id, judul, konten, gambar, tanggal_publish, link FROM artikel ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("⚠️ Tidak ada artikel di dalam database.")
        return

    print(f"[*] Memproses {len(rows)} artikel menjadi XML Blogger...")
    today_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000+07:00')
    
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:app="http://www.w3.org/2007/app">',
        '  <title type="text">Blogger Export</title>',
        f'  <updated>{today_iso}</updated>',
        '  <generator version="7.00">Blogger</generator>',
        '  <author>',
        f'    <name>{esc(AUTHOR_NAME)}</name>',
        '    <email>noreply@blogger.com</email>',
        '  </author>',
    ]

    for row in rows:
        artikel_id, judul, konten, gambar, tanggal_publish, link = row
        
        published_iso = today_iso
        if tanggal_publish:
            try:
                dt = datetime.fromisoformat(tanggal_publish.replace('Z', '+00:00'))
                published_iso = dt.strftime('%Y-%m-%dT%H:%M:%S.000+07:00')
            except:
                pass

        safe_content = esc(konten)
        post_id = f"tag:blogger.com,1999:blog-{artikel_id}.post-{artikel_id}"
        post_url = f"https://dummy.blogspot.com/{artikel_id}.html"

        xml_parts.append('  <entry>')
        xml_parts.append(f'    <id>{post_id}</id>')
        xml_parts.append(f'    <published>{published_iso}</published>')
        xml_parts.append(f'    <updated>{published_iso}</updated>')
        xml_parts.append('    <app:control><app:draft>no</app:draft></app:control>')
        xml_parts.append(f'    <title type="text">{esc(judul)}</title>')
        xml_parts.append(f'    <content type="html">{safe_content}</content>')
        xml_parts.append(f'    <link rel="alternate" type="text/html" href="{post_url}" title="{esc(judul)}"/>')
        xml_parts.append('    <author>')
        xml_parts.append(f'      <name>{esc(AUTHOR_NAME)}</name>')
        xml_parts.append('      <email>noreply@blogger.com</email>')
        xml_parts.append('    </author>')
        xml_parts.append('  </entry>')

    xml_parts.append('</feed>')

    output_filename = "export_blogger.xml"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_parts))

    print(f"\n[✅ SELESAI] File XML berhasil dibuat: {output_filename}")
    print(f"Total artikel siap diimpor: {len(rows)}")

# ==========================================================================
# BAGIAN 3: JALANKAN SEMUANYA
# ==========================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("MULAI PROSES SCRAPING & EXPORT BLOGGER")
    print("=" * 50)
    
    # 1. Ambil berita dari RSS
    jalankan_scraping()
    
    # 2. Export ke XML Blogger
    print("\n" + "=" * 50)
    print("MULAI EXPORT KE XML")
    print("=" * 50)
    generate_blogger_xml()
    
    print("\n[PROSES SELESAI]")
