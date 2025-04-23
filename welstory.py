from flask import Flask, request, jsonify
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
KST = pytz.timezone("Asia/Seoul")

# 기존 WEBHOOK_URL을 기본 URL로 변경
MATTERMOST_BASE_URL = "https://meeting.ssafy.com"
MATTERMOST_WEBHOOK_PATH = "본인_웹훅_주소"
USERNAME = "웰스토리_아이디"
PASSWORD = "웰스토리_비번번^^"


def get_current_seoul_time():
    return datetime.now(KST)


def get_menu():
    try:
        api = WelplusAPI()
        api.login(USERNAME, PASSWORD)
        menu = api.get_today_menu()
        return menu
    except Exception as e:
        print(f"메뉴 가져오기 실패: {str(e)}")
        # 오류 발생 시 기본 구조의 빈 딕셔너리 반환
        return {"점심": []}


# 자동 실행을 위한 스케줄러 함수
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)


def job():
    current_time = get_current_seoul_time()
    logging.info(
        f"작업 시작 (서울 시간: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')})"
    )
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


def schedule_job():
    """스케줄러에서 실행할 작업을 확인하고 실행"""
    seoul_time = get_current_seoul_time()
    scheduled_time = "02:30"
    schedule_time_obj = datetime.strptime(scheduled_time, "%H:%M").time()

    if (
        seoul_time.time().hour == schedule_time_obj.hour
        and seoul_time.time().minute == schedule_time_obj.minute
    ):
        job()


def format_menu_message(menu):
    message = "## :knife_fork_plate: 오늘의 점심 메뉴 :lunch_today_parrot:\n\n"

    # 라면 메뉴 분리
    regular_items = []
    ramen_item = None

    for item in menu.get("점심", []):
        if "[라면" in item.get("메뉴명", ""):
            ramen_item = item
        else:
            regular_items.append(item)

    # 기존 메뉴 테이블 생성
    if regular_items:
        # 이미지 행
        message += "|"
        for item in regular_items:
            image_md = "이미지 없음"
            if item.get("이미지"):
                image_md = f"![메뉴이미지]({item['이미지']})"
            message += f" {image_md} |"
        message += "\n"

        # 구분선
        message += "|" + "---|" * len(regular_items) + "\n"

        # 음식점 행
        message += "|"
        for item in regular_items:
            message += f" {item['코너']} |"
        message += "\n"

        # 메뉴 제목 행
        message += "|"
        for item in regular_items:
            message += f" **{item['메뉴명']}** |"
        message += "\n"

        # 메뉴 상세 행
        message += "|"
        for item in regular_items:
            details = ", ".join(filter(None, item["구성"]))
            message += f" {details} |"
        message += "\n"

        # 칼로리 행
        message += "|"
        for item in regular_items:
            message += f" {item['칼로리']}kcal |"
        message += "\n"

        # 평점 행
        message += "|"
        for item in regular_items:
            rating_info = ""
            if item.get("평균평점", 0) > 0:
                rating_info = f"⭐ {item['평균평점']:.1f} ({item['참여자수']}명)"
            else:
                rating_info = "평가 없음"
            message += f" {rating_info} |"
        message += "\n\n"

    # 라면 메뉴 테이블 추가 (2열 테이블 버전)
    if ramen_item:
        # 라면 종류와 토핑 분리
        ramen_types = []
        toppings = []
        topping_start_idx = -1

        # 구성 리스트에서 '[토핑' 항목 이후부터 토핑으로 간주
        for i, item in enumerate(ramen_item.get("구성", [])):
            if "[토핑" in item:
                topping_start_idx = i
                break

        # 토핑 시작 인덱스가 찾아졌으면 분리
        if topping_start_idx > 0:
            # '[라면' 항목 제외하고 토핑 전까지는 라면 종류
            for i, item in enumerate(ramen_item.get("구성", [])):
                if (
                    i > 0 and i < topping_start_idx
                ):  # 첫 번째 항목([라면 n종 중 택1]) 제외
                    ramen_types.append(item)

            # 토핑 항목 이후부터 끝까지는 토핑
            for i, item in enumerate(ramen_item.get("구성", [])):
                if i > topping_start_idx:  # [토핑N종] 이후
                    toppings.append(item)
        else:
            # 토핑 구분자가 없는 경우 또는 찾지 못한 경우
            # 아무 필터링 없이 첫 번째 항목([라면 n종 중 택1])만 제외하고 모두 라면 종류로 간주
            for i, item in enumerate(ramen_item.get("구성", [])):
                if i > 0:  # 첫 번째 항목 제외
                    ramen_types.append(item)

        # 라면 정보가 포함된 2열 테이블 생성
        message += "## :sinjjang-ramen: 오늘의 라면 메뉴 :todayramen: \n\n"

        # 간단한 2열 테이블
        message += "| 라면 메뉴 | 라면 종류 |\n"
        message += "|---|---|\n"

        # 라면 이미지와 종류들
        image_md = "이미지 없음"
        if ramen_item.get("이미지"):
            image_md = f"![라면이미지]({ramen_item['이미지']})"

        # 라면 종류 리스트 (콤마로 구분)
        ramen_types_formatted = ", ".join(ramen_types)

        message += f"| {image_md} | {ramen_types_formatted} |\n"

        # 토핑 리스트 (콤마로 구분)
        toppings_formatted = ", ".join(toppings)

        message += f"| 토핑 | {toppings_formatted} |\n"

    return message


def format_menu_message_wen(menu):
    message = "## :knife_fork_plate: 승리의 특식 데이 :hodong_eating_lunch_outside: :siuuuu:\n\n"

    # 라면 메뉴 분리
    regular_items = []
    ramen_item = None

    for item in menu.get("점심", []):
        if "[라면" in item.get("메뉴명", ""):
            ramen_item = item
        else:
            regular_items.append(item)

    # 기존 메뉴 테이블 생성
    if regular_items:
        # 이미지 행
        message += "|"
        for item in regular_items:
            image_md = "이미지 없음"
            if item.get("이미지"):
                image_md = f"![메뉴이미지]({item['이미지']})"
            message += f" {image_md} |"
        message += "\n"

        # 구분선
        message += "|" + "---|" * len(regular_items) + "\n"

        # 음식점 행
        message += "|"
        for item in regular_items:
            message += f" {item['코너']} |"
        message += "\n"

        # 메뉴 제목 행
        message += "|"
        for item in regular_items:
            message += f" **{item['메뉴명']}** |"
        message += "\n"

        # 메뉴 상세 행
        message += "|"
        for item in regular_items:
            details = ", ".join(filter(None, item["구성"]))
            message += f" {details} |"
        message += "\n"

        # 칼로리 행
        message += "|"
        for item in regular_items:
            message += f" {item['칼로리']}kcal |"
        message += "\n"

        # 평점 행
        message += "|"
        for item in regular_items:
            rating_info = ""
            if item.get("평균평점", 0) > 0:
                rating_info = f"⭐ {item['평균평점']:.1f} ({item['참여자수']}명)"
            else:
                rating_info = "평가 없음"
            message += f" {rating_info} |"
        message += "\n\n"

    # 라면 메뉴 테이블 추가 (2열 테이블 버전)
    if ramen_item:
        # 라면 종류와 토핑 분리
        ramen_types = []
        toppings = []
        topping_start_idx = -1

        # 구성 리스트에서 '[토핑' 항목 이후부터 토핑으로 간주
        for i, item in enumerate(ramen_item.get("구성", [])):
            if "[토핑" in item:
                topping_start_idx = i
                break

        # 토핑 시작 인덱스가 찾아졌으면 분리
        if topping_start_idx > 0:
            # '[라면' 항목 제외하고 토핑 전까지는 라면 종류
            for i, item in enumerate(ramen_item.get("구성", [])):
                if (
                    i > 0 and i < topping_start_idx
                ):  # 첫 번째 항목([라면 n종 중 택1]) 제외
                    ramen_types.append(item)

            # 토핑 항목 이후부터 끝까지는 토핑
            for i, item in enumerate(ramen_item.get("구성", [])):
                if i > topping_start_idx:  # [토핑N종] 이후
                    toppings.append(item)
        else:
            # 토핑 구분자가 없는 경우 또는 찾지 못한 경우
            # 아무 필터링 없이 첫 번째 항목([라면 n종 중 택1])만 제외하고 모두 라면 종류로 간주
            for i, item in enumerate(ramen_item.get("구성", [])):
                if i > 0:  # 첫 번째 항목 제외
                    ramen_types.append(item)

        # 라면 정보가 포함된 2열 테이블 생성
        message += "## :sinjjang-ramen: 오늘의 라면 메뉴 :todayramen: \n\n"

        # 간단한 2열 테이블
        message += "| 라면 메뉴 | 라면 종류 |\n"
        message += "|---|---|\n"

        # 라면 이미지와 종류들
        image_md = "이미지 없음"
        if ramen_item.get("이미지"):
            image_md = f"![라면이미지]({ramen_item['이미지']})"

        # 라면 종류 리스트 (콤마로 구분)
        ramen_types_formatted = ", ".join(ramen_types)

        message += f"| {image_md} | {ramen_types_formatted} |\n"

        # 토핑 리스트 (콤마로 구분)
        toppings_formatted = ", ".join(toppings)

        message += f"| 토핑 | {toppings_formatted} |\n"

    return message


def format_menu_message_fri(menu):
    message = "## :busan_goat: 와!!!!! :sans: 금요일!!!!! :shinchangseop: :siuuuuu: :siuuuuuuuuu: :siuuuu: :ronaldo_chams: :rorange_caramel: \n\n"

    # 라면 메뉴 분리
    regular_items = []
    ramen_item = None

    for item in menu.get("점심", []):
        if "[라면" in item.get("메뉴명", ""):
            ramen_item = item
        else:
            regular_items.append(item)

    # 기존 메뉴 테이블 생성
    if regular_items:
        # 이미지 행
        message += "|"
        for item in regular_items:
            image_md = "이미지 없음"
            if item.get("이미지"):
                image_md = f"![메뉴이미지]({item['이미지']})"
            message += f" {image_md} |"
        message += "\n"

        # 구분선
        message += "|" + "---|" * len(regular_items) + "\n"

        # 음식점 행
        message += "|"
        for item in regular_items:
            message += f" {item['코너']} |"
        message += "\n"

        # 메뉴 제목 행
        message += "|"
        for item in regular_items:
            message += f" **{item['메뉴명']}** |"
        message += "\n"

        # 메뉴 상세 행
        message += "|"
        for item in regular_items:
            details = ", ".join(filter(None, item["구성"]))
            message += f" {details} |"
        message += "\n"

        # 칼로리 행
        message += "|"
        for item in regular_items:
            message += f" {item['칼로리']}kcal |"
        message += "\n"

        # 평점 행
        message += "|"
        for item in regular_items:
            rating_info = ""
            if item.get("평균평점", 0) > 0:
                rating_info = f"⭐ {item['평균평점']:.1f} ({item['참여자수']}명)"
            else:
                rating_info = "평가 없음"
            message += f" {rating_info} |"
        message += "\n\n"

    # 라면 메뉴 테이블 추가 (2열 테이블 버전)
    if ramen_item:
        # 라면 종류와 토핑 분리
        ramen_types = []
        toppings = []
        topping_start_idx = -1

        # 구성 리스트에서 '[토핑' 항목 이후부터 토핑으로 간주
        for i, item in enumerate(ramen_item.get("구성", [])):
            if "[토핑" in item:
                topping_start_idx = i
                break

        # 토핑 시작 인덱스가 찾아졌으면 분리
        if topping_start_idx > 0:
            # '[라면' 항목 제외하고 토핑 전까지는 라면 종류
            for i, item in enumerate(ramen_item.get("구성", [])):
                if (
                    i > 0 and i < topping_start_idx
                ):  # 첫 번째 항목([라면 n종 중 택1]) 제외
                    ramen_types.append(item)

            # 토핑 항목 이후부터 끝까지는 토핑
            for i, item in enumerate(ramen_item.get("구성", [])):
                if i > topping_start_idx:  # [토핑N종] 이후
                    toppings.append(item)
        else:
            # 토핑 구분자가 없는 경우 또는 찾지 못한 경우
            # 아무 필터링 없이 첫 번째 항목([라면 n종 중 택1])만 제외하고 모두 라면 종류로 간주
            for i, item in enumerate(ramen_item.get("구성", [])):
                if i > 0:  # 첫 번째 항목 제외
                    ramen_types.append(item)

        # 라면 정보가 포함된 2열 테이블 생성
        message += "## :sinjjang-ramen: 오늘의 라면 메뉴 :todayramen: \n\n"

        # 간단한 2열 테이블
        message += "| 라면 메뉴 | 라면 종류 |\n"
        message += "|---|---|\n"

        # 라면 이미지와 종류들
        image_md = "이미지 없음"
        if ramen_item.get("이미지"):
            image_md = f"![라면이미지]({ramen_item['이미지']})"

        # 라면 종류 리스트 (콤마로 구분)
        ramen_types_formatted = ", ".join(ramen_types)

        message += f"| {image_md} | {ramen_types_formatted} |\n"

        # 토핑 리스트 (콤마로 구분)
        toppings_formatted = ", ".join(toppings)

        message += f"| 토핑 | {toppings_formatted} |\n"

    return message


def format_simple_menu_message(menu):
    message = "## :knife_fork_plate: 오늘 메뉴 평점 중간 점검 !! :master_park:\n\n"

    # 이미지 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            image_md = "이미지 없음"
            if item.get("이미지"):
                image_md = f"![메뉴이미지]({item['이미지']})"
            message += f" {image_md} |"
    message += "\n"

    # 구분선
    message += "|" + "---|" * len(menu["점심"]) + "\n"

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

    # 평점 행
    message += "|"
    for meal_type, items in menu.items():
        for item in items:
            rating_info = ""
            if item.get("평균평점", 0) > 0:
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
        "channel_id": channel_id,  # channel_id가 있을 경우 해당 채널로 전송
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
        self.device_id = "95CB2CC5-543E-4DA7-AD7D-3D2D463CB0A0"
        self.token = None
        self.headers = {
            "X-Device-Id": self.device_id,
            "X-Autologin": "Y",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Welplus/1.01.08",
            # 예시 : 'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Welplus/1.01.08'
        }

    def login(self, username, password):
        url = f"{self.base_url}/login"

        login_headers = self.headers.copy()
        login_headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "Authorization": "Bearer null",
            }
        )

        data = {"username": username, "password": password, "remember-me": "true"}

        response = requests.post(url, headers=login_headers, data=data)

        if response.status_code == 200:
            print("로그인 성공")
            self.token = response.headers.get("Authorization")
            return response.json()
        else:
            raise Exception(f"Login failed: {response.status_code}")

    def get_today_menu(self):
        if not self.token:
            raise Exception("Not logged in")

        url = f"{self.base_url}/api/meal"

        headers = self.headers.copy()
        headers.update({"Authorization": self.token})

        today = datetime.now().strftime("%Y%m%d")

        params = {
            "menuDt": today,
            "menuMealType": "2",  # 2는 점심
            "restaurantCode": "REST000595",  # 삼성 부산 전기
            "sortingFlag": "",
            "mainDivRestaurantCode": "REST000595",
            "activeRestaurantCode": "REST000595",
        }

        response = requests.get(url, headers=headers, params=params)

        print(response.url)
        print(response.text)

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
        headers.update({"Authorization": self.token})

        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")

        params = {
            "menuDt": tomorrow,
            "menuMealType": "2",  # 2는 점심
            "restaurantCode": "REST000595",
            "sortingFlag": "",
            "mainDivRestaurantCode": "REST000595",
            "activeRestaurantCode": "REST000595",
        }

        response = requests.get(url, headers=headers, params=params)

        # print(response.url)
        # print(response.text)

        if response.status_code == 200:
            menu_data = response.json()
            return self._parse_menu(menu_data)
        else:
            raise Exception(f"Failed to get menu: {response.status_code}")

    def get_menu_rating(
        self, menu_dt, hall_no, menu_course_type, menu_meal_type, restaurant_code
    ):
        """메뉴 평점 조회"""
        if not self.token:
            raise Exception("Not logged in")

        url = f"{self.base_url}/api/meal/getMenuEvalAvg"

        headers = self.headers.copy()
        headers.update({"Authorization": self.token})

        params = {
            "menuDt": menu_dt,
            "hallNo": hall_no,
            "menuCourseType": menu_course_type,
            "menuMealType": menu_meal_type,
            "restaurantCode": restaurant_code,
            "mainDivRestaurantCode": restaurant_code,
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            # print(response.url)
            # print(response.text)
            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "평균평점": data.get("MENU_GRADE_AVG", 0),
                    "참여자수": data.get("TOT_CNT", 0),
                }
        except Exception as e:
            print(f"평점 조회 실패: {str(e)}")

        return {"평균평점": 0, "참여자수": 0}

    def _parse_menu(self, menu_data):
        """메뉴 데이터 파싱"""
        try:
            menu_items = []
            meal_list = menu_data.get("data", {}).get("mealList", [])

            # 기본적으로 최대 4개 항목만 처리하되, SELF 배식대가 나오면 중단
            count = 0
            for meal in meal_list:
                if count >= 4:  # 최대 4개까지만 처리
                    break

                # 코너가 "SELF 배식대"면 루프 종료
                course_txt = meal.get("courseTxt", "")
                if course_txt == "SELF 배식대":
                    break

                # 기본 메뉴 정보
                menu_name = meal.get("menuName", "")
                kcal = meal.get("sumKcal", "")
                sub_menu_txt = meal.get("subMenuTxt", "").split(",")

                # 이미지 URL 구성
                photo_url = meal.get("photoUrl", "")
                photo_cd = meal.get("photoCd", "")
                image_url = f"{photo_url}{photo_cd}" if photo_url and photo_cd else None

                # 평점 정보 조회
                rating_info = self.get_menu_rating(
                    meal.get("menuDt"),
                    meal.get("hallNo"),
                    meal.get("menuCourseType"),
                    meal.get("menuMealType"),
                    meal.get("restaurantCode"),
                )

                menu_info = {
                    "코너": course_txt,
                    "메뉴명": menu_name,
                    "칼로리": kcal,
                    "구성": sub_menu_txt,
                    "이미지": image_url,
                    "평균평점": rating_info["평균평점"],
                    "참여자수": rating_info["참여자수"],
                }
                menu_items.append(menu_info)
                count += 1  # 처리된 메뉴 카운트 증가

            # SELF 배식대 항목 찾기
            self_meal = None
            for meal in meal_list:
                if meal.get("courseTxt", "") == "SELF 배식대":
                    self_meal = meal
                    break

            # SELF 배식대 메뉴 추가
            if self_meal:
                # 기본 메뉴 정보
                course_txt = self_meal.get("courseTxt", "")
                menu_name = self_meal.get("menuName", "")
                kcal = self_meal.get("sumKcal", "")
                sub_menu_txt = self_meal.get("subMenuTxt", "").split(",")

                # 이미지 URL 구성
                photo_url = self_meal.get("photoUrl", "")
                photo_cd = self_meal.get("photoCd", "")
                image_url = f"{photo_url}{photo_cd}" if photo_url and photo_cd else None

                menu_info = {
                    "코너": course_txt,
                    "메뉴명": menu_name,
                    "칼로리": kcal,
                    "구성": sub_menu_txt,
                    "이미지": image_url,
                }
                menu_items.append(menu_info)

            # 라면 항목 찾기 (마이보글)
            ramen_meal = None
            for meal in meal_list:
                if meal.get("courseTxt", "") == "마이보글" or "[라면" in meal.get(
                    "menuName", ""
                ):
                    ramen_meal = meal
                    break

            # 라면 메뉴 추가
            if ramen_meal:
                # 기본 메뉴 정보
                course_txt = ramen_meal.get("courseTxt", "")
                menu_name = ramen_meal.get("menuName", "")
                kcal = ramen_meal.get("sumKcal", "")
                sub_menu_txt = ramen_meal.get("subMenuTxt", "").split(",")

                # 이미지 URL 구성
                photo_url = ramen_meal.get("photoUrl", "")
                photo_cd = ramen_meal.get("photoCd", "")
                image_url = f"{photo_url}{photo_cd}" if photo_url and photo_cd else None

                # 평점 정보 조회
                rating_info = self.get_menu_rating(
                    ramen_meal.get("menuDt"),
                    ramen_meal.get("hallNo"),
                    ramen_meal.get("menuCourseType"),
                    ramen_meal.get("menuMealType"),
                    ramen_meal.get("restaurantCode"),
                )

                menu_info = {
                    "코너": course_txt,
                    "메뉴명": menu_name,
                    "칼로리": kcal,
                    "구성": sub_menu_txt,
                    "이미지": image_url,
                    "평균평점": rating_info["평균평점"],
                    "참여자수": rating_info["참여자수"],
                }
                menu_items.append(menu_info)

            return {"점심": menu_items}
        except Exception as e:
            raise Exception(f"Failed to parse menu data: {str(e)}")


def main():
    # 평일(월~금)에만 스케줄러 설정
    schedule.every().monday.at("02:00").do(
        lambda: send_to_mattermost(format_menu_message(get_menu()))
    )
    schedule.every().tuesday.at("02:00").do(
        lambda: send_to_mattermost(format_menu_message(get_menu()))
    )
    schedule.every().wednesday.at("02:00").do(
        lambda: send_to_mattermost(format_menu_message_wen(get_menu()))
    )
    schedule.every().thursday.at("02:00").do(
        lambda: send_to_mattermost(format_menu_message(get_menu()))
    )
    schedule.every().friday.at("02:00").do(
        lambda: send_to_mattermost(format_menu_message_fri(get_menu()))
    )

    # 간단 메뉴 스케줄 (03:30) - 평일에만 실행
    schedule.every().monday.at("03:30").do(
        lambda: send_to_mattermost(format_simple_menu_message(get_menu()))
    )
    schedule.every().tuesday.at("03:30").do(
        lambda: send_to_mattermost(format_simple_menu_message(get_menu()))
    )
    schedule.every().wednesday.at("03:30").do(
        lambda: send_to_mattermost(format_simple_menu_message(get_menu()))
    )
    schedule.every().thursday.at("03:30").do(
        lambda: send_to_mattermost(format_simple_menu_message(get_menu()))
    )
    schedule.every().friday.at("03:30").do(
        lambda: send_to_mattermost(format_simple_menu_message(get_menu()))
    )

    # 스케줄러를 별도 스레드에서 실행
    scheduler_thread = threading.Thread(target=run_schedule)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Flask 앱 실행
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)

    get_menu()


if __name__ == "__main__":
    main()
