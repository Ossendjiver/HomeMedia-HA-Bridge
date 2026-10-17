import asyncio
import unittest
from custom_components.home_media_bridge.routing_lease import RoutingLease, LeaseBusy, LeaseLost

class LeaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now=0.;self.busy=False
        self.lease=RoutingLease(lambda:self.busy,clock=lambda:self.now)
        self.owner='backend-0123456789012345'
    async def test_exclusion_and_no_foreign_release(self):
        await self.lease.acquire(self.owner)
        with self.assertRaises(LeaseBusy):await self.lease.acquire('another-0123456789012345')
        self.assertFalse(await self.lease.release('another-0123456789012345'))
        self.assertTrue(self.lease.state()['active'])
    async def test_legacy_guard_and_expiry(self):
        self.busy=True
        with self.assertRaises(LeaseBusy):await self.lease.acquire(self.owner)
        self.busy=False;await self.lease.acquire(self.owner);self.now=31
        with self.assertRaises(LeaseLost):await self.lease.renew(self.owner)
        await self.lease.expire();self.assertFalse(self.lease.state()['active'])
    async def test_bound_lifetime(self):
        await self.lease.acquire(self.owner)
        for i in range(1,18):self.now=i*10;await self.lease.renew(self.owner)
        self.now=180
        with self.assertRaises(LeaseLost):await self.lease.renew(self.owner)
    async def test_settling_does_not_block_explicit_next_command(self):
        await self.lease.acquire(self.owner);await self.lease.release(self.owner)
        self.assertFalse(self.lease.state()['active']);self.assertTrue(self.lease.state()['settling'])
        await self.lease.acquire('next-job-0123456789012345')
        self.assertTrue(self.lease.state()['active'])
    async def test_legacy_routes_do_not_suppress_physical_followup(self):
        owner='ha-012345678901234567890'
        await self.lease.acquire(owner);await self.lease.release(owner)
        self.assertFalse(self.lease.state()['settling'])
    async def test_context_cleanup_on_cancel(self):
        entered=asyncio.Event()
        async def run():
            async with self.lease.hold(self.owner):entered.set();await asyncio.Event().wait()
        task=asyncio.create_task(run());await entered.wait();task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        self.assertFalse(self.lease.state()['active'])
