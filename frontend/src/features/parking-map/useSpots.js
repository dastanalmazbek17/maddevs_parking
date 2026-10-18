import { useEffect, useState } from "react";

import { request } from "../../shared/api.js";

export const POLL_MS = 5000;
export const COALESCE_MS = 150;
export const RECONNECT_MAX_MS = 15000;

export function nextReconnectDelay(attempt) {
  const delay = 1000 * 2 ** attempt;
  return delay > RECONNECT_MAX_MS ? RECONNECT_MAX_MS : delay;
}

export function spotsSocketUrl(location) {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws/spots/`;
}

/** Drops a response that finished after a newer request or an unmount. */
export function createRequestGate() {
  let current = 0;
  let alive = true;
  return {
    issue() {
      current += 1;
      return current;
    },
    current() {
      return current;
    },
    accept(id) {
      return alive && id === current;
    },
    close() {
      alive = false;
    },
  };
}

export function createSpotFeed({
  fetchSpots,
  onStatus,
  WebSocketImpl = WebSocket,
  location = globalThis.location,
  timers = globalThis,
}) {
  let stopped = false;
  let socket = null;
  let attempt = 0;
  let reconnectTimer = null;
  let pollTimer = null;
  let coalesceTimer = null;

  function stopPoll() {
    if (pollTimer === null) return;
    timers.clearInterval(pollTimer);
    pollTimer = null;
  }

  function startPoll() {
    if (stopped || pollTimer !== null) return;
    pollTimer = timers.setInterval(() => {
      fetchSpots();
    }, POLL_MS);
  }

  function scheduleFetch() {
    if (stopped) return;
    if (coalesceTimer !== null) timers.clearTimeout(coalesceTimer);
    coalesceTimer = timers.setTimeout(() => {
      coalesceTimer = null;
      fetchSpots();
    }, COALESCE_MS);
  }

  function connect() {
    if (stopped) return;
    const current = new WebSocketImpl(spotsSocketUrl(location));
    socket = current;
    current.onopen = () => {
      if (stopped || socket !== current) return;
      attempt = 0;
      stopPoll();
      onStatus("online");
      fetchSpots();
    };
    current.onmessage = (event) => {
      if (stopped || socket !== current) return;
      let payload = null;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload?.type === "spots.changed") scheduleFetch();
    };
    current.onclose = () => {
      if (stopped || socket !== current) return;
      socket = null;
      onStatus("reconnecting");
      startPoll();
      const delay = nextReconnectDelay(attempt);
      attempt += 1;
      reconnectTimer = timers.setTimeout(connect, delay);
    };
  }

  return {
    start() {
      onStatus("reconnecting");
      startPoll();
      connect();
    },
    stop() {
      stopped = true;
      if (reconnectTimer !== null) timers.clearTimeout(reconnectTimer);
      reconnectTimer = null;
      stopPoll();
      if (coalesceTimer !== null) timers.clearTimeout(coalesceTimer);
      coalesceTimer = null;
      if (socket) {
        const current = socket;
        socket = null;
        current.onopen = null;
        current.onmessage = null;
        current.onclose = null;
        current.close();
      }
    },
  };
}

export function useSpots() {
  const [spots, setSpots] = useState([]);
  const [link, setLink] = useState("reconnecting");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const gate = createRequestGate();
    const load = () => {
      const id = gate.issue();
      request("/api/spots/", { auth: false })
        .then((data) => {
          if (!gate.accept(id)) return;
          setSpots(Array.isArray(data) ? data : []);
          setError("");
          setLoaded(true);
        })
        .catch((err) => {
          if (!gate.accept(id)) return;
          setError(err.message || "Нет связи с сервером.");
          setLoaded(true);
        });
    };

    load();
    const feed = createSpotFeed({
      fetchSpots: load,
      onStatus: (status) => {
        if (gate.accept(gate.current())) setLink(status);
      },
    });
    feed.start();
    return () => {
      gate.close();
      feed.stop();
    };
  }, []);

  return { spots, link, error, loaded };
}
