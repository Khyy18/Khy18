"""FSM states for the exchange flow."""

from aiogram.fsm.state import State, StatesGroup


class ExchangeStates(StatesGroup):
    """States for the exchange conversation flow."""

    select_from_currency = State()
    select_to_currency = State()
    enter_amount = State()
    enter_wallet = State()
    confirm_exchange = State()
