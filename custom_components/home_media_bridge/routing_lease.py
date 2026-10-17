"""HA-local fencing for backend jobs and legacy router scripts. No disk polling."""
from __future__ import annotations
import asyncio
import re
import time
from contextlib import asynccontextmanager

OWNER = re.compile(r"[A-Za-z0-9_-]{16,96}\Z")
class LeaseBusy(RuntimeError): pass
class LeaseLost(RuntimeError): pass

class RoutingLease:
    def __init__(self, legacy_busy, notify=lambda: None, clock=time.monotonic):
        self.legacy_busy, self.notify, self.clock = legacy_busy, notify, clock
        self.lock = asyncio.Lock(); self.owner = None; self.expires = 0.; self.started = 0.; self.settling_until = 0.
    def state(self):
        active = self.owner is not None and self.clock() < self.expires
        return {"active": active, "owner": self.owner if active else None,
            "settling": self.clock() < self.settling_until,
            "remaining_seconds": max(0, round(self.expires-self.clock(), 1)) if active else 0}
    async def acquire(self, owner):
        if not isinstance(owner,str) or not OWNER.fullmatch(owner): raise ValueError("Invalid lease owner")
        async with self.lock:
            if self.legacy_busy(): raise LeaseBusy("A legacy route or HA operation is already running")
            state = self.state()
            if state["active"] and state["owner"] != owner: raise LeaseBusy("Another playback operation holds the lease")
            if not state["active"]: self.started = self.clock()
            self.owner = owner; self.expires = min(self.clock()+30, self.started+180)
            self.notify(); return self.state()
    async def renew(self, owner):
        async with self.lock:
            if not self.state()["active"] or self.owner != owner: raise LeaseLost("Routing lease no longer belongs to this job")
            # Existing scripts owned by this lease are expected to be running;
            # an old app's boolean is handled by the HA adapter separately.
            if self.clock()-self.started >= 180: raise LeaseLost("Routing lease exceeded its maximum lifetime")
            self.expires = min(self.clock()+30,self.started+180); self.notify(); return self.state()
    async def release(self, owner):
        async with self.lock:
            if self.owner != owner: return False
            if not owner.startswith("ha-"): self.settling_until = self.clock()+20
            self.owner = None; self.expires = 0.; self.notify(); return True
    async def expire(self):
        async with self.lock:
            if self.owner and not self.state()["active"]:
                self.owner = None; self.expires = 0.; self.notify()
    @asynccontextmanager
    async def hold(self, owner):
        await self.acquire(owner)
        parent=asyncio.current_task(); lost=False
        async def renewer():
            nonlocal lost
            try:
                while True:
                    await asyncio.sleep(10); await self.renew(owner)
            except asyncio.CancelledError: raise
            except Exception:
                lost=True
                if parent:parent.cancel()
        task = asyncio.create_task(renewer())
        try:
            yield
            if lost:raise LeaseLost("Legacy routing lease renewal failed")
        except asyncio.CancelledError:
            if lost:raise LeaseLost("Legacy routing cancelled after lease loss") from None
            raise
        finally:
            task.cancel(); await asyncio.gather(task,return_exceptions=True)
            await self.release(owner)
