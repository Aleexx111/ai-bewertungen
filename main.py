import streamlit as st
from google import genai
import pandas as pd
import time
import json
import io
import re

# --- KONFIGURATION ---
st.set_page_config(page_title="AI Shop Texter Pro", page_icon="🛍️", layout="wide")

# --- PASSWORT SCHUTZ ---
def check_password():
    if st.session_state.get('password_correct', False):
        return True
    
    st.header("🔒 Login erforderlich")
    password_input = st.text_input("Bitte Passwort eingeben", type="password")
    if st.button("Anmelden"):
        if password_input == "Marketing2024":
            st.session_state['password_correct'] = True
            st.rerun()
        else:
            st.error("Falsches Passwort")
    return False

if not check_password():
    st.stop()

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("API Key intern geladen 🔒")
    else:
        api_key = st.text_input("Dein Google API Key", type="password")
        if api_key: st.success("Key manuell eingegeben! ✅")
    
    st.divider()
    tonality = st.selectbox("Zielgruppe / Tonalität", [
        "Tech-Enthusiast (Du) - Fachlich tief, kein Marketing-BlaBla", 
        "B2B / Systemhaus (Sie) - Seriös, lösungsbezogen", 
        "Standard E-Commerce - Ausgewogen"
    ])
    
    # BLACKLIST (Output Filter)
    default_blacklist = (
        "garantie, guaranty, guarantee, warrant, warrant, support, warranty, warranties, "
        "teflon, lycra, plexiglas, plexigalax, pu-leder, pu leder, puleder, textilleder, "
        "swarovski, swarowski, svarovski, svarowski, swarovsky, swarowsky, svarovsky, svarowsky, "
        "farovski, farofski, varofski, farovsky, farofsky, varofsky, warofski, farowski, warofsky, farowsky, "
        "fusionschuko, velcro, garantiert, garantieren, warantyservice, "
        "Gewährleistung, gewährleistet, gewährleistest, gewährleisten, garantiere, garantierst, "
        "Herstellergarantie, lebenslange Garantie, Herstellerunterstützung, Hersteller-Unterstützung, "
        "Edelstahl rostfrei, Rostfreier Edelstahl, Highlights im Detail"
    )
    blacklist_input = st.text_area("Verbotene Wörter (Output):", value=default_blacklist, height=200)

# --- FUNKTIONEN ---

def clean_input_pre_processing(text):
    """
    NEU: Reinigt den Input-Namen VOR der KI.
    Entfernt kryptische Kürzel am Anfang (z.B. "SER ", "RP HDSA "), 
    behält aber bekannte Marken.
    """
    if not isinstance(text, str): return str(text)
    
    # Liste von Marken, die NICHT gelöscht werden dürfen, auch wenn sie großgeschrieben sind
    BRAND_WHITELIST = [
        "ASUS", "AMD", "INTEL", "MSI", "HP", "DELL", "LENOVO", "ACER", "APPLE", 
        "SAMSUNG", "LG", "SONY", "EVGA", "PNY", "PALIT", "ZOTAC", "XFX", "NZXT",
        "CORSAIR", "RAZER", "LOGITECH", "ROCCAT", "STEELSERIES", "BENQ", "AOC",
        "BE QUIET", "NOCTUA", "SEASONIC", "CRUCIAL", "KINGSTON", "WESTERN DIGITAL", "WD", "SEAGATE",
        "SANDISK", "ADATA", "PATRIOT", "G.SKILL", "TEAMGROUP", "HYPERX", "SAPPHIRE",
        "POWERCOLOR", "INNO3D", "GAINWARD", "KFA2", "GIGABYTE", "ASROCK", "BIOSTAR", "TERRA"
    ]
    
    words = text.split()
    if not words: return text
    
    # Wir prüfen das erste Wort (und optional das zweite)
    # Logik: Ist es komplett Großgeschrieben? Hat es 2-6 Buchstaben? Ist es NICHT in der Whitelist? -> Weg damit!
    
    # Schleife, falls mehrere Kürzel nacheinander kommen (z.B. "RP HDSA Name")
    while len(words) > 0:
        first_word = words[0]
        # Bereinigen von Sonderzeichen für den Check (z.B. "SER:" -> "SER")
        clean_word = re.sub(r'[^A-Z0-9]', '', first_word)
        
        # Check: Ist es ein Code? (Alles Großbuchstaben, 2-7 Zeichen lang)
        is_code = first_word.isupper() and 2 <= len(clean_word) <= 7
        
        # Check: Ist es eine Marke?
        is_brand = clean_word in BRAND_WHITELIST
        
        if is_code and not is_brand:
            # Es ist ein Code (z.B. "SER") und keine Marke -> Löschen
            words.pop(0) 
        else:
            # Es ist kein Code oder eine Marke -> Wir sind fertig mit Löschen
            break
            
    return " ".join(words)

def clean_json_string(text):
    text = text.replace("```json", "").replace("```", "")
    text = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    return text.strip()

def clean_product_text_output(text):
    """Reinigung des FERTIGEN Textes (Output)"""
    if not text: return ""
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    for tag in ["<h1>", "</h1>", "<h2>", "</h2>", "<h3>", "</h3>", "<strong>", "</strong>", "<b>", "</b>", "<i>", "</i>"]:
        text = text.replace(tag, "")
    text = text.replace("## ", "").replace("# ", "").replace("**", "")
    text = text.replace("Highlights:", "").replace("Features:", "").replace("Beschreibung:", "")
    
    # Wort-Filter
    text = text.replace("gewährleistet", "sorgt für").replace("Gewährleistet", "Sorgt für").replace("gewährleisten", "sorgen für")
    text = text.replace("garantiert", "stellt sicher").replace("Garantiert", "Stellt sicher").replace("garantieren", "stellen sicher")
    text = text.replace("stellt sicher für", "ermöglicht")
    
    while "\n\n\n" in text: text = text.replace("\n\n\n", "\n\n")
    return text.strip()

def get_gemini_response_json(product_data, style, blacklist):
    client = genai.Client(api_key=api_key)
    blacklist_instruction = f"VERBOTENE WÖRTER: {blacklist}" if blacklist else ""

    prompt = f"""
    Du bist ein Senior Technical Copywriter für PC-Hardware.
    INPUT: {product_data}
    STIL: {style}
    ANWEISUNGEN:
    1. ANALYSE: Ignoriere kryptische Abkürzungen am Anfang, falls noch vorhanden.
    2. STRUKTUR: 2 Absätze (Intro + Tech-Details als Fließtext). Länge: GPU/CPU ~300 Wörter, Zubehör ~80.
    3. NO-GOS: Keine "gewährleistet"/"garantiert". {blacklist_instruction}
    4. FORMAT: Kein HTML, keine Labels, Valides JSON.
    OUTPUT JSON: {{ "meta_title": "...", "meta_description": "...", "keywords": "...", "product_description": "..." }}
    """
    
    response = client.models.generate_content(
        model='gemini-2.0-flash-exp', 
        contents=prompt,
        config={'response_mime_type': 'application/json'}
    )
    
    try:
        data = json.loads(clean_json_string(response.text), strict=False)
    except:
        cleaned_text = clean_json_string(response.text).replace('\n', '\\n')
        data = json.loads(cleaned_text, strict=False)

    if "product_description" in data:
        data["product_description"] = clean_product_text_output(data["product_description"])
    if "meta_description" in data:
        data["meta_description"] = data["meta_description"].replace("gewährleistet", "bietet").replace("garantiert", "ermöglicht")
            
    return data

def generate_with_retry(input_str, tonality, blacklist, status_placeholder):
    max_retries = 3
    retry_delay = 60 
    
    for attempt in range(max_retries):
        try:
            return get_gemini_response_json(input_str, tonality, blacklist)
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "429" in str(e) or "Resource exhausted" in error_msg:
                if attempt < max_retries - 1:
                    status_placeholder.warning(f"⏳ Rate Limit (429). Warte {retry_delay} Sek. und versuche es erneut...")
                    time.sleep(retry_delay)
                    status_placeholder.info("🔄 Neuer Versuch...")
                    continue 
            
            return {
                "meta_title": "Fehler",
                "meta_description": "Fehler",
                "keywords": "Fehler",
                "product_description": f"Fehler: {error_msg}"
            }

# --- UI HAUPTBEREICH ---
st.title("🛍️ AI Content Factory v6.1 (Clean Input)")
st.info("Neu: Input-Cleaner entfernt 'SER', 'RP HDSA' etc. VOR der Generierung.")

tab1, tab2 = st.tabs(["📝 Einzel-Check", "🏭 CSV Massen-Verarbeitung"])

# --- TAB 1 ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Input")
        raw_specs = st.text_area("Technische Daten / Name:", height=150, placeholder="SER Terra MINISERVER G6...")
        raw_sku = st.text_input("SKU:")
        raw_ean = st.text_input("EAN:")
        
        # Test-Anzeige für den User
        if raw_specs:
            cleaned_preview = clean_input_pre_processing(raw_specs)
            if cleaned_preview != raw_specs:
                st.caption(f"✨ Bereinigter Input für KI: **{cleaned_preview}**")
        
        generate_btn = st.button("Start 🚀", type="primary")

    with col2:
        st.subheader("Vorschau")
        if generate_btn and raw_specs:
            # Input reinigen
            clean_specs = clean_input_pre_processing(raw_specs)
            combined_input = f"Specs: {clean_specs} | SKU: {raw_sku} | EAN: {raw_ean}"
            
            with st.spinner('KI schreibt...'):
                data = get_gemini_response_json(combined_input, tonality, blacklist_input)
                if data:
                    st.code(data.get("meta_title"), language="text")
                    st.text(data.get("product_description"))
                else: st.error("Fehler.")

# --- TAB 2 ---
with tab2:
    st.subheader("Excel Export mit Smart-Bremse & Input-Wäsche")
    
    col_upload1, col_upload2 = st.columns(2)
    with col_upload1:
        csv_sep = st.selectbox("Trennzeichen", ["; (Semikolon)", ", (Komma)"], key="sep2")
        selected_sep = csv_sep[0]
        
    uploaded_file = st.file_uploader("CSV Datei", type=["csv"])
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file, sep=selected_sep, dtype=str)
            st.write(f"Geladen: {len(df)} Produkte")
            
            spec_col = next((c for c in df.columns if c.lower() in ['specs', 'name', 'titel', 'bezeichnung']), None)
            sku_col = next((c for c in df.columns if c.lower() in ['sku', 'herstellernummer', 'mpn', 'artnr']), None)
            ean_col = next((c for c in df.columns if c.lower() in ['ean', 'barcode']), None)
            
            if spec_col:
                if st.button("Start Massenverarbeitung"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    results = {"title": [], "meta": [], "keys": [], "desc": []}
                    total = len(df)
                    
                    for index, row in df.iterrows():
                        # 1. INPUT REINIGUNG (Das ist neu!)
                        original_name = str(row[spec_col])
                        clean_name = clean_input_pre_processing(original_name)
                        
                        status_text.text(f"Produkt {index + 1}/{total}: {clean_name[:40]}...")
                        
                        input_str = f"Produkt: {clean_name}"
                        if sku_col and pd.notna(row[sku_col]): input_str += f" | SKU: {row[sku_col]}"
                        if ean_col and pd.notna(row[ean_col]): input_str += f" | EAN: {row[ean_col]}"
                        
                        json_res = generate_with_retry(input_str, tonality, blacklist_input, status_text)
                        
                        results["title"].append(json_res.get("meta_title", ""))
                        results["meta"].append(json_res.get("meta_description", ""))
                        results["keys"].append(json_res.get("keywords", ""))
                        results["desc"].append(json_res.get("product_description", ""))
                        
                        progress_bar.progress((index + 1) / total)
                        
                        # Rate Limit Pausen
                        time.sleep(5)
                        if (index + 1) % 5 == 0 and (index + 1) < total:
                            status_text.info(f"☕ Sicherheits-Pause nach 5 Artikeln...")
                            time.sleep(10)

                    df['SEO_Meta_Title'] = results["title"]
                    df['SEO_Meta_Description'] = results["meta"]
                    df['SEO_Keywords'] = results["keys"]
                    df['Shop_Beschreibung_Clean'] = results["desc"]
                    
                    st.success("✅ Fertig!")
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Produktdaten')
                        
                    st.download_button(
                        label="📥 Excel herunterladen (.xlsx)",
                        data=buffer.getvalue(),
                        file_name="fertige_produkte_v6_1.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.error("Spalte 'Name'/'Specs' fehlt.")
                    
        except Exception as e:
            st.error(f"Fehler: {e}")