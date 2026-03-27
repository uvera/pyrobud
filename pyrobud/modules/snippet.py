import asyncio
import re
from typing import ClassVar, Optional

import telethon as tg

from .. import command, module, util

_SNIP_RE = re.compile(r"/([^ ]+?)/")


class SnippetsModule(module.Module):
    name: ClassVar[str] = "Snippet"
    db: util.db.AsyncDB

    async def on_load(self) -> None:
        self.db = self.bot.get_db("snippets")

    async def _expand_snippets(self, orig_text: str) -> str:
        """Replace /name/ tokens using the DB; must run on the event loop (not a thread)."""
        parts: list[str] = []
        last_end = 0
        for m in _SNIP_RE.finditer(orig_text):
            parts.append(orig_text[last_end : m.start()])
            key = m.group(1)
            replacement: Optional[str] = await self.db.get(key)
            if replacement is not None:
                await self.bot.log_stat("replaced")
                parts.append(replacement)
            else:
                parts.append(m.group(0))
            last_end = m.end()
        parts.append(orig_text[last_end:])
        return "".join(parts)

    async def on_message(self, msg: tg.custom.Message) -> None:
        # Don't process snippets from inline bots
        if msg.via_bot_id:
            return

        if msg.out and msg.raw_text:
            orig_text = msg.raw_text

            text = await self._expand_snippets(orig_text)
            text = util.tg.truncate(text)

            if text != orig_text:
                await asyncio.sleep(1)
                await msg.edit(text=text, link_preview=False)

    @command.desc("Save a snippet (fetch: `/snippet/`)")
    @command.usage("[snippet name] [text?, or reply]")
    @command.alias("snippet", "snp")
    async def cmd_snip(self, ctx: command.Context) -> str:
        content = None
        if ctx.msg.is_reply:
            reply_msg = await ctx.msg.get_reply_message()
            content = reply_msg.raw_text

        if not content:
            if len(ctx.args) > 1:
                content = ctx.input[len(ctx.args[0]) :].strip()
            else:
                return "__Reply to a message with text or provide text after snippet name.__"

        name = ctx.args[0]
        await self.db.put(name, content.strip())
        return f"Snippet saved as `{name}`."

    @command.desc("Show all snippets")
    @command.alias("sl", "snl", "spl", "snips", "snippets")
    async def cmd_sniplist(self, ctx: command.Context) -> str:
        snippets = [f"**{key}**" async for key, _ in self.db]

        if snippets:
            return util.text.join_list(("Snippet list:", *snippets))

        return "__No snippets saved.__"

    @command.desc("Delete a snippet")
    @command.usage("[snippet name]")
    @command.alias(
        "ds", "sd", "snd", "spd", "rms", "srm", "rs", "sr", "rmsnip", "delsnip"
    )
    async def cmd_snipdel(self, ctx: command.Context) -> str:
        name = ctx.input

        if not await self.db.has(name):
            return "__That snippet doesn't exist.__"

        await self.db.delete(name)
        return f"Snippet `{name}` deleted."
