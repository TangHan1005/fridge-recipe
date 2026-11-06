import pandas as pd, streamlit as st
from recommend import normalize, recommend, identify_ingredients

st.set_page_config(page_title="智慧冰箱食譜推薦")
st.title("🧊 智慧冰箱食譜推薦")

@st.cache_data
def load(): return pd.read_json('recipes_clean.json')
df = load()

text = st.text_input("輸入食材(空格或頓號分隔)", "")
photo = st.camera_input("或拍攝冰箱食材") or st.file_uploader("或上傳照片", type=["jpg", "jpeg", "png"])
if photo:
    with st.spinner("辨識中..."):
        try: text += " " + identify_ingredients(photo.getvalue(), photo.type or "image/jpeg")
        except Exception as e: st.error(f"圖片辨識失敗:{e}")
have = normalize(text)
st.write("已辨識食材:", "、".join(have) or "(無)")
miss_n = st.slider("最多可缺幾樣主食材", 0, 4, 2)

if have:
    res = recommend(df, have, max_missing=miss_n)
    if res.empty: st.warning("找不到符合的食譜,試著放寬缺料數")
    for _, r in res.iterrows():
        row = df.loc[r['idx']]
        with st.expander(f"{r['name']}｜缺:{'、'.join(r['missing']) or '無'}｜難度{r['difficulty']}｜{r['kcal']}kcal"):
            st.write("✅ 已有:", "、".join(r['have']))
            st.write("**用量**"); st.write("\n".join(f"- {a}" for a in row['amounts_tw']))
            st.write("**步驟**"); st.write("\n".join(f"{i}. {s}" for i, s in enumerate(row['steps_tw'], 1)))
