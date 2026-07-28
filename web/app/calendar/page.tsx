import type { Metadata } from 'next';
import { formatWhen, getCalendar, type CalendarItem } from '@/lib/api';

export const metadata: Metadata = {
  title: 'Calendar',
  description:
    'Upcoming Golden Opportunities for Independence training sessions and volunteer shifts, in one place.',
};

// Public content must reflect live scheduling.
export const dynamic = 'force-dynamic';

// --- Date helpers -----------------------------------------------------------
// The API returns naive-UTC ISO strings. We parse them exactly the way
// formatWhen already does (new Date(...) → local rendering) so day grouping and
// the month grid stay consistent with the times shown on every other page.

const WEEKDAY_HEADERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// Local Y-M-D key for grouping (avoids UTC/local drift between grid and list).
function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function monthKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}`;
}

// Monday-first weekday index (0 = Monday … 6 = Sunday) to match en-GB.
function mondayIndex(d: Date): number {
  return (d.getDay() + 6) % 7;
}

function formatDayHeading(d: Date): string {
  return d.toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function formatMonthTitle(d: Date): string {
  return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
}

interface DatedItem extends CalendarItem {
  start: Date;
}

export default async function CalendarPage() {
  let items: CalendarItem[] | null = null;
  let loadError = false;

  try {
    items = await getCalendar();
  } catch {
    loadError = true;
  }

  // Parse + drop anything unparseable so a bad row can't break the page.
  const dated: DatedItem[] = (items ?? [])
    .map((it) => ({ ...it, start: new Date(it.starts_at) }))
    .filter((it) => !Number.isNaN(it.start.getTime()));

  // Group by calendar day for the accessibility-first upcoming list.
  const byDay = new Map<string, DatedItem[]>();
  for (const it of dated) {
    const key = dayKey(it.start);
    const bucket = byDay.get(key);
    if (bucket) bucket.push(it);
    else byDay.set(key, [it]);
  }
  const dayGroups = Array.from(byDay.values()); // API is pre-sorted by start.

  // Group by month for the month-grid enhancement.
  const monthOrder: string[] = [];
  const byMonth = new Map<string, DatedItem[]>();
  for (const it of dated) {
    const key = monthKey(it.start);
    const bucket = byMonth.get(key);
    if (bucket) {
      bucket.push(it);
    } else {
      byMonth.set(key, [it]);
      monthOrder.push(key);
    }
  }

  const todayKey = dayKey(new Date());

  return (
    <div className="container page">
      <h1>What&rsquo;s coming up</h1>
      <p className="lede">
        Every upcoming training session and volunteer shift, in date order. The
        list below is the quickest way to scan — the month grids underneath give
        you the bigger picture.
      </p>

      <ul className="cal-legend" aria-hidden="true">
        <li>
          <span className="cal-dot cal-dot-training" />
          Training
        </li>
        <li>
          <span className="cal-dot cal-dot-opportunity" />
          Volunteer shift
        </li>
      </ul>

      {loadError && (
        <div className="alert alert-danger" role="alert">
          <strong>We couldn&rsquo;t load the calendar right now.</strong>
          <p>
            Please refresh the page in a moment. If it keeps happening, email{' '}
            <a href="mailto:contact@gofidog.org">
              contact@gofidog.org
            </a>
            .
          </p>
        </div>
      )}

      {!loadError && dated.length === 0 && (
        <div className="empty">
          <div className="empty-icon" aria-hidden="true">
            📅
          </div>
          <h2>Nothing on the calendar yet</h2>
          <p>
            No upcoming sessions or shifts right now — check back soon, or browse
            our trainings.
          </p>
        </div>
      )}

      {!loadError && dated.length > 0 && (
        <>
          {/* Primary, accessibility-first view: grouped by date. */}
          <section aria-labelledby="upcoming-heading" className="section-gap">
            <h2 id="upcoming-heading">Upcoming, in date order</h2>
            {dayGroups.map((group) => {
              const heading = formatDayHeading(group[0].start);
              return (
                <section
                  className="cal-day-group"
                  key={dayKey(group[0].start)}
                  aria-label={heading}
                >
                  <h3 className="cal-day-heading">{heading}</h3>
                  <ul className="cal-items">
                    {group.map((it) => (
                      <li
                        className={`cal-item cal-item-${it.type}`}
                        key={`${it.type}-${it.id}`}
                      >
                        <time
                          className="cal-item-time"
                          dateTime={it.starts_at}
                        >
                          {formatWhen(it.starts_at, it.ends_at)}
                        </time>
                        <div className="cal-item-body">
                          <span className="cal-item-title">{it.title}</span>
                          <span className="cal-item-meta">
                            <span className="cal-type-label">
                              {it.type === 'training'
                                ? 'Training'
                                : 'Volunteer shift'}
                            </span>
                            {it.location && <span>{it.location}</span>}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </section>

          {/* Enhancement: real-table month grid(s). */}
          <section aria-labelledby="grid-heading" className="section-gap">
            <h2 id="grid-heading">Month view</h2>
            {monthOrder.map((mKey) => (
              <MonthGrid
                key={mKey}
                items={byMonth.get(mKey) ?? []}
                todayKey={todayKey}
              />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

// A single month rendered as an accessible <table>. All items passed in belong
// to the same month.
function MonthGrid({
  items,
  todayKey,
}: {
  items: DatedItem[];
  todayKey: string;
}) {
  const first = items[0].start;
  const year = first.getFullYear();
  const month = first.getMonth();

  const firstOfMonth = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const leadingBlanks = mondayIndex(firstOfMonth);

  // Items indexed by day-of-month.
  const byDayNum = new Map<number, DatedItem[]>();
  for (const it of items) {
    const day = it.start.getDate();
    const bucket = byDayNum.get(day);
    if (bucket) bucket.push(it);
    else byDayNum.set(day, [it]);
  }

  // Build a flat list of cells then chunk into weeks of 7.
  type Cell = { day: number | null };
  const cells: Cell[] = [];
  for (let i = 0; i < leadingBlanks; i += 1) cells.push({ day: null });
  for (let d = 1; d <= daysInMonth; d += 1) cells.push({ day: d });
  while (cells.length % 7 !== 0) cells.push({ day: null });

  const weeks: Cell[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  const title = formatMonthTitle(firstOfMonth);

  return (
    <div className="cal-month">
      <table className="cal-grid">
        <caption>{title}</caption>
        <thead>
          <tr>
            {WEEKDAY_HEADERS.map((wd) => (
              <th key={wd} scope="col" abbr={wd}>
                <span aria-hidden="true">{wd}</span>
                <span className="sr-only">{fullWeekday(wd)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, wi) => (
            // eslint-disable-next-line react/no-array-index-key
            <tr key={wi}>
              {week.map((cell, ci) => {
                if (cell.day === null) {
                  return (
                    // eslint-disable-next-line react/no-array-index-key
                    <td key={ci} className="cal-empty" aria-hidden="true" />
                  );
                }
                const cellDate = new Date(year, month, cell.day);
                const isToday = dayKey(cellDate) === todayKey;
                const dayItems = byDayNum.get(cell.day) ?? [];
                const iso = `${year}-${pad(month + 1)}-${pad(cell.day)}`;
                const label = describeCell(cellDate, dayItems);
                return (
                  <td
                    key={ci}
                    className={isToday ? 'cal-cell-today' : undefined}
                    aria-label={label}
                  >
                    <time className="cal-daynum" dateTime={iso}>
                      {cell.day}
                    </time>
                    {dayItems.length > 0 && (
                      <ul className="cal-markers" aria-hidden="true">
                        {dayItems.map((it) => (
                          <li
                            key={`${it.type}-${it.id}`}
                            className={`cal-marker cal-marker-${it.type}`}
                          />
                        ))}
                      </ul>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function fullWeekday(short: string): string {
  const map: Record<string, string> = {
    Mon: 'Monday',
    Tue: 'Tuesday',
    Wed: 'Wednesday',
    Thu: 'Thursday',
    Fri: 'Friday',
    Sat: 'Saturday',
    Sun: 'Sunday',
  };
  return map[short] ?? short;
}

// Screen-reader label for a grid cell: the date plus a count of what's on.
function describeCell(date: Date, items: DatedItem[]): string {
  const dateLabel = date.toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  if (items.length === 0) return `${dateLabel}. Nothing scheduled.`;
  const trainings = items.filter((i) => i.type === 'training').length;
  const shifts = items.length - trainings;
  const parts: string[] = [];
  if (trainings > 0) {
    parts.push(`${trainings} ${trainings === 1 ? 'training' : 'trainings'}`);
  }
  if (shifts > 0) {
    parts.push(
      `${shifts} volunteer ${shifts === 1 ? 'shift' : 'shifts'}`,
    );
  }
  return `${dateLabel}. ${parts.join(', ')}.`;
}
