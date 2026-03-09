import os
import time
import re
from datetime import datetime, timedelta, timezone
import deepl
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client, Client

DEEPL_API_KEY = "a7aefc71-7412-4b5c-b39d-fed826a89d87:fx"
#SHEET_ID = "1Yh19VUoXaTtk-4nYmoZRUyRlJ7QnUqZOSCUm-mUlyME"
#JSON_FILE = "service_account_key.json"
REAL_OHAASA_URL = "https://www.asahi.co.jp/ohaasa/week/horoscope/"
SUPABASE_URL = "https://xhnebazckldsasyswtoa.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhobmViYXpja2xkc2FzeXN3dG9hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NDM3NjAsImV4cCI6MjA4ODUxOTc2MH0.8T7pXochvff7GxvOXjoFx9TbdlG2TZLm2oSSPnrCtdc"

def scrape_real_ohaasa():
    print(f"1단계: 진짜 오하아사 크롤링 중... {REAL_OHAASA_URL}")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(REAL_OHAASA_URL)
        time.sleep(3) 
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # 💡 [핵심] 정규식으로 '1 いて座(사수자리)...' 패턴을 강력하게 추출
        pattern = r'(\d{1,2})\s+([ぁ-んァ-ヶー一-龠]+座)\s+(.*?)(?=(?:\d{1,2}\s+[ぁ-んァ-ヶー一-龠]+座)|$)'
        matches = re.findall(pattern, page_text, re.DOTALL)
        
        horoscope_data = []
        for match in matches:
            rank = int(match[0].strip())
            sign_name = match[1].strip()
            body_text = match[2].strip()
            
            # 줄바꿈으로 문장 분리
            lines = [line.strip() for line in re.split(r'\n', body_text) if line.strip()]
            
            if len(lines) >= 2:
                lucky_action = lines[-1] # 마지막 줄이 '말차 디저트 먹기' 같은 럭키 미션
                content = " ".join(lines[:-1])
            else:
                lucky_action = "확인필요"
                content = body_text
                
            horoscope_data.append({
                "rank": rank,
                "sign_name_jp": sign_name,
                "content_jp": content,
                "lucky_action_jp": lucky_action
            })
            
        print(f"최종 수집된 별자리 개수: {len(horoscope_data)}개")
        return horoscope_data

    except Exception as e:
        print(f"🌐 크롤링 전체 오류 발생: {e}")
        return []
    finally:
        driver.quit()

def translate_and_process(raw_data):
    if not raw_data:
        return []

    print("2단계: DeepL 번역 중...")
    translator = deepl.Translator(DEEPL_API_KEY)
    final_results = []
    
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    print(f"🚀 오늘 날짜(KST): {today}") 
    
    for item in raw_data:
        try:
            sign_name = translator.translate_text(item['sign_name_jp'], target_lang="KO").text
            content = translator.translate_text(item['content_jp'], target_lang="KO").text
            lucky_action = translator.translate_text(item['lucky_action_jp'], target_lang="KO").text

            if "자리" not in sign_name:
                sign_name = sign_name + "자리"

            print(f"DEBUG: {item['rank']}위 | {sign_name} | 미션: {lucky_action}")

            final_results.append({
                "date": today,
                "rank": item['rank'], 
                "sign_name": sign_name,
                "content": content,
                "lucky_color": "자유", # 진짜 오하아사는 컬러가 없습니다. UI 깨짐 방지용 텍스트.
                "lucky_item": lucky_action # '말차 디저트 먹기'가 여기에 들어갑니다.
            })
        except Exception as e:
            print(f"❌ 번역/파싱 오류: {e}")
            continue
            
    return final_results

def update_supabase(processed_data):
    if not processed_data:
        return
    print("3단계: Supabase 업로드 시작...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    for data in processed_data:
        try:
            supabase.table("horoscopes").insert(data).execute()
        except Exception as e:
            print(f"❌ 데이터 삽입 오류: {e}")
    print("✅ Supabase 업데이트 완료!")

if __name__ == "__main__":
    print("🚀 진짜 오하아사 프로그램을 시작합니다.")
    raw_info = scrape_real_ohaasa()
    if raw_info:
        final_data = translate_and_process(raw_info)
        update_supabase(final_data)
    else:
        print("❌ 수집된 데이터가 없어 종료됩니다.")