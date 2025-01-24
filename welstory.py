# 월화수목금에만 되게하기, 슬래시 고치기, 타임 수정하기기

from flask import Flask, request, jsonify, abort
import requests
import schedule
import threading
import time
from datetime import datetime, timedelta
import pytz
import logging
import os

app = Flask(__name__)

# 한국 시간대 설정
KST = pytz.timezone('Asia/Seoul')

# 기존 WEBHOOK_URL을 기본 URL로 변경
MATTERMOST_BASE_URL = 'https://meeting.ssafy.com'
MATTERMOST_WEBHOOK_PATH = '본인_웹훅_주소소'
SLASH_TODAY_TOKEN = "슬래시토큰(싸피내부망에서만작동)" 
SLASH_TOMORROW_TOKEN = "슬래시토큰(싸피내부망에서만작동)"
USERNAME = 'WELSTORY_아이디'
PASSWORD = 'WELSTORY_비밀번호'

def get_current_seoul_time():
    return datetime.now(KST)

def get_menu():
    try:
        api = WelplusAPI()
        api.login(USERNAME, PASSWORD)
        menu = api.get_today_menu()
        return format_menu_message(menu)
    except Exception as e:
        return f"오류 발생: {str(e)}"
    
def get_menu_tommorow():
    try:
        api = WelplusAPI()
        api.login(USERNAME, PASSWORD)
        menu = api.get_tomorrow_menu()
        return format_menu_message(menu)
    except Exception as e:
        return f"오류 발생: {str(e)}"

# 자동 실행을 위한 스케줄러 함수
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

def job():
    current_time = get_current_seoul_time()
    logging.info(f"작업 시작 (서울 시간: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')})")
    try:
        api = WelplusAPI()
        api.login(USERNAME, PASSWORD)
        menu = api.get_today_menu()
        message = format_menu_message(menu)
        send_to_mattermost(message)
        logging.info("메뉴 전송 완료")
    except Exception as e:
        error_message = f"오류 발생: {str(e)}"
        logging.error(error_message)
        send_to_mattermost(error_message)

def verify_mattermost_token_today(token):
    """매터모스트 토큰 검증"""
    return token == SLASH_TODAY_TOKEN

def verify_mattermost_token_tomorrow(token):
    """매터모스트 토큰 검증"""
    return token == SLASH_TOMORROW_TOKEN

# 로깅 설정 강화
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.route('/menu', methods=['POST'])
def today_menu():
    logger.debug("========== 슬래시 커맨드 요청 시작 ==========")
    logger.debug(f"받은 Form 데이터: {request.form}")
    logger.debug(f"받은 Headers: {dict(request.headers)}")
    
    data = request.form
    channel_id = data.get('channel_id')
    token = data.get('token')
    
    logger.debug(f"Channel ID: {channel_id}")
    logger.debug(f"Token: {token}")
    
    try:
        immediate_response = {
            'response_type': 'in_channel',
            'text': '메뉴를 가져오는 중입니다...'
        }
        
        logger.debug("메뉴 정보 가져오기 시작")
        menu_message = get_menu()
        logger.debug(f"메뉴 정보: {menu_message[:100]}...") # 앞부분만 로깅
        
        logger.debug("매터모스트로 메시지 전송 시작")
        send_to_mattermost(menu_message, channel_id)
        logger.debug("매터모스트 전송 완료")
        
        return jsonify(immediate_response), 200
    except Exception as e:
        logger.error(f"에러 발생: {str(e)}", exc_info=True)  # 스택 트레이스 포함
        error_response = {
            'response_type': 'ephemeral',
            'text': f'메뉴를 가져오는데 실패했습니다: {str(e)}'
        }
        return jsonify(error_response), 500
    finally:
        logger.debug("========== 슬래시 커맨드 요청 종료 ==========")


@app.route('/tomorrow', methods=['POST'])
def tommorow_menu():
    # 토큰 검증
    token = request.form.get('token')
    if not verify_mattermost_token_tomorrow(token):
        abort(401, description="Invalid token")
    
    data = request.form
    channel_id = data.get('channel_id')
    
    immediate_response = {
        'response_type': 'in_channel',
        'text': '내일의 메뉴를 가져오는 중입니다...'
    }
    
    try:
        menu_message = get_menu_tommorow()
        send_to_mattermost(menu_message, channel_id)
        return jsonify(immediate_response), 200
    except Exception as e:
        error_response = {
            'response_type': 'ephemeral',
            'text': f'메뉴를 가져오는데 실패했습니다: {str(e)}'
        }
        return jsonify(error_response), 500

# 401 에러 핸들러 추가
@app.errorhandler(401)
def unauthorized_error(e):
    return jsonify({
        'response_type': 'ephemeral',
        'text': '인증에 실패했습니다. 유효하지 않은 토큰입니다.'
    }), 401

# 상태 확인용 엔드포인트
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

# 404 에러 핸들러
@app.errorhandler(404)
def not_found_error(e):
    logging.error(f"404 error: {request.url}")
    return jsonify({
        'response_type': 'ephemeral',
        'text': '요청한 경로를 찾을 수 없습니다.'
    }), 404

# 405 에러 핸들러
@app.errorhandler(405)
def method_not_allowed_error(e):
    logging.error(f"405 error: {request.method} {request.url}")
    return jsonify({
        'response_type': 'ephemeral',
        'text': '잘못된 HTTP 메소드입니다.'
    }), 405

def schedule_job():
    """스케줄러에서 실행할 작업을 확인하고 실행"""
    seoul_time = get_current_seoul_time()
    scheduled_time = "02:30"
    schedule_time_obj = datetime.strptime(scheduled_time, "%H:%M").time()
    
    if seoul_time.time().hour == schedule_time_obj.hour and \
        seoul_time.time().minute == schedule_time_obj.minute:
        job()

def format_menu_message(menu):
    message = "## 🍽️ 오늘의 점심 메뉴 :lunch_today_parrot:\n\n"
    
    # 이미지 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            image_md = "이미지 없음"
            if item.get('이미지'):
                image_md = f"![메뉴이미지]({item['이미지']})"
            message += f" {image_md} |"
    message += "\n"
    
    # 구분선
    message += "|" + "---|" * len(menu['점심']) + "\n"
    
    # 음식점 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            message += f" {item['코너']} |"
    message += "\n"
    
    # 메뉴 제목 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            message += f" **{item['메뉴명']}** |"
    message += "\n"
    
    # 메뉴 상세 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            details = ', '.join(filter(None, item['구성']))
            message += f" {details} |"
    message += "\n"
    
    # 칼로리 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            message += f" {item['칼로리']}kcal |"
    message += "\n"
    
    # 평점 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            rating_info = ""
            if item.get('평균평점', 0) > 0:
                rating_info = f"⭐ {item['평균평점']:.1f} ({item['참여자수']}명)"
            else:
                rating_info = "평가 없음"
            message += f" {rating_info} |"
    message += "\n"
    
    return message

def format_simple_menu_message(menu):
    """간단한 메뉴 포맷 (메뉴명, 사진, 평점만)"""
    message = "## 🍽️ 오늘 메뉴 평점 요약\n\n"
    
    # 이미지와 메뉴명, 평점만 보여주는 테이블
    message += "|" + " 메뉴 |" * len(menu['점심']) + "\n"
    message += "|" + "---|" * len(menu['점심']) + "\n"
    
    # 이미지 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            image_md = "이미지 없음"
            if item.get('이미지'):
                image_md = f"![메뉴이미지]({item['이미지']})"
            message += f" {image_md} |"
    message += "\n"
    
    # 메뉴명 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            message += f" **{item['메뉴명']}** |"
    message += "\n"
    
    # 평점 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            rating_info = ""
            if item.get('평균평점', 0) > 0:
                rating_info = f"⭐ {item['평균평점']:.1f} ({item['참여자수']}명)"
            else:
                rating_info = "평가 없음"
            message += f" {rating_info} |"
    message += "\n"
    
    return message

def send_to_mattermost(text, channel_id=None):
    print(f"메시지 전송: {text}")
    payload = {
        "text": text,
        "channel_id": channel_id  # channel_id가 있을 경우 해당 채널로 전송
    }
    
    # 웹훅 URL 결정
    webhook_url = f"{MATTERMOST_BASE_URL}{MATTERMOST_WEBHOOK_PATH}"

    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            print("메시지가 성공적으로 전송되었습니다.")
        else:
            print(f"메시지 전송 실패: {response.status_code}")
    except Exception as e:
        print(f"전송 중 오류 발생: {str(e)}")

class WelplusAPI:
    def __init__(self):
        self.base_url = "https://welplus.welstory.com"
        self.device_id = "본인_휴대폰_디바이스_ID_또는_UUID"
        self.token = None
        self.headers = {
            'X-Device-Id': self.device_id,
            'X-Autologin': 'Y',
            'User-Agent': '본인_유저_에이전트'
            # 예시 : 'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Welplus/1.01.08'
        }

    def login(self, username, password):
        url = f"{self.base_url}/login"
        
        login_headers = self.headers.copy()
        login_headers.update({
            'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
            'Authorization': 'Bearer null'
        })
        
        data = {
            'username': username,
            'password': password,
            'remember-me': 'true'
        }
        
        response = requests.post(url, headers=login_headers, data=data)
        
        if response.status_code == 200:
            print("로그인 성공")
            self.token = response.headers.get('Authorization')
            return response.json()
        else:
            raise Exception(f"Login failed: {response.status_code}")

    def get_today_menu(self):
        if not self.token:
            raise Exception("Not logged in")

        url = f"{self.base_url}/api/meal"
        
        headers = self.headers.copy()
        headers.update({
            'Authorization': self.token
        })

        today = datetime.now().strftime("%Y%m%d")
        
        params = {
            "menuDt": today,
            "menuMealType": "2",  # 2는 점심
            "restaurantCode": "REST000595", # 삼성 부산 전기
            "sortingFlag": "",
            "mainDivRestaurantCode": "REST000595",
            "activeRestaurantCode": "REST000595"
        }

        response = requests.get(url, headers=headers, params=params)

        # print(response.url)
        # print(response.text)
        
        if response.status_code == 200:
            menu_data = response.json()
            return self._parse_menu(menu_data)
        else:
            raise Exception(f"Failed to get menu: {response.status_code}")
    
    def get_tomorrow_menu(self):
        if not self.token:
            raise Exception("Not logged in")

        url = f"{self.base_url}/api/meal"
        
        headers = self.headers.copy()
        headers.update({
            'Authorization': self.token
        })

        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
        
        
        params = {
            "menuDt": tomorrow,
            "menuMealType": "2",  # 2는 점심
            "restaurantCode": "REST000595",
            "sortingFlag": "",
            "mainDivRestaurantCode": "REST000595",
            "activeRestaurantCode": "REST000595"
        }

        response = requests.get(url, headers=headers, params=params)

        # print(response.url)
        # print(response.text)
        
        if response.status_code == 200:
            menu_data = response.json()
            return self._parse_menu(menu_data)
        else:
            raise Exception(f"Failed to get menu: {response.status_code}")
        
    def get_menu_rating(self, menu_dt, hall_no, menu_course_type, menu_meal_type, restaurant_code):
        """메뉴 평점 조회"""
        if not self.token:
            raise Exception("Not logged in")

        url = f"{self.base_url}/api/meal/getMenuEvalAvg"
        
        headers = self.headers.copy()
        headers.update({
            'Authorization': self.token
        })

        params = {
            "menuDt": menu_dt,
            "hallNo": hall_no,
            "menuCourseType": menu_course_type,
            "menuMealType": menu_meal_type,
            "restaurantCode": restaurant_code,
            "mainDivRestaurantCode": restaurant_code
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            # print(response.url)
            # print(response.text)
            if response.status_code == 200:
                data = response.json().get('data', {})
                return {
                    "평균평점": data.get('MENU_GRADE_AVG', 0),
                    "참여자수": data.get('TOT_CNT', 0)
                }
        except Exception as e:
            print(f"평점 조회 실패: {str(e)}")
        
        return {"평균평점": 0, "참여자수": 0}

    def _parse_menu(self, menu_data):
        """메뉴 데이터 파싱"""
        try:
            menu_items = []
            meal_list = menu_data.get('data', {}).get('mealList', [])
            
            for meal in meal_list[:4]:
                # 기본 메뉴 정보
                course_txt = meal.get('courseTxt', '')
                menu_name = meal.get('menuName', '')
                kcal = meal.get('sumKcal', '')
                sub_menu_txt = meal.get('subMenuTxt', '').split(',')
                
                # 이미지 URL 구성
                photo_url = meal.get('photoUrl', '')
                photo_cd = meal.get('photoCd', '')
                image_url = f"{photo_url}{photo_cd}" if photo_url and photo_cd else None

                # 평점 정보 조회
                rating_info = self.get_menu_rating(
                    meal.get('menuDt'),
                    meal.get('hallNo'),
                    meal.get('menuCourseType'),
                    meal.get('menuMealType'),
                    meal.get('restaurantCode')
                )

                menu_info = {
                    '코너': course_txt,
                    '메뉴명': menu_name,
                    '칼로리': kcal,
                    '구성': sub_menu_txt,
                    '이미지': image_url,
                    '평균평점': rating_info['평균평점'],
                    '참여자수': rating_info['참여자수']
                }
                menu_items.append(menu_info)

            for meal in meal_list[5:6]:
                # 기본 메뉴 정보
                course_txt = meal.get('courseTxt', '')
                menu_name = meal.get('menuName', '')
                kcal = meal.get('sumKcal', '')
                sub_menu_txt = meal.get('subMenuTxt', '').split(',')
                
                # 이미지 URL 구성
                photo_url = meal.get('photoUrl', '')
                photo_cd = meal.get('photoCd', '')
                image_url = f"{photo_url}{photo_cd}" if photo_url and photo_cd else None

                menu_info = {
                    '코너': course_txt,
                    '메뉴명': menu_name,
                    '칼로리': kcal,
                    '구성': sub_menu_txt,
                    '이미지': image_url,
                }
                menu_items.append(menu_info)

            return {"점심": menu_items}
        except Exception as e:
            raise Exception(f"Failed to parse menu data: {str(e)}")

def main():
    # 스케줄러 설정
    schedule.every().day.at("02:30").do(lambda: send_to_mattermost(get_menu()))
    
    # 간단 메뉴 스케줄 (03:30) - 람다로 통일
    schedule.every().day.at("03:30").do(lambda: send_to_mattermost(format_simple_menu_message(get_menu())))
    
    # 스케줄러를 별도 스레드에서 실행
    scheduler_thread = threading.Thread(target=run_schedule)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # Flask 앱 실행
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()