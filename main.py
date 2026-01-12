import streamlit as st
from google import genai
import pandas as pd
import time
import json
import io
import re  # NEU: Für die gründliche Text-Reinigung

# --- KONFIGURATION ---
st.set_page_config(page_title="AI Shop Texter Pro", page_icon="🛍️", layout="wide")

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("API Key intern geladen 🔒")
    else:
        api_key = st.text_input("Dein Google API Key", type="password")
        if api_key:
            st.success("Key manuell eingegeben! ✅")
    
    st.divider()
    
    tonality = st.selectbox(
        "Zielgruppe / Tonalität",
        [
            "Tech-Enthusiast (Du) - Fachlich tief, kein Marketing-BlaBla", 
            "B2B / Systemhaus (Sie) - Seriös, lösungsbezogen", 
            "Standard E-Commerce - Ausgewogen"
        ]
    )
    
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
    
    blacklist_input = st.text_area(
        "Verbotene Wörter (automatisch geladen):",
        value=default_blacklist,
        height=300,
        help="Diese Wörter werden strikt vermieden."
    )

# --- FUNKTIONEN ---
def clean_json_string(text):
    """
    Hilfsfunktion: Entfernt Markdown und unsichtbare Steuerzeichen, die JSON kaputt machen.
    """
    # 1. Markdown Code-Blöcke entfernen (```json ... ```)
    text = text.replace("```json", "").replace("```", "")
    
    # 2. Unsichtbare Steuerzeichen entfernen (außer normalen Zeilenumbrüchen)
    # Das hier löscht Tabulatoren und andere seltsame ASCII-Zeichen, die den Fehler 909 auslösen
    text = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    return text.strip()

def get_gemini_response_json(product_data, style, blacklist):
    """
    v5.4: Robustes JSON-Parsing mit Fehler-Korrektur (Strict=False).
    """
    if not api_key:
        return None
    
    try:
        client = genai.Client(api_key=api_key)
        
        blacklist_instruction = ""
        if blacklist:
            blacklist_instruction = f"VERBOTENE WÖRTER (Strengstens beachten!): {blacklist}"

        prompt = f"""
        Du bist ein Senior Technical Copywriter für PC-Hardware.
        
        INPUT DATEN:
        {product_data}
        
        ZIELGRUPPE & STIL: 
        {style}
        
        ANWEISUNGEN:
        1. STRUKTUR & LÄNGE:
           - Schreibe ZWEI klare Absätze.
           - Absatz 1: Einführung.
           - Absatz 2: Technische Details als FLIESSTEXT.
           - Gesamtlänge: Fokuskategorie (GPU/CPU) ca. 300 Wörter, Zubehör ca. 80 Wörter.
        
        2. SPRACHE & WORTSCHATZ (CRITICAL):
           - "gewährleistet" und "garantiert" sind VERBOTEN -> Nutze "sorgt für", "stellt sicher".
           - {blacklist_instruction}
        
        3. FORMATIERUNG (CLEAN TEXT):
           - Beginne DIREKT mit dem Text.
           - KEINE Labels, KEINE Listen, KEINE HTML Tags.
           - WICHTIG: Erzeuge valides JSON. Keine Steuerzeichen (Tabs) in den Strings.
        
        4. OUTPUT:
        Antworte NUR mit einem gültigen JSON-Objekt.
        
        {{
            "meta_title": "Optimierter SEO Titel (max 60 Zeichen)",
            "meta_description": "Klickstarke Beschreibung inkl. USP (max 155 Zeichen)",
            "keywords": "5-8 relevante Keywords, kommagetrennt",
            "product_description": "[Absatz 1]\\n\\n[Absatz 2]"
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', 
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        raw_text = response.text
        
        # --- SICHERES PARSEN ---
        try:
            # Versuch 1: Direktes Parsen (mit strict=False, das erlaubt oft Steuerzeichen)
            data = json.loads(clean_json_string(raw_text), strict=False)
        except json.JSONDecodeError:
            # Versuch 2: Wenn das schiefgeht, versuchen wir, harte Zeilenumbrüche zu reparieren
            # Manchmal macht die KI echte Zeilenumbrüche statt \n in den String
            cleaned_text = clean_json_string(raw_text).replace('\n', '\\n')
            try:
                data = json.loads(cleaned_text, strict=False)
            except:
                # Fallback: Wenn alles scheitert, geben wir den Roh-Text zurück, damit nichts verloren geht
                return {
                    "meta_title": "JSON Fehler",
                    "meta_description": "Bitte Artikel erneut prüfen",
                    "keywords": "",
                    "product_description": f"Fehler beim Lesen der KI-Antwort. Rohdaten: {raw_text[:500]}..."
                }

        # --- PYTHON CLEANER v5.3 Logik ---
        if "product_description" in data:
            desc = data["product_description"]
            
            # HTML Cleanup
            desc = desc.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
            for tag in ["<h1>", "</h1>", "<h2>", "</h2>", "<h3>", "</h3>", "<strong>", "</strong>", "<b>", "</b>", "<i>", "</i>"]:
                desc = desc.replace(tag, "")
            desc = desc.replace("## ", "").replace("# ", "").replace("**", "")
            desc = desc.replace("Highlights:", "").replace("Features:", "").replace("Beschreibung:", "")
            
            # Anti-Gewährleistet & Garantieren
            desc = desc.replace("gewährleistet", "sorgt für").replace("Gewährleistet", "Sorgt für").replace("gewährleisten", "sorgen für")
            desc = desc.replace("garantiert", "stellt sicher").replace("Garantiert", "Stellt sicher").replace("garantieren", "stellen sicher")
            desc = desc.replace("stellt sicher für", "ermöglicht")
            
            while "\n\n\n" in desc:
                desc = desc.replace("\n\n\n", "\n\n")
            
            data["product_description"] = desc.strip()
            
            if "meta_description" in data:
                m_desc = data["meta_description"]
                m_desc = m_desc.replace("gewährleistet", "bietet").replace("garantiert", "ermöglicht")
                data["meta_description"] = m_desc
                
        return data
        
    except Exception as e:
        return {
            "meta_title": "Fehler",
            "meta_description": "Fehler",
            "keywords": "Fehler",
            "product_description": f"Fehler bei Generierung: {str(e)}"
        }

# --- UI HAUPTBEREICH ---
st.title("🛍️ AI Content Factory v5.4")
st.info("Update: Sicherheits-Fix für 'Invalid Control Character' Fehler.")

tab1, tab2 = st.tabs(["📝 Einzel-Check", "🏭 CSV Massen-Verarbeitung"])

# --- TAB 1: EINZELNES PRODUKT ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Input")
        raw_specs = st.text_area("Technische Daten / Name:", height=150, placeholder="ASUS ROG Strix GeForce RTX 4090...")
        raw_sku = st.text_input("SKU / Herstellernummer (optional):")
        raw_ean = st.text_input("EAN (optional):")
        
        combined_input = f"Specs: {raw_specs} | SKU: {raw_sku} | EAN: {raw_ean}"
        generate_btn = st.button("Analysieren & Generieren 🚀", type="primary")

    with col2:
        st.subheader("Vorschau")
        if generate_btn and raw_specs:
            with st.spinner('KI schreibt...'):
                data = get_gemini_response_json(combined_input, tonality, blacklist_input)
                
                if data:
                    st.caption("Meta Title:")
                    st.code(data.get("meta_title"), language="text")
                    st.caption("Produkttext (Clean):")
                    st.text(data.get("product_description"))
                else:
                    st.error("Fehler bei der API Anfrage.")

# --- TAB 2: EXCEL EXPORT ---
with tab2:
    st.subheader("CSV Import -> Excel Export")
    
    col_upload1, col_upload2 = st.columns(2)
    with col_upload1:
        csv_sep = st.selectbox(
            "Trennzeichen der Input-Datei",
            ["; (Semikolon - Standard)", ", (Komma)"],
            key="csv_sep_tab2"
        )
        selected_sep = csv_sep[0]
        
    st.markdown("Lade deine CSV hoch. Du bekommst eine saubere Excel-Datei zurück.")
    
    uploaded_file = st.file_uploader("CSV Datei hier ablegen", type=["csv"])
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file, sep=selected_sep, dtype=str)
            st.write("Erkannte Daten:", df.head(3))
            
            spec_col = next((c for c in df.columns if c.lower() in ['specs', 'name', 'titel', 'bezeichnung']), None)
            sku_col = next((c for c in df.columns if c.lower() in ['sku', 'herstellernummer', 'mpn', 'artnr']), None)
            ean_col = next((c for c in df.columns if c.lower() in ['ean', 'barcode']), None)
            
            if not spec_col:
                st.error("❌ Keine Spalte für Produktnamen/Specs gefunden!")
            else:
                st.success(f"✅ Haupt-Spalte: '{spec_col}'")
                
                if st.button("Start Massenverarbeitung"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    res_titles = []
                    res_metas = []
                    res_keywords = []
                    res_bodies = []
                    
                    total = len(df)
                    
                    for index, row in df.iterrows():
                        status_text.text(f"Produkt {index + 1}/{total}...")
                        
                        input_str = f"Produkt: {row[spec_col]}"
                        if sku_col and pd.notna(row[sku_col]):
                            input_str += f" | SKU: {row[sku_col]}"
                        if ean_col and pd.notna(row[ean_col]):
                            input_str += f" | EAN: {row[ean_col]}"
                            
                        json_res = get_gemini_response_json(input_str, tonality, blacklist_input)
                        
                        if json_res:
                            res_titles.append(json_res.get("meta_title", ""))
                            res_metas.append(json_res.get("meta_description", ""))
                            res_keywords.append(json_res.get("keywords", ""))
                            res_bodies.append(json_res.get("product_description", ""))
                        else:
                            res_titles.append("Fehler")
                            res_metas.append("")
                            res_keywords.append("")
                            res_bodies.append("")
                        
                        progress_bar.progress((index + 1) / total)
                        time.sleep(1)
                    
                    df['SEO_Meta_Title'] = res_titles
                    df['SEO_Meta_Description'] = res_metas
                    df['SEO_Keywords'] = res_keywords
                    df['Shop_Beschreibung_Clean'] = res_bodies
                    
                    st.success("✅ Fertig!")
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Produktdaten')
                        
                    st.download_button(
                        label="📥 Fertige Excel (.xlsx) herunterladen",
                        data=buffer.getvalue(),
                        file_name="fertige_produkte_v5_4.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
        except Exception as e:
            st.error(f"Kritischer Fehler: {e}")