import { EMPTY_FILTER, formatStake, MODE_LABEL_RU, MODE_PAIRS, STAKE_OPTIONS, type GameMode } from '@arena/shared';
import { Button, CurrencyIcon, Icon } from '@arena/ui';
import { setLobbyFilter, useLobbyFilter } from '../lib/lobbyFilter.js';
import { useNav } from '../navigation.js';
import { ScreenHeader } from './common.js';
import { CheckTile, MODE_ICON, ScriptTitle, Segmented, StakeRange } from './lobbyParts.js';

function toggle<T>(list: readonly T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

const LOWEST = STAKE_OPTIONS[0];
const HIGHEST = STAKE_OPTIONS[STAKE_OPTIONS.length - 1]!;

/** Filter for «Открытые игры». Nothing ticked in a group means «любые». */
export default function FiltersScreen() {
  const [filter] = useLobbyFilter();
  const { back } = useNav();
  const set = (patch: Partial<typeof filter>) => setLobbyFilter({ ...filter, ...patch });
  const min = filter.stakeMin ?? LOWEST;
  const max = filter.stakeMax ?? HIGHEST;

  return (
    <div className="app-stack felt-form">
      <ScreenHeader
        title="Фильтры"
        action={
          <button type="button" className="app-bar__action" onClick={() => setLobbyFilter(EMPTY_FILTER)}>
            Сбросить
          </button>
        }
      />

      <section className="felt-section">
        <ScriptTitle>Ставка</ScriptTitle>
        <p className="felt-value">
          {formatStake(min)} – {formatStake(max)} <CurrencyIcon kind="credits" size={20} />
        </p>
        <StakeRange
          min={min}
          max={max}
          onChange={(lo, hi) => set({ stakeMin: lo === LOWEST ? undefined : lo, stakeMax: hi === HIGHEST ? undefined : hi })}
        />
      </section>

      <section className="felt-section">
        <ScriptTitle>Игроки</ScriptTitle>
        <Segmented label="Игроки" options={[2, 3, 4, 5, 6] as const} value={filter.players} onToggle={(v) => set({ players: toggle(filter.players, v) })} />
      </section>

      <div className="felt-pair">
        <section className="felt-section">
          <ScriptTitle>Колода</ScriptTitle>
          <Segmented label="Колода" options={[24, 36, 52] as const} value={filter.deckSizes} onToggle={(v) => set({ deckSizes: toggle(filter.deckSizes, v) })} />
        </section>
        <section className="felt-section">
          <ScriptTitle>Скорость</ScriptTitle>
          <Segmented
            label="Скорость"
            options={['normal', 'fast'] as const}
            value={filter.speeds}
            render={(v) => <Icon name={v === 'fast' ? 'speedFast' : 'speedNormal'} size={20} aria-label={v === 'fast' ? 'Быстрая' : 'Обычная'} />}
            onToggle={(v) => set({ speeds: toggle(filter.speeds, v) })}
          />
        </section>
      </div>

      <section className="felt-section">
        <ScriptTitle>Режимы игры</ScriptTitle>
        <div className="check-grid">
          {MODE_PAIRS.flat().map((mode: GameMode) => (
            <CheckTile key={mode} icon={MODE_ICON[mode]} label={MODE_LABEL_RU[mode]!} on={filter.modes.includes(mode)} onClick={() => set({ modes: toggle(filter.modes, mode) })} />
          ))}
        </div>
        <p className="app-muted">Отметьте оба режима пары, если подходят оба.</p>
      </section>

      <Button variant="primary" block onClick={back}>
        Показать столы
      </Button>
    </div>
  );
}
