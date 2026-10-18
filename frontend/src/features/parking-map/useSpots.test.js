import { describe, expect, it } from "vitest";

import {
  COALESCE_MS,
  POLL_MS,
  RECONNECT_MAX_MS,
  createRequestGate,
  createSpotFeed,
  nextReconnectDelay,
  spotsSocketUrl,
} from "./useSpots.js";

function createClock() {
  let now = 0;
  let seq = 1;
  const queue = [];

  function remove(handle) {
    const index = queue.findIndex((item) => item.handle === handle);
    if (index >= 0) queue.splice(index, 1);
  }

  return {
    setTimeout(fn, ms) {
      const handle = seq;
      seq += 1;
      queue.push({ handle, fn, at: now + ms, every: 0 });
      return handle;
    },
    clearTimeout: remove,
    setInterval(fn, ms) {
      const handle = seq;
      seq += 1;
      queue.push({ handle, fn, at: now + ms, every: ms });
      return handle;
    },
    clearInterval: remove,
    advance(ms) {
      const end = now + ms;
      for (;;) {
        let nextIndex = -1;
        for (let index = 0; index < queue.length; index += 1) {
          if (queue[index].at <= end && (nextIndex < 0 || queue[index].at < queue[nextIndex].at)) {
            nextIndex = index;
          }
        }
        if (nextIndex < 0) break;
        const item = queue[nextIndex];
        now = item.at;
        if (item.every) item.at = now + item.every;
        else queue.splice(nextIndex, 1);
        item.fn();
      }
      now = end;
    },
  };
}

class FakeSocket {
  static opened = [];

  constructor(url) {
    this.url = url;
    this.handlers = {};
    FakeSocket.opened.push(this);
  }

  set onopen(fn) {
    this.handlers.open = fn;
  }

  set onmessage(fn) {
    this.handlers.message = fn;
  }

  set onclose(fn) {
    this.handlers.close = fn;
  }

  open() {
    this.handlers.open?.();
  }

  push(payload) {
    this.handlers.message?.({ data: JSON.stringify(payload) });
  }

  serverClose() {
    this.handlers.close?.();
  }

  close() {
    this.handlers.close?.();
  }
}

const page = { protocol: "http:", host: "localhost:8080" };

function feed(fetchSpots, timers, onStatus = () => {}) {
  return createSpotFeed({
    fetchSpots,
    onStatus,
    WebSocketImpl: FakeSocket,
    location: page,
    timers,
  });
}

describe("spot feed", () => {
  it("builds a same-origin socket url", () => {
    expect(spotsSocketUrl(page)).toBe("ws://localhost:8080/ws/spots/");
    expect(spotsSocketUrl({ protocol: "https:", host: "park.example" })).toBe(
      "wss://park.example/ws/spots/",
    );
  });

  it("waits 1, 2, 4 seconds and then caps at 15", () => {
    expect(nextReconnectDelay(0)).toBe(1000);
    expect(nextReconnectDelay(1)).toBe(2000);
    expect(nextReconnectDelay(2)).toBe(4000);
    expect(nextReconnectDelay(3)).toBe(8000);
    expect(nextReconnectDelay(4)).toBe(RECONNECT_MAX_MS);
  });

  it("polls until the socket opens, then stops", () => {
    FakeSocket.opened = [];
    const calls = [];
    const timers = createClock();
    const statuses = [];
    const live = feed(
      () => calls.push("fetch"),
      timers,
      (status) => statuses.push(status),
    );
    live.start();
    expect(statuses).toEqual(["reconnecting"]);
    timers.advance(POLL_MS);
    expect(calls).toEqual(["fetch"]);
    FakeSocket.opened[0].open();
    expect(statuses.at(-1)).toBe("online");
    expect(calls).toEqual(["fetch", "fetch"]);
    timers.advance(POLL_MS * 3);
    expect(calls).toEqual(["fetch", "fetch"]);
    live.stop();
  });

  it("reconnects with a growing pause and reads spots again on open", () => {
    FakeSocket.opened = [];
    const calls = [];
    const timers = createClock();
    const live = feed(() => calls.push("fetch"), timers);
    live.start();
    FakeSocket.opened[0].open();
    calls.length = 0;
    FakeSocket.opened[0].serverClose();
    timers.advance(999);
    expect(FakeSocket.opened).toHaveLength(1);
    timers.advance(1);
    expect(FakeSocket.opened).toHaveLength(2);
    FakeSocket.opened[1].open();
    expect(calls).toEqual(["fetch"]);
    live.stop();
  });

  it("groups a burst of signals into one reload", () => {
    FakeSocket.opened = [];
    const calls = [];
    const timers = createClock();
    const live = feed(() => calls.push("fetch"), timers);
    live.start();
    FakeSocket.opened[0].open();
    calls.length = 0;
    FakeSocket.opened[0].push({ type: "spots.changed" });
    timers.advance(100);
    FakeSocket.opened[0].push({ type: "spots.changed" });
    timers.advance(COALESCE_MS - 1);
    expect(calls).toEqual([]);
    timers.advance(1);
    expect(calls).toEqual(["fetch"]);
    live.stop();
  });

  it("does not reconnect or reload after stop", () => {
    FakeSocket.opened = [];
    const calls = [];
    const timers = createClock();
    const live = feed(() => calls.push("fetch"), timers);
    live.start();
    FakeSocket.opened[0].open();
    FakeSocket.opened[0].push({ type: "spots.changed" });
    live.stop();
    timers.advance(RECONNECT_MAX_MS * 2);
    expect(FakeSocket.opened).toHaveLength(1);
    expect(calls).toEqual(["fetch"]);
  });

  it("ignores a response that is no longer current", () => {
    const gate = createRequestGate();
    const first = gate.issue();
    const second = gate.issue();
    expect(gate.accept(first)).toBe(false);
    expect(gate.accept(second)).toBe(true);
    gate.close();
    expect(gate.accept(second)).toBe(false);
  });
});
