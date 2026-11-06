import json, os, unicodedata
import pandas as pd
from opencc import OpenCC
t2s = OpenCC('t2s')

_A = json.load(open('aliases.json', encoding='utf8'))
ALIAS = {a: n for n, als in _A['CANON'].items() for a in als}
ALIAS_SORTED = sorted(ALIAS, key=len, reverse=True)

try:   # 字典以外的「其他食材」名稱,讓使用者也能輸入(例如 玉竹、石斛)
    _R = json.load(open('recipes_clean.json', encoding='utf8'))
    OTHER = sorted({o for x in _R for o in x.get('ing_other', []) if len(o) >= 2}, key=len, reverse=True)
except Exception:
    OTHER = []

# 調味料清單(給網頁勾選用)與預設勾選
PANTRY_ALL = list(_A['PANTRY'])
DEFAULT_PANTRY = ['鹽', '糖', '醬油', '食用油', '水', '料酒', '醋', '胡椒', '太白粉', '蔥', '薑', '蒜']


def normalize(text):
    orig = unicodedata.normalize('NFKC', text)
    text = t2s.convert(orig).lower()
    found = [o for o in OTHER if o in orig]
    for a in ALIAS_SORTED:
        if a in text:
            found.append(ALIAS[a]); text = text.replace(a, '、')
    return sorted(set(found))


def recommend(df, have, max_missing=2, top_n=10, pantry=None, strict_pantry=False):
    """pantry: 使用者家裡有的調味料清單(None = 全部都有)
       strict_pantry: True 時,缺任何調味料的食譜直接排除"""
    have, rows = set(have), []
    pantry = set(PANTRY_ALL if pantry is None else pantry)
    for i, r in df.iterrows():
        minor = set(r.get('ing_minor', []))                                  # 副食材(藥材、特殊配料)
        main = (set(r['ing_main']) | set(r.get('ing_other', []))) - minor    # 生鮮才算主食材
        hit, miss = main & have, main - have
        if not main or not hit or len(miss) > max_missing: continue
        miss_p = set(r['ing_pantry']) - pantry
        miss_m = minor - have                                                # 副食材:缺了不影響篩選,只提醒
        if strict_pantry and miss_p: continue
        rows.append(dict(idx=i, name=r['name_tw'], category=r['category'],
                         difficulty=r['difficulty'], kcal=r['kcal'],
                         have=sorted(hit), missing=sorted(miss),
                         missing_pantry=sorted(miss_p), missing_minor=sorted(miss_m),
                         n_miss=len(miss), n_hit=len(hit), n_miss_p=len(miss_p), n_minor=len(miss_m)))
    out = pd.DataFrame(rows)
    if out.empty: return out
    # 缺主食材少 > 用到你的食材多 > 缺副食材少 > 缺調味料少 > 難度低
    return (out.sort_values(['n_miss', 'n_hit', 'n_minor', 'n_miss_p', 'difficulty'],
                            ascending=[True, False, True, True, True])
               .head(top_n).reset_index(drop=True))


def _get_key(user_key=None):
    """金鑰來源順序:使用者自己輸入 > 環境變數 > Streamlit Secrets"""
    if user_key: return user_key
    k = os.environ.get('GEMINI_API_KEY')
    if k: return k.strip()
    try:
        import streamlit as st
        return str(st.secrets['GEMINI_API_KEY']).strip()
    except Exception:
        return None


def identify_ingredients(img_bytes, media_type="image/jpeg", api_key=None):
    import time
    key = _get_key(api_key)
    if not key:
        raise RuntimeError("沒有設定 Gemini 金鑰(請到 Streamlit 的 Secrets 設定 GEMINI_API_KEY)")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    prompt = "列出圖中可辨識的食材,繁體中文,只用頓號分隔,不要其他文字。"
    names = [m.name.replace('models/', '') for m in client.models.list()
             if 'flash' in m.name and 'generateContent' in (m.supported_actions or [])
             and not any(x in m.name for x in ('image', 'tts', 'live', 'audio', 'embedding'))]
    names.sort(key=lambda n: ('lite' in n, n))
    err = None
    for model in names[:4]:
        for i in range(3):
            try:
                r = client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_bytes(data=img_bytes, mime_type=media_type), prompt])
                return r.text
            except Exception as e:
                err = e
                if '503' in str(e) or '429' in str(e): time.sleep(2 * (i + 1))
                else: break
    raise err
