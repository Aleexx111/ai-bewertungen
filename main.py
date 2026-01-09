import streamlit as st
from google import genai
import pandas as pd
import time
import json

# --- PASSWORT SCHUTZ ---
def check_password():
    """Gibt True zurück, wenn das Passwort korrekt ist."""
    
    # Wir schauen, ob das Passwort schon eingegeben wurde
    if st.session_state.get('password_correct', False):
        return True

    # Eingabefeld anzeigen
    st.header("🔒 Login erforderlich")
    password_input = st.text_input("Bitte Passwort eingeben", type="password")
    
    if st.button("Anmelden"):
        # HIER DEIN PASSWORT FESTLEGEN (z.B. "Marketing2024")
        if password_input == "Marketing2024":
            st.session_state['password_correct'] = True
            st.rerun()  # App neu laden
        else:
            st.error("Falsches Passwort")
            
    return False

# Wenn das Passwort NICHT stimmt, brechen wir hier ab!
if not check_password():
    st.stop()

# --- KONFIGURATION ---
st.set_page_config(page_title="AI Shop Texter Pro", page_icon="🛍️", layout="wide")

# --- SEITENLEISTE ---
with st.sidebar:
    st.header("⚙️ Einstellungen")
    
    # 1. API KEY (aus Secrets oder Input)
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("API Key intern geladen 🔒")
    else:
        api_key = st.text_input("Dein Google API Key", type="password")
        if api_key:
            st.success("Key manuell eingegeben! ✅")
    
    st.divider()
    
    # 2. TONALITÄT (Angepasst)
    tonality = st.selectbox(
        "Zielgruppe / Tonalität",
        [
            "Tech-Enthusiast (Du) - Fachlich tief, kein Marketing-BlaBla", 
            "B2B / Systemhaus (Sie) - Seriös, lösungsbezogen", 
            "Standard E-Commerce - Ausgewogen"
        ]
    )
    
    # 3. BLACKLIST
    st.subheader("🚫 Blacklist")
    blacklist_input = st.text_area(
        "Verbotene Wörter:",
        placeholder="billig, Schnäppchen, Highlights im Detail, Monster",
        help="Diese Wörter werden strikt vermieden."
    )

# --- FUNKTIONEN ---
def get_gemini_response_json(product_data, style, blacklist):
    """
    v4.2: Keine Überschrift am Start, keine Labels, reiner Fließtext mit Absätzen.
    """
    if not api_key:
        return None
    
    try:
        client = genai.Client(api_key=api_key)
        
        blacklist_instruction = ""
        if blacklist:
            blacklist_instruction = f"VERBOTENE WÖRTER (Strengstens beachten!): {blacklist}"

        # Prompt Update: Verbot von Titeln im Text & Labels
        prompt = f"""
        Du bist ein Senior Technical Copywriter für PC-Hardware.
        
        INPUT DATEN:
        {product_data}
        
        ZIELGRUPPE & STIL: 
        {style}
        
        ANWEISUNGEN:
        1. STRUKTUR & LÄNGE:
           - Schreibe ZWEI klare Absätze.
           - Absatz 1: Einführung und Einordnung des Produkts.
           - Absatz 2: Technische Details und Features als FLIESSTEXT (verbinde die Fakten logisch).
           - Gesamtlänge: Fokuskategorie (GPU/CPU) ca. 300 Wörter, Zubehör ca. 80 Wörter.
        
        2. FORMATIERUNG (EXTREM WICHTIG):
           - START: Beginne DIREKT mit dem ersten Satz. Wiederhole NICHT den Produktnamen als Überschrift am Anfang!
           - KEINE Labels wie "Highlights:", "Beschreibung:", "Features:" oder ähnliches verwenden.
           - KEINE Bulletpoints, keine Listen.
           - Trenne die beiden Absätze durch das HTML-Tag <br><br>.
           - Nutze KEINE <h1>, <h2> Tags.
           - {blacklist_instruction}
        
        3. OUTPUT:
        Antworte NUR mit einem gültigen JSON-Objekt.
        
        {{
            "meta_title": "Optimierter SEO Titel (max 60 Zeichen)",
            "meta_description": "Klickstarke Beschreibung inkl. USP (max 155 Zeichen)",
            "keywords": "5-8 relevante Keywords, kommagetrennt",
            "product_description": "[Hier Absatz 1]<br><br>[Hier Absatz 2 mit den technischen Details]"
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', 
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        # JSON laden
        data = json.loads(response.text)
        
        # --- PYTHON NACHBEARBEITUNG (Sicherheitsnetz) ---
        if "product_description" in data:
            desc = data["product_description"]
            
            # 1. Überschriften Tags killen
            for tag in ["<h1>", "</h1>", "<h2>", "</h2>", "<h3>", "</h3>", "<strong>", "</strong>", "<b>", "</b>"]:
                desc = desc.replace(tag, "")
            
            # 2. Markdown killen
            desc = desc.replace("## ", "").replace("# ", "").replace("**", "")
            
            # 3. Das Wort "Highlights:" entfernen, falls die KI es doch schreibt
            desc = desc.replace("Highlights:", "").replace("Features:", "")
            
            # 4. Doppelte Zeilenumbrüche säubern (optional, aber sauberer)
            desc = desc.replace("<br> <br>", "<br><br>")
            
            # 5. Falls der Text mit <br> anfängt (wegen Löschung), weg damit
            while desc.startswith("<br>"):
                desc = desc[4:]
            
            data["product_description"] = desc.strip()
                
        return data
        
    except Exception as e:
        return {
            "meta_title": "Fehler",
            "meta_description": "Fehler",
            "keywords": "Fehler",
            "product_description": f"Fehler bei Generierung: {str(e)}"
        }
# --- UI HAUPTBEREICH ---
st.title("🛍️ AI Content Factory v4.0 (Pro)")
st.info("Neu: Automatische Erkennung von Fokuskategorien & Ausgabe in getrennten Spalten.")

tab1, tab2 = st.tabs(["📝 Einzel-Check", "🏭 CSV Massen-Verarbeitung"])

# --- TAB 1: EINZELNES PRODUKT ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Input")
        raw_specs = st.text_area("Technische Daten / Name:", height=150, placeholder="ASUS ROG Strix GeForce RTX 4090...")
        raw_sku = st.text_input("SKU / Herstellernummer (optional):")
        raw_ean = st.text_input("EAN (optional):")
        
        # Input zusammenbauen
        combined_input = f"Specs: {raw_specs} | SKU: {raw_sku} | EAN: {raw_ean}"
        
        generate_btn = st.button("Analysieren & Generieren 🚀", type="primary")

    with col2:
        st.subheader("Vorschau")
        if generate_btn and raw_specs:
            with st.spinner('Analysiere Produkttyp und schreibe...'):
                data = get_gemini_response_json(combined_input, tonality, blacklist_input)
                
                if data:
                    st.caption("Meta Title:")
                    st.code(data.get("meta_title"), language="text")
                    
                    st.caption("Meta Description:")
                    st.code(data.get("meta_description"), language="text")
                    
                    st.caption("Produkttext:")
                    st.markdown(data.get("product_description"))
                else:
                    st.error("Fehler bei der API Anfrage.")

# --- TAB 2: MASSENVERARBEITUNG (CSV) ---
with tab2:
    st.subheader("CSV Import")
    
    col_upload1, col_upload2 = st.columns(2)
    with col_upload1:
        csv_sep = st.selectbox(
            "Trennzeichen",
            ["; (Semikolon - Standard)", ", (Komma)"],
            key="csv_sep_tab2"
        )
        selected_sep = csv_sep[0]
        
    st.markdown("""
    **Anleitung:**
    Die CSV sollte idealerweise folgende Spalten haben (Groß/Kleinschreibung egal):
    * `specs` oder `name` (Pflicht)
    * `sku` oder `herstellernummer` (Optional)
    * `ean` (Optional)
    """)
    
    uploaded_file = st.file_uploader("CSV Datei hier ablegen", type=["csv"])
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file, sep=selected_sep, dtype=str) # Alles als Text lesen
            st.write("Erkannte Daten (erste 3 Zeilen):", df.head(3))
            
            # Spalten suchen (flexibel)
            spec_col = next((c for c in df.columns if c.lower() in ['specs', 'name', 'titel', 'bezeichnung']), None)
            sku_col = next((c for c in df.columns if c.lower() in ['sku', 'herstellernummer', 'mpn', 'artnr']), None)
            ean_col = next((c for c in df.columns if c.lower() in ['ean', 'barcode']), None)
            
            if not spec_col:
                st.error("❌ Keine Spalte für Produktnamen/Specs gefunden! Bitte nenne eine Spalte 'specs' oder 'name'.")
            else:
                st.success(f"✅ Haupt-Spalte: '{spec_col}' | SKU: {'✅ '+sku_col if sku_col else '❌'} | EAN: {'✅ '+ean_col if ean_col else '❌'}")
                
                if st.button("Start Massenverarbeitung"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # Neue Listen für die Ergebnisse
                    res_titles = []
                    res_metas = []
                    res_keywords = []
                    res_bodies = []
                    
                    total = len(df)
                    
                    for index, row in df.iterrows():
                        status_text.text(f"Produkt {index + 1}/{total}: {str(row[spec_col])[:30]}...")
                        
                        # Daten zusammenbauen
                        input_str = f"Produkt: {row[spec_col]}"
                        if sku_col and pd.notna(row[sku_col]):
                            input_str += f" | SKU: {row[sku_col]}"
                        if ean_col and pd.notna(row[ean_col]):
                            input_str += f" | EAN: {row[ean_col]}"
                            
                        # KI Aufruf
                        json_res = get_gemini_response_json(input_str, tonality, blacklist_input)
                        
                        # Ergebnisse in Listen speichern
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
                        time.sleep(1) # Schutz vor Rate Limits
                    
                    # Alles in den DataFrame schreiben (neue Spalten)
                    df['SEO_Meta_Title'] = res_titles
                    df['SEO_Meta_Description'] = res_metas
                    df['SEO_Keywords'] = res_keywords
                    df['Shop_Beschreibung_HTML'] = res_bodies
                    
                    st.success("✅ Fertig! Alle Texte generiert.")
                    
                    # Export
                    csv_export = df.to_csv(index=False, sep=';').encode('utf-8-sig')
                    st.download_button(
                        label="📥 Fertige Excel-CSV herunterladen",
                        data=csv_export,
                        file_name="fertige_produkte_v4.csv",
                        mime="text/csv",
                    )
                    
        except Exception as e:
            st.error(f"Kritischer Fehler: {e}")