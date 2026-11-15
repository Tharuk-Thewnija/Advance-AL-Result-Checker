"""One paid job at a time; uncertain billing disables further automatic calls."""
import re
import time

from .budget import LimitReached, ChargeUnconfirmed
from .client import ServiceError


class Interrupted(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class Solver:
    def __init__(self, client, budget, notify):
        self.client, self.budget, self.notify = client, budget, notify
        self.solution_meta = {}
        self.last_charge = 0

    def update(self, **extra):
        self.notify(dict(self.budget.snapshot(), **extra))

    def controls(self, stop, skip):
        if stop.is_set(): raise Interrupted('stop')
        if skip.is_set():
            skip.clear()
            raise Interrupted('skip')

    def receipt(self, job, reply):
        terminal_states = ('solved', 'failed', 'expired', 'cancelled')
        if reply.get('id') != job or reply.get('status') not in terminal_states:
            self.budget.uncertain()
            raise ChargeUnconfirmed('The final charge could not be confirmed. Automatic mode is paused.')
        credits = reply.get('credits_charged')
        if type(credits) is not int or credits < 0:
            # Read the SAME job once; never create another paid solve to repair
            # a receipt that arrived before its charge was populated.
            try:
                fresh = self.client.get(job)
            except ServiceError:
                fresh = None
            if isinstance(fresh,dict) and fresh.get('id')==job and fresh.get('status') in terminal_states:
                reply = fresh
                credits = reply.get('credits_charged')
            if type(credits) is not int or credits < 0:
                self.budget.uncertain()
                raise ChargeUnconfirmed(f"NoneCAP reported {reply['status']}, but its final charge could not be confirmed after rechecking the same job. Automatic collection is paused.")
        # Missing costs are never treated as free, even on failed jobs.
        self.budget.settle(job, credits)
        self.last_charge = credits
        self.update()
        return reply

    def cancel(self, job):
        try:
            try:
                reply = self.client.cancel(job)
            except ServiceError as exc:
                if exc.code != 'conflict': raise
                reply = self.client.get(job)
            self.receipt(job, reply)
        except (ServiceError, LimitReached, TypeError, AttributeError):
            self.budget.uncertain()
        self.update()

    def solve(self, widget, stop, skip, *, timeout=120):
        self.budget.check()
        self.controls(stop, skip)
        balance = self.client.balance()
        self.update(**balance)
        if balance['balance'] <= 0 and balance['plan_remaining'] <= 0:
            raise ServiceError('insufficient_credits')
        self.controls(stop, skip)
        self.budget.reserve()
        self.update(status='Requesting one automatic solve…')
        job, terminal = None, False
        try:
            reply = self.client.create(widget['sitekey'], rqdata=widget.get('rqdata', ''),
                                       enterprise=widget.get('enterprise', False), user_agent=widget.get('user_agent', ''))
            job = reply.get('id')
            if not isinstance(job, str) or not re.fullmatch(r'solve_[A-Za-z0-9_-]{1,96}', job):
                job = None
                self.budget.uncertain()
                raise ServiceError('invalid_response', uncertain=True)
            deadline = time.monotonic() + timeout
            while True:
                self.controls(stop, skip)
                if reply.get('status') in ('solved', 'failed', 'expired', 'cancelled'):
                    terminal = True
                    reply = self.receipt(job, reply)
                    token = reply.get('token')
                    if reply['status'] != 'solved' or not isinstance(token, str) or not 0 < len(token) <= 65536:
                        raise ServiceError('solve_failed')
                    self.update(status='Automatic solve received; submitting the form…')
                    self.solution_meta = {name: reply.get(name) for name in ('resp_key', 'user_agent')
                                          if isinstance(reply.get(name), str)}
                    return token
                if reply.get('status') not in ('pending', 'solving'):
                    raise ServiceError('invalid_response')
                if time.monotonic() >= deadline:
                    raise ServiceError('solve_timeout')
                stop.wait(min(.5, max(0, deadline - time.monotonic())))
                self.controls(stop, skip)
                reply = self.client.get(job)
        except (Interrupted, ServiceError, LimitReached) as exc:
            if job and not terminal:
                self.cancel(job)
            elif isinstance(exc, ServiceError) and exc.uncertain:
                self.budget.uncertain()
            self.update()
            raise
