import asyncio
import re
from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional

import telethon as tg
from telethon.tl.types import PeerUser

from .. import module, util

# Same token pattern as the Snippet module — skip buffering to avoid fighting edits.
_SNIP_TOKEN_RE = re.compile(r"/([^ ]+?)/")


@dataclass
class _MergeBuffer:
    messages: List[tg.custom.Message] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None


class MessageMergeModule(module.Module):
    name: ClassVar[str] = "Message merge"

    _buffers: Dict[int, _MergeBuffer]
    _locks: Dict[int, asyncio.Lock]

    async def on_load(self) -> None:
        self._buffers = {}
        self._locks = {}

    async def on_started(self) -> None:
        if not self._merge_enabled():
            self.log.info(
                "Message merge is disabled — set message_merge = true under [bot] in config.toml."
            )
            return
        scope = self.bot.config["bot"].get("message_merge_scope", "private")
        delay_ms = self.bot.config["bot"].get("message_merge_delay_ms", 1500)
        self.log.info(
            "Message merge active (delay_ms=%s, scope=%r). "
            "Groups/channels need scope \"all\".",
            delay_ms,
            scope,
        )

    def _lock_for(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]

    @staticmethod
    def _coerce_bool(val: object) -> bool:
        if isinstance(val, bool):
            return val
        inner = getattr(val, "value", val)
        if isinstance(inner, bool):
            return inner
        if isinstance(val, str) or isinstance(inner, str):
            s = str(inner if isinstance(inner, str) else val).strip().lower()
            return s in ("true", "1", "yes", "on")
        return bool(val)

    def _merge_enabled(self) -> bool:
        return self._coerce_bool(self.bot.config["bot"].get("message_merge"))

    def _delay_sec(self) -> float:
        raw = self.bot.config["bot"].get("message_merge_delay_ms", 1500)
        try:
            ms = int(raw)
        except (TypeError, ValueError):
            ms = 1500
        return max(0.1, min(60.0, ms / 1000.0))

    def _scope_allows(self, msg: tg.custom.Message) -> bool:
        scope = self.bot.config["bot"].get("message_merge_scope", "private")
        if scope == "all":
            return True
        if scope != "private":
            self.log.warning(
                "Invalid message_merge_scope %r; using private", scope
            )
        priv = getattr(msg, "is_private", None)
        if priv is True:
            return True
        if priv is False:
            return False
        return isinstance(getattr(msg, "peer_id", None), PeerUser)

    def _is_command_line(self, text: str) -> bool:
        # Match command_dispatcher.command_predicate: empty prefix would make
        # startswith("") true for every line and block merging entirely.
        prefix = self.bot.prefix
        if not prefix:
            return False
        return bool(text and text.startswith(prefix))

    def _has_snippet_tokens(self, text: str) -> bool:
        return _SNIP_TOKEN_RE.search(text) is not None

    def _is_own_outgoing_line(self, msg: tg.custom.Message) -> bool:
        """Telethon usually sets out=True for your lines; self-chat / sync can omit it."""
        if msg.out:
            return True
        uid = getattr(self.bot, "uid", None)
        if uid is None:
            return False
        if msg.sender_id == uid:
            return True
        peer = getattr(msg, "peer_id", None)
        if isinstance(peer, PeerUser) and peer.user_id == uid:
            return True
        return False

    async def _cancel_timer(self, buf: _MergeBuffer) -> None:
        task = buf.timer_task
        buf.timer_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _flush_buffer_unlocked(self, chat_id: int) -> None:
        buf = self._buffers.get(chat_id)
        if not buf:
            return

        if len(buf.messages) < 2:
            buf.messages.clear()
            return

        messages = list(buf.messages)
        buf.messages.clear()

        combined = "\n".join(m.raw_text or "" for m in messages)
        combined = util.tg.truncate(combined)
        first = messages[0]
        rest = messages[1:]

        try:
            # Plain text: avoid client parse_mode mangling merged lines.
            await first.edit(
                combined,
                link_preview=False,
                formatting_entities=[],
            )
        except tg.errors.MessageNotModifiedError:
            pass
        except tg.errors.RPCError as e:
            self.log.warning("Merge edit failed: %s", e)
            try:
                await first.edit(combined, link_preview=False, parse_mode=None)
            except Exception as e2:
                self.log.warning("Merge edit retry (parse_mode=None) failed: %s", e2)
                return

        for m in rest:
            try:
                await m.delete()
            except tg.errors.RPCError as e:
                self.log.debug("Merge delete failed for msg %s: %s", m.id, e)

    async def _schedule_merge(self, chat_id: int) -> None:
        delay = self._delay_sec()
        buf = self._buffers[chat_id]

        await self._cancel_timer(buf)

        async def _run() -> None:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

            lock = self._lock_for(chat_id)
            async with lock:
                buf = self._buffers.get(chat_id)
                if buf is not None:
                    buf.timer_task = None
                await self._flush_buffer_unlocked(chat_id)

        buf.timer_task = asyncio.create_task(_run())

    async def on_message(self, event: tg.events.NewMessage.Event) -> None:
        try:
            await self._handle_new_message(event)
        except Exception:
            self.log.exception("Message merge handler failed")

    async def _handle_new_message(self, event: tg.events.NewMessage.Event) -> None:
        msg = event.message
        if not self._merge_enabled():
            return

        if not self._is_own_outgoing_line(msg):
            return

        if msg.fwd_from:
            return

        body = msg.raw_text
        if not body:
            return

        chat_id = msg.chat_id
        lock = self._lock_for(chat_id)

        if msg.via_bot_id:
            async with lock:
                buf = self._buffers.get(chat_id)
                if buf:
                    await self._cancel_timer(buf)
                await self._flush_buffer_unlocked(chat_id)
            return

        if not self._scope_allows(msg):
            return

        async with lock:
            text = msg.raw_text

            if self._is_command_line(text):
                buf0 = self._buffers.get(chat_id)
                if buf0:
                    await self._cancel_timer(buf0)
                await self._flush_buffer_unlocked(chat_id)
                return

            if self._has_snippet_tokens(text):
                buf0 = self._buffers.get(chat_id)
                if buf0:
                    await self._cancel_timer(buf0)
                await self._flush_buffer_unlocked(chat_id)
                return

            buf = self._buffers.setdefault(chat_id, _MergeBuffer())
            buf.messages.append(msg)
            await self._schedule_merge(chat_id)

    async def on_stop(self) -> None:
        if not getattr(self, "_buffers", None):
            return

        for chat_id in list(self._buffers.keys()):
            lock = self._lock_for(chat_id)
            async with lock:
                buf = self._buffers.get(chat_id)
                if buf:
                    await self._cancel_timer(buf)
                    buf.messages.clear()
