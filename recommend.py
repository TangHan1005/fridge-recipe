import json, os, unicodedata
import pandas as pd
from opencc import OpenCC
t2s = OpenCC('t2s')

_TERMS = {}
_STATE = {'stamp': None}
_A, ALIAS, ALIAS_SORTED, OTHER, PANTRY_ALL = {}, {}, [], [], []


def refresh():
    """資料檔(aliases.json、recipes_clean.json)內容有更新,就自動重新讀取,不用重啟網站"""
    global _A, ALIAS, ALIAS_SORTED, OTHER, PANTRY_ALL
    stamp = tuple(os.stat(f).st_mtime_ns if os.path.exists(f) else 0 for f in ('aliases.json', 'recipes_clean.json'))
    if stamp == _STATE['stamp']: return
    _A = json.load(open('aliases.json', encoding='utf8'))
    ALIAS = {a: n for n, als in _A['CANON'].items() for a in als}
    ALIAS_SORTED = sorted(ALIAS, key=len, reverse=True)
    try:   # 字典以外的「其他食材」名稱,讓使用者也能輸入(例如 玉竹、石斛)
        _R = json.load(open('recipes_clean.json', encoding='utf8'))
        OTHER = sorted({o for x in _R for o in x.get('ing_other', []) if len(o) >= 2}, key=len, reverse=True)
    except Exception:
        OTHER = []
    PANTRY_ALL = list(_A['PANTRY'])        # 調味料清單(給網頁勾選用)
    _TERMS.clear()
    _STATE['stamp'] = stamp


refresh()
DEFAULT_PANTRY = ['鹽', '糖', '醬油', '食用油', '水', '料酒', '醋', '胡椒', '太白粉', '蔥', '薑', '蒜']


def normalize(text):
    refresh()
    orig = unicodedata.normalize('NFKC', text)
    text = t2s.convert(orig).lower()
    found = [o for o in OTHER if o in orig]
    for a in ALIAS_SORTED:
        if a in text:
            found.append(ALIAS[a]); text = text.replace(a, '、')
    return sorted(set(found))


# 使用者可以選擇「不想看到」的食譜類型(用食材關鍵字比對菜名與食材,關鍵字為簡體)
HIDE_TAGS = {
    '特殊肉類(兔、牛蛙、田螺、乳鴿、鱔魚、海參)': ['兔', '牛蛙', '田鸡', '田螺', '鸽', '鳝', '海参'],
    '內臟、血類、雞爪、豬蹄': ['猪肝', '猪腰', '肥肠', '大肠', '猪肚', '毛肚', '脑花', '鸭血', '猪血',
                         '鸡肝', '鸡胗', '鸡爪', '凤爪', '猪蹄', '猪皮'],
}
def _is_hidden(r, hide):
    text = str(r.get('name', '')) + ' ' + ' '.join(r.get('ingredients', []))
    return any(k in text for t in (hide or []) for k in HIDE_TAGS.get(t, []))


# 比對時視為同一類的食材(使用者輸入「雞肉」,雞腿、雞翅的食譜也要找得到)
SAME = {'雞胸肉': '雞肉', '雞腿': '雞肉', '雞翅': '雞肉', '五花肉': '豬肉'}
def _c(names): return {SAME.get(x, x) for x in names}


def _title_terms(c):
    """某個食材在菜名裡可能的寫法(含同類別名,例如 雞肉 -> 雞、雞腿、雞翅)"""
    if c not in _TERMS:
        names = {c} | {k for k, v in SAME.items() if v == c}
        _TERMS[c] = set(names).union(*[set(_A['CANON'].get(n, [])) for n in names])
    return _TERMS[c]


def recommend(df, have, max_missing=2, top_n=20, pantry=None, strict_pantry=False,
              must_use=None, diversity=True, max_same=3, hide=None, categories=None):
    """have: 使用者有的主食材(標準名稱清單)
       pantry: 使用者家裡有的調味料(None = 全部都有)
       strict_pantry: True 時,缺任何調味料的食譜直接排除
       must_use: 一定要用到的食材(例如 ['雞肉'])
       diversity: True 時,避免一堆差不多的食譜擠在前面,並讓每種食材都有機會出現
       max_same: 「主食材完全相同」的食譜,最多先排幾道(例如一堆只用雞蛋的食譜)
       hide: 要隱藏的食譜類型(HIDE_TAGS 的名稱清單)
       categories: 只看這些料理類型(例如 ['soup', 'meat_dish'])"""
    refresh()
    have = list(have)
    have_c, must_c = _c(have), _c(must_use or [])
    pantry = set(PANTRY_ALL if pantry is None else pantry)
    cands = []
    for i, r in df.iterrows():
        if _is_hidden(r, hide): continue                                     # 使用者選擇不想看到的類型
        if categories and r['category'] not in categories: continue          # 只看某些料理類型
        minor = set(r.get('ing_minor', []))                                  # 副食材(藥材、特殊配料)
        orig = (set(r['ing_main']) | set(r.get('ing_other', []))) - minor    # 生鮮才算主食材
        main_c = _c(orig)
        hit_c, miss_c = main_c & have_c, main_c - have_c
        if not main_c or not hit_c or len(miss_c) > max_missing: continue
        if must_c and not must_c <= hit_c: continue
        miss_p = set(r['ing_pantry']) - pantry
        if strict_pantry and miss_p: continue
        miss_m = minor - set(have)                                           # 副食材:缺了不影響篩選,只提醒
        cov = len(hit_c) / len(main_c)        # 這道菜的食材,你有幾成
        use = len(hit_c) / len(have_c)        # 你輸入的食材,這道菜用到幾成
        score = 2 * cov * use / (cov + use)   # 兩者都高才高(調和平均)
        title = str(r['name_tw']) + ' ' + str(r.get('name', ''))
        star = {c for c in hit_c if any(t in title for t in _title_terms(c))}
        score += 0.2 * len(star) / len(have_c)     # 菜名就有這個食材(例如 清蒸鱸魚)= 主角,排前面;配角食材不加分
        cands.append(dict(idx=i, name=r['name_tw'], category=r['category'],
                          difficulty=r['difficulty'], kcal=r['kcal'],
                          have=sorted(h for h in have if SAME.get(h, h) in hit_c),
                          missing=sorted(x for x in orig if SAME.get(x, x) in miss_c),
                          missing_pantry=sorted(miss_p), missing_minor=sorted(miss_m),
                          n_miss=len(miss_c), n_hit=len(hit_c), n_miss_p=len(miss_p), n_minor=len(miss_m),
                          score=round(score, 3), _main=main_c, _hit=hit_c, _key=frozenset(main_c)))
    if not cands: return pd.DataFrame()

    # 逐道挑選:分數高 + 帶來「還沒被推薦到的食材」 - 和已選食譜太像 - 同一組食材已經太多道
    selected, covered, same_count = [], set(), {}
    maxsim = [0.0] * len(cands)
    remaining = list(range(len(cands)))
    while remaining and len(selected) < top_n:
        def gain(k):
            c = cands[k]
            if not diversity: return c['score']
            g = c['score'] + 0.3 * len(c['_hit'] - covered) / len(have_c) - 0.3 * maxsim[k]
            if same_count.get(c['_key'], 0) >= max_same: g -= 1.0     # 超過上限的排到最後(名額沒滿時才會補上)
            return g
        best = max(remaining, key=lambda k: (round(gain(k), 6), -cands[k]['n_miss'], -cands[k]['n_minor'],
                                              -cands[k]['n_miss_p'], -(cands[k]['difficulty'] or 9)))
        selected.append(best); remaining.remove(best)
        covered |= cands[best]['_hit']
        same_count[cands[best]['_key']] = same_count.get(cands[best]['_key'], 0) + 1
        for k in remaining:                       # 更新每道候選菜和已選食譜的最大相似度(Jaccard)
            m1, m2 = cands[k]['_main'], cands[best]['_main']
            maxsim[k] = max(maxsim[k], len(m1 & m2) / len(m1 | m2))
    out = pd.DataFrame([{k: v for k, v in cands[k].items() if not k.startswith('_')} for k in selected])
    out.attrs['total'] = len(cands)               # 符合條件的食譜總數
    return out


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
