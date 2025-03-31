import os
import streamlit as st
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 환경 변수 로드
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")



def extract_video_id(url):
    """
    유튜브 URL에서 영상 ID를 추출하는 함수
    예:
      https://www.youtube.com/watch?v=dQw4w9WgXcQ  --> 'dQw4w9WgXcQ'
      https://youtu.be/dQw4w9WgXcQ                 --> 'dQw4w9WgXcQ'
    """
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    if hostname in ('www.youtube.com', 'youtube.com'):
        qs = parse_qs(parsed_url.query)
        return qs.get('v', [None])[0]
    elif hostname == "youtu.be":
        return parsed_url.path.lstrip("/")
    return None

def seconds_to_hms(seconds):
    """초 단위의 시간을 HH:MM:SS 형식으로 변환하는 함수"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def fetch_transcript(url):
    """
    유튜브 영상 URL을 받아 자막을 가져와 각 자막 항목에 대해
    [시작시간 ~ 종료시간] 자막내용 형식의 텍스트를 리턴한다.
    만약 한국어 자막이 없으면 영어 자막을 자동 번역('ko')하여 사용한다.
    """
    video_id = extract_video_id(url)
    if not video_id:
        return "올바른 유튜브 URL을 입력해주세요."

    try:
        # 영상의 모든 자막 목록을 가져옵니다.
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            # 먼저 한국어 원본 자막("ko")을 찾습니다.
            transcript = transcript_list.find_transcript(['ko'])
            st.info("한국어 원본 자막을 찾았습니다.")
            transcript_data = transcript.fetch()
        except Exception as original_error:
            # 한국어 자막이 없으면 영어("en") 자막에서 자동 번역을 시도합니다.
            st.info("한국어 자막이 없으므로 영어 자막에서 자동 번역을 시도합니다.")
            transcript = transcript_list.find_transcript(['en'])
            transcript = transcript.translate('ko')
            transcript_data = transcript.fetch()

        # 각 자막 항목을 형식에 맞게 문자열로 조합합니다.
        transcript_lines = []
        for snippet in transcript_data:
            start = snippet.start  # 객체의 속성을 사용
            # 일부 자막은 'duration' 속성이 없는 경우가 있으므로 안전하게 처리
            duration = snippet.duration if hasattr(snippet, "duration") else 0
            end = start + duration
            start_str = seconds_to_hms(start)
            end_str = seconds_to_hms(end)
            transcript_lines.append(f"[{start_str} ~ {end_str}] {snippet.text}")
        transcript_text = "\n".join(transcript_lines)
        return transcript_text

    except Exception as e:
        return "자막을 가져오는 중 오류 발생: " + str(e)

# streamlit 앱 구성
st.title("유튜브 영상 요약을 호로록?!?!")

# 유튜브 URL 입력칸 (라벨: "요약하고 싶은 유튜브url을 입력하시오")
video_url = st.text_input("요약하고 싶은 유튜브url을 입력하셩")

if st.button("실행"):
    if not video_url:
        st.error("먼저 유튜브 URL을 입력해주셩.")
    else:
        # 유튜브 URL로부터 자막을 가져옵니다.
        transcript = fetch_transcript(video_url)

        # transcript가 None이면 에러 처리
        if transcript is None:
            st.error("자막을 가져오는 중 오류가 발생했어 인생 망한거야.")
        # transcript가 오류 메시지를 담고 있는 경우도 처리
        elif transcript.startswith("자막을 가져오는 중 오류 이제 진짜 망한거야") or transcript.startswith("올바른"):
            st.error(transcript)
        else:
            # lecture_prompt_template 구성
            prompt_template = f"""다음은 유튜브 동영상의 전체 자막이야.
요약 영상 및 자막은 전체 영상길이의 20%를 넘지 않아야 해,

요약할 때는 다음 기준을 따르세요:
- 각 전환점을 기준으로 핵심 내용과 주요 이슈를 골라 요약해.
- 핵심 문맥은 영상에서 가장 중요한 메시지와 정보, 그리고 논리 흐름을 유지하는 문장들이야.
- 가능한 한 요약에 필요한 정보만 포함하고, 불필요한 잡담, 인사말, 예시 반복은 생략해줘.
- 데이터는 유튜브 자막으로, 타임스탬프가 포함되어 있어.
- 원하는 요청사항: 이 전체 자막을 20% 이내 분량으로 줄이고 싶어.
- 필요한 내용들의 타임스탬프만 추출하여, 그 총합이 전체 영상 길이의 20%를 넘지 않아야 해.
- 연속적인 구간끼리 자연스럽게 묶을 수 있지만, 개별 구간에 중요한 내용이 있다면 반드시 묶어야 하는 것은 아니야. 
각 구간이 개별적으로 중요한 경우 그대로 선택할 수 있도록 유연하게 고려해.
- 추출된 구간들은 자연스럽게 이어지는 흐름으로 표시해야 해.

응답은 다음 JSON 형식으로 제공해주세요:
{{
    "segments": [
        {{
            "start_time": float,  // 구간 시작 시간(초)
            "end_time": float,    // 구간 종료 시간(초)
            "duration": float,   // 구간 길이(초)
            "content": str // 구간에서의 내용(문자열)

        }},
        // 추가 구간...
    ]
}}

다음은 분석할 영상의 자막입니다:
{transcript}"""

            st.subheader("생성된 Prompt")
            st.code(prompt_template, language="python")

           

            # ChatOpenAI 모델 초기화 (OpenAI Chat API 사용)
            llm = ChatOpenAI(
                model_name="o3-mini",
                openai_api_key=api_key,
            )

            
            st.info("LangChain을 사용해 LLM 모델에 프롬프트를 전달 중입니다. 잠시만 기다려주세요...")

            try:
                response = llm.invoke(prompt_template)
                st.subheader("LLM 모델 응답 결과")
                st.text_area("응답", response.content, height=300)
            except Exception as e:
                st.error("LLM 모델 호출 중 오류 발생: " + str(e))