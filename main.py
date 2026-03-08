import requests  # 이 줄이 빠져있어서 'name requests is not defined' 오류가 났을 거예요!
from bs4 import BeautifulSoup
import deepl
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# 셀레니움 관련
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client, Client

DEEPL_API_KEY = "a7aefc71-7412-4b5c-b39d-fed826a89d87:fx"
SHEET_ID = "1Yh19VUoXaTtk-4nYmoZRUyRlJ7QnUqZOSCUm-mUlyME"
JSON_FILE = "service_account_key.json"
OHASA_URL = "https://www.asahi.co.jp/ohaasa/week/horoscope/index.html" # 일본 오하아사 공식 페이지
SUPABASE_URL = "https://etbjpdagmpsjlldoojgw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0YmpwZGFnbXBzamxsZG9vamd3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5MzI2OTcsImV4cCI6MjA4ODUwODY5N30.m7cvuwpIKuzK4Ay103X5VqRy5Q0MOjHisQUq0S8Ct_o"

def scrape_ohasa():
    print(f"셀레니움 브라우저 가동 (M2 최적화): {OHASA_URL}")
    
    options = Options()
    options.add_argument("--headless") # 창 없이 실행
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(OHASA_URL)
        print("페이지 로딩 대기 중 (5초)...")
        time.sleep(5) 

        # 방법 1: 텍스트 덩어리 전체를 가져와서 '座'가 포함된 줄만 필터링
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = body_text.split('\n')
        
        fortune_list = []
        for line in lines:
            line = line.strip()
            # 일본 별자리명(좌)이 포함되고, 운세 내용(최소 10자 이상)이 있는 줄만 수집
            if '座' in line and len(line) > 10:
                fortune_list.append(line)

        # 방법 2: 만약 방법 1이 실패하면(0개면), p태그나 div태그를 직접 뒤짐
        if len(fortune_list) < 12:
            elements = driver.find_elements(By.CSS_SELECTOR, "div, p, li")
            for el in elements:
                txt = el.text.strip()
                if '座' in txt and len(txt) > 20:
                    fortune_list.append(txt.replace('\n', ' '))

        # 중복 제거 및 12개 확보
        final_data = []
        for item in fortune_list:
            if item not in final_data:
                final_data.append(item)
        
        final_data = final_data[:12]
        
        if not final_data:
            print("❌ 데이터를 찾지 못했습니다. 사이트 구조를 다시 확인해야 합니다.")
        else:
            print(f"✅ {len(final_data)}개의 운세 데이터를 찾았습니다!")
            
        return final_data

    except Exception as e:
        print(f"🌐 셀레니움 오류: {e}")
        return []
    finally:
        driver.quit()
    
# 2. 한국어로 번역 (Translator)
def translate_to_korean(text_list):
    if not text_list:
        return []
    
    print(f"총 {len(text_list)}개의 문장 번역 시작...")
    translator = deepl.Translator(DEEPL_API_KEY)
    
    # 리스트 전체를 한 번의 API 호출로 번역 (글자수 절약 및 속도 향상)
    results = translator.translate_text(text_list, target_lang="KO")
    
    return [r.text for r in results]

# 3. 구글 시트에 업데이트 (Storage)
def update_google_sheet(translated_data):
    print("구글 시트에 항목별로 저장 중...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1

    today = datetime.now().strftime("%Y-%m-%d")
    
    # 헤더가 없다면 추가 (최초 1회)
    if not sheet.get_all_values():
        sheet.append_row(["날짜", "운세내용"])

    # 데이터 저장
    for info in translated_data:
        sheet.append_row([today, info])
        
    print(f"✅ {today}자 운세 12건 업데이트 완료!")
    
    # 오늘 날짜와 함께 번역된 데이터 한 줄 추가
    today = datetime.now().strftime("%Y-%m-%d")
    sheet.append_row([today] + translated_data)
    print(f"{today} 데이터 업데이트 완료!")
    
def update_supabase(translated_data):
    print("Supabase에 데이터 업로드 중...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    for info in translated_data:
        data = {
            "date": today,
            "content": info
        }
        # 데이터를 Supabase 테이블에 삽입
        supabase.table("horoscopes").insert(data).execute()
        
    print("✅ Supabase 업데이트 완료!")

# --- 메인 실행 흐름 ---
if __name__ == "__main__":
    try:
        # 1단계: 수집
        raw_info = scrape_ohasa()
        if raw_info:
            # 2단계: 번역
            korean_info = translate_to_korean(raw_info)
            
            # 3단계: 저장
            update_google_sheet(korean_info)
            update_supabase(korean_info)     # 신규 Supabase 저장 추가
        else:
            print("데이터가 없어 작업을 중단합니다.")
        
    except Exception as e:
        print(f"오류 발생: {e}")