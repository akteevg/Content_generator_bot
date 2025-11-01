"""Telegram bot entry point for the content idea generator."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Callable

import requests
from telebot import TeleBot, apihelper, types as tb_types

from .gigachat import GigaChatClient, GigaChatConfig, GigaChatError
from .parsing import IdeaParsingError, parse_ideas
from .prompts import (
    IDEA_SYSTEM_PROMPT,
    POST_SYSTEM_PROMPT,
    build_idea_prompt,
    build_post_prompt,
)
from .settings import MissingSettingError, get_settings
from .state import Idea, StateManager


logger = logging.getLogger(__name__)


def format_parameters(niche: str, goal: str, content_format: str) -> str:
    return (
        "Ваши параметры:\n"
        f"• Ниша: {niche}\n"
        f"• Цель: {goal}\n"
        f"• Формат: {content_format}"
    )


def format_ideas(ideas: list[Idea]) -> str:
    lines = ["Вот 5 идей:"]
    for index, idea in enumerate(ideas, start=1):
        lines.append(f"{index}. *{idea.title}* — {idea.description}")
    lines.append("\nВыберите идею, ответив номером или кнопкой ниже.")
    return "\n".join(lines)


def _build_number_keyboard(count: int, callback_prefix: str) -> tb_types.InlineKeyboardMarkup:
    keyboard = tb_types.InlineKeyboardMarkup(row_width=5)
    buttons = [
        tb_types.InlineKeyboardButton(str(i), callback_data=f"{callback_prefix}:{i}")
        for i in range(1, count + 1)
    ]
    keyboard.add(*buttons)
    return keyboard


def _build_restart_keyboard() -> tb_types.InlineKeyboardMarkup:
    keyboard = tb_types.InlineKeyboardMarkup()
    keyboard.add(
        tb_types.InlineKeyboardButton("Сгенерировать новый набор", callback_data="action:new"),
        tb_types.InlineKeyboardButton("О боте", callback_data="action:about"),
    )
    return keyboard


def create_app() -> TeleBot:
    try:
        settings = get_settings()
    except MissingSettingError as exc:
        raise RuntimeError(
            "Не заданы необходимые переменные окружения. См. README.md"
        ) from exc

    if settings.telegram_disable_ssl_verify:
        session = requests.Session()
        session.verify = False
        apihelper.session = session
        logger.warning(
            "TELEGRAM_DISABLE_SSL_VERIFY=true — проверка SSL отключена. Используйте только для диагностики."
        )

    bot = TeleBot(settings.telegram_bot_token, parse_mode="Markdown")
    state_manager = StateManager()

    verify_ssl = settings.gigachat_verify_ssl
    if verify_ssl is True:
        logger.info("GigaChat client will use system certificate store for TLS verification")
    elif isinstance(verify_ssl, str):
        logger.info("GigaChat client will use custom CA bundle: %s", verify_ssl)

    gigachat = GigaChatClient(
        GigaChatConfig(
            client_id=settings.gigachat_client_id,
            client_secret=settings.gigachat_client_secret,
            verify_ssl=verify_ssl,
        )
    )

    def with_state(handler: Callable):
        def wrapper(message):
            user_id = message.from_user.id
            state = state_manager.get(user_id)
            return handler(message, state)

        return wrapper

    def ask_niche(chat_id: int) -> None:
        bot.send_message(
            chat_id,
            "Начнём! Напишите, для какой ниши нужен контент (например: фитнес, образование, бизнес и т.д.).",
        )

    def ask_goal(chat_id: int) -> None:
        bot.send_message(
            chat_id,
            "Спасибо! Теперь укажите цель контента (например: привлечь аудиторию, обучить, продать и т.д.).",
        )

    def ask_format(chat_id: int) -> None:
        bot.send_message(
            chat_id,
            "Отлично. Какой формат интересует? (например: пост в соцсетях, статья и т.д.).",
        )

    def show_parameters(chat_id: int, state) -> None:
        keyboard = tb_types.InlineKeyboardMarkup()
        keyboard.add(tb_types.InlineKeyboardButton("Сгенерировать идеи", callback_data="action:generate"))
        bot.send_message(
            chat_id,
            format_parameters(state.niche, state.goal, state.content_format),
            reply_markup=keyboard,
        )

    help_text = (
        "ℹ️ Этот бот — MVP генератора контента.\n\n"
        "Как он работает:\n"
        "1. Спрашивает нишу, цель и формат.\n"
        "2. Генерирует 5 релевантных идей с краткими описаниями.\n"
        "3. Превращает выбранную идею в оформленный Markdown-пост с призывом к действию.\n\n"
        "Команды:\n"
        "/start — запустить сценарий заново.\n"
        "/help — показать эту подсказку."
    )

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        user_id = message.from_user.id
        state_manager.reset(user_id)
        greeting = (
            f"Привет, {message.from_user.first_name or 'друг'}! 👋\n"
            "Я — бот для генерации контент-идей: за три шага соберу исходные данные (нишу, цель и формат), предложу 5 идей и превращу выбранную в готовый пост. "
            "Если нужна подсказка — напиши /help.\n"
            "А сейчас расскажи, для какой ниши нужен контент."
        )
        bot.send_message(message.chat.id, greeting)
        ask_niche(message.chat.id)

    @bot.message_handler(commands=["help"])
    def handle_help(message):
        bot.send_message(message.chat.id, help_text)

    @bot.callback_query_handler(func=lambda call: call.data == "action:new")
    def handle_new(call):
        state_manager.reset(call.from_user.id)
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "🔄 Запускаем сценарий заново. Напиши нишу, чтобы начать новый набор идей.",
        )
        ask_niche(call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "action:about")
    def handle_about(call):
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, help_text)

    @bot.callback_query_handler(func=lambda call: call.data == "action:generate")
    def handle_generate(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        state = state_manager.get(user_id)
        if not all([state.niche, state.goal, state.content_format]):
            bot.send_message(
                call.message.chat.id,
                "Не все параметры заданы. Давайте начнём заново командой /start.",
            )
            return

        bot.send_chat_action(call.message.chat.id, "typing")
        bot.send_message(call.message.chat.id, "Генерирую идеи, это займёт несколько секунд...")

        try:
            response = gigachat.generate_completion(
                IDEA_SYSTEM_PROMPT,
                build_idea_prompt(state.niche, state.goal, state.content_format),
                temperature=0.9,
            )
            ideas = parse_ideas(response)
        except (GigaChatError, IdeaParsingError) as exc:
            logger.exception("Не удалось получить идеи")
            bot.send_message(
                call.message.chat.id,
                "Произошла ошибка при генерации идей. Попробуйте снова командой /start.",
            )
            return

        state.ideas = ideas
        state.step = "waiting_idea_selection"

        keyboard = _build_number_keyboard(len(ideas), "pick")
        bot.send_message(
            call.message.chat.id,
            format_ideas(ideas),
            reply_markup=keyboard,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pick:"))
    def handle_pick(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        state = state_manager.get(user_id)
        if state.step != "waiting_idea_selection" or not state.ideas:
            bot.send_message(call.message.chat.id, "Похоже, идеи ещё не готовы. Нажмите /start.")
            return

        try:
            selected_index = int(call.data.split(":", 1)[1]) - 1
        except ValueError:
            bot.send_message(call.message.chat.id, "Не удалось понять номер идеи. Попробуйте снова.")
            return

        if selected_index < 0 or selected_index >= len(state.ideas):
            bot.send_message(call.message.chat.id, "Такой идеи нет. Выберите номер из списка.")
            return

        state.selected_index = selected_index
        idea = state.ideas[selected_index]
        state.step = "generating_post"

        bot.send_chat_action(call.message.chat.id, "typing")
        bot.send_message(call.message.chat.id, "Отличный выбор! Собираю готовый пост...")

        try:
            post_text = gigachat.generate_completion(
                POST_SYSTEM_PROMPT,
                build_post_prompt(
                    state.niche,
                    state.goal,
                    state.content_format,
                    idea.title,
                    idea.description,
                ),
                temperature=0.8,
            )
        except GigaChatError:
            logger.exception("Ошибка генерации поста")
            bot.send_message(
                call.message.chat.id,
                "Не удалось получить текст поста. Попробуйте снова командой /start.",
            )
            return

        state.step = "finished"
        bot.send_message(
            call.message.chat.id,
            f"Готово! Вот ваш пост:\n\n{post_text}",
            reply_markup=_build_restart_keyboard(),
        )

    @bot.message_handler(content_types=["text"])
    @with_state
    def handle_text(message, state):
        user_input = message.text.strip()
        chat_id = message.chat.id

        if message.entities and any(ent.type == "bot_command" for ent in message.entities):
            return

        if state.step == "waiting_niche":
            state.niche = user_input
            state.step = "waiting_goal"
            ask_goal(chat_id)
        elif state.step == "waiting_goal":
            state.goal = user_input
            state.step = "waiting_format"
            ask_format(chat_id)
        elif state.step == "waiting_format":
            state.content_format = user_input
            state.step = "ready_to_generate"
            show_parameters(chat_id, state)
        elif state.step == "waiting_idea_selection" and user_input.isdigit():
            # Поддержка текстового ввода номера идеи.
            fake_call = SimpleNamespace(
                id=str(message.message_id),
                from_user=message.from_user,
                message=message,
                data=f"pick:{user_input}",
            )
            handle_pick(fake_call)  # type: ignore[arg-type]
        else:
            bot.send_message(
                chat_id,
                "Не понял сообщение. Используйте /start, чтобы начать заново.",
            )

    return bot

