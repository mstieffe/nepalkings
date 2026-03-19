"""Lightweight background wrapper for network polling.

Desktop:  runs the callable in a daemon thread.
Web/emscripten:  fires async XMLHttpRequests so the browser event-loop
                 is never blocked.  Results are checked each frame.

Usage:

    poller = BackgroundPoller(my_fetch_function, args=(game_id,))
    # In your game loop:
    poller.poll()             # kicks off work if none is running
    if poller.has_result():   # non-blocking check
        data = poller.result  # latest result
"""
import sys as _sys
import threading

_IS_EMSCRIPTEN = _sys.platform == "emscripten"


class BackgroundPoller:
    """Run a callable in a daemon thread; cache the latest result."""

    def __init__(self, func, args=(), kwargs=None):
        self._func = func
        self._args = args
        self._kwargs = kwargs or {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._result = None
        self._has_result = False
        self._busy = False
        # Async-XHR state (emscripten only)
        self._pending_rids: dict | None = None

    # ── public api ──────────────────────────────────────────────

    def poll(self, args=None, kwargs=None):
        """Start a background fetch if one isn't already running."""
        with self._lock:
            if self._busy:
                # On emscripten, check pending async requests each call
                if _IS_EMSCRIPTEN and self._pending_rids is not None:
                    self._check_async_results()
                return
            self._busy = True

        a = args if args is not None else self._args
        kw = kwargs if kwargs is not None else self._kwargs

        if _IS_EMSCRIPTEN:
            # Use async XHR only for the game-state poller (fetch_server_data)
            fname = getattr(self._func, '__name__', '')
            if fname == 'fetch_server_data':
                self._start_async_poll(a, kw)
            else:
                self._run(a, kw)
        else:
            try:
                t = threading.Thread(target=self._run, args=(a, kw), daemon=True)
                t.start()
            except RuntimeError:
                self._run(a, kw)

    def has_result(self):
        """Return True if a new result is available since the last read."""
        # Drive the async state machine when polled for results
        if _IS_EMSCRIPTEN and self._pending_rids is not None:
            self._check_async_results()
        return self._has_result

    @property
    def result(self):
        """Return the latest result and clear the *has_result* flag."""
        with self._lock:
            self._has_result = False
            return self._result

    @property
    def busy(self):
        if _IS_EMSCRIPTEN and self._pending_rids is not None:
            self._check_async_results()
        return self._busy

    # ── internals (threaded, desktop) ───────────────────────────

    def _run(self, args, kwargs):
        try:
            res = self._func(*args, **kwargs)
            with self._lock:
                self._result = res
                self._has_result = True
        except Exception as e:
            print(f"[BackgroundPoller] {self._func.__name__}: {e}")
        finally:
            with self._lock:
                self._busy = False

    # ── internals (async XHR, emscripten) ───────────────────────

    def _start_async_poll(self, args, _kwargs):
        """Fire all GET requests in parallel using async XHR."""
        from utils.http_compat import start_async_get
        from config import settings

        game_id = args[0] if args else None
        if game_id is None:
            # Not a game poll — fall back to synchronous
            self._run(args, _kwargs)
            return

        base = settings.SERVER_URL
        self._pending_rids = {
            'game': start_async_get(f'{base}/games/get_game', {'game_id': game_id}),
            'logs': start_async_get(f'{base}/msg/get_log_entries', {'game_id': game_id}),
            'chats': start_async_get(f'{base}/msg/get_chat_messages', {'game_id': game_id}),
            'spells': start_async_get(f'{base}/spells/get_active_spells', {'game_id': game_id}),
        }
        self._pending_game_id = game_id
        self._async_responses: dict = {}
        self._phase = 1  # phase 1 = main requests, phase 2 = figure requests

    def _check_async_results(self):
        """Poll pending async XHR requests; assemble result when all done."""
        from utils.http_compat import check_async, start_async_get
        from config import settings

        if self._pending_rids is None:
            return

        still_pending = {}
        for key, rid in self._pending_rids.items():
            resp = check_async(rid)
            if resp is None:
                still_pending[key] = rid
            else:
                self._async_responses[key] = resp

        if still_pending:
            self._pending_rids = still_pending
            return

        if self._phase == 1:
            # Phase 1 done — fire figure requests for each player
            game_resp = self._async_responses.get('game')
            if game_resp and game_resp.status_code == 200:
                game_dict = game_resp.json().get('game')
                if game_dict:
                    base = settings.SERVER_URL
                    fig_rids = {}
                    for player in game_dict.get('players', []):
                        pid = player['id']
                        key = f'figures_{pid}'
                        fig_rids[key] = start_async_get(
                            f'{base}/figures/get_figures', {'player_id': pid})
                    if fig_rids:
                        self._pending_rids = fig_rids
                        self._phase = 2
                        return

            # No figures to fetch or game failed — go straight to assembly
            self._pending_rids = None
            self._finish_async()
        else:
            # Phase 2 done — all figure requests complete
            self._pending_rids = None
            self._finish_async()

    def _finish_async(self):
        """Assemble the combined result and mark as ready."""
        try:
            result = self._assemble_server_data()
            with self._lock:
                self._result = result
                self._has_result = True
        except Exception as e:
            print(f"[BackgroundPoller] async assemble: {e}")
        finally:
            with self._lock:
                self._busy = False

    def _assemble_server_data(self):
        """Build the dict that ``Game.apply_server_data`` expects."""
        r = self._async_responses

        game_resp = r.get('game')
        if not game_resp or game_resp.status_code != 200:
            return None

        game_dict = game_resp.json().get('game')
        if not game_dict:
            return None

        logs_resp = r.get('logs')
        logs = logs_resp.json().get('log_entries', []) if logs_resp and logs_resp.status_code == 200 else []

        chats_resp = r.get('chats')
        chats = chats_resp.json().get('chat_messages', []) if chats_resp and chats_resp.status_code == 200 else []

        spells_resp = r.get('spells')
        active_spells = spells_resp.json().get('active_spells', []) if spells_resp and spells_resp.status_code == 200 else []

        # Collect figure responses from phase-2 async requests
        figures_by_player = {}
        for player in game_dict.get('players', []):
            pid = player['id']
            fig_resp = r.get(f'figures_{pid}')
            if fig_resp and fig_resp.status_code == 200:
                figures_by_player[pid] = fig_resp.json().get('figures', [])
            else:
                figures_by_player[pid] = []

        self._async_responses = {}
        return {
            'game': game_dict,
            'logs': logs,
            'chats': chats,
            'active_spells': active_spells,
            'figures': figures_by_player,
        }
