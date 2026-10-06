# -*- coding: utf-8 -*-
import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageEnhance, ImageOps
import io
import datetime
import json
import re
import os
import time

# ---------------------------------------------------------
# 0. 로컬 파일 영구 저장/로드 관련 설정
# ---------------------------------------------------------
DB_FILE_PATH = "orders_db.json"

def load_orders():
    """서버 로컬 JSON 파일에서 발주서 DB를 불러옵니다."""
    if os.path.exists(DB_FILE_PATH):
        try:
            with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_orders(data):
    """발주서 DB를 서버 로컬 JSON 파일에 저장합니다."""
    try:
        with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"데이터 저장 중 오류 발생: {e}")

# ---------------------------------------------------------
# 1. 고해상도 & 이미지 회전/대비 보정 최적화 함수
# ---------------------------------------------------------
def prepare_image_for_analysis(image, max_size=(2500, 2500)):
    """
    카메라 메타데이터 기반 스마트 자동 회전 및 명암 대비 강화
    모바일 촬영 시 대용량 파일 리사이징 및 메모리 오버플로우 방지
    """
    # 1) 카메라 orientation EXIF 데이터에 따른 바른 방향 회전
    img = ImageOps.exif_transpose(image)
    
    # 2) 해상도 최적화
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    # 3) 대비(Contrast) 강화 (1.6배) - 글자와 배경 명확 분리
    enhancer_contrast = ImageEnhance.Contrast(img)
    img = enhancer_contrast.enhance(1.6)
    
    # 4) 선명도(Sharpness) 강화 (1.5배)
    enhancer_sharpness = ImageEnhance.Sharpness(img)
    img = enhancer_sharpness.enhance(1.5)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return Image.open(buffer)

# ---------------------------------------------------------
# 2. 페이지 및 세션 초기화
# ---------------------------------------------------------
st.set_page_config(
    page_title="인쇄 스마트 공정 & 후가공 검수 시스템",
    page_icon="🏭",
    layout="wide"
)

if "order_database" not in st.session_state:
    st.session_state.order_database = load_orders()

if "current_inspected_order" not in st.session_state:
    st.session_state.current_inspected_order = None

def get_genai_client():
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
        if api_key:
            return genai.Client(api_key=api_key.strip())
    except Exception:
        pass
    return None

def parse_json_safely(raw_text):
    if not raw_text:
        return None
    
    cleaned = re.sub(r'```(?:json)?', '', raw_text).strip('` \n\r')
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    fixed = re.sub(r'(["\d\]}])\s*\n\s*(["{])', r'\1,\n\2', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None

# ---------------------------------------------------------
# 3. Gemini API 호출 로직
# ---------------------------------------------------------
def call_gemini_api_fast(image, prompt):
    client = get_genai_client()
    if not client:
        return None, "❌ GEMINI_API_KEY가 설정되지 않았습니다. .streamlit/secrets.toml을 확인해 주세요."
    
    optimized_img = prepare_image_for_analysis(image)
    
    # 올바른 Gemini 모델명 목록으로 수
   candidate_models = [
        "gemini-2.5-flash",
        "gemini-1.5-flash"
    ]
    
    last_error = None
    
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[optimized_img, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            return response.text, None
        except Exception as e:
            last_error = str(e)
            if "404" in last_error or "NOT_FOUND" in last_error:
                continue
            elif "503" in last_error or "UNAVAILABLE" in last_error:
                time.sleep(1.5)
                continue
            else:
                break

    return None, f"❌ API 호출 중 오류가 발생했습니다: {last_error}"
# ---------------------------------------------------------
# 4. 메인 UI 레이아웃
# ---------------------------------------------------------
st.title("🏭 인쇄 스마트 공정 & 후가공 검수 시스템")
st.markdown("---")

tab_order, tab_inspect, tab_status = st.tabs([
    "1️⃣ [STEP 1] 발주서 등록/분석", 
    "2️⃣ [STEP 2] 인쇄물 스캔 & 발주서 자동 매칭", 
    "3️⃣ [STEP 3] 공정 진행 현황판 및 수정"
])

# ---------------------------------------------------------
# TAB 1: 발주서 등록 및 저장
# ---------------------------------------------------------
with tab_order:
    st.header("📋 1단계: 작업 발주서 등록")
    st.caption("AI 기반 고정밀 분석으로 발주서를 영구 저장합니다.")

    input_method_order = st.radio(
        "발주서 입력 방식을 선택하세요:",
        ["📂 이미지 파일 업로드", "📷 카메라로 직접 촬영"],
        key="radio_order_input"
    )

    order_source = None
    if input_method_order == "📂 이미지 파일 업로드":
        order_source = st.file_uploader("발주서 이미지 업로드", type=["jpg", "jpeg", "png"], key="order_upload")
    else:
        order_source = st.camera_input("발주서를 카메라 중앙에 맞추고 촬영하세요", key="order_camera")

    if order_source:
        order_img = Image.open(order_source)
        col1, col2 = st.columns([1, 1])

        with col1:
            st.image(order_img, caption="등록할 발주서 이미지", use_container_width=True)

        with col2:
            if st.button("⚡ 발주서 분석 및 등록", key="btn_parse_order"):
                prompt = """
                You are an expert OCR model specializing in Korean printing purchase order forms.

                CRITICAL STEP:
                Check if the document image is upside down (180 degrees rotated) or sideways. If it is upside down or misoriented, mentally rotate it to the correct upright reading orientation FIRST before extracting text.

                Extraction Rules:
                1. client_name: Exact company, client, or binding shop name (제본처/발주처/거래처, e.g., 'P&M 제본', 'SSE'). Look for bottom or top section headers.
                2. item_name: Read exact book title or item name written in the form (e.g. 'Quick Deli A1', '퀵 델리 A1'). Do not invent names.
                3. quantity: Read quantity accurately (e.g., 1,000부, 500개).
                4. post_processing: Read coating info (Glossy/유광, Matte/무광, UV, Foil, etc.).
                5. key_warnings: Read handwritten notes, red ink marks, or special warnings.

                Return STRICT JSON ONLY in KOREAN:
                {
                  "client_name": "거래처/제본처명",
                  "item_name": "도서명/품목명",
                  "quantity": "수량",
                  "post_processing": "코팅/후가공",
                  "key_warnings": "주의사항"
                }
                """
                with st.spinner("🚀 고정밀 회전/OCR 분석 중..."):
                    raw_res, err = call_gemini_api_fast(order_img, prompt)
                    
                    if err:
                        st.error(err)
                    else:
                        data = parse_json_safely(raw_res)
                        if data:
                            client = (data.get('client_name') or '미지정거래처').strip()
                            item = (data.get('item_name') or '미지정품목').strip()
                            
                            if client == '미지정거래처' and item == '미지정품목':
                                doc_id = f"발주서_{datetime.datetime.now().strftime('%M%S')}"
                            else:
                                doc_id = f"{client}_{item}"
                            
                            data["client_name"] = client
                            data["item_name"] = item
                            data["status"] = "대기중"
                            data["registered_at"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                            
                            st.session_state.order_database[doc_id] = data
                            save_orders(st.session_state.order_database)
                            
                            st.success(f"✅ [{doc_id}] 발주서 영구 저장 완료!")
                            
                            st.subheader("📄 등록된 발주서 요약")
                            st.markdown(f"• **제본처(거래처):** {client}")
                            st.markdown(f"• **책 제목(품목명):** {item}")
                            st.markdown(f"• **수량:** {data.get('quantity', '-')}")
                            st.markdown(f"• **코팅/후가공:** {data.get('post_processing', '-')}")
                            st.markdown(f"• **주의사항:** {data.get('key_warnings', '-')}")
                        else:
                            st.error("분석 실패: JSON 형식을 파싱할 수 없습니다.")
                            st.text(raw_res)

# ---------------------------------------------------------
# TAB 2: 실제 인쇄물 스캔 및 자동 매칭/검수
# ---------------------------------------------------------
with tab_inspect:
    st.header("🔎 2단계: 실제 인쇄물 스캔 및 매칭")
    st.caption("출력된 인쇄물을 검수하여 저장된 DB의 상태를 업데이트합니다.")

    if not st.session_state.order_database:
        st.warning("⚠ 저장된 발주서가 없습니다. 1단계에서 먼저 발주서를 등록해 주세요.")
    else:
        input_method_inspect = st.radio(
            "인쇄물 입력 방식을 선택하세요:",
            ["📂 이미지 파일 업로드", "📷 카메라로 직접 촬영"],
            key="radio_inspect_input"
        )

        inspect_source = None
        if input_method_inspect == "📂 이미지 파일 업로드":
            inspect_source = st.file_uploader("인쇄물/후가공 결과물 이미지 업로드", type=["jpg", "jpeg", "png"], key="inspect_upload")
        else:
            inspect_source = st.camera_input("인쇄물을 카메라에 대고 촬영하세요", key="inspect_camera")

        if inspect_source:
            print_img = Image.open(inspect_source)
            c1, c2 = st.columns([1, 1])

            with c1:
                st.image(print_img, caption="검수할 실물 인쇄물", use_container_width=True)

            with c2:
                if st.button("⚡ 매칭 및 검수", key="btn_match"):
                    db_summary = json.dumps(st.session_state.order_database, ensure_ascii=False)
                    
                    prompt = f"""
                    Compare the printed product image with the registered Order Database below.

                    Registered DB:
                    {db_summary}

                    Inspection Steps:
                    1. Read printed title and coating texture (Glossy vs Matte).
                    2. Match with the most suitable key in DB.
                    3. Check if coating and title match properly.

                    Return STRICT JSON in Korean:
                    {{
                      "matched_key": "Exact matched key from DB",
                      "match_confidence": "High / Medium / Low",
                      "inspection_result": "PASS 또는 FAIL",
                      "defect_summary": "검수 결과 및 상세 판정 이유 (자연스러운 한국어로 작성)"
                    }}
                    """

                    with st.spinner("🚀 고정밀 매칭 검수 중..."):
                        raw_res, err = call_gemini_api_fast(print_img, prompt)

                        if err:
                            st.error(err)
                        else:
                            res_data = parse_json_safely(raw_res)
                            if res_data:
                                matched_key = res_data.get("matched_key")
                                inspection_result = res_data.get("inspection_result", "FAIL")
                                
                                if matched_key in st.session_state.order_database:
                                    order_info = st.session_state.order_database[matched_key]
                                    
                                    order_info["status"] = "완료(합격)" if inspection_result == "PASS" else "재작업(불합격)"
                                    order_info["inspection_note"] = res_data.get("defect_summary", "")
                                    
                                    save_orders(st.session_state.order_database)
                                    
                                    st.success(f"🎯 매칭 성공 및 업데이트 완료! ID: [{matched_key}]")
                                    
                                    st.subheader("📄 매칭된 발주서 정보")
                                    st.markdown(f"• **제본처(거래처):** {order_info.get('client_name')}")
                                    st.markdown(f"• **책 제목:** {order_info.get('item_name')}")
                                    st.markdown(f"• **수량:** {order_info.get('quantity')}")
                                    st.markdown(f"• **코팅 형식:** {order_info.get('post_processing')}")
                                    st.markdown(f"• **주의사항:** {order_info.get('key_warnings')}")
                                    
                                    st.markdown("---")
                                    st.subheader("📊 검수 결과")
                                    if inspection_result == "PASS":
                                        st.success("✅ **검수 결과:** 합격 (PASS)")
                                    else:
                                        st.error("❌ **검수 결과:** 불합격 (FAIL)")
                                    st.info(f"**검수 의견:** {res_data.get('defect_summary', '특이사항 없음')}")
                                else:
                                    st.warning("⚠ 일치하는 발주서를 찾을 수 없습니다.")
                                    st.write(res_data)
                            else:
                                st.error("결과 분석 중 오류가 발생했습니다.")
                                st.text(raw_res)

# ---------------------------------------------------------
# TAB 3: 공정 진행 현황판 및 데이터 직접 수정/삭제 기능
# ---------------------------------------------------------
with tab_status:
    st.header("📊 3단계: 전체 공정 현황판 및 데이터 수정")
    st.caption("저장된 발주서 데이터의 오타를 직접 수정하거나 삭제할 수 있습니다.")

    if not st.session_state.order_database:
        st.info("현재 저장된 발주서 데이터가 없습니다.")
    else:
        for doc_id in list(st.session_state.order_database.keys()):
            info = st.session_state.order_database.get(doc_id)
            if not info:
                continue
                
            with st.expander(f"📌 [{info.get('status')}] {doc_id} (등록일: {info.get('registered_at')})"):
                col_a, col_b = st.columns(2)
                
                with col_a:
                    st.markdown("##### 📄 기존 정보")
                    st.markdown(f"• **제본처(거래처):** {info.get('client_name')}")
                    st.markdown(f"• **책 제목:** {info.get('item_name')}")
                    st.markdown(f"• **수량:** {info.get('quantity')}")
                    st.markdown(f"• **코팅/후가공:** {info.get('post_processing')}")
                    st.markdown(f"• **주의사항:** {info.get('key_warnings')}")
                    if "inspection_note" in info:
                        st.markdown(f"• **검수 의견:** {info.get('inspection_note')}")

                with col_b:
                    st.markdown("##### ✏ 데이터 수정 / 삭제")
                    new_client = st.text_input("제본처(거래처) 수정", value=info.get('client_name', ''), key=f"edit_client_{doc_id}")
                    new_item = st.text_input("책 제목(품목명) 수정", value=info.get('item_name', ''), key=f"edit_item_{doc_id}")
                    new_post = st.text_input("코팅/후가공 수정", value=info.get('post_processing', ''), key=f"edit_post_{doc_id}")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("💾 정보 저장", key=f"save_{doc_id}"):
                            new_doc_id = f"{new_client}_{new_item}"
                            
                            info['client_name'] = new_client
                            info['item_name'] = new_item
                            info['post_processing'] = new_post
                            
                            if new_doc_id != doc_id:
                                st.session_state.order_database[new_doc_id] = info
                                if doc_id in st.session_state.order_database:
                                    del st.session_state.order_database[doc_id]
                            else:
                                st.session_state.order_database[doc_id] = info
                                
                            save_orders(st.session_state.order_database)
                            st.toast(f"✅ [{new_doc_id}] 성공적으로 수정 및 저장되었습니다!", icon="💾")
                            time.sleep(0.8)
                            st.rerun()

                    with btn_col2:
                        if st.button("🗑 항목 삭제", key=f"del_{doc_id}"):
                            if doc_id in st.session_state.order_database:
                                del st.session_state.order_database[doc_id]
                            save_orders(st.session_state.order_database)
                            st.toast(f"🗑 [{doc_id}] 삭제되었습니다.", icon="🗑")
                            time.sleep(0.8)
                            st.rerun()
