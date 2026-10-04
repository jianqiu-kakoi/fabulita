#!/usr/bin/env python3
"""Build the public My Japanese practice assignments.

Writes the ``jp-practice-*`` assignments into
``examples/my-japanese/homework.json``: one assignment per grammar lesson in the
learner's own notes (past / ていた, potential form, らしい・ておく・ために・つもり,
続ける・〜く・だからこそ, そうです・すぎる, や・やすい／にくい・すぐ,
わりに・たびに・ないこともない・っぽい・づらい).

Every sentence here was written for this public page. The tutor's worksheet
questions and the learner's personal answers stay in the private, gitignored
``homework.local.json``; nothing from them is copied. Answers are standard
Japanese grammar. Most items are tap-to-choose (single_choice) or tap-to-order
word tiles; a few open writing prompts are self-reviewed against a model answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOMEWORK = ROOT / "examples" / "my-japanese" / "homework.json"
PREFIX = "jp-practice-"
GAP = "＿＿＿"


def _shuffled(options: list[str], *seed: object) -> list[str]:
    digest = hashlib.sha256(":".join(str(part) for part in seed).encode("utf-8")).hexdigest()
    out = list(options)
    random.Random(int(digest, 16)).shuffle(out)
    return out


def choice(item_id: str, number: int, prompt: str, answer: str, distractors: list[str],
           translation: str = "", note: str = "") -> dict:
    options = [answer, *distractors]
    assert len(set(options)) == len(options), item_id
    item = {
        "id": item_id,
        "number": number,
        "prompt": prompt,
        "options": _shuffled(options, item_id),
        "answers": [answer],
        "canonicalAnswer": answer,
    }
    if translation:
        item["answerTranslation"] = translation
    notes = [text for text in (("中文：" + translation) if translation else "", ("提示：" + note) if note else "") if text]
    if notes:
        item["ambiguityNote"] = "　".join(notes)
    return item


def tiles(item_id: str, number: int, chinese: str, tile_list: list[str], answers: list[str]) -> dict:
    for answer in answers:
        assert sorted(answer) == sorted("".join(tile_list)), (item_id, answer)
    return {
        "id": item_id,
        "number": number,
        "prompt": "排成句子：" + chinese,
        "wordTiles": tile_list,
        "tileJoiner": "",
        "answers": answers,
        "canonicalAnswer": answers[0],
        "answerTranslation": chinese,
        "ambiguityNote": "中文：" + chinese,
    }


def open_item(item_id: str, number: int, task: str, model: str, translation: str) -> dict:
    return {
        "id": item_id,
        "number": number,
        "prompt": task,
        "answerMode": "self_review",
        "answers": [model],
        "canonicalAnswer": model,
        "answerTranslation": translation,
    }


def section(section_id: str, title: str, instructions: str, kind: str, items: list[dict]) -> dict:
    return {"id": section_id, "title": title, "instructions": instructions, "type": kind, "items": items}


def table(table_id: str, verb: str, title: str, rows: list[tuple[str, str]]) -> dict:
    return {"id": table_id, "verb": verb, "title": title,
            "rows": [{"person": left, "form": right} for left, right in rows]}


def assignment(slug: str, title: str, source_title: str, sections: list[dict],
               tables: list[dict] | None = None) -> dict:
    out = {
        "id": PREFIX + slug,
        "title": title,
        "badge": "日语练习",
        "sourceTitle": source_title,
        "level": "N5–N4",
        "answerKeyBasis": "standard_japanese_grammar",
        "contentOrigin": "independently_written_public_practice",
        "source": {},
        "answerLanguageLabel": "日语",
    }
    if tables:
        out["referenceTables"] = tables
    out["sections"] = sections
    return out


# ── 1. ～た / ～ました · ～ていた / ～ていました · どのくらい ────────────────
def lesson_past() -> dict:
    p = "jp-past"
    forms = [
        ("みる", "～ていました", "みていました", ["みていた", "みました", "みるていました"]),
        ("よむ", "～ていた", "よんでいた", ["よんでいました", "よみていた", "よむでいた"]),
        ("かく", "～ていました", "かいていました", ["かきていました", "かいていた", "かっていました"]),
        ("きく", "～ていた", "きいていた", ["きいていました", "きくていた", "きっていた"]),
        ("はなす", "～ていました", "はなしていました", ["はなしていた", "はなすていました", "はなっていました"]),
        ("いく", "～ていた", "いっていた", ["いいていた", "いっていました", "いくていた"]),
        ("かう", "～ました", "かいました", ["かった", "かいていました", "かうました"]),
        ("つくる", "～た", "つくった", ["つくりました", "つくていた", "つくた"]),
        ("りょうりする", "～ました", "りょうりしました", ["りょうりした", "りょうりしていました", "りょうりするました"]),
        ("のむ", "～た", "のんだ", ["のみた", "のんでいた", "のみました"]),
        ("たべる", "～ていました", "たべていました", ["たべていた", "たべました", "たべっていました"]),
        ("よむ", "～ました", "よみました", ["よんだ", "よんでいました", "よむました"]),
    ]
    form_items = [
        choice(f"{p}-form-{n:02d}", n, f"{verb} → {target}", answer, wrong)
        for n, (verb, target, answer, wrong) in enumerate(forms, start=1)
    ]
    sentences = [
        (f"きのうの よる 9じごろ、なにを {GAP}か。—— おふろに はいっていました。", "していました", ["します", "してください"],
         "昨天晚上九点左右你在做什么？——我在泡澡。", "问“当时正在做什么”用 ～ていました。"),
        (f"こどものとき、まいにち こうえんで {GAP}。", "あそんでいました", ["あそびます", "あそびたいです"],
         "小时候，我每天都在公园玩。", "过去一段时间里反复做的事，用 ～ていました。"),
        (f"せんしゅうまつ、ともだちと えいがを {GAP}。", "みました", ["みます", "みてください"],
         "上周末我和朋友看了电影。", "已经做完的一件事，用 ～ました。"),
        (f"でんわが きたとき、わたしは ほんを {GAP}。", "よんでいました", ["よみます", "よんでください"],
         "电话来的时候，我正在看书。", ""),
        (f"{GAP}、ちかくの スーパーで やさいを かいました。", "きのう", ["あした", "らいしゅう"],
         "昨天我在附近的超市买了蔬菜。", "かいました 是过去时，所以选过去的时间。"),
        (f"けさ、パンと たまごを {GAP}。", "たべました", ["たべます", "たべたいです"],
         "今天早上我吃了面包和鸡蛋。", ""),
    ]
    sentence_items = [
        choice(f"{p}-sent-{n:02d}", n, prompt, answer, wrong, zh, note)
        for n, (prompt, answer, wrong, zh, note) in enumerate(sentences, start=1)
    ]
    how_long = [
        (f"にほんごを べんきょうして、{GAP}ですか。—— はんとしぐらいです。", "どのくらい", ["どこ", "だれ"],
         "你学日语多久了？——大约半年。"),
        (f"いえから えきまで {GAP} かかりますか。—— あるいて 10ぷんです。", "どのくらい", ["なにを", "どれ"],
         "从家到车站要多久？——走路十分钟。"),
        (f"きのうは {GAP} ねましたか。—— 7じかん ねました。", "どのくらい", ["どうして", "どこで"],
         "昨天你睡了多久？——睡了七个小时。"),
        ("しゅみに いっしゅうかん どのくらい じかんを つかいますか。", "5じかんぐらい つかいます",
         ["テニスを します", "こうえんで します"], "你每周在爱好上花多少时间？——大约五个小时。"),
        ("いまの まちに すんで、どのくらいですか。", "2ねんに なります", ["とうきょうです", "たのしいです"],
         "你在现在的城市住多久了？——两年了。"),
    ]
    how_items = [
        choice(f"{p}-how-{n:02d}", n, prompt, answer, wrong, zh)
        for n, (prompt, answer, wrong, zh) in enumerate(how_long, start=1)
    ]
    tile_items = [
        tiles(f"{p}-tiles-01", 1, "我小时候每天都在学钢琴。",
              ["まいにち", "こどものとき", "ならっていました", "ピアノを"],
              ["こどものときまいにちピアノをならっていました"]),
        tiles(f"{p}-tiles-02", 2, "昨天晚上八点左右我在看电视。",
              ["テレビを", "きのうのよる", "みていました", "8じごろ"],
              ["きのうのよる8じごろテレビをみていました"]),
        tiles(f"{p}-tiles-03", 3, "上周末我和家人一起度过了。",
              ["かぞくと", "せんしゅうまつ", "すごしました"],
              ["せんしゅうまつかぞくとすごしました", "かぞくとせんしゅうまつすごしました"]),
        tiles(f"{p}-tiles-04", 4, "我住在这个城市两年了。",
              ["2ねんに", "このまちに", "なります", "すんで"],
              ["このまちにすんで2ねんになります"]),
    ]
    return assignment(
        "past", "日语 ① 过去式 ～た／～ました · ～ていた／～ていました · どのくらい",
        "練習：～た・～ていた・どのくらい",
        [
            section(f"{p}-form", "① 变形", "看动词和要求，选出正确的形式。～ていた＝随意体，～ていました＝礼貌体。",
                    "single_choice", form_items),
            section(f"{p}-sent", "② 句子里选", "选出放进句子里最自然的说法。", "single_choice", sentence_items),
            section(f"{p}-how", "③ どのくらい", "问“多久 / 多少”时用 どのくらい。选出正确的问法或回答。",
                    "single_choice", how_items),
            section(f"{p}-tiles", "④ 连词成句", "看中文意思，按顺序点词块拼成句子。点上面已选的词块可以撤回。",
                    "text_input", tile_items),
        ],
        tables=[table(f"{p}-ref", "ていた", "～ていた（随意）／～ていました（礼貌）", [
            ("みる", "みていた・みていました"), ("よむ", "よんでいた・よんでいました"),
            ("かく", "かいていた・かいていました"), ("はなす", "はなしていた・はなしていました"),
            ("いく", "いっていた・いっていました"), ("する", "していた・していました"),
        ])],
    )


# ── 2. 可能形 ～られる／～える／できる ───────────────────────────────────
def lesson_potential() -> dict:
    p = "jp-potential"
    forms = [
        ("のむ", "のめる", ["のまれる", "のめれる", "のみる"]),
        ("いく", "いける", ["いかれる", "いきれる", "いけれる"]),
        ("みる", "みられる", ["みるれる", "みれられる", "みらる"]),
        ("くる", "こられる", ["くれる", "きられる", "こる"]),
        ("する", "できる", ["される", "しれる", "すれる"]),
        ("はなす", "はなせる", ["はなされる", "はなしれる", "はなすれる"]),
        ("よむ", "よめる", ["よまれる", "よみれる", "よむれる"]),
        ("かく", "かける", ["かかれる", "かきれる", "かくれる"]),
        ("およぐ", "およげる", ["およがれる", "およぎれる", "およぐれる"]),
        ("あう", "あえる", ["あわれる", "あいれる", "あうれる"]),
        ("あそぶ", "あそべる", ["あそばれる", "あそびれる", "あそぶれる"]),
        ("おきる", "おきられる", ["おかれる", "おきらる", "おけられる"]),
        ("りょうりする", "りょうりできる", ["りょうりされる", "りょうりしれる", "りょうりすれる"]),
    ]
    form_items = [
        choice(f"{p}-form-{n:02d}", n, f"{verb} → 可能形", answer, wrong)
        for n, (verb, answer, wrong) in enumerate(forms, start=1)
    ]
    sentences = [
        (f"わたしは すこし えいごが {GAP}。", "はなせます", ["はなします", "はなしたいです"], "我会说一点英语。",
         "“能力”用可能形，前面用 が。"),
        (f"この みずは きれいじゃないので、{GAP}。", "のめません", ["のみます", "のみたいです"], "这水不干净，不能喝。", ""),
        (f"しゅくだいが おおいので、こんやは パーティーに {GAP}。", "いけません", ["いきます", "いってください"],
         "作业很多，今晚去不了聚会。", ""),
        (f"その まんがは どこで よめますか。—— アプリで {GAP}。", "よめます", ["よみたいです", "よんでください"],
         "那本漫画在哪里能看？——在 App 上能看。", ""),
        (f"ギターが {GAP}か。—— はい、すこし ひけます。", "ひけます", ["ひいて", "ひきたい"],
         "你会弹吉他吗？——会，弹一点。", ""),
        (f"あしが いたくて、はやく {GAP}。", "はしれません", ["はしりたいです", "はしってください"],
         "脚疼，跑不快。", ""),
        (f"この さかなは ほねが おおくて、こどもは {GAP}。", "たべられません", ["たべたいです", "たべてください"],
         "这条鱼刺多，小孩吃不了。", ""),
    ]
    sentence_items = [
        choice(f"{p}-sent-{n:02d}", n, prompt, answer, wrong, zh, note)
        for n, (prompt, answer, wrong, zh, note) in enumerate(sentences, start=1)
    ]
    answers = [
        ("にほんで なにが できますか。", "おいしい すしが たべられます", ["すしを たべてください", "すしが たべたいですか"],
         "在日本能做什么？——能吃到好吃的寿司。"),
        ("どんな スポーツが できますか。", "テニスが できます", ["テニスを してください", "テニスが すきでしたか"],
         "你会什么运动？——我会打网球。"),
        ("ひとりで どこへ いけますか。", "ちかくの まちへ ひとりで いけます", ["ひとりで いってください", "どこへ いきましたか"],
         "你一个人能去哪里？——我能一个人去附近的城市。"),
        ("ピアノが ひけますか。", "いいえ、ひけません", ["いいえ、ひいてください", "はい、ひきたいですか"],
         "你会弹钢琴吗？——不，不会。"),
    ]
    answer_items = [
        choice(f"{p}-qa-{n:02d}", n, prompt, answer, wrong, zh)
        for n, (prompt, answer, wrong, zh) in enumerate(answers, start=1)
    ]
    tile_items = [
        tiles(f"{p}-tiles-01", 1, "我会做咖喱。", ["つくれます", "カレーが"], ["カレーがつくれます"]),
        tiles(f"{p}-tiles-02", 2, "在伦敦能看音乐剧。", ["ミュージカルが", "ロンドンで", "みられます"],
              ["ロンドンでミュージカルがみられます"]),
        tiles(f"{p}-tiles-03", 3, "我能一个人去日本。", ["いけます", "ひとりで", "にほんへ"],
              ["にほんへひとりでいけます", "ひとりでにほんへいけます"]),
        tiles(f"{p}-tiles-04", 4, "我想变得会写汉字。", ["かけるように", "かんじが", "なりたいです"],
              ["かんじがかけるようになりたいです"]),
    ]
    write_items = [
        open_item(f"{p}-write-01", 1, "用可能形写两句：在你住的城市能做什么？",
                  "わたしの まちでは おいしい ラーメンが たべられます。こうえんで テニスも できます。",
                  "在我住的城市能吃到好吃的拉面。在公园也能打网球。"),
        open_item(f"{p}-write-02", 2, "写一句你“现在还不会、但想学会”的事（～ように なりたいです）。",
                  "にほんごの ほんが よめるように なりたいです。", "我想变得能读日语书。"),
    ]
    return assignment(
        "potential", "日语 ② 可能形 ～られる／～える／できる",
        "練習：可能形",
        [
            section(f"{p}-form", "① 变成可能形", "一段动词：る→られる；五段动词：う段→え段＋る；する→できる，くる→こられる。",
                    "single_choice", form_items),
            section(f"{p}-sent", "② 句子里选", "选出表示“能 / 不能”的说法。", "single_choice", sentence_items),
            section(f"{p}-qa", "③ 选回答", "选出用可能形正确回答问题的一句。", "single_choice", answer_items),
            section(f"{p}-tiles", "④ 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
            section(f"{p}-write", "⑤ 写一写", "自由写作，不自动判分，写完对照参考作答。", "open_response", write_items),
        ],
        tables=[table(f"{p}-ref", "可能形", "可能形：一段 る→られる · 五段 う段→え段＋る · する→できる · くる→こられる", [
            ("たべる・みる・ねる", "たべられる・みられる・ねられる"),
            ("のむ・よむ", "のめる・よめる"), ("いく・かく・きく", "いける・かける・きける"),
            ("はなす・まつ・とる", "はなせる・まてる・とれる"),
            ("する・りょうりする", "できる・りょうりできる"), ("くる", "こられる"),
        ])],
    )


# ── 3. らしい · ～ればよかった · ～ておく · ～ために · ～つもり ─────────────
def lesson_plans() -> dict:
    p = "jp-plans"
    grammar = [
        (f"てんきよほうに よると、あしたは ゆきが ふる{GAP}。", "らしいです", ["つもりです", "ておきます"],
         "据天气预报说，明天好像会下雪。", "听说 / 好像 → らしい。"),
        (f"なつやすみは ほっかいどうへ いく{GAP}です。", "つもり", ["らしい", "ために"],
         "暑假我打算去北海道。", "打算 → 辞书形＋つもり。"),
        (f"パーティーの まえに、のみものを かって{GAP}。", "おきます", ["らしいです", "つもりです"],
         "聚会前我先把饮料买好。", "提前做好 → ～ておく。"),
        (f"けんこうの {GAP}、まいあさ あるいています。", "ために", ["らしい", "つもり"],
         "为了健康，我每天早上走路。", "名词＋の＋ために＝为了……"),
        (f"かさを もってくれば {GAP}。", "よかったです", ["おきます", "つもりです"],
         "要是带伞来就好了。", "后悔 → ～ば よかった。"),
        (f"えがおで あいさつするのは、かのじょ{GAP}ですね。", "らしい", ["ために", "つもり"],
         "笑着打招呼，真像她的风格。", "名词＋らしい＝很有……的样子。"),
        (f"りゅうがくする {GAP}、おかねを ためています。", "ために", ["らしい", "ておく"],
         "为了留学，我在存钱。", "动词辞书形＋ために。"),
        (f"しけんの まえに、もっと べんきょう{GAP} よかったです。", "すれば", ["して", "する"],
         "考试前要是再多学点就好了。", "する → すれば。"),
    ]
    grammar_items = [
        choice(f"{p}-pick-{n:02d}", n, prompt, answer, wrong, zh, note)
        for n, (prompt, answer, wrong, zh, note) in enumerate(grammar, start=1)
    ]
    regrets = [
        ("かさを わすれて、あめに ぬれました。", "かさを もってくれば よかったです",
         ["かさを もってきて よかったです", "かさを もってくる つもりです"], "要是带了伞就好了。"),
        ("よふかしして、きょうは とても ねむいです。", "はやく ねれば よかったです",
         ["はやく ねて おきます", "はやく ねる らしいです"], "要是早点睡就好了。"),
        ("コンサートの チケットが うりきれでした。", "はやく かえば よかったです",
         ["はやく かって ください", "はやく かう ために"], "要是早点买就好了。"),
        ("りょこうで しゃしんを 1まいも とりませんでした。", "しゃしんを とれば よかったです",
         ["しゃしんを とって おきました", "しゃしんを とる らしいです"], "要是拍了照片就好了。"),
    ]
    regret_items = [
        choice(f"{p}-regret-{n:02d}", n, f"{situation}→ 你会说：", answer, wrong, zh)
        for n, (situation, answer, wrong, zh) in enumerate(regrets, start=1)
    ]
    tile_items = [
        tiles(f"{p}-tiles-01", 1, "听说明天会下雨。", ["あめが", "ふるらしいです", "あしたは"],
              ["あしたはあめがふるらしいです"]),
        tiles(f"{p}-tiles-02", 2, "为了健康，我每天跑步。", ["ために", "けんこうの", "はしっています", "まいにち"],
              ["けんこうのためにまいにちはしっています"]),
        tiles(f"{p}-tiles-03", 3, "下个月我打算去旅行。", ["りょこうする", "つもりです", "らいげつ"],
              ["らいげつりょこうするつもりです"]),
        tiles(f"{p}-tiles-04", 4, "我会提前订好酒店。", ["よやくして", "ホテルを", "おきます"],
              ["ホテルをよやくしておきます"]),
        tiles(f"{p}-tiles-05", 5, "要是早点睡就好了。", ["はやく", "よかったです", "ねれば"],
              ["はやくねればよかったです"]),
    ]
    write_items = [
        open_item(f"{p}-write-01", 1,
                  "下周你要和朋友去旅行，上次因为没准备很辛苦。用至少三个这课的语法写 2–3 句。",
                  "まえの りょこうでは じゅんびが たりなくて たいへんでした。もっと はやく じゅんびすれば よかったです。"
                  "こんどは たのしむ ために、ホテルを よやくして おく つもりです。",
                  "上次旅行准备不足，很辛苦。要是早点准备就好了。这次为了玩得开心，我打算提前订好酒店。"),
    ]
    return assignment(
        "plans", "日语 ③ らしい · ～ればよかった · ～ておく · ～ために · ～つもり",
        "練習：らしい・ればよかった・ておく・ために・つもり",
        [
            section(f"{p}-pick", "① 选语法", "选出放进句子里最合适的一项。", "single_choice", grammar_items),
            section(f"{p}-regret", "② ～ればよかった", "看情况，选出“要是……就好了”的正确说法。",
                    "single_choice", regret_items),
            section(f"{p}-tiles", "③ 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
            section(f"{p}-write", "④ 小故事", "自由写作，不自动判分，写完对照参考作答。", "open_response", write_items),
        ],
    )


# ── 4. ～続ける · い形容词く＋动词 · だからこそ · 词汇 ──────────────────────
def lesson_keep() -> dict:
    p = "jp-keep"
    keep = [
        ("3じかん ゲームを しています。", "3じかん ゲームを しつづけています",
         ["3じかん ゲームを してつづけています", "3じかん ゲームを するつづけています"]),
        ("あめが ずっと ふっています。", "あめが ふりつづけています",
         ["あめが ふってつづけています", "あめが ふるつづけています"]),
        ("かれは 10ねん おなじ かいしゃで はたらいています。", "かれは 10ねん おなじ かいしゃで はたらきつづけています",
         ["かれは 10ねん おなじ かいしゃで はたらいてつづけています", "かれは 10ねん おなじ かいしゃで はたらくつづけています"]),
        ("ゆめを あきらめないで、おいかけます。", "ゆめを おいつづけます",
         ["ゆめを おってつづけます", "ゆめを おうつづけます"]),
        ("よる おそくまで ともだちと はなしていました。", "よる おそくまで ともだちと はなしつづけていました",
         ["よる おそくまで ともだちと はなしてつづけていました", "よる おそくまで ともだちと はなすつづけていました"]),
    ]
    keep_items = [
        choice(f"{p}-keep-{n:02d}", n, f"{base}→ 用 ～つづける：", answer, wrong, note="ます形去掉 ます＋つづける。")
        for n, (base, answer, wrong) in enumerate(keep, start=1)
    ]
    adverbs = [("はやい", "おきる", "早起"), ("おおきい", "かく", "写大一点"), ("やすい", "かう", "便宜地买"),
               ("たかい", "とぶ", "跳得高"), ("わかい", "みえる", "看起来年轻"), ("おそい", "ねる", "晚睡")]
    adverb_items = [
        choice(f"{p}-adv-{n:02d}", n, f"{adj} ＋ {verb} →", f"{adj[:-1]}く {verb}",
               [f"{adj[:-1]}いに {verb}", f"{adj[:-1]}くて {verb}"], zh, "い形容词修饰动词：い → く。")
        for n, (adj, verb, zh) in enumerate(adverbs, start=1)
    ]
    because = [
        (f"かぞくが たいせつ{GAP}、いっしょの じかんを だいじに したいです。", "だからこそ", ["なのに", "だけど"],
         "正因为家人重要，我想珍惜在一起的时间。"),
        (f"しっぱいする ことが ある{GAP}、つづける ことが たいせつです。", "からこそ", ["のに", "けど"],
         "正因为会失败，坚持才重要。"),
        (f"じぶんの ゆめ{GAP}、あきらめたくないです。", "だからこそ", ["なのに", "でも"],
         "正因为是自己的梦想，才不想放弃。"),
    ]
    because_items = [
        choice(f"{p}-because-{n:02d}", n, prompt, answer, wrong, zh, "だからこそ＝正因为……才。")
        for n, (prompt, answer, wrong, zh) in enumerate(because, start=1)
    ]
    words = [
        (f"あめの ひは {GAP}に きを つけて ください。", "あしもと", ["ほどう", "みらい"], "下雨天请注意脚下。"),
        (f"くるまが おおいので、{GAP}を あるきましょう。", "ほどう", ["あしもと", "みらい"], "车很多，我们走人行道吧。"),
        (f"しけんの まえに、ともだちが {GAP}くれました。", "はげまして", ["くりかえして", "いだいて"], "考试前朋友鼓励了我。"),
        (f"おなじ まちがいを {GAP}ないように します。", "くりかえさ", ["はげまさ", "あゆま"], "我会注意不再犯同样的错误。"),
        (f"{GAP}ころ、よく こうえんで あそびました。", "おさない", ["すなおな", "からい"], "小时候我常在公园玩。"),
        (f"せんせいの アドバイスを {GAP}に ききます。", "すなお", ["おさない", "からい"], "我坦率地听老师的建议。"),
        (f"しょうらいに おおきな ゆめを {GAP}います。", "いだいて", ["はげまして", "くりかえして"], "我对未来怀有大大的梦想。"),
    ]
    word_items = [
        choice(f"{p}-word-{n:02d}", n, prompt, answer, wrong, zh)
        for n, (prompt, answer, wrong, zh) in enumerate(words, start=1)
    ]
    tile_items = [
        tiles(f"{p}-tiles-01", 1, "我每天都在坚持学日语。", ["べんきょうしつづけています", "にほんごを", "まいにち"],
              ["まいにちにほんごをべんきょうしつづけています"]),
        tiles(f"{p}-tiles-02", 2, "请把名字写大一点。", ["なまえを", "かいてください", "おおきく"],
              ["なまえをおおきくかいてください"]),
        tiles(f"{p}-tiles-03", 3, "正因为难，才有意思。", ["むずかしい", "おもしろいです", "からこそ"],
              ["むずかしいからこそおもしろいです"]),
    ]
    return assignment(
        "keep", "日语 ④ ～つづける · い形容词＋动词 · だからこそ · 词汇",
        "練習：続ける・〜く・だからこそ",
        [
            section(f"{p}-keep", "① ～つづける", "选出用「～つづける」改写后的正确句子。", "single_choice", keep_items),
            section(f"{p}-adv", "② い形容词 → ～く", "选出 い形容词修饰动词的正确形式。", "single_choice", adverb_items),
            section(f"{p}-because", "③ だからこそ", "选出放进句子里最合适的一项。", "single_choice", because_items),
            section(f"{p}-word", "④ 这课的词", "选出放进句子里最合适的词。", "single_choice", word_items),
            section(f"{p}-tiles", "⑤ 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
        ],
    )


# ── 5. ～そうです · ～すぎる · あなたなら どうする ──────────────────────────
def lesson_looks() -> dict:
    p = "jp-looks"
    looks = [
        ("そらが くらくて、くもが くろいです。", "あめが ふりそうです", ["あめが ふるそうです", "あめが ふりすぎます"],
         "好像要下雨了。", "看起来 → ます形＋そう；ふるそうです 是“听说会下雨”。"),
        ("とても きれいな ケーキです。", "おいしそうです", ["おいしいそうです", "おいしすぎます"],
         "看起来很好吃。", "い形容词：去掉 い＋そう。"),
        ("ともだちが ずっと あくびを しています。", "ねむそうです", ["ねむいそうです", "ねむすぎます"],
         "朋友看起来很困。", ""),
        ("とても たかい ジェットコースターです。", "こわそうです", ["こわいそうです", "こわくそうです"],
         "看起来很可怕。", ""),
        ("この ラーメンは スープが まっかです。", "からそうです", ["からいそうです", "からくそうです"],
         "看起来很辣。", ""),
        ("ひょうばんの いい ほんです。", "よさそうです", ["いいそうです", "よそうです"],
         "看起来不错。", "いい → よさそう（特殊）。"),
    ]
    looks_items = [
        choice(f"{p}-looks-{n:02d}", n, f"{situation}→", answer, wrong, zh, note)
        for n, (situation, answer, wrong, zh, note) in enumerate(looks, start=1)
    ]
    too = [
        ("この かばんは とても たかいです。", "たかすぎます", ["たかいすぎます", "たかくすぎます"], "这个包太贵了。"),
        ("きのう たくさん たべました。", "たべすぎました", ["たべるすぎました", "たべてすぎました"], "昨天吃太多了。"),
        ("この へやは とても しずかです。", "しずかすぎます", ["しずかなすぎます", "しずかにすぎます"], "这个房间太安静了。"),
        ("きのう ゲームを 6じかん しました。", "ゲームを しすぎました", ["ゲームを するすぎました", "ゲームを してすぎました"],
         "昨天游戏玩太多了。"),
        ("この コーヒーは とても あついです。", "あつすぎます", ["あついすぎます", "あつくすぎます"], "这杯咖啡太烫了。"),
    ]
    too_items = [
        choice(f"{p}-too-{n:02d}", n, f"{situation}→", answer, wrong, zh,
               "い形容词去 い / な形容词去 な / 动词ます形去 ます，再接 すぎる。")
        for n, (situation, answer, wrong, zh) in enumerate(too, start=1)
    ]
    what_if = [
        ("ともだちが やくそくの じかんに 30ぷん おくれました。",
         "すこし まちます。それから でんわを かけます。", "我会等一会儿，然后给他打电话。"),
        ("みせで かった ふくが ちいさすぎました。",
         "みせに もっていって、ちがう サイズに かえて もらいます。", "我会拿去店里，请他们换别的尺码。"),
        ("みちで さいふを ひろいました。", "こうばんに とどけます。", "我会交到派出所。"),
        ("らいしゅう 1しゅうかん やすみが あります。", "おんせんに いって、ゆっくり やすみたいです。",
         "我想去泡温泉，好好休息。"),
    ]
    what_items = [
        open_item(f"{p}-what-{n:02d}", n, f"{situation} あなたなら どうしますか。", model, zh)
        for n, (situation, model, zh) in enumerate(what_if, start=1)
    ]
    return assignment(
        "looks", "日语 ⑤ ～そうです（看起来）· ～すぎる · あなたなら どうする",
        "練習：そうです・すぎる",
        [
            section(f"{p}-looks", "① ～そうです", "看情况，选出“看起来……”的正确说法。", "single_choice", looks_items),
            section(f"{p}-too", "② ～すぎる", "选出“太……了”的正确说法。", "single_choice", too_items),
            section(f"{p}-what", "③ あなたなら どうする？", "用自己的话回答，不自动判分，写完对照参考作答。",
                    "open_response", what_items),
        ],
    )


# ── 6. や · ～く＋动词 · ～やすい／～にくい · すぐ · 阅读 ─────────────────
STORY = (
    "「あたらしい がっこう」　ユキは こんげつから あたらしい がっこうに かよって います。"
    "がっこうは えきから ちかいです。でんしゃや バスで いく ことが できます。"
    "でも、ユキは いつも あるいて いきます。あるくのは からだに いいからです。"
    "あたらしい がっこうの じゅぎょうは まえの がっこうより わかりやすいです。クラスの ともだちも やさしいです。"
    "でも、あさ 7じに おきるのは たいへんです。ユキは よる おそく ねると、あさ はやく おきにくいです。"
    "きのうは とても つかれていたので、いえに かえって すぐ ねました。"
)


def lesson_easy() -> dict:
    p = "jp-easy"
    ya = [
        ("スーパーで りんごを かいます。みかんも かいます。", "スーパーで りんごや みかんを かいます",
         ["スーパーで りんごを みかんや かいます", "スーパーで りんごや みかんや を かいます"]),
        ("へやに ソファが あります。テレビも あります。", "へやに ソファや テレビが あります",
         ["へやに ソファが テレビや あります", "へやに ソファや が テレビ あります"]),
        ("やすみの ひは そうじを します。せんたくも します。", "やすみの ひは そうじや せんたくを します",
         ["やすみの ひは そうじを せんたくや します", "やすみの ひは そうじや を せんたく します"]),
    ]
    ya_items = [
        choice(f"{p}-ya-{n:02d}", n, f"{base}→ 用「や」合成一句：", answer, wrong, note="AやB＝A、B 等等（举例）。")
        for n, (base, answer, wrong) in enumerate(ya, start=1)
    ]
    adverb_words = ["はやく", "おおきく", "やすく", "わかく"]
    adverbs = [
        ("あと 3ぷんで バスが でます。", f"バスていまで {GAP} あるきます。", "はやく", "还有三分钟车就开了，快点走去车站。"),
        ("じが ちいさくて よめません。", f"もっと {GAP} かいてください。", "おおきく", "字太小看不清，请写大一点。"),
        ("セールで ふくを はんがくで かいました。", f"ふくを {GAP} かいました。", "やすく", "打折时半价买了衣服。"),
        ("そふは 70さいですが、60さいぐらいに みえます。", f"そふは {GAP} みえます。", "わかく", "爷爷看起来很年轻。"),
    ]
    adverb_items = [
        choice(f"{p}-adv-{n:02d}", n, f"{situation}→ {sentence}", answer,
               [word for word in adverb_words if word != answer], zh)
        for n, (situation, sentence, answer, zh) in enumerate(adverbs, start=1)
    ]
    easy = [
        (f"この ペンは かるくて、{GAP}です。", "かきやすい", ["かきにくい", "かくやすい"], "这支笔很轻，好写。"),
        (f"この ほんは かんじが おおくて、{GAP}です。", "よみにくい", ["よみやすい", "よむにくい"], "这本书汉字多，难读。"),
        (f"この くつは かるいので、{GAP}です。", "あるきやすい", ["あるきにくい", "あるくやすい"], "这双鞋很轻，好走。"),
        (f"この くすりは おおきくて、{GAP}です。", "のみにくい", ["のみやすい", "のむにくい"], "这药片太大，难咽。"),
        (f"せんせいの せつめいは とても {GAP}です。", "わかりやすい", ["わかりにくい", "わかるやすい"], "老师的说明很好懂。"),
    ]
    easy_items = [
        choice(f"{p}-easy-{n:02d}", n, prompt, answer, wrong, zh, "ます形去掉 ます＋やすい（容易）／にくい（难）。")
        for n, (prompt, answer, wrong, zh) in enumerate(easy, start=1)
    ]
    soon = [
        ("ともだち：「バスが もう きましたよ！」", "すぐ いきます！", ["あとで いきます", "ゆっくり いきます"], "马上来！"),
        ("おかあさん：「ばんごはんが できたよ！」", "すぐ たべに いきます！", ["あとで たべます", "たべたくないです"], "马上去吃！"),
        ("しごとが おわりました。とても つかれています。", "いえに かえって、すぐ ねます", ["ゆっくり しごとを します", "もっと はたらきます"],
         "回家马上睡觉。"),
    ]
    soon_items = [
        choice(f"{p}-soon-{n:02d}", n, f"{situation}→ あなた：", answer, wrong, zh)
        for n, (situation, answer, wrong, zh) in enumerate(soon, start=1)
    ]
    reading = [
        ("ユキは いつから あたらしい がっこうに かよって いますか。", "こんげつから", ["せんげつから", "らいげつから"],
         "这个月开始。"),
        ("がっこうまで なにで いく ことが できますか。", "でんしゃや バスで いけます", ["ひこうきで いけます", "ふねで いけます"],
         "坐电车或公交可以到。"),
        ("どうして ユキは あるいて いきますか。", "あるくのは からだに いいからです",
         ["でんしゃが たかいからです", "がっこうが とおいからです"], "因为走路对身体好。"),
        ("あたらしい がっこうの じゅぎょうは どうですか。", "まえの がっこうより わかりやすいです",
         ["まえの がっこうより むずかしいです", "とても つまらないです"], "比以前的学校好懂。"),
        ("ユキは なにが たいへんですか。", "あさ 7じに おきることです", ["あるくことです", "ともだちを つくることです"],
         "早上七点起床很辛苦。"),
        ("きのう、いえに かえって なにを しましたか。", "すぐ ねました", ["すぐ べんきょうしました", "すぐ でかけました"],
         "马上睡觉了。"),
    ]
    reading_items = [
        choice(f"{p}-read-{n:02d}", n, prompt, answer, wrong, zh)
        for n, (prompt, answer, wrong, zh) in enumerate(reading, start=1)
    ]
    tile_items = [
        tiles(f"{p}-tiles-01", 1, "这个手机很好用。", ["スマホは", "この", "つかいやすいです"],
              ["このスマホはつかいやすいです"]),
        tiles(f"{p}-tiles-02", 2, "他看起来很年轻。", ["わかく", "かれは", "みえます"], ["かれはわかくみえます"]),
        tiles(f"{p}-tiles-03", 3, "我马上回家。", ["かえります", "すぐ", "いえに"],
              ["すぐいえにかえります", "いえにすぐかえります"]),
        tiles(f"{p}-tiles-04", 4, "我买了衣服和食物等。", ["ふくや", "かいました", "たべものを"],
              ["ふくやたべものをかいました"]),
    ]
    return assignment(
        "easy", "日语 ⑥ や · ～く＋动词 · ～やすい／～にくい · すぐ · 阅读",
        "練習：や・やすい・にくい・すぐ",
        [
            section(f"{p}-ya", "① や", "选出用「や」把两句合成一句的正确说法。", "single_choice", ya_items),
            section(f"{p}-adv", "② ～く＋动词", "看情况，选出合适的词：はやく / おおきく / やすく / わかく。",
                    "single_choice", adverb_items),
            section(f"{p}-easy", "③ ～やすい？～にくい？", "选出最合适的一项。", "single_choice", easy_items),
            section(f"{p}-soon", "④ すぐ", "看情况，选出用「すぐ」的回答。", "single_choice", soon_items),
            section(f"{p}-read", "⑤ よみもの", "先读短文，再选答案。" + STORY, "single_choice", reading_items),
            section(f"{p}-tiles", "⑥ 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
        ],
    )


# ── 7. ～わりに · ～たびに · ～ないこともない · ～っぽい · ～づらい ──────────
def lesson_warini() -> dict:
    p = "jp-warini"
    grammar_options = ["わりに", "たびに", "っぽい", "づらい", "こともない"]
    which = [
        (f"この くるまは ふるい{GAP}、よく はしります。", "わりに", "这辆车虽然旧，却跑得很好。"),
        (f"この うたを きく{GAP}、こうこうの ころを おもいだします。", "たびに", "每次听这首歌，都会想起高中时代。"),
        (f"この いすは かたくて、すわり{GAP}です。", "づらい", "这把椅子太硬，坐着难受。"),
        (f"かれは 40さいですが、ふくが わかもの{GAP}です。", "っぽい", "他四十岁了，穿着却像年轻人。"),
        (f"いまから はしれば、まにあわない{GAP}ですが…。", "こともない", "现在跑的话，也不是赶不上……"),
        (f"しゅっちょうの {GAP}、ちがう ホテルに とまります。", "たびに", "每次出差都住不同的酒店。"),
        (f"この スープは みず{GAP}です。", "っぽい", "这汤水水的（太淡）。"),
        (f"かのじょは わかい{GAP}、しっかりしています。", "わりに", "她虽然年轻，却很稳重。"),
        (f"この じは ちいさくて、よみ{GAP}です。", "づらい", "这字太小，难读。"),
        (f"1じかん あるけない{GAP}ですが、つかれると おもいます。", "こともない", "也不是走不了一小时，但我想会累。"),
    ]
    which_items = [
        choice(f"{p}-which-{n:02d}", n, prompt, answer, [o for o in grammar_options if o != answer][:3], zh)
        for n, (prompt, answer, zh) in enumerate(which, start=1)
    ]
    combine = [
        ("この みせは ちいさいです。でも、いつも こんでいます。", "この みせは ちいさい わりに、いつも こんでいます",
         ["この みせは ちいさい たびに、いつも こんでいます", "この みせは ちいさいっぽい、いつも こんでいます"],
         "这家店虽然小，却总是很挤。"),
        ("ひこうきに のります。そのとき いつも すこし きんちょうします。", "ひこうきに のる たびに、すこし きんちょうします",
         ["ひこうきに のる わりに、すこし きんちょうします", "ひこうきに のりづらい、すこし きんちょうします"],
         "每次坐飞机都会有点紧张。"),
        ("たくさん れんしゅうしました。でも、じょうずに なりませんでした。", "たくさん れんしゅうした わりに、じょうずに なりませんでした",
         ["たくさん れんしゅうした たびに、じょうずに なりませんでした", "たくさん れんしゅうしたっぽい、じょうずに なりませんでした"],
         "练了很多，却没有变好。"),
        ("この まちに きます。そのとき いつも おなじ カフェに いきます。", "この まちに くる たびに、おなじ カフェに いきます",
         ["この まちに くる わりに、おなじ カフェに いきます", "この まちに きづらい、おなじ カフェに いきます"],
         "每次来这个城市都去同一家咖啡馆。"),
    ]
    combine_items = [
        choice(f"{p}-combine-{n:02d}", n, f"{base}→", answer, wrong, zh)
        for n, (base, answer, wrong, zh) in enumerate(combine, start=1)
    ]
    could = [
        ("まいにち 5じに おきられますか。", "おきられない ことも ないですが、たいへんです",
         ["おきられる ことも ないです", "おきない たびに たいへんです"], "也不是起不来，但很辛苦。"),
        ("いっしゅうかん ネットなしで せいかつできますか。", "できない ことも ないですが、ふべんだと おもいます",
         ["できる ことも ないです", "できない わりに ふべんです"], "也不是不能，但我想会很不方便。"),
    ]
    could_items = [
        choice(f"{p}-could-{n:02d}", n, question, answer, wrong, zh, "～ないこともない＝也不是不能（但……）。")
        for n, (question, answer, wrong, zh) in enumerate(could, start=1)
    ]
    tile_items = [
        tiles(f"{p}-tiles-01", 1, "他比实际年龄看起来成熟。", ["わりに", "おとなっぽいです", "ねんれいの", "かれは"],
              ["かれはねんれいのわりにおとなっぽいです"]),
        tiles(f"{p}-tiles-02", 2, "每次见他，都会聊工作。", ["はなしをします", "しごとの", "かれにあうたびに"],
              ["かれにあうたびにしごとのはなしをします"]),
        tiles(f"{p}-tiles-03", 3, "这双鞋很难走路。", ["くつは", "この", "あるきづらいです"],
              ["このくつはあるきづらいです"]),
        tiles(f"{p}-tiles-04", 4, "这个设计有点孩子气。", ["このデザインは", "こどもっぽいです", "すこし"],
              ["このデザインはすこしこどもっぽいです"]),
    ]
    write_items = [
        open_item(f"{p}-write-01", 1, "用「～わりに」写一句关于你自己的句子。",
                  "わたしの へやは せまい わりに、すみやすいです。", "我的房间虽然小，却很好住。"),
        open_item(f"{p}-write-02", 2, "用「～たびに」写一句关于你自己的句子。",
                  "にほんに いく たびに、ラーメンを たべます。", "每次去日本，我都会吃拉面。"),
        open_item(f"{p}-write-03", 3, "用「～ないこともない」写一句关于你自己的句子。",
                  "マラソンを はしれない ことも ないですが、たいへんだと おもいます。", "也不是跑不了马拉松，但我想会很辛苦。"),
    ]
    return assignment(
        "warini", "日语 ⑦ ～わりに · ～たびに · ～ないこともない · ～っぽい · ～づらい",
        "練習：わりに・たびに・ないこともない・っぽい・づらい",
        [
            section(f"{p}-which", "① 哪个语法？", "选出放进句子里最自然的语法。", "single_choice", which_items),
            section(f"{p}-combine", "② 合成一句", "选出用「わりに」或「たびに」把两句合成一句的正确说法。",
                    "single_choice", combine_items),
            section(f"{p}-could", "③ ～ないこともない", "选出用「～ないこともない」的正确回答。", "single_choice", could_items),
            section(f"{p}-tiles", "④ 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
            section(f"{p}-write", "⑤ 写自己", "自由写作，不自动判分，写完对照参考作答。", "open_response", write_items),
        ],
    )


def build_assignments() -> list[dict]:
    return [lesson_past(), lesson_potential(), lesson_plans(), lesson_keep(),
            lesson_looks(), lesson_easy(), lesson_warini()]


def upsert(homework_path: Path, new_assignments: list[dict]) -> None:
    data = json.loads(homework_path.read_text(encoding="utf-8"))
    by_id = {assignment["id"]: assignment for assignment in new_assignments}
    kept = []
    for existing in data.get("assignments", []):
        kept.append(by_id.pop(existing.get("id"), existing))
    data["assignments"] = kept + [a for a in new_assignments if a["id"] in by_id]
    homework_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--homework", type=Path, default=HOMEWORK)
    args = parser.parse_args(argv)
    assignments = build_assignments()
    ids = [item["id"] for a in assignments for s in a["sections"] for item in s["items"]]
    assert len(ids) == len(set(ids))
    upsert(args.homework, assignments)
    print(json.dumps({
        "assignments": len(assignments),
        "questions": len(ids),
        "homework": str(args.homework),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
