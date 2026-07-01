from datetime import datetime
from typing import Dict, Optional, Tuple

class CheckInEngine:
    def __init__(self):
        # morning 인증 허용 시간: 05:30 ~ 07:30
        self.auth_start = (5, 30)
        self.auth_end = (7, 30)
        # morning 인증 지각 보정 허용 마감: 07:40
        self.auth_hard_end = (7, 40)
        # 휴무(주휴/월휴/특휴) 신청 허용 마감: 당일 12:00
        self.leave_end = (12, 0)

    def get_target_date(self, current_dt: datetime = None) -> str:
        """
        morning 운영에서는 제출 날짜를 그대로 목표 날짜로 사용합니다.
        """
        if current_dt is None:
            current_dt = datetime.now()
        return current_dt.strftime("%Y-%m-%d")

    def is_blackout_time(self, current_dt: datetime = None) -> bool:
        """
        인증 허용 시간(05:30 ~ 07:30) 외 시간인지 확인합니다.
        """
        if current_dt is None:
            current_dt = datetime.now()
        now_hm = (current_dt.hour, current_dt.minute)
        return not (self.auth_start <= now_hm <= self.auth_end)

    def is_action_allowed(self, action_type: str, current_dt: datetime = None) -> bool:
        """
        액션 종류별 허용 시간 여부를 반환합니다.

        action_type:
        - "status": 항상 허용
        - "week_off"/"month_off"/"special_off": 당일 12:00 이전 허용
        - 그 외 인증 액션: morning 인증 시간(05:30 ~ 07:40) 내 허용
        """
        if current_dt is None:
            current_dt = datetime.now()

        if action_type == "status":
            return True

        now_hm = (current_dt.hour, current_dt.minute)
        if action_type in ("week_off", "month_off", "special_off"):
            return now_hm < self.leave_end
        return self.auth_start <= now_hm <= self.auth_hard_end

    def parse_ocr_datetime(self, target_date_str: str, end_time_str: str) -> Optional[datetime]:
        """OCR 종료시각 문자열을 datetime으로 변환합니다."""
        if " " in end_time_str:
            try:
                return datetime.strptime(end_time_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

        try:
            h, m = map(int, end_time_str.split(":"))
            base_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            return base_date.replace(hour=h, minute=m, second=0)
        except ValueError:
            return None

    def validate_ocr_time(self, target_date_str: str, end_time_str: str, auth_minutes: int, target_minutes: int) -> Tuple[bool, bool, bool]:
        """
        OCR로 추출된 종료 시간이 허가된 시간(당일 05:30 ~ 07:40)인지 검증합니다.
        Returns: (is_fake_date, is_absent_due_to_late, is_ontime)
        - is_fake_date: 아예 오래전 사진이나 범위 밖 사진인지 여부
        - is_absent_due_to_late: morning 정책에서는 사용하지 않음(False 고정)
        - is_ontime: 허용 구간 내 종료 여부
        """
        ocr_dt = self.parse_ocr_datetime(target_date_str, end_time_str)
        if ocr_dt is None:
            return True, False, False

        target_base = datetime.strptime(target_date_str, "%Y-%m-%d")
        valid_start = target_base.replace(hour=5, minute=30, second=0)
        valid_end = target_base.replace(hour=7, minute=40, second=0)

        # 아예 시간 범위 (05:30 ~ 07:30) 바깥인 경우 -> 허위 사진
        if ocr_dt < valid_start or ocr_dt > valid_end:
            return True, False, False

        # 허용 범위 내 종료
        return False, False, True

    def apply_late_minute_adjustment(self, target_date_str: str, end_time_str: str, auth_minutes: int) -> Tuple[int, int]:
        """
        07:30 이후 종료분은 지각 분만큼 인증 시간을 차감합니다.
        Returns: (adjusted_auth_minutes, deducted_minutes)
        """
        ocr_dt = self.parse_ocr_datetime(target_date_str, end_time_str)
        if ocr_dt is None:
            return auth_minutes, 0

        target_base = datetime.strptime(target_date_str, "%Y-%m-%d")
        penalty_start = target_base.replace(hour=7, minute=30, second=0)
        if ocr_dt <= penalty_start:
            return auth_minutes, 0

        deducted = int((ocr_dt - penalty_start).total_seconds() // 60)
        adjusted = max(0, auth_minutes - deducted)
        return adjusted, deducted

    def is_within_deadline(self, current_dt: datetime = None) -> bool:
        # 하위호환 유지용 (이제 validate_ocr_time이 완전히 대체함)
        return True

    def process_leave_request(self, user_record: Dict, leave_type: str) -> Tuple[bool, str, float]:
        """
        휴무 요청을 검증합니다.
        leave_type: '주휴', '반휴', '월휴'
        리턴: (승인여부-bool, 챗봇출력메시지-str, 차감량-float)
        """
        # 구글 시트에서 넘어온 데이터 파싱
        weekly_leave_str = str(user_record.get("주간휴무", "0"))
        monthly_leave_str = str(user_record.get("남은월휴", "0"))
        
        try:
            weekly_leave = float(weekly_leave_str)
        except ValueError:
            weekly_leave = 0.0
            
        try:
            monthly_leave = float(monthly_leave_str) 
        except ValueError:
            monthly_leave = 0.0

        if leave_type == "반휴":
            if weekly_leave < 0.5:
                return False, "잔여 주간 휴무가 부족합니다. 이번 주 휴무를 모두 사용하셨습니다.", 0.0
            return True, "반휴가 적용되었습니다. 오늘 목표 시간은 30분으로 고정됩니다.\n사진을 전송해 주세요!", 0.5
            
        elif leave_type == "주휴":
            if weekly_leave < 1.0:
                return False, "잔여 주간 휴무가 부족합니다. 이번 주 휴무를 모두 사용하셨습니다.", 0.0
            return True, "주휴 처리가 완료되었습니다. 오늘 하루 푹 쉬세요! (자동 PASS)", 1.0
            
        elif leave_type == "월휴":
            if monthly_leave < 1.0:
                return False, "남은 월휴가 없습니다.", 0.0
            return True, "월휴 처리가 완료되었습니다. 푹 쉬세요! (자동 PASS)", 1.0
        
        return False, f"알 수 없는 휴가 타입입니다: {leave_type}", 0.0

check_in_engine = CheckInEngine()
