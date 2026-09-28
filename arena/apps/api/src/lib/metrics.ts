import { monitorEventLoopDelay } from 'node:perf_hooks';

type Labels = Record<string, string>;

/**
 * Tiny Prometheus registry: counters kept in memory, gauges computed at scrape time.
 * Scraped from /api/internal/metrics (behind INTERNAL_API_SECRET).
 */
export class Metrics {
  private counters = new Map<string, { help: string; values: Map<string, number> }>();
  private readonly loop = monitorEventLoopDelay({ resolution: 20 });

  constructor() {
    this.loop.enable();
  }

  inc(name: string, help: string, labels: Labels = {}, by = 1): void {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = { help, values: new Map() };
      this.counters.set(name, counter);
    }
    const key = labelString(labels);
    counter.values.set(key, (counter.values.get(key) ?? 0) + by);
  }

  render(gauges: Record<string, { help: string; value: number }>): string {
    const lines: string[] = [];
    for (const [name, counter] of this.counters) {
      lines.push(`# HELP ${name} ${counter.help}`, `# TYPE ${name} counter`);
      for (const [labels, value] of counter.values) lines.push(`${name}${labels} ${value}`);
    }
    const memory = process.memoryUsage();
    const all = {
      ...gauges,
      arena_process_resident_memory_bytes: { help: 'Resident memory', value: memory.rss },
      arena_process_heap_used_bytes: { help: 'V8 heap in use', value: memory.heapUsed },
      arena_event_loop_lag_p99_ms: { help: 'Event loop delay, 99th percentile', value: this.loop.percentile(99) / 1e6 },
      arena_uptime_seconds: { help: 'Process uptime', value: Math.round(process.uptime()) },
    };
    for (const [name, gauge] of Object.entries(all)) {
      lines.push(`# HELP ${name} ${gauge.help}`, `# TYPE ${name} gauge`, `${name} ${Number(gauge.value.toFixed(3))}`);
    }
    this.loop.reset();
    return `${lines.join('\n')}\n`;
  }
}

function labelString(labels: Labels): string {
  const entries = Object.entries(labels);
  return entries.length ? `{${entries.map(([k, v]) => `${k}="${v.replace(/"/g, '')}"`).join(',')}}` : '';
}

/** One registry per process. */
export const metrics = new Metrics();
