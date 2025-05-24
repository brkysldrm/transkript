import streamlit as st
import pdfplumber
import re
import pandas as pd

# Öğrenci bilgilerini çıkar
def parse_student_info(text):
    tc_no = re.search(r'T\.C\. Kimlik No\s*:\s*(\d{11})', text)
    ogr_no = re.search(r'Öğrenci No\s*:\s*(\d+)', text)
    adsoyad_raw = re.search(r'Adı Soyadı\s*:\s*(.*)', text)
    adsoyad = adsoyad_raw.group(1).split("Öğretim")[0].strip() if adsoyad_raw else "Bulunamadı"
    bolum_raw = re.search(r'Bölüm\s*/\s*Program\s*:\s*(.*)', text)
    bolum = bolum_raw.group(1).split("Öğretim")[0].strip() if bolum_raw else "Bulunamadı"
    return {
        'TC Kimlik No': tc_no.group(1) if tc_no else "Bulunamadı",
        'Öğrenci No': ogr_no.group(1) if ogr_no else "Bulunamadı",
        'Adı Soyadı': adsoyad,
        'Bölüm/Program': bolum
    }

# Dersleri PDF'ten çıkar
def parse_courses(text):
    dersler = []
    donemler = list(re.finditer(r'(\d+\.\s*\d{4}\s*-\s*\d{4}\s+(Güz|Bahar)\s+Dönemi)', text))
    for i, match in enumerate(donemler):
        start = match.end()
        end = donemler[i + 1].start() if i + 1 < len(donemler) else len(text)
        donem_text = text[start:end]

        # Satır temizliği
        donem_text_cleaned = ""
        for line in donem_text.splitlines():
            parts = re.findall(r'(\d*[A-ZÇĞİÖŞÜ]{3,}\d{5,7})', line)
            if len(parts) >= 2:
                second_code = parts[1]
                index = line.find(second_code)
                donem_text_cleaned += line[:index] + '\n' + line[index:] + '\n'
            else:
                donem_text_cleaned += line + '\n'
        donem_text = donem_text_cleaned

        # Ders regex'i
        ders_pattern = r'(\d*[A-ZÇĞİÖŞÜ]{3,}\d{5,7})\s+(.+?)\s+([A-F][\+\-]?|G\+|G\-)?\s+([\d,]*)\s+(\d+)'
        for match in re.findall(ders_pattern, donem_text):
            kod, ad, harf, katsayi, akts = match
            dersler.append({
                "Kodu": kod.strip(),
                "Ders Adı": ad.strip(),
                "Harf Notu": harf.strip() if harf else "",
                "Başarı Katsayısı": katsayi.replace(",", ".") if katsayi else "",
                "AKTS": int(akts)
            })
    return dersler

# Zorunlu ders kontrolü
def zorunlu_ders_kontrolu(df, zorunlu_dersler):
    df_lower = df.copy()
    df_lower["Ders Adı (küçük)"] = df_lower["Ders Adı"].str.lower()
    alinmamis, basarisiz = [], []
    for donem, dersler in zorunlu_dersler.items():
        for ders, akts in dersler.items():
            ders_lower = ders.lower()
            bulunan = df_lower[df_lower["Ders Adı (küçük)"].str.contains(ders_lower)]
            if bulunan.empty:
                alinmamis.append((donem, ders, akts))
            elif all(n == "F" for n in bulunan["Harf Notu"]):
                basarisiz.append((donem, ders, akts))
    return alinmamis, basarisiz

# Seçmeli ders kontrolü
def secmeli_ders_kontrolu(df, secmeli_sartlar):
    df_gecilen = df[df["Harf Notu"] != "F"]
    eksik = []
    for donem, detay in secmeli_sartlar.items():
        alinmis = []
        for ders, akts in detay["alternatif_dersler"].items():
            if any(ders.lower() in ad.lower() for ad in df_gecilen["Ders Adı"]):
                alinmis.append((ders, akts))
        if len(alinmis) < detay["secilecek_sayi"]:
            eksik.append({
                "donem": donem,
                "alinan": alinmis,
                "eksik_sayi": detay["secilecek_sayi"] - len(alinmis),
                "gerekli": detay["secilecek_sayi"],
                "alternatifler": detay["alternatif_dersler"]
            })
    return eksik

# 🎯 Zorunlu dersler
zorunlu_dersler = {
    "1. Sınıf Güz": {
        "ANATOMİ I": 4,
        "BİLGİ TEKNOLOJİLERİ VE ARAÇLARI I": 2,
        "FİZİK": 3,
        "TIBBİ BİYOLOJİ VE GENETİK": 4,
        "ODYOLOJİYE GİRİŞ VE ETİK": 5,
        "SAĞLIK HİZMETLERİNDE İLETİŞİM": 2,
        "ATATÜRK İLKELERİ VE İNKILAP TARİHİ I": 2,
        "İNGİLİZCE I": 4,
        "TÜRK DİLİ I": 2
    },
    "1. Sınıf Bahar": {
        "BİLGİ TEKNOLOJİLERİ VE ARAÇLARI II": 2,
        "TIBBİ İLKYARDIM": 2,
        "DAVRANIŞ BİLİMLERİ": 2,
        "FİZYOLOJİ": 4,
        "ODYOLOJİDE AKUSTİK VE FONETİK İLKELER": 4,
        "AKUSTİK FİZİK": 4,
        "İŞİTME, KONUŞMA VE DENGEDE YAPI VE İŞLEV": 3,
        "ATATÜRK İLKELERİ VE İNKILAP TARİHİ II": 2,
        "İNGİLİZCE II": 4,
        "TÜRK DİLİ II": 2
    },
    "2. Sınıf Güz": {
        "İNGİLİZCE III": 4,
        "MESLEKİ UYGULAMA I": 4,
        "TEMEL ODYOLOJİK TESTLER": 4,
        "VESTİBULER SİSTEM VE HASTALIKLARI": 4,
        "KULAK, BURUN VE BOĞAZ HASTALIKLARI": 4,
        "ODYOLOJİDE ENSTRÜMANTASYON VE KALİBRASYON": 3,
        "GENETİK VE GENETİK İŞİTME KAYIPLARI": 2,
        "İŞİTSEL ALGI SÜREÇLERİ": 3
    },
    "2. Sınıf Bahar": {
        "İNGİLİZCE IV": 4,
        "MESLEKİ UYGULAMA II": 4,
        "OBJEKTİF İŞİTME TESTLERİ": 3,
        "OBJEKTİF VESTİBULER TESTLER": 4,
        "PEDİATRİK ODYOLOJİK TESTLER": 4,
        "İŞİTSEL REHABİLİTASYON": 4,
        "İŞİTME CİHAZLARI I": 3,
        "İŞARET DİLİ II": 3,
        "İLETİŞİM BOZUKLUKLARINDA AİLE DANIŞMANLIĞI": 2,
        "MESLEKİ İNGİLİZCE VE TIBBİ TERMİNOLOJİ": 2
    },
    "3. Sınıf Güz": {
        "MESLEKİ UYGULAMA III": 4,
        "VESTİBULER  PATOLO. TANI. VE DEĞERLENDİRİLME": 4,
        "ODYOLOJİDE ÖZEL KONULAR": 4,
        "İŞİTME CİHAZLARI II": 4,
        "İŞİTSEL İMPLANTLAR I": 4,
        "GERİATRİK ODYOLOJİ": 2,
        "İLERİ ODYOLOJİK TEST TEKNİKLERİ": 4,
        "TİNNİTUS VE DEĞERLENDİRİLMESİ": 4,
        "EĞİTİM ODYOLOJİSİ": 3
    },
    "3. Sınıf Bahar": {
        "BİYOİSTATİSTİK": 2,
        "İŞİTME KAYBI VE KONUŞMA BOZUKLUKLARI": 2,
        "MESLEKİ UYGULAMA IV": 4,
        "ENDÜSTRİYEL ODYOLOJİ": 4,
        "VESTİBULER SİSTEMİN TEDAVİ VE REHABİLİTASYONU": 4,
        "OLGULARLA VESTİBULOKOKLEAR PATOLOJİLER": 3,
        "İŞİTSEL İMPLANTLAR II": 3,
        "BİLİMSEL ARAŞTIRMA YÖNTEMLERİNE GİRİŞ": 2
    },
    "4. Sınıf Güz": {
        "ELEKTİF UYGULAMA": 4,
        "KLİNİKTE EĞİTİM VE UYGULAMA I": 14,
        "ODYOLOJİ SEMİNER I": 4,
        "DENEYSEL ODYOLOJİ VE PROJE HAZIRLAMA I": 3,
        "İŞİTME CİHAZLI İŞİTSEL REHABİLİTASYON": 4
    },
    "4. Sınıf Bahar": {
        "KLİNİKTE EĞİTİM VE UYGULAMA II": 14,
        "ODYOLOJİ SEMİNER II": 4,
        "DENEYSEL ODYOLOJİ VE PROJE HAZIRLAMA II": 3,
        "İŞİTME ENG. BEBEK VE ÇOCUK. EĞİTSEL YAKLAŞIM": 3,
        "İŞİTME MERKEZLERİNDE UYGULAMA": 4
    }
}

# ✅ Seçmeli ders şartları
secmeli_sartlar = {
    "2. Sınıf Güz": {
        "alternatif_dersler": {
            "SES, NEFES VE ARTİKÜLASYON TEKNİKLERİ": 3,
            "BİLİMSEL OKURYAZARLIK": 3,
            "İŞARET DİLİ I": 3
        },
        "secilecek_sayi": 2
    },
    "3. Sınıf Bahar": {
        "alternatif_dersler": {
            "KULAK KALIPLARI": 2,
            "VÜCUT MEKANİĞİ VE POSTÜR": 2,
            "OYUN TEMELLİ BECERİ GELİŞTİRME": 2
        },
        "secilecek_sayi": 2
    },
    "4. Sınıf Güz": {
        "alternatif_dersler": {
            "ODYOLOJİYE SEKTÖREL BAKIŞ": 2,
            "İŞİTME KAYIP. MATERYAL VE PROG. HAZIRLAMA": 2
        },
        "secilecek_sayi": 1
    }
}

# 🎯 Streamlit arayüz
st.set_page_config(page_title="Transkript Analiz", layout="wide")
st.title("🎓 Transkript Analiz Programı")

uploaded_file = st.file_uploader("Transkript PDF dosyasını yükleyin", type="pdf")

if uploaded_file:
    with pdfplumber.open(uploaded_file) as pdf:
        all_text = '\n'.join([p.extract_text() for p in pdf.pages if p.extract_text()])

    info = parse_student_info(all_text)
    dersler = parse_courses(all_text)
    df = pd.DataFrame(dersler).drop_duplicates(subset=["Kodu", "Ders Adı"], keep="last")
    toplam_akts = df[df["Harf Notu"] != "F"]["AKTS"].sum()

    st.subheader("👤 Öğrenci Bilgileri")
    st.info(f"{info['Adı Soyadı']} - {info['Öğrenci No']} - {info['Bölüm/Program']} - TC: {info['TC Kimlik No']}")
    st.success(f"Toplam Geçilen AKTS: {toplam_akts}")

    st.subheader("📘 Alınan Dersler")
    st.dataframe(df)

    alinmamis, basarisiz = zorunlu_ders_kontrolu(df, zorunlu_dersler)
    secmeli_eksikler = secmeli_ders_kontrolu(df, secmeli_sartlar)

    if alinmamis:
        st.subheader("🟡 Alınmamış Zorunlu Dersler")
        for donem, ders, akts in alinmamis:
            st.warning(f"{donem} → {ders} ({akts} AKTS) dersi alınmamış.")

    if basarisiz:
        st.subheader("🔴 Başarısız Zorunlu Dersler")
        for donem, ders, akts in basarisiz:
            st.error(f"{donem} → {ders} ({akts} AKTS) dersi F ile başarısız.")

    if secmeli_eksikler:
        st.subheader("⚠️ Eksik Seçmeli Ders Koşulları")
        for item in secmeli_eksikler:
            st.warning(f"{item['donem']} → En az {item['gerekli']} seçmeli ders alınmalı. Eksik: {item['eksik_sayi']}")
            st.caption("Alternatifler:")
            for ad, akts in item["alternatifler"].items():
                st.caption(f"• {ad} ({akts} AKTS)")

    if not alinmamis and not basarisiz and not secmeli_eksikler:
        st.success("🎉 Tüm zorunlu ve seçmeli ders koşulları sağlanmış!")
