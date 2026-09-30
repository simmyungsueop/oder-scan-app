import streamlit as st
from PIL import Image
from google import genai
import datetime

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="후가공 자동 판별 시스템",
    page_icon="📦",
    layout="centered"
)

# 커스텀 UI 스타일
st.markdown("""
    <style>
    .main-header { font-size: 22px; font-weight: bold; color: #1E3A8A; text-align: center; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-header'>📦 발주서 AI 스캔 및 후가공 판별</div>", unsafe_allow_html=True)

# 2. Gemini API Client 설정 (secrets.toml 사용으로 보안 강화)
@st.cache_resource
def get_genai_client():
    try:
        # secrets.toml 파일에서 안전하게 키를 가져옵니다.
        api_key = st.secrets["GEMINI_API_KEY"]
        return genai.Client(api_key=api_key)
    except Exception:
        return None

client = get_genai_client()

# 3. AI 분석 및 자동 정리 함수
def analyze_order_sheet(image):
    if not client:
        return "❌ API Key가 설정되지 않았습니다. `.streamlit/secrets.toml` 설정을 확인해주세요."
    
    try:
        # 공장 및 현장에 맞춘 정밀 지침 프롬프트
        prompt = """
        당신은 20년 경력의 인쇄 및 후가공 전문 공장장입니다. 
        제공된 발주서(작업지시서) 이미지를 정밀 분석하여 현장 작업자가 즉시 파악할 수 있도록 주요 항목을 정리해 주세요.

        [분석 가이드라인]
        1. 주요 후가공 항목: 금박/은박, 에폭시, UV코팅, 무광/유광 코팅, 톰슨(형압/도송), 오시, 미싱, 중전철 등
        2. 특이사항/주의사항: 수량 단위, 인쇄 종이 재질, 용지 결 방향, 공정상 주의할 점 2~3줄 요약
        3. 손글씨나 도장 등으로 글자가 가려져 불명확한 경우, 문맥상 추정하여 작성하고 단어 뒤에 [추정] 표시를 붙여주세요.

        [응답 양식]
        다음 서식에 맞추어 깔끔하게 마크다운 형태로 출력하세요:

        ### 📋 발주서 분석 결과
        - **거래처명:** 
        - **품목/작업명:** 
        - **수량:** 
        - **후가공 종류:** 
        
        ---
        #### ⚠️ 공장장 작업 주의사항
        (공정 관점에서 주의할 점을 요점만 정리)
        """
        
        # Gemini Vision 모델을 통한 이미지+텍스트 분석
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )
        return response.text
    except Exception as e:
        return f"❌ 분석 중 오류가 발생했습니다: {str(e)}"

# 4. 탭 구성 (카메라 스캔 / 파일 업로드)
tab1, tab2 = st.tabs(["📷 휴대폰 카메라 스캔", "📁 파일 업로드"])

# --- [TAB 1] 카메라 촬영 ---
with tab1:
    st.caption("스마트폰 카메라로 발주서나 작업지시서를 촬영해 주세요.")
    img_file = st.camera_input("발주서 촬영")
    
    if img_file is not None:
        image = Image.open(img_file)
        st.image(image, caption="촬영된 발주서 이미지", use_container_width=True)
        
        # 분석 실행 버튼
        if st.button("🔍 촬영된 발주서 분석하기", key="btn_camera"):
            with st.spinner("AI가 발주서를 분석하고 주요 포인트를 정리 중입니다..."):
                result = analyze_order_sheet(image)
                st.success("✅ AI 분석 완료")
                st.markdown(result)

# --- [TAB 2] 파일 업로드 ---
with tab2:
    st.caption("저장된 발주서 이미지(JPG, PNG)를 선택해 주세요.")
    uploaded_file = st.file_uploader("발주서 이미지 선택", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption="업로드된 발주서 이미지", use_container_width=True)
        
        # 분석 실행 버튼
        if st.button("🔍 업로드된 발주서 분석하기", key="btn_upload"):
            with st.spinner("AI가 발주서를 분석하고 주요 포인트를 정리 중입니다..."):
                result = analyze_order_sheet(image)
                st.success("✅ AI 분석 완료")
                st.markdown(result)

st.markdown("---")
st.caption(f"시스템 상태: 보안 연결 완료 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")