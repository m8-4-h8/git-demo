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

# Difficulty ranks (shared by vows and tracks) -> canonical engine rank value.
RANK_ALIASES = {
    "troublesome": "troublesome", "беспокойный": "troublesome",
    "тревожный": "troublesome",
    "dangerous": "dangerous", "опасный": "dangerous",
    "formidable": "formidable", "грозный": "formidable",
    "extreme": "extreme", "экстремальный": "extreme",
    "epic": "epic", "эпический": "epic",
}

# Progress-track types -> canonical engine track type value.
TRACK_TYPE_ALIASES = {
    "combat": "combat", "схватка": "combat", "бой": "combat",
    "journey": "journey", "путешествие": "journey", "путь": "journey",
    "bond": "bond", "связь": "bond",
    "custom": "custom", "своё": "custom", "свое": "custom", "другое": "custom",
}

# /vow sub-commands -> canonical action.
VOW_ACTIONS = {
    "new": "new", "новый": "new", "создать": "new",
    "list": "list", "список": "list",
    "progress": "progress", "прогресс": "progress", "отметить": "progress",
    "fulfill": "fulfill", "выполнить": "fulfill", "исполнить": "fulfill",
    "forsake": "forsake", "отказаться": "forsake", "бросить": "forsake",
}

# /track sub-commands -> canonical action.
TRACK_ACTIONS = {
    "new": "new", "новый": "new", "создать": "new",
    "list": "list", "список": "list",
    "hit": "hit", "отметить": "hit", "прогресс": "hit",
    "end": "end", "завершить": "end", "конец": "end",
    "clear": "clear", "сброс": "clear", "сбросить": "clear",
}

# /gm sub-commands -> canonical action.
GM_ACTIONS = {
    "start": "start", "старт": "start", "начать": "start",
    "scene": "scene", "сцена": "scene",
    "npcs": "npcs", "нпс": "npcs", "персонажи": "npcs",
    "stop": "stop", "стоп": "stop", "завершить": "stop",
}


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
            "🎲 Commands\n"
            "/new — create your hero (step by step)\n"
            "/me — show your hero sheet\n"
            "/roll <stat> [adds] [burn] — action roll\n"
            "/ask <odds> <question> — ask the Oracle (yes/no)\n"
            "/oracle [table] — draw a spark of inspiration\n"
            "/set <track> <value> — change health/spirit/supply/momentum\n"
            "/vow <new|list|progress|fulfill|forsake> — sworn quests\n"
            "/track <new|list|hit|end|clear> — group progress tracks\n"
            "/gm <start|scene|npcs|stop> — play with an AI Game Master\n"
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
            "*Vows & tracks:* swear a quest with `/vow new <rank> <title>`, mark "
            "progress as you act (`/vow progress 1`), then `/vow fulfill 1` to test "
            "the outcome. `/track` works the same way for combats, journeys and "
            "bonds shared by the whole group.\n\n"
            "That's it. Start with /new and just play. Try /tutorial to see it in "
            "action."
        ),
        # generic
        "no_character": "You don't have a hero yet. Create one with /new.",
        "error_generic": "⚠️ Something went wrong. Please try again.",
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
        # vows & progress tracks — rank / type labels
        "rank_troublesome": "Troublesome", "rank_dangerous": "Dangerous",
        "rank_formidable": "Formidable", "rank_extreme": "Extreme",
        "rank_epic": "Epic",
        "type_combat": "Combat", "type_journey": "Journey",
        "type_bond": "Bond", "type_custom": "Custom",
        # vows
        "vow_usage": (
            "Usage:\n"
            "/vow new <rank> <title>\n"
            "/vow list\n"
            "/vow progress <id|title> [hits]\n"
            "/vow fulfill <id|title>\n"
            "/vow forsake <id|title>\n"
            "ranks: troublesome, dangerous, formidable, extreme, epic"
        ),
        "vow_new_usage": (
            "Usage: /vow new <rank> <title>\n"
            "ranks: troublesome, dangerous, formidable, extreme, epic\n"
            "example: /vow new dangerous Find the lost troop"
        ),
        "vow_unknown_rank": (
            "Unknown rank '{rank}'. Choose: troublesome, dangerous, "
            "formidable, extreme, epic."
        ),
        "vow_item": "#{id} {title} [{rank}]\n{bar} {progress:.1f}/10",
        "vow_created": "🗡 Vow sworn!",
        "vow_list_header": "🗡 Active vows:",
        "vow_list_empty": "No active vows. Swear one with: /vow new <rank> <title>",
        "vow_not_found": "Vow '{ref}' not found. See /vow list.",
        "vow_progress_done": "📈 Progress on “{title}”\n{bar} {progress:.1f}/10",
        "vow_fulfill_header": "🗡 Fulfillment roll — “{title}”",
        "vow_fulfill_line": (
            "Progress score {score} · challenge dice {a} | {b}\nResult: {result}"
        ),
        "vow_fulfilled_strong": "💪 Strong hit — vow fulfilled! 🎉",
        "vow_fulfilled_weak": "👍 Weak hit — fulfilled, but with a complication.",
        "vow_fulfill_miss": "💥 Miss — not fulfilled. Progress stands; keep going.",
        "vow_forsaken_spirit": "🏳 Vow “{title}” forsaken. Spirit −1 (now {spirit}/5).",
        "vow_forsaken_no_char": "🏳 Vow “{title}” forsaken.",
        # progress tracks
        "track_usage": (
            "Usage:\n"
            "/track new <type> <rank> <title>\n"
            "/track list\n"
            "/track hit <id|title> [hits]\n"
            "/track end <id|title>\n"
            "/track clear <id|title>\n"
            "types: combat, journey, bond, custom"
        ),
        "track_new_usage": (
            "Usage: /track new <type> <rank> <title>\n"
            "types: combat, journey, bond, custom\n"
            "ranks: troublesome, dangerous, formidable, extreme, epic\n"
            "example: /track new combat formidable Duel with the warlord"
        ),
        "track_unknown_type": (
            "Unknown type '{type}'. Choose: combat, journey, bond, custom."
        ),
        "track_unknown_rank": (
            "Unknown rank '{rank}'. Choose: troublesome, dangerous, "
            "formidable, extreme, epic."
        ),
        "track_item": "#{id} {title} [{type} · {rank}]\n{bar} {progress:.1f}/10",
        "track_created": "🧭 Progress track created!",
        "track_list_header": "🧭 Active group tracks:",
        "track_list_empty": (
            "No active tracks. Start one with: /track new <type> <rank> <title>"
        ),
        "track_not_found": "Track '{ref}' not found. See /track list.",
        "track_hit_done": "📈 Progress on “{title}”\n{bar} {progress:.1f}/10",
        "track_end_header": "🧭 Encounter ended — “{title}”",
        "track_end_line": "{bar} {progress:.1f}/10\nResult: {result}",
        "track_end_strong": "💪 Strong hit — a decisive success!",
        "track_end_weak": "👍 Weak hit — success, at a cost.",
        "track_end_miss": "💥 Miss — it goes badly.",
        "track_cleared": "🧭 Track “{title}” cleared (progress reset to 0).",
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
            "🎲 Команды\n"
            "/new — создать героя (по шагам)\n"
            "/me — лист героя\n"
            "/roll <хар-ка> [бонус] [сжечь] — бросок действия\n"
            "/ask <шанс> <вопрос> — спросить Оракула (да/нет)\n"
            "/oracle [таблица] — подсказка-вдохновение\n"
            "/set <трек> <значение> — изменить здоровье/дух/припасы/импульс\n"
            "/vow <new|list|progress|fulfill|forsake> — обеты (клятвы)\n"
            "/track <new|list|hit|end|clear> — треки прогресса группы\n"
            "/gm <start|scene|npcs|stop> — игра с AI-Мастером\n"
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
            "*Обеты и треки:* принеси обет `/vow new <ранг> <название>`, отмечай "
            "прогресс по ходу игры (`/vow progress 1`), затем `/vow fulfill 1` — "
            "бросок исхода. `/track` работает так же для схваток, путешествий и "
            "связей, общих для всей группы.\n\n"
            "Вот и всё. Начни с /new и просто играй. Глянь /tutorial — там по шагам."
        ),
        # generic
        "no_character": "У тебя ещё нет героя. Создай командой /new.",
        "error_generic": "⚠️ Что-то пошло не так. Попробуй ещё раз.",
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
        # vows & progress tracks — rank / type labels
        "rank_troublesome": "Беспокойный", "rank_dangerous": "Опасный",
        "rank_formidable": "Грозный", "rank_extreme": "Экстремальный",
        "rank_epic": "Эпический",
        "type_combat": "Схватка", "type_journey": "Путешествие",
        "type_bond": "Связь", "type_custom": "Своё",
        # vows
        "vow_usage": (
            "Использование:\n"
            "/vow new <ранг> <название>\n"
            "/vow list\n"
            "/vow progress <id|название> [разы]\n"
            "/vow fulfill <id|название>\n"
            "/vow forsake <id|название>\n"
            "ранги: troublesome, dangerous, formidable, extreme, epic"
        ),
        "vow_new_usage": (
            "Использование: /vow new <ранг> <название>\n"
            "ранги: troublesome, dangerous, formidable, extreme, epic\n"
            "пример: /vow new dangerous Найти пропавший отряд"
        ),
        "vow_unknown_rank": (
            "Неизвестный ранг «{rank}». Выбери: troublesome, dangerous, "
            "formidable, extreme, epic."
        ),
        "vow_item": "#{id} {title} [{rank}]\n{bar} {progress:.1f}/10",
        "vow_created": "🗡 Обет принесён!",
        "vow_list_header": "🗡 Активные обеты:",
        "vow_list_empty": "Нет активных обетов. Принеси: /vow new <ранг> <название>",
        "vow_not_found": "Обет «{ref}» не найден. Смотри /vow list.",
        "vow_progress_done": "📈 Прогресс по «{title}»\n{bar} {progress:.1f}/10",
        "vow_fulfill_header": "🗡 Бросок выполнения — «{title}»",
        "vow_fulfill_line": (
            "Очки прогресса {score} · кубики испытания {a} | {b}\nИтог: {result}"
        ),
        "vow_fulfilled_strong": "💪 Сильный успех — обет выполнен! 🎉",
        "vow_fulfilled_weak": "👍 Слабый успех — выполнен, но с осложнением.",
        "vow_fulfill_miss": "💥 Провал — не выполнен. Прогресс сохраняется, продолжай.",
        "vow_forsaken_spirit": "🏳 Обет «{title}» оставлен. Дух −1 (теперь {spirit}/5).",
        "vow_forsaken_no_char": "🏳 Обет «{title}» оставлен.",
        # progress tracks
        "track_usage": (
            "Использование:\n"
            "/track new <тип> <ранг> <название>\n"
            "/track list\n"
            "/track hit <id|название> [разы]\n"
            "/track end <id|название>\n"
            "/track clear <id|название>\n"
            "типы: combat, journey, bond, custom"
        ),
        "track_new_usage": (
            "Использование: /track new <тип> <ранг> <название>\n"
            "типы: combat, journey, bond, custom\n"
            "ранги: troublesome, dangerous, formidable, extreme, epic\n"
            "пример: /track new combat formidable Дуэль с вождём"
        ),
        "track_unknown_type": (
            "Неизвестный тип «{type}». Выбери: combat, journey, bond, custom."
        ),
        "track_unknown_rank": (
            "Неизвестный ранг «{rank}». Выбери: troublesome, dangerous, "
            "formidable, extreme, epic."
        ),
        "track_item": "#{id} {title} [{type} · {rank}]\n{bar} {progress:.1f}/10",
        "track_created": "🧭 Трек прогресса создан!",
        "track_list_header": "🧭 Активные треки группы:",
        "track_list_empty": (
            "Нет активных треков. Начни: /track new <тип> <ранг> <название>"
        ),
        "track_not_found": "Трек «{ref}» не найден. Смотри /track list.",
        "track_hit_done": "📈 Прогресс по «{title}»\n{bar} {progress:.1f}/10",
        "track_end_header": "🧭 Испытание завершено — «{title}»",
        "track_end_line": "{bar} {progress:.1f}/10\nИтог: {result}",
        "track_end_strong": "💪 Сильный успех — решительная победа!",
        "track_end_weak": "👍 Слабый успех — успех, но с ценой.",
        "track_end_miss": "💥 Провал — всё идёт плохо.",
        "track_cleared": "🧭 Трек «{title}» сброшен (прогресс обнулён).",
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


# --- AI Game Master strings (gm/ layer) ----------------------------------------
TEXTS["en"].update({
    "gm_usage": "Usage: /gm start | scene | npcs | stop",
    "gm_disabled": "The Game Master is turned off.",
    "gm_pick_header": "🎲 Choose your campaign:",
    "gm_pick_failed": "The Game Master is silent right now — try again in a moment.",
    "gm_pick_expired": "Those options expired. Run /gm start again.",
    "gm_started": "🗺️ Campaign begun: {title}\nA vow is sworn: {goal}",
    "gm_scene_header": "🗺️ Current scene:",
    "gm_no_campaign": "No active campaign. Start one with /gm start.",
    "gm_npcs_header": "🎭 NPCs the GM remembers:",
    "gm_npcs_empty": "The GM hasn't named any NPCs yet.",
    "gm_npc_item": "• {name}: {description}",
    "gm_stop_confirm": "End the current campaign? Its state will be cleared.",
    "gm_stopped": "Campaign ended.",
    "gm_stop_cancelled": "Cancelled — the campaign continues.",
    "gm_yes": "Yes, end it",
    "gm_no": "No, keep playing",
})
TEXTS["ru"].update({
    "gm_usage": "Использование: /gm start | scene | npcs | stop",
    "gm_disabled": "Мастер (GM) выключен.",
    "gm_pick_header": "🎲 Выбери кампанию:",
    "gm_pick_failed": "Мастер сейчас молчит — попробуй ещё раз через миг.",
    "gm_pick_expired": "Эти варианты устарели. Запусти /gm start заново.",
    "gm_started": "🗺️ Кампания начата: {title}\nПринесён обет: {goal}",
    "gm_scene_header": "🗺️ Текущая сцена:",
    "gm_no_campaign": "Активной кампании нет. Начни её командой /gm start.",
    "gm_npcs_header": "🎭 NPC, которых помнит Мастер:",
    "gm_npcs_empty": "Мастер пока не называл NPC по имени.",
    "gm_npc_item": "• {name}: {description}",
    "gm_stop_confirm": "Завершить текущую кампанию? Её состояние будет очищено.",
    "gm_stopped": "Кампания завершена.",
    "gm_stop_cancelled": "Отменено — кампания продолжается.",
    "gm_yes": "Да, завершить",
    "gm_no": "Нет, играем дальше",
})


# --- Button-driven UX (menu, moves, submenus) ----------------------------------
TEXTS["en"].update({
    # navigation
    "btn_home": "🏠 Menu",
    "menu_title": "Main menu — pick an action:",
    # main-menu buttons
    "menu_move": "⚔️ Make a Move",
    "menu_roll": "🎲 Roll",
    "menu_vows": "📜 My Vows",
    "menu_tracks": "🗺️ Tracks",
    "menu_character": "👤 Character",
    "menu_oracle": "🔮 Oracle",
    "menu_gm": "🎭 GM / Scene",
    "menu_help": "❓ Help",
    # move categories
    "cat_adventure": "🌄 Adventure",
    "cat_combat": "⚔️ Combat",
    "cat_quest": "🎯 Quest",
    # move names
    "move_strike": "Strike",
    "move_clash": "Clash",
    "move_face_danger": "Face Danger",
    "move_secure_advantage": "Secure an Advantage",
    "move_gather_information": "Gather Information",
    "move_gather_your_resolve": "Gather Your Resolve",
    "move_reach_a_milestone": "Reach a Milestone",
    # move flow
    "move_cat_title": "Choose a move category:",
    "move_pick_title": "Choose a move:",
    "move_stat_title": "Which stat do you roll?",
    "move_result_header": "⚔️ {move}",
    "move_effect_header": "Effect:",
    "move_no_effect": "No mechanical change.",
    # roll / oracle flows
    "roll_pick_title": "Roll which stat?",
    "oracle_pick_title": "How likely is it?",
    # character submenu
    "char_menu_title": "Character:",
    "char_show_btn": "📜 Sheet",
    "char_set_btn": "✏️ Adjust tracks",
    "char_create_btn": "✨ Create hero",
    "char_set_title": "Which track to adjust?",
    "char_field_now": "{field}: {value}",
    # vows submenu
    "vow_menu_title": "Vows:",
    "vow_list_title": "Choose a vow:",
    "vow_act_title": "What do you do with this vow?",
    "vow_list_btn": "📜 List",
    "vow_new_btn": "✨ New vow",
    "vow_do_progress": "📈 Progress",
    "vow_do_fulfill": "✅ Fulfill",
    "vow_do_forsake": "🏳 Forsake",
    "vnew_pick_rank": "Choose the vow's rank:",
    "vnew_ask_title": "Type the vow's title: (/cancel to abort)",
    # tracks submenu
    "track_menu_title": "Group tracks:",
    "track_list_title": "Choose a track:",
    "track_act_title": "What do you do with this track?",
    "track_list_btn": "🗺️ List",
    "track_new_btn": "✨ New track",
    "track_do_hit": "📈 Mark progress",
    "track_do_end": "🏁 End",
    "track_do_clear": "🧹 Clear",
    "tnew_pick_type": "Choose the track type:",
    "tnew_pick_rank": "Choose the track's rank:",
    "tnew_ask_title": "Type the track's title: (/cancel to abort)",
    # GM submenu
    "gm_menu_title": "Game Master:",
    "gm_start_btn": "🗺️ Start campaign",
    "gm_scene_btn": "🎬 Scene",
    "gm_npcs_btn": "🎭 NPCs",
    "gm_stop_btn": "⏹ End campaign",
})
TEXTS["ru"].update({
    # navigation
    "btn_home": "🏠 Меню",
    "menu_title": "Главное меню — выбери действие:",
    # main-menu buttons
    "menu_move": "⚔️ Сделать ход",
    "menu_roll": "🎲 Бросок",
    "menu_vows": "📜 Мои обеты",
    "menu_tracks": "🗺️ Треки",
    "menu_character": "👤 Персонаж",
    "menu_oracle": "🔮 Оракул",
    "menu_gm": "🎭 GM / Сцена",
    "menu_help": "❓ Помощь",
    # move categories
    "cat_adventure": "🌄 Приключение",
    "cat_combat": "⚔️ Схватка",
    "cat_quest": "🎯 Поход",
    # move names
    "move_strike": "Удар",
    "move_clash": "Сшибка",
    "move_face_danger": "Встретить опасность",
    "move_secure_advantage": "Закрепить преимущество",
    "move_gather_information": "Собрать сведения",
    "move_gather_your_resolve": "Собраться с духом",
    "move_reach_a_milestone": "Достичь вехи",
    # move flow
    "move_cat_title": "Выбери категорию хода:",
    "move_pick_title": "Выбери ход:",
    "move_stat_title": "Какой характеристикой бросаешь?",
    "move_result_header": "⚔️ {move}",
    "move_effect_header": "Эффект:",
    "move_no_effect": "Без механических изменений.",
    # roll / oracle flows
    "roll_pick_title": "Каким параметром бросок?",
    "oracle_pick_title": "Насколько это вероятно?",
    # character submenu
    "char_menu_title": "Персонаж:",
    "char_show_btn": "📜 Лист",
    "char_set_btn": "✏️ Изменить треки",
    "char_create_btn": "✨ Создать героя",
    "char_set_title": "Какой трек изменить?",
    "char_field_now": "{field}: {value}",
    # vows submenu
    "vow_menu_title": "Обеты:",
    "vow_list_title": "Выбери обет:",
    "vow_act_title": "Что сделать с обетом?",
    "vow_list_btn": "📜 Список",
    "vow_new_btn": "✨ Новый обет",
    "vow_do_progress": "📈 Прогресс",
    "vow_do_fulfill": "✅ Выполнить",
    "vow_do_forsake": "🏳 Отказаться",
    "vnew_pick_rank": "Выбери ранг обета:",
    "vnew_ask_title": "Введи название обета: (/cancel — отмена)",
    # tracks submenu
    "track_menu_title": "Треки группы:",
    "track_list_title": "Выбери трек:",
    "track_act_title": "Что сделать с треком?",
    "track_list_btn": "🗺️ Список",
    "track_new_btn": "✨ Новый трек",
    "track_do_hit": "📈 Отметить",
    "track_do_end": "🏁 Завершить",
    "track_do_clear": "🧹 Сброс",
    "tnew_pick_type": "Выбери тип трека:",
    "tnew_pick_rank": "Выбери ранг трека:",
    "tnew_ask_title": "Введи название трека: (/cancel — отмена)",
    # GM submenu
    "gm_menu_title": "Мастер (GM):",
    "gm_start_btn": "🗺️ Начать кампанию",
    "gm_scene_btn": "🎬 Сцена",
    "gm_npcs_btn": "🎭 NPC",
    "gm_stop_btn": "⏹ Завершить кампанию",
})


# --- Inventory & background --------------------------------------------------
TEXTS["en"].update({
    # sheet additions
    "sheet_items": "📦 Inventory: {items}",
    "sheet_items_empty": "empty",
    "sheet_background": "📖 Story: {text}",
    "sheet_background_empty": "not set",
    # character-menu buttons
    "item_add_btn": "➕ Add item",
    "item_del_btn": "➖ Remove item",
    "bg_set_btn": "✏️ Set story",
    # add item
    "item_add_prompt": "Type the item's name: (/cancel to abort)",
    "item_empty_name": "Please enter a non-empty name.",
    "item_too_long": "Too long — at most {max} characters.",
    "inventory_full": "Inventory is full (max {max} items).",
    "item_added": "📦 Added: {item}",
    # remove item
    "item_remove_title": "Pick an item to remove:",
    "inventory_empty": "Your inventory is empty.",
    "item_removed": "🗑 Removed: {item}",
    # background
    "bg_prompt": "Tell your hero's story (up to {max} characters): (/cancel to abort)",
    "bg_too_long": "Too long — at most {max} characters.",
    "bg_set": "📖 Story updated.",
})
TEXTS["ru"].update({
    # sheet additions
    "sheet_items": "📦 Инвентарь: {items}",
    "sheet_items_empty": "пусто",
    "sheet_background": "📖 История: {text}",
    "sheet_background_empty": "не задана",
    # character-menu buttons
    "item_add_btn": "➕ Добавить предмет",
    "item_del_btn": "➖ Убрать предмет",
    "bg_set_btn": "✏️ Задать историю",
    # add item
    "item_add_prompt": "Введи название предмета: (/cancel — отмена)",
    "item_empty_name": "Введи непустое название.",
    "item_too_long": "Слишком длинно — максимум {max} символов.",
    "inventory_full": "Инвентарь полон (максимум {max} предметов).",
    "item_added": "📦 Добавлено: {item}",
    # remove item
    "item_remove_title": "Выбери предмет для удаления:",
    "inventory_empty": "Инвентарь пуст.",
    "item_removed": "🗑 Убрано: {item}",
    # background
    "bg_prompt": "Расскажи историю героя (до {max} символов): (/cancel — отмена)",
    "bg_too_long": "Слишком длинно — максимум {max} символов.",
    "bg_set": "📖 История обновлена.",
})


# --- Archetypes & the guided /new flow ---------------------------------------
TEXTS["en"].update({
    # one-line stat explanations (shown during allocation)
    "stat_edge_desc": "speed, reflexes, precision in swift action",
    "stat_heart_desc": "will, charisma, bonds with others and yourself",
    "stat_iron_desc": "strength, endurance, direct confrontation",
    "stat_shadow_desc": "stealth, cunning, acting unseen",
    "stat_wits_desc": "observation, improvisation, knowledge",
    # archetype names
    "arch_warrior_name": "Warrior",
    "arch_rogue_name": "Rogue",
    "arch_ranger_name": "Ranger",
    "arch_sage_name": "Sage",
    "arch_priest_name": "Priest",
    "arch_bard_name": "Bard",
    "arch_savage_name": "Savage",
    "arch_wanderer_name": "Wanderer",
    # archetype descriptions (2-3 sentences, original flavour)
    "arch_warrior_desc": (
        "You hold the line where others break. Strength and steel are your "
        "answer to almost any threat."
    ),
    "arch_rogue_desc": (
        "Shadow and a sharp plan beat brute force. You slip in unseen and are "
        "gone before the alarm is raised."
    ),
    "arch_ranger_desc": (
        "The wild trails are your home and no quarry escapes the horizon. A keen "
        "eye and quick feet carry you where others get lost."
    ),
    "arch_sage_desc": (
        "You seek the knowledge that sleeps in old stones and forgotten words. "
        "Where force fails, understanding decides."
    ),
    "arch_priest_desc": (
        "Your faith is a shield for your companions and a light in the deepest "
        "night. You mend bodies and keep the party's spirit whole."
    ),
    "arch_bard_desc": (
        "A word and a song open doors closed to any blade. You inspire your "
        "friends and unsettle your foes."
    ),
    "arch_savage_desc": (
        "You grew where only the strongest survive, and you carry that fury with "
        "you. In battle you are an unstoppable storm."
    ),
    "arch_wanderer_desc": (
        "No road is strange to you, no land holds you long. You read the omens "
        "of the trail and find a path where there is none."
    ),
    # starting-item labels (archetype gear)
    "item_sword": "Sword", "item_shield": "Shield",
    "item_daggers": "Daggers", "item_lockpicks": "Lockpicks",
    "item_bow": "Bow", "item_arrows": "Arrows",
    "item_spellbook": "Spellbook", "item_staff": "Staff",
    "item_holy_symbol": "Holy symbol", "item_healing_herbs": "Healing herbs",
    "item_lute": "Lute", "item_wine_flask": "Wine flask",
    "item_axe": "Axe", "item_beast_pelt": "Beast pelt",
    "item_herbs": "Herbs", "item_wanderers_staff": "Wanderer's staff",
    # flow
    "new_pick_archetype": "Choose your hero's path:",
    "new_arch_boost": "This path strengthens: {stat}",
    "new_alloc_intro": (
        "You have 5 stats. Spread the values 1, 1, 2, 2, 3 across them — each "
        "value used once."
    ),
    "new_alloc_unassigned": "—",
    "new_alloc_tap_value": "Tap a value, then choose which stat receives it.",
    "new_assign_prompt": "Assign {value} to which stat?",
    "new_confirm_title": "Review your hero:",
    "new_confirm_archetype_line": "Path: {icon} {name}",
    "new_confirm_items_line": "📦 Starting gear: {items}",
    "new_boost_mark": " (+1 path)",
    "sheet_archetype": "🎲 Path: {icon} {name}",
    "btn_confirm": "✅ Confirm",
    "btn_other_path": "⬅️ Another path",
    "btn_done": "✅ Done",
    "btn_create_hero": "✅ Create hero",
    "btn_restart": "🔄 Start over",
})
TEXTS["ru"].update({
    # one-line stat explanations (shown during allocation)
    "stat_edge_desc": "скорость, рефлексы, точность в стремительных действиях",
    "stat_heart_desc": "воля, харизма, связь с другими и собой",
    "stat_iron_desc": "сила, выносливость, прямая конфронтация",
    "stat_shadow_desc": "скрытность, хитрость, действия в обход",
    "stat_wits_desc": "наблюдательность, импровизация, знания",
    # archetype names
    "arch_warrior_name": "Воин",
    "arch_rogue_name": "Разбойник",
    "arch_ranger_name": "Следопыт",
    "arch_sage_name": "Мудрец",
    "arch_priest_name": "Жрец",
    "arch_bard_name": "Бард",
    "arch_savage_name": "Дикарь",
    "arch_wanderer_name": "Странник",
    # archetype descriptions (2-3 sentences, original flavour)
    "arch_warrior_desc": (
        "Ты держишь строй там, где другие бегут. Сила и сталь — твой ответ "
        "почти на любую угрозу."
    ),
    "arch_rogue_desc": (
        "Тень и точный расчёт надёжнее грубой силы. Ты входишь незамеченным и "
        "уходишь раньше, чем поднимут тревогу."
    ),
    "arch_ranger_desc": (
        "Дикие тропы — твой дом, и добыча не уйдёт за горизонт. Меткий глаз и "
        "быстрые ноги ведут тебя там, где теряются другие."
    ),
    "arch_sage_desc": (
        "Ты ищешь знание, что дремлет в старых камнях и забытых словах. Там, где "
        "сила бессильна, решает понимание."
    ),
    "arch_priest_desc": (
        "Твоя вера — щит для спутников и свет в самой глухой ночи. Ты исцеляешь "
        "тела и держишь дух отряда."
    ),
    "arch_bard_desc": (
        "Слово и песня открывают двери, запертые для клинка. Ты вдохновляешь "
        "друзей и сбиваешь с толку врагов."
    ),
    "arch_savage_desc": (
        "Ты вырос там, где выживает лишь сильнейший, и носишь эту ярость с собой. "
        "В бою ты буря, которую не остановить."
    ),
    "arch_wanderer_desc": (
        "Ни один путь тебе не чужой, ни одна земля не держит надолго. Ты читаешь "
        "приметы дороги и находишь тропу там, где её нет."
    ),
    # starting-item labels (archetype gear)
    "item_sword": "Меч", "item_shield": "Щит",
    "item_daggers": "Кинжалы", "item_lockpicks": "Отмычки",
    "item_bow": "Лук", "item_arrows": "Стрелы",
    "item_spellbook": "Книга заклинаний", "item_staff": "Посох",
    "item_holy_symbol": "Символ веры", "item_healing_herbs": "Целебные травы",
    "item_lute": "Лютня", "item_wine_flask": "Фляга вина",
    "item_axe": "Топор", "item_beast_pelt": "Звериная шкура",
    "item_herbs": "Травы", "item_wanderers_staff": "Посох странника",
    # flow
    "new_pick_archetype": "Выбери путь героя:",
    "new_arch_boost": "Этот путь усиливает: {stat}",
    "new_alloc_intro": (
        "У тебя 5 характеристик. Распредели значения 1, 1, 2, 2, 3 между ними — "
        "каждое значение по одному разу."
    ),
    "new_alloc_unassigned": "—",
    "new_alloc_tap_value": "Нажми значение, затем выбери, какой характеристике его отдать.",
    "new_assign_prompt": "Кому отдать {value}?",
    "new_confirm_title": "Проверь героя:",
    "new_confirm_archetype_line": "Путь: {icon} {name}",
    "new_confirm_items_line": "📦 Стартовые предметы: {items}",
    "new_boost_mark": " (+1 путь)",
    "sheet_archetype": "🎲 Путь: {icon} {name}",
    "btn_confirm": "✅ Подтвердить",
    "btn_other_path": "⬅️ Другой путь",
    "btn_done": "✅ Готово",
    "btn_create_hero": "✅ Создать героя",
    "btn_restart": "🔄 Начать заново",
})
