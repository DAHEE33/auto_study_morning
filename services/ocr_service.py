import os
import re
from google.cloud import vision
from core.config import settings
from typing import Optional, Tuple

class OCRService:
    def __init__(self):
        self.is_mock = False
        self.client = None
        
        try:
            # Set environment variable for Google Cloud SDK auth
            if settings.credentials_path.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(settings.credentials_path)
                self.client = vision.ImageAnnotatorClient()
            else:
                self.is_mock = True
        except Exception as e:
            print(f"⚠️ Google Cloud Vision init failed: {e}. Running in MOCK Mode.")
            self.is_mock = True

    def _parse_duration_to_minutes(self, text: str) -> int:
        """'X시간 Y분' 또는 'X시간' 또는 'Y분' 형태의 텍스트를 파싱하여 분 단위로 반환"""
        text = text.replace(" ", "")
        match = re.search(r'(?:(\d+)시간)?(?:(\d+)분)?', text)
        if not match:
            return 0
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        return h * 60 + m

    def extract_time_from_image(self, image_path: str) -> Tuple[Optional[str], int, int, str]:
        """
        구루미 UI 이미지에서 텍스트를 파싱하여 공부 종료 시각과 순공 시간을 추출합니다.
        Returns:
            (종료시각 "YYYY-MM-DD HH:MM:SS" 또는 "HH:MM", 당일시간(분), 누적시간(분), OCR원문텍스트)
        """
        if self.is_mock:
            # Mock 데이터 반환 (테스트용)
            print(f"[MOCK] OCR 추출 진행: {image_path}")
            return "23:55", 120, 8550, "dev_user 2시간 142시간 30분 2026-04-15 20:49:02"
            
        try:
            with open(image_path, "rb") as image_file:
                content = image_file.read()

            image = vision.Image(content=content)
            # OCR 엔진 호출
            response = self.client.text_detection(image=image)
            texts = response.text_annotations
            
            if not texts:
                print("[OCR] 텍스트 감지 실패: 이미지에서 텍스트를 찾을 수 없음")
                return None, 0, 0, ""
                
            full_text = texts[0].description
            print(f"[OCR] 원문 텍스트:\n{full_text}\n---")
            
            # 공백/줄바꿈 정규화
            normalized_text = re.sub(r'\s+', ' ', full_text)
            
            # 1. 종료 시각(타임스탬프) 파싱
            # "2026-07-06 06:17:26" 형식
            end_time = None
            dt_match = re.search(r'(\d{4}[-./]\d{2}[-./]\d{2})\s*(\d{2}:\d{2}:\d{2})', normalized_text)
            if dt_match:
                date_part = dt_match.group(1).replace('.', '-').replace('/', '-')
                time_part = dt_match.group(2)
                end_time = f"{date_part} {time_part}"
                print(f"[OCR] 종료시각 감지: {end_time}")
            else:
                # HH:MM:SS 또는 HH:MM 단독 형식
                hm_match = re.findall(r'\b(\d{1,2}:\d{2}(?::\d{2})?)\b', normalized_text)
                if hm_match:
                    end_time = hm_match[-1]
                    print(f"[OCR] 종료시각 감지 (시간만): {end_time}")

            # 2. 당일시간, 누적시간 파싱 ("X시간 Y분" 형태)
            # 더 유연한 패턴: 공백, O/0 혼동 대응
            duration_pattern = r'(\d+)\s*시\s*간\s*(\d+)\s*분|(\d+)\s*시\s*간|(\d+)\s*분'
            duration_matches = re.findall(duration_pattern, normalized_text)
            
            durations = []
            for match in duration_matches:
                if match[0] and match[1]:  # X시간 Y분
                    minutes = int(match[0]) * 60 + int(match[1])
                elif match[2]:  # X시간
                    minutes = int(match[2]) * 60
                elif match[3]:  # Y분
                    minutes = int(match[3])
                else:
                    continue
                durations.append(minutes)
            
            print(f"[OCR] 감지된 시간들(분): {durations}")
            
            daily_mnts = 0
            total_mnts = 0
            
            if len(durations) == 0:
                # 대체 패턴 시도: 숫자+시간/분 형태
                alt_pattern = r'(\d+)\s*시간\s*(\d+)\s*분|(\d+)\s*시간|(\d+)\s*분'
                alt_matches = re.findall(alt_pattern, full_text)
                for match in alt_matches:
                    if match[0] and match[1]:
                        minutes = int(match[0]) * 60 + int(match[1])
                    elif match[2]:
                        minutes = int(match[2]) * 60
                    elif match[3]:
                        minutes = int(match[3])
                    else:
                        continue
                    durations.append(minutes)
                print(f"[OCR] 대체 패턴으로 감지된 시간들(분): {durations}")
            
            if len(durations) >= 2:
                # 두 개 이상: 작은 값=당일, 큰 값=누적
                daily_mnts = min(durations[0], durations[1])
                total_mnts = max(durations[0], durations[1])
            elif len(durations) == 1:
                daily_mnts = durations[0]
            
            print(f"[OCR] 최종 파싱 결과 - 종료시각: {end_time}, 당일: {daily_mnts}분, 누적: {total_mnts}분")
            return end_time, daily_mnts, total_mnts, full_text
            
        except Exception as e:
            print(f"OCR Error: {e}")
            import traceback
            traceback.print_exc()
            return None, 0, 0, ""

ocr_service = OCRService()
