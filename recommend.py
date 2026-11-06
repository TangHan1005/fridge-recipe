import json, unicodedata, base64
import pandas as pd
from opencc import OpenCC
t2s = OpenCC('t2s')
MODEL = "claude-sonnet-5-5"   # 辨識圖片用的模型,可自行更換

_A = json.load(open('aliases.json', encoding='utf8'))
ALIAS = {}
for n, als in _A['CANON'].items():
    for a in als: ALIAS[a] = n
ALIAS_SORTED = sorted(ALIAS, key=len, reverse=True)

def normalize(text):
    """使用者輸入(繁/簡/部首異體字皆可) -> 標準主食材清單(調味料不算)"""
    text = t2s.convert(unicodedata.normalize('NFKC', text)).lower()
    found = []
    for a in ALIAS_SORTED:
        if a in text:
            found.append(ALIAS[a]); text = text.replace(a, '、')
    return sorted(set(found))

def recommend(df, have, max_missing=2, top_n=10):
    """缺料少 > 命中多 > 難度低 排序;至少要命中 1 項主食材"""
    have, rows = set(have), []
    for i, r in df.iterrows():
        main = set(r['ing_main'])
        hit, miss = main & have, main - have
        if not main or not hit or len(miss) > max_missing: continue
        rows.append(dict(idx=i, name=r['name_tw'], category=r['category'],
                         difficulty=r['difficulty'], kcal=r['kcal'],
                         have=sorted(hit), missing=sorted(miss),
                         n_miss=len(miss), n_hit=len(hit)))
    out = pd.DataFrame(rows)
    if out.empty: return out
    return (out.sort_values(['n_miss', 'n_hit', 'difficulty'], ascending=[True, False, True])
               .head(top_n).reset_index(drop=True))

def identify_ingredients(img_bytes, media_type="image/jpeg"):
    """用 Claude 視覺辨識冰箱照片,回傳食材文字(需設定 ANTHROPIC_API_KEY)"""
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=300,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.b64encode(img_bytes).decode()}},
            {"type": "text", "text": "列出圖中可辨識的食材,繁體中文,只用頓號分隔,不要其他文字。"}]}])
    return msg.content[0].text
