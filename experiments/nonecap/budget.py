"""Window-session soft credit threshold and strict submission-count limit."""
import threading


class LimitReached(Exception):
    pass


class Budget:
    def __init__(self, credit_limit=10, max_attempts=3):
        self.lock = threading.RLock()
        self.spent = self.attempts = 0
        self.blocked = False
        self.receipts = set()
        self.configure(credit_limit, max_attempts)

    def configure(self, credit_limit, max_attempts):
        if type(credit_limit) is not int or not 1 <= credit_limit <= 100000:
            raise ValueError('Enter a credit threshold between 1 and 100,000.')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 1000:
            raise ValueError('Enter an automatic-attempt limit between 1 and 1,000.')
        with self.lock:
            self.credit_limit = credit_limit; self.max_attempts = max_attempts

    def check(self):
        with self.lock:
            if self.blocked: raise LimitReached('Charge could not be confirmed. Automatic mode is paused for this session.')
            if self.spent >= self.credit_limit: raise LimitReached('Session credit threshold reached. Continue manually.')
            if self.attempts >= self.max_attempts: raise LimitReached('Session automatic-attempt limit reached. Continue manually.')

    def reserve(self):
        with self.lock:
            self.check(); self.attempts += 1

    def settle(self, job, credits):
        with self.lock:
            if job in self.receipts: return
            if type(credits) is not int or credits < 0:
                self.uncertain(); raise LimitReached('NoneCAP did not confirm the charge. Automatic mode is paused.')
            self.receipts.add(job); self.spent += credits

    def uncertain(self):
        with self.lock:
            self.blocked = True

    def snapshot(self):
        with self.lock:
            return dict(spent=self.spent, attempts=self.attempts, blocked=self.blocked,
                        credit_limit=self.credit_limit, max_attempts=self.max_attempts)
