import hashlib
import pandas as pd, streamlit as st
from recommend import normalize, recommend, identify_ingredients, PANTRY_ALL, DEFAULT_PANTRY

MAX_FREE_PHOTOS = 5      # 每位訪客(每次開啟網頁)最多可用網站金鑰辨識幾張照片

st.set_page_config(page_title="智慧冰箱食譜推薦", page_icon="🧊")
st.title("智慧冰箱食譜推薦")

@st.cache_data
def load(): return pd.read_json('recipes_clean.json')

@st.cache_data(show_spinner="辨識中...")
def identify(b, mt, _key=None): return identify_ingredients(b, mt, api_key=_key)

df = load()
if 'seen_photos' not in st.session_state:
    st.session_state.seen_photos = set()

text = st.text_input("輸入食材(空格或頓號分隔)", "")

with st.expander("📷 用照片辨識食材"):
    own_key = st.text_input("使用自己的 Gemini 金鑰(選填,填了就不受次數限制)", type="password")
    photo = st.file_uploader("上傳冰箱或食材照片", type=["jpg", "jpeg", "png", "jfif"])

if photo:
    b = photo.getvalue()
    h = hashlib.md5(b).hexdigest()
    is_new = h not in st.session_state.seen_photos
    if is_new and not own_key and len(st.session_state.seen_photos) >= MAX_FREE_PHOTOS:
        st.warning(f"本次使用的免費照片辨識次數已用完(上限 {MAX_FREE_PHOTOS} 張)。"
                   "可以改用文字輸入,或在上方填入自己的 Gemini 金鑰。")
    else:
        mt = "image/png" if (photo.name or "").lower().endswith(".png") else "image/jpeg"
        try:
            text += " " + identify(b, mt, _key=own_key or None)
            st.session_state.seen_photos.add(h)
        except Exception as e:
            st.error(f"圖片辨識失敗:{e}")

have = normalize(text)
st.write("已辨識食材:", "、".join(have) or "(無)")

with st.expander("🧂 調味料設定(勾選家裡有的)"):
    pantry = st.multiselect("沒勾選的調味料,會在食譜裡標示為缺料", PANTRY_ALL, default=DEFAULT_PANTRY)
    strict = st.checkbox("只推薦「調味料我都有」的食譜", value=False)

miss_n = st.slider("最多可缺幾樣主食材", 0, 4, 2)
top_n = st.slider("最多顯示幾道菜", 5, 50, 20)
must = st.multiselect("一定要用到的食材(選填)", have) if have else []

if have:
    res = recommend(df, have, max_missing=miss_n, top_n=top_n, pantry=pantry,
                    strict_pantry=strict, must_use=must)
    if res.empty:
        st.warning("找不到符合的食譜,試著放寬缺料數、取消調味料限制,或取消「一定要用到」的食材")
    else:
        st.caption(f"共 {res.attrs.get('total', len(res))} 道符合,顯示 {len(res)} 道。"
                   "排序:越能用到你輸入的食材、缺料越少越前面,並讓相似的食譜分散開。")
    for _, r in res.iterrows():
        row = df.loc[r['idx']]
        miss = '、'.join(r['missing']) or '無'
        mp = '、'.join(r['missing_pantry'])
        mm = '、'.join(r['missing_minor'])
        title = (f"{r['name']}｜主食材缺:{miss}" + (f"｜副食材缺:{mm}" if mm else "")
                 + (f"｜其他缺:{mp}" if mp else "") + f"｜難度{r['difficulty']}｜{r['kcal']}kcal")
        with st.expander(title):
            st.write("已有:", "、".join(r['have']))
            if mm: st.write("副食材(可省略或替換,味道可能不同):", mm)
            if mp: st.write("需要補的調味料:", mp)
            st.write("**用量**")
            st.write("\n".join(f"- {a}" for a in row['amounts_tw']))
            st.write("**步驟**")
            st.write("\n".join(f"{i}. {s}" for i, s in enumerate(row['steps_tw'], 1)))

st.caption("食譜資料來源:HowToCook(Unlicense,公有領域)。食材辨識使用 Google Gemini。本網站為專題作品。")
