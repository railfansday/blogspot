import sqlite3
import os
import html as html_mod
from datetime import datetime
from pathlib import Path

# ==========================================================================
# KONFIGURASI PATH (DIPERBAIKI)
# ==========================================================================
BASE_DIR = Path(__file__).parent.resolve()

# ✅ FIX: DB_PATH sekarang berupa objek Path (bukan string) agar .parent berfungsi
DB_PATH = BASE_DIR / "database_hasil5" / "database.sqlite"

AUTHOR_NAME = "Admin"

def esc(text):
    """Escape teks untuk XML"""
    if not text:
        return ""
    return html_mod.escape(str(text))

def ensure_database():
    """✅ FIX: Buat database kosong jika tidak ditemukan agar tidak error"""
    # Karena DB_PATH sudah Path, .parent dan .mkdir() bisa digunakan
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    if not DB_PATH.exists():
        print(f"⚠️ Database tidak ditemukan di {DB_PATH}")
        print("   Membuat database kosong...")
        # ✅ FIX: sqlite3.connect() membutuhkan string, jadi kita bungkus dengan str()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artikel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE, judul TEXT, konten TEXT, gambar TEXT,
                tanggal_publish TEXT, tanggal_update TEXT
            )
        """)
        conn.commit()
        conn.close()
        print("   ✅ Database kosong berhasil dibuat.\n")

def generate_blogger_xml():
    # Panggil fungsi pembuat database
    ensure_database()

    print("[*] Membaca database...")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT id, judul, konten, gambar, tanggal_publish, link FROM artikel ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("⚠️ Tidak ada artikel di dalam database. File XML akan dibuat kosong.")
    else:
        print(f"[*] Memproses {len(rows)} artikel menjadi format XML Blogger...")

    today_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000+07:00')
    
    # Header XML Blogger (Atom Feed)
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:app="http://www.w3.org/2007/app" xmlns:thr="http://purl.org/syndication/thread/1.0" xmlns:georss="http://www.georss.org/georss">',
        '  <title type="text">Blogger Export</title>',
        f'  <updated>{today_iso}</updated>',
        '  <generator version="7.00">Blogger</generator>',
        '  <author>',
        f'    <name>{esc(AUTHOR_NAME)}</name>',
        '    <email>noreply@blogger.com</email>',
        '  </author>',
    ]

    # Loop setiap artikel menjadi <entry>
    for row in rows:
        artikel_id, judul, konten, gambar, tanggal_publish, link = row
        
        if tanggal_publish:
            try:
                dt = datetime.fromisoformat(tanggal_publish.replace('Z', '+00:00'))
                published_iso = dt.strftime('%Y-%m-%dT%H:%M:%S.000+07:00')
            except:
                published_iso = today_iso
        else:
            published_iso = today_iso

        # Konten di-escape agar tag <script> iklan tidak merusak XML
        safe_content = esc(konten)
        
        post_id = f"tag:blogger.com,1999:blog-{artikel_id}.post-{artikel_id}"
        post_url = f"https://dummy.blogspot.com/{artikel_id}.html"

        xml_parts.append('  <entry>')
        xml_parts.append(f'    <id>{post_id}</id>')
        xml_parts.append(f'    <published>{published_iso}</published>')
        xml_parts.append(f'    <updated>{published_iso}</updated>')
        xml_parts.append('    <app:control xmlns:app="http://www.w3.org/2007/app"><app:draft>no</app:draft></app:control>')
        xml_parts.append(f'    <title type="text">{esc(judul)}</title>')
        xml_parts.append(f'    <content type="html">{safe_content}</content>')
        xml_parts.append(f'    <link rel="alternate" type="text/html" href="{post_url}" title="{esc(judul)}"/>')
        xml_parts.append('    <author>')
        xml_parts.append(f'      <name>{esc(AUTHOR_NAME)}</name>')
        xml_parts.append('      <email>noreply@blogger.com</email>')
        xml_parts.append('    </author>')
        xml_parts.append('  </entry>')

    xml_parts.append('</feed>')

    # Simpan ke file
    output_filename = "export_blogger.xml"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_parts))

    print(f"\n[✅ SELESAI] File XML berhasil dibuat: {output_filename}")
    print(f"Total artikel siap diimpor: {len(rows)}")
    print("\n📌 Cara Impor ke Blogger:")
    print("1. Buka Blogger -> Setelan -> Impor konten")
    print("2. Pilih file 'export_blogger.xml'")
    print("3. Tunggu proses selesai, lalu cek postingan Anda.")

if __name__ == "__main__":
    generate_blogger_xml()
