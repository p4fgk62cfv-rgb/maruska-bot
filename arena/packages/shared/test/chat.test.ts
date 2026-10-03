import { describe, expect, it } from 'vitest';
import { censor, hasLink, isSwear } from '../src/chat.js';

// The same cases as the bot's test_antimat.py: the Arena chat must agree with the bot.
const SWEARS = [
  'ну ты и сука', 'СУКА!!!', 'иди нахуй', 'хуйня какая-то', 'похуй вообще', 'пиздец',
  'распиздяй', 'бля, опять', 'блядь', 'заебал уже', 'ебать ты', 'долбоеб', 'уебок',
  'мудак', 'пидорас', 'ты гандон', 'охуеть', 'выебнулся',
  'xуй', 'cyka', 'сууука', 'х.у.й', 'х у й', 'п.и.з.д.е.ц', 'бляяяяя', 'ХУЙ',
];
const CLEAN = [
  'тебе привет', 'свежий хлеб', 'небо голубое', 'он всё страхует', 'политические дебаты',
  'оскорблять нельзя', 'хулиган', 'сучок на дереве', 'ребята, привет', 'употреблять',
  'колебания', 'психуешь?', 'у меня всё хорошо', 'застрахуемся', 'ухудшение', 'хулить',
  'команда', 'щебетать', 'небольшой', 'учебник', '', '123', 'кто на 10К в переводного?',
];

describe('chat: profanity and links', () => {
  it.each(SWEARS)('hides «%s»', (text) => expect(censor(text)).toContain('***'));
  it.each(CLEAN)('keeps «%s»', (text) => expect(censor(text)).toBe(text));

  it('replaces only the bad word', () => {
    expect(censor('ну ты и сука, играй давай')).toBe('ну ты и ***, играй давай');
    expect(censor('х.у.й тебе')).toBe('*** тебе');
    expect(isSwear('Пиздец')).toBe(true);
  });

  it('finds links', () => {
    for (const t of ['https://x.com', 'заходи t.me/somechannel', 'www.site.org', 'casino-win.ru бонус', 'kazino.xyz']) expect(hasLink(t)).toBe(true);
    for (const t of ['кто на 10К?', 'ставка 2.5К', 'ок. играем', 'привет.всем']) expect(hasLink(t)).toBe(false);
  });
});
