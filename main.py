import os
import time
import re
from datetime import datetime
import deepl
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client, Client

DEEPL_API_KEY = "a7aefc71-7412-4b5c-b39d-fed826a89d87:fx"
SHEET_ID = "1Yh19VUoXaTtk-4nYmoZRUyRlJ7QnUqZOSCUm-mUlyME"
JSON_FILE = "service_account_key.json"
OHASA_URL = "https://www.tv-asahi.co.jp/goodmorning/uranai/" # 일본 오하아사 공식 페이지
SUPABASE_URL = "https://etbjpdagmpsjlldoojgw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0YmpwZGFnbXBzamxsZG9vamd3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5MzI2OTcsImV4cCI6MjA4ODUwODY5N30.m7cvuwpIKuzK4Ay103X5VqRy5Q0MOjHisQUq0S8Ct_o"

def scrape_ohasa():
    print(f"1단계: 셀레니움 가동 중... {OHASA_URL}")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(OHASA_URL)
        time.sleep(12) 

        # 💡 [투트랙 전략 1] 상단 랭킹 배너에서 '진짜 순위' 딕셔너리 만들기
        # 상단 배너(ul.rank-box)는 항상 1위부터 12위 순서로 나열되어 있습니다.
        rank_dict = {}
        nav_items = driver.find_elements(By.CSS_SELECTOR, "ul.rank-box li")
        for index, nav in enumerate(nav_items):
            try:
                # span 안의 'かに座'(게자리) 같은 이름을 가져와 순위(index + 1)와 매칭합니다.
                sign_name = nav.find_element(By.CSS_SELECTOR, "span").text.strip()
                if sign_name:
                    rank_dict[sign_name] = str(index + 1)
            except:
                continue

        horoscope_data = []
        
        # 💡 [투트랙 전략 2] 기존에 완벽하게 작동했던 본문 수집 로직 유지
        items = driver.find_elements(By.CSS_SELECTOR, ".list_area li, #uranai_list li, .uranai_item")
        if not items:
            items = driver.find_elements(By.XPATH, "//div[contains(., 'ラッキーカラー') and contains(., '座')]")

        seen_signs = set()

        for item in items:
            text = item.text.strip().replace('\n', ' ')
            if '座' in text and 30 < len(text) < 400:
                
                # 중복 수집 방지
                sign_name_raw = text.split('座')[0] + '座'
                if sign_name_raw not in seen_signs:
                    seen_signs.add(sign_name_raw)
                    
                    # 🎯 [핵심] 수집한 본문에 포함된 별자리 이름으로 진짜 순위를 찾아옵니다.
                    real_rank = "13" # 매칭 실패 시 기본값
                    for sign_key, rank_val in rank_dict.items():
                        if sign_key in text:
                            real_rank = rank_val
                            break
                    
                    # 강제 index 대신 진짜 순위(real_rank)를 부여합니다.
                    horoscope_data.append({
                        "rank": real_rank, 
                        "raw_text": f"운세데이터|{text}"
                    })

        # 1위부터 12위까지 순서대로 DB에 들어가도록 깔끔하게 정렬
        horoscope_data.sort(key=lambda x: int(x['rank']) if x['rank'].isdigit() else 99)

        print(f"최종 수집된 별자리 개수: {len(horoscope_data)}개")
        return horoscope_data

    except Exception as e:
        print(f"🌐 오류 발생: {e}")
        return []
    finally:
        driver.quit()

def translate_and_process(raw_data):
    if not raw_data:
        return []
    
    unique_raw = []
    seen = set()
    for item in raw_data:
        if item['raw_text'] not in seen:
            unique_raw.append(item)
            seen.add(item['raw_text'])

    translator = deepl.Translator(DEEPL_API_KEY)
    final_results = []
    today = datetime.now().strftime("%Y-%m-%d")

    for item in unique_raw:
        try:
            translated = translator.translate_text(item['raw_text'], target_lang="KO").text
            # 디버깅을 위해 번역본을 출력해봅니다.
            print(f"DEBUG 번역본: {translated}")

            # 1. 별자리 이름 추출
            sign_match = re.search(r'\|(.*?)\(', translated)
            sign_name = sign_match.group(1).strip() if sign_match else "별자리"
            
            # 2. 럭키 컬러 추출 (콜론 뒤의 단어 추출)
            color_match = re.search(r'컬러\s*[:：]\s*(.*?)(\s|$)', translated)
            lucky_color = color_match.group(1).strip() if color_match else "확인필요"
            
            # 3. 행운의 열쇠(아이템) 추출 - "열쇠" 키워드 추가
            # "행운의 열쇠: 에코백" 같은 구조에서 '에코백'만 가져옵니다.
            # 3. 행운의 열쇠(아이템) 추출 및 불순물 제거
            item_match = re.search(r'(열쇠|아이템|물건)\s*[:：]\s*(.*?)($)', translated)
            if item_match:
                lucky_item = item_match.group(2).strip()
                # 💡 추가: '오늘의 순위' 같은 불필요한 문구가 붙어있다면 제거합니다.
                lucky_item = lucky_item.split('오늘의')[0].strip()
                lucky_item = lucky_item.replace('▲', '').strip() # 화살표 기호도 삭제
            else:
                lucky_item = "확인필요"
                        
            # 4. 운세 본문 추출
            content = translated.split(')')[-1].split('럭키')[0].split('행운')[0].strip()

            final_results.append({
                "date": today,
                "rank": item['rank'],
                "sign_name": sign_name,
                "content": content,
                "lucky_color": lucky_color,
                "lucky_item": lucky_item
            })
        except Exception as e:
            print(f"파싱 오류: {e}")
            continue
            
    return final_results

def update_supabase(processed_data):
    if not processed_data:
        print("Supabase에 보낼 데이터가 비어있습니다.")
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
    print("🚀 프로그램을 시작합니다.")
    raw_info = scrape_ohasa()
    
    if raw_info:
        final_data = translate_and_process(raw_info)
        update_supabase(final_data)
    else:
        print("❌ 수집된 데이터가 없어 프로그램이 종료됩니다.")