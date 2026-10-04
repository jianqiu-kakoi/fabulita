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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from my_japanese_lesson_notes import LESSON_NOTES  # noqa: E402
from my_japanese_option_notes import OPTION_NOTES  # noqa: E402


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
           translation: str = "", note: str = "",
           option_notes: dict[str, tuple[str, str]] | None = None) -> dict:
    options = [answer, *distractors]
    assert len(set(options)) == len(options), item_id
    item = {
        "id": item_id,
        "number": number,
        "prompt": prompt,
        "options": _shuffled(options, item_id),
        "answers": [answer],
        "canonicalAnswer": answer,
        "optionNotes": {
            option: {"gloss": text[0], "english": text[1]}
            for option in options
            for text in [(option_notes or {}).get(option) or OPTION_NOTES[option]]
        },
    }
    if translation:
        item["answerTranslation"] = translation
    notes = [text for text in (("中文：" + translation) if translation else "", ("提示：" + note) if note else "") if text]
    if notes:
        item["ambiguityNote"] = "　".join(notes)
    return item


def _chunks(sentence: str) -> list[str]:
    return [part for part in re.split(r"[\s、]+", sentence) if part]


def sentence_tiles(item_id: str, number: int, prompt: str, answer: str, wrong: list[str],
                   translation: str = "", note: str = "") -> dict:
    """Build the right sentence from shuffled tiles; look-alike tiles come from the wrong options."""
    right = _chunks(answer)
    decoys: list[str] = []
    for option in wrong:
        for part in _chunks(option):
            if part not in right and part not in decoys:
                decoys.append(part)
    decoys = decoys[:3]
    tile_list = right + decoys
    _rng(item_id, "tiles").shuffle(tile_list)
    if tile_list[:len(right)] == right:
        tile_list = tile_list[1:] + tile_list[:1]
    compact = "".join(right)
    item = {
        "id": item_id,
        "number": number,
        "prompt": prompt,
        "wordTiles": tile_list,
        "tileJoiner": "",
        "answers": [compact, answer],
        "canonicalAnswer": answer,
    }
    notes = [text for text in (("中文：" + translation) if translation else "", ("提示：" + note) if note else "") if text]
    if translation:
        item["answerTranslation"] = translation
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
               tables: list[dict] | None = None, heading: str = "", intro: str = "") -> dict:
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
        # Japanese conjugates by verb ending, not by person.
        out["referenceHeading"] = heading or "先看规则表"
        out["referenceIntro"] = intro or "可以一边看表一边练习；熟悉以后再把表收起来测试自己。"
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
        tables=[
            table(f"{p}-te", "て形", "第 1 步：把动词变成て形（看动词结尾）", [
                ("～る（一段：たべる・みる）", "去 る＋て：たべて・みて"),
                ("～う・～つ・～る（五段）", "って：かって・まって・つくって"),
                ("～む・～ぶ・～ぬ", "んで：よんで・あそんで・しんで"),
                ("～く", "いて：かいて・きいて"),
                ("～ぐ", "いで：およいで"),
                ("～す", "して：はなして"),
                ("例外", "いく→いって・する→して・くる→きて"),
            ]),
            table(f"{p}-teita", "ていた", "第 2 步：て形＋いた（随意）／いました（礼貌）＝当时正在……", [
                ("よむ → よんで", "よんでいた・よんでいました"),
                ("かく → かいて", "かいていた・かいていました"),
                ("いく → いって", "いっていた・いっていました"),
                ("する → して", "していた・していました"),
            ]),
            table(f"{p}-ta", "た", "对比：～た／～ました＝做完了（把て换成た）", [
                ("よんで → よんだ", "よんだ・よみました"),
                ("かいて → かいた", "かいた・かきました"),
                ("いって → いった", "いった・いきました"),
                ("して → した", "した・しました"),
            ]),
        ],
        heading="先看规则表：动词结尾 → て形 → ～ていた",
        intro="日语按动词结尾变形，和人称无关。先把动词变成て形，再加 いた／いました；把て换成た就是过去式。",
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
        heading="先看规则表：动词结尾 → 可能形",
        intro="日语按动词结尾变形，和人称无关。一段动词加 られる，五段动词把最后的う段音变成え段再加る。",
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
        sentence_tiles(f"{p}-regret-{n:02d}", n, f"{situation}→ 你会说：", answer, wrong, zh,
                       "后悔 → 动词ば形＋よかった。")
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
            section(f"{p}-regret", "② ～ればよかった", "看情况，点词块拼出“要是……就好了”的句子。里面混了干扰词块。",
                    "text_input", regret_items),
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
        sentence_tiles(f"{p}-keep-{n:02d}", n, f"{base}→ 用 ～つづける：", answer, wrong,
                       note="ます形去掉 ます＋つづける。")
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
            section(f"{p}-keep", "① ～つづける", "用「～つづける」改写：按顺序点词块拼出句子。里面混了几个错误形式，别选。",
                    "text_input", keep_items),
            section(f"{p}-tiles", "② 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
            section(f"{p}-adv", "③ い形容词 → ～く", "选出 い形容词修饰动词的正确形式。", "single_choice", adverb_items),
            section(f"{p}-because", "④ だからこそ", "选出放进句子里最合适的一项。", "single_choice", because_items),
            section(f"{p}-word", "⑤ 这课的词", "选出放进句子里最合适的词。", "single_choice", word_items),
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
        sentence_tiles(f"{p}-ya-{n:02d}", n, f"{base}→ 用「や」合成一句：", answer, wrong,
                       note="AやB＝A、B 等等（举例）；最后一个名词后面接助词。")
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
            section(f"{p}-ya", "① や", "用「や」把两句合成一句：按顺序点词块，里面混了干扰词块。", "text_input", ya_items),
            section(f"{p}-tiles", "② 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
            section(f"{p}-adv", "③ ～く＋动词", "看情况，选出合适的词：はやく / おおきく / やすく / わかく。",
                    "single_choice", adverb_items),
            section(f"{p}-easy", "④ ～やすい？～にくい？", "选出最合适的一项。", "single_choice", easy_items),
            section(f"{p}-soon", "⑤ すぐ", "看情况，选出用「すぐ」的回答。", "single_choice", soon_items),
            section(f"{p}-read", "⑥ よみもの", "先读短文，再选答案。" + STORY, "single_choice", reading_items),
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
        sentence_tiles(f"{p}-combine-{n:02d}", n, f"{base}→", answer, wrong, zh,
                       "虽然……却 → わりに；每次……都 → たびに。")
        for n, (base, answer, wrong, zh) in enumerate(combine, start=1)
    ]
    could = [
        ("まいにち 5じに おきられますか。", "おきられない ことも ないですが、たいへんです",
         ["おきられる ことも ないです", "おきない たびに たいへんです"], "也不是起不来，但很辛苦。"),
        ("いっしゅうかん ネットなしで せいかつできますか。", "できない ことも ないですが、ふべんだと おもいます",
         ["できる ことも ないです", "できない わりに ふべんです"], "也不是不能，但我想会很不方便。"),
    ]
    could_items = [
        sentence_tiles(f"{p}-could-{n:02d}", n, question, answer, wrong, zh, "～ないこともない＝也不是不能（但……）。")
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
            section(f"{p}-combine", "② 合成一句", "用「わりに」或「たびに」把两句合成一句：按顺序点词块，里面混了干扰词块。",
                    "text_input", combine_items),
            section(f"{p}-could", "③ ～ないこともない", "用「～ないこともない」回答：按顺序点词块，里面混了干扰词块。",
                    "text_input", could_items),
            section(f"{p}-tiles", "④ 连词成句", "看中文意思，按顺序点词块拼成句子。", "text_input", tile_items),
            section(f"{p}-write", "⑤ 写自己", "自由写作，不自动判分，写完对照参考作答。", "open_response", write_items),
        ],
    )


# ── 0. て形 ──────────────────────────────────────────────────────────
def lesson_te() -> dict:
    p = "jp-te"
    groups = ["一段动词", "五段动词", "不规则动词"]
    group_items = [
        ("たべる", "一段动词", "た-べ-る：る 前面是 e 段。"),
        ("みる", "一段动词", "み-る：る 前面是 i 段。"),
        ("かう", "五段动词", "不以 る 结尾。"),
        ("よむ", "五段动词", "不以 る 结尾。"),
        ("つくる", "五段动词", "つく-る：る 前面是 u 段，所以是五段。"),
        ("かえる（回家）", "五段动词", "例外：看起来像一段，其实是五段（かえって）。"),
        ("はいる", "五段动词", "例外：看起来像一段，其实是五段（はいって）。"),
        ("おきる", "一段动词", "お-き-る：る 前面是 i 段。"),
        ("ねる", "一段动词", "ね-る：る 前面是 e 段。"),
        ("はしる", "五段动词", "例外：看起来像一段，其实是五段（はしって）。"),
        ("する", "不规则动词", "只有 する 和 くる 是不规则动词。"),
        ("くる", "不规则动词", "只有 する 和 くる 是不规则动词。"),
    ]
    group_choices = [
        choice(f"{p}-group-{n:02d}", n, f"{verb} 是哪一类动词？", answer,
               [g for g in groups if g != answer], note=note)
        for n, (verb, answer, note) in enumerate(group_items, start=1)
    ]
    forms = [
        ("かう", "かって", ["かいて", "かうて", "かんで"], "う → って"),
        ("まつ", "まって", ["まちて", "まつて", "まんで"], "つ → って"),
        ("つくる", "つくって", ["つくて", "つくりて", "つくんで"], "五段 る → って"),
        ("よむ", "よんで", ["よみて", "よって", "よむで"], "む → んで"),
        ("あそぶ", "あそんで", ["あそびて", "あそって", "あそぶて"], "ぶ → んで"),
        ("しぬ", "しんで", ["しにて", "しって", "しぬて"], "ぬ → んで"),
        ("かく", "かいて", ["かきて", "かって", "かいで"], "く → いて"),
        ("きく", "きいて", ["ききて", "きって", "きいで"], "く → いて"),
        ("およぐ", "およいで", ["およぎて", "およいて", "およって"], "ぐ → いで"),
        ("はなす", "はなして", ["はなって", "はなすて", "はないて"], "す → して"),
        ("たべる", "たべて", ["たべって", "たべりて", "たべんで"], "一段：去 る＋て"),
        ("みる", "みて", ["みって", "みりて", "みんで"], "一段：去 る＋て"),
        ("いく", "いって", ["いいて", "いきて", "いくて"], "例外：いく → いって"),
        ("する", "して", ["すて", "しって", "すって"], "不规则：する → して"),
        ("くる", "きて", ["くて", "こって", "きって"], "不规则：くる → きて"),
        ("かえる（回家）", "かえって", ["かえて", "かえりて", "かえんで"], "かえる 是五段：る → って"),
        ("はいる", "はいって", ["はいて", "はいりて", "はいんで"], "はいる 是五段：る → って"),
        ("のむ", "のんで", ["のみて", "のって", "のむで"], "む → んで"),
    ]
    form_choices = [
        choice(f"{p}-form-{n:02d}", n, f"{verb} → て形", answer, wrong, note=note)
        for n, (verb, answer, wrong, note) in enumerate(forms, start=1)
    ]
    past = [
        ("よんで", "よんだ", ["よんた", "よみた"]),
        ("かいて", "かいた", ["かいだ", "かきた"]),
        ("はなして", "はなした", ["はなしだ", "はなった"]),
        ("いって", "いった", ["いきた", "いいた"]),
        ("およいで", "およいだ", ["およいた", "およぎた"]),
        ("たべて", "たべた", ["たべだ", "たべった"]),
    ]
    past_choices = [
        choice(f"{p}-ta-{n:02d}", n, f"{te} → た形（过去式）", answer, wrong, note="て→た，で→だ。")
        for n, (te, answer, wrong) in enumerate(past, start=1)
    ]
    sentences = [
        (f"ちょっと {GAP} ください。（まつ）", "まって", ["まちて", "まつて"], "请稍等一下。"),
        (f"ここで くつを {GAP} ください。（ぬぐ）", "ぬいで", ["ぬいて", "ぬぎて"], "请在这里脱鞋。"),
        (f"しゅくだいを {GAP} おきます。（する）", "して", ["すて", "しって"], "我先把作业做好。"),
        (f"あさごはんを {GAP}、がっこうへ いきます。（たべる）", "たべて", ["たべって", "たべりて"],
         "吃完早饭去学校。"),
        (f"でんしゃに {GAP} いきます。（のる）", "のって", ["のりて", "のんで"], "坐电车去。"),
        (f"きのうの よる、おんがくを {GAP} いました。（きく）", "きいて", ["きって", "ききて"], "昨晚我在听音乐。"),
    ]
    sentence_choices = [
        choice(f"{p}-sent-{n:02d}", n, prompt, answer, wrong, zh)
        for n, (prompt, answer, wrong, zh) in enumerate(sentences, start=1)
    ]
    return assignment(
        "te", "日语 ⓪ て形：怎么变、怎么认（先学这个）",
        "練習：て形",
        [
            section(f"{p}-group", "① 判断动词类别", "先判断动词是一段、五段还是不规则动词。", "single_choice", group_choices),
            section(f"{p}-form", "② 变成て形", "按类别和最后一个字变成て形。", "single_choice", form_choices),
            section(f"{p}-ta", "③ て形 → た形", "把 て 换成 た、で 换成 だ。", "single_choice", past_choices),
            section(f"{p}-sent", "④ 句子里用て形", "看括号里的动词，选出正确的て形。", "single_choice", sentence_choices),
            section(f"{p}-mix", "⑤ 各种形式混合", "同一个动词的不同形式放在一起，选出题目要的那一个。",
                    "single_choice", verb_form_mix()),
        ],
        tables=[table(f"{p}-forms", "形式", "动词形式总表（たべる＝一段 · よむ＝五段）", [
            (f"{name}：{use}", f"{VERB_FORMS['たべる'][key]} · {VERB_FORMS['よむ'][key]}")
            for key, name, use in FORM_KINDS
        ])],
        heading="动词形式总表：同一个动词的各种形式",
        intro="日语动词靠改词尾来表达时态、否定、请求、可能等。所有形式都按同一套分类来变：一段、五段、不规则。",
    )


# (key, name, what it does)
FORM_KINDS = [
    ("dict", "辞书形", "原形；随意体现在 / 将来"),
    ("masu", "ます形", "礼貌体"),
    ("nai", "ない形", "否定：不……"),
    ("te", "て形", "连接后面的成分"),
    ("ta", "た形", "随意体过去：……了"),
    ("pot", "可能形", "能、会"),
    ("ba", "ば形", "条件：如果……"),
    ("vol", "意向形", "……吧 / 我要……"),
]
FORM_NAMES = {key: name for key, name, _ in FORM_KINDS}
FORM_USES = {key: use for key, _, use in FORM_KINDS}
VERB_FORMS = {
    "たべる": dict(dict="たべる", masu="たべます", nai="たべない", te="たべて", ta="たべた", pot="たべられる", ba="たべれば", vol="たべよう"),
    "よむ": dict(dict="よむ", masu="よみます", nai="よまない", te="よんで", ta="よんだ", pot="よめる", ba="よめば", vol="よもう"),
    "かく": dict(dict="かく", masu="かきます", nai="かかない", te="かいて", ta="かいた", pot="かける", ba="かけば", vol="かこう"),
    "はなす": dict(dict="はなす", masu="はなします", nai="はなさない", te="はなして", ta="はなした", pot="はなせる", ba="はなせば", vol="はなそう"),
    "いく": dict(dict="いく", masu="いきます", nai="いかない", te="いって", ta="いった", pot="いける", ba="いけば", vol="いこう"),
    "かう": dict(dict="かう", masu="かいます", nai="かわない", te="かって", ta="かった", pot="かえる", ba="かえば", vol="かおう"),
    "まつ": dict(dict="まつ", masu="まちます", nai="またない", te="まって", ta="まった", pot="まてる", ba="まてば", vol="まとう"),
    "みる": dict(dict="みる", masu="みます", nai="みない", te="みて", ta="みた", pot="みられる", ba="みれば", vol="みよう"),
    "する": dict(dict="する", masu="します", nai="しない", te="して", ta="した", pot="できる", ba="すれば", vol="しよう"),
    "くる": dict(dict="くる", masu="きます", nai="こない", te="きて", ta="きた", pot="こられる", ba="くれば", vol="こよう"),
}
VERB_MEANINGS = {"たべる": ("吃", "eat"), "よむ": ("读", "read"), "かく": ("写", "write"), "はなす": ("说", "speak"),
                 "いく": ("去", "go"), "かう": ("买", "buy"), "まつ": ("等", "wait"), "みる": ("看", "see"),
                 "する": ("做", "do"), "くる": ("来", "come")}
MIX_QUESTIONS = [
    ("たべる", "nai", ""), ("よむ", "masu", ""), ("かく", "ta", ""), ("はなす", "pot", ""),
    ("いく", "te", "いく 是例外：いって。"), ("かう", "nai", "う 结尾的五段：ない形是 わない（かわない）。"),
    ("まつ", "ba", ""), ("みる", "pot", ""), ("する", "pot", "する 的可能形是 できる。"),
    ("くる", "nai", "くる 的ない形是 こない。"), ("よむ", "vol", ""), ("たべる", "ba", ""),
    ("はなす", "nai", ""), ("かく", "pot", ""), ("くる", "masu", "くる 的ます形是 きます。"), ("まつ", "te", ""),
]


def verb_form_mix() -> list[dict]:
    items = []
    for number, (verb, key, note) in enumerate(MIX_QUESTIONS, start=1):
        item_id = f"jp-te-mix-{number:02d}"
        forms = VERB_FORMS[verb]
        others = [k for k in forms if k != key and forms[k] != forms[key]]
        picked = random.Random(int(hashlib.sha256(item_id.encode()).hexdigest(), 16)).sample(others, 3)
        zh, en = VERB_MEANINGS[verb]
        notes = {forms[k]: (f"{verb} 的{FORM_NAMES[k]}（{FORM_USES[k]}）", f"{FORM_NAMES[k]} of {verb} ({en})")
                 for k in [key, *picked]}
        items.append(choice(item_id, number, f"{verb}（{zh}）的{FORM_NAMES[key]}是？", forms[key],
                            [forms[k] for k in picked], note=note, option_notes=notes))
    return items


# ── 图片动词：22 个动作，配已审核的 Icons8 图 ─────────────────────────────
ACTIONS_FILE = ROOT / "examples" / "my-japanese" / "assets" / "vocab-images" / "actions.json"
# (picture key, dictionary form, 中文, masu, nai, te, ta)
ACTION_VERBS = [
    ("correr", "はしる", "跑", "はしります", "はしらない", "はしって", "はしった"),
    ("nadar", "およぐ", "游泳", "およぎます", "およがない", "およいで", "およいだ"),
    ("bailar", "おどる", "跳舞", "おどります", "おどらない", "おどって", "おどった"),
    ("cantar", "うたう", "唱歌", "うたいます", "うたわない", "うたって", "うたった"),
    ("comer", "たべる", "吃", "たべます", "たべない", "たべて", "たべた"),
    ("beber", "のむ", "喝", "のみます", "のまない", "のんで", "のんだ"),
    ("leer", "よむ", "读", "よみます", "よまない", "よんで", "よんだ"),
    ("escribir", "かく", "写", "かきます", "かかない", "かいて", "かいた"),
    ("cocinar", "りょうりする", "做饭", "りょうりします", "りょうりしない", "りょうりして", "りょうりした"),
    ("caminar", "あるく", "走路", "あるきます", "あるかない", "あるいて", "あるいた"),
    ("dormir", "ねる", "睡觉", "ねます", "ねない", "ねて", "ねた"),
    ("estudiar", "べんきょうする", "学习", "べんきょうします", "べんきょうしない", "べんきょうして", "べんきょうした"),
    ("trabajar", "はたらく", "工作", "はたらきます", "はたらかない", "はたらいて", "はたらいた"),
    ("hablar", "はなす", "说话", "はなします", "はなさない", "はなして", "はなした"),
    ("escuchar", "きく", "听", "ききます", "きかない", "きいて", "きいた"),
    ("mirar", "みる", "看", "みます", "みない", "みて", "みた"),
    ("comprar", "かう", "买", "かいます", "かわない", "かって", "かった"),
    ("lavar", "あらう", "洗", "あらいます", "あらわない", "あらって", "あらった"),
    ("viajar", "りょこうする", "旅行", "りょこうします", "りょこうしない", "りょこうして", "りょこうした"),
    ("abrir", "あける", "打开", "あけます", "あけない", "あけて", "あけた"),
    ("esperar", "まつ", "等", "まちます", "またない", "まって", "まった"),
    ("descansar", "やすむ", "休息", "やすみます", "やすまない", "やすんで", "やすんだ"),
]
ACTION_FORM_NAMES = {"dict": "辞书形", "masu": "ます形", "nai": "ない形", "te": "て形", "ta": "た形"}


def _action_images() -> tuple[dict, dict]:
    data = json.loads(ACTIONS_FILE.read_text(encoding="utf-8"))["images"]
    images, ids = {}, {}
    for key, *_ in ACTION_VERBS:
        image = data[key]["image"]
        assert image.get("reviewed") is True, key
        image_id = f"jp-action-{key}"
        images[image_id] = {**image, "deliver": "file"}
        ids[key] = image_id
    return images, ids


def _verb_forms(row: tuple) -> dict:
    key, dictionary, zh, masu, nai, te, ta = row
    return {"dict": dictionary, "masu": masu, "nai": nai, "te": te, "ta": ta}


def _rng(*seed: object) -> random.Random:
    return random.Random(int(hashlib.sha256(":".join(map(str, seed)).encode()).hexdigest(), 16))


def picture_choice(item_id: str, number: int, prompt: str, image_id: str, answer: str,
                   distractors: list[str], notes: dict[str, tuple[str, str]], note: str = "") -> dict:
    item = choice(item_id, number, prompt, answer, distractors, note=note, option_notes=notes)
    item["imageId"] = image_id
    return item


def lesson_pictures() -> dict:
    p = "jp-pic"
    images, ids = _action_images()
    verbs = {row[1]: row for row in ACTION_VERBS}
    names = list(verbs)
    meaning = {row[1]: (row[2], row[0]) for row in ACTION_VERBS}
    word_notes = {v: (f"{meaning[v][0]}（辞书形）", "dictionary form") for v in names}

    pick_items = []
    for n, row in enumerate(ACTION_VERBS, start=1):
        verb = row[1]
        wrong = _rng(p, "pick", verb).sample([v for v in names if v != verb], 3)
        pick_items.append(picture_choice(f"{p}-pick-{n:02d}", n, "看图，选出对应的日语动词。", ids[row[0]],
                                         verb, wrong, word_notes))

    image_items = []
    for n, row in enumerate(ACTION_VERBS[:12], start=1):
        verb = row[1]
        others = _rng(p, "img", verb).sample([r for r in ACTION_VERBS if r[1] != verb], 2)
        options = [row, *others]
        _rng(p, "img-order", verb).shuffle(options)
        image_items.append({
            "id": f"{p}-image-{n:02d}",
            "number": n,
            "prompt": f"选择与日语 “{verb}” 对应的图片。",
            "options": [o[1] for o in options],
            "answers": [verb],
            "canonicalAnswer": verb,
            "answerTranslation": row[2],
            "ambiguityNote": f"中文：{verb}＝{row[2]}",
            "imageOptions": [{"value": o[1], "imageId": ids[o[0]]} for o in options],
            "optionNotes": {o[1]: {"gloss": f"{o[2]}（辞书形）", "english": "dictionary form"} for o in options},
        })

    doing_items = []
    for n, row in enumerate(ACTION_VERBS[::2], start=1):
        forms = _verb_forms(row)
        answer = forms["te"] + "います"
        wrong = [forms["masu"], forms["nai"], forms["ta"]]
        notes = {
            answer: (f"正在{row[2]}（て形＋います）", "is doing (ている)"),
            forms["masu"]: (f"{row[2]}（ます形：习惯 / 将来）", "does / will do"),
            forms["nai"]: (f"不{row[2]}（ない形）", "does not"),
            forms["ta"]: (f"{row[2]}了（た形：过去）", "did"),
        }
        doing_items.append(picture_choice(f"{p}-doing-{n:02d}", n, "图里的人现在正在做什么？", ids[row[0]],
                                          answer, wrong, notes, "正在做 → て形＋います。"))

    return {
        **assignment(
            "pictures", "日语 图片动词：看图选词 · 看图选形式",
            "練習：絵で覚える動詞",
            [
                section(f"{p}-pick", "① 看图选动词", "观察图片，从四个动词里选出正确的一个。", "single_choice", pick_items),
                section(f"{p}-image", "② 日语选图", "读日语动词，从三张图里选出正确的一张。", "single_choice", image_items),
                section(f"{p}-doing", "③ 正在做什么？", "看图，选出“正在……”的说法：て形＋います。", "single_choice", doing_items),
            ],
        ),
        "images": images,
        "source": {
            "title": "Action pictures",
            "license": "配图按各图库许可使用",
            "attribution": "插画来自 Icons8，作者、来源和许可随每张配图保留。",
        },
    }


# ── ⓪-2 ない形 ───────────────────────────────────────────────────────
def lesson_nai() -> dict:
    p = "jp-nai"
    images, ids = _action_images()
    forms = [
        ("たべる", "たべない", ["たべらない", "たべわない", "たばない"], "一段：去 る＋ない"),
        ("みる", "みない", ["みらない", "まない", "みわない"], "一段：去 る＋ない"),
        ("よむ", "よまない", ["よみない", "よむない", "よめない"], "む → ま＋ない"),
        ("かく", "かかない", ["かきない", "かけない", "かくない"], "く → か＋ない"),
        ("はなす", "はなさない", ["はなしない", "はなすない", "はなせない"], "す → さ＋ない"),
        ("まつ", "またない", ["まちない", "まつない", "まてない"], "つ → た＋ない"),
        ("あそぶ", "あそばない", ["あそびない", "あそぶない", "あそべない"], "ぶ → ば＋ない"),
        ("かう", "かわない", ["かあない", "かいない", "かえない"], "う 结尾：う → わ＋ない（不是 あ）"),
        ("あう", "あわない", ["ああない", "あいない", "あえない"], "う 结尾：う → わ＋ない"),
        ("いく", "いかない", ["いきない", "いくない", "いけない"], "く → か＋ない"),
        ("かえる（回家）", "かえらない", ["かえない", "かえりない", "かえれない"], "かえる 是五段：る → ら＋ない"),
        ("する", "しない", ["すない", "さない", "できない"], "不规则：する → しない"),
        ("くる", "こない", ["きない", "くない", "こられない"], "不规则：くる → こない"),
        ("ある", "ない", ["あらない", "ありない", "あない"], "特殊：ある 的否定就是 ない"),
    ]
    nai_notes_common = {
        "たべらない": "一段动词直接去 る＋ない", "たべわない": "一段动词直接去 る＋ない", "たばない": "一段动词直接去 る＋ない",
        "みらない": "一段动词直接去 る＋ない", "まない": "一段动词直接去 る＋ない", "みわない": "一段动词直接去 る＋ない",
        "よみない": "五段：う段 → あ段（よま）", "よむない": "五段：う段 → あ段（よま）",
        "かきない": "五段：う段 → あ段（かか）", "かくない": "五段：う段 → あ段（かか）",
        "はなしない": "五段：う段 → あ段（はなさ）", "はなすない": "五段：う段 → あ段（はなさ）",
        "まちない": "五段：う段 → あ段（また）", "まつない": "五段：う段 → あ段（また）",
        "あそびない": "五段：う段 → あ段（あそば）", "あそぶない": "五段：う段 → あ段（あそば）",
        "かあない": "う 结尾要变 わ：かわない", "かいない": "う 结尾要变 わ：かわない",
        "ああない": "う 结尾要变 わ：あわない", "あいない": "う 结尾要变 わ：あわない",
        "いきない": "五段：く → か（いかない）", "いくない": "五段：く → か（いかない）",
        "かえない": "かえる（回家）是五段：かえらない", "かえりない": "かえる（回家）是五段：かえらない",
        "すない": "する → しない", "さない": "する → しない",
        "きない": "くる → こない", "くない": "くる → こない",
        "あらない": "ある 的否定是 ない", "ありない": "ある 的否定是 ない", "あない": "ある 的否定是 ない",
    }
    real = {
        "よめない": ("读不了（可能形的否定）", "cannot read"), "かけない": ("写不了（可能形的否定）", "cannot write"),
        "はなせない": ("说不了（可能形的否定）", "cannot speak"), "まてない": ("等不了（可能形的否定）", "cannot wait"),
        "あそべない": ("玩不了（可能形的否定）", "cannot play"), "かえない": ("买不了（可能形否定）；回家是 かえらない", "cannot buy"),
        "あえない": ("见不了（可能形的否定）", "cannot meet"), "いけない": ("去不了；不可以", "cannot go; must not"),
        "かえれない": ("回不了家（可能形的否定）", "cannot go home"), "できない": ("做不了（可能形的否定）", "cannot do"),
        "こられない": ("来不了（可能形的否定）", "cannot come"),
    }
    form_items = []
    for n, (verb, answer, wrong, note) in enumerate(forms, start=1):
        notes = {answer: (f"{verb} 的ない形：不……", "negative (ない)")}
        for option in wrong:
            notes[option] = real.get(option) or ("✗ 错误形式：" + nai_notes_common[option], "not a real form")
        form_items.append(choice(f"{p}-form-{n:02d}", n, f"{verb} → ない形", answer, wrong, note=note,
                                 option_notes=notes))

    polite = [
        (f"わたしは おさけを {GAP}。（のむ，礼貌体）", "のみません", ["のまない", "のみませんでした"], "我不喝酒。"),
        (f"きのうは テレビを {GAP}。（みる，礼貌体过去）", "みませんでした", ["みません", "みなかった"], "昨天我没看电视。"),
        (f"あした、がっこうへ {GAP}よ。（いく，随意体）", "いかない", ["いきません", "いかなかった"], "明天我不去学校哦。"),
        (f"けさ、あさごはんを {GAP}。（たべる，随意体过去）", "たべなかった", ["たべない", "たべませんでした"], "今天早上我没吃早饭。"),
        (f"しゅうまつは しごとを {GAP}。（する，礼貌体）", "しません", ["しない", "しませんでした"], "周末我不工作。"),
        (f"せんしゅう、ともだちに {GAP}。（あう，随意体过去）", "あわなかった", ["あわない", "あいませんでした"], "上周我没见朋友。"),
    ]
    polite_notes = {
        "のみません": ("不喝（礼貌体现在）", "don't drink (polite)"), "のまない": ("不喝（随意体）", "don't drink (casual)"),
        "のみませんでした": ("没喝（礼貌体过去）", "didn't drink (polite)"),
        "みませんでした": ("没看（礼貌体过去）", "didn't watch (polite)"), "みません": ("不看（礼貌体现在）", "don't watch (polite)"),
        "みなかった": ("没看（随意体过去）", "didn't watch (casual)"),
        "いかない": ("不去（随意体）", "won't go (casual)"), "いきません": ("不去（礼貌体）", "won't go (polite)"),
        "いかなかった": ("没去（随意体过去）", "didn't go (casual)"),
        "たべなかった": ("没吃（随意体过去）", "didn't eat (casual)"), "たべない": ("不吃（随意体现在）", "don't eat (casual)"),
        "たべませんでした": ("没吃（礼貌体过去）", "didn't eat (polite)"),
        "しません": ("不做（礼貌体现在）", "don't do (polite)"), "しない": ("不做（随意体）", "don't do (casual)"),
        "しませんでした": ("没做（礼貌体过去）", "didn't do (polite)"),
        "あわなかった": ("没见（随意体过去）", "didn't meet (casual)"), "あわない": ("不见（随意体现在）", "don't meet (casual)"),
        "あいませんでした": ("没见（礼貌体过去）", "didn't meet (polite)"),
    }
    polite_items = [
        choice(f"{p}-polite-{n:02d}", n, prompt, answer, wrong, zh,
               "礼貌体：ません／ませんでした；随意体：ない／なかった。", option_notes=polite_notes)
        for n, (prompt, answer, wrong, zh) in enumerate(polite, start=1)
    ]

    patterns = [
        (f"ここで しゃしんを とら{GAP}ください。", "ないで", ["なくても", "なければ"], "请不要在这里拍照。", "～ないでください＝请不要……"),
        (f"あしたは やすみだから、はやく おき{GAP}いいです。", "なくても", ["ないで", "なければ"], "明天休息，不早起也可以。", "～なくてもいい＝不……也可以"),
        (f"しけんが あるから、べんきょうし{GAP}なりません。", "なければ", ["ないで", "なくても"], "因为有考试，必须学习。", "～なければならない＝必须……"),
        (f"おなじ まちがいを くりかえさ{GAP}ように します。", "ない", ["ないで", "なければ"], "我会注意不再犯同样的错误。", "～ないように＝为了不……"),
        (f"よる おそく コーヒーを のま{GAP}ください。ねられませんよ。", "ないで", ["なくても", "なければ"], "晚上请不要喝咖啡，会睡不着哦。", ""),
        (f"この しゅくだいは きょう ださ{GAP}いいです。らいしゅうで だいじょうぶです。", "なくても", ["ないで", "なければ"],
         "这个作业今天不交也可以，下周就行。", ""),
    ]
    pattern_notes = {
        "ないで": ("（～ないで）ください＝请不要……", "please don't"),
        "なくても": ("（～なくても）いい＝不……也可以", "don't have to"),
        "なければ": ("（～なければ）ならない＝必须……", "must"),
        "ない": ("ない形本身＝不……", "not"),
    }
    pattern_items = [
        choice(f"{p}-pattern-{n:02d}", n, prompt, answer, wrong, zh, note, option_notes=pattern_notes)
        for n, (prompt, answer, wrong, zh, note) in enumerate(patterns, start=1)
    ]

    picture_items = []
    for n, row in enumerate(ACTION_VERBS[1::3], start=1):
        f = _verb_forms(row)
        wrong = [f["masu"], f["te"], f["ta"]]
        notes = {
            f["nai"]: (f"不{row[2]}（ない形）", "does not"),
            f["masu"]: (f"{row[2]}（ます形）", "does (polite)"),
            f["te"]: (f"{row[2]}（て形）", "て-form"),
            f["ta"]: (f"{row[2]}了（た形）", "did"),
        }
        picture_items.append(picture_choice(f"{p}-pic-{n:02d}", n, "看图：这个动作的ない形是？", ids[row[0]],
                                            f["nai"], wrong, notes))

    return {
        **assignment(
            "nai", "日语 ⓪-2 ない形：不……（ません · ないで · なければ）",
            "練習：ない形",
            [
                section(f"{p}-form", "① 变成ない形", "按动词类别变成ない形。注意 う 结尾要变 わ。", "single_choice", form_items),
                section(f"{p}-polite", "② 礼貌体 / 随意体的否定", "看括号里的要求，选出正确的否定形式。",
                        "single_choice", polite_items),
                section(f"{p}-pattern", "③ ない形＋固定说法", "ないでください／なくてもいい／なければならない／ないように。",
                        "single_choice", pattern_items),
                section(f"{p}-pic", "④ 看图选ない形", "看图想想是什么动作，再选出它的ない形。", "single_choice", picture_items),
            ],
            tables=[
                table(f"{p}-rule", "ない形", "ない形：五段把最后的 う段音 → あ段＋ない", [
                    ("一段：去 る＋ない", "たべる→たべない · みる→みない"),
                    ("五段：う段 → あ段＋ない", "よむ→よまない · かく→かかない · はなす→はなさない"),
                    ("五段 う 结尾：う → わ（坑）", "かう→かわない · あう→あわない"),
                    ("不规则", "する→しない · くる→こない"),
                    ("特殊", "ある→ない"),
                ]),
                table(f"{p}-row", "あいう", "同一行对照：ない形（あ段）· ます形（い段）· 辞书形（う段）", [
                    ("かく", "かかない · かきます · かく"),
                    ("よむ", "よまない · よみます · よむ"),
                    ("まつ", "またない · まちます · まつ"),
                    ("かう", "かわない · かいます · かう"),
                ]),
            ],
            heading="先看规则表：ない形怎么变",
            intro="和ます形同一个思路：五段动词换最后一个音。ます形换成い段，ない形换成あ段；う 结尾的要换成 わ。",
        ),
        "images": images,
        "source": {
            "title": "Action pictures",
            "license": "配图按各图库许可使用",
            "attribution": "插画来自 Icons8，作者、来源和许可随每张配图保留。",
        },
    }


# ── ⓪-3 ます形 ──────────────────────────────────────────────────────
def lesson_masu() -> dict:
    p = "jp-masu"
    _, ids = _action_images()
    X = "✗ 错误形式："
    forms = [
        ("かく", "かきます", ["かくます", "かかます", "かいます"], "く → き＋ます"),
        ("よむ", "よみます", ["よむます", "よまます", "よんます"], "む → み＋ます"),
        ("はなす", "はなします", ["はなすます", "はなさます", "はなせます"], "す → し＋ます"),
        ("まつ", "まちます", ["まつます", "またます", "まってます"], "つ → ち＋ます"),
        ("あそぶ", "あそびます", ["あそぶます", "あそばます", "あそんます"], "ぶ → び＋ます"),
        ("およぐ", "およぎます", ["およぐます", "およがます", "およいます"], "ぐ → ぎ＋ます"),
        ("かう", "かいます", ["かうます", "かわます", "かっます"], "う → い＋ます"),
        ("つくる", "つくります", ["つくます", "つくるます", "つくらます"], "五段 る → り＋ます"),
        ("たべる", "たべます", ["たべります", "たべるます", "たびます"], "一段：去 る＋ます"),
        ("みる", "みます", ["みります", "みるます", "まます"], "一段：去 る＋ます"),
        ("おきる", "おきます", ["おきります", "おきるます", "おかます"], "一段：去 る＋ます"),
        ("かえる（回家）", "かえります", ["かえます", "かえるます", "かえらます"], "かえる 是五段：る → り＋ます"),
        ("はしる", "はしります", ["はします", "はしるます", "はしらます"], "はしる 是五段：る → り＋ます"),
        ("する", "します", ["すます", "さます", "しります"], "不规则：する → します"),
        ("くる", "きます", ["くます", "こます", "きります"], "不规则：くる → きます"),
        ("べんきょうする", "べんきょうします", ["べんきょうすます", "べんきょうさます", "べんきょうできます"],
         "名词＋する：只变 する → します"),
    ]
    real = {
        "かいます": ("かう（买）的ます形，不是 かく", "masu of かう"),
        "はなせます": ("会说（可能形）", "can speak"),
        "かえます": ("かえる（换，一段）的ます形；回家是 かえります", "masu of 変える (change)"),
        "はします": (X + "はしる 是五段，不能去 る：はしります", "not a real form"),
        "べんきょうできます": ("能学习（可能形）", "can study"),
        "まってます": ("（口语）在等＝まっています", "is waiting (casual speech)"),
    }

    reasons = {
        "かくます": "辞书形不能直接加 ます，く 要变 き", "かかます": "か 是 あ段（ない形用），ます形要 い段：かき",
        "よむます": "辞书形不能直接加 ます，む 要变 み", "よまます": "ま 是 あ段，ます形要 い段：よみ",
        "よんます": "よん 是て形的音便，ます形是 よみます",
        "はなすます": "辞书形不能直接加 ます，す 要变 し", "はなさます": "さ 是 あ段，ます形要 い段：はなし",
        "まつます": "辞书形不能直接加 ます，つ 要变 ち", "またます": "た 是 あ段，ます形要 い段：まち",
        "あそぶます": "辞书形不能直接加 ます，ぶ 要变 び", "あそばます": "ば 是 あ段，ます形要 い段：あそび",
        "あそんます": "あそん 是て形的音便，ます形是 あそびます",
        "およぐます": "辞书形不能直接加 ます，ぐ 要变 ぎ", "およがます": "が 是 あ段，ます形要 い段：およぎ",
        "およいます": "およい 是て形的音便，ます形是 およぎます",
        "かうます": "辞书形不能直接加 ます，う 要变 い", "かわます": "わ 是ない形用的（かわない），ます形是 かいます",
        "かっます": "かっ 是て形的音便，ます形是 かいます",
        "つくます": "つくる 是五段，不能像一段那样去 る：つくります", "つくるます": "辞书形不能直接加 ます",
        "つくらます": "ら 是 あ段，ます形要 い段：つくり",
        "たべります": "一段动词去 る＋ます，不加 り", "たべるます": "辞书形不能直接加 ます，要去 る",
        "たびます": "一段动词不变词干，直接 たべ＋ます",
        "みります": "一段动词去 る＋ます，不加 り", "みるます": "辞书形不能直接加 ます，要去 る",
        "まます": "一段动词不变词干，直接 み＋ます",
        "おきります": "一段动词去 る＋ます，不加 り", "おきるます": "辞书形不能直接加 ます，要去 る",
        "おかます": "一段动词不变词干，直接 おき＋ます",
        "かえるます": "辞书形不能直接加 ます", "かえらます": "ら 是 あ段，ます形要 い段：かえり",
        "はしるます": "辞书形不能直接加 ます", "はしらます": "ら 是 あ段，ます形要 い段：はしり",
        "すます": "する 不规则：します（すます 是另一个词“办完”）", "さます": "する 不规则：します",
        "しります": "する 不规则：します",
        "くます": "くる 不规则：きます", "こます": "こ 是ない形用的（こない），ます形是 きます",
        "きります": "くる 不规则：きます（きります 是“剪”）",
        "べんきょうすます": "名词＋する 只变 する → します", "べんきょうさます": "名词＋する 只变 する → します",
    }

    form_items = []
    for n, (verb, answer, wrong, note) in enumerate(forms, start=1):
        notes = {answer: (f"{verb} 的ます形（礼貌体）", "masu form")}
        for option in wrong:
            notes[option] = real.get(option) or (X + reasons[option], "not a real form")
        form_items.append(choice(f"{p}-form-{n:02d}", n, f"{verb} → ます形", answer, wrong, note=note,
                                 option_notes=notes))

    tense = [
        (f"まいあさ コーヒーを {GAP}。（のむ）", "のみます", "习惯：每天早上喝咖啡。"),
        (f"きのう えいがを {GAP}。（みる）", "みました", "过去：昨天看了电影。"),
        (f"わたしは おさけを {GAP}。（のむ，否定）", "のみません", "否定：我不喝酒。"),
        (f"せんしゅうは しごとを {GAP}。（する，过去否定）", "しませんでした", "过去否定：上周没工作。"),
        (f"あした ともだちに {GAP}。（あう）", "あいます", "将来：明天见朋友。"),
        (f"きのうは どこにも {GAP}。（いく，过去否定）", "いきませんでした", "过去否定：昨天哪儿也没去。"),
    ]
    tense_sets = {
        "のみます": ["のみました", "のみません", "のみませんでした"],
        "みました": ["みます", "みません", "みませんでした"],
        "のみません": ["のみます", "のみました", "のみませんでした"],
        "しませんでした": ["します", "しました", "しません"],
        "あいます": ["あいました", "あいません", "あいませんでした"],
        "いきませんでした": ["いきます", "いきました", "いきません"],
    }
    label = {"ます": "肯定 · 现在 / 将来", "ました": "肯定 · 过去", "ません": "否定 · 现在 / 将来", "ませんでした": "否定 · 过去"}

    def tense_note(option: str) -> tuple[str, str]:
        for ending in ("ませんでした", "ました", "ません", "ます"):
            if option.endswith(ending):
                return (f"{option[:-len(ending)]}＋{ending}：{label[ending]}", ending)
        raise ValueError(option)

    tense_items = []
    for n, (prompt, answer, zh) in enumerate(tense, start=1):
        wrong = tense_sets[answer]
        tense_items.append(choice(f"{p}-tense-{n:02d}", n, prompt, answer, wrong, zh,
                                  "ます／ました／ません／ませんでした：看时间和肯定否定。",
                                  option_notes={o: tense_note(o) for o in [answer, *wrong]}))

    roads = [
        ("かう", "礼貌体过去", "かいました", ["かった", "かって", "かいます"]),
        ("かう", "随意体过去", "かった", ["かいました", "かって", "かわない"]),
        ("よむ", "礼貌体过去", "よみました", ["よんだ", "よんで", "よみます"]),
        ("よむ", "随意体过去", "よんだ", ["よみました", "よんで", "よまない"]),
        ("りょうりする", "礼貌体过去", "りょうりしました", ["りょうりした", "りょうりして", "りょうりします"]),
        ("いく", "随意体过去", "いった", ["いきました", "いって", "いかない"]),
    ]
    road_names = {"ました": ("礼貌体过去：ます形 → ました", "polite past"), "ます": ("礼貌体现在 / 将来：ます形", "polite"),
                  "て": ("て形（连接用）", "て-form"), "で": ("て形（连接用）", "て-form"),
                  "た": ("随意体过去：て形 → た", "casual past"), "だ": ("随意体过去：て形 → だ", "casual past"),
                  "ない": ("ない形：否定", "negative")}

    def road_note(option: str) -> tuple[str, str]:
        for ending in ("ました", "ます", "ない", "て", "で", "た", "だ"):
            if option.endswith(ending):
                return road_names[ending]
        raise ValueError(option)

    road_items = [
        choice(f"{p}-road-{n:02d}", n, f"{verb} 的{kind}是？", answer, wrong,
               note="礼貌体过去走ます形（ます→ました）；随意体过去走て形（て→た）。",
               option_notes={o: road_note(o) for o in [answer, *wrong]})
        for n, (verb, kind, answer, wrong) in enumerate(roads, start=1)
    ]

    stems = [
        (f"にほんへ いき{GAP}です。（いく＋たい）", "たい", "いきたいです＝想去", ["る", "ます"]),
        (f"この ペンは かき{GAP}です。（かく＋やすい）", "やすい", "かきやすいです＝好写", ["たい", "ない"]),
        (f"きのう たべ{GAP}ました。（たべる＋すぎる）", "すぎ", "たべすぎました＝吃太多了", ["ない", "て"]),
        (f"あめが ふり{GAP}です。（ふる＋そう）", "そう", "ふりそうです＝看起来要下雨", ["ない", "たい"]),
        (f"まいにち べんきょうし{GAP}います。（する＋つづける）", "つづけて", "べんきょうしつづけています＝一直在学", ["ない", "すぎ"]),
    ]
    stem_names = {"たい": ("ます形去ます＋たい＝想……", "want to"), "やすい": ("ます形去ます＋やすい＝容易……", "easy to"),
                  "すぎ": ("ます形去ます＋すぎる＝太……", "too much"), "そう": ("ます形去ます＋そう＝看起来要……", "looks like"),
                  "つづけて": ("ます形去ます＋つづける＝一直……", "keep doing"),
                  "る": ("✗ 这里要接在ます形词干后面", "not here"), "ます": ("✗ 这里不是礼貌体结尾", "not here"),
                  "ない": ("✗ 放 ない 在这里不成句", "not here"), "て": ("✗ て 不接在ます形词干后", "not here")}
    stem_items = [
        choice(f"{p}-stem-{n:02d}", n, prompt, answer, wrong, zh, "很多语法＝ます形去掉 ます，再接尾巴。",
               option_notes={o: stem_names[o] for o in [answer, *wrong]})
        for n, (prompt, answer, zh, wrong) in enumerate(stems, start=1)
    ]

    picture_items = []
    for n, row in enumerate(ACTION_VERBS[2::3], start=1):
        f = _verb_forms(row)
        wrong = [f["dict"], f["nai"], f["te"]]
        notes = {f["masu"]: (f"{row[2]}（ます形：礼貌体）", "masu form"), f["dict"]: (f"{row[2]}（辞书形）", "dictionary form"),
                 f["nai"]: (f"不{row[2]}（ない形）", "negative"), f["te"]: (f"{row[2]}（て形）", "て-form")}
        picture_items.append(picture_choice(f"{p}-pic-{n:02d}", n, "看图：这个动作的ます形是？", ids[row[0]],
                                            f["masu"], wrong, notes))

    images, _ = _action_images()
    used = {item["imageId"] for item in picture_items}
    return {
        **assignment(
            "masu", "日语 ⓪-3 ます形：礼貌体（ます · ました · ません）",
            "練習：ます形",
            [
                section(f"{p}-form", "① 变成ます形", "五段换成 い段＋ます；一段去 る＋ます；する→します，くる→きます。",
                        "single_choice", form_items),
                section(f"{p}-tense", "② ます／ました／ません／ませんでした", "看括号和时间，选出正确的礼貌体。",
                        "single_choice", tense_items),
                section(f"{p}-road", "③ 过去式的两条路", "礼貌体过去走ます形；随意体过去走て形。", "single_choice", road_items),
                section(f"{p}-stem", "④ ます形去掉 ます，再接语法", "たい・やすい・すぎる・そう・つづける 都接在这里。",
                        "single_choice", stem_items),
                section(f"{p}-pic", "⑤ 看图选ます形", "看图想想是什么动作，再选出它的ます形。", "single_choice", picture_items),
            ],
            tables=[
                table(f"{p}-rule", "ます形", "ます形：五段把最后的 う段音 → い段＋ます", [
                    ("一段：去 る＋ます", "たべる→たべます · みる→みます"),
                    ("五段：う段 → い段＋ます", "かく→かきます · よむ→よみます · まつ→まちます"),
                    ("五段 う 结尾", "かう→かいます · あう→あいます"),
                    ("像一段的五段（例外）", "かえる→かえります · はしる→はしります"),
                    ("不规则", "する→します · くる→きます"),
                    ("名词＋する", "りょうりする→りょうりします"),
                ]),
                table(f"{p}-tense", "ます", "礼貌体四个形式", [
                    ("肯定 · 现在 / 将来", "たべます"), ("肯定 · 过去", "たべました"),
                    ("否定 · 现在 / 将来", "たべません"), ("否定 · 过去", "たべませんでした"),
                ]),
            ],
            heading="先看规则表：ます形怎么变",
            intro="ます形是礼貌体的基础。五段动词换到 い段，和ない形（あ段）是同一个思路。",
        ),
        "images": {image_id: images[image_id] for image_id in sorted(used)},
        "source": {
            "title": "Action pictures",
            "license": "配图按各图库许可使用",
            "attribution": "插画来自 Icons8，作者、来源和许可随每张配图保留。",
        },
    }


def build_assignments() -> list[dict]:
    built = [lesson_te(), lesson_nai(), lesson_masu(), lesson_pictures(), lesson_past(), lesson_potential(), lesson_plans(), lesson_keep(),
             lesson_looks(), lesson_easy(), lesson_warini()]
    for item in built:
        notes = LESSON_NOTES.get(item["id"][len(PREFIX):])
        if notes:
            item["lessonNotes"] = notes
            item["lessonNotesHeading"] = "先读笔记：" + item["title"].split(" ", 2)[-1]
    return built


def upsert(homework_path: Path, new_assignments: list[dict]) -> None:
    data = json.loads(homework_path.read_text(encoding="utf-8"))
    # Generated assignments follow the builder's lesson order; progress is
    # stored per assignment id, so reordering never touches saved answers.
    generated = {assignment["id"] for assignment in new_assignments}
    others = [a for a in data.get("assignments", []) if a.get("id") not in generated]
    data["assignments"] = others + list(new_assignments)
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
