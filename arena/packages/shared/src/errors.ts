import type { EngineErrorCode } from '@arena/game-engine';

/** Every error the API or WebSocket can return. Clients show `ERROR_TEXT_RU`, never raw messages. */
export type AppErrorCode =
  | 'UNAUTHORIZED'
  | 'INIT_DATA_INVALID'
  | 'INIT_DATA_EXPIRED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'VALIDATION_FAILED'
  | 'RATE_LIMITED'
  | 'INSUFFICIENT_FUNDS'
  | 'DUPLICATE_REQUEST'
  | 'ROOM_FULL'
  | 'ROOM_CLOSED'
  | 'GAME_ALREADY_STARTED'
  | 'WRONG_PASSWORD'
  | 'ALREADY_IN_ROOM'
  | 'MODE_NOT_SUPPORTED'
  | 'DECK_NOT_SUPPORTED'
  | 'PLAYER_DISCONNECTED'
  | 'NO_CONNECTION'
  | 'BANNED'
  | 'DAILY_CREDITS_NOT_READY'
  | 'DAILY_CREDITS_BALANCE_TOO_HIGH'
  | 'SERVER_ERROR'
  | EngineErrorCode;

export interface ApiErrorBody {
  error: AppErrorCode;
  message: string;
}

export const ERROR_TEXT_RU: Record<AppErrorCode, string> = {
  UNAUTHORIZED: 'Сессия истекла. Откройте игру из Telegram заново.',
  INIT_DATA_INVALID: 'Не удалось подтвердить вход через Telegram.',
  INIT_DATA_EXPIRED: 'Ссылка на игру устарела. Откройте её из бота заново.',
  FORBIDDEN: 'Нет доступа.',
  NOT_FOUND: 'Не найдено.',
  VALIDATION_FAILED: 'Проверьте введённые данные.',
  RATE_LIMITED: 'Слишком часто. Подождите немного.',
  INSUFFICIENT_FUNDS: 'Недостаточно средств.',
  DUPLICATE_REQUEST: 'Запрос уже обработан.',
  ROOM_FULL: 'Комната заполнена.',
  ROOM_CLOSED: 'Комната закрыта.',
  GAME_ALREADY_STARTED: 'Игра уже началась.',
  WRONG_PASSWORD: 'Неверный пароль.',
  ALREADY_IN_ROOM: 'Вы уже в другой комнате.',
  MODE_NOT_SUPPORTED: 'Этот режим скоро появится.',
  DECK_NOT_SUPPORTED: 'Эта колода скоро появится.',
  PLAYER_DISCONNECTED: 'Игрок отключился.',
  NO_CONNECTION: 'Нет соединения.',
  SERVER_ERROR: 'Ошибка сервера. Попробуйте ещё раз.',
  BANNED: 'Учётная запись заблокирована.',
  DAILY_CREDITS_NOT_READY: 'Бесплатные кредиты можно получать раз в сутки.',
  DAILY_CREDITS_BALANCE_TOO_HIGH: 'Бесплатные кредиты выдаются, только если на счету меньше 1450.',
  NOT_ILLEGAL: 'Эта карта сыграна честно.',
  CANNOT_UNDO: 'Вернуть карту уже нельзя.',
  GAME_FINISHED: 'Игра уже закончилась.',
  NOT_A_PLAYER: 'Вы не участвуете в этой игре.',
  PLAYER_NOT_ACTIVE: 'Вы уже вышли из игры.',
  CARD_NOT_IN_HAND: 'Этой карты нет у вас в руке.',
  INVALID_CARD: 'Неизвестная карта.',
  THROW_IN_NOT_ALLOWED: 'Сейчас подкидывать нельзя.',
  INVALID_TARGET: 'Выберите карту на столе.',
  NOTHING_TO_TAKE: 'Брать нечего.',
  CANNOT_PASS: 'Сейчас нельзя сказать «Бито».',
  BAD_ACTION: 'Недопустимое действие.',
  NOT_YOUR_TURN: 'Сейчас не ваш ход.',
  CARD_DOES_NOT_BEAT: 'Этой картой не побить.',
  RANK_NOT_ON_TABLE: 'Подкинуть можно только карту того же достоинства.',
  BOUT_LIMIT_REACHED: 'Больше карт подкинуть нельзя.',
  TRANSFER_NOT_ALLOWED: 'Перевести нельзя.',
};

export function errorText(code: AppErrorCode): string {
  return ERROR_TEXT_RU[code] ?? ERROR_TEXT_RU.SERVER_ERROR!;
}
