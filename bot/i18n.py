"""Localization for the Telegram frontend (RU/EN).

All user-facing strings live here so the rest of the bot stays free of literals.
This is a frontend concern: the pure ``engine`` returns data (enums, dataclasses)
and never deals with languages. Use :func:`t` to render a key for a language.

Command keyword aliases (stat/track/odds names, the ``burn`` flag) are also kept
here so players can type either English or Russian words.
"""

from __future__ import annotations

DEFAULT_LANG = "en"
LANGS = ("ru", "en")

# --- command keyword aliases (typed by players) -> canonical engine names -----

STAT_ALIASES = {
    "edge": "edge", "напор": "edge",
    "heart": "heart", "сердце": "heart",
    "iron": "iron", "сталь": "iron", "железо": "iron",
    "shadow": "shadow", "тень": "shadow",
    "wits": "wits", "смекалка": "wits", "ум": "wits",
}

TRACK_ALIASES = {
    "health": "health", "здоровье": "health", "хп": "health",
    "spirit": "spirit", "дух": "spirit",
    "supply": "supply", "припасы": "supply",
    "momentum": "momentum", "импульс": "momentum",
}

ODDS_ALIASES = {
    "almost_certain": "almost_certain", "почти": "almost_certain",
    "likely": "likely", "вероятно": "likely",
    "fifty_fifty": "fifty_fifty", "поровну": "fifty_fifty", "5050": "fifty_fifty",
    "unlikely": "unlikely", "навряд": "unlikely",
    "small_chance": "small_chance", "маловероятно": "small_chance",
}

BURN_WORDS = {"burn", "сжечь", "импульс"}


def resolve_lang(stored: str | None, tg_code: str | None) -> str:
    """Pick the language: stored choice, else Telegram client code, else EN."""
    if stored in LANGS:
        return stored  # type: ignore[return-value]
    if tg_code and tg_code.lower().startswith("ru"):
        return "ru"
    return DEFAULT_LANG


def t(lang: str, key: str, /, **kwargs: object) -> str:
    """Render a localized string, falling back to English then the key itself."""
    table = TEXTS.get(lang, TEXTS[DEFAULT_LANG])
    template = table.get(key) or TEXTS[DEFAULT_LANG].get(key) or key
    return template.format(**kwargs) if kwargs else template


TEXTS: dict[str, dict[str, str]] = {
    "en": {
        # stat / track / odds display labels
        "stat_edge": "Edge", "stat_heart": "Heart", "stat_iron": "Iron",
        "stat_shadow": "Shadow", "stat_wits": "Wits",
        "track_health": "Health", "track_spirit": "Spirit",
        "track_supply": "Supply", "momentum": "Momentum", "reset": "reset",
        "odds_almost_certain": "Almost certain", "odds_likely": "Likely",
        "odds_fifty_fifty": "Fifty-fifty", "odds_unlikely": "Unlikely",
        "odds_small_chance": "Small chance",
        # start / help / guide
        "start": (
            "👋 Welcome! This is a bot for *Ironsworn* — a tabletop role-playing "
            "game with *no game master*. You tell the story; the bot rolls the "
            "dice, answers yes/no questions as an Oracle, and tracks your hero.\n\n"
            "New here? Tap /tutorial for a 1-minute walkthrough, or /guide for a "
            "quick reference. Then create a hero with /new.\n\n"
            "Language: /language"
        ),
        "help": (
            "🎲 *Commands*\n"
            "/new — create your hero (step by step)\n"
            "/me — show your hero sheet\n"
            "/roll <stat> [adds] [burn] — action roll\n"
            "/ask <odds> <question> — ask the Oracle (yes/no)\n"
            "/oracle [table] — draw a spark of inspiration\n"
            "/set <track> <value> — change health/spirit/supply/momentum\n"
            "/tutorial — interactive walkthrough\n"
            "/guide — how to play\n"
            "/language — switch RU/EN\n\n"
            "stats: edge, heart, iron, shadow, wits\n"
            "odds: almost_certain, likely, fifty_fifty, unlikely, small_chance\n"
            "examples: /roll iron · /roll iron burn · /ask likely Are we noticed?"
        ),
        "guide": (
            "📖 *How to play (the short version)*\n\n"
            "Ironsworn is a story you tell yourself or with friends — no game "
            "master. You describe what your hero does; the dice and the Oracle "
            "decide how it goes.\n\n"
            "*The loop:*\n"
            "1) Want to do something risky? `/roll <stat>` — a *strong hit* means "
            "it goes well, a *weak hit* means yes-but, a *miss* means trouble.\n"
            "2) Not sure what the world does? Ask the Oracle: `/ask likely Is the "
            "gate guarded?` — it answers yes/no.\n"
            "3) Stuck for ideas? `/oracle` gives you a spark (a place, an NPC…).\n"
            "4) Track your hero with `/me`; adjust with `/set`.\n\n"
            "That's it. Start with /new and just play. Try /tutorial to see it in "
            "action."
        ),
        # generic
        "no_character": "You don't have a hero yet. Create one with /new.",
        # roll
        "roll_usage": (
            "Usage: /roll <stat> [adds] [burn]\n"
            "stat: edge, heart, iron, shadow, wits\n"
            "adds — optional bonus; burn — spend momentum\n"
            "examples: /roll iron · /roll heart 1 · /roll iron burn"
        ),
        "roll_header": "🎲 Action roll — {stat}",
        "roll_natural": "Action die {die} + stat {stat}",
        "roll_adds": " + adds {adds}",
        "roll_score": " = score {score}",
        "roll_capped": " (capped at 10)",
        "roll_natural_only": " = {total}",
        "roll_burn": "🔥 Burned momentum → score {score} (momentum reset to {reset:+d})",
        "roll_challenge": "Challenge dice: {a} | {b}",
        "roll_result": "Result: {label}",
        "outcome_strong": "💪 Strong hit", "outcome_weak": "👍 Weak hit",
        "outcome_miss": "💥 Miss",
        "match_note": "⚡ Match! A dramatic twist — a boost on a hit, a complication on a miss.",
        # ask / oracle
        "ask_usage": (
            "Usage: /ask <odds> <question>\n"
            "odds: almost_certain, likely, fifty_fifty, unlikely, small_chance\n"
            "example: /ask likely Are we noticed?"
        ),
        "ask_header": "🔮 Oracle",
        "ask_question": "Q: {question}",
        "ask_odds": "Odds: {label} ({chance}% yes) — rolled {roll}",
        "ask_answer": "Answer: {label}",
        "answer_yes": "✅ Yes", "answer_no": "❌ No",
        "extreme_note": "⚡ Extreme result — an unexpected, dramatic twist!",
        "oracle_none": "No oracle tables are available.",
        "oracle_unknown_table": "Unknown table '{table}'. Available: {available}",
        "oracle_line": "🔮 {title}: {entry}",
        # set
        "set_usage": (
            "Usage: /set <track> <value>\n"
            "track: health, spirit, supply, momentum\n"
            "example: /set supply 3"
        ),
        "set_unknown": "Unknown track '{field}'. Choose: health, spirit, supply, momentum.",
        "set_out_of_bounds": "{field} must be between {low} and {high}.",
        "set_done": "{field} set to {value}.",
        # sheet
        "sheet": (
            "📜 {name}\n"
            "{edge_l} {edge}  {heart_l} {heart}  {iron_l} {iron}  "
            "{shadow_l} {shadow}  {wits_l} {wits}\n"
            "{health_l} {health}/5   {spirit_l} {spirit}/5   {supply_l} {supply}/5\n"
            "{momentum_l} {momentum:+d} ({reset_l} {reset:+d})"
        ),
        # /new conversation
        "new_intro": "Let's forge a hero! What is their name? (/cancel to abort)",
        "new_empty_name": "Please enter a non-empty name.",
        "new_ask_stat": "Set {stat} ({lo}-{hi}):",
        "new_bad_stat": "Please enter a whole number from {lo} to {hi} for {stat}.",
        "new_already_exists": "You already have a hero. Use /me to view it or /set to change it.",
        "new_created": "Hero created!",
        "new_cancelled": "Hero creation cancelled.",
        "new_failed": "Could not create hero: {error}",
        # language
        "language_current": "Current language: {lang}. Choose:",
        "language_set": "Language set to {lang}.",
        # buttons
        "btn_next": "Next ▶", "btn_back": "◀ Back", "btn_play": "Let's play! ▶",
        "btn_ru": "Русский", "btn_en": "English",
        # tutorial pages
        "tut_1": (
            "📘 *Tutorial (1/4)* — What is this?\n\n"
            "Ironsworn is a role-playing game with *no game master*. You imagine "
            "the story; the bot is your dice, your Oracle, and your character "
            "sheet. Play solo or with friends in a group chat.\n\n"
            "Tap Next to learn the three things you'll actually do."
        ),
        "tut_2": (
            "📘 *Tutorial (2/4)* — Your hero\n\n"
            "First you make a hero with /new: a name, five *stats* (Edge, Heart, "
            "Iron, Shadow, Wits, each 1–3) and three *tracks* (Health, Spirit, "
            "Supply). *Momentum* is your narrative drive.\n\n"
            "You'll roll those stats to act. See your sheet anytime with /me."
        ),
        "tut_3": (
            "📘 *Tutorial (3/4)* — Acting & asking\n\n"
            "• Do something risky → `/roll iron` (or another stat). Strong hit = "
            "great; weak hit = yes, but…; miss = trouble.\n"
            "• Ask the world a yes/no question → `/ask likely Is the door locked?`\n"
            "• Need a spark of an idea → `/oracle` gives a place or an NPC.\n\n"
            "Out of a tight spot, spend drive: `/roll iron burn`."
        ),
        "tut_4": (
            "📘 *Tutorial (4/4)* — Go play!\n\n"
            "That's the whole loop: imagine → roll or ask → narrate the result.\n\n"
            "Create your hero now with /new, then try `/ask likely …` and "
            "`/roll <stat>`. Have fun, Ironsworn!"
        ),
    },
    "ru": {
        # stat / track / odds display labels
        "stat_edge": "Напор", "stat_heart": "Сердце", "stat_iron": "Сталь",
        "stat_shadow": "Тень", "stat_wits": "Смекалка",
        "track_health": "Здоровье", "track_spirit": "Дух",
        "track_supply": "Припасы", "momentum": "Импульс", "reset": "сброс",
        "odds_almost_certain": "Почти наверняка", "odds_likely": "Скорее да",
        "odds_fifty_fifty": "50 на 50", "odds_unlikely": "Скорее нет",
        "odds_small_chance": "Вряд ли",
        # start / help / guide
        "start": (
            "👋 Привет! Это бот для *Ironsworn* — настольной ролевой игры *без "
            "ведущего*. Историю придумываешь ты, а бот кидает кубики, отвечает на "
            "вопросы да/нет как Оракул и ведёт лист героя.\n\n"
            "Первый раз? Нажми /tutorial — разбор за минуту, или /guide — короткая "
            "шпаргалка. Потом создай героя командой /new.\n\n"
            "Язык: /language"
        ),
        "help": (
            "🎲 *Команды*\n"
            "/new — создать героя (по шагам)\n"
            "/me — лист героя\n"
            "/roll <хар-ка> [бонус] [сжечь] — бросок действия\n"
            "/ask <шанс> <вопрос> — спросить Оракула (да/нет)\n"
            "/oracle [таблица] — подсказка-вдохновение\n"
            "/set <трек> <значение> — изменить здоровье/дух/припасы/импульс\n"
            "/tutorial — интерактивный разбор\n"
            "/guide — как играть\n"
            "/language — переключить RU/EN\n\n"
            "характеристики: напор, сердце, сталь, тень, смекалка\n"
            "шансы: почти, вероятно, поровну, навряд, маловероятно\n"
            "примеры: /roll сталь · /roll сталь сжечь · /ask вероятно Нас заметили?"
        ),
        "guide": (
            "📖 *Как играть (кратко)*\n\n"
            "Ironsworn — это история, которую ты ведёшь сам или с друзьями, без "
            "ведущего. Ты описываешь, что делает герой; кубики и Оракул решают, "
            "как всё обернётся.\n\n"
            "*Цикл игры:*\n"
            "1) Делаешь что-то рискованное? `/roll <хар-ка>` — *сильный успех* = "
            "вышло хорошо, *слабый успех* = да, но…, *провал* = неприятности.\n"
            "2) Не знаешь, как поступит мир? Спроси Оракула: `/ask вероятно Ворота "
            "охраняют?` — ответит да/нет.\n"
            "3) Нет идей? `/oracle` подкинет искру (место, персонажа…).\n"
            "4) Следи за героем через `/me`, меняй через `/set`.\n\n"
            "Вот и всё. Начни с /new и просто играй. Глянь /tutorial — там по шагам."
        ),
        # generic
        "no_character": "У тебя ещё нет героя. Создай командой /new.",
        # roll
        "roll_usage": (
            "Использование: /roll <хар-ка> [бонус] [сжечь]\n"
            "характеристики: напор, сердце, сталь, тень, смекалка\n"
            "бонус — необязательная добавка; сжечь — потратить импульс\n"
            "примеры: /roll сталь · /roll сердце 1 · /roll сталь сжечь"
        ),
        "roll_header": "🎲 Бросок действия — {stat}",
        "roll_natural": "Кубик действия {die} + хар-ка {stat}",
        "roll_adds": " + бонус {adds}",
        "roll_score": " = очки {score}",
        "roll_capped": " (макс. 10)",
        "roll_natural_only": " = {total}",
        "roll_burn": "🔥 Импульс сожжён → очки {score} (импульс сброшен до {reset:+d})",
        "roll_challenge": "Кубики испытания: {a} | {b}",
        "roll_result": "Итог: {label}",
        "outcome_strong": "💪 Сильный успех", "outcome_weak": "👍 Слабый успех",
        "outcome_miss": "💥 Провал",
        "match_note": "⚡ Дубль! Драматический поворот — усиление при успехе, осложнение при провале.",
        # ask / oracle
        "ask_usage": (
            "Использование: /ask <шанс> <вопрос>\n"
            "шансы: почти, вероятно, поровну, навряд, маловероятно\n"
            "пример: /ask вероятно Нас заметили?"
        ),
        "ask_header": "🔮 Оракул",
        "ask_question": "Вопрос: {question}",
        "ask_odds": "Шанс: {label} ({chance}% за «да») — выпало {roll}",
        "ask_answer": "Ответ: {label}",
        "answer_yes": "✅ Да", "answer_no": "❌ Нет",
        "extreme_note": "⚡ Экстремальный результат — неожиданный драматический поворот!",
        "oracle_none": "Нет доступных таблиц оракула.",
        "oracle_unknown_table": "Неизвестная таблица «{table}». Доступны: {available}",
        "oracle_line": "🔮 {title}: {entry}",
        # set
        "set_usage": (
            "Использование: /set <трек> <значение>\n"
            "трек: здоровье, дух, припасы, импульс\n"
            "пример: /set припасы 3"
        ),
        "set_unknown": "Неизвестный трек «{field}». Выбери: здоровье, дух, припасы, импульс.",
        "set_out_of_bounds": "{field}: значение должно быть от {low} до {high}.",
        "set_done": "{field} — теперь {value}.",
        # sheet
        "sheet": (
            "📜 {name}\n"
            "{edge_l} {edge}  {heart_l} {heart}  {iron_l} {iron}  "
            "{shadow_l} {shadow}  {wits_l} {wits}\n"
            "{health_l} {health}/5   {spirit_l} {spirit}/5   {supply_l} {supply}/5\n"
            "{momentum_l} {momentum:+d} ({reset_l} {reset:+d})"
        ),
        # /new conversation
        "new_intro": "Создаём героя! Как его зовут? (/cancel — отмена)",
        "new_empty_name": "Введи непустое имя.",
        "new_ask_stat": "Задай {stat} ({lo}-{hi}):",
        "new_bad_stat": "Введи целое число от {lo} до {hi} для «{stat}».",
        "new_already_exists": "У тебя уже есть герой. Посмотри его через /me или меняй через /set.",
        "new_created": "Герой создан!",
        "new_cancelled": "Создание героя отменено.",
        "new_failed": "Не удалось создать героя: {error}",
        # language
        "language_current": "Текущий язык: {lang}. Выбери:",
        "language_set": "Язык переключён на {lang}.",
        # buttons
        "btn_next": "Дальше ▶", "btn_back": "◀ Назад", "btn_play": "Поехали! ▶",
        "btn_ru": "Русский", "btn_en": "English",
        # tutorial pages
        "tut_1": (
            "📘 *Туториал (1/4)* — Что это?\n\n"
            "Ironsworn — ролевая игра *без ведущего*. Историю придумываешь ты, а "
            "бот — это твои кубики, Оракул и лист персонажа. Можно играть одному "
            "или с друзьями в групповом чате.\n\n"
            "Нажми «Дальше» — расскажу про три вещи, которые ты будешь делать."
        ),
        "tut_2": (
            "📘 *Туториал (2/4)* — Твой герой\n\n"
            "Сначала создаёшь героя командой /new: имя, пять *характеристик* "
            "(Напор, Сердце, Сталь, Тень, Смекалка — каждая 1–3) и три *трека* "
            "(Здоровье, Дух, Припасы). *Импульс* — твой нарративный разгон.\n\n"
            "Этими характеристиками ты бросаешь кубики. Лист героя — /me."
        ),
        "tut_3": (
            "📘 *Туториал (3/4)* — Действия и вопросы\n\n"
            "• Делаешь рискованное → `/roll сталь` (или другая хар-ка). Сильный "
            "успех = отлично; слабый = да, но…; провал = беда.\n"
            "• Спроси мир да/нет → `/ask вероятно Дверь заперта?`\n"
            "• Нужна искра идеи → `/oracle` подкинет место или персонажа.\n\n"
            "Из передряги можно вырваться, сжигая разгон: `/roll сталь сжечь`."
        ),
        "tut_4": (
            "📘 *Туториал (4/4)* — Играем!\n\n"
            "Весь цикл: придумай → брось или спроси → опиши результат.\n\n"
            "Создай героя командой /new, потом попробуй `/ask вероятно …` и "
            "`/roll <хар-ка>`. Доброй игры, Ironsworn!"
        ),
    },
}
