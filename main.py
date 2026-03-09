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

# --- ⚙️ 기본 설정 ---
# 환경 변수에서 먼저 찾고, 없으면 기존 값을 쓰도록 설정
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "a7aefc71-7412-4b5c-b39d-fed826a89d87:fx")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xhnebazckldsasyswtoa.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhobmViYXpja2xkc2FzeXN3dG9hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NDM3NjAsImV4cCI6MjA4ODUxOTc2MH0.8T7pXochvff7GxvOXjoFx9TbdlG2TZLm2oSSPnrCtdc")

OHASA_URL = "https://www.tv-asahi.co.jp/goodmorning/uranai/" # TV 아사히 오하아사 공식 페이지

def scrape_ohasa():
    print(f"1단계: 셀레니움 가동 중... {OHASA_URL}")
    options = Options()
    # 💡 오늘 추가한 강력한 네트워크 에러 방지 옵션 유지
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get(OHASA_URL)
        time.sleep(8) # 페이지 로딩 넉넉히 대기

        # [투트랙 전략 1] 상단 랭킹 배너에서 '진짜 순위' 딕셔너리 만들기
        rank_dict = {}
        nav_items = driver.find_elements(By.CSS_SELECTOR, "ul.rank-box li")
        for index, nav in enumerate(nav_items):
            try:
                sign_name = nav.find_element(By.CSS_SELECTOR, "span").text.strip()
                if sign_name:
                    rank_dict[sign_name] = str(index + 1)
            except:
                continue

        horoscope_data = []
        
        # [투트랙 전략 2] 기존에 완벽하게 작동했던 본문 수집 로직 유지
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
                    
                    real_rank = "13" 
                    for sign_key, rank_val in rank_dict.items():
                        if sign_key in text:
                            real_rank = rank_val
                            break
                    
                    horoscope_data.append({
                        "rank": real_rank, 
                        "raw_text": f"운세데이터|{text}"
                    })

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
    
    # 💡 깃허브 액션에서도 한국 시간으로 강제 고정하는 로직 유지
    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    print(f"🚀 오늘 날짜(KST): {today}") 
    
    for item in unique_raw:
        try:
            translated = translator.translate_text(item['raw_text'], target_lang="KO").text
            print(f"DEBUG 번역본: {translated}")

            sign_match = re.search(r'\|(.*?)\(', translated)
            sign_name = sign_match.group(1).strip() if sign_match else "별자리"
            
            color_match = re.search(r'컬러\s*[:：]\s*(.*?)(\s|$)', translated)
            lucky_color = color_match.group(1).strip() if color_match else "확인필요"
            
            item_match = re.search(r'(열쇠|아이템|물건)\s*[:：]\s*(.*?)($)', translated)
            if item_match:
                lucky_item = item_match.group(2).strip()
                lucky_item = lucky_item.split('오늘의')[0].strip()
                lucky_item = lucky_item.replace('▲', '').strip() 
            else:
                lucky_item = "확인필요"
                        
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
    
    # 1. 오늘 날짜 가져오기
    today = processed_data[0]['date']
    
    try:
        # 2. 빗자루질: 오늘 날짜의 찌꺼기 데이터가 있다면 싹 지워버립니다! (충돌 원천 차단)
        supabase.table("horoscopes").delete().eq("date", today).execute()
        print(f"🧹 {today} 기존 데이터 초기화 완료!")
        
        # 3. 한방에 넣기: for문 없이 12개를 한꺼번에 깔끔하게 밀어 넣습니다.
        supabase.table("horoscopes").insert(processed_data).execute()
        
    except Exception as e:
        print(f"❌ 데이터 삽입 오류: {e}")
            
    print("✅ Supabase 업데이트 완료!")

if __name__ == "__main__":
    print("🚀 TV 아사히 오하아사 프로그램을 시작합니다.")
    raw_info = scrape_ohasa()
    
    if raw_info:
        final_data = translate_and_process(raw_info)
        update_supabase(final_data)
    else:
        print("❌ 수집된 데이터가 없어 프로그램이 종료됩니다.")