from app.presentation.telegram.errors import user_id_of


def is_admin(update: object, admin_ids: tuple[int, ...]) -> bool:
    """True when the driver behind this update may open the admin panel.

    Lives here rather than in the admin handlers because the menu keyboard has
    to ask the same question before it decides whether to draw the button.
    """
    user_id = user_id_of(update)
    return user_id is not None and user_id in admin_ids
