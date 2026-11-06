import hashlib, re
import pandas as pd, streamlit as st
import recommend as R
from recommend import normalize, recommend, identify_ingredients, DEFAULT_PANTRY

MAX_FREE_PHOTOS = 5      # 每位訪客(每次開啟網頁)最多可用網站金鑰辨識幾張照片

CAT_NAME = {'meat_dish': '肉類', 'vegetable_dish': '蔬菜', 'staple': '主食', 'aquatic': '水產',
            'breakfast': '早餐', 'soup': '湯品', 'drink': '飲品', 'dessert': '甜點',
            'semi-finished': '半成品', 'condiment': '醬料'}
EXAMPLES = [('雞蛋 + 番茄', '雞蛋 番茄'), ('雞肉 + 洋蔥 + 馬鈴薯', '雞肉 洋蔥 馬鈴薯'), ('豬肉 + 青椒', '豬肉 青椒')]

st.set_page_config(page_title="智慧冰箱食譜", page_icon="🧊")


def data_sig():
    """資料檔內容的指紋;檔案一換,指紋就變,下面的 load() 就會重新讀取"""
    return hashlib.md5(open('recipes_clean.json', 'rb').read()).hexdigest()[:8]


@st.cache_data
def load(sig):
    d = pd.read_json('recipes_clean.json')
    text = d['name'] + ' ' + d['ingredients'].map(' '.join)
    return d[~text.str.contains('兔')].reset_index(drop=True)      # 不收兔肉料理


@st.cache_data(show_spinner="辨識中...")
def identify(b, mt, _key=None): return identify_ingredients(b, mt, api_key=_key)


def _fill(s): st.session_state['ing'] = s


IMG = re.compile(r'!\[[^\]]*\]\([^)]*\)|<img[^>]*>')      # 圖片語法:網站顯示不出圖,直接拿掉


def render_steps(steps):
    """步驟轉成 markdown:【小標題】用粗體,其餘依序編號(遇到小標題重新編號);圖片拿掉"""
    blocks, cur, n = [], [], 0
    for s in steps:
        s = IMG.sub('', str(s)).strip()
        if not s: continue
        if s.startswith('【') and s.endswith('】'):
            if cur: blocks.append("\n".join(cur)); cur = []
            blocks.append(f"**{s[1:-1]}**"); n = 0
        else:
            n += 1; cur.append(f"{n}. {s}")
    if cur: blocks.append("\n".join(cur))
    return "\n\n".join(blocks)


R.refresh()
SIG = data_sig()
df = load(SIG)
if 'seen_photos' not in st.session_state:
    st.session_state.seen_photos = set()

st.title("智慧冰箱食譜")
st.caption("輸入冰箱裡有的食材,找今天能煮的菜")

# ---------- 輸入食材 ----------
text = st.text_input("輸入食材", key='ing', placeholder="例如:雞蛋 番茄 洋蔥(用空格或頓號分隔)")

with st.expander("用照片辨識食材"):
    own_key = st.text_input("使用自己的 Gemini 金鑰(選填,填了就不受次數限制)", type="password")
    photo = st.file_uploader("上傳冰箱或食材照片", type=["jpg", "jpeg", "png", "jfif"])
    if photo:
        b = photo.getvalue()
        h = hashlib.md5(b).hexdigest()
        is_new = h not in st.session_state.seen_photos
        if is_new and not own_key and len(st.session_state.seen_photos) >= MAX_FREE_PHOTOS:
            st.warning(f"本次使用的免費照片辨識次數已用完(上限 {MAX_FREE_PHOTOS} 張)。"
                       "可以改用文字輸入,或填入自己的 Gemini 金鑰。")
        else:
            mt = "image/png" if (photo.name or "").lower().endswith(".png") else "image/jpeg"
            try:
                text += " " + identify(b, mt, _key=own_key or None)
                st.session_state.seen_photos.add(h)
            except Exception as e:
                st.error(f"圖片辨識失敗:{e}")

have = normalize(text)
if have:
    st.markdown("已辨識食材:" + "、".join(have))

# ---------- 篩選設定 ----------
with st.expander("篩選設定"):
    c1, c2 = st.columns(2)
    miss_n = c1.slider("最多可缺幾樣主食材", 0, 4, 2)
    top_n = c2.slider("最多顯示幾道菜", 5, 50, 20)
    cat_keys = st.multiselect("料理類型(不選 = 全部)", list(CAT_NAME), format_func=lambda k: CAT_NAME[k])
    must = st.multiselect("一定要用到的食材(選填)", have) if have else []
    pantry = st.multiselect("家裡有的調味料(沒勾選的會標示為缺料)", R.PANTRY_ALL, default=DEFAULT_PANTRY)
    strict = st.checkbox("只推薦「調味料我都有」的食譜", value=False)
    st.caption("排序:越能用到你輸入的食材、缺料越少越前面,並讓相似的食譜分散開。")

# ---------- 結果 ----------
if not have:
    st.markdown("**先輸入食材,或點一下範例:**")
    for col, (label, val) in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(label, on_click=_fill, args=(val,), use_container_width=True)
else:
    res = recommend(df, have, max_missing=miss_n, top_n=top_n, pantry=pantry, strict_pantry=strict,
                    must_use=must, categories=cat_keys or None)
    if res.empty:
        st.warning("找不到符合的食譜,試著放寬缺料數、取消調味料限制、料理類型或「一定要用到」的食材")
    else:
        st.markdown(f"**找到 {res.attrs.get('total', len(res))} 道,顯示前 {len(res)} 道**")
    for _, r in res.iterrows():
        row = df.loc[r['idx']]
        d = int(r['difficulty']) if pd.notna(r['difficulty']) else 0
        meta = [CAT_NAME.get(r['category'], ''), '難度 ' + '★' * d + '☆' * (5 - d),
                f"{int(r['kcal'])} 大卡" if pd.notna(r['kcal']) else '']
        with st.container(border=True):
            st.markdown(f"#### {r['name']}")
            st.caption(" · ".join(m for m in meta if m))
            if r['missing']:
                st.markdown(f":orange[**缺 {len(r['missing'])} 樣**]:{'、'.join(r['missing'])}")
            else:
                st.markdown(":green[**食材齊全**]")
            st.markdown("已有:" + "、".join(r['have']))
            if r['missing_minor']:
                st.caption("副食材(可省略):" + "、".join(r['missing_minor']))
            if r['missing_pantry']:
                st.caption("需要補的調味料:" + "、".join(r['missing_pantry']))
            with st.expander("查看用量與步驟"):
                st.markdown("**用量**")
                st.markdown("\n".join(f"- {a}" for a in row['amounts_tw']))
                st.markdown("**步驟**")
                st.markdown(render_steps(row['steps_tw']))

st.divider()
st.caption(f"食譜資料來源:HowToCook(Unlicense,公有領域)。食材辨識使用 Google Gemini。本網站為專題作品。　資料版本 {SIG}・共 {len(df)} 道")
