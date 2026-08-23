from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.value_objects.user_settings import RADIUS_STEP_METERS, RESULT_LIMIT_STEP

_RADIUS_STEP_KM = RADIUS_STEP_METERS // 1000


def build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"➕ Radius +{_RADIUS_STEP_KM} km",
                    callback_data="settings:radius:inc",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"➖ Radius -{_RADIUS_STEP_KM} km",
                    callback_data="settings:radius:dec",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"➕ Natijalar +{RESULT_LIMIT_STEP}",
                    callback_data="settings:limit:inc",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"➖ Natijalar -{RESULT_LIMIT_STEP}",
                    callback_data="settings:limit:dec",
                )
            ],
        ]
    )
