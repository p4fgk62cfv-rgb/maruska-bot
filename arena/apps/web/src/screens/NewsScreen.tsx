import { useState } from 'react';
import { markNewsSeen, NEWS, newsDate } from '../lib/news.js';
import { ScreenHeader } from './common.js';

/** «Новости»: what changed in the Arena, day by day, newest first. */
export default function NewsScreen() {
  // Read once on entry: what was new stays marked while the player reads.
  const [seenBefore] = useState(markNewsSeen);
  return (
    <div className="app-stack news">
      <ScreenHeader title="Новости" />
      <section className="news-hero">
        <span className="news-hero__icon" aria-hidden="true">📰</span>
        <strong>Что нового в Арене</strong>
        <span>Все обновления, улучшения и новинки — по дням, от свежих к первым.</span>
      </section>
      {NEWS.map((day, i) => {
        const fresh = day.id > seenBefore;
        return (
          <article key={day.id} className={`news-day${i === 0 ? ' news-day--latest' : ''}`}>
            <header className="news-day__head">
              <span className="news-day__date">{newsDate(day.date)}</span>
              {fresh && <span className="news-day__new">новое</span>}
            </header>
            <h3 className="news-day__headline">{day.headline}</h3>
            <ul className="news-day__items">
              {day.items.map((item) => (
                <li key={item.title} className="news-item">
                  <span className="news-item__emoji" aria-hidden="true">{item.emoji}</span>
                  <span className="news-item__body">
                    <strong>{item.title}</strong>
                    <span>{item.text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </article>
        );
      })}
      <p className="news-foot">Маруська Арена · спасибо, что играете с нами ♥</p>
    </div>
  );
}
