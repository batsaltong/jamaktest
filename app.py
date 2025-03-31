import os
import streamlit as st
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import requests

# 환경 변수 로드
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# Tor 프록시 설정
proxies = {
    'http': 'socks5h://localhost:9050',
    'https': 'socks5h://localhost:9050'
}

def extract_video_id(url):
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    if hostname in ('www.youtube.com', 'youtube.com'):
        qs = parse_qs(parsed_url.query)
        return qs.get('v', [None])[0]
    elif hostname == "youtu.be":
        return parsed_url.path.lstrip("/")
    return None

def seconds_to_hms(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def fetch_transcript(url):
    video_id = extract_video_id(url)
    if not video_id:
        return "올바른 유튜브 URL을 입력해주세요."

    try:
        # YouTubeTranscriptApi를 통해 자막을 가져옵니다.
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies)  # 프록시 추가
        try:
            transcript = transcript_list.find_transcript(['ko'])
            st.info("한국어 원본 자막을 찾았습니다.")
            transcript_data = transcript.fetch()
        except Exception as original_error:
            st.info("한국어 자막이 없으므로 영어 자막에서 자동 번역을 시도합니다.")
            transcript = transcript_list.find_transcript(['en'])
            transcript = transcript.translate('ko')
            transcript_data = transcript.fetch()

        transcript_lines = []
        for snippet in transcript_data:
            start = snippet.start
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

video_url = st.text_input("요약하고 싶은 유튜브url을 입력하셩")

if st.button("실행"):
    if not video_url:
        st.error("먼저 유튜브 URL을 입력해주셩.")
    else:
        transcript = fetch_transcript(video_url)

        if transcript is None:
            st.error("자막을 가져오는 중 오류가 발생했어 인생 망한거야.")
        elif transcript.startswith("자막을 가져오는 중 오류 발생") or transcript.startswith("올바른"):
            st.error(transcript)
        else:
            prompt_template = f"""다음은 유튜브 동영상의 전체 자막이야.
요약 영상 및 자막은 전체 영상길이의 20%를 넘지 않아야 해,
... (이하 생략) ..."""

            st.subheader("생성된 Prompt")
            st.code(prompt_template, language="python")

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
