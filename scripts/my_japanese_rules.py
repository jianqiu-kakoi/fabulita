"""Explain a Japanese verb form step by step, for answer feedback.

rule("かう", "te") ->
    ① 判断类别：う 结尾（不是 る）→ 五段动词
    ② 规则：五段 う・つ・る 结尾 → 促音便，变 って
    ③ 得到：かう → かって
Covers て／た／ていた／ていました／ています／ます／ました／ません／ませんでした／
たい／ない／可能／ば／意向 for 一段, 五段 (with look-alike exceptions),
する／くる and 名词＋する. Lines are joined with "\n".
"""

from __future__ import annotations

TO_A = dict(zip("うくぐすつぬぶむる", "わかがさたなばまら"))
TO_I = dict(zip("うくぐすつぬぶむる", "いきぎしちにびみり"))
TO_E = dict(zip("うくぐすつぬぶむる", "えけげせてねべめれ"))
TO_O = dict(zip("うくぐすつぬぶむる", "おこごそとのぼもろ"))
VOWEL = {}
for _vowel, _row in {
    "a": "あかがさざただなはばぱまやらわ", "i": "いきぎしじちぢにひびぴみり",
    "u": "うくぐすずつづぬふぶぷむゆる", "e": "えけげせぜてでねへべぺめれ", "o": "おこごそぞとどのほぼぽもよろを",
}.items():
    for _kana in _row:
        VOWEL[_kana] = _vowel
# Look like 一段 (i/e sound before る) but are 五段.
GODAN_EXCEPTIONS = {"かえる（回家）", "はいる", "はしる", "しる", "きる（剪）", "いる（需要）"}


def _clean(verb: str) -> str:
    return verb.split("（")[0]


def group(verb: str) -> str:
    plain = _clean(verb)
    if plain in ("する", "くる") or plain.endswith("する"):
        return "irregular"
    if verb in GODAN_EXCEPTIONS:
        return "godan-exception"
    if plain.endswith("る") and len(plain) >= 2 and VOWEL.get(plain[-2]) in ("i", "e"):
        return "ichidan"
    return "godan"


def classify(verb: str) -> str:
    """Step ①: why the verb is in its group."""
    plain = _clean(verb)
    kind = group(verb)
    if kind == "irregular":
        if plain in ("する", "くる"):
            return f"① 判断类别：{plain} 是不规则动词（只有 する 和 くる）"
        return f"① 判断类别：{plain[:-2]}＋する → 按 する 变（不规则动词）"
    end = plain[-1]
    if end != "る":
        return f"① 判断类别：{end} 结尾（不是 る）→ 五段动词"
    before = plain[-2]
    row = VOWEL.get(before, "?")
    if kind == "ichidan":
        return f"① 判断类别：る 前面的 {before} 是 {row} 段 → 一段动词"
    if kind == "godan-exception":
        return f"① 判断类别：る 前面的 {before} 是 {row} 段，看起来像一段，但 {verb} 是例外 → 五段动词"
    return f"① 判断类别：る 前面的 {before} 是 {row} 段（a・u・o 段）→ 五段动词"


def _te_step(verb: str, past: bool) -> tuple[str, str]:
    """Step ② and the produced word for て形 / た形."""
    plain = _clean(verb)
    t, d = ("た", "だ") if past else ("て", "で")
    kind = group(verb)
    if kind == "irregular":
        if plain == "くる":
            return f"② 规则：不规则，くる → き＋{t}", "き" + t
        return f"② 规则：不规则，する → し＋{t}", plain[:-2] + "し" + t
    if kind == "ichidan":
        return f"② 规则：一段动词去掉 る＋{t}", plain[:-1] + t
    stem, end = plain[:-1], plain[-1]
    if plain == "いく":
        return f"② 规则：く 结尾本该 イ音便（いい{t}），但 いく 是例外 → 促音便 っ{t}", "いっ" + t
    if end in "うつる":
        return f"② 规则：五段 う・つ・る 结尾 → 促音便，变 っ{t}", stem + "っ" + t
    if end in "むぶぬ":
        return f"② 规则：五段 む・ぶ・ぬ 结尾 → 撥音便，变 ん{d}", stem + "ん" + d
    if end == "く":
        return f"② 规则：五段 く 结尾 → イ音便，变 い{t}", stem + "い" + t
    if end == "ぐ":
        return f"② 规则：五段 ぐ 结尾 → イ音便，变 い{d}", stem + "い" + d
    return f"② 规则：五段 す 结尾 → し{t}（不发生音便）", stem + "し" + t


def _shift_step(verb: str, form: str) -> tuple[str, str]:
    """Step ② and the produced word for ます／ない／可能／ば／意向."""
    plain = _clean(verb)
    kind = group(verb)
    if kind == "irregular":
        noun = plain[:-2] if plain not in ("する", "くる") else ""
        core = "くる" if plain == "くる" else "する"
        result = {"くる": {"masu": "きます", "nai": "こない", "pot": "こられる", "ba": "くれば", "vol": "こよう"},
                  "する": {"masu": "します", "nai": "しない", "pot": "できる", "ba": "すれば", "vol": "しよう"}}[core][form]
        return f"② 规则：不规则，{core} → {result}（要记住）", noun + result
    if plain == "ある" and form == "nai":
        return "② 规则：特殊，ある 的否定就是 ない（不是 あらない）", "ない"
    stem, end = plain[:-1], plain[-1]
    if kind == "ichidan":
        tail = {"masu": "ます", "nai": "ない", "pot": "られる", "ba": "れば", "vol": "よう"}[form]
        extra = "（口语常说 ～れる）" if form == "pot" else ""
        return f"② 规则：一段动词去掉 る＋{tail}{extra}", stem + tail
    if form == "masu":
        return f"② 规则：五段把最后的 {end}（う段）换成 {TO_I[end]}（い段）＋ます", stem + TO_I[end] + "ます"
    if form == "nai":
        if end == "う":
            return "② 规则：五段 う 结尾特殊，换成 わ（不是 あ）＋ない", stem + "わない"
        return f"② 规则：五段把最后的 {end}（う段）换成 {TO_A[end]}（あ段）＋ない", stem + TO_A[end] + "ない"
    if form == "pot":
        return f"② 规则：五段把最后的 {end}（う段）换成 {TO_E[end]}（え段）＋る", stem + TO_E[end] + "る"
    if form == "ba":
        return f"② 规则：五段把最后的 {end}（う段）换成 {TO_E[end]}（え段）＋ば", stem + TO_E[end] + "ば"
    return f"② 规则：五段把最后的 {end}（う段）换成 {TO_O[end]}（お段）＋う", stem + TO_O[end] + "う"


def rule(verb: str, form: str) -> str:
    """form: te, ta, teita, teimashita, teimasu, masu, mashita, masen, masendeshita, tai, nai, pot, ba, vol, dict."""
    plain = _clean(verb)
    if form == "dict":
        return "辞书形＝原形，字典里的样子"
    lines = [classify(verb)]
    if form in ("te", "ta", "teita", "teimashita", "teimasu"):
        step, word = _te_step(verb, form == "ta")
        lines.append(step)
        if form in ("teita", "teimashita", "teimasu"):
            tail, label = {"teita": ("いた", "随意体"), "teimashita": ("いました", "礼貌体"),
                           "teimasu": ("います", "正在 / 一直在")}[form]
            lines.append(f"③ 再加 {tail}（{label}）")
            lines.append(f"④ 得到：{plain} → {word} → {word}{tail}")
        else:
            lines.append(f"③ 得到：{plain} → {word}")
        return "\n".join(lines)
    if form in ("mashita", "masen", "masendeshita", "tai"):
        step, word = _shift_step(verb, "masu")
        tail = {"mashita": "ました", "masen": "ません", "masendeshita": "ませんでした", "tai": "たいです"}[form]
        lines.append(step)
        lines.append("③ 去掉 ます＋たいです" if form == "tai" else f"③ ます → {tail}")
        lines.append(f"④ 得到：{plain} → {word} → {word[:-2]}{tail}")
        return "\n".join(lines)
    step, word = _shift_step(verb, form)
    lines.append(step)
    lines.append(f"③ 得到：{plain} → {word}")
    return "\n".join(lines)
