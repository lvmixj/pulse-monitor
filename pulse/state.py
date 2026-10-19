"""Monitoring data and pause state, independent of Qt and appearance."""
from collections import deque


class MonitorState:
    def __init__(self):
        self.latest = None
        self.history = deque(maxlen=900)
        self.paused = False
        self.frozen = None
        self.frozen_history = None

    @property
    def display(self):
        return self.frozen if self.paused else self.latest

    def receive(self, sample):
        self.latest = sample
        self.history.append(dict(time=sample['time'], cpu=sample['cpu'], memory=sample['memory']['percent'],
                                 gpu=sample['gpus'][0]['usage'] if sample['gpus'] else None,
                                 read=sample['disk']['read'], write=sample['disk']['write'],
                                 down=sample['network']['down'], up=sample['network']['up']))
        while self.history and sample['time']-self.history[0]['time'] > 300:
            self.history.popleft()

    def toggle_pause(self):
        # A pause always represents an actual sample, never an empty startup state.
        if self.latest is None:
            return
        self.paused = not self.paused
        self.frozen = self.latest if self.paused else None
        self.frozen_history = deque(self.history) if self.paused else None
