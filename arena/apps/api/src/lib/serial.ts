/**
 * Runs async jobs one after another. Every room and every game owns one, so two
 * messages that arrive at the same time can never interleave their awaits.
 */
export class SerialQueue {
  private tail: Promise<unknown> = Promise.resolve();

  run<T>(job: () => Promise<T> | T): Promise<T> {
    const result = this.tail.then(job, job);
    this.tail = result.catch(() => undefined);
    return result;
  }
}
