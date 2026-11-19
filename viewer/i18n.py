"""Japanese page labels and controls (owner 2026-10-25: labels and controls only; unit / building / tech
names and the longer explanations stay English). Applied to the page template at build time:
    translate(html, "ja")
TEXT: visible text between tags (exact, surrounding spaces kept). RAW: labels set from script code.
Game terms follow the Japanese client (封建時代, 城主時代, 町の人, 黄金, 石材, ...).
"""
import re

TEXT = {
    # ---- Fogline
    "Fogline Replay Reader": "Fogline リプレイリーダー",
    "Sight": "視点", "Vision": "視界", "Villagers": "町の人", "All": "すべて", "Army": "軍",
    "Triangles": "三角形", "Icons × count": "アイコン × 数", "Buildings": "建物", "Shapes by type": "種類別の形",
    "Icons": "アイコン", "Army heat": "軍ヒートマップ", "Off": "オフ", "Whole game so far": "試合全体（ここまで）",
    "Last 3 min": "直近3分", "Resources": "資源", "Show true values": "真の値を表示", "Food safety": "食料の安全度",
    "TC midline": "TC 中間線", "Orders": "命令", "Command rings": "コマンドリング", "Large map": "大きいマップ",
    "Font": "フォント", "Speed": "速度", "Load view file": "ビューファイルを開く", "Camera": "カメラ",
    "trail": "軌跡", "off": "オフ", "Impassable": "通行不能", "Map": "マップ", "Reset view": "表示リセット",
    "Game view": "ゲーム視点", "North up": "北が上", "custom": "カスタム", "Play": "再生",
    "Opponent read": "相手の読み", "Read": "読み", "Gold": "黄金", "Bank (rough)": "資源残高（概算）",
    "Castle timing": "城主時代タイミング", "Economy (review)": "経済（レビュー）",
    "Their techs (review)": "相手の技術（レビュー）", "Implied gold": "推定黄金", "Gold villagers": "金鉱の町の人",
    "Implied bank (rough)": "推定資源残高（概算）", "Last 60 s": "直近60秒",
    "Castle (projected)": "城主時代（予測）", "Delay from what you saw": "確認した支出による遅れ",
    "Off-path spending seen": "確認した寄り道の支出", "Their safe food": "相手の安全な食料",
    "Active safe food": "アクティブな安全食料", "Active runs out in": "アクティブ食料の枯渇まで",
    "Potential (scouted)": "潜在（偵察済み）", "Your army vs what you saw": "自軍 vs 確認した敵軍",
    "What you saw": "確認したもの", "Fights": "戦闘", "Time": "時間", "Length": "長さ",
    "P1 lost": "P1 損失", "P2 lost": "P2 損失", "Value edge": "価値差", "Army before → after": "軍（前 → 後）",
    "Enemy seen": "確認した敵", "Ideal · same cost": "理想 · 同コスト", "Effectiveness": "有効度",
    "Hunt premium": "狩猟ボーナス", "of it map hunt": "うちマップ狩猟", "Mills out / defence": "前線製粉所 / 防衛",
    "Net": "差引", "Gathered so far": "これまでの採集量", "Natural food taken": "取得した自然食料",
    "Food from": "食料の内訳", "Farms": "農場", "Food": "食料", "Wood": "木材", "Stone": "石材",
    "vils": "町の人", "nominal/min": "名目/分", "measured/min": "実測/分", "eff.": "効率", "food on": "食料源",
    "food": "食料", "other": "その他", "none": "なし", "res": "資源", "natural ·": "自然 ·", "farms ·": "農場 ·",
    "no command in the last 20 s": "直近20秒にコマンドなし", "no research yet": "研究なし",
    "Villagers implied from your sight": "視界から推定した町の人",
    "Same, minus villagers you saw killed": "同上（倒した町の人を除く）", "True (review only)": "真値（レビューのみ）",
    "True active food (review only)": "真のアクティブ食料（レビューのみ）",
    "Potential (dashed): scouted food that is safe for them": "潜在（破線）：偵察済みで相手にとって安全な食料",
    "Scouted, not safe for them": "偵察済み・相手にとって危険",
    "Show skirmishes (under 3 deaths and under 400 resources)": "小競り合いも表示（死亡3未満かつ400資源未満）",
    "cliff": "崖", "deep water (land units can't stand)": "深い水（陸上ユニット不可）", "deep water": "深い水",
    "sight (from unit sight radii, approximate)": "視界（ユニットの視界半径から概算）",
    "• villager": "• 町の人", "○ fishing boat / other gatherer": "○ 漁船 / その他の採集者",
    "▲ army, size ∝ resource value (label: units · value)": "▲ 軍（大きさ ∝ 資源価値、ラベル：数 · 価値）",
    "◯ dashed circle ⚔n: fight n in progress (see Fights)": "◯ 破線の円 ⚔n：戦闘 n 進行中（戦闘を参照）",
    "⬚ dashed square: enemy building where you last saw it": "⬚ 破線の四角：最後に確認した敵の建物",
    "shaded squares: where each army spent time (Army heat)": "影の四角：各軍の滞在場所（軍ヒートマップ）",
    "No army data in this file.": "このファイルに軍のデータはありません。",
    "No enemy units or buildings seen yet in this replay.": "このリプレイではまだ敵ユニットや建物を確認していません。",
    # ---- fight page
    "Fight Review": "戦闘レビュー", "Analysis notes": "解析メモ",
    "Show skirmishes (under 2 deaths or under 200 resources lost)": "小競り合いも表示（死亡2未満または損失200資源未満）", "Attack lines": "攻撃線", "Load fights file": "戦闘ファイルを開く",
    "Data": "データ", "Odds before": "事前の勝率", "Win odds before": "事前の勝率", "Lost": "損失",
    "Damage": "ダメージ", "Damage dealt": "与ダメージ", "Techs": "技術", "Target choice": "ターゲット選択",
    "Focus fire": "集中攻撃", "Overkill": "オーバーキル", "No fight at this moment": "この時点で戦闘なし",
    "none yet": "まだなし", "upset": "番狂わせ", "– (no attack data)": "–（攻撃データなし）",
    "○ villager": "○ 町の人", "✕ death": "✕ 死亡", "bar under unit: HP (when damaged)": "ユニット下のバー：HP（損傷時）",
    # ---- profile page
    "Civs": "文明", "Openings": "序盤の型", "Feudal / Castle (median)": "封建 / 城主（中央値）",
    "Villagers at 10:00 (median)": "10:00 の町の人（中央値）", "Attacks that paid off": "成果のあった攻撃",
    "Enemy army he'd seen at attacks": "攻撃時に確認していた敵軍", "Timings": "タイミング",
    "Attacks: what they were made into": "攻撃：相手の状態別", "Scouting": "偵察", "Units made, by age": "時代別の生産ユニット",
    "Age": "時代", "Units (all games)": "ユニット（全試合）",
    "Economy: resources gathered per minute (median over games)": "経済：毎分の採集量（試合の中央値）",
    "Resource": "資源", "Hunt and villager efficiency (median over games)": "狩猟と町の人の効率（試合の中央値）",
    "Him": "本人", "Opponents": "対戦相手", "Army value difference (his − theirs, median over games)": "軍の価値差（本人 − 相手、試合の中央値）",
    "Biggest lead / deficit (median)": "最大リード / 最大劣勢（中央値）", "res, positive = his army bigger": "資源、正 = 本人の軍が大きい",
    "Landmarks he built": "建てたランドマーク", "Landmark": "ランドマーク", "Games": "試合", "Finished (median)": "完成（中央値）",
    "Per game": "試合ごと", "Game": "試合", "Civ": "文明", "Opponent": "対戦相手", "Opening": "序盤の型",
    "Feudal": "封建", "Castle": "城主", "Vils 10:00": "町の人 10:00", "Attacks": "攻撃", "Paid off": "成果",
    "Base looks": "本拠地の確認", "Army seen": "確認した軍", "Pages": "ページ", "Every attack": "すべての攻撃",
    "Value": "価値", "Their army": "相手の軍", "Their safe food (his est. / true)": "相手の安全な食料（推定 / 真値）",
    "Enemy state": "相手の状態", "Vils killed": "倒した町の人", "Result": "結果", "good": "成功", "poor": "失敗",
    "Not included": "対象外", "How these are measured": "計測方法", "no attacks found": "攻撃なし",
    "none in these games": "これらの試合ではなし", "opp.": "相手", "Player": "プレイヤー", "Started": "開始",
    "Finished": "完成", "Gathered": "採集量", "ages reached": "到達した時代",
    "Army value difference (his − theirs)": "軍の価値差（本人 − 相手）",
    "Food time on hunt": "狩猟の食料時間", "Efficiency food / wood / gold": "効率 食料 / 木材 / 黄金",
    "value seen in the minute before ÷ true value": "直前1分に確認した価値 ÷ 真の価値",
    # profile rows / charts
    "Natural food taken (berries, deer, boar, sheep)": "取得した自然食料（ベリー、シカ、イノシシ、羊）",
    "… share outside his base": "… うち本拠地の外の割合",
    "Food from other sources (passive: cattle, pastures, boats…)": "その他の食料源（受動収入：牛、牧草地、漁船…）",
    "Farms: majority of food from": "農場：食料の過半を占めた時刻", "Farms built by 10:00": "10:00 までの農場数",
    "Food time on deer / boar": "シカ / イノシシの食料時間", "Food time on map hunt": "マップ狩猟の食料時間",
    "Hunt premium (food)": "狩猟ボーナス（食料）", "… of it map hunt": "… うちマップ狩猟",
    "Forward mills (res)": "前線製粉所（資源）", "Outposts / towers / walls (res)": "前哨基地 / 塔 / 壁（資源）",
    "Food efficiency": "食料の効率", "Wood efficiency": "木材の効率", "Gold efficiency": "黄金の効率",
    "Feudal reached": "封建時代到達", "Castle reached": "城主時代到達", "First military unit": "最初の軍ユニット",
    "Second TC": "2つ目の TC",
    "Time with a look at their base in the last 60 s": "直近60秒以内に相手の本拠地を確認していた時間",
    "Their buildings seen within 60 s of going up": "建設から60秒以内に確認した相手の建物",
    "Their buildings never seen": "一度も確認しなかった相手の建物",
    "Enemy army seen in the minute before fights": "戦闘前1分間に確認した敵軍",
    "Their safe food low (his sight) — yes": "相手の安全な食料が少ない（本人の視点） — はい",
    "Their safe food low (his sight) — no": "相手の安全な食料が少ない（本人の視点） — いいえ",
    "Their safe food low (true) — yes": "相手の安全な食料が少ない（真値） — はい",
    "Their safe food low (true) — no": "相手の安全な食料が少ない（真値） — いいえ",
    "Their army weaker (as he'd seen it) — yes": "相手の軍が弱い（確認した範囲） — はい",
    "Their army weaker (as he'd seen it) — no": "相手の軍が弱い（確認した範囲） — いいえ",
    "Their army weaker (true) — yes": "相手の軍が弱い（真値） — はい", "Their army weaker (true) — no": "相手の軍が弱い（真値） — いいえ",
    "Enemy greedy (Castle going up / little army) — yes": "相手が欲張り（城主時代へ / 軍が少ない） — はい",
    "Enemy greedy (Castle going up / little army) — no": "相手が欲張り（城主時代へ / 軍が少ない） — いいえ",
    "share of the game": "試合中の割合", "share of their buildings": "相手の建物の割合",
    "value share, fights with enemy army": "価値の割合（敵軍のいる戦闘）",
    "Economy: resources gathered per minute (median over games)": "経済：毎分の採集量（試合の中央値）",
    "Food time on hunt": "狩猟の食料時間",
}

# labels set from script code (exact source snippets)
RAW = [
    ('"Castle reached"', '"城主時代到達"'), ('"Castle (projected)"', '"城主時代（予測）"'),
    (': "Active safe food"', ': "アクティブな安全食料"'), (': "Active runs out in"', ': "アクティブ食料の枯渇まで"'),
    ('`Reading P${p} ', '`P${p} の読み：'), ("`from P${o}'s sight`", "`P${o} の視点から`"),
    ('meter("odds", "Odds"', 'meter("odds", "勝率"'), ('meter("target", "Target"', 'meter("target", "ターゲット"'),
    ('meter("focus", "Focus"', 'meter("focus", "集中"'), ('meter("over", "Overkill"', 'meter("over", "オーバーキル"'),
    ('`Fight ${F.n} · ', '`戦闘 ${F.n} · '), ('"No fight at this moment"', '"この時点で戦闘なし"'),
    ('<span class="k">Hunt premium</span>', '<span class="k">狩猟ボーナス</span>'),
    ('"no command in the last 20 s"', '"直近20秒にコマンドなし"'),
    ('`<span><i class="sw" style="background:${pc(o)}"></i>P${o} natural food taken (berries, deer, boar, sheep)</span>`',
     '`<span><i class="sw" style="background:${pc(o)}"></i>P${o} 取得した自然食料（ベリー、シカ、イノシシ、羊）</span>`'),
    ('P${o} hunt premium (solid) · mills out + defence (dashed)', 'P${o} 狩猟ボーナス（実線） · 前線製粉所 + 防衛（破線）'),
    ('"everything" : `P${pv} sight`', '"全体" : `P${pv} の視点`'),
    ('`seen ${E.n_seen[ai]}`', '`確認 ${E.n_seen[ai]}`'), ('` · ${E.kills[ai]} seen killed`', '` · 倒した ${E.kills[ai]}`'),
    ('Villagers seen (last ${D.params.window}s)', '確認した町の人（直近 ${D.params.window} 秒）'),
    ('`P${a} lost`; $("thP2").textContent = `P${b} lost`', '`P${a} 損失`; $("thP2").textContent = `P${b} 損失`'),
    ("`P${o}'s army`", "`P${o} の軍`"),
    ('`wins (strength ${r.vs.toFixed(2)}×)` : `loses (strength ${r.vs.toFixed(2)}×)`',
     '`勝つ（戦力 ${r.vs.toFixed(2)}×）` : `負ける（戦力 ${r.vs.toFixed(2)}×）`'),
    ('<span class="k">Yours · ', '<span class="k">自軍 · '), (' head-on</span>', ' 正面衝突時</span>'),
    ('Implied gold (top chart${techOn ? "; solid = minus their techs, dotted = without" : ""}); gold villagers seen (dotted, lower chart)',
     '推定黄金（上のグラフ${techOn ? "；実線 = 技術を差し引き、点線 = 差し引きなし" : ""}）；金鉱の町の人（点線、下のグラフ）'),
    ('`P${a.idx} lost`; $("thB").textContent = b ? `P${b.idx} lost`', '`P${a.idx} 損失`; $("thB").textContent = b ? `P${b.idx} 損失`'),
    ('"fights at 4 samples/s" : "1 sample/s (recorded before fight sampling)"', '"戦闘は毎秒4サンプル" : "毎秒1サンプル（戦闘サンプリング導入前の録画）"'),
    ('${fmtN(d.unattributed)} unattributed', '${fmtN(d.unattributed)} 帰属不明'),
    ('F.odds && F.odds.upset ? "upset" : ""', 'F.odds && F.odds.upset ? "番狂わせ" : ""'),
    ('${won ? " · came out ahead" : ""}', '${won ? " · 優勢で終了" : ""}'), ('+ " res at start"', '+ " 資源（開始時）"'),
    ('{ inf: "infantry", ranged: "ranged", cav: "cavalry", horse_archer: "horse archer", siege: "siege", monk: "religious", hero: "hero", naval: "ship" }',
     '{ inf: "歩兵", ranged: "遠距離", cav: "騎兵", horse_archer: "騎射", siege: "攻城", monk: "宗教", hero: "英雄", naval: "船" }'),
    (' (rectangle)</span>', '（長方形）</span>'), (' (diamond)</span>', '（菱形）</span>'),
    ('<span>■ building', '<span>■ 建物'),
]


# generated text in the profile page (regex, applied to the finished page)
PATTERNS = [
    (r"· median (\d+:\d\d) · (\d+) of (\d+) games", r"· 中央値 \1 · \2 / \3 試合"),
    (r">(\d+) attacks<", r">\1 回の攻撃<"),
    (r">(\d+) games · (\d+) attacks · ", r">\1 試合 · \2 回の攻撃 · "),
]


def translate(html, lang):
    if lang != "ja":
        return html
    import html as _h
    for en, ja in sorted(TEXT.items(), key=lambda kv: -len(kv[0])):
        for key in {en, _h.escape(en)}:           # the profile page escapes ' and & in its labels
            html = re.sub(r">(\s*)" + re.escape(key) + r"(\s*)<", lambda m: ">" + m.group(1) + ja + m.group(2) + "<", html)
    for a, b in PATTERNS:
        html = re.sub(a, b, html)
    for a, b in RAW:
        html = html.replace(a, b)
    return html.replace('<html lang="en"', '<html lang="ja"')
